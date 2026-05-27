"""POST srchCltrCdtn.do with user criteria."""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from scraper.session import OnbidSession, load_criteria


def build_search_payload(page_index: int = 1, cltr_nm: str | None = None) -> str:
    criteria = load_criteria()
    form = criteria["form"]
    onbid = criteria["onbid"]
    today = date.today()
    end = today + timedelta(days=form.get("bid_period_days", 30))

    pairs: list[tuple[str, str]] = [
        ("pageIndex", str(page_index)),
        ("pageUnit", str(onbid.get("page_unit", 30))),
        ("srchBidPerdBgngDt", today.isoformat()),
        ("srchBidPerdEndDt", end.isoformat()),
        ("srchPvctYn", ""),
        ("srchArrayCtgrId", ""),
        ("srchWordType", form.get("srch_word_type", "0001")),
        ("srchSortType", form.get("srch_sort_type", "ASC")),
        ("srchLowstBidBgngPrc", ""),
        ("srchLowstBidEndPrc", str(form.get("srch_lowst_bid_end_prc", ""))),
        ("srchApslEvlBgngAmt", ""),
        ("srchApslEvlEndAmt", ""),
        ("cltrScrnGrpCd", ""),
        ("cltrPrptDivCd", ""),
        ("onbidCltrno", ""),
        ("onbidPbancNo", ""),
        ("pbctNo", ""),
        ("pbctCdtnNo", ""),
        ("srchLowstBidBgng", ""),
        ("srchApslEvlAmtType", "001"),
        ("rtnListUrl", ""),
        ("searchCltrMnmtNoYn", "N"),
        ("srchCltrNm", cltr_nm or ""),
        ("srchCltrType", form["srch_cltr_type"]),
        ("srchDspsMthod", form["srch_dsps_mthod"]),
        ("srchBidMthod", form["srch_bid_mthod"]),
        ("srchBidDivType", form["srch_bid_div_type"]),
        ("srchShrYn", form.get("srch_shr_yn", "N")),
        ("srchBidPerdType", "0002"),
        ("calBidPerdBgngDt", today.isoformat()),
        ("calhBidPerdEndDt", end.isoformat()),
        ("srchBldSqmsType", form.get("srch_bld_sqms_type", "RANGE")),
        ("srchMinBldLdar", str(form.get("srch_min_bld_ldar", 24))),
        ("srchMaxBldLdar", ""),
        ("srchLdarType", "ALL"),
        ("checkMobileUsg", "on"),
        ("checkMobileRgn", "on"),
    ]

    # 유찰횟수 cap (직접입력 모드)
    usbd_bgng = form.get("srch_usbd_nft_bgng")
    usbd_end = form.get("srch_usbd_nft_end")
    if usbd_bgng is not None or usbd_end is not None:
        pairs.append(("srchUsbdNftType", "0001"))
        pairs.append(("srchUsbdNftBgng", str(usbd_bgng) if usbd_bgng is not None else ""))
        pairs.append(("srchUsbdNftEnd", str(usbd_end) if usbd_end is not None else ""))
    else:
        pairs.append(("srchUsbdNftType", "ALL"))

    for code in form.get("srch_prpt_types", []):
        pairs.append(("srchPrptType", code))

    for rgn in form.get("srch_array_rgn", []):
        pairs.append(("srchArrayRgn", rgn))

    return urlencode(pairs)


def fetch_search_page(
    session: OnbidSession,
    page_index: int = 1,
    delay_sec: float | None = None,
    cltr_nm: str | None = None,
) -> dict[str, Any]:
    criteria = load_criteria()
    delay = delay_sec if delay_sec is not None else criteria["onbid"].get("request_delay_sec", 1.5)
    path = criteria["onbid"]["list_path"]
    body = build_search_payload(page_index, cltr_nm=cltr_nm)

    if delay > 0 and page_index > 1:
        time.sleep(delay)

    with session.httpx_client() as client:
        resp = client.post(path, content=body, headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        resp.raise_for_status()
        return resp.json()


def iter_list_pages(
    session: OnbidSession,
    max_pages: int | None = None,
    cltr_nm: str | None = None,
):
    page = 1
    total_pages = 1
    while page <= total_pages:
        if max_pages is not None and page > max_pages:
            break
        data = fetch_search_page(session, page_index=page, cltr_nm=cltr_nm)
        rows = data.get("cltrInfVOList") or []
        if not rows:
            break
        rowcount = int(rows[0].get("rowcount") or len(rows))
        page_unit = int(criteria_page_unit())
        total_pages = max(1, (rowcount + page_unit - 1) // page_unit)
        yield page, rows
        page += 1


def search_queries() -> list[str]:
    """Region-mode 분기:
      seoul_all       → 서울 25개 자치구 키워드 (srchArrayRgn 무시되는 이슈 대응)
      songpa_gangnam  → 동별 키워드 검색 ('송파구 잠실본동' 등)
    """
    criteria = load_criteria()
    regions = criteria["regions"]
    mode = regions.get("mode", "songpa_gangnam")
    if mode == "seoul_all":
        return [
            "서울특별시 종로구", "서울특별시 중구", "서울특별시 용산구", "서울특별시 성동구",
            "서울특별시 광진구", "서울특별시 동대문구", "서울특별시 중랑구", "서울특별시 성북구",
            "서울특별시 강북구", "서울특별시 도봉구", "서울특별시 노원구", "서울특별시 은평구",
            "서울특별시 서대문구", "서울특별시 마포구", "서울특별시 양천구", "서울특별시 강서구",
            "서울특별시 구로구", "서울특별시 금천구", "서울특별시 영등포구", "서울특별시 동작구",
            "서울특별시 관악구", "서울특별시 서초구", "서울특별시 강남구", "서울특별시 송파구",
            "서울특별시 강동구",
        ]
    queries: list[str] = []
    for dong in regions.get("songpa_dongs", []):
        queries.append(f"송파구 {dong}")
    for dong in regions.get("gangnam_whitelist", []):
        queries.append(f"강남구 {dong}")
    return queries


def iter_all_queries(
    session: OnbidSession,
    max_pages_per_query: int | None = 3,
):
    seen: set[str] = set()
    for q in search_queries():
        for _page, rows in iter_list_pages(session, max_pages=max_pages_per_query, cltr_nm=q or None):
            for raw in rows:
                key = f"{raw.get('onbidCltrno')}-{raw.get('pbctCdtnNo')}"
                if key in seen:
                    continue
                seen.add(key)
                yield q, raw


def criteria_page_unit() -> int:
    return int(load_criteria()["onbid"].get("page_unit", 30))
