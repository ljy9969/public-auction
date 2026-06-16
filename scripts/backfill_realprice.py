"""기존 properties 행에 국토부 실거래가 시세 통계 백필.

각 매물의 카테고리에 맞는 데이터셋 (오피스텔/아파트/연립다세대/토지/단독다가구) 사용.
최근 6개월 윈도우. 같은 동/단지 + 면적 매칭으로 시세 산출.

Usage: .\.venv\Scripts\python.exe -m scripts.backfill_realprice
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 한국어 주소 출력이 cp949로 깨지면 Task Scheduler 셸이 NativeCommandError로 침묵 종료
# (2026-06-16 [3/5] 직후 daily-scrape.ps1 사망 사례). notify_*.py 패턴과 동일.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import get_connection
from scraper.filters.realprice import clear_trade_cache, estimate_market, estimate_rental


def main() -> None:
    # 거래 캐시 비우기 — long-running backend(지금 수집 반복)에서 전날 거래가
    # 모듈 캐시에 남아 stale 시세를 쓰는 것 방지. (캐시는 1회 백필 단위로만 유효)
    clear_trade_cache()
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, category, address_jibun, building_name, title, area_build_m2,
                  min_price, main_purps, use_apr_day, appraisal_price,
                  share_yn, building_share_ratio, land_share_ratio,
                  geo_lat, geo_lng
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
            "main_purps": r["main_purps"],
            "use_apr_day": r["use_apr_day"],
            "appraisal_price": r["appraisal_price"],
            "share_yn": r["share_yn"],
            "building_share_ratio": r["building_share_ratio"],
            "land_share_ratio": r["land_share_ratio"],
            "geo_lat": r["geo_lat"],
            "geo_lng": r["geo_lng"],
        }
        stats = estimate_market(prop, months=12)
        if not stats:
            # 새(엄격) 매칭에서 비교 거래 0건 → 옛 로직 시세가 남지 않도록 초기화.
            #   (miss인데 기존 값을 유지하면 stale 시세가 그대로 노출됨)
            conn.execute(
                "UPDATE properties SET market_median_price=NULL, market_min_price=NULL, "
                "market_max_price=NULL, market_sample_count=NULL, market_period_months=NULL, "
                "market_diff_percent=NULL, market_endpoint_label=NULL, market_match_kind=NULL, "
                "market_samples=NULL WHERE id=?",
                (r["id"],),
            )
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
