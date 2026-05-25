"""Re-geocode every row in `properties` and refresh address_jibun + geo coords.

Use after improving address parsing or geocoder fallback so existing rows are
upgraded from dong-centroid placeholders to building-level coordinates.

    .\.venv\Scripts\python.exe -m scripts.backfill_geo
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection
from scraper.filters.coords import haversine_km
from scraper.filters.geo import resolve_coords
from scraper.parse import _extract_jibun
from scraper.session import load_criteria


def main() -> None:
    criteria = load_criteria()
    seo = criteria["regions"]["seolleung"]
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, address_jibun, region_line, geo_lat, geo_lng FROM properties"
    ).fetchall()
    updated = 0
    for row in rows:
        d = dict(row)
        title = d.get("title") or ""
        region = d.get("region_line") or ""
        jibun = _extract_jibun(title, region)
        new_addr = (
            f"{region} {jibun}".strip()
            if region and jibun
            else (d.get("address_jibun") or region or title)
        )
        coords = resolve_coords(
            {"address_jibun": new_addr, "title": title, "region_line": region},
            criteria,
            force=True,
        )
        if not coords:
            print(f"[skip] id={d['id']} no coords for {new_addr!r}")
            continue
        lat, lng = coords
        dist = round(haversine_km(lat, lng, seo["lat"], seo["lng"]), 2)
        conn.execute(
            "UPDATE properties SET address_jibun=?, geo_lat=?, geo_lng=?, distance_seolleung_km=? WHERE id=?",
            (new_addr, lat, lng, dist, d["id"]),
        )
        updated += 1
        print(f"[ok] id={d['id']} addr={new_addr!r} -> ({lat:.5f}, {lng:.5f}) {dist}km")
    conn.commit()
    conn.close()
    print(f"\nUpdated {updated}/{len(rows)} rows")


if __name__ == "__main__":
    main()
