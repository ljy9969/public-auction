"""법원경매 상세(PGJ153F00) 응답에서 '분의' 텍스트 위치 진단.

목적: 검색 API 응답에 토지 지분 분모/분자 정보가 없음을 확인(2026-06-03 진단).
상세 API(scraper_court.detail.fetch_detail)는 같은 응답 dma_result에 목록내역
grid를 포함할 가능성이 큼 — 한 매물만 호출해 dma_result 전체에서 '분의' 패턴이
들어간 경로(key path)를 찾는다.

찾은 경로를 _parse_land_share_ratio에 입력으로 추가해서, 백필이 30건 모두
real ratio로 채울 수 있게 만든다.

Usage:
    python -m scripts.probe_detail_land_share
"""
from __future__ import annotations

import json
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

from scraper_court.detail import fetch_detail
from scraper_court.session import CourtSession

TARGETS = [
    # (cs_no, cort_ofc_cd, dspsl_gds_seq)  -- backfill 결과 처음 3건
    ("2024타경74337", "B000250", 1),   # id=1176, 토지 / 전
    ("2024타경82178", "B000250", 3),   # id=1177, 토지 / 주차장
    ("2025타경863",   "B000250", 1),   # id=1178, 토지 / 임야 (캡처에서 확인된 매물)
]


def grep_paths(obj, needle: str, path: str = "") -> list[tuple[str, str]]:
    """obj 안에서 needle을 포함한 모든 (path, snippet) 리스트."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        if needle in obj:
            out.append((path or "<root>", obj[:400]))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(grep_paths(v, needle, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(grep_paths(v, needle, f"{path}[{i}]"))
    return out


def main() -> int:
    with CourtSession() as sess:
        for cs_no, cort, seq in TARGETS:
            print(f"\n========== {cs_no} ({cort}-{seq}) ==========")
            try:
                d = fetch_detail(sess, cs_no=cs_no, cort_ofc_cd=cort, dspsl_gds_seq=seq)
            except Exception as exc:
                print(f"  ERROR: {exc}")
                continue
            print(f"  dma_result 키: {list(d.keys())}")
            hits = grep_paths(d, "분의")
            if not hits:
                print("  (어디에도 '분의' 없음)")
                # 그래도 ratio가 들어갈 만한 후보 키(목록/지분/면적) 한 줄씩
                for k in d.keys():
                    if any(t in k.lower() for t in ("dlr", "list", "mok", "gd", "lst")):
                        v = d[k]
                        if isinstance(v, list) and v:
                            print(f"    후보 list {k}[0] 키: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")
                            print(f"    후보 list {k}[0] 샘플: {json.dumps(v[0], ensure_ascii=False)[:400]}")
                        else:
                            print(f"    후보 키 {k}: {repr(v)[:200]}")
            else:
                for path, snippet in hits:
                    print(f"  [in {path}]")
                    print(f"    {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
