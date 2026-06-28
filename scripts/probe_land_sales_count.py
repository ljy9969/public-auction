"""기획부동산 3번 신호 검증 — 국토부 토지매매 실거래가에서 같은 지번/동 거래 수.

가설: 기획부동산이면 같은 지번에 다수가 매수 → MOLIT 토지매매 데이터에서
같은 지번에 짧은 기간 거래가 많이 잡혀야 한다.

표적 3건 (현재 의심 매물 + 통제군):
  · id=1915 처인구 해곡동 산65-5      공유자 65명  (가장 확실한 의심)
  · id=1917 현덕면 운정리 204-2       공유자 19명  (의심)
  · id=1916 안중읍 성해리 산43-3      공유자 9명   (경계, 가족 다지분 가능)

코드 적용은 하지 않고 결과만 출력.

Usage:
    python -m scripts.probe_land_sales_count
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API_KEY = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
KAKAO_KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
LAND_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade"

# 표적 매물 (id, 주소, 비교용 공유자 수)
TARGETS = [
    (1915, "경기도 용인시 처인구 해곡동 산65-5", 65),
    (1917, "경기도 평택시 현덕면 운정리 204-2", 19),
    (1916, "경기도 평택시 안중읍 성해리 산43-3", 9),
    # 통제군 — 단독 매물 (공유자 1명, 기획 부동산 아님)
    (1859, "서울특별시 은평구 갈현동 477-28", 1),
]

# 최근 36개월 (3년)
MONTHS = 36


def recent_months(n: int) -> list[str]:
    """YYYYMM 문자열 리스트 (지금부터 n개월 전까지)."""
    from datetime import date
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def kakao_sgg_cd(addr: str) -> tuple[str | None, str | None, str | None]:
    """주소 → (sgg_cd 5자리, 동/리명, 지번 본번-부번 문자열) 반환."""
    if not KAKAO_KEY:
        return None, None, None
    try:
        r = httpx.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            params={"query": addr},
            headers={"Authorization": f"KakaoAK {KAKAO_KEY}"},
            timeout=10.0,
        )
        r.raise_for_status()
        docs = r.json().get("documents") or []
        if not docs:
            return None, None, None
        addr_info = docs[0].get("address") or {}
        b_code = (addr_info.get("b_code") or "").strip()
        sgg_cd = b_code[:5] if len(b_code) >= 5 else None
        umd = (addr_info.get("region_3depth_name") or "").strip()
        bonbun = addr_info.get("main_address_no") or ""
        bubun = addr_info.get("sub_address_no") or ""
        jibun = f"{bonbun}-{bubun}" if bubun else bonbun
        # 산 번지는 main_address_no 가 '산1' 같은 형태
        return sgg_cd, umd, jibun
    except Exception as e:
        print(f"  kakao err: {e}")
        return None, None, None


def fetch_trades(sgg_cd: str, ymd: str) -> list[dict]:
    """해당 시군구·월의 토지매매 거래 전부."""
    items: list[dict] = []
    page = 1
    while True:
        r = httpx.get(LAND_ENDPOINT, params={
            "serviceKey": API_KEY,
            "LAWD_CD": sgg_cd,
            "DEAL_YMD": ymd,
            "_type": "json",
            "numOfRows": "1000",
            "pageNo": str(page),
        }, timeout=15.0)
        try:
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        body = (data.get("response") or {}).get("body") or {}
        raw = (body.get("items") or {}).get("item")
        if not raw:
            break
        if isinstance(raw, dict):
            raw = [raw]
        items.extend(raw)
        total = int(body.get("totalCount") or 0)
        if page * 1000 >= total:
            break
        page += 1
    return items


def main() -> int:
    if not API_KEY:
        print("DATA_GO_KR_API_KEY 미설정")
        return 1
    months = recent_months(MONTHS)
    print(f"검사 기간: 최근 {MONTHS}개월 ({months[-1]} ~ {months[0]})\n")

    for prop_id, addr, n_co in TARGETS:
        print(f"=== id={prop_id} {addr} (공유자 {n_co}명) ===")
        sgg_cd, umd, my_jibun = kakao_sgg_cd(addr)
        print(f"  sgg_cd={sgg_cd} umd={umd!r} my_jibun={my_jibun!r}")
        if not sgg_cd or not umd:
            print("  주소 조회 실패\n")
            continue

        # 산 번지 처리: address_jibun "산43-3" → kakao 결과의 main_no가 "산43" 일 수도
        is_san = "산" in addr.split(umd)[-1] if umd in addr else False
        my_addr_jibun = addr.split(umd)[-1].strip()  # "산43-3" 또는 "204-2"

        all_trades: list[dict] = []
        for ymd in months:
            for t in fetch_trades(sgg_cd, ymd):
                if (t.get("umdNm") or "").strip() == umd:
                    all_trades.append(t)

        print(f"  같은 동·리({umd}) 토지매매 총: {len(all_trades)}건")

        # 같은 지번 거래만 추리기 — t.jibun 이 우리 매물 지번과 같은지
        same_jibun = []
        for t in all_trades:
            tj = (t.get("jibun") or "").strip()
            if tj and (tj == my_addr_jibun or tj.replace(" ", "") == my_addr_jibun.replace(" ", "")):
                same_jibun.append(t)

        print(f"  같은 지번({my_addr_jibun!r}) 거래: {len(same_jibun)}건")
        if same_jibun:
            # 거래일 분포
            dates = sorted(
                f"{t.get('dealYear')}-{int(t.get('dealMonth') or 0):02d}-{int(t.get('dealDay') or 0):02d}"
                for t in same_jibun
            )
            print(f"    날짜 분포: {dates[0]} ~ {dates[-1]}")
            from collections import Counter as _C
            month_counts = _C(
                f"{t.get('dealYear')}-{int(t.get('dealMonth') or 0):02d}"
                for t in same_jibun
            )
            top_months = month_counts.most_common(5)
            print(f"    월별 top: {top_months}")

        # 같은 동의 지번별 거래 수 — 다수 거래 지번 확인
        jibun_counts = Counter((t.get("jibun") or "").strip() for t in all_trades)
        top10 = jibun_counts.most_common(10)
        print(f"  같은 동 지번별 top10: {top10}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
