"""Quality post-filters from plan §3."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from scraper.session import load_criteria

# '제지하층', '제 지하층', '지하 1층' 등 — '지하철'은 매칭 안 됨(층 글자 필요)
_BASEMENT_RE = re.compile(r"지하\s*\d*\s*층")


def _is_land_or_road(prop: dict[str, Any]) -> bool:
    cat = (prop.get("category") or "") + (prop.get("title") or "")
    return any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지"))


def apply_quality_filters(prop: dict[str, Any]) -> dict[str, Any]:
    criteria = load_criteria()
    pf = criteria["post_filters"]
    notes: list[str] = list(prop.get("filter_notes") or [])
    is_land = _is_land_or_road(prop)
    # 지분 매물(건물지분/토지지분) — 면적 하한 면제 (소액 지분 투자 포함)
    is_share = (
        is_land
        or prop.get("share_yn") == "Y"
        or prop.get("building_shared") is True
    )

    # 지하층 매물 제외 — 제목 또는 상세(위치/이용현황/주위환경)에 '지하층' 표기
    title = prop.get("title") or ""
    if _BASEMENT_RE.search(title):
        prop["passes_filters"] = False
        notes.append("quality: 지하층 (제외)")
    else:
        detail = prop.get("detail_json") or {}
        for k, v in detail.items():
            if any(kw in k for kw in ("위치", "이용", "현황", "주위")) and _BASEMENT_RE.search(str(v)):
                prop["passes_filters"] = False
                notes.append("quality: 지하층 (위치/현황, 제외)")
                break

    # Active bids only (rough: status not closed)
    status = (prop.get("status") or "").strip()
    if status and any(x in status for x in ("낙찰", "유찰마감", "종료", "취소")):
        prop["passes_filters"] = False
        notes.append(f"quality: closed status ({status})")

    # 면적 하한은 '단독 건물'에만 적용 — 지분/토지/도로는 면적 무관 (소액 지분 핵심)
    if not is_share:
        bld = prop.get("area_build_m2")
        min_bld = pf.get("min_bld_area_m2", 23)
        if bld is not None and bld > 0 and bld < min_bld:
            prop["passes_filters"] = False
            notes.append(f"quality: building {bld}㎡ < {min_bld}㎡")

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

    # 주거용건물 세부 7종 화이트리스트 — 주거용건물 카테고리에만 적용 (오피스텔/용도복합/토지는 우회)
    allowed = pf.get("allowed_categories") or []
    if allowed and "주거용건물" in category:
        if not any(ac in category for ac in allowed):
            prop["passes_filters"] = False
            notes.append(f"quality: category not in allowed list ({category})")

    # 토지 세부 14종 화이트리스트 (학교용지/종교용지/철도용지 등 제외)
    land_allowed = pf.get("land_allowed_categories") or []
    if land_allowed and is_land:
        sub = category.split("/")[-1].strip() if "/" in category else category
        if not any(la in sub for la in land_allowed):
            prop["passes_filters"] = False
            notes.append(f"quality: 토지 용도 제외 ({sub})")

    # 유찰 cap — 모든 용도 통일 (max_fail_count, 기본 5 — 6회 이상 제외)
    max_fail = pf.get("max_fail_count")
    if max_fail is not None:
        fail = prop.get("fail_count")
        if fail is not None and fail > max_fail:
            prop["passes_filters"] = False
            notes.append(f"quality: fail count {fail} > {max_fail}")

    # Max price re-check — 최저가 비공개(None/0)면 감정가로 판단 (초고가 매물 제외)
    #   토지/도로: max_min_price_land (1천만) / 주거 지분: max_min_price_share (5천만) / 단독: max_min_price (3억)
    min_price = prop.get("min_price")
    appr = prop.get("appraisal_price")
    is_share_building = prop.get("share_yn") == "Y" or prop.get("building_shared") is True
    if is_land:
        max_price = pf.get("max_min_price_land", 10_000_000)
        kind = "land"
    elif is_share_building:
        max_price = pf.get("max_min_price_share", 50_000_000)
        kind = "share"
    else:
        max_price = pf.get("max_min_price", 300_000_000)
        kind = "default"
    effective_price = min_price if (min_price is not None and min_price > 0) else appr
    if effective_price is None:
        # 최저가·감정가 둘 다 비공개 → 가격 판단 불가, 제외
        prop["passes_filters"] = False
        notes.append("quality: price undisclosed (가격 비공개 제외)")
    elif effective_price > max_price:
        prop["passes_filters"] = False
        basis = "min bid" if (min_price is not None and min_price > 0) else "appraisal"
        notes.append(f"quality: {basis} {int(effective_price) // 1_000_000}M > {max_price // 1_000_000}M ({kind})")

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
