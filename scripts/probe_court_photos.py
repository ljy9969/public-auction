"""court 매물 사진 백필 상태 + 정적 서빙 확인.

Usage:
    python -m scripts.probe_court_photos
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
PHOTO_DIR = ROOT / "data" / "court_photos"


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("=== 1) court 매물 사진 채움 비율 ===")
    r = conn.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN image_url IS NOT NULL AND image_url != '' THEN 1 ELSE 0 END) filled
           FROM properties WHERE source='court'"""
    ).fetchone()
    print(f"  court 총 {r['total']}건, 사진 채워짐 {r['filled']}건 ({100*r['filled']/r['total']:.1f}%)")

    print()
    print("=== 2) 한 매물 샘플 ===")
    s = conn.execute(
        """SELECT id, cltr_no, court_case_no, image_url, image_urls
           FROM properties WHERE source='court' AND image_url IS NOT NULL
           LIMIT 2"""
    ).fetchall()
    for row in s:
        print(f"  id={row['id']} cltr_no={row['cltr_no']}")
        print(f"    image_url={row['image_url']!r}")
        urls = row["image_urls"]
        if urls:
            print(f"    image_urls={urls[:200]}")

    print()
    print("=== 3) PHOTO_DIR 파일 수 ===")
    if not PHOTO_DIR.exists():
        print(f"  ★ {PHOTO_DIR} 디렉토리 자체가 없음")
    else:
        files = list(PHOTO_DIR.iterdir())
        print(f"  {PHOTO_DIR} 안 파일: {len(files)}개")
        if files:
            for f in files[:3]:
                print(f"    {f.name} ({f.stat().st_size} bytes)")

    print()
    print("=== 4) 사용자 캡처 매물 (2024타경74337) 상태 ===")
    rows4 = conn.execute(
        """SELECT id, cltr_no, image_url, image_urls
           FROM properties WHERE court_case_no='2024타경74337' ORDER BY id"""
    ).fetchall()
    for row in rows4:
        print(f"  id={row['id']} cltr_no={row['cltr_no']} image_url={row['image_url']!r}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
