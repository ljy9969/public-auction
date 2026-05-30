"""낙찰 통계 대시보드 — #4.

데이터 한계: 실 낙찰가는 온비드 낙찰결과를 별도 수집해야 하며 미구현.
대안으로 **현재 등록된 매물의 할인율·예측 낙찰가**로 통계를 산출한다.

- 카테고리별 평균 할인율 = 1 - min_price / appraisal_price
- 유찰 회차별 분포 + 평균 할인율
- 지역(시/도) 분포
- 입찰 마감 시계열 (일자별 매물 수)
- 예측 낙찰가율 = predicted_price_median / appraisal_price

추후 `auction_results` 테이블이 채워지면 실 낙찰가 기반 통계가 가산된다.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from scraper import db as scraper_db


def _category_bucket(prop: dict[str, Any]) -> str:
    cat = (prop.get("category") or "") + (prop.get("title") or "")
    if prop.get("building_shared") or prop.get("share_yn") == "Y":
        return "주거 지분"
    if any(k in cat for k in ("도로", "토지", "전 /", "답 /", "과수원", "임야", "대지")):
        return "토지/도로"
    if "오피스텔" in cat or "용도복합" in cat:
        return "오피스텔/용도복합"
    if "아파트" in cat or "주상복합" in cat:
        return "아파트"
    if any(k in cat for k in ("빌라", "다세대", "도시형생활")):
        return "빌라/다세대"
    if "단독주택" in cat or "전원주택" in cat:
        return "단독주택"
    return "기타"


def _region_bucket(prop: dict[str, Any]) -> str:
    """시/도 단위 region — 주소 첫 토큰."""
    addr = prop.get("address_jibun") or prop.get("address_road") or ""
    if not addr:
        return "미상"
    first = addr.split()[0] if addr else "미상"
    return first or "미상"


def _discount(prop: dict[str, Any]) -> float | None:
    appr = prop.get("appraisal_price")
    mp = prop.get("min_price")
    if not appr or appr <= 0 or not mp or mp <= 0:
        return None
    return round((1 - mp / appr) * 100, 2)


def _predicted_ratio(prop: dict[str, Any]) -> float | None:
    appr = prop.get("appraisal_price")
    pred = prop.get("predicted_price_median")
    if not appr or appr <= 0 or not pred or pred <= 0:
        return None
    return round(pred / appr * 100, 2)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.mean(values), 2)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 2)


def compute_stats() -> dict[str, Any]:
    rows = scraper_db.list_properties(passes_only=True, limit=10_000, offset=0)

    cat_disc: dict[str, list[float]] = defaultdict(list)
    cat_pred: dict[str, list[float]] = defaultdict(list)
    region_count: dict[str, int] = defaultdict(int)
    fail_disc: dict[int, list[float]] = defaultdict(list)
    bid_end_count: dict[str, int] = defaultdict(int)
    price_buckets: dict[str, int] = defaultdict(int)
    risk_count: dict[str, int] = defaultdict(int)

    total = 0
    discounts_all: list[float] = []
    predicted_all: list[float] = []

    for r in rows:
        total += 1
        cat = _category_bucket(r)
        region = _region_bucket(r)
        region_count[region] += 1

        d = _discount(r)
        if d is not None:
            cat_disc[cat].append(d)
            discounts_all.append(d)
            fail = int(r.get("fail_count") or 0)
            fail_disc[fail].append(d)

        p = _predicted_ratio(r)
        if p is not None:
            cat_pred[cat].append(p)
            predicted_all.append(p)

        # 입찰 마감 일별 분포 (yyyy-mm-dd)
        bid_end = r.get("bid_end")
        if isinstance(bid_end, str) and len(bid_end) >= 10:
            bid_end_count[bid_end[:10]] += 1

        # 가격 버킷 (만 원)
        mp = r.get("min_price")
        if mp:
            if mp < 10_000_000:
                price_buckets["~1천만"] += 1
            elif mp < 50_000_000:
                price_buckets["1~5천만"] += 1
            elif mp < 100_000_000:
                price_buckets["5천만~1억"] += 1
            elif mp < 200_000_000:
                price_buckets["1~2억"] += 1
            elif mp < 300_000_000:
                price_buckets["2~3억"] += 1
            else:
                price_buckets["3억+"] += 1

        # 권리 위험도 분포
        ra = r.get("rights_analysis")
        if isinstance(ra, dict):
            risk_count[ra.get("risk_level", "unknown")] += 1
        else:
            risk_count["unknown"] += 1

    by_category = [
        {
            "category": cat,
            "count": len(cat_disc.get(cat, [])),
            "avg_discount_pct": _avg(cat_disc.get(cat, [])),
            "median_discount_pct": _median(cat_disc.get(cat, [])),
            "avg_predicted_ratio_pct": _avg(cat_pred.get(cat, [])),
        }
        for cat in sorted(set(cat_disc.keys()) | set(cat_pred.keys()))
    ]

    by_fail = [
        {
            "fail_count": k,
            "count": len(v),
            "avg_discount_pct": _avg(v),
            "median_discount_pct": _median(v),
        }
        for k, v in sorted(fail_disc.items())
    ]

    by_region = sorted(
        [{"region": k, "count": v} for k, v in region_count.items()],
        key=lambda x: -x["count"],
    )[:12]

    timeline = sorted(
        [{"date": k, "count": v} for k, v in bid_end_count.items()],
        key=lambda x: x["date"],
    )

    price_distribution = [
        {"bucket": b, "count": price_buckets.get(b, 0)}
        for b in ("~1천만", "1~5천만", "5천만~1억", "1~2억", "2~3억", "3억+")
    ]

    risk_distribution = [
        {"level": k, "count": v}
        for k, v in sorted(risk_count.items(), key=lambda x: ["low", "medium", "high", "unknown"].index(x[0]) if x[0] in ("low", "medium", "high", "unknown") else 99)
    ]

    return {
        "total_count": total,
        "overall_avg_discount_pct": _avg(discounts_all),
        "overall_median_discount_pct": _median(discounts_all),
        "overall_avg_predicted_ratio_pct": _avg(predicted_all),
        "by_category": by_category,
        "by_fail_count": by_fail,
        "by_region": by_region,
        "bid_end_timeline": timeline,
        "price_distribution": price_distribution,
        "risk_distribution": risk_distribution,
        "data_note": (
            "통계는 현재 등록된 진행 매물의 할인율(1 - 최저가/감정가) 기반입니다. "
            "실 낙찰가 시계열은 온비드 낙찰결과 별도 수집 후 추가될 예정입니다."
        ),
    }
