"""토지 지분 매물 3건의 raw 필드 + detail_json 전체 dump.

'분의' 정보가 buldList(=title) 외 어디에 들어 있는지 진단용. 출력 보고
patterns/필드를 추가해서 _parse_land_share_ratio 입력에 반영.

Usage:
    python -m scripts.probe_land_share_source
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


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM properties
           WHERE source='court' AND share_yn='Y' AND category LIKE '토지%'
           ORDER BY id
           LIMIT 3"""
    ).fetchall()
    if not rows:
        print("(토지 지분 매물 없음)")
        return 0

    for r in rows:
        d = dict(r)
        print(f"========== id={d['id']}  category={d['category']} ==========")
        for k, v in d.items():
            if v is None or v == "":
                continue
            if k == "detail_json":
                continue  # 아래서 따로 풀어 출력
            s = repr(v)
            if len(s) > 300:
                s = s[:300] + "...(truncated)"
            print(f"  {k:30s} {s}")
        if d.get("detail_json"):
            print("  --- detail_json ---")
            try:
                dj = json.loads(d["detail_json"])
                for k, v in dj.items():
                    s = repr(v)
                    if len(s) > 500:
                        s = s[:500] + "...(truncated)"
                    print(f"    {k:18s} {s}")
            except Exception as e:
                print(f"    (parse err: {e})")
        # '분의' 패턴이 들어간 필드 모두 표시
        print("  --- '분의' 패턴 탐지 ---")
        found_any = False
        for k, v in d.items():
            if not isinstance(v, str) or "분의" not in v:
                continue
            print(f"    [in {k}] {v[:300]}")
            found_any = True
        if d.get("detail_json"):
            try:
                dj = json.loads(d["detail_json"])
                for k, v in dj.items():
                    if isinstance(v, str) and "분의" in v:
                        print(f"    [in detail_json.{k}] {v[:300]}")
                        found_any = True
            except Exception:
                pass
        if not found_any:
            print("    (어디에도 '분의' 패턴 없음 — court 응답에 정보 자체가 없을 가능성)")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
