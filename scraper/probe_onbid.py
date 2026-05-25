"""Probe Onbid condition search network endpoints (one-off reverse engineering)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

SEARCH_URL = (
    "https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrcdtnsrch/"
    "CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do"
)
OUT = Path(__file__).resolve().parent.parent / "docs" / "probe-results.json"


def main() -> None:
    captured: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        def on_response(response):
            url = response.url
            if "CltrCdtnSrch" in url or "cltrcdtnsrch" in url.lower():
                entry = {
                    "url": url,
                    "status": response.status,
                    "method": response.request.method,
                }
                try:
                    if "json" in (response.headers.get("content-type") or ""):
                        entry["body_preview"] = str(response.json())[:2000]
                    elif response.status == 200 and response.request.method == "POST":
                        text = response.text()
                        entry["body_preview"] = text[:2000] if text else None
                except Exception as e:
                    entry["error"] = str(e)
                captured.append(entry)

        page.on("response", on_response)
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=120_000)

        # Dismiss popups if present
        for sel in [
            "button:has-text('닫기')",
            ".layer_close",
            "#todayClose",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click(timeout=2000)
            except Exception:
                pass

        page_title = page.title()
        html_snippet = page.content()[:5000]

        # Try to find search button and click
        search_clicked = False
        for sel in [
            "button:has-text('검색')",
            "a:has-text('검색')",
            "#btnSrch",
            ".btn_search",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.click(timeout=5000)
                    search_clicked = True
                    page.wait_for_timeout(5000)
                    break
            except Exception:
                continue

        # Collect script srcs
        scripts = page.eval_on_selector_all(
            "script[src]",
            "els => els.map(e => e.src).filter(s => s.includes('cltr') || s.includes('Cltr'))",
        )

        browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "search_url": SEARCH_URL,
        "page_title": page_title,
        "search_clicked": search_clicked,
        "script_srcs": scripts,
        "captured_responses": captured,
        "html_snippet": html_snippet,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Captured {len(captured)} CltrCdtnSrch responses")


if __name__ == "__main__":
    main()
