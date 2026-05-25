"""Playwright session: CSRF token, cookies, and live page for detail fetches."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

CONFIG_DIR = Path(__file__).resolve().parent / "config"


def load_criteria() -> dict[str, Any]:
    with (CONFIG_DIR / "criteria.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_selectors() -> dict[str, Any]:
    with (CONFIG_DIR / "selectors.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class OnbidSession:
    csrf_token: str
    cookies: dict[str, str]
    user_agent: str
    base_url: str
    search_url: str
    referer: str
    _playwright: Playwright | None = field(default=None, repr=False)
    _browser: Browser | None = field(default=None, repr=False)
    _context: BrowserContext | None = field(default=None, repr=False)
    _page: Page | None = field(default=None, repr=False)

    def httpx_client(self) -> httpx.Client:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/plain, */*; q=0.01",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "X-CSRF-TOKEN": self.csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.referer,
            "Origin": self.base_url.rstrip("/"),
        }
        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            cookies=self.cookies,
            timeout=60.0,
            follow_redirects=True,
        )

    def fetch_html(
        self,
        url: str,
        *,
        timeout_ms: int = 60_000,
        wait_until: str = "networkidle",
        wait_for_selector: str | None = None,
    ) -> str:
        """Navigate the live Playwright page to `url` and return HTML.

        Onbid's mvmnCltrDtl.do refuses httpx GETs (404) and ships the real body
        inside an HTML comment that JS later replaces, so we wait for network
        idle (and optionally a content selector) before snapshotting.
        """
        if self._page is None:
            raise RuntimeError("Playwright page is not available on this session")
        self._page.goto(url, wait_until=wait_until, timeout=timeout_ms)  # type: ignore[arg-type]
        if wait_for_selector:
            try:
                self._page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
            except Exception:
                pass
        return self._page.content()

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            self._browser = None
            self._context = None
            self._page = None
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None

    def __enter__(self) -> "OnbidSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _dismiss_popups(page: Page, selectors: dict[str, Any]) -> None:
    for sel in selectors.get("popups", {}).get("close", []):
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                loc.click(timeout=1500)
        except Exception:
            pass


def create_session(headless: bool = True) -> OnbidSession:
    criteria = load_criteria()
    selectors = load_selectors()
    onbid = criteria["onbid"]
    base = onbid.get("base_url", "https://www.onbid.co.kr").rstrip("/")
    search_path = onbid["search_path"]
    search_url = f"{base}{search_path}"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="ko-KR", user_agent=user_agent)
        page = context.new_page()
        page.goto(search_url, wait_until="domcontentloaded", timeout=120_000)
        _dismiss_popups(page, selectors)

        csrf_meta = selectors["search_page"]["csrf_meta"]
        csrf = page.locator(csrf_meta).get_attribute("content")
        if not csrf:
            html = page.content()
            m = re.search(r'name="_csrf"\s+content="([^"]+)"', html)
            csrf = m.group(1) if m else ""

        cookies = {c["name"]: c["value"] for c in context.cookies()}
    except Exception:
        pw.stop()
        raise

    if not csrf:
        browser.close()
        pw.stop()
        raise RuntimeError("Failed to obtain CSRF token from Onbid search page")

    return OnbidSession(
        csrf_token=csrf,
        cookies=cookies,
        user_agent=user_agent,
        base_url=base,
        search_url=search_url,
        referer=search_url,
        _playwright=pw,
        _browser=browser,
        _context=context,
        _page=page,
    )
