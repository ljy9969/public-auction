"""Fetch property detail HTML via the live Playwright session (httpx fallback)."""
from __future__ import annotations

import logging
import time
from typing import Any

from scraper.parse import detail_url
from scraper.session import OnbidSession, load_criteria

logger = logging.getLogger(__name__)

_DETAIL_404_MARKERS = ("404", "Not Found", "오류가 발생", "잘못된 접근")


def _looks_like_error(html: str) -> bool:
    if not html or len(html) < 500:
        return True
    head = html[:2000]
    return any(m in head for m in _DETAIL_404_MARKERS)


def fetch_detail_html(session: OnbidSession, row: dict[str, Any]) -> str:
    criteria = load_criteria()
    delay = float(criteria["onbid"].get("request_delay_sec", 1.5))
    url = detail_url(row)

    if delay > 0:
        time.sleep(delay)

    if session._page is not None:
        try:
            # Detail body is JS-rendered; wait for a content table to appear
            html = session.fetch_html(
                url,
                wait_until="networkidle",
                wait_for_selector="table",
            )
            if not _looks_like_error(html):
                return html
            logger.debug("Detail via Playwright looked empty for %s", url)
        except Exception as exc:
            logger.debug("Playwright detail navigation failed: %s", exc)

    path = url.split(criteria["onbid"]["base_url"].rstrip("/"))[-1]
    with session.httpx_client() as client:
        resp = client.get(
            path,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text
