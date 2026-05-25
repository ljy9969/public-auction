"""기존 properties 행에 건축물대장 정보(floor_total 등) 채우기.

Usage: .\.venv\Scripts\python.exe -m scripts.backfill_building
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection
from scraper.filters.building import fetch_building_info


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, address_jibun, floor_total FROM properties"
    ).fetchall()
    updated = 0
    for r in rows:
        addr = r["address_jibun"]
        if not addr:
            print(f"[skip] id={r['id']} no address")
            continue
        if r["floor_total"]:
            print(f"[skip] id={r['id']} already has floor_total={r['floor_total']}")
            continue
        info = fetch_building_info(addr)
        if not info:
            print(f"[miss] id={r['id']} addr={addr!r} — registry returned nothing")
            continue
        floor_total = int(float(info.get("grndFlrCnt") or 0)) or None
        bld_name = (info.get("bldNm") or "").strip() or None
        use_apr = (info.get("useAprDay") or "").strip() or None
        main_purps = (info.get("mainPurpsCdNm") or "").strip() or None
        ride_elv = int(float(info.get("rideUseElvtCnt") or 0))
        emer_elv = int(float(info.get("emgenUseElvtCnt") or 0))
        elevator_yn = "Y" if (ride_elv + emer_elv) > 0 else None
        conn.execute(
            """UPDATE properties
               SET floor_total = COALESCE(?, floor_total),
                   building_name = COALESCE(?, building_name),
                   use_apr_day = COALESCE(?, use_apr_day),
                   main_purps = COALESCE(?, main_purps)
               WHERE id = ?""",
            (floor_total, bld_name, use_apr, main_purps, r["id"]),
        )
        updated += 1
        print(
            f"[ok] id={r['id']} {bld_name or '?'} grnd={floor_total} elv={elevator_yn}"
            f" useApr={use_apr or '?'} purps={main_purps or '?'}"
        )
    conn.commit()
    conn.close()
    print(f"\nUpdated {updated}/{len(rows)} rows")


if __name__ == "__main__":
    main()
