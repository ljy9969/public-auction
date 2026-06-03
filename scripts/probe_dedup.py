"""upsert dedup 이슈 진단 — court 매물 중복 + SQLite IS ? 동작 검증.

가설: upsert_property의 'WHERE cltr_no=? AND pbct_cdtn_no IS ?' 에 None
바인딩 시, SQLite 가 'IS NULL' 로 정상 해석하지 못해 항상 빈 결과를
돌려준다 → 매번 새 INSERT → 같은 cltr_no가 N번 들어감.

Usage:
    python -m scripts.probe_dedup
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

    print("=== 1) court 매물 중 cltr_no 중복 (상위 10) ===")
    rows = conn.execute(
        """SELECT cltr_no, COUNT(*) n
           FROM properties
           WHERE source='court'
           GROUP BY cltr_no
           HAVING COUNT(*) > 1
           ORDER BY n DESC
           LIMIT 10"""
    ).fetchall()
    for r in rows:
        print(f"  cltr_no={r['cltr_no']!r:32s} n={r['n']}")
    if not rows:
        print("  중복 없음 — 이미 정리됨?")

    print()
    print("=== 2) court 매물 pbct_cdtn_no 분포 ===")
    rows2 = conn.execute(
        """SELECT
             SUM(CASE WHEN pbct_cdtn_no IS NULL THEN 1 ELSE 0 END) as nulls,
             SUM(CASE WHEN pbct_cdtn_no IS NOT NULL THEN 1 ELSE 0 END) as notnulls,
             COUNT(*) as total
           FROM properties WHERE source='court'"""
    ).fetchone()
    print(f"  NULL: {rows2['nulls']}건, NOT NULL: {rows2['notnulls']}건, 총 {rows2['total']}건")

    print()
    print("=== 3) SQLite 'IS ?' + None 바인딩 동작 검증 ===")
    sample = conn.execute(
        "SELECT cltr_no FROM properties WHERE source='court' AND pbct_cdtn_no IS NULL LIMIT 1"
    ).fetchone()
    if not sample:
        print("  court+NULL 샘플 없음 — 건너뜀")
    else:
        cltr = sample["cltr_no"]
        print(f"  샘플 cltr_no={cltr!r}")
        a = conn.execute(
            "SELECT id FROM properties WHERE cltr_no=? AND pbct_cdtn_no IS ?",
            (cltr, None),
        ).fetchall()
        b = conn.execute(
            "SELECT id FROM properties WHERE cltr_no=? AND pbct_cdtn_no IS NULL",
            (cltr,),
        ).fetchall()
        c = conn.execute(
            "SELECT id FROM properties WHERE cltr_no=? AND pbct_cdtn_no = ?",
            (cltr, None),
        ).fetchall()
        print(f"  WHERE pbct_cdtn_no IS ?     + None : {len(a)}건  (upsert 가 쓰는 쿼리)")
        print(f"  WHERE pbct_cdtn_no IS NULL          : {len(b)}건  (정답)")
        print(f"  WHERE pbct_cdtn_no = ?      + None : {len(c)}건  (= 는 NULL 매칭 안 됨, 0이 정상)")
        if len(a) == 0 and len(b) > 0:
            print("  ★ 버그 확정 — 'IS ?' + None 이 매칭 실패 → upsert 가 매번 새 INSERT")
        elif len(a) == len(b):
            print("  IS ? + None 정상 매칭 — 중복 원인은 다른 곳")

    print()
    print("=== 4) 중복 매물 1건의 id별 pbct_cdtn_no/scraped_at 비교 ===")
    if rows:
        cltr = rows[0]["cltr_no"]
        dets = conn.execute(
            "SELECT id, cltr_no, pbct_cdtn_no, scraped_at, share_yn "
            "FROM properties WHERE source='court' AND cltr_no=? ORDER BY id",
            (cltr,),
        ).fetchall()
        print(f"  cltr_no={cltr!r} → {len(dets)}건")
        for d in dets:
            print(
                f"    id={d['id']} pbct_cdtn_no={d['pbct_cdtn_no']!r} "
                f"scraped_at={d['scraped_at']}"
            )

    print()
    print("=== 5) 중복 4건의 cltr_no byte-level 비교 (미세 차이 탐지) ===")
    if rows:
        cltr = rows[0]["cltr_no"]
        dets = conn.execute(
            "SELECT id, cltr_no FROM properties WHERE source='court' AND cltr_no=? ORDER BY id",
            (cltr,),
        ).fetchall()
        bytes_seen: set[bytes] = set()
        for d in dets:
            b = d["cltr_no"].encode("utf-8")
            bytes_seen.add(b)
            print(f"  id={d['id']} bytes={b!r} len={len(b)}")
        if len(bytes_seen) == 1:
            print("  → 모두 동일한 bytes. cltr_no 차이 아님.")
        else:
            print(f"  → {len(bytes_seen)}가지 다른 bytes! 미세 차이 있음.")

    print()
    print("=== 6) court 매물 source/source_url 분포 ===")
    rows6 = conn.execute(
        """SELECT cltr_no, COUNT(DISTINCT source_url) usrc, COUNT(*) n
           FROM properties WHERE source='court'
           GROUP BY cltr_no HAVING COUNT(*) > 1
           ORDER BY n DESC LIMIT 5"""
    ).fetchall()
    for r in rows6:
        print(f"  cltr_no={r['cltr_no']!r:30s} n={r['n']}  distinct source_url={r['usrc']}")

    print()
    print("=== 7) 한 scrape 내 등장한 raw 응답 추적 — court_item_seq 분포 ===")
    # 같은 cltr_no 중복 행의 court_case_no / court_item_seq 가 정말 모두 같은지
    if rows:
        cltr = rows[0]["cltr_no"]
        dets = conn.execute(
            """SELECT id, court_case_no, court_item_seq, court_office_cd
               FROM properties WHERE source='court' AND cltr_no=? ORDER BY id""",
            (cltr,),
        ).fetchall()
        for d in dets:
            print(
                f"  id={d['id']} case_no={d['court_case_no']!r} "
                f"item_seq={d['court_item_seq']} cort={d['court_office_cd']}"
            )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
