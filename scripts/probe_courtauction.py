"""법원경매정보(courtauction.go.kr) 정찰 (P1).

목표: 검색 1회 + 상세 1회의 실제 JSON 페이로드·응답 + 용도 코드테이블 dump.
- 사용자가 직접 시연한 검색조건 재현: 서울 + 매각기일 2026.06.02~16 + 최저가 ≤1천만
- /pgj/pgjsearch/searchControllerMain.on POST 캡처
- 응답을 docs/courtauction_probe/ 에 저장

실행: python -m scripts.probe_courtauction
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "courtauction_probe"
OUT.mkdir(parents=True, exist_ok=True)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    captured: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.new_page()

        def on_request(req):
            url = req.url
            if ".on" in url and "courtauction" in url:
                try:
                    body = req.post_data
                except Exception:
                    body = None
                captured.append({
                    "phase": "request",
                    "url": url,
                    "method": req.method,
                    "headers": dict(req.headers),
                    "body": body[:5000] if body else None,
                })

        def on_response(resp):
            url = resp.url
            if ".on" in url and "courtauction" in url and resp.request.method == "POST":
                try:
                    text = resp.text()
                    snippet = text[:8000]
                except Exception:
                    snippet = None
                captured.append({
                    "phase": "response",
                    "url": url,
                    "status": resp.status,
                    "snippet": snippet,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        # 1) 물건상세검색 진입
        entry = (
            "https://www.courtauction.go.kr/pgj/index.on"
            "?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
        )
        print(f"[probe] entering {entry}")
        try:
            page.goto(entry, wait_until="networkidle", timeout=30_000)
        except Exception as e:
            print(f"[probe] goto exception: {e}")

        # 약간 대기 (코드테이블 로드)
        page.wait_for_timeout(2500)

        # 페이지 HTML 저장
        (OUT / "01_entry.html").write_text(page.content(), encoding="utf-8")
        print(f"[probe] saved entry HTML ({len(page.content())} bytes)")

        # 2) 검색 form 자동 채우기 시도 — WebSquare는 input id가 동적이라 일단 검색 버튼만 누름
        # 사용자가 묘사한 조건: 서울 + 1천만 이하 + 매각기일 6/2-6/16
        # 폼 자체는 디폴트에서 조금만 바꾸면 됨. 우선 디폴트 검색 한 번 트리거.
        try:
            # 검색 버튼은 보통 id에 "btn_search" 포함
            buttons = page.locator("input[type='button'], button").all()
            for b in buttons:
                try:
                    label = (b.get_attribute("value") or b.inner_text() or "").strip()
                    if label == "검색" or "검색" in label:
                        print(f"[probe] click '{label}'")
                        b.click(timeout=3_000)
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"[probe] could not click search: {e}")

        page.wait_for_timeout(3500)

        # 3) 캡처 저장
        (OUT / "02_network.json").write_text(
            json.dumps(captured, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[probe] saved {len(captured)} network events")

        # 4) WebSquare가 노출하는 코드테이블 dump — window scope 탐색
        try:
            tables = page.evaluate(
                """() => {
                    const dump = {};
                    const w = window;
                    for (const k of Object.keys(w)) {
                        if (/code|cd|tbl|lcl|mcl|scl/i.test(k)) {
                            try {
                                const v = w[k];
                                if (Array.isArray(v) && v.length && typeof v[0] === 'object') {
                                    dump[k] = v.slice(0, 80);
                                }
                            } catch (e) { /* skip */ }
                        }
                    }
                    return dump;
                }"""
            )
            (OUT / "03_codetables.json").write_text(
                json.dumps(tables, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[probe] saved {len(tables)} code-like globals")
        except Exception as e:
            print(f"[probe] codetable dump error: {e}")

        # 5) robots.txt + 이용약관 페이지 fetch
        try:
            robots = page.goto("https://www.courtauction.go.kr/robots.txt", wait_until="domcontentloaded", timeout=10_000)
            if robots:
                (OUT / "04_robots.txt").write_text(page.content(), encoding="utf-8")
                print(f"[probe] robots.txt HTTP {robots.status}")
        except Exception as e:
            print(f"[probe] robots fetch error: {e}")

        browser.close()

    print(f"\n[probe] outputs saved to {OUT}")
    for f in sorted(OUT.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name}: {size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
