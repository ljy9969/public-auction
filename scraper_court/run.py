"""법원경매 수집 CLI — dry-run 우선.

dry-run: DB write 없이 stdout으로 매물 dump (필터 통과 N건만).
실제 DB 통합은 P3 단계에서.

Usage:
    python -m scraper_court.run --dry-run --limit 5
    python -m scraper_court.run --dry-run --usg 토지
    python -m scraper_court.run --dry-run --max-price 50000000 --max-fail 5
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

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.filters.danger import apply_danger_filters
from scraper.filters.quality import apply_quality_filters
from scraper.filters.region import in_target_region
from scraper.session import load_criteria
from scraper_court.parse import parse_court_row
from scraper_court.search import iter_all_pages
from scraper_court.session import CourtSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="DB write 없이 stdout dump")
    parser.add_argument("--apply", action="store_true", help="DB에 upsert (기본은 dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="(dry-run) 필터 통과 N건만 출력; 0=무제한")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--sido", default="", help="시도명 (빈값=모든 시도 = 수도권 sweep)")
    parser.add_argument("--usg", default="", choices=["", "토지", "건물"], help="대분류")
    parser.add_argument("--max-price", type=int, default=None, help="최저매각가 상한 (원)")
    parser.add_argument("--max-fail", type=int, default=5)
    parser.add_argument("--bid-start", default="", help="YYYYMMDD")
    parser.add_argument("--bid-end", default="", help="YYYYMMDD")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True  # 기본 안전모드

    # 시도 → 코드 변환 (빈값이면 sweep)
    from scraper_court.codes import SIDO_CODES, USG_LCL
    if args.sido:
        sido_codes_to_use = [SIDO_CODES.get(args.sido, "")]
    else:
        # 수도권 sweep — 서울/경기/인천
        sido_codes_to_use = [SIDO_CODES["서울특별시"], SIDO_CODES["경기도"], SIDO_CODES["인천광역시"]]

    usg_lcl = ""
    if args.usg:
        rev = {v: k for k, v in USG_LCL.items()}
        usg_lcl = rev.get(args.usg, "")

    criteria = load_criteria()
    pf = criteria.get("post_filters", {})
    # criteria.yaml의 가격 cap 동일 적용
    if args.max_price is None:
        args.max_price = int(pf.get("max_min_price", 300_000_000))

    passed: list[dict] = []
    raw_count = 0
    filtered_out: dict[str, int] = {}

    def _bucket(prop: dict) -> str:
        notes = prop.get("filter_notes") or []
        return next((n.split("(")[0].strip() for n in notes
                     if "quality:" in n or "danger:" in n), "other")

    with CourtSession() as session:
        session.warm_up()
        for sido_cd in sido_codes_to_use:
            for row in iter_all_pages(
                session,
                sido_cd=sido_cd,
                usg_lcl=usg_lcl,
                max_price=args.max_price,
                max_fail_count=args.max_fail,
                bid_start_ymd=args.bid_start or None,
                bid_end_ymd=args.bid_end or None,
                max_pages=args.max_pages,
                page_size=args.page_size,
            ):
                raw_count += 1
                prop = parse_court_row(row)

                # 1) 지역 분기 — 공매·경매 공통 region.py 적용
                if not in_target_region(prop):
                    filtered_out["region: 수도권/쪈쪠 외"] = filtered_out.get("region: 수도권/쪈쪠 외", 0) + 1
                    continue

                # 2) quality + danger — universal price/유찰/카테고리/지하층 등
                prop = apply_quality_filters(prop)
                prop = apply_danger_filters(prop)
                if not prop.get("passes_filters", True):
                    filtered_out[_bucket(prop)] = filtered_out.get(_bucket(prop), 0) + 1
                    continue

                # 3) 권리분석 + 낙찰가 예측 (공매·경매 공통, prop dict 기반)
                from scraper.analyze_rights import analyze_rights
                from scraper.predict_price import predict_price
                try:
                    prop["rights_analysis"] = analyze_rights(prop)
                except Exception:
                    pass
                try:
                    pred = predict_price(prop)
                    if pred:
                        prop["predicted_price_low"] = pred["low"]
                        prop["predicted_price_median"] = pred["median"]
                        prop["predicted_price_high"] = pred["high"]
                        prop["predicted_price_basis"] = pred["basis"]
                except Exception:
                    pass

                passed.append(prop)
                if args.limit and len(passed) >= args.limit:
                    break
            if args.limit and len(passed) >= args.limit:
                break

    # DB upsert (--apply)
    saved = 0
    if args.apply:
        from scraper.db import upsert_property
        for p in passed:
            # 'raw_row'은 prop dict에만 두고 DB 컬럼엔 넣지 않음
            p_db = {k: v for k, v in p.items() if k != "raw_row"}
            try:
                upsert_property(p_db)
                saved += 1
            except Exception as e:
                logger.error("upsert failed for %s: %s", p.get("cltr_no"), e)

    # 출력
    print(f"\n=== 법원경매 {'apply' if args.apply else 'dry-run'} 결과 ===")
    print(f"raw 응답 수신: {raw_count}건")
    print(f"필터 통과: {len(passed)}건")
    if args.apply:
        print(f"DB 저장:   {saved}건")
    print(f"필터 거부:")
    for k, v in sorted(filtered_out.items(), key=lambda x: -x[1])[:10]:
        print(f"  {v}건 — {k}")
    print()
    for i, p in enumerate(passed, 1):
        print(f"--- 통과 #{i} ---")
        print(f"  source        : {p.get('source')}")
        print(f"  사건번호       : {p.get('court_case_no')} (물건 {p.get('court_item_seq')})")
        print(f"  법원           : {p.get('court_office_nm')}")
        print(f"  소재지(지번)   : {p.get('address_jibun')}")
        print(f"  소재지(도로명) : {p.get('address_road')}")
        print(f"  카테고리       : {p.get('category')}")
        print(f"  건물명         : {p.get('building_name')}")
        print(f"  면적(㎡)       : {p.get('area_build_m2')}")
        print(f"  감정가         : {p.get('appraisal_price'):,}원" if p.get('appraisal_price') else "  감정가         : -")
        print(f"  최저가         : {p.get('min_price'):,}원" if p.get('min_price') else "  최저가         : -")
        print(f"  유찰           : {p.get('fail_count')}회")
        print(f"  매각기일       : {p.get('bid_end')}")
        print(f"  좌표(WGS84)    : ({p.get('geo_lat')}, {p.get('geo_lng')})")
        print(f"  지분           : {p.get('share_yn')}")
        print(f"  url            : {p.get('source_url')}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
