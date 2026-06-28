"""기획부동산 의심 매물 자동 판정 휴리스틱.

사용자 정의 특징(2026-06-25):
  1. 공유자가 많다 (적게는 7명, 최대 100+)
  2. 공유자들의 성·나이·사는 곳이 대부분 다르다 (우리는 성만 추론 가능)
  3. 단시간 불특정 다수에게 매도 (등기부 차단 + 국토부 지번 마스킹으로 자동 판별 불가)

→ 1번 + 2번(성씨 다양성)으로 휴리스틱 구성. 3번은 사용자가 등기부등본으로 직접 확인.

판정 룰 (OR 결합 — 사용자 결정 임계값 A):
  · Rule A: 공유자 ≥ 7  AND 유니크 성씨 / 공유자 ≥ 0.7
  · Rule B: 공유자 ≥ 15 AND 유니크 성씨 / 공유자 ≥ 0.5
  · Rule C: 공유자 ≥ 30 (다양성 무관)

공유자 정의: parties_json 안 role ∈ {"공유자", "채무자겸소유자"}.
"""
from __future__ import annotations

import json
from typing import Any

_CO_OWNER_ROLES = frozenset({"공유자", "채무자겸소유자"})

# 자동 휴리스틱이 단 reason 의 prefix (=수동 사유와 구분).
AUTO_REASON_PREFIX = "[자동]"


def judge(
    parties_json: str | None,
    co_owner_count: int | None,
) -> tuple[bool, str | None]:
    """기획부동산 의심 여부 + 사유 텍스트 반환.

    parties_json/co_owner_count 가 없으면 (False, None).
    의심 매물: (True, "[자동] 기획부동산 의심: 공유자 N명, 성씨 X종(다양성 Y%) — Rule Z").
    의심 아님: (False, None).
    """
    if not parties_json or not co_owner_count or co_owner_count < 7:
        return False, None
    try:
        parties = json.loads(parties_json)
    except (TypeError, ValueError):
        return False, None
    co_owners = [p for p in parties if p.get("role") in _CO_OWNER_ROLES]
    n = len(co_owners)
    if n < 7:
        return False, None
    # 마스킹된 이름의 첫 글자 = 성 (복성·법인명 일부 오차 허용)
    surnames = {((p.get("name") or "?")[0]) for p in co_owners}
    n_sur = len(surnames)
    diversity = n_sur / n if n else 0.0

    rule = None
    if n >= 30:
        rule = "C(≥30명)"
    elif n >= 15 and diversity >= 0.5:
        rule = "B(≥15명·다양성≥0.5)"
    elif n >= 7 and diversity >= 0.7:
        rule = "A(≥7명·다양성≥0.7)"
    if not rule:
        return False, None

    # alert_blacklist_reason 컬럼 50자 제한 안에 핵심만 압축.
    # 예: "[자동] 기획부동산 의심 — 공유자65/성26(40%)" ≈ 35자
    reason = (
        f"{AUTO_REASON_PREFIX} 기획부동산 의심 — "
        f"공유자{n}/성{n_sur}({diversity:.0%})"
    )
    return True, reason[:50]


def is_auto_managed(alert_blacklist: int | bool | None, reason: str | None) -> bool:
    """이 매물의 블랙리스트 상태가 *자동 휴리스틱이 관리* 중인지.

    True 면 자동 백필이 재평가 후 갱신/해제할 수 있다.
    False 면 사용자 수동 설정 → 자동이 건드리지 않는다.
    """
    if not alert_blacklist:
        return True  # 블랙리스트가 아니면 자동이 새로 켤 수 있음
    if not reason:
        return False  # 수동 토글(사유 미입력)으로 간주 — 보존
    return reason.startswith(AUTO_REASON_PREFIX)
