"""수집/백필 완료 후 Discord 웹훅으로 결과 요약 전송.

사용법:
    python -m scripts.notify_discord "21분 13초"   # 소요 시간 인자(선택)
DISCORD_WEBHOOK 미설정 시 조용히 종료.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()
DB_PATH = ROOT / os.environ.get("ONBID_DB_PATH", "data/onbid.db")


def _summary(duration: str | None) -> str:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    total = cur.execute("SELECT COUNT(*) FROM properties WHERE passes_filters=1").fetchone()[0]
    mkt = cur.execute(
        "SELECT COUNT(*) FROM properties WHERE passes_filters=1 AND market_median_price IS NOT NULL"
    ).fetchone()[0]
    rent = cur.execute(
        "SELECT COUNT(*) FROM properties WHERE passes_filters=1 AND rental_yield_percent IS NOT NULL"
    ).fetchone()[0]
    rows = cur.execute(
        "SELECT category, COUNT(*) FROM properties WHERE passes_filters=1 GROUP BY category ORDER BY 2 DESC"
    ).fetchall()
    con.close()

    cat_lines = "\n".join(f"  · {c}: {n}" for c, n in rows)
    lines = ["✅ **온비드 공매 통합 재수집 완료**"]
    if duration:
        lines.append(f"⏱️ 소요 시간: **{duration}**")
    lines.append(f"📊 매물 **{total}건** · 시세 **{mkt}** · 임대수익률 **{rent}**")
    lines.append(cat_lines)
    return "\n".join(lines)


def main() -> None:
    if not WEBHOOK:
        print("DISCORD_WEBHOOK 미설정 — 알림 건너뜀")
        return
    duration = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        resp = httpx.post(WEBHOOK, json={"content": _summary(duration)}, timeout=20)
        print(f"Discord 알림 전송: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"Discord 알림 실패: {exc!r}")


if __name__ == "__main__":
    main()
