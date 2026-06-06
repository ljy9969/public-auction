"""국토부 부동산 매매 실거래가 (data.go.kr) — 시세 검증.

Phase 1 (PoC): 오피스텔만. 통계: 중앙값·최저·최고·표본수, 우리 매물 대비 % 차이.
"""
from __future__ import annotations

import logging
import os
import re
import statistics
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE = "https://apis.data.go.kr/1613000"
# 매매 거래 — 카테고리별 엔드포인트
ENDPOINTS = {
    "오피스텔": "RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
    "아파트": "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "연립다세대": "RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "토지": "RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade",
    "단독다가구": "RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade",
}

# 전월세 거래 — 현재 오피스텔만 활성화됨 (확장 가능)
RENT_ENDPOINTS = {
    "오피스텔": "RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent",
}


def _select_endpoints(
    category: str,
    area_m2: float | None = None,
    main_purps: str | None = None,
) -> list[tuple[str, str]]:
    """용도 → 시도할 [(label, endpoint)] 리스트. 첫 항목이 primary(주 용도).

    ★ 경매/공매 카테고리는 부정확하다(건축물대장 업무시설=오피스텔 매물이
       '주거용건물/빌라'로 잡히는 등). 그래서 건축물대장 표제부 주용도
       (main_purps)를 우선 신호로 쓴다.
    ★ 같은 단지가 MOLIT의 여러 데이터셋에 등록된다(예: 청광플러스원큐브가
       [아파트]·[오피스텔] 양쪽). 그래서 주거/업무 소형은 오피스텔·아파트·
       연립다세대를 모두 조회해 단지명 매칭으로 어느 데이터셋이든 잡는다.
       동/지번 폴백(면적 기반)은 호출자가 primary endpoint로 제한한다.
    """
    sig = f"{category or ''} {main_purps or ''}"
    OFFI = ("오피스텔", ENDPOINTS["오피스텔"])
    APT = ("아파트", ENDPOINTS["아파트"])
    RH = ("연립다세대", ENDPOINTS["연립다세대"])
    SH = ("단독다가구", ENDPOINTS["단독다가구"])

    # 토지 먼저 (주거 키워드와 겹치지 않게)
    if any(k in sig for k in ("토지", "도로", "임야", "잡종지", "주차장")) or \
            "전 /" in sig or "답 /" in sig or "대지" in sig:
        return [("토지", ENDPOINTS["토지"])]
    # 업무시설(=오피스텔) / 오피스텔 / 용도복합 → 오피스텔 primary
    if any(k in sig for k in ("오피스텔", "용도복합", "업무시설")):
        return [OFFI, APT, RH]
    # 아파트 / 주상복합
    if "아파트" in sig or "주상복합" in sig:
        return [APT, RH, OFFI]
    # 도시형생활주택·다세대·연립·빌라·공동주택 → 연립다세대 primary
    if any(k in sig for k in ("도시형", "다세대", "연립", "빌라", "공동주택")):
        return [RH, APT, OFFI]
    # 단독/다가구 — 소형은 도시형생활주택 가능성↑ → 여러 데이터셋
    if "단독" in sig or "다가구" in sig:
        if area_m2 is not None and area_m2 <= 60:
            return [SH, RH, OFFI, APT]
        return [SH]
    return []


def _recent_months(n: int = 6, today: date | None = None) -> list[str]:
    """n개월 윈도우 안의 모든 YYYYMM (최신순) — n+1 개 반환.

    n=12, today=2026-06-04 → ['202606', '202605', ..., '202506'] (13개).
    1년 전 같은 달의 거래(예: 25.06.13) 도 1년 윈도우 안이므로 포함되어야
    하는데, 기존 range(n) 은 12개만 돌려 25.06 거래가 누락되던 버그
    (2026-06-04 사용자 보고).
    """
    today = today or date.today()
    out: list[str] = []
    y, m = today.year, today.month
    for _ in range(n + 1):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def fetch_monthly_trades(
    endpoint_path: str, sggCd: str, ymd: str, api_key: str
) -> list[dict[str, Any]]:
    """단일 (시군구, 연월) 매매 거래 페이징 호출."""
    url = f"{BASE}/{endpoint_path}"
    items: list[dict[str, Any]] = []
    page = 1
    try:
        with httpx.Client(timeout=20.0) as c:
            while True:
                r = c.get(
                    url,
                    params={
                        "serviceKey": api_key,
                        "LAWD_CD": sggCd,
                        "DEAL_YMD": ymd,
                        "_type": "json",
                        "numOfRows": "1000",
                        "pageNo": str(page),
                    },
                )
                r.raise_for_status()
                data = r.json()
                header = data.get("response", {}).get("header", {})
                if header.get("resultCode") not in ("00", "000"):
                    logger.debug("realprice header: %s", header)
                    break
                body = data.get("response", {}).get("body", {})
                raw = (body.get("items") or {}).get("item")
                if not raw:
                    break
                if isinstance(raw, dict):
                    raw = [raw]
                items.extend(raw)
                total = int(body.get("totalCount") or 0)
                if len(items) >= total or len(raw) < 1000:
                    break
                page += 1
    except Exception as exc:
        logger.debug("realprice fetch failed: %s", exc)
    return items


def _parse_amount(val: Any) -> int | None:
    """'25,500' (만원) → 255,000,000 (원). None 처리."""
    if val is None:
        return None
    s = str(val).replace(",", "").strip()
    if not s:
        return None
    try:
        return int(float(s)) * 10_000
    except ValueError:
        return None


def _normalize_name(s: str) -> str:
    """단지명 비교용 정규화 — 공백/특수문자 제거, 소문자."""
    return re.sub(r"[\s\-·_/()\[\]]+", "", s or "").lower()


# 같은 단지가 없을 때 '주변'으로 인정할 지번 본번 차이. MOLIT엔 좌표가 없어
# 진짜 반경(m) 대신 지번 본번 근접도를 위치 근사로 사용 (본번은 대체로 순차 배정).
JIBUN_NEAR_BONBUN = 10


def _bonbun(s: Any) -> int | None:
    """주소/지번에서 본번 추출. '...길동 387-5'→387, '179'→179, '179-3'→179."""
    m = re.search(r"(\d+)(?:-\d+)?\s*$", str(s or "").strip())
    return int(m.group(1)) if m else None


def _floor_diff(prop: dict[str, Any], trade: dict[str, Any]) -> int | None:
    """현재 매물 층과 거래 층 차이 (절대값). 둘 중 하나라도 없으면 None."""
    my_floor = None
    title = prop.get("title") or ""
    m = re.search(r"제\s*(\d+)\s*층", title)
    if m:
        my_floor = int(m.group(1))
    t_floor = trade.get("floor")
    if my_floor is None or t_floor is None:
        return None
    try:
        return abs(my_floor - int(t_floor))
    except (ValueError, TypeError):
        return None


def _match(prop: dict[str, Any], trade: dict[str, Any], area_tol: float = 0.10) -> int:
    """매물 vs 거래 유사도 점수 (높을수록 유사). 0이면 같은 동도 아님.

    - 같은 동: +3
    - 같은 단지명 (정규화 매칭): +6
    - 면적 ±10% 이내: +2 (±5% 이내: +3)
    - 같은 층 ±2 이내: +1
    """
    score = 0
    addr = prop.get("address_jibun") or ""
    umd = str(trade.get("umdNm") or "")
    if umd and umd in addr:
        score += 3

    # 단지명 — 공백/특수문자 제거 후 substring 비교
    bld_raw = str(prop.get("building_name") or "").strip()
    cand_raw = str(
        trade.get("offiNm") or trade.get("aptNm") or trade.get("mhouseNm") or ""
    ).strip()
    if not bld_raw:
        # building_name 없으면 title에서 추출 시도 (단지명 토큰)
        title = prop.get("title") or ""
        m = re.search(r"\s([가-힣A-Za-z0-9\-]+(?:오피스텔|아파트|빌라|레지던스|타워|프라자|시티))", title)
        bld_raw = m.group(1) if m else ""
    if bld_raw and cand_raw:
        n_bld = _normalize_name(bld_raw)
        n_cand = _normalize_name(cand_raw)
        if n_cand and (n_cand in n_bld or n_bld in n_cand):
            score += 6

    # 면적 매칭 — 같은 단지일 때 더 엄격하게.
    # ★ 차이 50% 이상이면 다른 평형으로 간주, score=0 강제(매칭 제외).
    # 동만 같은 거래가 16㎡ 도시형생활주택 vs 100㎡ 아파트 처럼 평형 차이가 큰
    # 케이스의 중앙값을 오염시키던 문제 해결 (2026-06-04).
    my_area = prop.get("area_build_m2")
    trade_area = trade.get("excluUseAr") or trade.get("totalFloorAr")
    if my_area and trade_area:
        try:
            my = float(my_area)
            tr = float(trade_area)
            if my > 0:
                ratio = abs(tr - my) / my
                if ratio > 0.5:
                    return 0
                if ratio <= 0.05:
                    score += 3
                elif ratio <= area_tol:
                    score += 2
        except (ValueError, TypeError):
            pass

    # 층수 매칭 (옵셔널 보너스)
    fd = _floor_diff(prop, trade)
    if fd is not None and fd <= 2:
        score += 1

    return score


def estimate_market(prop: dict[str, Any], months: int = 6) -> dict[str, Any] | None:
    """매물 1건의 시세 통계 산출. None이면 데이터 부재.

    반환:
      market_median_price, market_min_price, market_max_price: 원 단위
      market_sample_count: 비교에 사용된 거래 건수
      market_period_months: 조회 윈도우
      market_diff_percent: (최저가 / 중앙값 - 1) * 100. 음수 = 시세보다 저렴
      market_endpoint_label: '오피스텔' 등
      market_samples: 최대 5개 샘플 거래
    """
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        return None

    candidates = _select_endpoints(
        prop.get("category") or "", prop.get("area_build_m2"), prop.get("main_purps")
    )
    if not candidates:
        return None
    primary_label = candidates[0][0]  # 주 용도 endpoint — 동/지번 폴백은 여기로만 제한

    # 시군구코드 — Kakao b_code 앞 5자리에서 추출
    sgg_cd: str | None = None
    # cltr_mnmt_no or 주소로 sggCd 유도
    from scraper.filters.building import _lookup_kakao_address
    kakao_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    addr = prop.get("address_jibun") or ""
    if kakao_key and addr:
        info = _lookup_kakao_address(addr, kakao_key)
        if info:
            b_code = (info.get("b_code") or "").strip()
            if len(b_code) >= 5:
                sgg_cd = b_code[:5]
    if not sgg_cd:
        return None

    # 최근 N개월 거래 모두 수집 — 카테고리에 매칭되는 모든 endpoint 통합.
    # 매칭 통과한 거래에 label 을 같이 박아둠(샘플 출력용).
    all_trades: list[dict[str, Any]] = []
    label_by_trade: dict[int, str] = {}  # id(trade) → label
    for label, endpoint in candidates:
        for ymd in _recent_months(months):
            for t in fetch_monthly_trades(endpoint, sgg_cd, ymd, api_key):
                all_trades.append(t)
                label_by_trade[id(t)] = label
    if not all_trades:
        return None
    # 첫 후보의 라벨을 'primary' 로 사용(샘플 출력 등). 매칭 결과 라벨은 가장
    # 거래가 많이 잡힌 endpoint 로 결정.
    label = candidates[0][0]

    # 매물과 매칭 점수 산출
    scored = [(t, _match(prop, t)) for t in all_trades]
    addr = prop.get("address_jibun") or ""
    my_bonbun = _bonbun(addr)

    def _area_ok(t: dict[str, Any]) -> bool:
        my = prop.get("area_build_m2")
        ta = t.get("excluUseAr") or t.get("totalFloorAr")
        if not my or not ta:
            return False
        try:
            return abs(float(ta) - float(my)) / float(my) <= 0.15
        except (ValueError, TypeError):
            return False

    def _jibun_near(t: dict[str, Any]) -> bool:
        tb = _bonbun(t.get("jibun"))
        return (
            my_bonbun is not None
            and tb is not None
            and abs(tb - my_bonbun) <= JIBUN_NEAR_BONBUN
        )

    # 우선순위:
    #  1) 같은 단지 + 면적 (score≥11)   2) 같은 단지 (score≥9)
    #  3) 인근 지번(본번±N) + 면적 + 같은 동 ← 같은 단지 없을 때 '주변'으로 제한
    #  4) 같은 동 + 면적 (마지막 폴백) — min/max는 이상치 제거(분위수)로 보정
    # ★ 동 only(면적 매칭 없음)는 제거(2026-06-04). dong+area도 동 전체라
    #   범위가 비현실적(1.45~6.23억)이라 3) 인근 지번을 우선 도입(2026-06-05).
    # 단지명 매칭(building)은 어느 데이터셋이든 인정(같은 단지가 아파트·오피스텔
    # 양쪽에 등록될 수 있음). 면적 기반 폴백(jibun/dong)은 다른 용도가 섞이지
    # 않도록 primary endpoint 거래로만 제한.
    def _is_primary(t: dict[str, Any]) -> bool:
        return label_by_trade.get(id(t)) == primary_label

    tier_bld_area = [t for t, s in scored if s >= 11]
    tier_bld = [t for t, s in scored if s >= 9]
    tier_jibun = [
        t for t, s in scored
        if s > 0 and _jibun_near(t) and _area_ok(t) and _is_primary(t)
        and str(t.get("umdNm") or "") and str(t.get("umdNm") or "") in addr
    ]
    tier_dong_area = [t for t, s in scored if s >= 5 and _is_primary(t)]

    if tier_bld_area:
        sample, match_kind = tier_bld_area, "building+area"
    elif tier_bld:
        sample, match_kind = tier_bld, "building"
    elif tier_jibun:
        sample, match_kind = tier_jibun, "jibun"
    elif tier_dong_area:
        sample, match_kind = tier_dong_area, "dong+area"
    else:
        return None

    prices = [_parse_amount(t.get("dealAmount")) for t in sample]
    prices = [p for p in prices if p]
    if not prices:
        return None

    # 시간 가중 중앙값 — 최근 거래에 가중치 부여
    # 각 거래의 거래일을 today와의 일자 차이로 환산 → 가중치 = exp(-days/180)
    import math
    today_ord = date.today().toordinal()
    weighted: list[tuple[int, float]] = []
    for t, p in zip(sample, prices):
        try:
            d = date(int(t["dealYear"]), int(t["dealMonth"]), int(t["dealDay"])).toordinal()
            days_ago = max(0, today_ord - d)
            w = math.exp(-days_ago / 180.0)  # 6개월 반감기
        except (KeyError, ValueError, TypeError):
            w = 0.5
        weighted.append((p, w))
    # 단순 median과 weighted mean 둘 다 산출, weighted를 사용
    weighted.sort(key=lambda x: x[0])
    total_w = sum(w for _, w in weighted)
    acc = 0.0
    weighted_median = weighted[len(weighted) // 2][0]  # fallback
    for p, w in weighted:
        acc += w
        if acc >= total_w / 2:
            weighted_median = p
            break
    median = weighted_median
    # min/max — 절대 극단값 대신 분위수(10~90%)로 이상치 제거. 동 전체 폴백 시
    # 1.45~6.23억 같은 비현실적 범위를 막는다. 표본이 적으면(<10) 절대값 유지.
    ps = sorted(prices)
    if len(ps) >= 10:
        lo_i = int(len(ps) * 0.10)
        hi_i = min(len(ps) - 1, math.ceil(len(ps) * 0.90) - 1)
        min_p, max_p = ps[lo_i], ps[hi_i]
    else:
        min_p, max_p = ps[0], ps[-1]

    # 동 전체(dong+area) 매칭은 다른 단지가 섞여, 분위수 트리밍 후에도 범위가
    # 과대(예: 천호동 청광노블하임 2.4~5.0억)하면 그 매물의 '시세'로 신뢰할 수
    # 없다. max가 min의 1.6배를 넘으면 시세 없음(NULL) 처리 — 같은 단지/인근
    # 지번만 진짜 시세로 인정(사용자 정책 2026-06-05). 단지·지번 매칭은 면제.
    if match_kind == "dong+area" and min_p and max_p and max_p > min_p * 1.6:
        return None

    my_min = prop.get("min_price")
    diff_pct: float | None = None
    if my_min and median:
        diff_pct = round((my_min / median - 1) * 100, 1)

    # 샘플은 거래일 최신순 — 매칭된 전체 사용 (UI에서 스크롤)
    sample_sorted = sorted(
        sample,
        key=lambda t: (t.get("dealYear") or 0, t.get("dealMonth") or 0, t.get("dealDay") or 0),
        reverse=True,
    )

    return {
        "market_median_price": median,
        "market_min_price": min_p,
        "market_max_price": max_p,
        "market_sample_count": len(prices),
        "market_period_months": months,
        "market_diff_percent": diff_pct,
        "market_endpoint_label": label,
        "market_match_kind": match_kind,
        "market_samples": [
            {
                "name": s.get("offiNm") or s.get("aptNm") or s.get("mhouseNm") or "",
                "dong": s.get("umdNm") or "",
                "area_m2": s.get("excluUseAr"),
                "floor": s.get("floor"),
                "deal_amount": _parse_amount(s.get("dealAmount")),
                "deal_date": f"{s.get('dealYear')}-{s.get('dealMonth'):02d}-{s.get('dealDay'):02d}"
                if s.get("dealYear")
                else "",
            }
            for s in sample_sorted
        ],
    }


def apply_realprice(prop: dict[str, Any]) -> dict[str, Any]:
    """post-filter pipeline 통합용. 통계 dict를 prop에 평탄화 저장."""
    stats = estimate_market(prop)
    if not stats:
        return prop
    for k, v in stats.items():
        prop[k] = v
    return prop


def _select_rent_endpoint(category: str) -> tuple[str, str] | None:
    cat = category or ""
    if "오피스텔" in cat or "용도복합" in cat:
        return "오피스텔", RENT_ENDPOINTS["오피스텔"]
    return None


def estimate_rental(prop: dict[str, Any], months: int = 12) -> dict[str, Any] | None:
    """오피스텔 전월세 데이터로 예상 임대 수익률 산출.

    전세는 무시(monthlyRent=0). 월세 거래만 사용.
    수익률 = (월세 × 12) / (매수가 − 평균 보증금) × 100
    """
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        return None

    sel = _select_rent_endpoint(prop.get("category") or "")
    if not sel:
        return None
    label, endpoint = sel

    sgg_cd: str | None = None
    from scraper.filters.building import _lookup_kakao_address

    kakao_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    addr = prop.get("address_jibun") or ""
    if kakao_key and addr:
        info = _lookup_kakao_address(addr, kakao_key)
        if info:
            b_code = (info.get("b_code") or "").strip()
            if len(b_code) >= 5:
                sgg_cd = b_code[:5]
    if not sgg_cd:
        return None

    all_trades: list[dict[str, Any]] = []
    for ymd in _recent_months(months):
        all_trades.extend(fetch_monthly_trades(endpoint, sgg_cd, ymd, api_key))

    # 월세 거래만 + 매칭
    rented = [t for t in all_trades if _parse_amount(t.get("monthlyRent"))]
    if not rented:
        return None

    scored = [(t, _match(prop, t)) for t in rented]
    tier_bld = [t for t, s in scored if s >= 9]
    tier_dong_area = [t for t, s in scored if s >= 5]
    tier_dong = [t for t, s in scored if s >= 3]

    if tier_bld and len(tier_bld) >= 2:
        sample = tier_bld
        match_kind = "building"
    elif tier_dong_area:
        sample = tier_dong_area
        match_kind = "dong+area"
    elif tier_dong:
        sample = tier_dong
        match_kind = "dong"
    else:
        return None

    monthly_amounts = [_parse_amount(t.get("monthlyRent")) for t in sample]
    monthly_amounts = [m for m in monthly_amounts if m]
    deposit_amounts = [_parse_amount(t.get("deposit")) or 0 for t in sample]
    if not monthly_amounts:
        return None

    median_monthly = int(statistics.median(monthly_amounts))
    median_deposit = int(statistics.median(deposit_amounts)) if deposit_amounts else 0

    my_price = prop.get("min_price") or 0
    yield_pct: float | None = None
    if my_price > median_deposit:
        yield_pct = round(median_monthly * 12 / (my_price - median_deposit) * 100, 2)

    sample_sorted = sorted(
        sample,
        key=lambda t: (t.get("dealYear") or 0, t.get("dealMonth") or 0, t.get("dealDay") or 0),
        reverse=True,
    )

    return {
        "rental_monthly_avg": median_monthly,  # 원 단위
        "rental_deposit_avg": median_deposit,  # 원 단위
        "rental_sample_count": len(monthly_amounts),
        "rental_yield_percent": yield_pct,
        "rental_match_kind": match_kind,
        "rental_endpoint_label": label,
        "rental_samples": [
            {
                "name": s.get("offiNm") or "",
                "dong": s.get("umdNm") or "",
                "area_m2": s.get("excluUseAr"),
                "floor": s.get("floor"),
                "monthly": _parse_amount(s.get("monthlyRent")) or 0,
                "deposit": _parse_amount(s.get("deposit")) or 0,
                "deal_date": f"{s.get('dealYear')}-{s.get('dealMonth'):02d}-{s.get('dealDay'):02d}"
                if s.get("dealYear")
                else "",
            }
            for s in sample_sorted
        ],
    }

