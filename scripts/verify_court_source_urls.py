"""court source_url 마이그레이션 검증 — 1회용.

update_court_source_urls 실행 후 모든 court 행이 새 형식
(PGJ151F00 + #cort=...&name=...&year=...&sa=...)으로 갱신됐는지 확인.

Usage:
    python -m scripts.verify_court_source_urls
"""
from __future__ import annotations

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


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, court_case_no, court_office_nm, source_url "
        "FROM properties WHERE source='court'"
    ).fetchall()
    total = len(rows)
    print(f"court rows: {total}")
    if total == 0:
        print("(no court rows — 마이그레이션 대상 없음)")
        return 0

    checks = {
        "PGJ151F00": "PGJ151F00",
        "#cort=":    "#cort=",
        "name=":     "name=",
        "year=":     "year=",
        "sa=":       "sa=",
    }
    for label, needle in checks.items():
        n = sum(1 for r in rows if needle in (r["source_url"] or ""))
        mark = "OK" if n == total else "!!"
        print(f"  [{mark}] {label:12s} {n}/{total}")

    # 서로 다른 법원 샘플 3건 — 폼 prefill이 어떤 값을 받는지 직관 확인용.
    seen: set[str] = set()
    samples = []
    for r in rows:
        nm = r["court_office_nm"] or ""
        if nm in seen:
            continue
        seen.add(nm)
        samples.append(r)
        if len(samples) >= 3:
            break
    if samples:
        print()
        print("샘플:")
        for s in samples:
            print(f"  id={s['id']} {s['court_office_nm']} {s['court_case_no']}")
            print(f"    {s['source_url']}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
