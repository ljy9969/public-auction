"""Onbid 로그인 후 상세 페이지 HTML이 채워지는지 1회 probe.

사용 후 결과 출력만 — 영구 변경 없음.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.onbid.co.kr/op/cm/cmcommon/CommonController/login.do"
HOME_URL = "https://www.onbid.co.kr/"
# 능현오피스텔 상세
TEST_DETAIL = (
    "https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrdtl/CltrDtlController/mvmnCltrDtl.do"
    "?onbidCltrno=1952553&pbctCdtnNo=5842595&pbctNo=10023020&onbidPbancNo=885105"
)


def main() -> None:
    user = os.environ.get("ONBID_USER", "")
    pw = os.environ.get("ONBID_PASS", "")
    if not (user and pw):
        print("ONBID_USER / ONBID_PASS not set in .env"); return

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ko-KR")
        page = ctx.new_page()

        print("=== 1. Anonymous detail (control) ===")
        page.goto(TEST_DETAIL, wait_until="networkidle", timeout=60_000)
        html = page.content()
        print(f"len={len(html)} tables={html.count('<table')}")

        print("\n=== 2. Login attempt ===")
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        # Try common login link patterns
        for sel in ("a:has-text('로그인')", "a[href*='login']", "a[href*='Login']"):
            try:
                page.locator(sel).first.click(timeout=2000)
                print(f"clicked {sel}")
                break
            except Exception:
                pass
        page.wait_for_load_state("networkidle", timeout=30_000)
        print(f"url after login click: {page.url}")
        # Inspect login form
        inputs = page.locator("input").all()
        print(f"input count: {len(inputs)}")
        for i in inputs[:20]:
            try:
                name = i.get_attribute("name") or ""
                typ = i.get_attribute("type") or ""
                if name:
                    print(f"  input name={name!r} type={typ!r}")
            except Exception:
                pass

        # Try filling id/password — selectors guessed
        try:
            for s in ("input[name=userId]", "input[name=memId]", "input[id*=id]", "input[type=text]"):
                try:
                    page.locator(s).first.fill(user, timeout=2000)
                    print(f"filled user into {s}")
                    break
                except Exception:
                    pass
            for s in ("input[name=password]", "input[name=memPw]", "input[name=userPw]", "input[type=password]"):
                try:
                    page.locator(s).first.fill(pw, timeout=2000)
                    print(f"filled pw into {s}")
                    break
                except Exception:
                    pass
            # Submit
            for s in ("button:has-text('로그인')", "a:has-text('로그인')", "input[type=submit]"):
                try:
                    page.locator(s).first.click(timeout=2000)
                    print(f"clicked submit {s}")
                    break
                except Exception:
                    pass
            page.wait_for_load_state("networkidle", timeout=30_000)
            print(f"url after submit: {page.url}")
            print(f"title: {page.title()}")
        except Exception as exc:
            print(f"login failed: {exc}")

        print("\n=== 3. Logged-in detail ===")
        page.goto(TEST_DETAIL, wait_until="networkidle", timeout=60_000)
        html2 = page.content()
        print(f"len={len(html2)} tables={html2.count('<table')}")
        # Show first 500 chars of body content
        import re
        body = re.search(r"<body[^>]*>(.*?)</body>", html2, re.S)
        if body:
            content = body.group(1).strip()[:500]
            print(f"\nbody first 500:\n{content}")

        ctx.close()
        b.close()


if __name__ == "__main__":
    main()
