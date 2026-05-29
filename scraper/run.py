"""CLI entry: scrape Onbid listings, apply filters, save to SQLite."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running as python -m scraper.run from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.db import delete_failed_properties, finish_run, start_run, upsert_property
from scraper.detail import fetch_detail_html
from scraper.filters import apply_all_post_filters
from scraper.filters.region import in_target_region
from scraper.parse import parse_detail_html, parse_list_row
from scraper.search import iter_all_queries
from scraper.session import create_session, load_criteria

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _matches_list_criteria(
    raw: dict,
    exclude_categories: tuple[str, ...] = (),
    *,
    min_bld_area: float = 23.0,
    max_min_price: float = 300_000_000,
    max_fail_count: int | None = None,
    allowed_categories: tuple[str, ...] = (),
) -> bool:
    """Onbid list-row checks before detail fetch."""
    if raw.get("dspsMthodCd") != "0001":
        return False
    if raw.get("cptnMthodCd") != "0001":
        return False
    # 최저가 비공개(None/0)면 감정가로 판단 — 둘 다 비공개면 제외, 초고가(922억 대지)도 제외
    price = raw.get("lowstBidPrc")
    appr = raw.get("cltrApslEvlAvgAmt")
    effective_price = price if (price and float(price) > 0) else appr
    if effective_price is None or float(effective_price) > max_min_price:
        return False
    cat = (raw.get("ctgrFullNm") or raw.get("ctgrNm") or "")
    is_land = any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지"))

    # 면적 하한은 list 단계에서 적용하지 않음 — 지분 매물(면적 작음)을 놓치지 않기 위해
    # detail fetch 후 quality에서 '단독 건물'에만 23㎡ 적용 (지분/토지는 면제)
    _ = min_bld_area  # noqa: F841 (호출 호환 유지)
    if max_fail_count is not None:
        fail = raw.get("uscbdCnt") or raw.get("usbdCnt")
        if fail is not None and int(fail) > max_fail_count:
            return False
    if exclude_categories:
        if any(ex and ex in cat for ex in exclude_categories):
            return False
    if allowed_categories and not is_land:
        if not any(ac in cat for ac in allowed_categories):
            return False
    return True


def run_scrape(
    *,
    max_pages: int | None = None,
    fetch_details: bool = True,
    headless: bool = True,
) -> int:
    criteria = load_criteria()
    run_id = start_run(criteria)
    saved = 0
    skipped = 0
    error: str | None = None
    session = None

    try:
        removed = delete_failed_properties()
        if removed:
            logger.info("Removed %s previously failed rows from DB", removed)

        logger.info("Opening Onbid session (Playwright)...")
        session = create_session(headless=headless)

        pages_cap = max_pages if max_pages is not None else 3
        pf = criteria.get("post_filters", {})
        exclude_cats = tuple(pf.get("exclude_categories", []) or ())
        allowed_cats = tuple(pf.get("allowed_categories", []) or ())
        min_bld = float(pf.get("min_bld_area_m2", 23))
        max_min_price = float(pf.get("max_min_price", 300_000_000))
        # list 단계는 느슨하게 (지분 매물도 일단 통과) — 정확한 분기는 quality.py에서 처리
        max_fail_count = pf.get("max_fail_count")
        for query, raw in iter_all_queries(session, max_pages_per_query=pages_cap):
            if not in_target_region(raw):
                skipped += 1
                continue
            if not _matches_list_criteria(
                raw,
                exclude_cats,
                min_bld_area=min_bld,
                max_min_price=max_min_price,
                max_fail_count=max_fail_count,
                allowed_categories=allowed_cats,
            ):
                skipped += 1
                continue
            logger.debug("Match from query %s: %s", query, raw.get("onbidCltrno"))
            prop = parse_list_row(raw)
            raw_row = prop.pop("raw_list", raw)

            if fetch_details:
                try:
                    html = fetch_detail_html(session, raw_row)
                    if html:
                        detail = parse_detail_html(html)
                        prop.update({k: v for k, v in detail.items() if v is not None})
                except Exception as exc:
                    logger.debug("Detail fetch failed %s: %s", prop["cltr_no"], exc)

            prop = apply_all_post_filters(prop, raw=raw_row)
            if not prop.get("passes_filters", True):
                skipped += 1
                logger.debug(
                    "Skip (filters): %s — %s",
                    prop.get("cltr_no"),
                    prop.get("filter_notes"),
                )
                continue

            upsert_property(prop)
            saved += 1

        finish_run(run_id, saved, None)
        logger.info("Saved %s properties, skipped %s (run %s)", saved, skipped, run_id)
        return saved
    except Exception as exc:
        error = str(exc)
        finish_run(run_id, saved, error)
        logger.exception("Scrape failed: %s", exc)
        raise
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                logger.debug("Session close failed", exc_info=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Onbid condition search")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--no-details", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    run_scrape(
        max_pages=args.max_pages,
        fetch_details=not args.no_details,
        headless=not args.headed,
    )


if __name__ == "__main__":
    main()
