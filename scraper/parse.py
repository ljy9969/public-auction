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
        "asset_type": (row.get("scrnPrptDvsnNm") or "").strip() or None,
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
    """True if 건물 row가 '실제 지분'(비율 < 100%)을 나타냄. None이면 건물 행 없음.

    주의: '1분의1 지분'(100%)은 단독 소유이므로 지분이 아님 → False.
    """
    found = False
    for r in area_rows:
        if "건물" in r["용도"]:
            found = True
            ratio = _parse_share_fraction(r["비고"]) or _parse_share_fraction(r["지분"])
            if ratio is not None:
                if ratio < 1.0:
                    return True   # 실제 지분 (예: 9/10)
                # ratio >= 1.0 → 단독 (1분의1) — 지분 아님, 계속 확인
            elif _is_share_marked(r["지분"]) or _is_share_marked(r["비고"]):
                return True       # 비율 못 구했지만 지분 표기 있음
    return False if found else None


def _parse_share_fraction(text: str) -> float | None:
    """지분 비율(0~1) 추출.

    예: '지분(총면적 43.85 10분의9 지분)' → 9/10 = 0.9
        '지분(총면적 195 1950분의298.35 지분)' → 298.35/1950 = 0.153
        '지분 2/7' → 2/7 = 0.286
    """
    if not text:
        return None
    # 한국식: 'N분의M' → M/N (분모가 앞)
    m = re.search(r"([\d.]+)\s*분의\s*([\d.]+)", text)
    if m:
        denom, numer = float(m.group(1)), float(m.group(2))
        if denom > 0:
            return numer / denom
    # 서양식: 'M/N' → M/N
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
    if m:
        numer, denom = float(m.group(1)), float(m.group(2))
        if denom > 0:
            return numer / denom
    return None


def _building_share_ratio(area_rows: list[dict[str, str]]) -> float | None:
    """건물 행의 지분 비율(0~1). 100%(단독) 또는 지분 표기 없으면 None."""
    for r in area_rows:
        if "건물" in r["용도"]:
            ratio = _parse_share_fraction(r["비고"]) or _parse_share_fraction(r["지분"])
            if ratio is not None and ratio < 1.0:
                return round(ratio, 4)
    return None


# 온비드 detail 페이지의 '소유권 이전비용 계산기' 위젯 등 — 권리관계/상세정보가 아닌 UI 노이즈
_NOISE_KEYWORDS = (
    "삭제메시지",
    "계산하기",
    "초기화",
    "기준시가표준액",
    "소유권 이전비용",
    "소유권 이전 등기비용",
    "국민주택채권 매입기준표",
    "매입기준표 참고",
    "바로가기",
)


def _is_noise(label: str, value: str) -> bool:
    text = f"{label} {value}"
    if any(k in text for k in _NOISE_KEYWORDS):
        return True
    # 계산기 폼이 한 셀에 통째로 들어온 비정상적으로 긴 값
    return len(value) > 400


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
            if _is_noise(label, value):
                continue
            detail[label] = value
            if any(k in label for k in ("근저당", "가압류", "권리", "임차")):
                rights[label] = value
            if any(k in label for k in ("입찰", "개찰", "일정")):
                schedule[label] = value

    area_rows = _parse_area_info(soup)
    building_shared = _building_shared(area_rows)
    building_share_ratio = _building_share_ratio(area_rows)
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
        "building_share_ratio": building_share_ratio,
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
