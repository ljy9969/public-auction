"""기존 properties 행의 transit_minutes/transit_mode를 ODsay 기반으로 재계산."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection
from scraper.filters.transit import apply_transit_filter


def main() -> None:
    conn = get_connection()
    # ODsay 예산 가드(별도 커넥션)와 잠금 충돌 방지 — busy_timeout + per-row commit.
    conn.execute("PRAGMA busy_timeout=15000")
    rows = conn.execute(
        "SELECT id, address_jibun, title, region_line, geo_lat, geo_lng FROM properties"
    ).fetchall()
    updated = 0
    for r in rows:
        prop: dict = {
            "address_jibun": r["address_jibun"],
            "title": r["title"],
            "region_line": r["region_line"],
            "geo_lat": r["geo_lat"],
            "geo_lng": r["geo_lng"],
        }
        out = apply_transit_filter(prop)
        minutes = out.get("transit_minutes")
        mode = out.get("transit_mode")
        estimated = out.get("transit_estimated")
        if minutes is None:
            # ODsay 일일 한도 이월(deferred) 또는 좌표 미해결 → 다음 실행에서 재시도
            deferred = any(
                "deferred (ODsay" in n for n in (out.get("filter_notes") or [])
            )
            print(f"[{'defer' if deferred else 'miss'}] id={r['id']}")
            continue
        conn.execute(
            "UPDATE properties SET transit_minutes=?, transit_mode=?, transit_estimated=? WHERE id=?",
            (minutes, mode, 1 if estimated else 0, r["id"]),
        )
        conn.commit()  # per-row commit — 예산 가드 커넥션 잠금 대기 최소화
        updated += 1
        print(f"[ok] id={r['id']} {minutes}분 ({mode})")
    conn.commit()
    conn.close()
    print(f"\nUpdated {updated}/{len(rows)} rows")


if __name__ == "__main__":
    main()
