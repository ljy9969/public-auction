"""Shared property models for scraper and API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PropertyBase(BaseModel):
    cltr_no: str
    pbct_no: str | None = None
    pbct_cdtn_no: str | None = None
    onbid_pbanc_no: str | None = None
    title: str
    address_jibun: str | None = None
    address_road: str | None = None
    category: str | None = None
    bid_method: str | None = None
    min_price: int | None = None
    appraisal_price: int | None = None
    area_build_m2: float | None = None
    share_yn: str | None = None
    building_shared: bool | None = None
    building_share_ratio: float | None = None
    fail_count: int | None = None
    bid_start: str | None = None
    bid_end: str | None = None
    status: str | None = None
    transit_minutes: int | None = None
    transit_estimated: bool = False
    distance_seolleung_km: float | None = None
    distance_sister_km: float | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None
    source_url: str | None = None
    scraped_at: datetime | None = None
    passes_filters: bool = True
    filter_notes: list[str] = Field(default_factory=list)
    floor_total: int | None = None
    building_name: str | None = None
    use_apr_day: str | None = None
    main_purps: str | None = None
    transit_mode: str | None = None
    transit_summary: str | None = None
    cltr_mnmt_no: str | None = None
    image_url: str | None = None
    image_urls: list[str] | None = None
    atch_file_lst_no: int | None = None
    market_median_price: int | None = None
    market_min_price: int | None = None
    market_max_price: int | None = None
    market_sample_count: int | None = None
    market_period_months: int | None = None
    market_diff_percent: float | None = None
    market_endpoint_label: str | None = None
    market_match_kind: str | None = None
    market_samples: list[dict[str, Any]] | None = None
    rental_monthly_avg: int | None = None
    rental_deposit_avg: int | None = None
    rental_sample_count: int | None = None
    rental_yield_percent: float | None = None
    rental_match_kind: str | None = None
    rental_endpoint_label: str | None = None
    rental_samples: list[dict[str, Any]] | None = None
    rights_analysis: dict[str, Any] | None = None
    predicted_price_low: int | None = None
    predicted_price_median: int | None = None
    predicted_price_high: int | None = None
    predicted_price_basis: str | None = None
    asset_type: str | None = None
    source: str = "onbid"
    court_case_no: str | None = None
    court_office_cd: str | None = None
    court_office_nm: str | None = None
    court_item_seq: int | None = None


class PropertyDetail(PropertyBase):
    id: int | None = None
    detail_json: dict[str, Any] | None = None
    rights_json: dict[str, Any] | None = None
    schedule_json: dict[str, Any] | None = None
    fee_rate: str | None = None
    region_line: str | None = None


class PropertyListItem(PropertyBase):
    id: int | None = None
    fee_rate: str | None = None
    region_line: str | None = None


class ScrapeStatus(BaseModel):
    running: bool = False
    last_run_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    count: int = 0
    error: str | None = None


class ScrapeTriggerResponse(BaseModel):
    started: bool
    message: str
