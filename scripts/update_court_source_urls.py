"""기존 court 매물의 source_url을 PGJ151F00 + 사건번호 query params로 일괄 갱신.

신규 수집은 parse.py가 자동으로 새 URL을 박는다. 이 스크립트는 1회용 — 이미
DB에 들어간 행만 마이그레이션.

Usage:
    python -m scripts.update_court_source_urls
"""
from __future__ import annotations

import re
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

BASE = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"


def main() -> int:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, court_case_no, court_office_cd FROM properties WHERE source='court'"
    ).fetchall()
    print(f"court rows: {len(rows)}")

    n = 0
    for r in rows:
        case = r["court_case_no"] or ""
        cort = r["court_office_cd"] or ""
        m = re.match(r"(\d{4})\s*타경\s*(\d+)", case)
        parts: list[str] = []
        if cort:
            parts.append(f"cortOfcCd={cort}")
        if m:
            parts.append(f"saYear={m.group(1)}")
            parts.append(f"saSer={m.group(2)}")
        url = BASE + ("&" + "&".join(parts) if parts else "")
        conn.execute("UPDATE properties SET source_url=? WHERE id=?", (url, r["id"]))
        n += 1

    conn.commit()
    print(f"updated: {n}건")
    sample = conn.execute(
        "SELECT source_url FROM properties WHERE source='court' LIMIT 1"
    ).fetchone()
    if sample:
        print(f"sample: {sample[0]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
