"""지역 필터.

- 주거/오피스텔 매물: 송파/강남 화이트리스트 + 선릉 3km (엄격)
- 지분/도로/토지 매물: 수도권(서울+경기+인천) 전체 + 알려진 재개발 진행/예정 지역
"""
from __future__ import annotations

from typing import Any

from scraper.filters.coords import DONG_COORDS, haversine_km
from scraper.session import load_criteria

SONGPA_EXCLUDE_SUBSTRINGS = ("문정동", "가락동", "거여동", "마천동", "오금동", "장지동", "풍납동")

# 수도권 광역
_METRO_PREFIXES = ("서울특별시", "서울 ", "경기도 ", "경기 ", "인천광역시", "인천 ")
# 재개발/재건축 진행·예정 핫스팟 (서울 25개 자치구 + 1기 신도시 + 주요 경기 정비도시)
_REDEV_HOTSPOTS = (
    # 서울 — 정비·재개발 활발 지역
    "용산구", "성동구", "마포구", "영등포구", "동작구", "관악구",
    "노원구", "도봉구", "은평구", "서대문구", "강서구", "양천구",
    "구로구", "성북구", "동대문구", "중랑구", "광진구", "강북구",
    "금천구", "종로구", "중구", "강동구",
    # 경기 — 1·2기 신도시 + 정비 활발
    "성남시", "수원시", "고양시", "광명시", "안양시", "의왕시",
    "하남시", "과천시", "부천시", "안산시", "용인시", "남양주시",
    "구리시", "의정부시",
    # 인천 — 정비 활발
    "부평구", "미추홀구", "남동구", "서구",
)


def _is_share_or_land(raw_or_prop: dict[str, Any]) -> bool:
    """지분/토지/도로 카테고리 — 지역 제한을 수도권으로 완화하는 대상."""
    cat = (
        raw_or_prop.get("ctgrFullNm")
        or raw_or_prop.get("ctgrNm")
        or raw_or_prop.get("category")
        or ""
    )
    title = raw_or_prop.get("onbidCltrNm") or raw_or_prop.get("title") or ""
    haystack = cat + " " + title
    if any(k in haystack for k in ("도로", "토지 /", "전 /", "답 /", "과수원", "임야", "대지")):
        return True
    shr = raw_or_prop.get("shrYn") or raw_or_prop.get("share_yn")
    if shr == "Y":
        return True
    return False


def in_metro_redev_area(addr: str) -> bool:
    """수도권 + 알려진 재개발 핫스팟 매칭."""
    if not addr:
        return False
    if not any(p in addr for p in _METRO_PREFIXES):
        return False
    # 서울 강남/송파는 이미 엄격 룰로 처리 — 여기선 그 외 수도권 + 정비 지역
    if any(spot in addr for spot in _REDEV_HOTSPOTS):
        return True
    # 화이트리스트에 없어도 송파/강남구 자체는 통과 (해당 dong은 엄격 룰)
    if "송파구" in addr or "강남구" in addr or "서초구" in addr:
        return True
    return False


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
    """주거/오피스텔은 엄격(송파/강남+선릉3km).
    지분/도로/토지는 수도권+재개발 핫스팟까지 확장."""
    criteria = load_criteria()
    regions = criteria["regions"]
    addr = property_address(raw_or_prop)

    if not addr:
        return False

    # 지분/도로/토지 — 수도권 광역 허용 (입문자 소액 투자 대상)
    if _is_share_or_land(raw_or_prop):
        # 서울/경기/인천 외 지역은 차단
        if not any(p in addr for p in _METRO_PREFIXES):
            return False
        # 그 안에서 재개발 핫스팟 또는 송파/강남/서초만 통과
        return in_metro_redev_area(addr)

    # 주거/오피스텔 — 기존 엄격 룰
    if any(
        x in addr
        for x in (
            "원주",
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
            "인천",
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
