"""ODsay 대중교통 API 일일 호출 예산 가드.

배경(2026-06-03): ODsay 일 1,000콜 한도를 초과해 'API 제공 중단' 통보를 받음.
유력 원인은 경매(court) 통합으로 신규 매물 수백 건이 한꺼번에 유입되며 그들의
첫 transit_minutes backfill이 한도를 넘긴 것. 캐시·카테고리 가드는 '이미 채워진'
매물엔 동작하지만 대량 신규 매물의 최초 1회 호출은 막지 못한다.

이 모듈은 properties와 같은 SQLite DB에 odsay_usage(date, calls) 테이블로
**KST 날짜별 호출 수를 누적**한다. 자정(KST)을 넘기면 새 날짜 행이 생겨 자동 리셋.
라이브 스크랩·backfill 등 여러 프로세스가 같은 카운터를 공유한다.

상한은 990(=1000 - 여유 10). 환경변수 ODSAY_DAILY_CAP 으로 조정 가능.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from scraper.db import get_connection

logger = logging.getLogger(__name__)

# 일 1,000 한도. 990에서 멈춰 경합·중복 호출 여유 ~10건 확보.
DAILY_CAP = int(os.environ.get("ODSAY_DAILY_CAP", "990"))
_KST = timezone(timedelta(hours=9))


def _today_kst() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d")


def _conn():
    conn = get_connection()
    # backfill 등 다른 커넥션과 잠깐 겹쳐도 에러 대신 대기하도록.
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS odsay_usage ("
        "date TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0)"
    )
    return conn


def calls_today() -> int:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT calls FROM odsay_usage WHERE date=?", (_today_kst(),)
        ).fetchone()
        return int(row["calls"]) if row else 0
    finally:
        conn.close()


def remaining() -> int:
    return max(0, DAILY_CAP - calls_today())


def try_consume(n: int = 1) -> bool:
    """오늘 예산에서 n콜 차감 시도.

    한도 내면 차감하고 True, 초과하면 차감하지 않고 False(=ODsay 호출 금지).
    DB 잠금 등 예외 시에는 쿼터 보호를 위해 보수적으로 False.
    """
    today = _today_kst()
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT calls FROM odsay_usage WHERE date=?", (today,)
        ).fetchone()
        used = int(row["calls"]) if row else 0
        if used + n > DAILY_CAP:
            return False
        conn.execute(
            "INSERT INTO odsay_usage(date, calls) VALUES(?, ?) "
            "ON CONFLICT(date) DO UPDATE SET calls = calls + ?",
            (today, n, n),
        )
        conn.commit()
        return True
    except Exception as exc:  # database is locked 등 — 쿼터 보호 우선
        logger.warning("odsay_budget.try_consume failed (%s) — ODsay 호출 보류", exc)
        return False
    finally:
        conn.close()
