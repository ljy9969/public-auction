"""Drop all scraped properties and search-run records.

Usage:
    .\.venv\Scripts\python.exe -m scripts.reset_db          # delete all
    .\.venv\Scripts\python.exe -m scripts.reset_db --failed # delete passes_filters=0 only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection


def reset(*, failed_only: bool) -> None:
    conn = get_connection()
    if failed_only:
        cur = conn.execute("DELETE FROM properties WHERE passes_filters = 0")
        print(f"Deleted {cur.rowcount} failed rows")
    else:
        cur = conn.execute("DELETE FROM properties")
        print(f"Deleted {cur.rowcount} property rows")
        cur = conn.execute("DELETE FROM search_runs")
        print(f"Deleted {cur.rowcount} search_runs rows")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset Onbid scraper DB")
    parser.add_argument("--failed", action="store_true", help="Delete only passes_filters=0 rows")
    args = parser.parse_args()
    reset(failed_only=args.failed)
