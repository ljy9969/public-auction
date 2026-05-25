"""Strict target-region checks (Songpa whitelist + Gangnam whitelist + 3km)."""
from __future__ import annotations

from typing import Any

from scraper.filters.coords import DONG_COORDS, haversine_km
from scraper.session import load_criteria

SONGPA_EXCLUDE_SUBSTRINGS = ("문정동", "가락동", "거여동", "마천동", "오금동", "장지동", "풍납동")


def property_address(raw_or_prop: dict[str, Any]) -> str:
    return (
        raw_or_prop.get("address_jibun")
        or raw_or_prop.get("region_line")
        or raw_or_prop.get("sidoSgkEmd")
        or raw_or_prop.get("onbidCltrNm")
        or raw_or_prop.get("title")
        or ""
    ).strip()


def _songpa_false_positive(addr: str) -> bool:
    """Block dongs outside the whitelist that would otherwise sneak through."""
    if any(x in addr for x in SONGPA_EXCLUDE_SUBSTRINGS):
        return True
    # 잠실(법정동)은 잠실2~7동까지 포괄 — 잠실본동만 허용
    if "잠실동" in addr and "잠실본동" not in addr:
        return True
    return False


def matches_songpa_strict(addr: str, dongs: list[str]) -> bool:
    if "송파구" not in addr and "송파" not in addr:
        return False
    if _songpa_false_positive(addr):
        return False
    return any(dong in addr for dong in dongs)


def matches_gangnam_dong(addr: str, whitelist: list[str]) -> bool:
    if "강남구" not in addr:
        return False
    blocked = ("자곡동", "일원동", "개포동", "개포1동", "개포2동", "도곡동", "수서동", "세곡동")
    if any(b in addr for b in blocked):
        return False
    return any(dong in addr for dong in whitelist)


def in_target_region(raw_or_prop: dict[str, Any], *, require_gangnam_radius: bool = True) -> bool:
    """True only for Songpa whitelist or Gangnam whitelist within 3km of Seolleung."""
    criteria = load_criteria()
    regions = criteria["regions"]
    addr = property_address(raw_or_prop)

    if not addr:
        return False

    if any(
        x in addr
        for x in (
            "원주",
            "인천",
            "부산",
            "대구",
            "광주",
            "대전",
            "울산",
            "강원",
            "경기",
            "충청",
            "전라",
            "경상",
            "제주",
        )
    ):
        return False

    songpa_ok = matches_songpa_strict(addr, regions["songpa_dongs"])
    if songpa_ok:
        return True

    gangnam_dong_ok = matches_gangnam_dong(addr, regions["gangnam_whitelist"])
    if not gangnam_dong_ok:
        return False

    if not require_gangnam_radius:
        return True

    seolleung = regions["seolleung"]
    coords = None
    for dong in regions["gangnam_whitelist"]:
        if dong in addr and dong in DONG_COORDS:
            coords = DONG_COORDS[dong]
            break

    if not coords:
        from scraper.filters.geo import resolve_coords

        prop = raw_or_prop if "address_jibun" in raw_or_prop else {"address_jibun": addr, "title": addr}
        coords = resolve_coords(prop, criteria)

    if not coords:
        return False
    dist = haversine_km(coords[0], coords[1], seolleung["lat"], seolleung["lng"])
    return dist <= float(seolleung["radius_km"])
