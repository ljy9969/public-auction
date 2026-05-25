"""국토부 건축HUB 건축물대장 표제부 (getBrTitleInfo) 연동.

Kakao 주소 검색으로 법정동코드 + 번/지를 얻어 표제부를 호출, 지상층수·건물명·
승강기 대수 등을 가져온다.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

REGISTRY_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _lookup_kakao_address(address: str, kakao_key: str) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                "https://dapi.kakao.com/v2/local/search/address.json",
                params={"query": address},
                headers={"Authorization": f"KakaoAK {kakao_key}"},
            )
            r.raise_for_status()
            docs = r.json().get("documents") or []
            if not docs:
                return None
            return docs[0].get("address") or None
    except Exception as exc:
        logger.debug("Kakao address lookup failed for %r: %s", address, exc)
        return None


def fetch_building_info(address: str) -> dict[str, Any] | None:
    """Address → 건축물대장 표제부 main item (max grndFlrCnt across 동들)."""
    kakao_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    bldg_key = os.environ.get("BLDG_REGISTRY_API_KEY", "").strip()
    if not (address and kakao_key and bldg_key):
        return None

    addr_info = _lookup_kakao_address(address, kakao_key)
    if not addr_info:
        return None
    b_code = (addr_info.get("b_code") or "").strip()
    if len(b_code) != 10:
        return None
    bun = (addr_info.get("main_address_no") or "").zfill(4)
    ji = (addr_info.get("sub_address_no") or "0").zfill(4)
    if not bun or bun == "0000":
        return None

    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.get(
                REGISTRY_URL,
                params={
                    "serviceKey": bldg_key,
                    "sigunguCd": b_code[:5],
                    "bjdongCd": b_code[5:],
                    "platGbCd": "1" if addr_info.get("mountain_yn") == "Y" else "0",
                    "bun": bun,
                    "ji": ji,
                    "_type": "json",
                    "numOfRows": "30",
                    "pageNo": "1",
                },
            )
            r.raise_for_status()
            data = r.json()
            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") != "00":
                logger.debug(
                    "Registry %s: %s", header.get("resultCode"), header.get("resultMsg")
                )
                return None
            items = data.get("response", {}).get("body", {}).get("items") or {}
            raw = items.get("item") if isinstance(items, dict) else None
            if not raw:
                return None
            item_list = raw if isinstance(raw, list) else [raw]
            return max(item_list, key=lambda it: _safe_int(it.get("grndFlrCnt")) or 0)
    except Exception as exc:
        logger.debug("Registry fetch failed for %r: %s", address, exc)
        return None


def apply_building_registry(prop: dict[str, Any]) -> dict[str, Any]:
    """Enrich prop with floor_total / building_name / elevator override / use_apr_day / main_purps."""
    addr = prop.get("address_jibun") or ""
    if not addr:
        return prop
    info = fetch_building_info(addr)
    if not info:
        return prop

    floor_total = _safe_int(info.get("grndFlrCnt"))
    if floor_total and floor_total > 0:
        prop["floor_total"] = floor_total

    bld_name = (info.get("bldNm") or "").strip()
    if bld_name:
        prop["building_name"] = bld_name

    elv_ride = _safe_int(info.get("rideUseElvtCnt")) or 0
    elv_emer = _safe_int(info.get("emgenUseElvtCnt")) or 0
    if (elv_ride + elv_emer) > 0:
        # Registry trumps unknown — explicit elevator presence
        prop["elevator_yn"] = "Y"

    use_apr = (info.get("useAprDay") or "").strip()
    if use_apr:
        prop["use_apr_day"] = use_apr

    main_purps = (info.get("mainPurpsCdNm") or "").strip()
    if main_purps:
        prop["main_purps"] = main_purps

    # 도로명주소 — newPlatPlc (예: "서울특별시 강남구 테헤란로 ...")
    road = (info.get("newPlatPlc") or "").strip()
    if road and not prop.get("address_road"):
        prop["address_road"] = road

    return prop
