"""법원경매 P2 dry-run 다각도 진단.

목적:
1. 다양한 조건(토지/건물·전국/서울·지분/단독)으로 데이터 흐름 검증
2. 좌표·면적·카테고리 라벨이 들어있는 raw field 발굴
3. sido 필터의 실제 동작 확인
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper_court.search import iter_all_pages
from scraper_court.session import CourtSession


def run_scenario(s: CourtSession, name: str, **kwargs) -> list[dict]:
    print(f"\n========== {name} ==========")
    rows = list(iter_all_pages(s, max_pages=2, page_size=50, **kwargs))
    print(f"받은 row: {len(rows)}")
    if not rows:
        return rows
    # 시도(시군구) 분포
    sigu = Counter(r.get("hjguSigu") or "?" for r in rows)
    print(f"시군구 top: {sigu.most_common(8)}")
    # 카테고리 코드 분포
    mcls = Counter(r.get("mclsUtilCd") for r in rows)
    scls = Counter(r.get("sclsUtilCd") for r in rows)
    print(f"mcls top: {mcls.most_common(5)}")
    print(f"scls top: {scls.most_common(8)}")
    # 지분 여부 (mulBigo + title)
    share_y = sum(1 for r in rows if "지분" in (r.get("mulBigo") or "") or "지분" in (r.get("buldList") or ""))
    print(f"지분 매물(추정): {share_y}")
    return rows


def main() -> int:
    diag = {}
    with CourtSession() as s:
        s.warm_up()

        # 1) 토지 + 서울 sido + 1천만 이하
        r1 = run_scenario(s, "1) 토지 + sido=11(서울) + ≤1천만", sido_cd="11", usg_lcl="10000", max_price=10000000)
        # 2) 토지 전국 + 1천만 이하
        r2 = run_scenario(s, "2) 토지 전국 + ≤1천만", sido_cd="", usg_lcl="10000", max_price=10000000)
        # 3) 건물 + 서울 + 3억 이하
        r3 = run_scenario(s, "3) 건물 + sido=11(서울) + ≤3억", sido_cd="11", usg_lcl="20000", max_price=300000000)
        # 4) 토지 + 서울중앙지법(B000210)
        r4 = run_scenario(s, "4) 토지 + 서울중앙지법 + ≤1천만", court_cd="B000210", usg_lcl="10000", max_price=10000000)

    # 모든 row 합쳐서 raw field 분석
    all_rows = r1 + r2 + r3 + r4
    if all_rows:
        print(f"\n========== raw field 분석 (총 {len(all_rows)}건) ==========")
        # 각 row의 좌표·면적·카테고리 라벨 후보 필드 검사
        sample = all_rows[0]
        print(f"\n[샘플 row의 모든 키 ({len(sample)}개)]")
        for k in sorted(sample.keys()):
            v = sample.get(k)
            if isinstance(v, str) and len(v) > 200:
                v = v[:120] + "..."
            print(f"  {k}: {v!r}")

        # 좌표 후보 필드 분포
        print("\n[좌표 후보 — 한국 영역 검증]")
        for fld_x, fld_y in [("xCordi", "yCordi"), ("wgs84Xcordi", "wgs84Ycordi")]:
            ok = 0
            for r in all_rows:
                try:
                    x = float(r.get(fld_x) or 0)
                    y = float(r.get(fld_y) or 0)
                    # WGS84: lng 124-132, lat 33-39 / KATEC/TM: x 100k-1M, y 1M-2M
                    if 33 < y < 39 and 124 < x < 132:
                        ok += 1
                    elif 100_000 < x < 1_500_000 and 1_500_000 < y < 2_500_000:
                        ok += 1
                except (TypeError, ValueError):
                    pass
            print(f"  {fld_x}/{fld_y}: 유효 좌표 {ok}/{len(all_rows)} 건")

        # 면적 후보 필드
        print("\n[면적 후보]")
        for k in ("minArea", "maxArea", "pjbBuldList"):
            have = sum(1 for r in all_rows if r.get(k))
            print(f"  {k}: 채워진 row {have}/{len(all_rows)}")
        # 샘플
        print("\n  샘플 면적값:")
        for r in all_rows[:5]:
            print(f"   minArea={r.get('minArea')!r} maxArea={r.get('maxArea')!r} pjbBuldList={(r.get('pjbBuldList') or '')[:60]!r}")

        # 카테고리 라벨 후보 — Nm으로 끝나는 필드 중 카테고리스러운 것
        print("\n[카테고리 라벨 후보 — *UtilNm/*Nm 필드]")
        name_keys = set()
        for r in all_rows[:10]:
            for k in r.keys():
                if k.endswith("Nm") and "util" in k.lower():
                    name_keys.add(k)
        for k in sorted(name_keys):
            sample_vals = [r.get(k) for r in all_rows[:5] if r.get(k)]
            print(f"  {k}: {sample_vals[:3]}")

        # mulBigo (현황 비고) 샘플 — 지분/특이사항 키워드 검출
        print("\n[mulBigo 샘플 5건 — 지분·특이사항 정보 검출용]")
        for i, r in enumerate(all_rows[:5]):
            bigo = r.get("mulBigo") or ""
            print(f"  {i+1}. ({r.get('srnSaNo')}) {bigo[:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
