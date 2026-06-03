"""오늘(KST) ODsay 호출 예산 현황 출력 — 읽기 전용(카운터 증가 없음).

Usage:
    python -m scripts.check_odsay_budget
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 콘솔 cp949에서 한글/특수문자 print 깨짐 방지 (scraper_court.run과 동일 패턴)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.filters import odsay_budget


def main() -> None:
    cap = odsay_budget.DAILY_CAP
    used = odsay_budget.calls_today()
    left = odsay_budget.remaining()
    print(f"ODsay 일일 예산  : {cap}")
    print(f"오늘 사용(KST)   : {used}")
    print(f"잔여             : {left}")
    if left == 0:
        print("상태: 한도 도달 - 이후 transit은 이월(다음 날 재시도)")
    elif left < cap * 0.1:
        print("상태: 잔여 10% 미만 - 곧 이월 시작 가능")
    else:
        print("상태: 여유")


if __name__ == "__main__":
    main()
