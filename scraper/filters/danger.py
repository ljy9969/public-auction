"""위험 시그널 필터.

도서 *실전 부동산 경매 (수익 실현편)* — 유근용·정민우 의 권장 룰을 코드화.
매물 카테고리별로 다른 위험 패턴을 검사:

- 주거/오피스텔: 대항력 임차인 인수 위험
- 토지/도로: 농업진흥구역(자동 차단), 맹지·분묘기지권(caution)
- 공통: 유찰 5회 초과는 caution
"""
from __future__ import annotations

import re
from typing import Any


def _haystack(prop: dict[str, Any]) -> str:
    """매물의 모든 텍스트 필드를 합쳐 패턴 검색에 사용."""
    parts: list[str] = []
    parts.append(prop.get("title") or "")
    parts.append(prop.get("category") or "")
    parts.append(prop.get("status") or "")
    # detail_json (온비드 원문 — 비고란·매각물건명세서 등)
    detail = prop.get("detail_json") or {}
    if isinstance(detail, dict):
        for k, v in detail.items():
            parts.append(str(k))
            parts.append(str(v))
    rights = prop.get("rights_json") or {}
    if isinstance(rights, dict):
        for k, v in rights.items():
            parts.append(str(k))
            parts.append(str(v))
    return " ".join(parts)


def _is_land(prop: dict[str, Any]) -> bool:
    cat = (prop.get("category") or "") + (prop.get("title") or "")
    return any(k in cat for k in ("도로", "토지 /", "전 /", "답 /", "과수원", "임야", "대지"))


def apply_danger_filters(prop: dict[str, Any]) -> dict[str, Any]:
    notes: list[str] = list(prop.get("filter_notes") or [])
    text = _haystack(prop)
    is_land = _is_land(prop)

    # 1. 농업진흥구역/농업보호구역 — 토지에 한해 HARD BLOCK (사용 제한 강함)
    if is_land and re.search(r"농업\s*(?:진흥|보호)\s*(?:구역|지역)", text):
        prop["passes_filters"] = False
        notes.append("danger: 농업진흥/보호구역 (사용제한)")

    # 2. 맹지 — 토지에 caution
    if is_land and "맹지" in text:
        notes.append("caution: 맹지 (도로 미접)")

    # 3. 분묘기지권 — 토지에 caution
    if is_land and "분묘기지권" in text:
        notes.append("caution: 분묘기지권")

    # 4. 대항력 있는 임차인 + 인수 위험 — 주거/오피스텔
    if not is_land:
        if re.search(r"대항력\s*있는\s*임차인", text) or re.search(r"임차인.*?인수", text):
            notes.append("caution: 임차인 인수 위험")
        # 전세권/임차권 등기 명시
        if re.search(r"전세권|임차권\s*등기", text):
            notes.append("caution: 임차권 등기")

    # 5. 유찰 5회 초과 — 공통 caution
    fail = prop.get("fail_count")
    if fail is not None and int(fail) >= 5:
        notes.append(f"caution: 유찰 {fail}회 (권리/하자 점검 필요)")

    # 6. 선하지(고압선) — 토지 caution (책: 시세보다 낮게 입찰)
    if is_land and "선하지" in text:
        notes.append("caution: 선하지 (고압선)")

    # 7. 분묘 관련 일반 표현
    if is_land and ("분묘" in text and "분묘기지권" not in text):
        notes.append("caution: 분묘 존재")

    prop["filter_notes"] = notes
    return prop
