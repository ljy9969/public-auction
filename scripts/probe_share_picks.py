"""오늘 지분 투자 추천 0건 진단 — 3조건별 통과 매물 수 카운트.

Usage:
    python -m scripts.probe_share_picks
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.notify_share_investment import _load_catalysts, _match_catalyst  # noqa: E402

DB = ROOT / "data" / "onbid.db"
THRESHOLD = 0.70


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, title, address_jibun, category, share_yn,
               building_share_ratio, land_share_ratio, min_price, appraisal_price,
               market_median_price, fail_count, rights_analysis,
               court_case_no
        FROM properties
        WHERE passes_filters = 1 AND share_yn = 'Y'
        """
    ).fetchall()
    con.close()
    catalysts = _load_catalysts()
    print(f"지분(share_yn=Y) 매물 총: {len(rows)}건")
    print(f"호재 화이트리스트 항목: {len(catalysts)}건")

    # risk_level 분포 — '왜 low 가 0건인가' 진단
    risk_dist: dict[str, int] = {}
    sample_by_level: dict[str, list[str]] = {}
    for r in rows:
        ra = r["rights_analysis"]
        risk = None
        if isinstance(ra, str) and ra:
            try:
                risk = (json.loads(ra) or {}).get("risk_level")
            except json.JSONDecodeError:
                pass
        key = risk if risk else "NULL/parse-err"
        risk_dist[key] = risk_dist.get(key, 0) + 1
        sample_by_level.setdefault(key, []).append(str(r["id"]))
    print()
    print("=== risk_level 분포 (지분 매물 기준) ===")
    for k, v in risk_dist.items():
        print(f"  {k}: {v}건  (id 예: {', '.join(sample_by_level[k][:5])})")

    # medium/high 매물 1건의 flags 봐서 어떤 키워드로 막혔는지
    for r in rows:
        ra = r["rights_analysis"]
        if isinstance(ra, str) and ra:
            try:
                a = json.loads(ra) or {}
                if a.get("risk_level") and a.get("risk_level") != "low":
                    print()
                    print(f"=== 샘플 (id={r['id']}, {a.get('risk_level')}) ===")
                    print(f"  summary: {a.get('summary')}")
                    print(f"  flags: {a.get('flags')}")
                    break
            except json.JSONDecodeError:
                pass

    n_risk_low = 0
    n_cat = 0
    n_price = 0
    n_all = 0
    pass_risk: list[sqlite3.Row] = []
    pass_risk_cat: list[sqlite3.Row] = []

    for r in rows:
        ra = r["rights_analysis"]
        risk = None
        if isinstance(ra, str) and ra:
            try:
                risk = (json.loads(ra) or {}).get("risk_level")
            except json.JSONDecodeError:
                pass
        if risk == "low":
            n_risk_low += 1
            pass_risk.append(r)

        cat = _match_catalyst(r["address_jibun"] or "", catalysts)
        if cat:
            n_cat += 1
        if risk == "low" and cat:
            pass_risk_cat.append((r, cat))

        # 가격 조건
        sr = r["building_share_ratio"] or r["land_share_ratio"]
        sr = sr if (sr is not None and 0 < sr < 1) else None
        mn = r["min_price"]
        med = r["market_median_price"]
        ap = r["appraisal_price"]
        if mn:
            if med:
                ref = int(med * sr) if sr else int(med)
            elif ap:
                ref = int(ap)
            else:
                ref = 0
            if ref > 0 and mn <= ref * THRESHOLD:
                n_price += 1
                if risk == "low" and cat:
                    n_all += 1

    print()
    print("=== 조건별 통과 건수 (지분 매물 기준) ===")
    print(f"  ① 권리 안전 (risk_level=low): {n_risk_low}")
    print(f"  ② 지역 호재 매칭            : {n_cat}")
    print(f"  ③ 가격 ≤ 기준가×{THRESHOLD}      : {n_price}")
    print(f"  ★ 3조건 모두                : {n_all}")

    print()
    print("=== ①+② 통과 매물 (가격만 살펴보면 됨) ===")
    for r, cat in pass_risk_cat[:10]:
        mn = r["min_price"]
        med = r["market_median_price"]
        ap = r["appraisal_price"]
        sr_v = r["building_share_ratio"] or r["land_share_ratio"]
        sr_v = sr_v if (sr_v and 0 < sr_v < 1) else None
        ref = (int(med * sr_v) if (med and sr_v) else (med or ap)) if (med or ap) else None
        ratio = (mn / ref * 100) if (mn and ref) else None
        ratio_s = f"{ratio:.0f}%" if ratio is not None else "-"
        print(
            f"  id={r['id']} {(r['address_jibun'] or r['title'])[:30]} "
            f"min={mn} ref={ref} ({ratio_s}) · 호재={cat['name']}"
        )
    if not pass_risk_cat:
        print("  (없음)")

    print()
    print("=== ① 통과 매물 주소 (호재 매칭 안 된 매물 — 화이트리스트 보강 후보) ===")
    for r in pass_risk[:20]:
        addr = r["address_jibun"] or r["title"]
        print(f"  id={r['id']} {addr[:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
