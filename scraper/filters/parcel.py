"""VWorld 연속지적도(LP_PA_CBND_BUBUN) 필지 경계 폴리곤 조회.

geo_lat/lng 포인트가 포함된 지번 필지의 경계를 GeoJSON(EPSG:4326)으로 받아온다.
지도에서 마커와 함께 '그 번지'만 폴리곤으로 강조하는 용도. PNU 없이 좌표만으로
geomFilter=POINT 조회가 되므로 공매·경매 공통으로 쓸 수 있다.

키 발급: https://www.vworld.kr (무료, 데이터 API + 허용 도메인 등록 필요).
환경변수: VWORLD_API_KEY (필수), VWORLD_DOMAIN (요청 domain 파라미터; 기본 localhost).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

VWORLD_DATA_URL = "https://api.vworld.kr/req/data"


def fetch_parcel_polygon(
    lat: float,
    lng: float,
    *,
    api_key: str | None = None,
    domain: str | None = None,
) -> dict[str, Any] | None:
    """(lat, lng)를 포함하는 필지의 GeoJSON geometry + pnu/jibun 반환.

    반환: {"type": "Polygon"|"MultiPolygon", "coordinates": [...], "pnu": str, "jibun": str}
    실패/미존재 시 None. 좌표는 [lng, lat] 순(GeoJSON 표준, EPSG:4326).
    """
    key = (api_key or os.environ.get("VWORLD_API_KEY", "")).strip()
    if not key or lat is None or lng is None:
        return None
    dom = (domain or os.environ.get("VWORLD_DOMAIN", "") or "http://localhost").strip()
    params = {
        "service": "data",
        "version": "2.0",            # v2 데이터 API 필수 — 누락 시 INCORRECT_KEY
        "request": "GetFeature",
        "data": "LP_PA_CBND_BUBUN",   # 연속지적도(부분)
        "key": key,
        "geomFilter": f"POINT({lng} {lat})",
        "crs": "EPSG:4326",
        "geometry": "true",
        "attribute": "true",
        "size": "1",
        "format": "json",
    }
    # 도메인 인증은 'domain' 쿼리 파라미터가 아니라 Referer 헤더로 보내야 통과한다.
    # (domain 파라미터로 보내면 등록 URL과 불일치 시 INCORRECT_KEY — 2026-06-08 확인)
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(VWORLD_DATA_URL, params=params, headers={"Referer": dom})
            resp.raise_for_status()
            body = resp.json()
    except Exception:
        return None

    # 응답은 {"response": {...}} 래퍼. v1/v2 모두 대응:
    #  - result.featureCollection.features (구)
    #  - result.featureCollection 가 곧 FeatureCollection
    #  - result 가 FeatureCollection 또는 features 배열
    response = body.get("response") or body
    if response.get("status") != "OK":
        return None
    result = response.get("result") or {}
    fc = result.get("featureCollection") if isinstance(result, dict) else None
    if isinstance(fc, dict):
        features = fc.get("features") or []
    elif isinstance(result, dict) and result.get("type") == "FeatureCollection":
        features = result.get("features") or []
    elif isinstance(result, list):
        features = result
    else:
        features = []
    if not features:
        return None
    feat = features[0]
    geom = feat.get("geometry") or {}
    if not geom.get("coordinates"):
        return None
    props = feat.get("properties") or {}
    return {
        "type": geom.get("type"),
        "coordinates": geom.get("coordinates"),
        "pnu": props.get("pnu") or props.get("PNU"),
        "jibun": props.get("jibun") or props.get("addr") or props.get("ADDR"),
    }
