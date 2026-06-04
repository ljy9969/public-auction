"""court 매물 현재 회차 최저매각가 백필.

검색 API minmaePrice 는 첫 회차(=감정가) 만 반환하므로 유찰된 매물의
감액 가격이 안 들어온다. detail API 의 gdsDspslDxdyLst 에서 진행 중
회차의 tsLwsDspslPrc 를 가져와 min_price 를 보정.

대상: source='court' 매물 전체. 변경 없는 매물은 UPDATE skip.

대상 수 × 2초 (court session rate limit) ≈ 250 매물 = 약 8분.

Usage:
    python -m scripts.backfill_court_prices               # 전체
    python -m scripts.backfill_court_prices --limit 5     # 테스트
    python -m scripts.backfill_court_prices --only-failed # 유찰된 매물만
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "onbid.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection  # noqa: E402
from scraper_court.detail import fetch_detail  # noqa: E402
from scraper_court.parse import extract_current_min_price  # noqa: E402
from scraper_court.session import CourtSession  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="처리 건수 상한 (0=무제한)")
    ap.add_argument("--only-failed", action="store_true",
                    help="fail_count > 0 (유찰된) 매물만 — 1차는 search 값=감정가가 정상")
    args = ap.parse_args(argv)

    get_connection().close()  # ensure_columns
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    where = "source='court' AND court_case_no IS NOT NULL AND court_office_cd IS NOT NULL"
    if args.only_failed:
        where += " AND fail_count > 0"
    rows = conn.execute(
        f"""SELECT id, cltr_no, court_case_no, court_office_cd, court_item_seq,
                   min_price, fail_count
            FROM properties WHERE {where} ORDER BY id"""
    ).fetchall()
    if args.limit:
        rows = list(rows)[: args.limit]
    print(f"대상: {len(rows)}건 (court 상세 호출 2초/req → 약 {len(rows)*2/60:.1f}분)")
    if not rows:
        return 0

    updated = unchanged = missing = errors = 0
    with CourtSession() as sess:
        for r in rows:
            pid = int(r["id"])
            cs_no = r["court_case_no"]
            cort = r["court_office_cd"]
            seq = r["court_item_seq"] or 1
            try:
                d = fetch_detail(sess, cs_no=cs_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)
            except Exception as exc:
                errors += 1
                print(f"  [err] id={pid} {cs_no}-{seq}: {exc}")
                continue
            current = extract_current_min_price(d)
            if current is None:
                missing += 1
                print(f"  [no-current] id={pid} {cs_no}-{seq} (회차 없음 또는 종결)")
                continue
            old = r["min_price"]
            if old == current:
                unchanged += 1
                print(f"  [ok] id={pid} {cs_no}-{seq} {current:,}원 (변경 없음)")
                continue
            conn.execute("UPDATE properties SET min_price=? WHERE id=?", (current, pid))
            updated += 1
            old_s = f"{old:,}" if old is not None else "None"
            print(f"  [upd] id={pid} {cs_no}-{seq} {old_s} → {current:,}원 (유찰 {r['fail_count']}회)")
    conn.commit()
    conn.close()
    print()
    print(f"updated: {updated}건, unchanged: {unchanged}건, "
          f"no-current: {missing}건, errors: {errors}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
