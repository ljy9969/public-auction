"""upsert_property 라이브 동작 검증.

같은 cltr_no로 4번 upsert 호출 → 같은 id가 4번 반환되면 정상 (UPDATE 됨).
다른 id가 나오면 버그 — SELECT가 직전 INSERT를 못 본다는 것.

결과:
  - 같은 id 4번: 현재 upsert 정상. 과거 데이터 중복은 이전 버그(이미 픽스됨).
  - 다른 id: 현재도 버그 — 코드 추적 더 필요.

후처리: 만든 임시 row 자동 삭제.

Usage:
    python -m scripts.probe_upsert_sim
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

from scraper.db import upsert_property  # noqa: E402

TEST_CLTR = "TEST-DEDUP-PROBE-1"


def main() -> int:
    base_prop = {
        "cltr_no": TEST_CLTR,
        "title": "dedup probe — auto-cleanup",
        "source": "court",
        "share_yn": "N",
        "category": "토지 / 임야",
        "court_case_no": "TEST타경0-1",
    }
    ids: list[int] = []
    for i in range(4):
        i_id = upsert_property({**base_prop, "title": f"probe call #{i+1}"})
        ids.append(i_id)
        print(f"  call #{i+1} → id={i_id}")

    print()
    if len(set(ids)) == 1:
        print(f"★ 정상 — 4번 모두 동일 id={ids[0]} (UPDATE 작동). "
              f"과거 중복은 이전 버그(아마 bc34fe1 commit 전).")
        verdict = 0
    else:
        print(f"★ 버그 — id={ids} 모두 다름. 4번 INSERT 됨.")
        verdict = 1

    # cleanup — 만든 row 모두 삭제
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM properties WHERE cltr_no = ?", (TEST_CLTR,))
    conn.commit()
    conn.close()
    print(f"cleanup: TEST cltr_no={TEST_CLTR!r} 행 삭제 완료")
    return verdict


if __name__ == "__main__":
    sys.exit(main())
