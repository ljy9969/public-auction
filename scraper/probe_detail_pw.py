"""Playwright: capture detail navigation URL from condition search."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from scraper.session import load_criteria, load_selectors, _dismiss_popups

OUT = ROOT / "docs" / "probe-detail-pw.json"


def main():
    criteria = load_criteria()
    selectors = load_selectors()
    url = criteria["onbid"]["base_url"].rstrip("/") + criteria["onbid"]["search_path"]
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on(
            "request",
            lambda req: captured.append({"url": req.url, "method": req.method})
            if "cltr" in req.url.lower() and "dtl" in req.url.lower()
            else None,
        )
        page.goto(url, wait_until="networkidle", timeout=120000)
        _dismiss_popups(page, selectors)
        # click first property link if any
        links = page.locator("a[href*='Cltr'], a[href*='cltr'], .list_type_table a").all()
        link_hrefs = []
        for a in links[:5]:
            try:
                href = a.get_attribute("href")
                if href:
                    link_hrefs.append(href)
            except Exception:
                pass
        if link_hrefs:
            page.goto(
                link_hrefs[0]
                if link_hrefs[0].startswith("http")
                else criteria["onbid"]["base_url"].rstrip("/") + link_hrefs[0],
                wait_until="networkidle",
                timeout=60000,
            )
        browser.close()

    OUT.write_text(
        json.dumps({"link_hrefs": link_hrefs, "captured": captured}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {OUT}, links={len(link_hrefs)}, captured={len(captured)}")


if __name__ == "__main__":
    main()
