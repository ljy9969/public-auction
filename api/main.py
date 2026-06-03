"""FastAPI backend for Onbid property browser."""
from __future__ import annotations

import asyncio
import logging
import sys
import threading

logger = logging.getLogger(__name__)
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

# 법원경매 매물 사진 — courtauction은 공개 이미지 URL이 없어 base64를 받아
# data/court_photos/ 에 저장(scripts.backfill_court_photos)하고 여기서 정적 서빙한다.
# data 디렉터리는 docker-compose에서 컨테이너에 마운트됨(./data → /app/data).
_COURT_PHOTO_DIR = ROOT / "data" / "court_photos"
_COURT_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/api/court-photos",
    StaticFiles(directory=str(_COURT_PHOTO_DIR)),
    name="court-photos",
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
    """웹 '지금 수집' 풀파이프 — daily-scrape.ps1과 동일 단계.

    1. scraper.run + scraper_court.run   매물 수집 (공매 + 경매)
    2. backfill_all           Kakao 좌표 + 건축물대장 + ODsay 대중교통
    3. backfill_realprice     국토부 실거래가 5종(시세) + 임대 수익률
    4. backfill_analysis      권리분석 + 낙찰가 예측 (스크레이프 시점에 이미 채워지지만 멱등)
    5. sweep_filters          강화된 필터에 안 맞는 잔존 행 자동 마킹·삭제

    백필 3종은 source 무관하게 passes_filters=1 전체를 처리하므로 공매·경매 모두 커버.
    """
    global _scrape_state
    try:
        # 1) 공매(온비드)
        _scrape_state["message"] = "[1/6] 매물 수집 (공매)"
        count = run_scrape(max_pages=max_pages, fetch_details=True)

        # 1) 경매(법원경매) — daily-scrape.ps1과 동일하게 --apply, 수도권 sweep
        _scrape_state["message"] = "[1/6] 매물 수집 (경매)"
        from scraper_court.run import main as _court_scrape
        court_count = _court_scrape(["--apply", "--max-pages", str(max_pages or 10)])

        count = (count or 0) + (court_count or 0)
        _scrape_state["count"] = count

        # 경매 대표사진 백필 — courtauction은 공개 이미지 URL이 없어 base64를 받아 저장.
        # 공매는 직링크라 불필요. 실패해도 파이프라인 전체를 막지 않도록 격리.
        _scrape_state["message"] = "[2/6] 백필 (경매 대표사진)"
        try:
            from scripts.backfill_court_photos import main as _backfill_court_photos
            _backfill_court_photos([])
        except Exception:
            logger.exception("court photo backfill failed (계속 진행)")

        _scrape_state["message"] = "[3/6] 백필 (건축물대장 + Kakao + ODsay)"
        from scripts.backfill_all import main as _backfill_all
        _backfill_all()

        _scrape_state["message"] = "[4/6] 백필 (국토부 실거래가 시세)"
        from scripts.backfill_realprice import main as _backfill_realprice
        _backfill_realprice()

        _scrape_state["message"] = "[5/6] 백필 (권리분석 + 낙찰가 예측)"
        from scripts.backfill_analysis import main as _backfill_analysis
        _backfill_analysis()

        _scrape_state["message"] = "[6/6] Sweep (drift 정리)"
        # daily-scrape.ps1과 동일한 sweep 사용 — region + quality 재평가 후 drift 행 삭제.
        # (이전엔 quality만 재적용하는 인라인 버전이라 region drift를 못 잡았음)
        from scripts.sweep_filters import main as _sweep
        sweep_fail = _sweep(["--apply", "--delete"]) or 0

        _scrape_state["message"] = f"완료 — 저장 {count}건, drift 정리 {sweep_fail}건"
        _scrape_state["error"] = None
    except Exception as exc:
        _scrape_state["error"] = str(exc)
        _scrape_state["message"] = f"실패: {exc}"
        logger.exception("scrape pipeline failed")
    finally:
        _scrape_state["running"] = False
        _scrape_state["finished_at"] = datetime.now(timezone.utc)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/properties", response_model=list[PropertyListItem])
def list_properties(
    passes_only: bool = True,
    limit: int = 5000,  # 공·경매 통합 후 수백 건 → 잘림 방지
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
    # 진행 중일 때만 in-memory가 진실(라이브 진행 상황).
    # 아니면 DB(search_runs)가 진실 — daily-scrape.ps1 같은 별도 프로세스 수집도 반영.
    if _scrape_state["running"]:
        return ScrapeStatus(
            running=True,
            last_run_id=_scrape_state.get("last_run_id"),
            started_at=_scrape_state.get("started_at"),
            finished_at=_scrape_state.get("finished_at"),
            message=_scrape_state.get("message"),
            count=_scrape_state.get("count", 0),
            error=_scrape_state.get("error"),
        )
    last = _latest_db_run()
    if last:
        return ScrapeStatus(
            running=False,
            last_run_id=last.get("id"),
            started_at=_parse_iso(last.get("started_at")),
            finished_at=_parse_iso(last.get("finished_at")),
            message=_scrape_state.get("message"),
            count=last.get("count", 0) or 0,
            error=last.get("error"),
        )
    return ScrapeStatus(
        running=False,
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
