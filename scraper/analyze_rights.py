"""권리분석 자동 판정 — 휴리스틱 risk-level summary.

온비드 detail 페이지의 rights_json에는 임차인 마스킹 이름 정도만 들어있고
등기부등본의 날짜 기반 권리 순서는 직접 fetch가 차단되어 없음.

따라서 row-by-row 말소/인수 자동 판정은 불가능하고, 다음과 같은
'위험도 + 플래그' 형태의 휴리스틱을 제공한다.

출처: 도서 *실전 부동산 경매 (수익 실현편)* — 유근용·정민우 의
"권리분석은 결국 말소기준권리 찾는 것" 원칙을 따른다. 자동 판정은
참고용이며, 실제 입찰 전 등기부등본·매각물건명세서로 직접 확인 필요.
"""
from __future__ import annotations

import re
from typing import Any

# 인수 위험 키워드 (등기부 외 권리 + 대항력 임차인).
# 주의: 단순 "인수" 단어는 온비드 detail의 '소유권 이전비용 계산기' 위젯
# ("매수인이 부담", "취득세 인수" 등) 노이즈와 충돌한다. 그래서 명시적
# "임차인 인수" 또는 "대항력 임차인" 같은 컨텍스트 결합 패턴만 사용한다.
_TAKEOVER_PATTERNS = [
    (r"대항력\s*있는?\s*임차인", "대항력 임차인"),
    (r"임차인\s*(?:이|은|의|.{0,4})\s*인수", "임차인 인수 명시"),
    (r"임차인.{0,15}말소되지\s*않", "임차인 권리 인수"),
    (r"임차권\s*등기", "임차권등기"),
    (r"전세권\s*(?:설정|등기)", "전세권등기"),
    (r"유치권", "유치권"),
    (r"법정지상권", "법정지상권"),
    (r"분묘기지권", "분묘기지권"),
    (r"토지\s*별도\s*등기", "토지별도등기"),
    (r"대지권\s*(?:미등기|없음|없|미정리)", "대지권 미등기"),
    (r"(?:처분금지\s*)?가처분.{0,20}(?:인수|말소되지\s*않)", "가처분 인수"),
]

# 말소기준권리 후보 (등장 시 일반적으로 후순위 권리는 말소)
_BASE_PATTERNS = [
    r"근저당",
    r"저당권",
    r"(?<!처분금지\s)가압류",
    r"담보가등기",
    r"강제경매\s*개시",
    r"임의경매\s*개시",
]


def _haystack(prop: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(prop.get("title") or "")
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


def _count_tenants(prop: dict[str, Any]) -> int:
    """rights_json에서 '임차인' / '임차권' 키의 마스킹 이름 개수 추정."""
    rights = prop.get("rights_json") or {}
    if not isinstance(rights, dict):
        return 0
    names: set[str] = set()
    for k, v in rights.items():
        if ("임차인" in k or "임차권" in k) and isinstance(v, str):
            for raw in re.split(r"[,/、·]\s*", v):
                raw = raw.strip()
                if raw and ("*" in raw or len(raw) <= 5):
                    names.add(raw)
    return len(names)


def analyze_rights(prop: dict[str, Any]) -> dict[str, Any]:
    """매물 권리관계 자동 판정 휴리스틱.

    Returns
    -------
    dict with keys:
      risk_level: 안전(low) | 주의(medium) | 위험(high)
      summary: 한 줄 요약 한국어
      flags: list of {kind, label, source} — 인수 위험 항목
      base_rights_found: bool — 말소기준 후보 권리 텍스트 등장 여부
      tenant_count: int
      disclaimer: 사용자에게 보일 안내
    """
    text = _haystack(prop)
    flags: list[dict[str, str]] = []

    for pattern, label in _TAKEOVER_PATTERNS:
        if re.search(pattern, text):
            flags.append({"kind": "takeover_risk", "label": label})

    base_found = any(re.search(p, text) for p in _BASE_PATTERNS)

    tenant_count = _count_tenants(prop)
    if tenant_count > 0:
        # 임차인 존재 자체로는 위험 X — 대항력 있는 경우만 위험
        if not any(f["label"].startswith("대항력") or "임차인 인수" in f["label"] for f in flags):
            flags.append({
                "kind": "tenant_present",
                "label": f"임차인 {tenant_count}명 (대항력 확인 필요)",
            })

    # 지분 매물 caution — 입찰 메리트·환금성 (인수 위험과는 별개)
    if re.search(r"공유자\s*우선매수", text):
        flags.append({
            "kind": "co_owner_priority",
            "label": "공유자 우선매수권 — 낙찰해도 공유자가 같은 값에 가져갈 수 있음",
        })
    is_share = (prop.get("share_yn") == "Y") or prop.get("building_shared") is True
    if is_share:
        ratio = prop.get("building_share_ratio") or prop.get("land_share_ratio")
        rtxt = f" {round(ratio * 100)}%" if isinstance(ratio, (int, float)) and 0 < ratio < 1 else ""
        flags.append({
            "kind": "minority_share",
            "label": f"지분 매물{rtxt} — 단독 사용·처분 제약, 출구는 공유물분할 소송 등",
        })
    cautions = [f for f in flags if f["kind"] in ("co_owner_priority", "minority_share")]

    # 위험도 산정
    takeover = [f for f in flags if f["kind"] == "takeover_risk"]
    if len(takeover) >= 2:
        risk = "high"
    elif takeover or tenant_count > 0 or cautions:
        risk = "medium"
    else:
        risk = "low"

    risk_kr = {"low": "안전", "medium": "주의", "high": "위험"}[risk]

    if risk == "low":
        summary = "특수권리·대항력 임차인 키워드 미검출 — 등기부등본 확인 권장"
    elif risk == "high":
        labels = ", ".join(f["label"].split(" —")[0] for f in takeover[:3])
        summary = f"인수 위험 다중 ({labels}) — 입찰 전 변호사 자문 권장"
    elif takeover:
        summary = f"{takeover[0]['label']} 등 인수 위험 1건 — 직접 확인 필수"
    elif cautions:
        summary = " · ".join(f["label"].split(" —")[0] for f in cautions) + " — 입찰 메리트 신중 검토"
    else:
        summary = f"임차인 존재 ({tenant_count}명) — 대항력 직접 확인 필수"

    return {
        "risk_level": risk,
        "risk_label": risk_kr,
        "summary": summary,
        "flags": flags,
        "base_rights_found": base_found,
        "tenant_count": tenant_count,
        "disclaimer": (
            "자동 판정은 키워드 매칭 휴리스틱입니다. "
            "실제 입찰 전 등기부등본 + 매각물건명세서로 말소기준권리·대항력을 직접 확인하세요."
        ),
    }
