"""기획부동산 의심 매물 자동 블랙리스트 처리.

사용자 결정(2026-06-25):
  · 임계값 A: Rule A/B/C OR (planned_re_filter.judge 참고)
  · 수동 우선 C: alert_blacklist_reason 이 "[자동]" prefix 인 매물만 자동 관리
  · 백필 분리 B: scraper.run 과 별개로, daily-scrape의 한 단계로 호출

처리 로직:
  · 휴리스틱 양성 + (alert_blacklist=0 또는 reason이 [자동] prefix)
      → blacklist=1, reason="[자동] ..." 갱신
  · 휴리스틱 음성 + alert_blacklist=1 + reason이 [자동] prefix
      → blacklist=0 으로 해제 (자동이 한 것이니 자동이 거둠)
  · 수동(블랙리스트 1 + reason이 [자동] 아닌 텍스트, 또는 사용자가 의도 적은 사유)
      → 그대로 두고 건드리지 않음

court 매물만 대상 (공유자 데이터가 court 에만 있음).

Usage:
    python -m scripts.backfill_planned_re_suspect
    python -m scripts.backfill_planned_re_suspect --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper import db as scraper_db  # noqa: E402
from scraper.auto_blacklist import (  # noqa: E402
    is_auto_managed,
    judge_blacklist as judge,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 변경 없이 어떤 매물이 영향받는지 출력")
    args = parser.parse_args(argv)

    db_path = ROOT / "data" / "onbid.db"
    scraper_db.get_connection(db_path).close()  # migration trigger
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # 모든 매물 대상 — court(공유자 정보) + 전체(맹지/선하지/호텔 등 filter_notes 기반)
    rows = con.execute(
        """
        SELECT id, source, address_jibun, parties_json, co_owner_count,
               filter_notes, alert_blacklist, alert_blacklist_reason
        FROM properties
        WHERE passes_filters = 1
        """
    ).fetchall()
    con.close()

    if not rows:
        print("대상 0건")
        return 0

    print(f"대상 {len(rows)}건 평가 시작{' (dry-run)' if args.dry_run else ''}")
    new_marks = 0  # 새로 블랙리스트 마킹
    refreshed = 0  # 자동이 이미 마킹된 것 reason 갱신
    cleared = 0   # 자동이 해제 (조건 미달)
    skipped_manual = 0  # 수동 매물이라 건드리지 않음
    no_change = 0  # 변동 없음

    for r in rows:
        suspect, new_reason = judge(dict(r))
        current_bl = bool(r["alert_blacklist"])
        current_reason = r["alert_blacklist_reason"]
        auto = is_auto_managed(current_bl, current_reason)

        if not auto:
            skipped_manual += 1
            continue

        addr = (r["address_jibun"] or "")[:42]

        if suspect:
            if current_bl and current_reason == new_reason:
                no_change += 1
                continue
            action = "REFRESH" if current_bl else "MARK"
            print(f"  [{action:7s}] id={r['id']:4d} {addr:42s} → {new_reason}")
            if not args.dry_run:
                scraper_db.set_alert_blacklist(r["id"], True, new_reason)
            if current_bl:
                refreshed += 1
            else:
                new_marks += 1
        else:
            if current_bl:
                # 자동 매물이 더 이상 조건 미달 → 해제
                print(f"  [CLEAR  ] id={r['id']:4d} {addr:42s} ← 조건 미달")
                if not args.dry_run:
                    scraper_db.set_alert_blacklist(r["id"], False)
                cleared += 1
            else:
                no_change += 1

    print()
    print(f"완료: 신규 마킹 {new_marks} / reason 갱신 {refreshed} / "
          f"자동 해제 {cleared} / 수동 보존 {skipped_manual} / 변동 없음 {no_change}")
    if args.dry_run:
        print("(dry-run — DB 변경 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
