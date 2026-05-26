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


def _matches_list_criteria(raw: dict, exclude_categories: tuple[str, ...] = ()) -> bool:
    """Onbid list-row checks before detail fetch."""
    if raw.get("dspsMthodCd") != "0001":
        return False
    if raw.get("cptnMthodCd") != "0001":
        return False
    price = raw.get("lowstBidPrc")
    if price is not None and float(price) > 300_000_000:
        return False
    cat = (raw.get("ctgrFullNm") or raw.get("ctgrNm") or "")
    is_land = any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지"))

    if not is_land:
        # 건물 매물에만 24㎡ 면적 하한 적용
        bld = raw.get("bldSqms") or 0
        if float(bld) > 0 and float(bld) < 24:
            return False
    # 토지 지분(예: 도로 부속토지)은 입문자 권장 매물이므로 제목의 "지분매각" 키워드 허용
    title = (raw.get("onbidCltrNm") or "")
    if not is_land and any(kw in title for kw in ("지분매각", "지분처분", "공유지분")):
        return False
    fail = raw.get("usbdCnt")
    if fail is not None and int(fail) > 2:
        return False
    if exclude_categories:
        if any(ex and ex in cat for ex in exclude_categories):
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
        exclude_cats = tuple(criteria.get("post_filters", {}).get("exclude_categories", []) or ())
        for query, raw in iter_all_queries(session, max_pages_per_query=pages_cap):
            if not in_target_region(raw):
                skipped += 1
                continue
            if not _matches_list_criteria(raw, exclude_cats):
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
