"""한 매물의 가격 관련 필드 진단 — DB / detail API 양쪽에서.

사용자 보고: 1회 유찰된 매물의 BidScope min_price 가 감정가와 동일.
검색 API의 minmaePrice 가 첫 회차 가격을 그대로 반환하는 게 의심.

Usage:
    python -m scripts.probe_min_price 2025타경51291
"""
from __future__ import annotations

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


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.probe_min_price <court_case_no>")
        return 1
    case_no = sys.argv[1]

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, cltr_no, court_case_no, court_office_cd, court_item_seq,
                  min_price, appraisal_price, fail_count, title
           FROM properties WHERE court_case_no=? ORDER BY id""",
        (case_no,),
    ).fetchall()
    if not rows:
        print(f"DB 에 {case_no} 없음")
        return 1

    print(f"=== DB ({len(rows)} 행) ===")
    for r in rows:
        print(f"  id={r['id']} cltr_no={r['cltr_no']} cort={r['court_office_cd']} seq={r['court_item_seq']}")
        print(f"    min_price={r['min_price']:,}원  appraisal={r['appraisal_price']:,}원  유찰={r['fail_count']}회")
        print(f"    title={r['title'][:60]}")
    conn.close()

    cort = rows[0]["court_office_cd"]
    seq = rows[0]["court_item_seq"] or 1

    print()
    print(f"=== detail API ({case_no} / {cort} / seq={seq}) ===")
    with CourtSession() as sess:
        d = fetch_detail(sess, cs_no=case_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)

    print(f"dma_result 키: {list(d.keys())}")
    print()

    # 가격/금액 관련 필드는 모두 출력
    KEYWORDS = ("price", "amt", "mae", "val", "gameval", "minmae")

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = k.lower()
                if any(w in kl for w in KEYWORDS) and not isinstance(v, (dict, list)):
                    print(f"  {path}.{k} = {v!r}")
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:3]):  # 첫 3개만
                walk(v, f"{path}[{i}]")

    print("=== '가격/금액' 키워드 필드들 ===")
    walk(d)

    # gdsDspslDxdyLst (회차별 매각기일 리스트)는 별도로 정리
    print()
    print("=== gdsDspslDxdyLst (회차별 매각기일) ===")
    dxdy = d.get("gdsDspslDxdyLst") or []
    for i, item in enumerate(dxdy):
        if isinstance(item, dict):
            print(f"  [{i}] {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
