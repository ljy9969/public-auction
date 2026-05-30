"""FastAPI backend for Onbid property browser."""
from __future__ import annotations

import asyncio
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.schemas.property import (
    PropertyDetail,
    PropertyListItem,
    ScrapeStatus,
    ScrapeTriggerResponse,
)
from api import stats as stats_module
from scraper import db as scraper_db
from scraper.run import run_scrape

app = FastAPI(title="Onbid Public Auction API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_scrape_lock = threading.Lock()
_scrape_state: dict[str, Any] = {
    "running": False,
    "last_run_id": None,
    "started_at": None,
    "finished_at": None,
    "message": None,
    "count": 0,
    "error": None,
}


def _run_scrape_job(max_pages: int | None) -> None:
    global _scrape_state
    try:
        count = run_scrape(max_pages=max_pages, fetch_details=True)
        _scrape_state["count"] = count
        _scrape_state["message"] = f"Saved {count} properties"
        _scrape_state["error"] = None
    except Exception as exc:
        _scrape_state["error"] = str(exc)
        _scrape_state["message"] = "Scrape failed"
    finally:
        _scrape_state["running"] = False
        _scrape_state["finished_at"] = datetime.now(timezone.utc)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/properties", response_model=list[PropertyListItem])
def list_properties(
    passes_only: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> list[PropertyListItem]:
    rows = scraper_db.list_properties(passes_only=passes_only, limit=limit, offset=offset)
    return [PropertyListItem(**_public_fields(r)) for r in rows]


@app.get("/api/properties/lookup")
def lookup_property(q: str) -> dict[str, Any]:
    """사건번호/물건관리번호로 매물 직조회 (#7).

    q: cltr_no (예 2026-04174-001) 또는 cltr_mnmt_no 부분 일치.
    매물 발견 시 {found: true, id: int} 반환, 미발견은 {found: false}.
    """
    needle = (q or "").strip()
    if not needle:
        raise HTTPException(status_code=400, detail="query empty")
    conn = scraper_db.get_connection()
    row = conn.execute(
        """
        SELECT id FROM properties
        WHERE cltr_no = ?
           OR cltr_mnmt_no = ?
           OR cltr_no LIKE ?
           OR cltr_mnmt_no LIKE ?
        ORDER BY (CASE WHEN cltr_no = ? OR cltr_mnmt_no = ? THEN 0 ELSE 1 END), scraped_at DESC
        LIMIT 1
        """,
        (needle, needle, f"%{needle}%", f"%{needle}%", needle, needle),
    ).fetchone()
    conn.close()
    if row is None:
        return {"found": False, "query": needle}
    return {"found": True, "id": int(row["id"]), "query": needle}


@app.get("/api/properties/{prop_id}", response_model=PropertyDetail)
def get_property(prop_id: int) -> PropertyDetail:
    row = scraper_db.get_property(prop_id)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    return PropertyDetail(**_public_fields(row))


@app.get("/api/stats/summary")
def stats_summary() -> dict[str, Any]:
    return stats_module.compute_stats()


@app.post("/api/scrape", response_model=ScrapeTriggerResponse)
def trigger_scrape(
    background_tasks: BackgroundTasks,
    max_pages: int | None = 3,
) -> ScrapeTriggerResponse:
    if _scrape_state["running"]:
        return ScrapeTriggerResponse(started=False, message="Scrape already running")

    if not _scrape_lock.acquire(blocking=False):
        return ScrapeTriggerResponse(started=False, message="Scrape already running")

    _scrape_state["running"] = True
    _scrape_state["started_at"] = datetime.now(timezone.utc)
    _scrape_state["finished_at"] = None
    _scrape_state["message"] = "Scrape started"
    _scrape_state["error"] = None
    _scrape_state["count"] = 0
    _scrape_lock.release()

    def task() -> None:
        _run_scrape_job(max_pages)

    background_tasks.add_task(task)
    return ScrapeTriggerResponse(started=True, message="Scrape started in background")


def _latest_db_run() -> dict[str, Any] | None:
    """In-memory state는 uvicorn 재시작 시 휘발 — DB의 search_runs에서 가장 최근 완료 행 조회."""
    try:
        conn = scraper_db.get_connection()
        row = conn.execute(
            "SELECT id, started_at, finished_at, count, error "
            "FROM search_runs WHERE finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


@app.get("/api/scrape/status", response_model=ScrapeStatus)
def scrape_status() -> ScrapeStatus:
    finished_at = _scrape_state.get("finished_at")
    started_at = _scrape_state.get("started_at")
    last_run_id = _scrape_state.get("last_run_id")
    count = _scrape_state.get("count", 0)
    error = _scrape_state.get("error")
    # In-memory 비어있고 진행 중도 아니면 DB 마지막 run으로 보강
    if not _scrape_state["running"] and finished_at is None:
        last = _latest_db_run()
        if last:
            finished_at = _parse_iso(last.get("finished_at"))
            started_at = _parse_iso(last.get("started_at"))
            last_run_id = last.get("id")
            count = last.get("count", 0) or 0
            error = last.get("error")
    return ScrapeStatus(
        running=_scrape_state["running"],
        last_run_id=last_run_id,
        started_at=started_at,
        finished_at=finished_at,
        message=_scrape_state.get("message"),
        count=count,
        error=error,
    )


def _public_fields(row: dict[str, Any]) -> dict[str, Any]:
    allowed = set(PropertyDetail.model_fields.keys())
    out = {k: v for k, v in row.items() if k in allowed}
    if isinstance(out.get("scraped_at"), str):
        try:
            out["scraped_at"] = datetime.fromisoformat(out["scraped_at"].replace("Z", "+00:00"))
        except ValueError:
            pass
    return out
