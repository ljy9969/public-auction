"""Test which search payload returns Seoul Songpa/Gangnam rows."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from urllib.parse import urlencode

from scraper.session import create_session, load_criteria

def post_custom(session, extra_pairs: list[tuple[str, str]]):
    from scraper.search import build_search_payload
    from datetime import date, timedelta
    base = build_search_payload(1)
    # parse and replace
    pairs = []
    for part in base.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            pairs.append((k, v))
    # remove keys we're overriding
    override_keys = {k for k, _ in extra_pairs}
    pairs = [(k, v) for k, v in pairs if k not in override_keys and k != "srchArrayRgn" and k != "srchPrptType"]
    pairs.extend(extra_pairs)
    body = urlencode(pairs)
    criteria = load_criteria()
    path = criteria["onbid"]["list_path"]
    with session.httpx_client() as client:
        r = client.post(path, content=body, headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        r.raise_for_status()
        return r.json()


def count_seoul(rows):
    sp = sum(1 for r in rows if "송파" in (r.get("sidoSgkEmd") or ""))
    gn = sum(1 for r in rows if "강남" in (r.get("sidoSgkEmd") or ""))
    return sp, gn, len(rows)


def main():
    session = create_session()
    tests = [
        ("default_criteria", []),
        ("songpa_rgn", [("srchArrayRgn", "1100000000|1171000000")]),
        ("gangnam_rgn", [("srchArrayRgn", "1100000000|1168000000")]),
        ("cltr_nm_songpa", [("srchCltrNm", "송파구")]),
        ("no_prpt_type", [("srchPrptType", "")]),
    ]
    for name, extra in tests:
        if name == "no_prpt_type":
            data = post_custom(session, [("srchCltrType", "0001"), ("srchDspsMthod", "0001")])
        else:
            data = post_custom(session, extra)
        rows = data.get("cltrInfVOList") or []
        sp, gn, n = count_seoul(rows)
        print(f"{name}: rows={n} songpa={sp} gangnam={gn}")


if __name__ == "__main__":
    main()
