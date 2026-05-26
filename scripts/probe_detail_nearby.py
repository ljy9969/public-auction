"""Probe: 상세 페이지 진입 + 인근 시세/낙찰 사례 섹션 AJAX 식별."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

URL = "https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrcdtnsrch/CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do?srchCltrMnmtNo=2025-17474-001"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR", viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        requests: list[dict] = []
        responses: list[dict] = []

        page.on("request", lambda req: requests.append({"url": req.url, "method": req.method, "post": req.post_data}))

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct or "text" in ct:
                    responses.append({"url": resp.url, "status": resp.status, "ct": ct})
            except Exception:
                pass

        page.on("response", on_response)

        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(2000)
        page.evaluate("() => { const a = document.querySelector('a.con_area01'); if (a) a.click(); }")
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.wait_for_timeout(3000)

        # 스크롤
        for _ in range(8):
            page.evaluate("() => window.scrollBy(0, 800)")
            page.wait_for_timeout(700)
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.wait_for_timeout(1500)

        # 인근 시세 탭 클릭 — data-target="tab4"
        print("\n=== Clicking tab4 (인근 시세 및 낙찰 사례) ===")
        requests_before = len(requests)
        try:
            page.evaluate(
                "() => { const a = document.querySelector('a[data-target=\"tab4\"]'); if (a) a.click(); }"
            )
            page.wait_for_load_state("networkidle", timeout=30_000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print("tab4 click err:", e)

        # 탭 클릭 이후 요청만
        print("\n=== Tab4 클릭 이후 새 요청들 ===")
        for r in requests[requests_before:]:
            u = r["url"]
            print(f"  [{r['method']}] {u[:200]}")
            if r.get("post"):
                print(f"    body: {r['post'][:250]}")

        # 페이지의 "인근 시세 및 낙찰 사례" 관련 텍스트가 보이는지
        html = page.content()
        print(f"\n=== Detail page HTML length: {len(html)} ===")
        for kw in ("인근 시세", "낙찰 사례", "낙찰가율", "인근 낙찰", "주변 시세"):
            cnt = html.count(kw)
            print(f"  '{kw}' 등장 횟수: {cnt}")

        # 인근 시세 섹션을 채우는 AJAX 식별 — 모든 POST + GET ajax 추출
        print()
        print("=== 상세 페이지 진입 이후 POST/AJAX endpoints (cltrdtl/* 또는 cltr/* 위주) ===")
        seen = set()
        for r in requests:
            u = r["url"]
            if "/cltrdtl/" not in u and "/cltr/" not in u:
                continue
            key = u.split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{r['method']}] {u[:200]}")
            if r.get("post"):
                # 처음 일부 body
                print(f"    body: {r['post'][:200]}")

        # HTML에서 '인근' 키워드 주변 추출
        print()
        print("=== HTML 안 '인근/주변/낙찰' 주변 콘텐츠 ===")
        for kw in ("인근 시세", "낙찰 사례", "낙찰가율"):
            idx = html.find(kw)
            if idx > 0:
                snippet = re.sub(r"\s+", " ", html[max(0, idx-50):idx+250])
                print(f"  '{kw}': ...{snippet}...")

        browser.close()


if __name__ == "__main__":
    main()
