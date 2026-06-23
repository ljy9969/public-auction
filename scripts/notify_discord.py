"""수집/백필 시작·완료 Discord 웹훅 알림.

사용법:
    python -m scripts.notify_discord --start                 # 수집 시작 알림
    python -m scripts.notify_discord "21분 13초"            # 완료 + 소요 시간
    python -m scripts.notify_discord                         # 완료 (소요 시간 미표시)
DISCORD_WEBHOOK 미설정 시 조용히 종료.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()
DB_PATH = ROOT / os.environ.get("ONBID_DB_PATH", "data/onbid.db")


def _start_message() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"🚀 **BidScope 경공매 통합 재수집 시작** ({now})\n"
        "5단계 (수집·건축물대장/Kakao/ODsay·시세·권리분석/낙찰가·sweep) "
        "진행 중 — 완료 시 결과 요약 알림"
    )


def _summary(duration: str | None) -> str:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    total = cur.execute("SELECT COUNT(*) FROM properties WHERE passes_filters=1").fetchone()[0]
    # source 컬럼이 없는 구버전 DB에선 0으로 처리
    try:
        src_rows = cur.execute(
            "SELECT source, COUNT(*) FROM properties WHERE passes_filters=1 GROUP BY source"
        ).fetchall()
        src_map = {s or "onbid": n for s, n in src_rows}
    except sqlite3.OperationalError:
        src_map = {"onbid": total}
    onbid = src_map.get("onbid", 0)
    court = src_map.get("court", 0)
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
    lines = ["✅ **BidScope 경공매 통합 재수집 완료**"]
    if duration:
        lines.append(f"⏱️ 소요 시간: **{duration}**")
    lines.append(f"📊 매물 **{total}건** (공매 {onbid} · 경매 {court}) · 시세 **{mkt}** · 임대수익률 **{rent}**")
    lines.append(cat_lines)
    return "\n".join(lines)


def main() -> None:
    if not WEBHOOK:
        print("DISCORD_WEBHOOK 미설정 — 알림 건너뜀")
        return
    args = sys.argv[1:]
    if args and args[0] == "--start":
        content = _start_message()
        label = "시작"
    else:
        duration = args[0] if args else None
        content = _summary(duration)
        label = "완료"
    try:
        resp = httpx.post(WEBHOOK, json={"content": content}, timeout=20)
        print(f"Discord {label} 알림 전송: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"Discord {label} 알림 실패: {exc!r}")


if __name__ == "__main__":
    main()
