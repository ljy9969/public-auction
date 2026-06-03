"""법원경매 매물 대표사진 백필.

법원경매(courtauction.go.kr)는 매물 사진을 상세 응답(selectAuctnCsSrchRslt.on)의
csPicLst[].picFile 에 base64(JPEG)로만 내려준다. 공개 이미지 URL은 없다
(NAS 내부 경로 /nas_e_image_pgj/… 는 404).
→ 우리가 base64를 받아 data/court_photos/ 에 파일로 저장하고, API가 /api/court-photos/
   로 서빙한다. 프론트 PhotoGallery는 image_url/image_urls를 그대로 <img src>에 렌더.

공매(온비드)는 dnldImgFile.do 직링크라 백필이 불필요 — 이 스크립트는 source='court'만 대상.

Usage:
    python -m scripts.backfill_court_photos              # image_url 없는 court 매물만
    python -m scripts.backfill_court_photos --force      # 전체 재다운로드
    python -m scripts.backfill_court_photos --limit 20
"""
from __future__ import annotations

import argparse
import base64
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.db import get_connection
from scraper_court.detail import extract_photos, fetch_detail
from scraper_court.session import CourtSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PHOTO_DIR = ROOT / "data" / "court_photos"
URL_PREFIX = "/api/court-photos"
MAX_PHOTOS = 5


def _dspsl_gds_seq(cltr_no: str | None, court_item_seq: int | None) -> str:
    """cltr_no = '2023타경6292-1' → 끝 '-N'이 물건순번(dspslGdsSeq). 폴백 court_item_seq→1."""
    if cltr_no and "-" in cltr_no:
        tail = cltr_no.rsplit("-", 1)[-1]
        if tail.isdigit():
            return tail
    if court_item_seq:
        return str(court_item_seq)
    return "1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="image_url 있어도 재다운로드")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 상한 (0=무제한)")
    args = parser.parse_args(argv)

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    where = "source = 'court' AND court_case_no IS NOT NULL AND court_office_cd IS NOT NULL"
    if not args.force:
        where += " AND (image_url IS NULL OR image_url = '')"
    rows = conn.execute(
        f"SELECT id, cltr_no, court_case_no, court_office_cd, court_item_seq "
        f"FROM properties WHERE {where} ORDER BY scraped_at DESC"
    ).fetchall()
    conn.close()

    if args.limit:
        rows = rows[: args.limit]

    logger.info("대상 court 매물: %d건", len(rows))
    if not rows:
        return 0

    updated = 0
    with CourtSession() as session:
        session.warm_up()
        for r in rows:
            pid = int(r["id"])
            cs_no = r["court_case_no"]
            cort = r["court_office_cd"]
            seq = _dspsl_gds_seq(r["cltr_no"], r["court_item_seq"])
            try:
                dma = fetch_detail(session, cs_no=cs_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)
                photos = extract_photos(dma, max_count=MAX_PHOTOS)
            except Exception as e:
                logger.warning("상세 조회 실패 id=%s (%s): %s", pid, cs_no, e)
                continue

            if not photos:
                logger.info("사진 없음 id=%s (%s)", pid, cs_no)
                continue

            urls: list[str] = []
            for ph in photos:
                fname = ph["title"]
                try:
                    raw = base64.b64decode(ph["b64"])
                except Exception:
                    continue
                if raw[:3] != b"\xff\xd8\xff":  # JPEG magic 검증
                    continue
                (PHOTO_DIR / fname).write_bytes(raw)
                urls.append(f"{URL_PREFIX}/{fname}")

            if not urls:
                logger.info("유효 JPEG 없음 id=%s (%s)", pid, cs_no)
                continue

            import json as _json
            conn = get_connection()
            conn.execute(
                "UPDATE properties SET image_url=?, image_urls=? WHERE id=?",
                (urls[0], _json.dumps(urls, ensure_ascii=False), pid),
            )
            conn.commit()
            conn.close()
            updated += 1
            logger.info("저장 id=%s (%s): 사진 %d장", pid, cs_no, len(urls))

    print(f"\n=== 법원경매 사진 백필 완료 ===")
    print(f"대상 {len(rows)}건 중 {updated}건 사진 저장 → {PHOTO_DIR}")
    return updated


if __name__ == "__main__":
    main()
    sys.exit(0)
