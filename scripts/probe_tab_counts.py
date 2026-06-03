"""웹 탭 카운트 누락 원인 진단.

passes_filters=1 vs bid_end 미래 분포 + source + 카테고리 분포로
'왜 360 → 162 → 151'이 되는지 추적.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "onbid.db"
TODAY = date.today().isoformat()


def main() -> int:
    conn = sqlite3.connect(DB)

    total = conn.execute("SELECT COUNT(*) FROM properties WHERE passes_filters=1").fetchone()[0]
    print(f"== passes_filters=1 전체: {total}건 ==\n")

    future = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE passes_filters=1 "
        "AND substr(bid_end,1,10) >= ?",
        (TODAY,),
    ).fetchone()[0]
    past = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE passes_filters=1 "
        "AND substr(bid_end,1,10) < ?",
        (TODAY,),
    ).fetchone()[0]
    bid_null = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE passes_filters=1 "
        "AND (bid_end IS NULL OR bid_end='')"
    ).fetchone()[0]
    print(f"bid_end 분포 (오늘 {TODAY} 기준):")
    print(f"  >= 오늘 : {future:4d}건  ← 웹 탭에 보이는 후보")
    print(f"  <  오늘 : {past:4d}건  ← 자동 제외됨")
    print(f"  NULL     : {bid_null:4d}건  ← bid_end 없음 (어디로?)\n")

    # source 분포
    try:
        src = conn.execute(
            "SELECT COALESCE(source,'onbid'), COUNT(*) FROM properties "
            "WHERE passes_filters=1 GROUP BY source"
        ).fetchall()
        print("source 분포:")
        for s, n in src:
            print(f"  {s}: {n}건")
    except sqlite3.OperationalError:
        print("(source 컬럼 없음 — DB 구버전)")
    print()

    # bid_end 미래 매물의 카테고리 + source 분포 (탭 분류 시그널)
    print(f"bid_end >= 오늘({TODAY}) 매물의 카테고리 × source:")
    rows = conn.execute(
        "SELECT category, COALESCE(source,'onbid') AS src, share_yn, COUNT(*) "
        "FROM properties WHERE passes_filters=1 "
        "AND substr(bid_end,1,10) >= ? "
        "GROUP BY category, src, share_yn ORDER BY 4 DESC",
        (TODAY,),
    ).fetchall()
    print(f"  {'category':<40} {'src':<6} {'share':<5} {'cnt':>5}")
    for c, s, sh, n in rows[:25]:
        print(f"  {(c or '?'):<40} {s:<6} {sh or '-':<5} {n:>5}")
    print()

    # API limit=200 추정 영향
    print("API /api/properties?passes_only=true 기본 limit=200")
    print(f"  → DB {total}건 중 {min(total, 200)}건 반환")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
