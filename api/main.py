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


@app.get("/api/properties/{prop_id}", response_model=PropertyDetail)
def get_property(prop_id: int) -> PropertyDetail:
    row = scraper_db.get_property(prop_id)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    return PropertyDetail(**_public_fields(row))


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


@app.get("/api/scrape/status", response_model=ScrapeStatus)
def scrape_status() -> ScrapeStatus:
    return ScrapeStatus(
        running=_scrape_state["running"],
        last_run_id=_scrape_state.get("last_run_id"),
        started_at=_scrape_state.get("started_at"),
        finished_at=_scrape_state.get("finished_at"),
        message=_scrape_state.get("message"),
        count=_scrape_state.get("count", 0),
        error=_scrape_state.get("error"),
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
