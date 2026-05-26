"""Elevator required (ELVT_YN=Y or detail/list evidence)."""
from __future__ import annotations

import re
from typing import Any


def elevator_from_raw(row: dict[str, Any]) -> str | None:
    for key in ("elvtYn", "ELVT_YN", "elvt_yn", "elevYn"):
        v = row.get(key)
        if v is not None and str(v).strip():
            return "Y" if str(v).upper() in ("Y", "YES", "1", "유") else "N"
    return None


def elevator_from_detail(detail: dict[str, str] | None) -> str | None:
    if not detail:
        return None
    for label, value in detail.items():
        if not any(k in label for k in ("승강기", "엘리베이터", "ELEV")):
            continue
        text = f"{label} {value}"
        if re.search(r"(無|무|없|N\b|no)", text, re.I):
            return "N"
        if re.search(r"(有|유|있|Y\b|yes)", text, re.I):
            return "Y"
    return None


def resolve_elevator_yn(prop: dict[str, Any], raw: dict[str, Any] | None = None) -> str | None:
    if prop.get("elevator_yn"):
        return prop["elevator_yn"]
    if raw:
        from_raw = elevator_from_raw(raw)
        if from_raw:
            return from_raw
    return elevator_from_detail(prop.get("detail_json"))


def apply_elevator_filter(prop: dict[str, Any], raw: dict[str, Any] | None = None) -> dict[str, Any]:
    from scraper.session import load_criteria

    criteria = load_criteria()
    if not criteria.get("post_filters", {}).get("require_elevator", True):
        return prop

    # 토지/도로 매물은 엘리베이터 무의미 — 스킵
    cat = (prop.get("category") or "") + (prop.get("title") or "")
    if any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지")):
        return prop

    notes: list[str] = list(prop.get("filter_notes") or [])
    yn = resolve_elevator_yn(prop, raw)
    prop["elevator_yn"] = yn

    if yn == "Y":
        notes.append("elevator: yes")
    elif yn == "N":
        prop["passes_filters"] = False
        notes.append("elevator: no")
    else:
        # Unknown은 차단하지 않고 caution 태그만 — 사용자가 직접 판단
        notes.append("caution: elevator unknown")

    prop["filter_notes"] = notes
    return prop
