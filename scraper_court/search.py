"""법원경매 검색 — searchControllerMain.on POST + 페이지네이션.

P1 정찰에서 실측한 페이로드를 base로 두고 필요한 필드만 override.
주의:
- pageSize > 50 → 400 (실측, P2 정착)
- 모든 검색조건이 빈값 → 400. 최소 하나(법원·시도·기일·용도)는 채워야 함.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Iterator

from scraper_court.session import CourtSession

logger = logging.getLogger(__name__)

SEARCH_PATH = "/pgj/pgjsearch/searchControllerMain.on"

# P1 정찰에서 확보한 디폴트 페이로드 — 부동산 물건상세검색 시그니처.
# 모든 빈 필드를 그대로 유지해야 서버가 거절하지 않음.
DEFAULT_PAYLOAD: dict[str, Any] = {
    "rletDspslSpcCondCd": "",
    "bidDvsCd": "000331",                 # 입찰구분 - 전체
    "mvprpRletDvsCd": "00031R",           # 부동산
    "cortAuctnSrchCondCd": "0004601",     # 검색조건 코드
    "rprsAdongSdCd": "",
    "rprsAdongSggCd": "",
    "rprsAdongEmdCd": "",
    "rdnmSdCd": "",
    "rdnmSggCd": "",
    "rdnmNo": "",
    "mvprpDspslPlcAdongSdCd": "",
    "mvprpDspslPlcAdongSggCd": "",
    "mvprpDspslPlcAdongEmdCd": "",
    "rdDspslPlcAdongSdCd": "",
    "rdDspslPlcAdongSggCd": "",
    "rdDspslPlcAdongEmdCd": "",
    "cortOfcCd": "",
    "jdbnCd": "",
    "execrOfcDvsCd": "",
    "lclDspslGdsLstUsgCd": "",
    "mclDspslGdsLstUsgCd": "",
    "sclDspslGdsLstUsgCd": "",
    "cortAuctnMbrsId": "",
    "aeeEvlAmtMin": "",
    "aeeEvlAmtMax": "",
    "lwsDspslPrcRateMin": "",
    "lwsDspslPrcRateMax": "",
    "flbdNcntMin": "",
    "flbdNcntMax": "",
    "objctArDtsMin": "",
    "objctArDtsMax": "",
    "mvprpArtclKndCd": "",
    "mvprpArtclNm": "",
    "mvprpAtchmPlcTypCd": "",
    "notifyLoc": "off",
    "lafjOrderBy": "",
    "pgmId": "PGJ151F01",
    "csNo": "",
    "cortStDvs": "1",
    "statNum": 1,
    "bidBgngYmd": "",
    "bidEndYmd": "",
    "dspslDxdyYmd": "",
    "fstDspslHm": "",
    "scndDspslHm": "",
    "thrdDspslHm": "",
    "fothDspslHm": "",
    "dspslPlcNm": "",
    "lwsDspslPrcMin": "",
    "lwsDspslPrcMax": "",
    "grbxTypCd": "",
    "gdsVendNm": "",
    "fuelKndCd": "",
    "carMdyrMax": "",
    "carMdyrMin": "",
    "carMdlNm": "",
    "sideDvsCd": "",
}


def _build_payload(
    *,
    sido_cd: str = "11",                  # 서울 (기본)
    court_cd: str = "",                   # 빈값 = 전체 법원
    usg_lcl: str = "",                    # 빈값 = 모든 용도. 토지=10000 / 건물=20000
    min_price: int | None = None,         # 최저매각가 하한 (원)
    max_price: int | None = None,         # 최저매각가 상한 (원)
    max_fail_count: int | None = None,    # 유찰 횟수 상한
    min_area_m2: int | None = None,       # 면적 하한
    bid_start_ymd: str | None = None,     # 매각기일 시작 (YYYYMMDD)
    bid_end_ymd: str | None = None,       # 매각기일 끝
    page_no: int = 1,
    page_size: int = 50,                  # WebSquare가 50까지만 허용 (80은 400)
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dma_pageInfo": {
            "pageNo": page_no,
            "pageSize": page_size,
            "bfPageNo": "",
            "startRowNo": "",
            "totalCnt": "",
            "totalYn": "Y",
            "groupTotalCount": "",
        },
        "dma_srchGdsDtlSrchInfo": {**DEFAULT_PAYLOAD},
    }
    s = payload["dma_srchGdsDtlSrchInfo"]
    if sido_cd:
        # rd* = 부동산(real estate dong), mvprp* = 동산, rprs* = 대표.
        # 부동산 검색에는 rdDspslPlcAdong* 만 채움.
        s["rdDspslPlcAdongSdCd"] = sido_cd
    if court_cd:
        s["cortOfcCd"] = court_cd
    if usg_lcl:
        s["lclDspslGdsLstUsgCd"] = usg_lcl
    if min_price is not None:
        s["lwsDspslPrcMin"] = str(min_price)
    if max_price is not None:
        s["lwsDspslPrcMax"] = str(max_price)
    if max_fail_count is not None:
        s["flbdNcntMin"] = "0"
        s["flbdNcntMax"] = str(max_fail_count)
    if min_area_m2 is not None:
        s["objctArDtsMin"] = str(min_area_m2)
    if bid_start_ymd:
        s["bidBgngYmd"] = bid_start_ymd
    if bid_end_ymd:
        s["bidEndYmd"] = bid_end_ymd

    # 가드: 모든 필터 빈값이면 400. 기일 디폴트(오늘 ~ 90일)로 채움.
    has_filter = any([
        s.get("rdDspslPlcAdongSdCd"), s.get("cortOfcCd"),
        s.get("lclDspslGdsLstUsgCd"), s.get("bidBgngYmd"),
    ])
    if not has_filter:
        today = datetime.now()
        s["bidBgngYmd"] = today.strftime("%Y%m%d")
        s["bidEndYmd"] = (today + timedelta(days=90)).strftime("%Y%m%d")
    return payload


def search_page(
    session: CourtSession,
    *,
    sido_cd: str = "11",
    court_cd: str = "",
    usg_lcl: str = "",
    min_price: int | None = None,
    max_price: int | None = None,
    max_fail_count: int | None = None,
    min_area_m2: int | None = None,
    bid_start_ymd: str | None = None,
    bid_end_ymd: str | None = None,
    page_no: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    payload = _build_payload(
        sido_cd=sido_cd, court_cd=court_cd, usg_lcl=usg_lcl,
        min_price=min_price, max_price=max_price,
        max_fail_count=max_fail_count, min_area_m2=min_area_m2,
        bid_start_ymd=bid_start_ymd, bid_end_ymd=bid_end_ymd,
        page_no=page_no, page_size=page_size,
    )
    data = session.post_json(SEARCH_PATH, payload)
    return data


def iter_all_pages(
    session: CourtSession,
    *,
    max_pages: int = 5,
    **kwargs: Any,
) -> Iterator[dict[str, Any]]:
    """검색 결과를 페이지 단위로 yield. 매 row 하나씩 흘림."""
    for page_no in range(1, max_pages + 1):
        result = search_page(session, page_no=page_no, **kwargs)
        rows = (result.get("data") or {}).get("dlt_srchResult") or []
        total = (result.get("data") or {}).get("dma_pageInfo", {}).get("totalCnt")
        logger.info("court search page=%s rows=%s total=%s", page_no, len(rows), total)
        for row in rows:
            yield row
        if not rows:
            break
        try:
            if total and (page_no * kwargs.get("page_size", 100)) >= int(total):
                break
        except (TypeError, ValueError):
            pass
