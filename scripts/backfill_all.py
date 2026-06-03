"""모든 외부 API 통합 백필 — 건축물대장 + ODsay 한 번에.

기존 DB 행에 floor_total / building_name / use_apr_day / main_purps /
address_road / transit_minutes / transit_mode / transit_summary 채움.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection
from scraper.filters.building import fetch_building_info
from scraper.filters.transit import apply_transit_filter


def _safe_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, address_jibun, address_road, title, region_line,
                  geo_lat, geo_lng, floor_total, category
           FROM properties"""
    ).fetchall()
    for r in rows:
        addr = r["address_jibun"]
        updates: dict = {}

        # 1. 건축물대장 — floor_total 비어 있거나 address_road 없을 때
        if addr and (not r["floor_total"] or not r["address_road"]):
            info = fetch_building_info(addr)
            if info:
                updates["floor_total"] = _safe_int(info.get("grndFlrCnt"))
                updates["building_name"] = (info.get("bldNm") or "").strip() or None
                updates["use_apr_day"] = (info.get("useAprDay") or "").strip() or None
                updates["main_purps"] = (info.get("mainPurpsCdNm") or "").strip() or None
                updates["address_road"] = (info.get("newPlatPlc") or "").strip() or None

        # 2. ODsay 대중교통 — 매번 재계산 (오피스텔/용도복합만, 2026-06-03 정책)
        prop = {
            "address_jibun": r["address_jibun"],
            "title": r["title"],
            "region_line": r["region_line"],
            "geo_lat": r["geo_lat"],
            "geo_lng": r["geo_lng"],
            "category": r["category"],  # apply_transit_filter의 오피스텔 가드용
        }
        t = apply_transit_filter(prop)
        updates["transit_minutes"] = t.get("transit_minutes")
        updates["transit_mode"] = t.get("transit_mode")
        updates["transit_summary"] = t.get("transit_summary")
        updates["transit_estimated"] = 1 if t.get("transit_estimated") else 0

        # COALESCE로 기존값 보존 (None이면 덮어쓰지 않음, address_road 빼고)
        sets = ", ".join(
            f"{k} = COALESCE(?, {k})" if k != "address_road" else f"{k} = ?"
            for k in updates
        )
        params = list(updates.values()) + [r["id"]]
        conn.execute(f"UPDATE properties SET {sets} WHERE id = ?", params)
        print(
            f"[ok] id={r['id']} floor={updates.get('floor_total')} "
            f"road={updates.get('address_road') or '?'} "
            f"transit={updates.get('transit_minutes')}분({updates.get('transit_mode')}) "
            f"summary={updates.get('transit_summary') or '-'}"
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
