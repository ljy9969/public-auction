"""Find working Onbid detail URL for a sample row."""
import json
from pathlib import Path

import httpx

from scraper.search import fetch_search_page
from scraper.session import create_session

CANDIDATES = [
    "/op/cltrpbancinf/cltr/cltrdtl/CltrDtlController/mvmnCltrDtl.do",
    "/op/cltrpbancinf/cltr/cltrdtl/CltrDtlController/selectCltrDtl.do",
    "/op/cltrpbancinf/cltr/cltrdtl/CltrDtlController/mvmnCltrPbctDtl.do",
    "/op/cta/cltrpbancinf/cltr/cltrdtl/CltrDtlController/mvmnCltrDtl.do",
]

OUT = Path(__file__).resolve().parent.parent / "docs" / "probe-detail.json"


def main():
    session = create_session()
    data = fetch_search_page(session, 1)
    row = (data.get("cltrInfVOList") or [None])[0]
    if not row:
        print("no rows")
        return
    results = []
    with session.httpx_client() as client:
        for path in CANDIDATES:
            qs = (
                f"?onbidCltrno={row['onbidCltrno']}&pbctCdtnNo={row['pbctCdtnNo']}"
                f"&pbctNo={row['pbctNo']}&onbidPbancNo={row.get('onbidPbancNo','')}"
            )
            url = path + qs
            try:
                r = client.get(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml",
                        "Referer": session.referer,
                    },
                )
                results.append(
                    {
                        "path": path,
                        "status": r.status_code,
                        "len": len(r.text),
                        "has_table": "table" in r.text.lower(),
                    }
                )
            except Exception as e:
                results.append({"path": path, "error": str(e)})
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
