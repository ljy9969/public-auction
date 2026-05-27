"""Parse Onbid JSON list rows and detail HTML into property dicts."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from scraper.session import load_criteria, load_selectors


def detail_url(row: dict[str, Any]) -> str:
    """API 호출용 detail URL (scraper의 fetch_detail_html에서 사용 — 외부 노출 X)."""
    criteria = load_criteria()
    selectors = load_selectors()
    base = criteria["onbid"].get("base_url", "https://www.onbid.co.kr").rstrip("/")
    path = criteria["onbid"]["detail_path"]
    params = selectors["detail"]["url_params"]
    qs = "&".join(f"{k}={row[k]}" for k in params if row.get(k))
    return f"{base}{path}?{qs}"


def public_source_url(row: dict[str, Any]) -> str:
    """사용자용 '온비드 원문 보기' URL — 검색 페이지에 물건관리번호 prefill.

    mvmnCltrDtl.do는 직접 접근 시 404 페이지를 반환하므로 검색 결과 페이지로
    유도한다. scrnIndctCltrMngNo(화면표시 물건관리번호)가 검색 input과 호환.
    """
    base = "https://www.onbid.co.kr"
    mnmt = row.get("scrnIndctCltrMngNo") or row.get("cltrMnmtNo") or ""
    if mnmt:
        return (
            f"{base}/op/cltrpbancinf/cltr/cltrcdtnsrch/CltrCdtnSrchController/"
            f"mvmnCltrCdtnSrchClg.do?srchCltrMnmtNo={mnmt}"
        )
    return detail_url(row)


def _extract_jibun(title: str, region: str) -> str | None:
    """Pull the first bun-ji token (e.g. '708-16') that follows the dong name in the title."""
    if not title:
        return None
    remainder = title
    if region and title.startswith(region):
        remainder = title[len(region):].lstrip()
    m = re.match(r"^(\d+(?:-\d+)?)", remainder)
    return m.group(1) if m else None


def _cltr_image_url(row: dict[str, Any]) -> str | None:
    """Onbid 매물 대표 사진 (첫 번째 — atchSn=2)."""
    atch_lst = row.get("atchFileLstNo")
    if not atch_lst:
        return None
    return _cltr_image_url_for(atch_lst, 2)


def _cltr_image_url_for(atch_lst: Any, sn: int) -> str:
    return (
        "https://www.onbid.co.kr/op/cm/syc/filemng/filemngprcs/FileMngPrcsController/"
        f"dnldImgFile.do?atchFileLstNo={atch_lst}&atchSn={sn}"
        "&thnImgDownloadFlag=false&downloadImageKind=CLG_FILE_NM"
    )


def _cltr_image_urls(row: dict[str, Any], max_count: int = 5) -> list[str]:
    """대표 사진 + 추가 사진들 (atchSn 2..N). 실제 존재 여부는 프론트에서 onerror 처리."""
    atch_lst = row.get("atchFileLstNo")
    if not atch_lst:
        return []
    return [_cltr_image_url_for(atch_lst, sn) for sn in range(2, 2 + max_count)]


def parse_list_row(row: dict[str, Any]) -> dict[str, Any]:
    title = (row.get("onbidCltrNm") or "").strip()
    region = (row.get("sidoSgkEmd") or "").strip()
    share_yn = "Y" if "지분" in title else "N"
    jibun = _extract_jibun(title, region)
    address_jibun = f"{region} {jibun}".strip() if region and jibun else (region or title)
    return {
        "cltr_no": str(row.get("onbidCltrno") or ""),
        "pbct_no": str(row.get("pbctNo") or "") or None,
        "pbct_cdtn_no": str(row.get("pbctCdtnNo") or "") or None,
        "onbid_pbanc_no": str(row.get("onbidPbancNo") or "") or None,
        "title": title,
        "address_jibun": address_jibun,
        "address_road": None,
        "category": row.get("ctgrFullNm") or row.get("ctgrNm"),
        "bid_method": row.get("cptnMtdNm") or row.get("cptnMthodCd"),
        "min_price": _int(row.get("lowstBidPrc")),
        "appraisal_price": _int(row.get("cltrApslEvlAvgAmt")),
        "area_build_m2": _float(row.get("bldSqms")),
        "share_yn": share_yn,
        "fail_count": _int(row.get("uscbdCnt") or row.get("usbdCnt")),
        "bid_start": row.get("pbctBegnDtm"),
        "bid_end": row.get("pbctLastDdlnDt") or row.get("pbctDdlnDt"),
        "status": row.get("pbancPbctCltrStatNm"),
        "fee_rate": str(row.get("feeRate")) if row.get("feeRate") is not None else None,
        "region_line": region,
        "source_url": public_source_url(row),
        "cltr_mnmt_no": row.get("scrnIndctCltrMngNo") or row.get("cltrMnmtNo"),
        "image_url": _cltr_image_url(row),
        "image_urls": _cltr_image_urls(row, max_count=5),
        "atch_file_lst_no": row.get("atchFileLstNo"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "raw_list": row,
    }


def _parse_area_info(soup: BeautifulSoup) -> list[dict[str, str]]:
    """면적정보 표 파싱. PC table + 모바일 ul.op_mobile_tbl01 둘 다 지원.

    반환 행 키: {용도, 면적, 지분, 비고}
    """
    # PC: <table> with headers 용도/면적/지분/비고
    rows_out: list[dict[str, str]] = []
    for table in soup.select("table"):
        first_tr = table.select_one("tr")
        if not first_tr:
            continue
        headers = [c.get_text(" ", strip=True) for c in first_tr.find_all(["th", "td"])]
        if not ({"용도", "면적", "지분"}.issubset(set(headers))):
            continue
        idx = {name: headers.index(name) for name in ("용도", "면적", "지분") if name in headers}
        bigo_idx = headers.index("비고") if "비고" in headers else None
        for tr in table.select("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) < max(idx.values()) + 1:
                continue
            rows_out.append({
                "용도": cells[idx["용도"]],
                "면적": cells[idx["면적"]],
                "지분": cells[idx["지분"]],
                "비고": cells[bigo_idx] if bigo_idx is not None and bigo_idx < len(cells) else "",
            })
        if rows_out:
            return rows_out

    # 모바일: <div class="op_mobile_tbl01"> <ul> <li class="col_item"> <div>...</div> </li> </ul>
    # 각 li.col_item가 한 행, 그 안의 div가 컬럼. div 안의 span 텍스트가 값.
    for ul in soup.select(".op_mobile_tbl01 ul"):
        items = ul.select("li.col_item")
        if not items:
            continue
        for li in items:
            divs = li.find_all("div", recursive=False) or li.find_all("div")
            if len(divs) < 3:
                continue
            cells = [d.get_text(" ", strip=True) for d in divs]
            # 컬럼 순서: 용도 / 면적 / 지분 / 비고 (4개)
            row = {
                "용도": cells[0] if len(cells) > 0 else "",
                "면적": cells[1] if len(cells) > 1 else "",
                "지분": cells[2] if len(cells) > 2 else "",
                "비고": cells[3] if len(cells) > 3 else "",
            }
            if row["용도"] or row["면적"]:
                rows_out.append(row)
        if rows_out:
            return rows_out

    return rows_out


def _is_share_marked(value: str) -> bool:
    v = (value or "").strip()
    if not v or v in ("-", "—", "ㅡ", "·"):
        return False
    return "지분" in v or "/" in v or "분의" in v


def _building_shared(area_rows: list[dict[str, str]]) -> bool | None:
    """True if 건물 row indicates shared ownership; None if no 건물 row found."""
    found = False
    for r in area_rows:
        if "건물" in r["용도"]:
            found = True
            if _is_share_marked(r["지분"]) or _is_share_marked(r["비고"]):
                return True
    return False if found else None


def parse_detail_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    detail: dict[str, str] = {}
    rights: dict[str, str] = {}
    schedule: dict[str, str] = {}

    for table in soup.select("table"):
        for tr in table.select("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)
            value = cells[1].get_text(" ", strip=True)
            if not label:
                continue
            detail[label] = value
            if any(k in label for k in ("근저당", "가압류", "권리", "임차")):
                rights[label] = value
            if any(k in label for k in ("입찰", "개찰", "일정")):
                schedule[label] = value

    area_rows = _parse_area_info(soup)
    building_shared = _building_shared(area_rows)
    # 후방 호환: share_yn은 '건물 지분'에 한정해 Y/N 부여
    if building_shared is True:
        share_yn = "Y"
    elif building_shared is False:
        share_yn = "N"
    else:
        share_yn = None

    bld = _extract_area(detail.get("건물면적") or detail.get("연면적") or "")
    from scraper.filters.elevator import elevator_from_detail

    elevator_yn = elevator_from_detail(detail)
    return {
        "detail_json": detail,
        "rights_json": rights or None,
        "schedule_json": schedule or None,
        "share_yn": share_yn,
        "building_shared": building_shared,
        "area_info": area_rows or None,
        "area_build_m2": bld,
        "elevator_yn": elevator_yn,
    }


def _extract_area(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*㎡", text)
    return float(m.group(1)) if m else None


def _int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
