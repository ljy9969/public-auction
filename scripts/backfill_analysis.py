"""기존 properties 행에 권리분석(#9) + 낙찰가 예측(#10)을 백필.

신규 수집 매물은 scraper/run.py에서 이미 채워지지만, 과거 행은
이 스크립트로 일괄 갱신한다.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.analyze_rights import analyze_rights
from scraper.db import get_connection
from scraper.predict_price import predict_price

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _decode_json(raw: str | None) -> object:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def main() -> int:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, category, detail_json, rights_json, share_yn, "
        "building_shared, appraisal_price, min_price, fail_count, "
        "market_median_price, market_sample_count, market_min_price, market_max_price "
        "FROM properties WHERE passes_filters = 1"
    ).fetchall()

    n_rights, n_price = 0, 0
    for r in rows:
        prop = {
            "title": r["title"],
            "category": r["category"],
            "detail_json": _decode_json(r["detail_json"]),
            "rights_json": _decode_json(r["rights_json"]),
            "share_yn": r["share_yn"],
            "building_shared": bool(r["building_shared"]) if r["building_shared"] is not None else None,
            "appraisal_price": r["appraisal_price"],
            "min_price": r["min_price"],
            "fail_count": r["fail_count"],
            "market_median_price": r["market_median_price"],
            "market_sample_count": r["market_sample_count"],
            "market_min_price": r["market_min_price"],
            "market_max_price": r["market_max_price"],
        }

        # #9 권리분석
        try:
            analysis = analyze_rights(prop)
            conn.execute(
                "UPDATE properties SET rights_analysis = ? WHERE id = ?",
                (json.dumps(analysis, ensure_ascii=False), r["id"]),
            )
            n_rights += 1
        except Exception as exc:
            logger.debug("rights analysis failed for %s: %s", r["id"], exc)

        # #10 낙찰가 예측
        try:
            pred = predict_price(prop)
            if pred:
                conn.execute(
                    "UPDATE properties SET predicted_price_low = ?, "
                    "predicted_price_median = ?, predicted_price_high = ?, "
                    "predicted_price_basis = ? WHERE id = ?",
                    (pred["low"], pred["median"], pred["high"], pred["basis"], r["id"]),
                )
                n_price += 1
        except Exception as exc:
            logger.debug("price prediction failed for %s: %s", r["id"], exc)

    conn.commit()
    conn.close()
    logger.info("backfilled rights_analysis=%s, predicted_price=%s", n_rights, n_price)
    return 0


if __name__ == "__main__":
    sys.exit(main())
