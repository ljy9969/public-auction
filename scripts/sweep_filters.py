"""기존 properties 행에 **가격·유찰·카테고리** 기준 필터만 재적용 (drift 방지, 경량).

원인 시나리오: 필터를 강화한 뒤(예: max_min_price 추가, 감정가 fallback) 새로
수집되는 매물은 차단되지만, 이전에 passes_filters=1로 들어간 행은 그대로 남음.

이 스크립트는 외부 API를 다시 호출하지 않고, 이미 DB에 있는 값만으로
quality.py의 가격·유찰·카테고리 화이트리스트를 재평가한다.

Usage:
    python -m scripts.sweep_filters             # dry-run, drift 행만 출력
    python -m scripts.sweep_filters --apply     # passes_filters=0으로 마킹 + filter_notes 갱신
    python -m scripts.sweep_filters --apply --delete   # 마킹 + DB에서 삭제
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import delete_failed_properties, get_connection
from scraper.filters.quality import apply_quality_filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _decode_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="DB에 변경 반영")
    parser.add_argument("--delete", action="store_true", help="--apply 이후 실패 행 삭제")
    args = parser.parse_args()

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, category, min_price, appraisal_price, area_build_m2, "
        "share_yn, building_shared, fail_count, status, bid_end, "
        "filter_notes, detail_json FROM properties WHERE passes_filters = 1"
    ).fetchall()
    logger.info("Re-evaluating %s rows (quality filters only)", len(rows))

    fail = 0
    for r in rows:
        prop = {
            "title": r["title"],
            "category": r["category"],
            "min_price": r["min_price"],
            "appraisal_price": r["appraisal_price"],
            "area_build_m2": r["area_build_m2"],
            "share_yn": r["share_yn"],
            "building_shared": bool(r["building_shared"]) if r["building_shared"] is not None else None,
            "fail_count": r["fail_count"],
            "status": r["status"],
            "bid_end": r["bid_end"],
            "filter_notes": _decode_json(r["filter_notes"]) or [],
            "detail_json": _decode_json(r["detail_json"]) or {},
            "passes_filters": True,
        }
        prop = apply_quality_filters(prop)
        if not prop.get("passes_filters", True):
            fail += 1
            notes = prop.get("filter_notes") or []
            logger.info(
                "FAIL id=%s min=%s appr=%s — %s",
                r["id"], r["min_price"], r["appraisal_price"],
                [n for n in notes if "quality:" in n],
            )
            if args.apply:
                conn.execute(
                    "UPDATE properties SET passes_filters=0, filter_notes=? WHERE id=?",
                    (json.dumps(notes, ensure_ascii=False), r["id"]),
                )

    if args.apply:
        conn.commit()
        logger.info("Marked %s rows as failed", fail)
    else:
        logger.info("DRY RUN: %s rows would be marked failed (use --apply)", fail)

    if args.delete and args.apply and fail:
        removed = delete_failed_properties()
        logger.info("Deleted %s failed rows", removed)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
