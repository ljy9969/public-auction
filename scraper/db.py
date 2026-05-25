"""SQLite persistence for properties and scrape runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "onbid.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criteria_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    count INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cltr_no TEXT NOT NULL,
    pbct_no TEXT,
    pbct_cdtn_no TEXT,
    title TEXT NOT NULL,
    address_jibun TEXT,
    address_road TEXT,
    category TEXT,
    bid_method TEXT,
    min_price INTEGER,
    appraisal_price INTEGER,
    area_build_m2 REAL,
    share_yn TEXT,
    fail_count INTEGER,
    bid_start TEXT,
    bid_end TEXT,
    status TEXT,
    detail_json TEXT,
    rights_json TEXT,
    schedule_json TEXT,
    transit_minutes INTEGER,
    transit_estimated INTEGER DEFAULT 0,
    distance_seolleung_km REAL,
    geo_lat REAL,
    geo_lng REAL,
    source_url TEXT,
    scraped_at TEXT,
    passes_filters INTEGER DEFAULT 1,
    filter_notes TEXT,
    fee_rate TEXT,
    region_line TEXT,
    UNIQUE(cltr_no, pbct_cdtn_no)
);

CREATE INDEX IF NOT EXISTS idx_properties_cltr ON properties(cltr_no);
CREATE INDEX IF NOT EXISTS idx_properties_pass ON properties(passes_filters);
"""

# 새로 추가된 컬럼들 — 기존 DB에는 ALTER TABLE로 idempotent 마이그레이션
_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("floor_total", "INTEGER"),
    ("building_name", "TEXT"),
    ("use_apr_day", "TEXT"),
    ("main_purps", "TEXT"),
    ("transit_mode", "TEXT"),
    ("cltr_mnmt_no", "TEXT"),
    ("transit_summary", "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(properties)").fetchall()}
    for col, kind in _EXTRA_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE properties ADD COLUMN {col} {kind}")
    conn.commit()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def start_run(criteria: dict[str, Any], db_path: Path | None = None) -> int:
    conn = get_connection(db_path)
    cur = conn.execute(
        "INSERT INTO search_runs (criteria_json, started_at) VALUES (?, ?)",
        (json.dumps(criteria, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return int(run_id)


def delete_failed_properties(db_path: Path | None = None) -> int:
    """Remove rows that did not pass filters (stale wrong-region data)."""
    conn = get_connection(db_path)
    cur = conn.execute("DELETE FROM properties WHERE passes_filters = 0")
    conn.commit()
    n = cur.rowcount
    conn.close()
    return int(n)


def finish_run(run_id: int, count: int, error: str | None = None, db_path: Path | None = None) -> None:
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE search_runs SET finished_at = ?, count = ?, error = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), count, error, run_id),
    )
    conn.commit()
    conn.close()


def upsert_property(prop: dict[str, Any], db_path: Path | None = None) -> int:
    conn = get_connection(db_path)
    fields = {
        "cltr_no": prop["cltr_no"],
        "pbct_no": prop.get("pbct_no"),
        "pbct_cdtn_no": prop.get("pbct_cdtn_no"),
        "title": prop["title"],
        "address_jibun": prop.get("address_jibun"),
        "address_road": prop.get("address_road"),
        "category": prop.get("category"),
        "bid_method": prop.get("bid_method"),
        "min_price": prop.get("min_price"),
        "appraisal_price": prop.get("appraisal_price"),
        "area_build_m2": prop.get("area_build_m2"),
        "share_yn": prop.get("share_yn"),
        "fail_count": prop.get("fail_count"),
        "bid_start": prop.get("bid_start"),
        "bid_end": prop.get("bid_end"),
        "status": prop.get("status"),
        "detail_json": json.dumps(prop.get("detail_json"), ensure_ascii=False) if prop.get("detail_json") else None,
        "rights_json": json.dumps(prop.get("rights_json"), ensure_ascii=False) if prop.get("rights_json") else None,
        "schedule_json": json.dumps(prop.get("schedule_json"), ensure_ascii=False) if prop.get("schedule_json") else None,
        "transit_minutes": prop.get("transit_minutes"),
        "transit_estimated": 1 if prop.get("transit_estimated") else 0,
        "distance_seolleung_km": prop.get("distance_seolleung_km"),
        "geo_lat": prop.get("geo_lat"),
        "geo_lng": prop.get("geo_lng"),
        "source_url": prop.get("source_url"),
        "scraped_at": prop.get("scraped_at"),
        "passes_filters": 1 if prop.get("passes_filters", True) else 0,
        "filter_notes": json.dumps(prop.get("filter_notes", []), ensure_ascii=False),
        "fee_rate": prop.get("fee_rate"),
        "region_line": prop.get("region_line"),
        "floor_total": prop.get("floor_total"),
        "building_name": prop.get("building_name"),
        "use_apr_day": prop.get("use_apr_day"),
        "main_purps": prop.get("main_purps"),
        "transit_mode": prop.get("transit_mode"),
        "cltr_mnmt_no": prop.get("cltr_mnmt_no"),
        "transit_summary": prop.get("transit_summary"),
    }
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields if k not in ("cltr_no", "pbct_cdtn_no"))
    sql = f"""
        INSERT INTO properties ({cols}) VALUES ({placeholders})
        ON CONFLICT(cltr_no, pbct_cdtn_no) DO UPDATE SET {updates}
    """
    conn.execute(sql, list(fields.values()))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM properties WHERE cltr_no = ? AND pbct_cdtn_no IS ?",
        (prop["cltr_no"], prop.get("pbct_cdtn_no")),
    ).fetchone()
    conn.close()
    return int(row["id"]) if row else 0


def list_properties(
    *,
    passes_only: bool = True,
    limit: int = 200,
    offset: int = 0,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    where = "WHERE passes_filters = 1" if passes_only else ""
    rows = conn.execute(
        f"SELECT * FROM properties {where} ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_property(prop_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM properties WHERE id = ?", (prop_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def count_properties(passes_only: bool = True, db_path: Path | None = None) -> int:
    conn = get_connection(db_path)
    where = "WHERE passes_filters = 1" if passes_only else ""
    n = conn.execute(f"SELECT COUNT(*) FROM properties {where}").fetchone()[0]
    conn.close()
    return int(n)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("detail_json", "rights_json", "schedule_json", "filter_notes"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                pass
    d["passes_filters"] = bool(d.get("passes_filters"))
    d["transit_estimated"] = bool(d.get("transit_estimated"))
    return d
