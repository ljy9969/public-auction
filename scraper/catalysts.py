"""지역 호재 화이트리스트 로더·매처 (regional_catalysts.yaml).

매물 주소 → 호재 매칭. 디스코드 추천 알림과 웹 API(카드·상세 표시)가 공용으로 쓴다.
화이트리스트는 매월 자동 검증 루틴이 갱신.

매칭 단계 (3단계 누적):
1. 주소 문자열 게이트 — match 패턴 중 하나라도 주소에 포함.
2. 좌표 거리 강등 (B) — yaml의 `coord: [lat, lng]` 와 매물 geo_lat/lng가 모두
   있으면 직선거리(haversine)로 impact 동적 조정:
     <3km   유지 / 3~6km 한 단계 ↓ / 6~10km 두 단계 ↓ / >10km 매칭 취소.
   좌표 어느 한쪽이라도 없으면 주소 매칭만 적용(이전 동작과 동일).
3. 종목 강등 (C) — 호재로 매도가가 오르기 어려운 종목(임야·전답·잡종지·묘지·
   종교용지·공원 등)이면 한 단계 ↓. 대지·주거·오피스텔·상가가 함께/단독으로
   있으면 강등하지 않음.

등급 강등 순서: 상 → 중 → 하 → 하 (마지막은 멈춤; 매칭 자체는 유지).
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import yaml

_PATH = Path(__file__).resolve().parent / "config" / "regional_catalysts.yaml"
_CACHE: list[dict[str, Any]] | None = None

# 거리 임계 (km) — 호재 중심점 기준.
_NEAR_KM = 3.0   # 이내: 원 impact 유지
_MID_KM = 6.0    # 이내: 한 단계 ↓
_FAR_KM = 10.0   # 이내: 두 단계 ↓ / 초과: 매칭 취소

_IMPACT_ORDER = ("상", "중", "하")

# C — 호재로 매도가 상승이 제한적인 종목 키워드. category 문자열에 이게 포함되고
# 가치 상승 키워드(대지·주거·오피스텔·상가·주택)가 *함께* 없으면 한 단계 ↓.
_DEMOTE_CATEGORY_KW = ("임야", "전답", "잡종지", "묘지", "종교용지", "공원")
_KEEP_CATEGORY_KW = ("대지", "주거", "주택", "오피스텔", "상가", "도시형생활주택")


def load_catalysts() -> list[dict[str, Any]]:
    """catalysts 리스트 (프로세스 캐시). 로드 실패 시 빈 리스트."""
    global _CACHE
    if _CACHE is None:
        try:
            data = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
            _CACHE = data.get("catalysts") or []
        except Exception:
            _CACHE = []
    return _CACHE


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 직선거리(km). 지구 평균반지름 6371km."""
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _demote(impact: str | None, steps: int) -> str | None:
    """impact 등급을 steps 단계 ↓. 마지막 단계(하)에서는 멈춤."""
    if impact not in _IMPACT_ORDER or steps <= 0:
        return impact
    idx = min(_IMPACT_ORDER.index(impact) + steps, len(_IMPACT_ORDER) - 1)
    return _IMPACT_ORDER[idx]


def _is_demote_category(category: str | None) -> bool:
    """카테고리가 호재 수혜 제한 종목인지. 가치 상승 키워드가 함께 있으면 False."""
    if not category:
        return False
    if any(kw in category for kw in _KEEP_CATEGORY_KW):
        return False
    return any(kw in category for kw in _DEMOTE_CATEGORY_KW)


def match_catalyst(
    address: str | None,
    category: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, Any] | None:
    """주소(지번/도로명)에 match 문자열이 하나라도 포함되면 그 호재 요약 반환.

    추가로 좌표(B)·종목(C) 강등 룰 적용 — 모듈 docstring 참고.

    반환: {name, type, impact, confidence, [distance_km]} 또는 None.
    여러 개 매칭돼도 첫 번째(목록 상단 우선)만.
    """
    addr = address or ""
    if not addr:
        return None
    for c in load_catalysts():
        # 1) 주소 문자열 게이트
        hit = False
        for m in c.get("match") or []:
            if m and m in addr:
                hit = True
                break
        if not hit:
            continue

        impact = c.get("impact")
        distance_km: float | None = None

        # 2) 좌표 거리 강등 (B). 좌표 어느 한쪽이라도 없으면 스킵.
        coord = c.get("coord")
        if (
            isinstance(coord, (list, tuple)) and len(coord) == 2
            and isinstance(lat, (int, float)) and isinstance(lng, (int, float))
        ):
            try:
                clat, clng = float(coord[0]), float(coord[1])
                distance_km = _haversine_km(clat, clng, float(lat), float(lng))
                if distance_km > _FAR_KM:
                    return None  # 너무 멀면 매칭 취소
                if distance_km > _MID_KM:
                    impact = _demote(impact, 2)
                elif distance_km > _NEAR_KM:
                    impact = _demote(impact, 1)
                # _NEAR_KM 이내는 원 impact 유지
            except (TypeError, ValueError):
                pass

        # 3) 종목 강등 (C)
        if _is_demote_category(category):
            impact = _demote(impact, 1)

        result: dict[str, Any] = {
            "name": c.get("name"),
            "type": c.get("type"),
            "impact": impact,
            "confidence": c.get("confidence"),
        }
        if distance_km is not None:
            result["distance_km"] = round(distance_km, 2)
        return result
    return None
