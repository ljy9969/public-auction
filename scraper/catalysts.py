"""지역 호재 화이트리스트 로더·매처 (regional_catalysts.yaml).

매물 주소 → 호재 매칭. 디스코드 추천 알림과 웹 API(카드·상세 표시)가 공용으로 쓴다.
화이트리스트는 매월 자동 검증 루틴이 갱신.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PATH = Path(__file__).resolve().parent / "config" / "regional_catalysts.yaml"
_CACHE: list[dict[str, Any]] | None = None


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


def match_catalyst(address: str | None) -> dict[str, Any] | None:
    """주소(지번/도로명)에 match 문자열이 하나라도 포함되면 그 호재 요약 반환.

    반환: {name, type, impact, confidence} 또는 None.
    여러 개 매칭돼도 첫 번째(목록 상단 우선)만.
    """
    addr = address or ""
    if not addr:
        return None
    for c in load_catalysts():
        for m in c.get("match") or []:
            if m and m in addr:
                return {
                    "name": c.get("name"),
                    "type": c.get("type"),
                    "impact": c.get("impact"),
                    "confidence": c.get("confidence"),
                }
    return None
