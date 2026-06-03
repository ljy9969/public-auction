"""court 사이트에서 사라진 좀비 매물 정리.

신호: detail API(fetch_detail) 응답의 dma_result 키가 빈 [] = 그 사건이
court 사이트에서 더 이상 검색되지 않음(취하/매각완료/변경 등).

대상: source='court' AND share_yn='Y' AND category LIKE '토지%' AND
      land_share_ratio IS NULL.
  - 백필이 성공한 행은 ratio 채워져 있으므로 NULL 남은 행이 좀비 후보.
  - 신규 매물 timing 이슈로 NULL일 수 있으니 detail 한 번 더 확인 후 삭제.

Usage:
    python -m scripts.sweep_court_zombie               # dry-run (목록만)
    python -m scripts.sweep_court_zombie --delete      # 실제 삭제
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
from scraper_court.session import CourtSession  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true", help="실제 삭제 (기본 dry-run)")
    args = ap.parse_args()

    get_connection().close()
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, court_case_no, court_office_cd, court_item_seq, title
           FROM properties
           WHERE source='court'
             AND share_yn='Y'
             AND category LIKE '토지%'
             AND land_share_ratio IS NULL"""
    ).fetchall()
    print(f"좀비 후보: {len(rows)}건 (detail 한 번 더 확인)")

    zombies: list[int] = []
    with CourtSession() as sess:
        for r in rows:
            cs_no = r["court_case_no"]
            cort = r["court_office_cd"]
            seq = r["court_item_seq"] or 1
            try:
                d = fetch_detail(sess, cs_no=cs_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)
            except Exception as exc:
                print(f"  [err] id={r['id']} {cs_no}-{seq}: {exc} (좀비 미확정, skip)")
                continue
            if not d:  # 빈 dict
                zombies.append(r["id"])
                print(f"  [zombie] id={r['id']} {cs_no}-{seq} — {r['title']}")
            else:
                # detail 응답 차 있음 → 빈 응답 아님. NULL 사유 다른 것.
                print(f"  [keep] id={r['id']} {cs_no}-{seq} — detail OK, NULL 사유는 dspslStkCtt 패턴 미스")

    if not zombies:
        print("좀비 없음 — 정리할 것 없음.")
        conn.close()
        return 0

    print()
    print(f"좀비 확정: {len(zombies)}건 — id={zombies}")
    if not args.delete:
        print("(dry-run) --delete 로 실제 삭제.")
        conn.close()
        return 0

    placeholders = ",".join("?" * len(zombies))
    conn.execute(f"DELETE FROM properties WHERE id IN ({placeholders})", zombies)
    conn.commit()
    print(f"deleted: {len(zombies)}건")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
