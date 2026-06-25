"""법원경매 사건의 당사자내역(이해관계인 = 채권자·공유자 등) 백필.

source='court' 매물에 대해 selectCsDtlInf 호출 → parties_json + co_owner_count
저장. 이미 채워진 매물은 기본 skip(--force 로 강제 재조회).

Usage:
    python -m scripts.backfill_court_parties
    python -m scripts.backfill_court_parties --force
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper import db as scraper_db  # noqa: E402
from scraper_court.parties import (  # noqa: E402
    fetch_parties,
    normalize_parties,
)
from scraper_court.session import CourtSession  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="이미 채워진 매물도 다시 조회")
    args = parser.parse_args(argv)

    db_path = ROOT / "data" / "onbid.db"
    # get_connection() 안에서 _migrate()가 새 컬럼(parties_json, co_owner_count) 추가.
    scraper_db.get_connection(db_path).close()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    if args.force:
        rows = con.execute(
            """
            SELECT id, court_case_no, court_office_cd, address_jibun
            FROM properties
            WHERE source = 'court' AND court_case_no IS NOT NULL
              AND court_office_cd IS NOT NULL
            """
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT id, court_case_no, court_office_cd, address_jibun
            FROM properties
            WHERE source = 'court' AND court_case_no IS NOT NULL
              AND court_office_cd IS NOT NULL
              AND parties_json IS NULL
            """
        ).fetchall()
    con.close()

    if not rows:
        print("대상 0건 (이미 모두 채워짐)")
        return 0

    print(f"대상 {len(rows)}건 (court 상세 호출 ~2초/req → 약 {len(rows) * 2 // 60}분)")

    sess = CourtSession()
    sess.warm_up()

    ok = miss = err = 0
    for r in rows:
        addr = (r["address_jibun"] or "")[:40]
        try:
            raw = fetch_parties(
                sess,
                cs_no=r["court_case_no"],
                cort_ofc_cd=r["court_office_cd"],
            )
        except Exception as exc:
            err += 1
            logger.warning("id=%s %s — fetch err: %r", r["id"], addr, exc)
            continue
        parties, co_count = normalize_parties(raw)
        if not parties:
            scraper_db.set_parties(r["id"], None, 0)
            miss += 1
            print(f"  [miss] id={r['id']} {addr}")
            continue
        scraper_db.set_parties(r["id"], parties, co_count)
        ok += 1
        print(f"  [ok  ] id={r['id']} {addr} — {len(parties)}명, 공유자 {co_count}")

    sess.close()
    print(f"\n완료: ok={ok} miss={miss} err={err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
