"""법원경매 차량·기타 매물 일소 (1회용).

2026-06-03: 차량 매물이 category='기타'로 우회 통과했던 버그(e059c6b)
픽스 후 기존 DB에 남은 row 정리. 새 수집부턴 자동 차단.
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
    # timeout=30 — uvicorn 백엔드가 동시 connection 잡고 있을 때 30초까지 대기.
    conn = sqlite3.connect(DB, timeout=30)
    # 차량 + 기타 카테고리 court 매물
    cars = conn.execute(
        "SELECT id, court_case_no, title FROM properties "
        "WHERE source='court' AND (category='기타' OR category LIKE '기타%')"
    ).fetchall()
    print(f"대상: {len(cars)}건")
    for cid, case, title in cars[:10]:
        print(f"  id={cid} {case} — {title[:60]}")
    if len(cars) > 10:
        print(f"  ...외 {len(cars) - 10}건")

    n = conn.execute(
        "DELETE FROM properties WHERE source='court' AND (category='기타' OR category LIKE '기타%')"
    ).rowcount
    conn.commit()
    conn.close()
    print(f"\n삭제 완료: {n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
