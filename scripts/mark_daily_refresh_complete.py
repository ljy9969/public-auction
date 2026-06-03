"""daily-scrape 사이클 완료 시점을 search_runs에 별도 행으로 기록.

배경: scraper.run(onbid)은 흐름 초반(~10분)에 finish_run으로 끝나지만,
그 뒤 scraper_court.run + 5종 backfill이 더 돈다. _latest_db_run이
가장 최근 finished_at을 가져오는 구조라, 사용자가 보는 '마지막 갱신'이
onbid 종료 시점(흐름 초반)으로 고정됨 → 전체 사이클 완료 시점과 어긋남.

daily-scrape.ps1 마지막 단계에서 이 스크립트를 호출하면 'daily-refresh'
라벨의 instant 행 1건이 추가되고 _latest_db_run이 그걸 선택 → 화면에
전체 사이클 완료 시점이 표시.

Usage:
    python -m scripts.mark_daily_refresh_complete
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection  # noqa: E402


def main() -> int:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    n = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE passes_filters=1"
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO search_runs (criteria_json, started_at, finished_at, count) "
        "VALUES (?, ?, ?, ?)",
        (json.dumps({"label": "daily-refresh"}, ensure_ascii=False), now, now, n),
    )
    conn.commit()
    print(f"marked daily-refresh: id={cur.lastrowid} at {now}, count={n}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
