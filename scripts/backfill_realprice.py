"""기존 properties 행에 국토부 실거래가 시세 통계 백필.

각 매물의 카테고리에 맞는 데이터셋 (오피스텔/아파트/연립다세대/토지/단독다가구) 사용.
최근 6개월 윈도우. 같은 동/단지 + 면적 매칭으로 시세 산출.

Usage: .\.venv\Scripts\python.exe -m scripts.backfill_realprice
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection
from scraper.filters.realprice import estimate_market, estimate_rental


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, category, address_jibun, building_name, title, area_build_m2, min_price
           FROM properties WHERE passes_filters = 1"""
    ).fetchall()
    updated = 0
    for r in rows:
        prop = {
            "category": r["category"],
            "address_jibun": r["address_jibun"],
            "building_name": r["building_name"],
            "title": r["title"],
            "area_build_m2": r["area_build_m2"],
            "min_price": r["min_price"],
        }
        stats = estimate_market(prop, months=12)
        if not stats:
            print(f"[miss] id={r['id']} {r['title'][:40]}")
            continue
        conn.execute(
            """UPDATE properties SET
                market_median_price = ?,
                market_min_price = ?,
                market_max_price = ?,
                market_sample_count = ?,
                market_period_months = ?,
                market_diff_percent = ?,
                market_endpoint_label = ?,
                market_match_kind = ?,
                market_samples = ?
               WHERE id = ?""",
            (
                stats["market_median_price"],
                stats["market_min_price"],
                stats["market_max_price"],
                stats["market_sample_count"],
                stats["market_period_months"],
                stats["market_diff_percent"],
                stats["market_endpoint_label"],
                stats["market_match_kind"],
                json.dumps(stats["market_samples"], ensure_ascii=False),
                r["id"],
            ),
        )
        # 임대 수익률 — 오피스텔만 활성. 다른 카테고리는 None 반환
        rent = estimate_rental(prop, months=12)
        if rent:
            conn.execute(
                """UPDATE properties SET
                    rental_monthly_avg = ?,
                    rental_deposit_avg = ?,
                    rental_sample_count = ?,
                    rental_yield_percent = ?,
                    rental_match_kind = ?,
                    rental_endpoint_label = ?,
                    rental_samples = ?
                   WHERE id = ?""",
                (
                    rent["rental_monthly_avg"],
                    rent["rental_deposit_avg"],
                    rent["rental_sample_count"],
                    rent["rental_yield_percent"],
                    rent["rental_match_kind"],
                    rent["rental_endpoint_label"],
                    json.dumps(rent["rental_samples"], ensure_ascii=False),
                    r["id"],
                ),
            )
        updated += 1
        diff = stats["market_diff_percent"]
        diff_str = f"{diff:+.1f}%" if diff is not None else "-"
        rent_str = (
            f" rental_yield={rent['rental_yield_percent']:.2f}% ({rent['rental_sample_count']}건)"
            if rent
            else ""
        )
        print(
            f"[ok] id={r['id']} median={stats['market_median_price']:,}원 "
            f"({stats['market_sample_count']}건, {stats['market_match_kind']}) "
            f"diff={diff_str}{rent_str}"
        )
    conn.commit()
    conn.close()
    print(f"\nUpdated {updated}/{len(rows)} rows")


if __name__ == "__main__":
    main()
