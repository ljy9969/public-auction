"""Transit time to 선릉로 433 (직장).

우선순위:
  1. ODsay 대중교통 환승검색 — 실제 버스/지하철 경로 (가장 정확)
  2. 출/도착지 700m 이내(ODsay -98) → 도보 환산
  3. Kakao Mobility 자가용 길찾기 (대중교통 미가용 시 차량 시간으로 대체)
  4. 휴리스틱 — 가장 가까운 역까지 도보 + 지하철 단순 환산
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any

import httpx

from scraper.filters.coords import haversine_km
from scraper.filters.geo import resolve_coords
from scraper.session import load_criteria

logger = logging.getLogger(__name__)

NEARBY_STATIONS: list[tuple[str, float, float]] = [
    ("선릉", 37.5045, 127.0489),
    ("역삼", 37.5005, 127.0365),
    ("삼성", 37.5088, 127.0630),
    ("잠실", 37.5133, 127.1002),
    ("석촌", 37.5055, 127.1065),
    ("송파", 37.4995, 127.1125),
    ("방이", 37.5115, 127.1180),
    ("교대", 37.4934, 127.0146),
    ("강남", 37.4979, 127.0276),
    ("도곡", 37.4885, 127.0465),
]

ODSAY_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
ODSAY_REFERER = "http://localhost:5173"
KAKAO_NAVI_URL = "https://apis-navi.kakaomobility.com/v1/directions"


def _summarize_path(path: dict) -> str:
    """ODsay path → "지하철 2호선 → 분당선 (환승 1회)" 식 요약."""
    info = path.get("info") or {}
    sub_paths = path.get("subPath") or []
    legs: list[str] = []
    for sp in sub_paths:
        ttype = sp.get("trafficType")
        if ttype == 1:  # 지하철
            lane = (sp.get("lane") or [{}])
            name = lane[0].get("name", "지하철") if lane else "지하철"
            legs.append(name)
        elif ttype == 2:  # 버스
            lane = (sp.get("lane") or [{}])
            no = lane[0].get("busNo", "버스") if lane else "버스"
            legs.append(f"버스 {no}")
        # ttype==3 (도보)는 요약에서 생략
    transfers = (info.get("subwayTransitCount", 0) or 0) + (info.get("busTransitCount", 0) or 0)
    if not legs:
        return "도보"
    summary = " → ".join(legs)
    # 환승 횟수 = 교통수단 수 - 1 (도보 제외)
    n_legs = len(legs)
    n_transfers = max(0, n_legs - 1)
    if n_transfers > 0:
        summary += f" (환승 {n_transfers}회)"
    return summary


def odsay_transit_minutes(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, api_key: str
) -> tuple[int, str, str | None] | None:
    """Returns (minutes, mode, summary) where mode in {'transit', 'walk'}, or None."""
    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.get(
                ODSAY_URL,
                params={
                    "SX": origin_lng,
                    "SY": origin_lat,
                    "EX": dest_lng,
                    "EY": dest_lat,
                    "apiKey": api_key,
                    "OPT": "0",
                    "SearchPathType": "0",
                },
                headers={"Referer": ODSAY_REFERER, "Origin": ODSAY_REFERER},
            )
            data = r.json()
            err = data.get("error")
            if err:
                code = err[0].get("code") if isinstance(err, list) else err.get("code")
                if str(code) == "-98":
                    walk_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
                    return (max(1, int(walk_km * 60 / 5)), "walk", None)
                logger.debug("ODsay error: %s", err)
                return None
            paths = data.get("result", {}).get("path") or []
            if not paths:
                return None
            best = paths[0]
            info = best.get("info", {})
            minutes = info.get("totalTime")
            if minutes is None:
                return None
            return (int(minutes), "transit", _summarize_path(best))
    except Exception as exc:
        logger.debug("ODsay request failed: %s", exc)
        return None


def kakao_car_minutes(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, api_key: str
) -> int | None:
    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.get(
                KAKAO_NAVI_URL,
                params={
                    "origin": f"{origin_lng},{origin_lat}",
                    "destination": f"{dest_lng},{dest_lat}",
                    "priority": "RECOMMEND",
                },
                headers={"Authorization": f"KakaoAK {api_key}"},
            )
            if r.status_code != 200:
                return None
            routes = r.json().get("routes") or []
            if not routes:
                return None
            sec = routes[0].get("summary", {}).get("duration")
            return int(sec / 60) if sec else None
    except Exception:
        return None


def heuristic_transit_minutes(prop_lat: float, prop_lng: float) -> int:
    criteria = load_criteria()
    dest_lat, dest_lng = _transit_destination(criteria)
    best = 999
    for _name, slat, slng in NEARBY_STATIONS:
        walk_km = haversine_km(prop_lat, prop_lng, slat, slng)
        walk_min = int(walk_km * 12)
        ride_km = haversine_km(slat, slng, dest_lat, dest_lng)
        ride_min = int(ride_km * 4) + 5
        best = min(best, walk_min + ride_min)
    return best


def _transit_destination(criteria: dict[str, Any]) -> tuple[float, float]:
    dest = criteria["regions"].get("transit_destination") or criteria["regions"]["seolleung"]
    return float(dest["lat"]), float(dest["lng"])


def apply_transit_filter(prop: dict[str, Any]) -> dict[str, Any]:
    criteria = load_criteria()
    max_min = criteria["post_filters"].get("max_transit_minutes")
    cat = prop.get("category") or ""
    is_officetel_mixed = ("오피스텔" in cat) or ("용도복합" in cat)
    # mode=seoul_all + 오피스텔/용도복합 아닌 매물 → 시간 제한 skip (정보는 그대로 기록)
    if criteria["regions"].get("mode") == "seoul_all" and not is_officetel_mixed:
        max_min = None
    notes: list[str] = list(prop.get("filter_notes") or [])
    dest_lat, dest_lng = _transit_destination(criteria)

    coords = resolve_coords(prop, criteria)
    if not coords:
        notes.append("transit: no coordinates")
        prop["filter_notes"] = notes
        return prop

    minutes: int | None = None
    mode: str = "heuristic"
    summary: str | None = None

    # 우선순위: ODsay 대중교통 > ODsay 도보(10분 이내) > 휴리스틱.
    # 자가용은 출퇴근에 안 씀 — Kakao Mobility fallback 제거.
    odsay_key = os.environ.get("ODSAY_API_KEY", "").strip()
    if odsay_key:
        result = odsay_transit_minutes(coords[0], coords[1], dest_lat, dest_lng, odsay_key)
        if result is not None:
            minutes, mode, summary = result
            if mode == "walk" and minutes > 10:
                minutes = None  # 도보 10분 초과면 휴리스틱 대중교통으로

    if minutes is None:
        minutes = heuristic_transit_minutes(coords[0], coords[1])
        mode = "heuristic"

    prop["transit_minutes"] = minutes
    prop["transit_mode"] = mode
    prop["transit_estimated"] = mode in ("heuristic", "car")
    prop["transit_summary"] = summary
    prop["transit_destination"] = (
        criteria["regions"].get("transit_destination", {}).get("address") or "선릉로 433"
    )

    if max_min is not None and minutes > max_min:
        prop["passes_filters"] = False
        notes.append(f"transit: {minutes}min > {max_min}min")
    else:
        notes.append(f"transit: {minutes}min ({mode})")

    prop["filter_notes"] = notes
    return prop
