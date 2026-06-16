"""입찰 시작/마감 D-day 임박 매물 요약을 Discord 웹훅으로 전송.

사용법:
    python -m scripts.notify_dday              # 기본 7일 이내
    python -m scripts.notify_dday --days 3     # 3일 이내만
    python -m scripts.notify_dday --dry-run    # 메시지 콘솔 출력만

DISCORD_WEBHOOK 미설정 시 dry-run으로 동작.
Task Scheduler에 매일 1회 등록해두면 D-day 푸시가 된다.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
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


def _dday_label(target: datetime, now: datetime) -> str:
    delta = (target.date() - now.date()).days
    if delta == 0:
        return "D-Day"
    if delta < 0:
        return f"D+{abs(delta)}"
    return f"D-{delta}"


def _format_won(n: int | None) -> str:
    if not n:
        return "-"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n / 10_000:.0f}만"
    return f"{n}원"


def _query_upcoming(days: int) -> tuple[list[dict], list[dict]]:
    now = datetime.now()
    horizon = (now + timedelta(days=days)).isoformat()
    today_iso = now.date().isoformat()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    starts = con.execute(
        """
        SELECT id, title, min_price, bid_start, fail_count
        FROM properties
        WHERE passes_filters = 1
          AND bid_start IS NOT NULL
          AND substr(bid_start, 1, 10) >= ?
          AND substr(bid_start, 1, 10) <= substr(?, 1, 10)
        ORDER BY bid_start
        """,
        (today_iso, horizon),
    ).fetchall()

    ends = con.execute(
        """
        SELECT id, title, min_price, bid_end, fail_count
        FROM properties
        WHERE passes_filters = 1
          AND bid_end IS NOT NULL
          AND substr(bid_end, 1, 10) >= ?
          AND substr(bid_end, 1, 10) <= substr(?, 1, 10)
        ORDER BY bid_end
        """,
        (today_iso, horizon),
    ).fetchall()
    con.close()
    return [dict(r) for r in starts], [dict(r) for r in ends]


def build_message(days: int) -> str | None:
    now = datetime.now()
    starts, ends = _query_upcoming(days)
    if not starts and not ends:
        return None

    # 이전 메시지(재수집 완료 요약)와 시각적으로 분리 — Discord가 leading whitespace를
    # 트림하므로 zero-width space(​)로 빈 줄을 강제한다.
    lines: list[str] = ["​", f"📅 **{days}일 이내 입찰 일정 D-day 알림** ({now:%Y-%m-%d %H:%M})"]

    def fmt(rows: list[dict], date_key: str) -> list[str]:
        out: list[str] = []
        for r in rows[:15]:
            try:
                dt = datetime.strptime(r[date_key][:16], "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                continue
            tag = _dday_label(dt, now)
            title = r["title"]
            if len(title) > 50:
                title = title[:48] + "…"
            out.append(
                f"  · `{tag}` {title} — 최저가 {_format_won(r['min_price'])} (유찰 {r['fail_count'] or 0}회)"
            )
        if len(rows) > 15:
            out.append(f"  · ...외 {len(rows) - 15}건")
        return out

    if ends:
        lines.append(f"\n🔴 **입찰 마감 임박 {len(ends)}건**")
        lines.extend(fmt(ends, "bid_end"))

    if starts:
        lines.append(f"\n🟢 **입찰 시작 {len(starts)}건**")
        lines.extend(fmt(starts, "bid_start"))

    return "\n".join(lines)


def _split_for_discord(text: str, limit: int = 1900) -> list[str]:
    """Discord content 2000자 제한 → 줄 경계로 안전 분할(여유 1900).

    한 줄이 자체로 limit 초과면 그 줄만 강제로 자른다. 헤더/항목 모두 보존.
    """
    chunks: list[str] = []
    cur = ""
    for ln in text.split("\n"):
        if len(ln) > limit:
            ln = ln[: limit - 1] + "…"
        if cur and len(cur) + 1 + len(ln) > limit:
            chunks.append(cur)
            cur = ln
        else:
            cur = ln if not cur else cur + "\n" + ln
    if cur:
        chunks.append(cur)
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    msg = build_message(args.days)
    if msg is None:
        print(f"D-day 알림 대상 없음 (이내 {args.days}일)")
        return 0

    if args.dry_run or not WEBHOOK:
        print(msg)
        if not WEBHOOK:
            print("\n[note] DISCORD_WEBHOOK 미설정 — 실제 전송 생략")
        return 0

    # Discord 2000자 초과 시 HTTP 400 → 청크 분할 전송(2026-06-10: 2010자 초과 사례).
    chunks = _split_for_discord(msg)
    for i, chunk in enumerate(chunks, 1):
        try:
            resp = httpx.post(WEBHOOK, json={"content": chunk}, timeout=20)
        except Exception as exc:
            print(f"Discord D-day 알림 실패({i}/{len(chunks)}): {exc!r}")
            return 1
        suffix = f" ({i}/{len(chunks)})" if len(chunks) > 1 else ""
        print(f"Discord D-day 알림 전송{suffix}: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            print(f"  응답: {resp.text[:300]}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
