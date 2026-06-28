"""자동 블랙리스트 통합 판정 — 여러 휴리스틱 룰 OR.

사용자 결정(2026-06-25/28):
  · 임계값: planned_re_filter 의 A/B/C 룰 그대로
  · 수동 우선: alert_blacklist_reason 이 "[자동]" prefix 인 매물만 자동 관리
  · 백필 분리: scripts/backfill_planned_re_suspect.py 가 매일 호출

룰 (우선순위 — 매칭 시 첫 번째 reason만 채택):
  1. 기획부동산 의심        ← planned_re_filter.judge (공유자+다양성)
  2. 분양형 호텔            ← danger.py 가 filter_notes에 마킹 (caution:)
  3. 분묘기지권 성립        ← danger.py (성립 명시·부정어 부재)
  4. 국가산단 지식산업센터  ← danger.py (가산동·구로동 우선)
  5. 무허가/불법건축물      ← danger.py (농지)
  6. 선하지(고압선)         ← danger.py
  7. 맹지(도로 미접)        ← danger.py

원천: 「실전 부동산 경매(수익 실현편)」 — 유근용·정민우
"""
from __future__ import annotations

import json
from typing import Any

from scraper.planned_re_filter import (
    AUTO_REASON_PREFIX,
    is_auto_managed,
    judge as judge_planned_re,
)

# (filter_notes 안 caution 키워드, 블랙리스트 reason 라벨). 우선순위 순서.
# 주의 — 부분 문자열 매칭이므로 더 구체적인 키워드를 앞에 두어야 한다.
# 예: "분묘기지권 성립"이 "분묘기지권"보다 먼저. "분묘 존재"는 격상 X(=목록 미포함).
_CAUTION_BLACKLIST_RULES = (
    ("분양형 호텔", "분양형 호텔 (시세 신뢰↓)"),
    ("분묘기지권 성립", "분묘기지권 성립"),
    ("국가산단 지식산업센터", "국가산단 지산 (임대 제한)"),
    ("무허가/불법건축물", "무허가/불법건축물"),
    ("선하지", "선하지 (고압선)"),
    ("맹지", "맹지 (도로 미접)"),
)


def _filter_notes(prop: dict[str, Any]) -> list[str]:
    fn = prop.get("filter_notes")
    if isinstance(fn, list):
        return fn
    if isinstance(fn, str):
        try:
            decoded = json.loads(fn)
            return decoded if isinstance(decoded, list) else []
        except (TypeError, ValueError):
            return []
    return []


def judge_blacklist(prop: dict[str, Any]) -> tuple[bool, str | None]:
    """매물 한 건에 대해 자동 블랙리스트 결정.

    반환: (True, "[자동] ...") 또는 (False, None).
    여러 룰이 매칭돼도 우선순위 첫 번째 reason 만 채택(50자 제한 + 가독성).
    """
    # 1. 기획부동산 의심 (가장 명확한 위험)
    suspect, reason = judge_planned_re(
        prop.get("parties_json"),
        prop.get("co_owner_count"),
    )
    if suspect:
        return True, reason

    # 2~4. filter_notes 의 caution 키워드 매칭 → 블랙리스트 격상
    notes = _filter_notes(prop)
    notes_text = " ".join(notes)
    for kw, label in _CAUTION_BLACKLIST_RULES:
        if kw in notes_text:
            return True, f"{AUTO_REASON_PREFIX} {label}"[:50]

    return False, None


# 재export — 호환성
__all__ = ["judge_blacklist", "is_auto_managed", "AUTO_REASON_PREFIX"]
