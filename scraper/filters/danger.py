"""위험 시그널 + 특수권리 필터.

도서 *실전 부동산 경매 (수익 실현편)* — 유근용·정민우 의 권장 룰을 코드화.
매물 카테고리별로 다른 위험 패턴을 검사:

- 주거/오피스텔: 대항력 임차인 인수 위험
- 토지/도로: 농업진흥구역(자동 차단), 맹지·분묘기지권(caution)
- 공통: 유찰 5회 초과, 유치권·법정지상권·NPL·가처분·토지별도등기 등 특수권리는 caution
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
    # filter_notes는 sweep 재실행 시 중복 누적 방지를 위해 caution/danger 항목은
    # 모두 초기화하고 다시 평가한다. 사용자/타 모듈이 추가한 다른 prefix 노트는 유지.
    notes: list[str] = [
        n for n in (prop.get("filter_notes") or [])
        if not (n.startswith("caution:") or n.startswith("danger:"))
    ]
    text = _haystack(prop)
    is_land = _is_land(prop)

    # 1. 농업진흥구역/농업보호구역 — 토지에 한해 HARD BLOCK (사용 제한 강함)
    if is_land and re.search(r"농업\s*(?:진흥|보호)\s*(?:구역|지역)", text):
        prop["passes_filters"] = False
        notes.append("danger: 농업진흥/보호구역 (사용제한)")

    # 2. 맹지 — 토지에 caution
    if is_land and "맹지" in text:
        notes.append("caution: 맹지 (도로 미접)")

    # 3. 분묘기지권 — 토지. '성립' 명시되고 '미성립/불분명' 부재 시 격상 대상.
    if is_land and "분묘기지권" in text:
        # 부정어 인근 매칭 회피 — '미성립', '성립여부 불분명', '성립하지 아니' 등
        neg = re.search(r"분묘기지권[\s\S]{0,40}(?:미\s*성립|성립\s*여부|성립하지|성립되지|불분명)", text)
        pos = re.search(r"분묘기지권[\s\S]{0,40}성립", text)
        if pos and not neg:
            notes.append("caution: 분묘기지권 성립")
        else:
            notes.append("caution: 분묘기지권 (성립 여부 검토)")

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

    # 7. 분묘 관련 일반 표현 — 부정어("분묘는 없", "분묘 없음", "발견되지" 등) 회피.
    if is_land and "분묘" in text and "분묘기지권" not in text:
        # '분묘' 뒤 0~10자 안에 '없'/'발견되지'/'발견하지 못' 같은 부정어 없을 때만
        if not re.search(r"분묘[\s\S]{0,15}(?:없|발견되지|발견하지\s*못|확인되지)", text):
            notes.append("caution: 분묘 존재")

    # 8. 유치권 — 공통 (등기부 외 권리, 인수 위험)
    if "유치권" in text:
        notes.append("caution: 유치권 신고")

    # 9. 법정지상권 — 토지 (건물 소유자에게 토지 사용권 인정 → 매수자 활용 제한)
    if "법정지상권" in text:
        notes.append("caution: 법정지상권")

    # 10. NPL/부실채권 — 공통 (담보가치 vs 채권 차이 검토 필요)
    if re.search(r"NPL|부실\s*채권|채권\s*매각", text, flags=re.IGNORECASE):
        notes.append("caution: NPL/부실채권")

    # 11. 가처분/가등기 인수 — 공통 (말소기준 이전 가처분이면 인수)
    if re.search(r"(?:처분금지\s*)?가처분", text) and ("인수" in text or "말소되지 않" in text):
        notes.append("caution: 가처분 인수 가능성")

    # 12. 토지별도등기 — 집합건물 (대지권 미등기, 토지 별도 권리관계 존재)
    if "토지별도등기" in text or re.search(r"토지\s*별도\s*등기", text):
        notes.append("caution: 토지별도등기")

    # 13. 대지권 미등기/없음 — 집합건물 (구분소유 가능 여부 검토)
    if re.search(r"대지권\s*(?:미등기|없음|없|미정리)", text):
        notes.append("caution: 대지권 미등기")

    # 14. 분양형 호텔 — 시세 신뢰 부족 + 운영사 의존 (책: 조심해야 할 분양형 호텔 투자)
    #   생활숙박시설(레지던스)·호텔 객실 단위 분양 매물. 감정가·시세 비교 데이터 부족.
    purp = (prop.get("main_purps") or "") + " " + (prop.get("title") or "")
    if re.search(r"(?:생활)?\s*숙박\s*시설|레지던스|분양형\s*호텔", purp) or \
            ("호텔" in purp and "객실" in text):
        notes.append("caution: 분양형 호텔 (시세 신뢰↓·운영사 의존)")

    # 15. 농지 위 무허가/불법건축물 — 농취증 발급 불가 위험 (책 L827).
    #   토지 매물에 한해 적용. 부정어("없음/없는" 등) 인근 매칭 회피.
    if is_land and re.search(
        r"(?:무허가|불법\s*건축물|위반\s*건축물|무단\s*증축|미등기\s*건물)", text
    ):
        # 직접 부정 부근(없음/없는/철거됨/철거완료)이 아닐 때만
        if not re.search(
            r"(?:무허가|불법\s*건축물|위반\s*건축물|미등기\s*건물)[\s\S]{0,12}"
            r"(?:없|철거|미존재|확인되지)", text
        ):
            notes.append("caution: 무허가/불법건축물 (농취증 불가 위험)")

    # 16. 국가 산업단지 내 지식산업센터 — 임대 목적 취득 제한 (책 L478).
    #   서울디지털산업단지(금천구 가산동·구로구 구로동) 우선 적용.
    #   향후 KICOX GeoJSON 연동으로 전국 국가산단 확장 가능.
    if re.search(r"지식산업\s*센터|아파트형\s*공장", text):
        addr = (prop.get("address_jibun") or "")
        if re.search(r"금천구\s*가산동|구로구\s*구로동", addr):
            notes.append("caution: 국가산단 지식산업센터 (임대 목적 취득 제한)")

    prop["filter_notes"] = notes
    return prop
