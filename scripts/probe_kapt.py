"""K-apt OpenAPI probe — 4개 API 모두 명세 확정 후 service명 후보 시도.

확정 op명 (사용자 캡처):
  공용관리비:   /getHsmp{LaborCost,Cleaning,Guard,...}InfoV2  (17종)
  개별사용료:   /getHsmp{HeatCost,HotWater,Electricity,...}InfoV2  (10종)
  장기수선:     /getHsmp{MonthRetalFee,ReserveBalance,...}InfoV2  (4종)
  단지목록:     /get{Sido,Sigungu,Total,Legaldong,Roadname}AptList3  (5종, V3)

확정 service: 공용관리비 = AptCmnuseManageCostServiceV2
추측: 나머지 3개
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

API_KEY = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
TEST_KAPT = "A10027405"
TEST_DATE = "202504"


def _call(url: str, params: dict, label: str) -> bool:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as c:
            r = c.get(url, params=params)
            sc = r.status_code
            body = r.text
    except Exception as e:
        sc, body = -1, f"<ERROR> {e!r}"
    is_ok = (sc == 200) and ("Unexpected" not in body) and ("SERVICE ERROR" not in body) and "API not found" not in body
    flag = "OK" if is_ok else "--"
    print(f"{flag} [{label}] HTTP {sc}")
    print(f"  URL: {url}")
    print(f"  Body[0:250]: {body[:250]}")
    print()
    return is_ok


def main() -> None:
    if not API_KEY:
        raise SystemExit("DATA_GO_KR_API_KEY 미설정")
    print(f"API_KEY: {API_KEY[:8]}...{API_KEY[-8:]}\n")

    cost_params = {
        "ServiceKey": API_KEY,
        "kaptCode": TEST_KAPT,
        "searchDate": TEST_DATE,
        "_type": "json",
    }

    # === 단지 목록 (V3) ===
    print("=" * 60)
    print("단지 목록 service명 후보 (op=getLegaldongAptList3 V3)")
    print("=" * 60)
    list_candidates = [
        "AptListService3",
        "AptListServiceV3",
        "AphusBassInfoServiceV3",
        "BrAptListServiceV3",
        "AptBassInfoServiceV3",
    ]
    list_params = {
        "ServiceKey": API_KEY,
        "loadCode": "1171010300",
        "pageNo": 1,
        "numOfRows": 50,
        "_type": "json",
    }
    for svc in list_candidates:
        _call(
            f"https://apis.data.go.kr/1613000/{svc}/getLegaldongAptList3",
            list_params,
            f"단지목록 / {svc}",
        )

    # === 개별사용료 (V2) ===
    print("=" * 60)
    print("개별사용료 service명 후보 (op=getHsmpHeatCostInfoV2)")
    print("=" * 60)
    indvdl_candidates = [
        "AptIndvdlUseFeeServiceV2",
        "AptIndvdlzUseFeeServiceV2",
        "AptIndvdlzUseFeeOfferServiceV2",
        "AptIndvdlUseFeeOfferServiceV2",
        "AptIndvdlUsefeeServiceV2",
        "AptIndvdlzUsefeeServiceV2",
        "AptIndvdlChrgServiceV2",
        "AptIndvdlChrgInfoServiceV2",
    ]
    for svc in indvdl_candidates:
        _call(
            f"https://apis.data.go.kr/1613000/{svc}/getHsmpHeatCostInfoV2",
            cost_params,
            f"개별사용료 / {svc}",
        )

    # === 장기수선충당금 (V2) ===
    print("=" * 60)
    print("장기수선 service명 후보 (op=getHsmpMonthFeeInfoV2)")
    print("=" * 60)
    lng_candidates = [
        "AptLngTrmRsrvFundServiceV2",
        "AptLngtrmRsrvFundServiceV2",
        "AptLngTrmRpirRsvfundServiceV2",
        "AptLngTrmRprRsvfundServiceV2",
        "AptLngtrmRpirRsvfundServiceV2",
        "AptLongTermReserveFundServiceV2",
        "AptLngtrmRprRsrvFundServiceV2",
        "AptLngTrmRprRsrvFundServiceV2",
    ]
    for svc in lng_candidates:
        _call(
            f"https://apis.data.go.kr/1613000/{svc}/getHsmpMonthFeeInfoV2",
            cost_params,
            f"장기수선 / {svc}",
        )


if __name__ == "__main__":
    main()
