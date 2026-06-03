"""모든 외부 API 통합 백필 — 건축물대장 + ODsay 한 번에.

기존 DB 행에 floor_total / building_name / use_apr_day / main_purps /
address_road / transit_minutes / transit_mode / transit_summary 채움.

처리 순서 (2026-06-03 — ODsay 일일 한도 1,000건 위기 대응):
  1. 오피스텔/용도복합 우선 (가장 가치 높은 카테고리)
  2. 주거 단독 (share_yn != 'Y')
  3. 그 외 (지분/토지 — ODsay 호출 없음, 좌표·건축물대장만)
  같은 카테고리 내에서는 bid_end 임박 순 (NULL 후순위).

카테고리별 ODsay 호출 횟수를 누적해 마지막에 요약 출력 — 다음 backfill
설계 결정(쿼터 분배, throttle 여부)의 근거 데이터로 사용.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 콘솔 cp949에서 한글/박스문자 print 깨짐 방지 (scraper_court.run과 동일)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.db import get_connection
from scraper.filters.building import fetch_building_info
from scraper.filters.geo import resolve_coords
from scraper.filters.transit import apply_transit_filter, _should_calculate_transit
from scraper.session import load_criteria


def _safe_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def main() -> None:
    conn = get_connection()
    # ODsay 예산 가드가 별도 커넥션으로 카운터를 쓰므로, 루프 중 잠깐 겹쳐도
    # 에러 대신 대기하도록. (아래 per-row commit과 함께 잠금 충돌 최소화)
    conn.execute("PRAGMA busy_timeout=15000")
    criteria = load_criteria()
    # 우선순위 정렬:
    #   priority 0 = 오피스텔/용도복합, 1 = 주거 단독, 2 = 그 외(지분/토지)
    #   같은 priority 안에서는 bid_end 임박 매물부터 (NULL은 후순위로 밀어둠)
    rows = conn.execute(
        """SELECT id, address_jibun, address_road, title, region_line,
                  geo_lat, geo_lng, floor_total, category, share_yn,
                  transit_minutes, transit_mode, transit_summary, transit_estimated,
                  bid_end
           FROM properties
           ORDER BY
             CASE
               WHEN category LIKE '%오피스텔%' OR category LIKE '%용도복합%' THEN 0
               WHEN category LIKE '%주거%' AND (share_yn IS NULL OR share_yn != 'Y') THEN 1
               ELSE 2
             END,
             CASE WHEN bid_end IS NULL OR bid_end = '' THEN 1 ELSE 0 END,
             bid_end ASC"""
    ).fetchall()

    # 카테고리(+share) → 호출/스킵 분포 누적. 마지막에 요약 출력.
    odsay_called: Counter[str] = Counter()
    odsay_cached: Counter[str] = Counter()
    odsay_skipped: Counter[str] = Counter()
    odsay_deferred: Counter[str] = Counter()  # 일일 한도 도달로 이월된 매물
    for r in rows:
        addr = r["address_jibun"]
        updates: dict = {}

        # 1. 건축물대장 — floor_total 비어 있거나 address_road 없을 때
        if addr and (not r["floor_total"] or not r["address_road"]):
            info = fetch_building_info(addr)
            if info:
                updates["floor_total"] = _safe_int(info.get("grndFlrCnt"))
                updates["building_name"] = (info.get("bldNm") or "").strip() or None
                updates["use_apr_day"] = (info.get("useAprDay") or "").strip() or None
                updates["main_purps"] = (info.get("mainPurpsCdNm") or "").strip() or None
                updates["address_road"] = (info.get("newPlatPlc") or "").strip() or None

        # 1.5. Kakao 좌표 — 카테고리 무관, 모든 row에 적용 (지도 마커용).
        #     transit_filter 가드(2026-06-03) 이후 토지/주거 지분 좌표 미수집 문제 해결.
        if r["geo_lat"] is None or r["geo_lng"] is None:
            prop_for_geo = {
                "address_jibun": addr,
                "title": r["title"],
                "region_line": r["region_line"],
                "geo_lat": r["geo_lat"],
                "geo_lng": r["geo_lng"],
            }
            coords = resolve_coords(prop_for_geo, criteria)
            if coords:
                updates["geo_lat"] = coords[0]
                updates["geo_lng"] = coords[1]

        # 2. ODsay 대중교통 — 오피스텔/용도복합 + 주거 단독만 + transit_minutes 캐시 (2026-06-03 정책).
        #    주거 지분/토지는 skip. transit_minutes가 이미 있으면 ODsay 재호출 안 함.
        cat = r["category"] or ""
        # 카테고리 분포 키 — '주거(지분)' / '주거(단독)' 으로 share 구분도 함께.
        if "주거" in cat and r["share_yn"] == "Y":
            cat_key = f"{cat} (지분)"
        else:
            cat_key = cat
        should_call = _should_calculate_transit(cat, r["share_yn"])
        if not should_call:
            odsay_skipped[cat_key] += 1
        elif r["transit_minutes"] is not None:
            odsay_cached[cat_key] += 1
        else:
            prop = {
                "address_jibun": r["address_jibun"],
                "title": r["title"],
                "region_line": r["region_line"],
                # geo 단계에서 방금 좌표를 채웠다면 그 값 사용 (DB 반영 전이라 r은 옛값)
                "geo_lat": updates.get("geo_lat", r["geo_lat"]),
                "geo_lng": updates.get("geo_lng", r["geo_lng"]),
                "category": cat,
                "share_yn": r["share_yn"],
            }
            t = apply_transit_filter(prop)
            tm = t.get("transit_minutes")
            deferred = any(
                "deferred (ODsay" in n for n in (t.get("filter_notes") or [])
            )
            if tm is not None:
                # ODsay 1콜 소비됨(성공=transit / 실패→heuristic 모두 소비). 결과 기록.
                odsay_called[cat_key] += 1
                updates["transit_minutes"] = tm
                updates["transit_mode"] = t.get("transit_mode")
                updates["transit_summary"] = t.get("transit_summary")
                updates["transit_estimated"] = 1 if t.get("transit_estimated") else 0
            elif deferred:
                # 일일 한도 도달 → 예산 미소비, transit_minutes 비워둠 → 다음 날 재시도.
                odsay_deferred[cat_key] += 1
                print(f"[odsay-defer] id={r['id']} 일일 한도 도달 — 이월 (cat={cat})")
            else:
                # 좌표 미해결 등 — ODsay 호출 자체 없었음. 다음 backfill에서 재시도.
                print(f"[transit-miss] id={r['id']} 좌표 미해결 (cat={cat})")

        if not updates:
            # 건축물대장 + transit 모두 캐시 적중 → 업데이트 없음 (DB·ODsay 부담 0)
            print(f"[skip] id={r['id']} 이미 채워짐 (cat={cat})")
            continue

        # COALESCE로 기존값 보존 (None이면 덮어쓰지 않음, address_road 빼고)
        sets = ", ".join(
            f"{k} = COALESCE(?, {k})" if k != "address_road" else f"{k} = ?"
            for k in updates
        )
        params = list(updates.values()) + [r["id"]]
        conn.execute(f"UPDATE properties SET {sets} WHERE id = ?", params)
        conn.commit()  # per-row commit — ODsay 예산 가드 커넥션의 잠금 대기 최소화
        # 어떤 분야가 채워졌는지 ok 로그에 표시 — 좌표만 채워진 토지 row도 식별 가능.
        parts = [f"[ok] id={r['id']}"]
        if "floor_total" in updates or "address_road" in updates:
            parts.append(f"floor={updates.get('floor_total')} road={updates.get('address_road') or '?'}")
        if "geo_lat" in updates:
            parts.append(f"geo=({updates['geo_lat']:.5f},{updates['geo_lng']:.5f})")
        if "transit_minutes" in updates:
            parts.append(f"transit={updates['transit_minutes']}분({updates.get('transit_mode')})")
        print(" ".join(parts))
    conn.commit()
    conn.close()

    # ── ODsay 카테고리별 호출 분포 요약 ───────────────────────────
    # 일일 한도 1,000건 — called 합계가 다음 backfill의 ODsay 소비량.
    # cached는 캐시 히트(추가 호출 0), skipped는 가드로 막힌 건수.
    total_called = sum(odsay_called.values())
    total_cached = sum(odsay_cached.values())
    total_skipped = sum(odsay_skipped.values())
    total_deferred = sum(odsay_deferred.values())
    print()
    print("── ODsay 호출 분포 (카테고리 × share) ─────────────────────")
    all_keys = sorted(
        set(odsay_called) | set(odsay_cached) | set(odsay_skipped) | set(odsay_deferred),
        key=lambda k: -odsay_called.get(k, 0),
    )
    for k in all_keys:
        print(
            f"  {k:32s} called={odsay_called.get(k, 0):3d}"
            f"  cached={odsay_cached.get(k, 0):3d}"
            f"  skipped={odsay_skipped.get(k, 0):3d}"
            f"  deferred={odsay_deferred.get(k, 0):3d}"
        )
    print(
        f"  {'TOTAL':32s} called={total_called:3d}  cached={total_cached:3d}"
        f"  skipped={total_skipped:3d}  deferred={total_deferred:3d}"
    )
    from scraper.filters import odsay_budget
    print(
        f"  ODsay 일일 예산 {odsay_budget.DAILY_CAP} 중 오늘 누적 "
        f"{odsay_budget.calls_today()}건 사용, 잔여 {odsay_budget.remaining()}건."
    )
    if total_deferred:
        print(f"  [!] {total_deferred}건은 한도 도달로 이월 - 내일(KST 자정 리셋 후) 재시도.")


if __name__ == "__main__":
    main()
