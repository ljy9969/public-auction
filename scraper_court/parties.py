"""법원경매정보 사건상세조회 — 당사자내역(이해관계인) fetch + count.

엔드포인트: /pgj/pgj15A/selectAuctnCsSrchRslt.on
  · submissionid = mf_wfm_mainFrame_sbm_selectCsDtlInf
  · sc-userid    = NONUSER
  · payload      = {"dma_srchCsDtlInf": {"cortOfcCd": ..., "csNo": ...}}

응답 data.dlt_rletCsIntrpsLst 의 각 항목:
  {auctnIntrpsDvsNm:"채권자|채무자겸소유자|가압류권자|공유자|...",
   intrpsNm:"이OO", intrpsSeq:1681, ...}

공유자 카운트 정의(사용자 결정 — 2026-06-25):
  "공유자" + "채무자겸소유자" — 후자도 사실상 지분 소유자라 합산.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scraper_court.session import CourtSession

logger = logging.getLogger(__name__)

CASE_DETAIL_PATH = "/pgj/pgj15A/selectAuctnCsSrchRslt.on"
CASE_DETAIL_SUBMISSION = "mf_wfm_mainFrame_sbm_selectCsDtlInf"

# 공유자 카운트 — 사용자 결정(B): "공유자" 명목 + "채무자겸소유자"
_CO_OWNER_ROLES = {"공유자", "채무자겸소유자"}


def encode_cs_no(user_cs_no: str | None) -> str | None:
    """사용자 형태 "2025타경42692" → 서버 14자리 "20250130042692".

    "타경"=01300, 사건번호는 5자리 zero-pad. 그 외 패턴은 그대로 반환.
    이미 14자리 숫자면 그대로(중복 변환 방지).
    """
    if not user_cs_no:
        return user_cs_no
    s = user_cs_no.strip()
    if s.isdigit() and len(s) == 14:
        return s
    m = re.match(r"^(\d{4})타경(\d+)$", s)
    if m:
        year, num = m.groups()
        return f"{year}01300{int(num):05d}"
    return s  # 다른 사건 종류는 호출자가 책임


def fetch_parties(
    session: CourtSession,
    *,
    cs_no: str,
    cort_ofc_cd: str,
) -> list[dict[str, Any]]:
    """사건 당사자내역 raw list 반환. 빈 응답 시 []."""
    csno_enc = encode_cs_no(cs_no)
    payload = {
        "dma_srchCsDtlInf": {
            "cortOfcCd": cort_ofc_cd,
            "csNo": csno_enc,
        }
    }
    data = session.post_json(
        CASE_DETAIL_PATH, payload,
        submission_id=CASE_DETAIL_SUBMISSION,
        sc_userid="NONUSER",
    )
    return (data.get("data") or {}).get("dlt_rletCsIntrpsLst") or []


def normalize_parties(raw: list[dict[str, Any]]) -> tuple[list[dict[str, str]], int]:
    """raw → (parties, co_owner_count).

    parties 항목: {"role": "공유자", "name": "이OO", "seq": 1681}
    role/name 없는 row는 건너뜀.
    co_owner_count = "공유자" + "채무자겸소유자" 합산.
    """
    parties: list[dict[str, str]] = []
    co_owner_count = 0
    for r in raw:
        role = (r.get("auctnIntrpsDvsNm") or "").strip()
        name = (r.get("intrpsNm") or "").strip()
        if not role and not name:
            continue
        seq = r.get("intrpsSeq")
        parties.append({
            "role": role,
            "name": name,
            "seq": int(seq) if isinstance(seq, (int, float)) else 0,
        })
        if role in _CO_OWNER_ROLES:
            co_owner_count += 1
    # 표시 순서: 채권자 → 채무자겸소유자 → 가압류 → 공유자 → 기타 (seq 정렬 보조)
    role_order = {
        "채권자": 0, "채무자겸소유자": 1, "채무자": 2, "소유자": 3,
        "가압류권자": 4, "근저당권자": 5, "임차인": 6, "공유자": 7,
    }
    parties.sort(key=lambda p: (role_order.get(p["role"], 99), p["seq"]))
    return parties, co_owner_count
