"""낙찰가 예측 휴리스틱.

학습된 ML 모델이 아니라 한국 공·경매 통계상 알려진 두 가지 근거를 결합한
**통계 기반 추정**이다. 사용자에게도 "AI" 라기보다 "통계 추정"으로 표시해야 한다.

1) **유찰 회차별 최저가 감액 규칙** — 온비드는 1회 유찰 시 최저가 10% 감액.
   따라서 N회 유찰 후 최저가 ≈ 감정가 × 0.9^N. 우리는 이 잔존가율을
   '최저가 = 입찰자가 받아들일 수 있는 시작점' 으로 본다.

2) **낙찰가율 (감정가 대비 낙찰가)** — 한국 경매 시장 통계:
   - 아파트 80~90% (서울 90%+)
   - 빌라/다세대 65~75%
   - 토지 50~65%
   - 차회 거듭될수록 낮아짐

3) **시세 보정** — `market_median_price` 있으면 시세에 가중. 시세 자체가
   현재 낙찰가의 강한 신호.

본 모듈은 [감정가, 유찰횟수, 시세, 카테고리] → 3분위(low/median/high) 추정 가격을 돌려준다.
"""
from __future__ import annotations

from typing import Any

# 카테고리별 평균 낙찰가율 (감정가 대비, 첫 회차 기준)
# 한국감정원·지지옥션 통계 보정값. 추후 우리 자체 낙찰결과 수집 시 학습 가능.
_BASE_WIN_RATIO = {
    "apartment": 0.85,   # 아파트/주상복합 (서울 평균 85%)
    "villa": 0.70,       # 빌라/다세대/도시형생활주택
    "officetel": 0.78,   # 오피스텔
    "house": 0.72,       # 단독주택/전원주택
    "land": 0.58,        # 토지/도로/대지
    "share": 0.45,       # 지분 매물 (경쟁 적음 + 환금성 낮음)
    "default": 0.70,
}


def _classify(prop: dict[str, Any]) -> str:
    cat = (prop.get("category") or "") + (prop.get("title") or "")
    if prop.get("building_shared") is True or prop.get("share_yn") == "Y":
        return "share"
    if any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지")):
        return "land"
    if "오피스텔" in cat or "용도복합" in cat:
        return "officetel"
    if "아파트" in cat or "주상복합" in cat:
        return "apartment"
    if "단독주택" in cat or "전원주택" in cat:
        return "house"
    if any(k in cat for k in ("빌라", "다세대", "도시형생활")):
        return "villa"
    return "default"


def predict_price(prop: dict[str, Any]) -> dict[str, Any] | None:
    """감정가/유찰/시세 기반 3분위 추정 낙찰가.

    Returns dict with keys: low / median / high / basis / kind / class.
    감정가가 없으면 None.
    """
    appraisal = prop.get("appraisal_price")
    if not appraisal or appraisal <= 0:
        return None
    appraisal = int(appraisal)

    fail = int(prop.get("fail_count") or 0)
    cls = _classify(prop)
    base = _BASE_WIN_RATIO.get(cls, _BASE_WIN_RATIO["default"])

    # 유찰 1회당 잔존가율 5%p 추가 감액 (시장이 한 차례 외면)
    # 다만 -25%p 까지만 (지나친 감액 방지)
    decay = min(0.05 * fail, 0.25)
    ratio = max(base - decay, 0.30)

    median_by_appraisal = int(appraisal * ratio)

    # 시세/실거래가 보정 — 국토부 실거래가 표본 수(market_sample_count)에 따라
    # 신뢰도 가중치를 동적으로. 표본이 많을수록 시세를 더 신뢰(감정가 의존↓).
    #   0건  → 0    (감정가만)
    #   1~2  → 0.35
    #   3~5  → 0.50
    #   6~9  → 0.60
    #   10+  → 0.70
    market = prop.get("market_median_price")
    market_n = int(prop.get("market_sample_count") or 0)
    market_min = prop.get("market_min_price")
    market_max = prop.get("market_max_price")

    # 지분 물건: 감정가·최저가는 지분 몫(court는 등기부 'M분의 K')이지만 시세(market_*)는
    # 전체 면적(100%) 기준이다. 지분 비율을 곱해 같은 스케일로 맞춰야 블렌딩이 왜곡되지 않는다.
    share_ratio = None
    if prop.get("share_yn") == "Y":
        share_ratio = prop.get("building_share_ratio")
        if share_ratio is None:
            share_ratio = prop.get("land_share_ratio")
    is_share = share_ratio is not None and 0 < share_ratio < 1
    if is_share:
        if market:
            market = market * share_ratio
        if market_min:
            market_min = market_min * share_ratio
        if market_max:
            market_max = market_max * share_ratio

    if market and market > 0 and market_n > 0:
        if market_n >= 10:
            w, confidence = 0.70, "high"
        elif market_n >= 6:
            w, confidence = 0.60, "high"
        elif market_n >= 3:
            w, confidence = 0.50, "medium"
        else:
            w, confidence = 0.35, "low"
        # 낙찰가 ≈ 시세 × 0.85 (시장가보다 다소 저렴하게 낙찰되는 경향)
        market_implied = market * 0.85
        median = int(median_by_appraisal * (1 - w) + market_implied * w)
        basis = (
            f"감정가 잔존가율({int(ratio*100)}%) + 국토부 실거래가 "
            f"{market_n}건 가중({int(w*100)}%)"
            + (f" · 시세 지분 {share_ratio*100:.1f}% 환산" if is_share else "")
        )
    else:
        w, confidence = 0.0, "none"
        median = median_by_appraisal
        basis = f"감정가 잔존가율({int(ratio*100)}%) — 실거래가 표본 없음"

    # 분포(low/high): 신뢰도 낮으면 밴드를 넓혀 불확실성 반영.
    band = 0.10 if confidence in ("high", "medium") else 0.15 if confidence == "low" else 0.18
    low = int(median * (1 - band))
    high = int(median * (1 + band))
    # 실거래가 범위가 있으면 밴드를 현실값으로 클램프 (낙찰가는 시세 범위 × 0.85 안쪽 경향)
    if market_min and market_min > 0 and market_max and market_max > 0:
        low = max(low, int(market_min * 0.70))
        high = min(high, int(market_max * 0.95))
        if low >= high:  # 클램프가 역전되면 중앙값 ±10%로 복귀
            low, high = int(median * 0.90), int(median * 1.10)

    # 현재 최저가 vs 예상 낙찰가 비교 (가드는 하지 않음 — 정보로 노출)
    min_price = prop.get("min_price") or 0
    vs_min_percent: float | None = None
    judgment: str | None = None
    if min_price > 0:
        vs_min_percent = round((median - min_price) / min_price * 100, 1)
        # judgment: 예상값이 최저가보다 낮으면 '고평가' (입찰 비추천), 비슷하면 '적정', 높으면 '저평가'
        if median < min_price * 0.97:
            judgment = "현재 최저가가 예상보다 높음 (다음 회차 대기 고려)"
        elif median > min_price * 1.10:
            judgment = "현재 최저가가 예상보다 낮음 (입찰 경쟁 강할 가능성)"
        else:
            judgment = "최저가 ≈ 예상 낙찰가 (적정 구간)"

    return {
        "low": low,
        "median": median,
        "high": high,
        "basis": basis,
        "kind": cls,
        "base_ratio": round(ratio, 3),
        "fail_count_applied": fail,
        "market_weight": round(w, 2),
        "market_sample_count": market_n,
        "confidence": confidence,
        "vs_min_percent": vs_min_percent,
        "judgment": judgment,
        "disclaimer": (
            "통계 기반 추정값입니다 (AI/ML 아님). "
            "감정가 잔존가율 + 카테고리별 한국 시장 낙찰가율 + 국토부 실거래가 신뢰도 가중. "
            "더 깊은 분석은 상단 'AI 예상가' 버튼을, 실제 입찰은 현장 답사·권리분석을 반영하세요."
        ),
    }
