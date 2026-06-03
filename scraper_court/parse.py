"""법원경매 응답 row → 우리 prop dict 포맷으로 매핑.

P2 dry-run + 진단 결과 반영:
- 면적: `minArea` 사용 (토지·건물 모두 300/300 채워짐, 단위 ㎡)
- 좌표: 응답의 xCordi/yCordi는 미상의 TM이라 변환 정확도 낮음.
        None으로 두고 기존 backfill_geo(Kakao)가 hjgu 지번으로 채움
- 카테고리: scls 코드 prefix → 한국어 라벨 + mulBigo 키워드 결합
- 지분: mulBigo의 "공유자" 키워드가 가장 신뢰성 높음
- 시도 필터: post-filter (hjguSido)에서 처리
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# 토지 종별 (sclsUtilCd 매핑) — 진단 응답에서 빈도순으로 확인된 코드.
# 우리 land_allowed_categories(criteria.yaml)와 매칭되는 라벨로.
_LAND_SCLS_LABEL: dict[str, str] = {
    "10101": "대지",
    "10102": "전",
    "10103": "답",
    "10105": "임야",
    "10108": "잡종지",
    "10114": "주차장",
    "10117": "도로",
    "10125": "주택부지",
    "10128": "기타토지",
    "10110": "공장용지",
    "10112": "창고용지",
    "10115": "과수원",
    "10118": "목장용지",
    "10121": "초지",
}

# 건물 종별 (sclsUtilCd) — 진단 sample 미충분, 보수적 매핑
_BLD_SCLS_LABEL: dict[str, str] = {
    "20101": "아파트",
    "20102": "다세대주택",
    "20103": "다가구주택",
    "20104": "단독주택",
    "20105": "주상복합",
    "20106": "상가",
    "20107": "오피스텔",
    "20108": "도시형생활주택",
    "20109": "연립주택",
    "20110": "빌라",
    "20111": "근린생활시설",
    "20112": "근린주택",
    "20113": "공장",
    "20114": "창고",
    "20115": "기숙사",
    "20116": "전원주택",
}

_LCLS_LABEL = {
    "10000": "토지",
    "20000": "주거용건물",  # 건물 lcl (quality.py 화이트리스트 키워드 매칭용)
}


def _format_ymd(ymd: str | None) -> str | None:
    """YYYYMMDD → 'YYYY-MM-DD HH:MM' (우리 bid_start/bid_end 포맷)."""
    if not ymd or len(ymd) < 8:
        return None
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]} 10:00"  # 기일입찰 통상 10시


def _format_int(n: Any) -> int | None:
    try:
        return int(n) if n is not None and str(n).strip() else None
    except (TypeError, ValueError):
        return None


def _format_price(n: Any) -> int | None:
    v = _format_int(n)
    return v if (v is not None and v > 0) else None


def _format_area(n: Any) -> float | None:
    """minArea 등 — 응답은 정수 문자열(예: '26', '1351'), 단위는 ㎡."""
    try:
        v = float(n)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _category_label(row: dict[str, Any]) -> str:
    lcls = row.get("lclsUtilCd") or ""
    scls = row.get("sclsUtilCd") or ""
    lcl_label = _LCLS_LABEL.get(lcls, "")
    scl_label = ""
    if lcls == "10000":
        scl_label = _LAND_SCLS_LABEL.get(scls, "")
    elif lcls == "20000":
        scl_label = _BLD_SCLS_LABEL.get(scls, "")
    if lcl_label and scl_label:
        return f"{lcl_label} / {scl_label}"
    return lcl_label or scl_label or "기타"


def _is_share(row: dict[str, Any], title: str) -> str:
    """지분 여부 — mulBigo + title + buldList 다중 검사.
    공유자 우선매수신고 / 지분매각 / 지분 키워드 모두 시그널.
    """
    bigo = row.get("mulBigo") or ""
    buld_list = row.get("buldList") or ""
    haystack = f"{bigo} {title} {buld_list}"
    if any(k in haystack for k in ("공유자", "지분", "지분매각", "지분 매각")):
        return "Y"
    return "N"


def _build_address(row: dict[str, Any]) -> tuple[str, str | None]:
    """(address_jibun, address_road). 도로명은 한국어 가공해서 'XX 동/읍/면'까지."""
    sido = row.get("hjguSido") or ""
    sigu = row.get("hjguSigu") or ""
    dong = row.get("hjguDong") or ""
    lotno = row.get("daepyoLotno") or ""
    jibun = " ".join(p for p in (sido, sigu, dong, lotno) if p).strip()

    rd1 = row.get("rd1Nm") or ""
    rd2 = row.get("rd2Nm") or ""
    rd_eup = row.get("rdEubMyun") or ""
    rd_nm = row.get("rdNm") or ""
    buld = row.get("buldNo") or ""
    road_parts = [p for p in (rd1, rd2, rd_eup, rd_nm, buld) if p]
    road = " ".join(road_parts).strip() or None
    return jibun, road


def _parse_sa_no(srn: str) -> tuple[str, str]:
    """'2025타경9546' → ('2025', '9546'). 매칭 실패 시 ('', '')."""
    m = re.match(r"(\d{4})\s*타경\s*(\d+)", srn or "")
    if not m:
        return "", ""
    return m.group(1), m.group(2)


def _build_source_url(row: dict[str, Any], srn_sa_no: str) -> str:
    """물건상세검색(PGJ151F00) 진입점 + 유저스크립트용 hash.

    WebSquare는 URL query params를 무시하지만, hash(#cort=...&name=...&year=...&sa=...)는
    브라우저에 남는다. Tampermonkey 유저스크립트가 읽어 폼 prefill.

    name(법원 한국어명)을 hash에 같이 박는 이유: 법원 select의 option value 형식이
    우리 API 코드('B000250')와 달라 value 매칭이 실패하는 사례 관측(2026-06-03).
    유저스크립트가 value 매칭 실패 시 option.text === name 으로 폴백.
    """
    import urllib.parse
    base = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
    sa_year, sa_ser = _parse_sa_no(srn_sa_no)
    cort = row.get("boCd") or row.get("cortOfcCd") or ""
    name = row.get("jiwonNm") or ""
    parts: list[str] = []
    if cort:
        parts.append(f"cort={cort}")
    if name:
        parts.append(f"name={urllib.parse.quote(name)}")
    if sa_year:
        parts.append(f"year={sa_year}")
    if sa_ser:
        parts.append(f"sa={sa_ser}")
    return base + ("#" + "&".join(parts) if parts else "")


def parse_court_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """법원경매 검색 응답 1건을 우리 prop dict 포맷으로.
    부동산(토지·건물)이 아니면 None 반환 → 호출자가 skip.
    """
    # ★ 차량(lclsUtilCd=30000)·기타(40000) 안전망 (2026-06-03 사용자 보고: 차량 매물 노출).
    #   검색 단계에서 USG_LCL_TARGET=['10000','20000']로 명시해도 만약 섞여 들어오면 컷.
    lcls = row.get("lclsUtilCd") or ""
    if lcls and lcls not in ("10000", "20000"):
        return None

    sa_no = row.get("srnSaNo") or ""           # '2023타경6292'
    mokmul_ser = row.get("mokmulSer") or "1"
    cltr_no = f"{sa_no}-{mokmul_ser}" if sa_no else (row.get("docid") or "")
    address_jibun, address_road = _build_address(row)
    bld_area = _format_area(row.get("minArea"))

    title_parts = [
        address_jibun,
        row.get("buldNm") or "",
        row.get("buldList") or "",
    ]
    title = " ".join(p for p in title_parts if p).strip() or sa_no

    cat = _category_label(row)
    share_yn = _is_share(row, title)

    return {
        "source": "court",
        "cltr_no": cltr_no,
        "pbct_no": None,
        "pbct_cdtn_no": None,
        "onbid_pbanc_no": None,
        "court_case_no": sa_no,
        "court_office_cd": row.get("boCd") or row.get("cortOfcCd"),
        "court_office_nm": row.get("jiwonNm"),
        "court_item_seq": _format_int(row.get("maemulSer")),
        "title": title,
        "address_jibun": address_jibun,
        "address_road": address_road,
        "category": cat,
        "bid_method": "기일입찰" if (row.get("ipchalGbncd") == "000331") else None,
        "min_price": _format_price(row.get("minmaePrice")),
        "appraisal_price": _format_price(row.get("gamevalAmt")),
        "area_build_m2": bld_area,
        "share_yn": share_yn,
        "fail_count": _format_int(row.get("yuchalCnt")),
        "bid_start": _format_ymd(row.get("maeGiil")),
        "bid_end": _format_ymd(row.get("maeGiil")),  # 기일입찰은 시작=마감
        "status": "진행중" if row.get("mulJinYn") == "Y" else "기타",
        # 좌표 — court 응답은 미상 TM이라 신뢰 못 함. backfill_geo가 Kakao로 채움.
        "geo_lat": None,
        "geo_lng": None,
        "building_name": row.get("buldNm") or None,
        "cltr_mnmt_no": sa_no,
        # mulBigo는 danger.py·analyze_rights.py가 활용하도록 detail_json에 노출
        "detail_json": {
            "비고": row.get("mulBigo") or "",
            "물건구분": row.get("mokGbncd") or "",
            "법원": row.get("jiwonNm") or "",
            "담당계": row.get("jpDeptNm") or "",
            "전화": row.get("tel") or "",
            "매각장소": row.get("maePlace") or "",
        },
        # 법원경매정보는 WebSquare SPA라 상세(PGJ153F00)가 POST로만 로드된다.
        # docId GET 딥링크는 세션이 없으면 튕긴다 → 공유 가능한 상세 URL 없음.
        # 물건상세검색(PGJ151F00) 진입점 + 법원/연도/사건번호 query params 시도.
        # WebSquare가 받아들이지 않으면 빈 폼이 뜨지만 카드에 사건번호 노출 → 수동 입력 가능.
        "source_url": _build_source_url(row, sa_no),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "raw_row": row,
    }
