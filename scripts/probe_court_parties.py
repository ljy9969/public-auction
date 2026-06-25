"""법원경매정보 사건상세조회 — 당사자내역 XHR endpoint 캡처 정찰.

평택지원 2025타경42692 (안중읍 성해리 산43-3)을 표적 케이스로:
  PGJ151F00 > prefill(법원/연도/사건번호) > 검색 > 소재지 클릭 >
  사건상세조회 클릭 > 사건내역 탭
의 단계에서 발생하는 XHR을 모두 캡처한다.

Usage:
    python -m scripts.probe_court_parties
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "probe-court-parties.json"

ENTRY = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"

# userscript에서 검증된 selector
SEL_CORT = "#mf_wfm_mainFrame_sbx_rletCortOfc"
SEL_YEAR = "#mf_wfm_mainFrame_sbx_rletCsYear"
SEL_SA = "#mf_wfm_mainFrame_ibx_rletCsNo"

CORT_CODE = "B000253"  # 수원지방법원 평택지원
CORT_NAME = "평택지원"
YEAR = "2025"
SA = "42692"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    captures: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()

        def on_request(req):
            if ".on" in req.url and req.method == "POST":
                try:
                    body = req.post_data_json
                except Exception:
                    body = req.post_data
                captures.append({
                    "url": req.url,
                    "method": req.method,
                    "headers": {k: v for k, v in req.headers.items()
                                if k.lower() in ("submissionid", "sc-userid",
                                                 "content-type", "referer")},
                    "body": body,
                })

        page.on("request", on_request)

        print(f"[1] entry: {ENTRY}")
        page.goto(ENTRY, wait_until="domcontentloaded")

        # option 로드 대기 — cort select에 5개 이상
        print("[2] wait for cort options")
        page.wait_for_function(
            f"document.querySelector('{SEL_CORT}') && document.querySelector('{SEL_CORT}').options.length > 5",
            timeout=15000,
        )

        # prefill — userscript 패턴
        print(f"[3] prefill cort={CORT_CODE} year={YEAR} sa={SA}")
        page.evaluate(
            """
            (args) => {
              const fire = (el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                if (window.jQuery) window.jQuery(el).trigger('change');
              };
              const elCort = document.querySelector(args.selCort);
              // option.value 매칭 우선, 못 찾으면 text 매칭
              let cortVal = null;
              for (const opt of elCort.options) {
                if (opt.value === args.cortCode) { cortVal = opt.value; break; }
              }
              if (cortVal == null) {
                for (const opt of elCort.options) {
                  if ((opt.text || '').trim() === args.cortName) { cortVal = opt.value; break; }
                }
              }
              fire(elCort, cortVal);
              fire(document.querySelector(args.selYear), args.year);
              fire(document.querySelector(args.selSa), args.sa);
            }
            """,
            {
                "selCort": SEL_CORT,
                "selYear": SEL_YEAR,
                "selSa": SEL_SA,
                "cortCode": CORT_CODE,
                "cortName": CORT_NAME,
                "year": YEAR,
                "sa": SA,
            },
        )
        page.wait_for_timeout(500)

        print("[4] click 검색")
        page.evaluate(
            """
            () => {
              for (const b of document.querySelectorAll('input[type="button"]')) {
                if ((b.value || '').trim() === '검색') { b.click(); return; }
              }
              for (const b of document.querySelectorAll('button')) {
                if ((b.textContent || '').trim() === '검색') { b.click(); return; }
              }
            }
            """
        )
        page.wait_for_timeout(3000)

        # 결과 표의 소재지 링크(앵커 텍스트가 주소) 또는 사건번호 셀 클릭
        print("[5] click result row (소재지 또는 사건번호)")
        try:
            page.locator("a:has-text('성해리')").first.click(timeout=8000)
        except Exception:
            try:
                page.locator("a:has-text('평택시')").first.click(timeout=8000)
            except Exception as e:
                print(f"[5] result link click failed: {e}")
        page.wait_for_timeout(3000)

        print("[6] click 사건상세조회")
        try:
            page.evaluate(
                """
                () => {
                  for (const b of document.querySelectorAll('input[type="button"], button, a')) {
                    const t = (b.value || b.textContent || '').trim();
                    if (t === '사건상세조회' || t.includes('사건상세조회')) { b.click(); return; }
                  }
                }
                """
            )
        except Exception as e:
            print(f"[6] 사건상세조회 click failed: {e}")
        page.wait_for_timeout(3000)

        # 사건내역 탭 클릭 (기본 선택일 수도)
        print("[7] click 사건내역 tab")
        try:
            page.evaluate(
                """
                () => {
                  for (const b of document.querySelectorAll('button, a, span, li, div')) {
                    const t = (b.textContent || '').trim();
                    if (t === '사건내역') { b.click(); return; }
                  }
                }
                """
            )
        except Exception:
            pass
        page.wait_for_timeout(2500)

        # 페이지 HTML 일부 — 당사자내역 표 확인
        html = page.content()
        idx = html.find("당사자내역")
        if idx >= 0:
            print(f"[OK] '당사자내역' found at {idx} in DOM")
            (ROOT / "docs" / "probe-court-parties.html").write_text(
                html[idx:idx + 6000], encoding="utf-8"
            )
        else:
            print("[WARN] '당사자내역' NOT found in DOM")
            (ROOT / "docs" / "probe-court-parties.html").write_text(
                html[:20000], encoding="utf-8"
            )

        browser.close()

    print(f"\n=== captured {len(captures)} POST .on requests ===")
    for c in captures:
        url_short = c["url"].replace("https://www.courtauction.go.kr", "")
        sub = c["headers"].get("submissionid", "-")
        body_keys = "<str>"
        if isinstance(c["body"], dict):
            body_keys = list(c["body"].keys())
        print(f"  {url_short}")
        print(f"    submission={sub} body={body_keys}")

    OUT.write_text(json.dumps(captures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nfull capture → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
