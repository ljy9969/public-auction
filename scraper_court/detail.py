"""법원경매 물건 상세 — 대표사진(base64) 추출.

상세 엔드포인트 selectAuctnCsSrchRslt.on 응답의 data.dma_result.csPicLst 에
사진들이 base64(JPEG)로 인라인 포함된다. 공개 URL은 없다(NAS 내부 경로 /nas_e_image_pgj/…는 404).
→ 우리가 base64를 받아 파일로 저장하고 자체 서빙한다.

사진 분류(cortAuctnPicDvsCd) — 진단(2026-06-03)에서 확인:
  000241 = 물건 전경/건물 사진 (대표)   ← 공매 대표사진에 해당
  000244 = 위치도
  000245 = 지적/구조/내부 등 다수
  000247 = 기타
대표 갤러리는 000241 우선, 없으면 000244 → 000245 순으로 폴백.
"""
from __future__ import annotations

import logging
from typing import Any

from scraper_court.search import DEFAULT_PAYLOAD
from scraper_court.session import CourtSession

logger = logging.getLogger(__name__)

DETAIL_PATH = "/pgj/pgj15B/selectAuctnCsSrchRslt.on"
DETAIL_SUBMISSION = "mf_wfm_mainFrame_sbm_selectGdsDtlSrchDtlInfo"

# 사진 분류 우선순위 — 앞쪽일수록 대표성 높음.
PIC_DIV_PRIORITY = ["000241", "000244", "000245", "000247"]


def fetch_detail(
    session: CourtSession,
    *,
    cs_no: str,
    cort_ofc_cd: str,
    dspsl_gds_seq: str | int = 1,
) -> dict[str, Any]:
    """물건 상세(dma_result) 반환. cs_no = '2023타경6292', cort_ofc_cd = 'B000210'."""
    srch_info = {**DEFAULT_PAYLOAD, "csNo": cs_no, "cortOfcCd": cort_ofc_cd, "sideDvsCd": "2"}
    payload = {
        "dma_srchGdsDtlSrch": {
            "csNo": cs_no,
            "cortOfcCd": cort_ofc_cd,
            "dspslGdsSeq": str(dspsl_gds_seq),
            "pgmId": "PGJ151F01",
            "srchInfo": srch_info,
        }
    }
    data = session.post_json(
        DETAIL_PATH, payload,
        submission_id=DETAIL_SUBMISSION,
        sc_userid="NONUSER",
    )
    return (data.get("data") or {}).get("dma_result") or {}


def extract_photos(dma_result: dict[str, Any], max_count: int = 5) -> list[dict[str, str]]:
    """csPicLst → [{title, b64}] (대표 분류 우선, 최대 max_count장).

    각 항목 b64는 순수 base64 문자열(접두 'data:' 없음).
    """
    pic_lst = dma_result.get("csPicLst") or []
    if not pic_lst:
        return []

    def sort_key(p: dict[str, Any]) -> tuple[int, int]:
        div = p.get("cortAuctnPicDvsCd") or ""
        try:
            div_rank = PIC_DIV_PRIORITY.index(div)
        except ValueError:
            div_rank = len(PIC_DIV_PRIORITY)
        try:
            seq = int(p.get("cortAuctnPicSeq") or 0)
        except (TypeError, ValueError):
            seq = 0
        return (div_rank, seq)

    out: list[dict[str, str]] = []
    for p in sorted(pic_lst, key=sort_key):
        b64 = p.get("picFile")
        if not b64:
            continue
        out.append({"title": p.get("picTitlNm") or f"{len(out) + 1}.jpg", "b64": b64})
        if len(out) >= max_count:
            break
    return out
