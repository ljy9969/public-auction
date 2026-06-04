"""court 매물 면적 필드 진단 — search 의 minArea vs detail 의 다른 필드.

사용자 보고: 2025타경51291 길동청광플러스원큐브 1306호 가 BidPick 에
1536m2(464.64평) 로 표시. 실제 네이버 부동산 = 전용 16.68m2 (공급 25.05m2).
60배 차이 — minArea 가 호수 전용면적이 아니라 다른 의미일 가능성.

Usage:
    python -m scripts.probe_area 2025타경51291
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
DB = ROOT / "data" / "onbid.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper_court.detail import fetch_detail  # noqa: E402
from scraper_court.session import CourtSession  # noqa: E402


def walk_keys_matching(obj, needles, path="", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if any(n in kl for n in needles) and not isinstance(v, (dict, list)):
                out.append((f"{path}.{k}" if path else k, v))
            walk_keys_matching(v, needles, f"{path}.{k}" if path else k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):
            walk_keys_matching(v, needles, f"{path}[{i}]", out)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.probe_area <court_case_no>")
        return 1
    case_no = sys.argv[1]

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, cltr_no, court_case_no, court_office_cd, court_item_seq,
                  area_build_m2, title
           FROM properties WHERE court_case_no=? ORDER BY id""",
        (case_no,),
    ).fetchall()
    if not rows:
        print(f"DB 에 {case_no} 없음")
        return 1

    print(f"=== DB ===")
    r = rows[0]
    print(f"  id={r['id']} area_build_m2={r['area_build_m2']} title={r['title'][:60]}")

    conn.close()

    cort = r["court_office_cd"]
    seq = r["court_item_seq"] or 1

    print()
    print(f"=== detail API ({case_no} / {cort} / seq={seq}) ===")
    with CourtSession() as sess:
        d = fetch_detail(sess, cs_no=case_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)

    print(f"dma_result 키: {list(d.keys())}")
    print()
    print("=== 'area / 면적 / ar' 키워드 ===")
    hits = walk_keys_matching(d, ("area", "ar", "msr"))
    for path, val in hits[:50]:
        print(f"  {path} = {val!r}")

    # 핵심 후보 리스트들 — 첫 항목 전체 dump
    print()
    print("=== gdsDspslObjctLst[0] 전체 ===")
    obj = (d.get("gdsDspslObjctLst") or [None])[0]
    if obj:
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    print()
    print("=== bldSdtrDtlLstAll[0] 전체 (앞 1건만) ===")
    bld_list = d.get("bldSdtrDtlLstAll") or []
    if bld_list:
        first = bld_list[0]
        if isinstance(first, list):
            first = first[0] if first else None
        if first:
            print(json.dumps(first, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
