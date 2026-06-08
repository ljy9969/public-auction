r"""법원경매 주소에 누락된 법정리(里) 복구 + 재지오코딩.

배경: _build_address 가 hjguRd(=실제 법정리명) 필드를 빠뜨려 면·읍 지역 농지가
'경기도 평택시 현덕면 397-1'처럼 리 없이 저장됐고, Kakao 지오코딩이 엉뚱한 리로
잡혔다(2026-06-08 운정리 397-1 → 권관리 오마커). parse.py 수정 후, 이미 저장된
court 행을 법원 API에서 다시 받아 올바른 주소·좌표로 갱신한다.

대상: source='court' 이면서 '…면/읍 <지번>'에 리가 빠진 행만.

    .\.venv\Scripts\python.exe -m scripts.backfill_court_ri          # dry-run
    .\.venv\Scripts\python.exe -m scripts.backfill_court_ri --apply  # DB 갱신
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 콘솔 기본 cp949 → 한국어/em-dash 출력 시 UnicodeEncodeError. utf-8 강제.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from scraper.db import get_connection
from scraper.filters.coords import haversine_km
from scraper.filters.geo import geocode_kakao, geocode_kakao_keyword
from scraper.session import load_criteria
from scraper_court.codes import SIDO_CODES, USG_LCL_TARGET
from scraper_court.parse import parse_court_row
from scraper_court.search import iter_all_pages
from scraper_court.session import CourtSession

# 면·읍 직후 리 없이 지번(또는 '산'+지번)이 오는 court 주소 = 리 누락 의심.
TARGET_SQL = (
    "SELECT id, cltr_no, address_jibun FROM properties "
    "WHERE source='court' AND ("
    "address_jibun GLOB '*[읍면] [0-9]*' OR address_jibun GLOB '*[읍면] 산[0-9]*')"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="DB 갱신 (기본 dry-run)")
    parser.add_argument("--max-pages", type=int, default=60)
    args = parser.parse_args(argv)

    api_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    if not api_key:
        print("[FATAL] KAKAO_REST_API_KEY 미설정 — 지오코딩 불가")
        return 1

    criteria = load_criteria()
    seo = criteria["regions"]["seolleung"]
    pf = criteria.get("post_filters", {})
    max_price = int(pf.get("max_min_price", 300_000_000))
    max_fail = int(pf.get("max_fail_count", 3))

    conn = get_connection()
    targets = {dict(r)["cltr_no"]: dict(r) for r in conn.execute(TARGET_SQL).fetchall()}
    print(f"대상 court 행: {len(targets)}건")
    for t in targets.values():
        print(f"  id={t['id']} {t['cltr_no']} | {t['address_jibun']}")

    # 대상은 모두 경기도. 토지+건물 sweep 으로 재수신 후 cltr_no 매칭.
    found: dict[str, dict] = {}
    with CourtSession() as session:
        session.warm_up()
        for usg in USG_LCL_TARGET:
            for row in iter_all_pages(
                session,
                sido_cd=SIDO_CODES["경기도"],
                usg_lcl=usg,
                max_price=max_price,
                max_fail_count=max_fail,
                max_pages=args.max_pages,
                page_size=50,
            ):
                prop = parse_court_row(row)
                if prop and prop.get("cltr_no") in targets and prop["cltr_no"] not in found:
                    found[prop["cltr_no"]] = prop

    print(f"\nAPI 재매칭: {len(found)}/{len(targets)}건")

    updated = 0
    for cltr_no, t in targets.items():
        prop = found.get(cltr_no)
        if not prop:
            print(f"[miss] id={t['id']} {cltr_no} — API 결과에 없음(폐기/마감 추정), 수동 확인 요")
            continue
        new_addr = prop.get("address_jibun") or ""
        if new_addr == t["address_jibun"]:
            print(f"[same] id={t['id']} {cltr_no} — 주소 변화 없음: {new_addr!r}")
            continue
        coords = geocode_kakao(new_addr, api_key)
        if not coords:
            kw = prop.get("title") or new_addr
            coords = geocode_kakao_keyword(kw, api_key)
        if not coords:
            print(f"[skip] id={t['id']} {cltr_no} — 지오코딩 실패: {new_addr!r}")
            continue
        lat, lng = coords
        dist = round(haversine_km(lat, lng, seo["lat"], seo["lng"]), 2)
        print(
            f"[ok]   id={t['id']} {cltr_no}\n"
            f"        {t['address_jibun']!r} -> {new_addr!r}\n"
            f"        coords -> ({lat:.5f}, {lng:.5f})  {dist}km"
        )
        if args.apply:
            conn.execute(
                "UPDATE properties SET address_jibun=?, title=?, geo_lat=?, geo_lng=?, "
                "distance_seolleung_km=? WHERE id=?",
                (new_addr, prop.get("title") or new_addr, lat, lng, dist, t["id"]),
            )
            updated += 1

    if args.apply:
        conn.commit()
    conn.close()
    print(f"\n{'갱신' if args.apply else 'dry-run(갱신 예정)'}: {updated if args.apply else '—'}건")
    if not args.apply:
        print("실제 반영하려면 --apply 를 붙여 다시 실행하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
