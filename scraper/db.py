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
    ("image_url", "TEXT"),
    ("image_urls", "TEXT"),  # JSON array
    ("atch_file_lst_no", "INTEGER"),
    # 면적정보 표의 '건물' 행 지분 여부 (True=건물지분, False=단독, None=상세 미파싱)
    ("building_shared", "INTEGER"),
    ("building_share_ratio", "REAL"),  # 건물 지분 비율 (0~1)
    ("land_share_ratio", "REAL"),      # 토지 지분 비율 (0~1) — court buldList의 "N분의 M" → M/N
    ("land_area_m2", "REAL"),          # 토지면적 (일괄매각 토지+건물일 때, 건물면적과 별도 보존)
    ("distance_sister_km", "REAL"),    # 서대문역까지 직선거리 (언니/쪠 영역 판정)
    # 국토부 실거래가 기반 시세 통계
    ("market_median_price", "INTEGER"),
    ("market_min_price", "INTEGER"),
    ("market_max_price", "INTEGER"),
    ("market_sample_count", "INTEGER"),
    ("market_period_months", "INTEGER"),
    ("market_diff_percent", "REAL"),
    ("market_endpoint_label", "TEXT"),
    ("market_match_kind", "TEXT"),
    ("market_samples", "TEXT"),  # JSON
    # 임대 수익률 (전월세 실거래)
    ("rental_monthly_avg", "INTEGER"),
    ("rental_deposit_avg", "INTEGER"),
    ("rental_sample_count", "INTEGER"),
    ("rental_yield_percent", "REAL"),
    ("rental_match_kind", "TEXT"),
    ("rental_endpoint_label", "TEXT"),
    ("rental_samples", "TEXT"),  # JSON
    # #9 권리분석 자동 판정 (휴리스틱) — analyze_rights.py
    ("rights_analysis", "TEXT"),  # JSON: {risk_level, summary, flags, ...}
    # #10 낙찰가 예측 휴리스틱 — predict_price.py
    ("predicted_price_low", "INTEGER"),
    ("predicted_price_median", "INTEGER"),
    ("predicted_price_high", "INTEGER"),
    ("predicted_price_basis", "TEXT"),
    # 재산유형 (예: 압류재산, 유입재산 등) — scrnPrptDvsnNm
    ("asset_type", "TEXT"),
    # 데이터 소스 — 'onbid'(공매, 기본) / 'court'(법원경매)
    ("source", "TEXT NOT NULL DEFAULT 'onbid'"),
    # 법원경매 전용 — onbid 매물은 NULL
    ("court_case_no", "TEXT"),       # '2024타경6292'
    ("court_office_cd", "TEXT"),     # 'B000210' (서울중앙지방법원)
    ("court_office_nm", "TEXT"),     # '서울중앙지방법원'
    ("court_item_seq", "INTEGER"),   # 사건 내 물건 순번 (maemulSer)
    # AI 예상 낙찰가 — 상세 페이지 'AI 예상가' 버튼 on-demand 호출 결과 캐시.
    # ai_estimate_json: {low, median, high, reasoning, confidence, ...} 직렬화.
    ("ai_estimate_json", "TEXT"),
    ("ai_provider", "TEXT"),         # 'claude' | 'gemini'
    ("ai_model", "TEXT"),            # 'claude-sonnet-4-6' 등
    ("ai_estimated_at", "TEXT"),     # ISO8601 (캐시 신선도 판단)
    # 사용자가 상세 페이지에서 직접 분류한 알림 블랙리스트(1=제외).
    # 지분 매물은 거의 항상 공유자 우선매수권이 있어 자동 룰로 컷할 수 없다 →
    # 사용자가 개별 물건 메리트를 판단해 알림에서만 빼는 수동 플래그(2026-06-07).
    ("alert_blacklist", "INTEGER NOT NULL DEFAULT 0"),
    # 블랙리스트 사유 — 사용자가 상세 페이지에서 입력(≤50자). 목록의
    # 'blacklist' 칩 hover 시 툴팁으로 노출 (2026-06-07).
    ("alert_blacklist_reason", "TEXT"),
    # 지번(번지) 경계 폴리곤 — VWorld 연속지적도(LP_PA_CBND_BUBUN)에서
    # geo_lat/lng 포인트로 조회한 GeoJSON geometry 캐시. 목록 hover·상세 지도에서
    # 마커와 함께 필지 영역을 강조 (2026-06-08). on-demand 1회 조회 후 영속.
    ("parcel_geojson", "TEXT"),       # JSON: {type, coordinates, pnu, jibun}
    ("parcel_fetched_at", "TEXT"),    # ISO8601 (조회 시각; 빈 결과도 기록해 재호출 방지)
    # 사용자가 상세 페이지에서 자유롭게 적는 메모 — 알림 블랙리스트(=알림에서 제외)와
    # 독립적으로, 임장 메모·체크 사항 등 자유로운 텍스트(≤500자, 2026-06-16).
    ("memo", "TEXT"),
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
    # 마이그레이션(ALTER)·쓰기가 다른 커넥션과 겹쳐도 'database is locked'로 즉시
    # 실패하지 않고 대기하도록. (스크랩/백필 중 새 컬럼 추가가 막히는 문제 방어)
    conn.execute("PRAGMA busy_timeout=10000")
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
        "land_area_m2": prop.get("land_area_m2"),
        "share_yn": prop.get("share_yn"),
        "building_shared": (
            1 if prop.get("building_shared") is True
            else 0 if prop.get("building_shared") is False
            else None
        ),
        "building_share_ratio": prop.get("building_share_ratio"),
        "land_share_ratio": prop.get("land_share_ratio"),
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
        "distance_sister_km": prop.get("distance_sister_km"),
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
        "image_url": prop.get("image_url"),
        "image_urls": (
            json.dumps(prop.get("image_urls"), ensure_ascii=False)
            if prop.get("image_urls") else None
        ),
        "atch_file_lst_no": prop.get("atch_file_lst_no"),
        "market_median_price": prop.get("market_median_price"),
        "market_min_price": prop.get("market_min_price"),
        "market_max_price": prop.get("market_max_price"),
        "market_sample_count": prop.get("market_sample_count"),
        "market_period_months": prop.get("market_period_months"),
        "market_diff_percent": prop.get("market_diff_percent"),
        "market_endpoint_label": prop.get("market_endpoint_label"),
        "market_match_kind": prop.get("market_match_kind"),
        "market_samples": (
            json.dumps(prop.get("market_samples"), ensure_ascii=False)
            if prop.get("market_samples") else None
        ),
        "rental_monthly_avg": prop.get("rental_monthly_avg"),
        "rental_deposit_avg": prop.get("rental_deposit_avg"),
        "rental_sample_count": prop.get("rental_sample_count"),
        "rental_yield_percent": prop.get("rental_yield_percent"),
        "rental_match_kind": prop.get("rental_match_kind"),
        "rental_endpoint_label": prop.get("rental_endpoint_label"),
        "rental_samples": (
            json.dumps(prop.get("rental_samples"), ensure_ascii=False)
            if prop.get("rental_samples") else None
        ),
        "rights_analysis": (
            json.dumps(prop.get("rights_analysis"), ensure_ascii=False)
            if prop.get("rights_analysis") else None
        ),
        "predicted_price_low": prop.get("predicted_price_low"),
        "predicted_price_median": prop.get("predicted_price_median"),
        "predicted_price_high": prop.get("predicted_price_high"),
        "predicted_price_basis": prop.get("predicted_price_basis"),
        "asset_type": prop.get("asset_type"),
        "source": prop.get("source") or "onbid",
        "court_case_no": prop.get("court_case_no"),
        "court_office_cd": prop.get("court_office_cd"),
        "court_office_nm": prop.get("court_office_nm"),
        "court_item_seq": prop.get("court_item_seq"),
    }
    # NOTE: ON CONFLICT(cltr_no, pbct_cdtn_no)에 의존하지 않는다.
    # 법원경매(court) 물건은 pbct_cdtn_no=NULL인데, SQLite UNIQUE 인덱스는
    # NULL을 서로 다른 값으로 취급해 충돌이 안 잡힌다 → 재스크랩마다 중복 INSERT.
    # cltr_no는 court·onbid 모두 물건당 고유하므로, IS(=NULL 안전) 조회로
    # 기존 행을 찾아 UPDATE, 없으면 INSERT 한다.
    existing = conn.execute(
        "SELECT id FROM properties WHERE cltr_no = ? AND pbct_cdtn_no IS ?",
        (prop["cltr_no"], prop.get("pbct_cdtn_no")),
    ).fetchone()
    if existing:
        # COALESCE 로 NULL 덮어쓰기 방지 — scrape 의 prop dict 는 image_url, geo_lat 등
        # 백필이 채우는 컬럼을 None 으로 갖고 있어, 매 scrape 마다 backfill 결과를 NULL 로
        # reset 하던 버그(2026-06-04 court 사진 0/81 사고)의 root fix.
        # 새 값이 NOT NULL 이면 그대로 덮어씀, NULL 이면 기존 값 유지.
        assigns = ", ".join(
            f"{k}=COALESCE(?, {k})" for k in fields if k not in ("cltr_no", "pbct_cdtn_no")
        )
        params = [v for k, v in fields.items() if k not in ("cltr_no", "pbct_cdtn_no")]
        params.append(int(existing["id"]))
        conn.execute(f"UPDATE properties SET {assigns} WHERE id = ?", params)
        new_id = int(existing["id"])
    else:
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        cur = conn.execute(
            f"INSERT INTO properties ({cols}) VALUES ({placeholders})",
            list(fields.values()),
        )
        new_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return new_id


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


def set_alert_blacklist(
    prop_id: int,
    value: bool,
    reason: str | None = None,
    db_path: Path | None = None,
) -> dict | None:
    """알림 블랙리스트 플래그 + 사유 토글. 매물이 없으면 None.

    - value=False 이면 사유도 함께 비움(NULL).
    - value=True 인데 reason 이 None 이면 기존 사유 보존(COALESCE 동작 X — 명시적
      None 이면 비움). 호출자가 사유 갱신 없이 토글만 하고 싶을 때를 위해 빈 문자열은
      비우는 것으로 통일.
    """
    conn = get_connection(db_path)
    if value:
        clean = (reason or "").strip()[:50] or None
        cur = conn.execute(
            "UPDATE properties SET alert_blacklist = 1, alert_blacklist_reason = ? "
            "WHERE id = ?",
            (clean, prop_id),
        )
    else:
        cur = conn.execute(
            "UPDATE properties SET alert_blacklist = 0, alert_blacklist_reason = NULL "
            "WHERE id = ?",
            (prop_id,),
        )
    conn.commit()
    changed = cur.rowcount
    if not changed:
        conn.close()
        return None
    row = conn.execute(
        "SELECT alert_blacklist, alert_blacklist_reason FROM properties WHERE id = ?",
        (prop_id,),
    ).fetchone()
    conn.close()
    return {
        "alert_blacklist": bool(row["alert_blacklist"]),
        "alert_blacklist_reason": row["alert_blacklist_reason"],
    }


def set_memo(
    prop_id: int,
    memo: str | None,
    db_path: Path | None = None,
) -> dict | None:
    """사용자 메모 갱신. 빈 문자열/공백/None 모두 NULL 로 통일. 매물이 없으면 None."""
    clean: str | None = (memo or "").strip()[:500] or None
    conn = get_connection(db_path)
    cur = conn.execute(
        "UPDATE properties SET memo = ? WHERE id = ?",
        (clean, prop_id),
    )
    conn.commit()
    changed = cur.rowcount
    if not changed:
        conn.close()
        return None
    row = conn.execute(
        "SELECT memo FROM properties WHERE id = ?",
        (prop_id,),
    ).fetchone()
    conn.close()
    return {"memo": row["memo"]}


def set_parcel(
    prop_id: int,
    geojson_str: str | None,
    fetched_at: str,
    db_path: Path | None = None,
) -> None:
    """지번 경계 폴리곤 GeoJSON 캐시 저장. geojson_str=None 이면 '조회했으나 결과
    없음'을 의미 — fetched_at 만 기록해 같은 매물을 매번 VWorld 에 재요청하지 않는다."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE properties SET parcel_geojson = ?, parcel_fetched_at = ? WHERE id = ?",
        (geojson_str, fetched_at, prop_id),
    )
    conn.commit()
    conn.close()


def count_properties(passes_only: bool = True, db_path: Path | None = None) -> int:
    conn = get_connection(db_path)
    where = "WHERE passes_filters = 1" if passes_only else ""
    n = conn.execute(f"SELECT COUNT(*) FROM properties {where}").fetchone()[0]
    conn.close()
    return int(n)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("detail_json", "rights_json", "schedule_json", "filter_notes", "market_samples", "rental_samples", "image_urls", "rights_analysis"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                pass
    d["passes_filters"] = bool(d.get("passes_filters"))
    d["transit_estimated"] = bool(d.get("transit_estimated"))
    return d
