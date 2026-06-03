"""기존 court 매물의 source_url을 PGJ151F00 진입점으로 일괄 갱신.

WebSquare가 URL query params를 prefill로 인식하지 않음을 확인(2026-06-03).
params 없이 진입점만 박는다.

Usage:
    python -m scripts.update_court_source_urls
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

URL = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"


def main() -> int:
    conn = sqlite3.connect(DB, timeout=30)
    n = conn.execute(
        "UPDATE properties SET source_url=? WHERE source='court'", (URL,)
    ).rowcount
    conn.commit()
    conn.close()
    print(f"updated: {n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
