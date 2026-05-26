"""Post-scrape filters: geo, building registry, quality, transit, elevator, danger."""
from scraper.filters.building import apply_building_registry
from scraper.filters.danger import apply_danger_filters
from scraper.filters.elevator import apply_elevator_filter
from scraper.filters.geo import apply_geo_filters
from scraper.filters.quality import apply_quality_filters
from scraper.filters.transit import apply_transit_filter

__all__ = [
    "apply_geo_filters",
    "apply_transit_filter",
    "apply_quality_filters",
    "apply_elevator_filter",
    "apply_building_registry",
    "apply_danger_filters",
]


def apply_all_post_filters(prop: dict, raw: dict | None = None) -> dict:
    prop.setdefault("passes_filters", True)
    prop = apply_geo_filters(prop)
    # Building registry runs after geo (address verified) and before elevator
    # so elevator filter can pick up registry-derived elevator_yn.
    prop = apply_building_registry(prop)
    prop = apply_quality_filters(prop)
    prop = apply_transit_filter(prop)
    prop = apply_elevator_filter(prop, raw=raw)
    # 마지막 — 책 기반 위험 시그널 (농업진흥구역 BLOCK, 맹지/분묘 등 CAUTION)
    prop = apply_danger_filters(prop)
    return prop
