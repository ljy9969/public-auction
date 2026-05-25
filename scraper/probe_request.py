"""Capture POST payload for srchCltrCdtn.do."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

SEARCH_URL = (
    "https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrcdtnsrch/"
    "CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do"
)
OUT = Path(__file__).resolve().parent.parent / "docs" / "probe-request.json"


def main() -> None:
    requests_log: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="ko-KR")

        def on_request(request):
            if "srchCltrCdtn" in request.url:
                requests_log.append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "post_data": request.post_data,
                        "headers": dict(request.headers),
                    }
                )

        page.on("request", on_request)
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=120_000)

        csrf = page.locator('meta[name="_csrf"]').get_attribute("content")

        # Trigger search via JS if exposed
        page.evaluate(
            """() => {
            const btn = document.querySelector('#btnSrch, .btn_srch, button.srch');
            if (btn) btn.click();
            else {
              const all = [...document.querySelectorAll('button, a')];
              const s = all.find(e => e.textContent && e.textContent.trim() === '검색');
              if (s) s.click();
            }
        }"""
        )
        page.wait_for_timeout(8000)

        # Also try calling known function names
        for fn in ["fn_srchCltrCdtn", "srchCltrCdtn", "searchCltr", "fn_search"]:
            try:
                exists = page.evaluate(f"() => typeof {fn} !== 'undefined'")
                if exists:
                    page.evaluate(f"() => {{ try {{ {fn}(); }} catch(e) {{}} }}")
                    page.wait_for_timeout(3000)
            except Exception:
                pass

        browser.close()

    OUT.write_text(
        json.dumps({"csrf": csrf, "requests": requests_log}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Logged {len(requests_log)} srch requests -> {OUT}")


if __name__ == "__main__":
    main()
