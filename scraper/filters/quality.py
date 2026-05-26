"""Quality post-filters from plan §3."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from scraper.session import load_criteria


def _is_land_or_road(prop: dict[str, Any]) -> bool:
    cat = (prop.get("category") or "") + (prop.get("title") or "")
    return any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지"))


def apply_quality_filters(prop: dict[str, Any]) -> dict[str, Any]:
    criteria = load_criteria()
    pf = criteria["post_filters"]
    notes: list[str] = list(prop.get("filter_notes") or [])
    is_land = _is_land_or_road(prop)

    # Active bids only (rough: status not closed)
    status = (prop.get("status") or "").strip()
    if status and any(x in status for x in ("낙찰", "유찰마감", "종료", "취소")):
        prop["passes_filters"] = False
        notes.append(f"quality: closed status ({status})")

    # Land/road exclusion — DISABLED when land is the target (소액 입문 토지 투자)
    # 도로·토지·농지 지분은 소액 입문에 핵심 매물이므로 통과
    # (책: '실전 부동산 경매' — 토지 지분 + 도로 부속토지 입문자 권장 종목)

    if not is_land:
        # Building area only matters for 건물 매물
        bld = prop.get("area_build_m2")
        if bld is not None and bld > 0 and bld < 24:
            prop["passes_filters"] = False
            notes.append(f"quality: building {bld}㎡ < 24㎡")

        # 건물 지분 차단 (토지지분만 있는 다세대·오피스텔은 허용)
        bs = prop.get("building_shared")
        if bs is True:
            prop["passes_filters"] = False
            notes.append("quality: building share (제외)")
        elif bs is None and prop.get("share_yn") == "Y":
            prop["passes_filters"] = False
            notes.append("quality: share unresolved (detail unavailable)")

    title = prop.get("title") or ""
    for kw in pf.get("exclude_share_keywords", []):
        if kw in title:
            prop["passes_filters"] = False
            notes.append(f"quality: title contains '{kw}'")
            break

    category = (prop.get("category") or "")
    for excluded in pf.get("exclude_categories", []):
        if excluded and excluded in category:
            prop["passes_filters"] = False
            notes.append(f"quality: category excluded ({excluded})")
            break

    # Fail count cap
    max_fail = pf.get("max_fail_count", 2)
    fail = prop.get("fail_count")
    if fail is not None and fail > max_fail:
        prop["passes_filters"] = False
        notes.append(f"quality: fail count {fail} > {max_fail}")

    # Max price re-check
    min_price = prop.get("min_price")
    max_price = pf.get("max_min_price", 300_000_000)
    if min_price is not None and min_price > max_price:
        prop["passes_filters"] = False
        notes.append(f"quality: min bid > {max_price // 1_000_000}M")

    # Bid end in future
    bid_end = prop.get("bid_end")
    if bid_end:
        try:
            end_dt = datetime.strptime(bid_end[:16], "%Y-%m-%d %H:%M")
            if end_dt < datetime.now():
                prop["passes_filters"] = False
                notes.append("quality: bid ended")
        except ValueError:
            pass

    prop["filter_notes"] = notes
    return prop
