"""기존 토지 지분 매물 land_share_ratio 백필 — 1회용.

신규 수집은 parse.py가 자동으로 채우지만, 컬럼 신설 이전에 들어온 행은
NULL. court의 buldList가 title에 통째로 박혀 있어 title 자체에 'N분의 M'
패턴이 있다 — 그걸로 추출.

대상: source='court' AND share_yn='Y' AND category LIKE '토지%' AND
      land_share_ratio IS NULL.

Usage:
    python -m scripts.backfill_land_share_ratio
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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper_court.parse import _parse_land_share_ratio  # noqa: E402


def main() -> int:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, title, detail_json
           FROM properties
           WHERE source='court'
             AND share_yn='Y'
             AND category LIKE '토지%'
             AND land_share_ratio IS NULL"""
    ).fetchall()
    print(f"대상: {len(rows)}건")

    updated = skipped = 0
    for r in rows:
        # detail_json.비고(=mulBigo)에도 'N분의 M'이 있을 수 있으니 같이 후보로.
        bigo = ""
        if r["detail_json"]:
            try:
                import json
                d = json.loads(r["detail_json"])
                bigo = d.get("비고") or ""
            except Exception:
                pass
        ratio = _parse_land_share_ratio(r["title"] or "", bigo)
        if ratio is None:
            skipped += 1
            print(f"  [skip] id={r['id']} 패턴 없음 — title={r['title'][:80]!r}")
            continue
        conn.execute(
            "UPDATE properties SET land_share_ratio=? WHERE id=?",
            (ratio, r["id"]),
        )
        updated += 1
        print(f"  [ok] id={r['id']} ratio={ratio:.4f} ({ratio*100:.1f}%)")
    conn.commit()
    conn.close()
    print()
    print(f"updated: {updated}건, skipped: {skipped}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
