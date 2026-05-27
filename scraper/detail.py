"""Fetch property detail HTML via the live Playwright session.

온비드 detail 페이지는 외부 직접 GET 차단(2558 byte 에러). 검색 페이지의 JS 함수
`fn_goCltrDetail(...)` 가 POST form submit으로 이동시킴 — 그 흐름을 재현해야 한다.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from scraper.session import OnbidSession, load_criteria

logger = logging.getLogger(__name__)


def fetch_detail_html(session: OnbidSession, row: dict[str, Any]) -> str:
    """검색 페이지의 fn_goCltrDetail()을 evaluate로 호출 → POST submit → detail HTML 반환.

    호출 후엔 검색 페이지로 되돌아가 다음 매물도 같은 page session으로 처리한다.
    """
    if session._page is None:
        return ""

    criteria = load_criteria()
    delay = float(criteria["onbid"].get("request_delay_sec", 1.5))
    if delay > 0:
        time.sleep(delay)

    page = session._page
    params = [
        str(row.get("cltrScrnGrpCd") or ""),
        str(row.get("cltrPrptDivCd") or ""),
        str(row.get("onbidCltrno") or ""),
        str(row.get("onbidPbancNo") or ""),
        str(row.get("pbctNo") or ""),
        str(row.get("pbctCdtnNo") or ""),
    ]
    if not params[2]:  # onbidCltrno 없으면 조회 불가
        return ""

    # 검색 페이지 컨텍스트로 복귀 (이전 매물 detail에서 nav 되어 있을 수 있음)
    if "mvmnCltrCdtnSrchClg" not in page.url:
        try:
            page.goto(session.search_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            logger.debug("Failed to return to search page: %s", exc)
            return ""

    js_args = ", ".join(f'"{p}"' for p in params)
    try:
        page.evaluate(f"fn_goCltrDetail({js_args})")
        page.wait_for_load_state("networkidle", timeout=30_000)
        # 면적정보 표가 렌더링될 때까지 잠깐 대기
        try:
            page.wait_for_selector(".op_mobile_tbl01, .txt01", timeout=10_000)
        except Exception:
            pass
        return page.content()
    except Exception as exc:
        logger.debug("fn_goCltrDetail navigation failed: %s", exc)
        return ""
