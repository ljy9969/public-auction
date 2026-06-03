"""기존 토지 지분 매물 land_share_ratio 백필 — court 상세 호출 기반.

검색 API 응답에는 분모/분자 정보 없음(2026-06-03 진단 확인). 상세 API
(fetch_detail) 응답의 dma_result.gdsDspslObjctLst[*].dspslStkCtt에
"갑구 N번 M분의 K ... 지분 전부" 형식으로 들어 있다 → _parse_land_share_ratio
정규식이 그대로 매칭.

대상: source='court' AND share_yn='Y' AND category LIKE '토지%' AND
      land_share_ratio IS NULL.

상세 호출은 court session(2초/req) 기준 30건 ≈ 1분. ipcheck 자극 안 함.

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

from scraper.db import get_connection  # noqa: E402  — ensure_columns
from scraper_court.detail import fetch_detail  # noqa: E402
from scraper_court.parse import _parse_land_share_ratio  # noqa: E402
from scraper_court.session import CourtSession  # noqa: E402


def main() -> int:
    get_connection().close()  # ALTER TABLE land_share_ratio 보장
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
    print(f"대상: {len(rows)}건 (court 상세 호출 2초/req → 약 {len(rows)*2/60:.1f}분)")
    if not rows:
        return 0

    updated = skipped = errors = 0
    with CourtSession() as sess:
        for r in rows:
            cs_no = r["court_case_no"]
            cort = r["court_office_cd"]
            seq = r["court_item_seq"] or 1
            try:
                d = fetch_detail(sess, cs_no=cs_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)
            except Exception as exc:
                errors += 1
                print(f"  [err] id={r['id']} {cs_no}-{seq}: {exc}")
                continue
            objs = d.get("gdsDspslObjctLst") or []
            ratio = None
            for o in objs:
                txt = o.get("dspslStkCtt") or ""
                ratio = _parse_land_share_ratio(txt)
                if ratio is not None:
                    break
            if ratio is None:
                skipped += 1
                first = objs[0] if objs else None
                snippet = (first.get("dspslStkCtt") if first else None) or "(빈 응답)"
                print(f"  [skip] id={r['id']} {cs_no}-{seq} — {snippet[:80]!r}")
                continue
            conn.execute(
                "UPDATE properties SET land_share_ratio=? WHERE id=?",
                (ratio, r["id"]),
            )
            updated += 1
            print(f"  [ok] id={r['id']} {cs_no}-{seq} ratio={ratio:.4f} ({ratio*100:.2f}%)")
    conn.commit()
    conn.close()
    print()
    print(f"updated: {updated}건, skipped: {skipped}건, errors: {errors}건")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
