"""Geographic post-filters: Songpa 5-dong, Gangnam whitelist, Seolleung 3km."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from scraper.filters.coords import DONG_COORDS, haversine_km
from scraper.filters.region import matches_gangnam_dong, matches_songpa_strict
from scraper.session import load_criteria

_DONG_CENTROID_TOL = 1e-4
_NOMINATIM_LAST_CALL: list[float] = [0.0]


def _is_dong_centroid(lat: float, lng: float) -> bool:
    for c in DONG_COORDS.values():
        if abs(c[0] - lat) < _DONG_CENTROID_TOL and abs(c[1] - lng) < _DONG_CENTROID_TOL:
            return True
    return False


def geocode_kakao(address: str, api_key: str) -> tuple[float, float] | None:
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://dapi.kakao.com/v2/local/search/address.json",
                params={"query": address},
                headers={"Authorization": f"KakaoAK {api_key}"},
            )
            resp.raise_for_status()
            docs = resp.json().get("documents") or []
            if not docs:
                return None
            return float(docs[0]["y"]), float(docs[0]["x"])
    except Exception:
        return None


def geocode_kakao_keyword(query: str, api_key: str) -> tuple[float, float] | None:
    """Kakao Places keyword search — covers building names that the address API misses."""
    if not query:
        return None
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                params={"query": query, "size": 1},
                headers={"Authorization": f"KakaoAK {api_key}"},
            )
            resp.raise_for_status()
            docs = resp.json().get("documents") or []
            if not docs:
                return None
            return float(docs[0]["y"]), float(docs[0]["x"])
    except Exception:
        return None


def _kakao_keyword_query(prop: dict[str, Any]) -> str:
    """Build a 'dong + building-or-bunji' query from title/address for Places search."""
    title = (prop.get("title") or "").strip()
    region = (prop.get("region_line") or "").strip()
    if not title:
        return prop.get("address_jibun") or ""
    remainder = title[len(region):].lstrip() if region and title.startswith(region) else title
    # Drop trailing unit/floor noise (e.g., '제13층 제1309호', '외 1필지 …')
    for marker in (" 제", " 외 ", "동 ", " 호 "):
        idx = remainder.find(marker)
        if idx > 0:
            remainder = remainder[:idx]
            break
    dong = ""
    for token in region.split():
        if token.endswith("동"):
            dong = token
            break
    return f"{dong} {remainder}".strip() if dong else remainder.strip()


def geocode_nominatim(address: str) -> tuple[float, float] | None:
    """Free OSM geocoder. Respects 1 req/sec usage policy."""
    if not address:
        return None
    elapsed = time.monotonic() - _NOMINATIM_LAST_CALL[0]
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "kr",
                    "accept-language": "ko",
                },
                headers={
                    "User-Agent": "onbid-public-auction-scraper/1.0 (private research)",
                },
            )
            _NOMINATIM_LAST_CALL[0] = time.monotonic()
            resp.raise_for_status()
            docs = resp.json()
            if not docs:
                return None
            return float(docs[0]["lat"]), float(docs[0]["lon"])
    except Exception:
        _NOMINATIM_LAST_CALL[0] = time.monotonic()
        return None


def resolve_coords(
    prop: dict[str, Any],
    criteria: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[float, float] | None:
    """Resolve geo coords with provenance.

    Order: cached (unless force / stale dong-centroid) → Kakao → Nominatim → dong centroid.
    """
    if not force and prop.get("geo_lat") and prop.get("geo_lng"):
        lat = float(prop["geo_lat"])
        lng = float(prop["geo_lng"])
        if not _is_dong_centroid(lat, lng):
            return lat, lng

    addr = prop.get("address_jibun") or prop.get("title") or ""

    api_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    if api_key:
        coords = geocode_kakao(addr, api_key)
        if coords:
            prop["geo_lat"], prop["geo_lng"] = coords
            prop["geo_source"] = "kakao"
            return coords
        keyword = _kakao_keyword_query(prop)
        if keyword:
            coords = geocode_kakao_keyword(keyword, api_key)
            if coords:
                prop["geo_lat"], prop["geo_lng"] = coords
                prop["geo_source"] = "kakao_keyword"
                return coords

    coords = geocode_nominatim(addr)
    if coords:
        prop["geo_lat"], prop["geo_lng"] = coords
        prop["geo_source"] = "nominatim"
        return coords

    for dong, fallback in DONG_COORDS.items():
        if dong in addr:
            prop["geo_lat"], prop["geo_lng"] = fallback
            prop["geo_source"] = "dong_centroid"
            return fallback
    return None


def apply_geo_filters(prop: dict[str, Any]) -> dict[str, Any]:
    criteria = load_criteria()
    regions = criteria["regions"]
    seolleung = regions["seolleung"]
    mode = regions.get("mode", "songpa_gangnam")
    notes: list[str] = list(prop.get("filter_notes") or [])
    addr = prop.get("address_jibun") or prop.get("title") or prop.get("region_line") or ""
    cat = prop.get("category") or ""
    is_officetel_mixed = ("오피스텔" in cat) or ("용도복합" in cat)

    coords = resolve_coords(prop, criteria)
    dist_km = None
    if coords:
        dist_km = haversine_km(coords[0], coords[1], seolleung["lat"], seolleung["lng"])
        prop["distance_seolleung_km"] = round(dist_km, 2)

    # mode=seoul_all + 오피스텔/용도복합이 아닌 매물 → 화이트리스트/3km 검사 skip
    if mode == "seoul_all" and not is_officetel_mixed:
        if prop.get("geo_source") == "dong_centroid":
            notes.append("geo: approximate (dong centroid)")
        prop["filter_notes"] = notes
        return prop

    songpa_ok = matches_songpa_strict(addr, regions["songpa_dongs"])
    gangnam_ok = matches_gangnam_dong(addr, regions["gangnam_whitelist"])
    gangnam_radius_ok = gangnam_ok and dist_km is not None and dist_km <= seolleung["radius_km"]

    # 언니(쪠) 영역 — 영등포구 OR 서대문역 8km (둘 중 하나, outer join)
    sister = regions.get("sister_zone") or {}
    sister_gu = sister.get("gu", "영등포구")
    in_yeongdeungpo = sister_gu in addr
    within_sister_radius = False
    st = sister.get("transit") or {}
    if coords and st.get("lat") and st.get("lng"):
        sdist = haversine_km(coords[0], coords[1], float(st["lat"]), float(st["lng"]))
        prop["distance_sister_km"] = round(sdist, 2)
        if st.get("radius_km"):
            within_sister_radius = sdist <= float(st["radius_km"])
    sister_ok = in_yeongdeungpo or within_sister_radius

    region_ok = songpa_ok or gangnam_radius_ok or sister_ok
    if not region_ok:
        prop["passes_filters"] = False
        notes.append("region: outside Songpa/Gangnam(쪈) / Yeongdeungpo(쪠) zones")
    else:
        if songpa_ok:
            notes.append("region: Songpa dong match (쪈)")
        if gangnam_radius_ok:
            notes.append(f"region: Gangnam within {seolleung['radius_km']}km of Seolleung (쪈)")
        if sister_ok:
            notes.append("region: Yeongdeungpo zone (쪠)")
        if prop.get("geo_source") == "dong_centroid":
            notes.append("geo: approximate (dong centroid)")

    prop["filter_notes"] = notes
    return prop
