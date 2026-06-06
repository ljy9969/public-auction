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


# (endpoint, 시군구, 연월) → 거래 리스트 캐시. 멀티 endpoint 도입 후 같은
# 시군구/월을 매 매물마다 재호출하던 중복을 제거해 백필 속도/안정성 향상.
# 프로세스 수명 동안만 유지(백필 1회 단위). 비우려면 clear_trade_cache().
_TRADE_CACHE: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

# 주소 → (lat, lng) 지오코딩 캐시. 비교 거래 마커용 좌표를 백필 때 한 번만 구해
# 저장한다(프론트는 저장된 좌표만 사용 — 상세 열 때마다 지오코딩하던 클라이언트
# 방식 대비 호출/쿼터 절감). 좌표는 불변이라 프로세스 수명 동안 재사용.
_GEOCODE_CACHE: dict[str, tuple[float, float] | None] = {}


def clear_trade_cache() -> None:
    _TRADE_CACHE.clear()


def _geocode_addr(address: str, kakao_key: str) -> tuple[float, float] | None:
    """지번 주소 → (위도, 경도). Kakao 주소검색(x=경도, y=위도). 프로세스 캐시."""
    if not address or not kakao_key:
        return None
    if address in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[address]
    from scraper.filters.building import _lookup_kakao_address
    coord: tuple[float, float] | None = None
    info = _lookup_kakao_address(address, kakao_key)
    if info:
        try:
            coord = (float(info["y"]), float(info["x"]))
        except (TypeError, ValueError, KeyError):
            coord = None
    _GEOCODE_CACHE[address] = coord
    return coord


def _region_prefix(addr: str) -> str:
    """주소에서 시도·시군구 접두만 — 비교거래(동+지번) 지오코딩 주소 조합용.
    '경기도 평택시 서정동 1021' → '경기도 평택시'."""
    m = re.match(r"^(.*?)\s*[가-힣0-9]+(?:동|읍|면|리)\b", addr or "")
    return m.group(1).strip() if m else (addr or "")


def fetch_monthly_trades(
    endpoint_path: str, sggCd: str, ymd: str, api_key: str
) -> list[dict[str, Any]]:
    """단일 (시군구, 연월) 매매 거래 페이징 호출. (endpoint·시군구·월 단위 캐시)"""
    ckey = (endpoint_path, sggCd, ymd)
    cached = _TRADE_CACHE.get(ckey)
    if cached is not None:
        return cached
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
    _TRADE_CACHE[ckey] = items
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
# 인근 지번 티어 면적 허용 오차. 같은 단지가 아닌 '주변 다른 건물'이라 면적은
# 보수적으로(±10%, 같은 단지 티어와 동일) — 평형 다른 매물 혼입 방지 (2026-06-06).
JIBUN_AREA_TOL = 0.10
# 인근 지번 거래의 실제 반경(m) 상한. 매물 좌표가 있으면 본번 근접에 더해, 거래
# 지번을 지오코딩한 위치가 이 반경 안인 것만 인정 — 큰 동 안에서 멀리 떨어진 다른
# 역세권 단지가 섞이는 문제 방지 (2026-06-06 천호동 대동피렌체리버 ~1km 사례).
JIBUN_RADIUS_M = 700
_GEOCODE_CACHE: dict[str, tuple[float, float] | None] = {}


def _geocode_jibun(address: str, kakao_key: str) -> tuple[float, float] | None:
    """주소 → (lat, lng). Kakao 지오코딩 + 캐시 (백필 1회 단위)."""
    if not address or not kakao_key:
        return None
    if address in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[address]
    from scraper.filters.building import _lookup_kakao_address
    info = _lookup_kakao_address(address, kakao_key)
    coord: tuple[float, float] | None = None
    if info:
        try:
            coord = (float(info["y"]), float(info["x"]))  # y=lat, x=lng
        except (KeyError, ValueError, TypeError):
            coord = None
    _GEOCODE_CACHE[address] = coord
    return coord


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


def _is_basement(trade: dict[str, Any]) -> bool:
    """거래가 지하층인지 (floor < 1). MOLIT floor는 지하면 음수(-1 등).
    우리는 수집 단계부터 지층 매물을 제외하므로 시세 비교에서도 빼야 함."""
    f = trade.get("floor")
    if f is None or str(f).strip() == "":
        return False  # 층 정보 없으면 제외 안 함 (과도 배제 방지)
    try:
        return int(float(f)) < 1
    except (ValueError, TypeError):
        return False


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
                if _is_basement(t):
                    continue  # 지하층 거래 제외 — 우리는 지층 매물을 수집하지 않음
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
            return abs(float(ta) - float(my)) / float(my) <= JIBUN_AREA_TOL
        except (ValueError, TypeError):
            return False

    def _jibun_near(t: dict[str, Any]) -> bool:
        tb = _bonbun(t.get("jibun"))
        return (
            my_bonbun is not None
            and tb is not None
            and abs(tb - my_bonbun) <= JIBUN_NEAR_BONBUN
        )

    # 폴백 매칭(jibun/dong+area)은 같은 동의 '다른 단지'를 잡아 가격대가 안 맞을 수 있다
    # (2026-06-05 평택 서정동 1021: 구축 지분 매물에 신축 롯데캐슬 시세가 붙어 3배 과대).
    # 1순위 건물 연식(±3년 — 보수적으로 비슷한 연식만), 매물 연식 모르면 2순위 감정가
    # 가격대(지분은 전체 환산 0.5~2.0배)로 동떨어진 거래를 제외. 둘 다 모르면 통과(현행).
    # 같은 단지(building) 매칭은 면제(진짜 같은 단지라 연식 자동 일치).
    _apr = str(prop.get("use_apr_day") or "")
    _my_year = int(_apr[:4]) if _apr[:4].isdigit() else None
    _appr = prop.get("appraisal_price") or 0
    _sr = (prop.get("building_share_ratio") or prop.get("land_share_ratio")) \
        if prop.get("share_yn") == "Y" else None
    _appr_full = (_appr / _sr) if (_appr and _sr and 0 < _sr < 1) else _appr

    def _fallback_comp_ok(t: dict[str, Any]) -> bool:
        ty = t.get("buildYear")
        try:
            ty = int(ty) if ty not in (None, "") else None
        except (ValueError, TypeError):
            ty = None
        if _my_year and ty:
            return abs(ty - _my_year) <= 3
        if _appr_full:
            cp = _parse_amount(t.get("dealAmount"))
            if cp:
                return 0.5 * _appr_full <= cp <= 2.0 * _appr_full
        return True

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

    # 인근 지번: 본번 근접에 더해 '실제 거리'로 한 번 더 좁힌다(좌표 있을 때).
    _prop_lat, _prop_lng = prop.get("geo_lat"), prop.get("geo_lng")
    _sido_sigungu = " ".join((addr or "").split()[:2])  # "서울특별시 강동구"

    def _jibun_geo_ok(t: dict[str, Any]) -> bool:
        if _prop_lat is None or _prop_lng is None:
            return True  # 매물 좌표 없으면 본번 근접만으로 (폴백)
        umd = str(t.get("umdNm") or "")
        jibun = str(t.get("jibun") or "")
        if not umd or not jibun:
            return True
        coord = _geocode_jibun(f"{_sido_sigungu} {umd} {jibun}", kakao_key)
        if not coord:
            return True  # 지오코딩 실패 → 본번 근접 신뢰(과도 제외 방지)
        from scraper.filters.coords import haversine_km
        return haversine_km(_prop_lat, _prop_lng, coord[0], coord[1]) * 1000 <= JIBUN_RADIUS_M

    tier_bld_area = [t for t, s in scored if s >= 11]
    tier_bld = [t for t, s in scored if s >= 9]
    tier_jibun = [
        t for t, s in scored
        if s > 0 and _jibun_near(t) and _area_ok(t) and _is_primary(t)
        and str(t.get("umdNm") or "") and str(t.get("umdNm") or "") in addr
        and _fallback_comp_ok(t) and _jibun_geo_ok(t)
    ]
    tier_dong_area = [
        t for t, s in scored if s >= 5 and _is_primary(t) and _fallback_comp_ok(t)
    ]

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
    # 표시 min/max는 실제 매칭 거래의 최저/최고 — 아래 거래 샘플 목록과 정확히
    # 일치(차트 최고 != 목록 최고 불일치 방지, 2026-06-05).
    ps = sorted(prices)
    min_p, max_p = ps[0], ps[-1]

    # 단, dong+area(동 전체)는 다른 단지가 섞여 범위가 과대해지기 쉽다. 이상치를
    # 제거한 분위수(10~90%) 범위로 '신뢰도'를 판정 — 그래도 max>min*1.6 이면 시세
    # 없음(NULL). 같은 단지/인근 지번 매칭은 면제(진짜 시세로 인정).
    if match_kind == "dong+area" and len(ps) >= 5:
        lo_i = int(len(ps) * 0.10)
        hi_i = min(len(ps) - 1, math.ceil(len(ps) * 0.90) - 1)
        trim_min, trim_max = ps[lo_i], ps[hi_i]
        if trim_min and trim_max and trim_max > trim_min * 1.6:
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

    # 비교 거래 마커용 좌표 — 동+지번을 Kakao로 지오코딩해 저장(프론트는 저장 좌표만 사용).
    region_pref = _region_prefix(addr)

    def _mk_sample(s: dict[str, Any]) -> dict[str, Any]:
        dong = s.get("umdNm") or ""
        jb = s.get("jibun") or ""
        lat = lng = None
        if kakao_key and region_pref and dong and jb:
            coord = _geocode_addr(f"{region_pref} {dong} {jb}", kakao_key)
            if coord:
                lat, lng = coord
        return {
            "name": s.get("offiNm") or s.get("aptNm") or s.get("mhouseNm") or "",
            "dong": dong,
            "jibun": jb,
            "lat": lat,
            "lng": lng,
            "area_m2": s.get("excluUseAr"),
            "floor": s.get("floor"),
            "deal_amount": _parse_amount(s.get("dealAmount")),
            "deal_date": f"{s.get('dealYear')}-{s.get('dealMonth'):02d}-{s.get('dealDay'):02d}"
            if s.get("dealYear")
            else "",
        }

    return {
        "market_median_price": median,
        "market_min_price": min_p,
        "market_max_price": max_p,
        "market_sample_count": len(prices),
        "market_period_months": months,
        "market_diff_percent": diff_pct,
        "market_endpoint_label": label,
        "market_match_kind": match_kind,
        "market_samples": [_mk_sample(s) for s in sample_sorted],
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

    # 월세 거래만 + 매칭 (지하층 제외 — 우리는 지층 매물 미수집)
    rented = [
        t for t in all_trades
        if _parse_amount(t.get("monthlyRent")) and not _is_basement(t)
    ]
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

