"""기존 DB에 쌓인 법원경매(court) 중복 행 정리 1회성 스크립트.

배경:
    db.py upsert가 ON CONFLICT(cltr_no, pbct_cdtn_no)에 의존했는데,
    court 물건은 pbct_cdtn_no=NULL이라 SQLite UNIQUE가 충돌을 못 잡아
    재스크랩마다 중복 행이 쌓였다. db.py는 IS(NULL-safe) 조회 방식으로 수정됨.
    이 스크립트는 그 수정 '이전'에 쌓인 기존 중복만 1회 정리한다.

정책:
    cltr_no(=물건당 고유) 그룹에서 enrichment가 가장 많이 채워진 행을 남기고
    (동점이면 id 큰=최신) 나머지를 삭제한다.

사용:
    python scripts/dedup_court_rows.py          # 미리보기(삭제 안 함)
    python scripts/dedup_court_rows.py --apply   # 실제 삭제
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "onbid.db"
ENRICH = [
    "transit_minutes", "geo_lat", "rights_analysis",
    "predicted_price_median", "market_median_price", "image_url", "use_apr_day",
]


def main(apply: bool) -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    groups = con.execute(
        "SELECT cltr_no FROM properties "
        "WHERE source='court' AND pbct_cdtn_no IS NULL "
        "GROUP BY cltr_no HAVING COUNT(*) > 1"
    ).fetchall()

    to_delete: list[int] = []
    for g in groups:
        rows = con.execute(
            "SELECT * FROM properties "
            "WHERE source='court' AND pbct_cdtn_no IS NULL AND cltr_no=?",
            (g["cltr_no"],),
        ).fetchall()
        keep = max(
            rows,
            key=lambda r: (sum(1 for c in ENRICH if r[c] is not None), r["id"]),
        )
        to_delete += [r["id"] for r in rows if r["id"] != keep["id"]]

    print(f"중복 그룹: {len(groups)}, 삭제 대상 행: {len(to_delete)}")
    if not apply:
        print("미리보기만 수행 (실제 삭제하려면 --apply).")
        con.close()
        return

    con.executemany("DELETE FROM properties WHERE id=?", [(i,) for i in to_delete])
    con.commit()
    left = con.execute(
        "SELECT COUNT(*) FROM (SELECT cltr_no FROM properties "
        "WHERE source='court' AND pbct_cdtn_no IS NULL "
        "GROUP BY cltr_no HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    print(f"삭제 완료. 남은 court 중복 그룹: {left}")
    con.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
