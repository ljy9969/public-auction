"""지분 투자 추천 매물을 Discord 웹훅으로 전송.

매일 수집·백필 후, 아래 3조건을 모두 만족하는 주거/토지 '지분' 매물을 선별해 알린다.
  ① 권리분석 안전 — rights_analysis.risk_level == 'low' (인수 위험·대항력 임차인 미검출)
  ② 시세/감정가 대비 저가 — 최저입찰가 ≤ 기준가 × threshold(기본 0.70)
     · 시세(국토부 실거래가) 있으면 '지분 환산 시세' 기준
     · 지분 매물은 시세 매칭이 드물어, 없으면 '감정가' 기준으로 폴백
  ③ 지역 호재 — scraper/config/regional_catalysts.yaml 화이트리스트 주소 매칭

⚠️ 호재는 운영자가 관리하는 화이트리스트 매칭이며(2026-01 지식 기반 초안),
   실제 추진 여부·물건과의 직접 연관성은 토지이음/시청 등으로 직접 확인해야 한다.

사용법:
    python -m scripts.notify_share_investment              # 전송(기본 0.70)
    python -m scripts.notify_share_investment --dry-run    # 콘솔 출력만
    python -m scripts.notify_share_investment --threshold 0.8

DISCORD_WEBHOOK 미설정 시 dry-run으로 동작.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()
DB_PATH = ROOT / os.environ.get("ONBID_DB_PATH", "data/onbid.db")
CATALYSTS_PATH = ROOT / "scraper" / "config" / "regional_catalysts.yaml"

# 호재의 '매도가 상승 기여도'(impact) → 이모지. 상=큰 상승, 중=보통, 하=제한적.
IMPACT_EMOJI = {"상": "🔴", "중": "🟠", "하": "🟡"}


def _load_catalysts() -> list[dict]:
    try:
        data = yaml.safe_load(CATALYSTS_PATH.read_text(encoding="utf-8"))
        return data.get("catalysts") or []
    except Exception as exc:
        print(f"[warn] 호재 화이트리스트 로드 실패: {exc!r}")
        return []


def _match_catalyst(address: str, catalysts: list[dict]) -> dict | None:
    """매물 주소에 호재 match 문자열이 하나라도 포함되면 그 호재 반환."""
    addr = address or ""
    for c in catalysts:
        for m in c.get("match") or []:
            if m and m in addr:
                return c
    return None


def _format_won(n: int | None) -> str:
    if not n:
        return "-"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n / 10_000:.0f}만"
    return f"{n}원"


def _share_ratio(p: dict) -> float | None:
    if p.get("share_yn") != "Y":
        return None
    r = p.get("building_share_ratio")
    if r is None:
        r = p.get("land_share_ratio")
    return r if (r is not None and 0 < r < 1) else None


# 지분 매물의 '본질적' flag — 매물이 지분이라는 사실 자체로 거의 항상 붙는다.
# 이 두 가지만 켜져 있는 medium 은 '인수 위험 없음' 으로 간주, 알림 대상에 포함.
# (이걸 인수 위험으로 보면 모든 지분 매물이 컷돼 알림이 0건이 되는 문제 — 2026-06-07)
_SHARE_INTRINSIC_FLAGS = frozenset({"co_owner_priority", "minority_share"})


def _risk_ok_for_share(p: dict) -> bool:
    """지분 알림 통과 기준 — low 면 무조건 통과, medium 은 본질 flag 만 있으면 통과."""
    ra = p.get("rights_analysis")
    if not isinstance(ra, str) or not ra:
        return False
    try:
        a = json.loads(ra) or {}
    except json.JSONDecodeError:
        return False
    level = a.get("risk_level")
    if level == "low":
        return True
    if level == "medium":
        flags = a.get("flags") or []
        other = [f for f in flags if f.get("kind") not in _SHARE_INTRINSIC_FLAGS]
        return not other
    return False


def _pick(p: dict, threshold: float) -> dict | None:
    """3조건 평가 → 통과 시 알림용 dict, 아니면 None."""
    if not _risk_ok_for_share(p):
        return None

    cat = p.get("_catalyst")
    if not cat:
        return None

    sr = _share_ratio(p)
    mn = p.get("min_price")
    med = p.get("market_median_price")
    ap = p.get("appraisal_price")
    if not mn:
        return None

    if med:
        ref = int(med * sr) if sr else int(med)
        basis = "시세"
    elif ap:
        ref = int(ap)
        basis = "감정가"
    else:
        return None

    if ref <= 0 or mn > ref * threshold:
        return None

    return {
        "id": p["id"],
        "address": p.get("address_jibun") or p.get("title"),
        "category": p.get("category") or "",
        "min_price": mn,
        "ref": ref,
        "basis": basis,
        "pct": round(mn / ref * 100),
        "fail_count": p.get("fail_count") or 0,
        "share_pct": round(sr * 100, 1) if sr else None,
        "catalyst": cat,
        # 검색창에 붙여넣을 식별번호
        "search_no": p.get("court_case_no") or p.get("cltr_mnmt_no") or "",
    }


def build_message(threshold: float, limit: int) -> str | None:
    catalysts = _load_catalysts()
    if not catalysts:
        return None

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, title, address_jibun, category, source, share_yn,
               building_share_ratio, land_share_ratio, min_price, appraisal_price,
               market_median_price, fail_count, rights_analysis,
               cltr_mnmt_no, court_case_no
        FROM properties
        WHERE passes_filters = 1 AND share_yn = 'Y'
        """
    ).fetchall()
    con.close()

    picks: list[dict] = []
    for r in rows:
        p = dict(r)
        p["_catalyst"] = _match_catalyst(p.get("address_jibun"), catalysts)
        hit = _pick(p, threshold)
        if hit:
            picks.append(hit)

    if not picks:
        return None

    # 할인율 큰 순 (저렴할수록 먼저)
    picks.sort(key=lambda x: x["pct"])
    picks = picks[:limit]

    lines = [
        f"💎 **지분 투자 추천 {len(picks)}건** — 권리 안전 · {basis_label(threshold)} · 지역 호재",
        "_매일 수집 후 자동 선별. 호재는 화이트리스트 매칭 — 추진 여부·현장은 직접 확인하세요._",
        "_호재 옆 매도가 상승 기여도: 🔴상 · 🟠중 · 🟡하_",
    ]
    for i, x in enumerate(picks, 1):
        cat = x["catalyst"]
        share = f"지분 {x['share_pct']}% · " if x["share_pct"] is not None else ""
        impact = cat.get("impact")
        impact_tag = f" {IMPACT_EMOJI.get(impact, '')}{impact}" if impact else ""
        lines.append(
            f"\n**{i}. {x['address']}**  ·  {x['category']}"
            f"\n   💰 최저 {_format_won(x['min_price'])} · {x['basis']} 대비 **{x['pct']}%** (유찰 {x['fail_count']}회)"
            f"\n   🧩 {share}권리 안전"
            f"\n   📈 호재: {cat['name']} ({cat.get('type', '')}){impact_tag}"
            + (f"\n   🔎 검색: `{x['search_no']}`" if x["search_no"] else "")
        )
    return "\n".join(lines)


def basis_label(threshold: float) -> str:
    return f"시세/감정가 대비 ≤{int(threshold * 100)}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="기준가(시세/감정가) 대비 최저가 상한 비율 (기본 0.70)")
    parser.add_argument("--limit", type=int, default=15, help="알림 최대 건수")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    msg = build_message(args.threshold, args.limit)
    if msg is None:
        print("지분 투자 추천 대상 없음")
        return 0

    if args.dry_run or not WEBHOOK:
        print(msg)
        if not WEBHOOK:
            print("\n[note] DISCORD_WEBHOOK 미설정 — 실제 전송 생략")
        return 0

    try:
        resp = httpx.post(WEBHOOK, json={"content": msg}, timeout=20)
        print(f"Discord 지분 투자 추천 전송: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"Discord 전송 실패: {exc!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
