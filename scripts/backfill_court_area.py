"""court 매물 호수/필지 단위 정확한 면적 백필 (detail.objctArDts).

검색 API minArea 는 동 전체 면적을 돌려주는 케이스가 있어 호수 전용면적
(예: 길동청광플러스원큐브 1306호 = 16.685㎡) 과 60배 차이. detail 의
gdsDspslObjctLst[0].objctArDts 에서 호수 단위 면적을 추출해 area_build_m2
보정.

Usage:
    python -m scripts.backfill_court_area              # 전체
    python -m scripts.backfill_court_area --limit 5    # 테스트
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
from scraper_court.parse import extract_areas  # noqa: E402
from scraper_court.session import CourtSession  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="처리 건수 상한 (0=무제한)")
    args = ap.parse_args(argv)

    get_connection().close()
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, cltr_no, court_case_no, court_office_cd, court_item_seq,
                  area_build_m2, land_area_m2, title
           FROM properties
           WHERE source='court' AND court_case_no IS NOT NULL AND court_office_cd IS NOT NULL
           ORDER BY id"""
    ).fetchall()
    if args.limit:
        rows = list(rows)[: args.limit]
    print(f"대상: {len(rows)}건 (court 상세 호출 2초/req → 약 {len(rows)*2/60:.1f}분)")
    if not rows:
        return 0

    updated = unchanged = missing = errors = 0
    with CourtSession() as sess:
        for r in rows:
            pid = int(r["id"])
            cs_no = r["court_case_no"]
            cort = r["court_office_cd"]
            seq = r["court_item_seq"] or 1
            try:
                d = fetch_detail(sess, cs_no=cs_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)
            except Exception as exc:
                errors += 1
                print(f"  [err] id={pid} {cs_no}-{seq}: {exc}")
                continue
            new_area, new_land = extract_areas(d)
            if new_area is None:
                missing += 1
                print(f"  [no-area] id={pid} {cs_no}-{seq}")
                continue
            old = r["area_build_m2"]
            old_land = r["land_area_m2"]
            area_same = old is not None and abs(old - new_area) < 0.01
            land_same = (new_land is None) or (
                old_land is not None and abs(old_land - new_land) < 0.01
            )
            if area_same and land_same:
                unchanged += 1
                print(f"  [ok] id={pid} {cs_no}-{seq} {new_area}㎡ (변경 없음)")
                continue
            # land 는 일괄매각에서만 잡힘 — None 이면 기존값 보존(COALESCE 의미)
            conn.execute(
                "UPDATE properties SET area_build_m2=?, land_area_m2=COALESCE(?, land_area_m2) WHERE id=?",
                (new_area, new_land, pid),
            )
            updated += 1
            old_s = f"{old}㎡" if old is not None else "None"
            land_s = f" · 토지 {new_land}㎡" if new_land is not None else ""
            print(f"  [upd] id={pid} {cs_no}-{seq} {old_s} → {new_area}㎡{land_s}")
    conn.commit()
    conn.close()
    print()
    print(f"updated: {updated}건, unchanged: {unchanged}건, "
          f"no-area: {missing}건, errors: {errors}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
