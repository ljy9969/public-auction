# Onbid 공매 — 맞춤 물건 브라우저

[온비드 조건검색](https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrcdtnsrch/CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do) 기반 Playwright 스크래퍼 + 송파/강남 선릉역 인근 후처리 필터 + React UI + FastAPI 백엔드.

매물 1건당:
- **건축물대장**으로 지상층수·엘리베이터·사용승인일·도로명주소
- **ODsay 대중교통 API**로 출퇴근 시간 + 경로 요약 (지하철/버스/환승)
- **Kakao Local API**로 정확한 좌표
- **Naver Maps**으로 지도 마커
- 송파/강남 화이트리스트 + 선릉 3km + 건물지분 차단 등 다중 후처리 필터

## 사전 준비

- Python 3.12+ (`.venv`에서 검증된 환경: 3.14)
- Node.js 20+
- Playwright Chromium

```powershell
cd c:\source\JEON2\public-auction
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\playwright.exe install chromium

# 환경변수 — .env (gitignore에 포함)
copy .env.example .env
# 다음 키들을 .env에 채워야 정확도가 가장 좋아짐:
#   KAKAO_REST_API_KEY      — 주소 → 좌표 (Kakao 개발자센터)
#   BLDG_REGISTRY_API_KEY   — 건축물대장 표제부 (data.go.kr)
#   ODSAY_API_KEY           — 대중교통 경로 (lib.odsay.com)
# 옵션:
#   ONBID_USER / ONBID_PASS — 향후 상세 페이지 fetch 통합 시 사용

# web/.env (Naver Maps JS 키)
copy web\.env.example web\.env
# VITE_NAVER_MAP_CLIENT_ID — NCP > AI·NAVER API > Maps Application > Client ID
```

## 실행

```powershell
# (선택) 기존 DB 초기화
.\.venv\Scripts\python.exe -m scripts.reset_db

# 1) 매물 수집
.\.venv\Scripts\python.exe -m scraper.run --max-pages 3

# 2) (선택) 기존 행에 건축물대장 + ODsay 정보 백필 — 외부 API 추가/변경 후
.\.venv\Scripts\python.exe -m scripts.backfill_all
# 개별:
.\.venv\Scripts\python.exe -m scripts.backfill_geo
.\.venv\Scripts\python.exe -m scripts.backfill_building
.\.venv\Scripts\python.exe -m scripts.backfill_transit

# 3) API 서버
.\.venv\Scripts\uvicorn.exe api.main:app --reload --port 8000

# 4) Web (별도 터미널)
cd web
npm install
npm run dev
```

http://localhost:5173 — Vite dev 서버가 `/api` → port 8000 프록시.

## 매물 선별 기준

`scraper/config/criteria.yaml`:

- **지역**: 송파 7동(잠실본·삼전·석촌·송파1·방이2·**방이·송파**) + 강남 화이트리스트(삼성/대치/역삼/논현/청담/압구정/신사) 선릉 3km 이내
- **출퇴근**: ≤ 30분 (선릉로 433, **ODsay 대중교통** 우선 → 도보 10분 이내 → 휴리스틱). 자가용은 출퇴근에 사용 안 함 — Kakao Mobility 폴백 제거.
- **지오코딩**: Kakao address → Kakao keyword → Nominatim → 동 중심 폴백
- **상세 페이지 지도**: Naver Maps (키 있을 때) / OSM iframe (키 없을 때)
- **온비드 검색폼**: 부동산·매각·전자입찰·일반경쟁·최저 ≤3억·건물 ≥24㎡·입찰기간 90일
- **용도 코드**: 주거용(0007), 용도복합·오피스텔(0005) — 상가/업무 제외
- **Post-filter**: 토지만 제외, 유찰 ≤3, 입찰 마감 제외, 카테고리 제외(상가용및업무용), 건물 지분 차단(토지지분 OK), 제목 키워드(지분매각·공유지분 등)
- **건축물대장 보강**: 지상층수, 엘리베이터 대수, 사용승인일, 도로명주소 자동 수집

## 주요 UI 기능 (목록 / 상세 페이지)

### 목록 페이지
- **좌측 sticky 지도** (Naver Maps) — 매물별 번호 마커, 카드 hover 시 빨강·확대 활성화, 마커 클릭 시 카드 활성화
- **카드 표** — 용도 / 최저가 / 감정가 / 건물면적(평) / 층수 / 건물 연식 / 입찰일 (D-day) / 직장까지 등
- **상단 필터 바** — 즐겨찾기만 / 지역(강남/송파) / 최저가(1·2·3억) / 연식(5·10·20년) / 층수(저/중/고) / 유찰 ≤ N / 초기화
- **카드 우측 별 ★** — 즐겨찾기 토글 (localStorage, 카드 클릭 navigation과 분리)
- **태그 색상 구분** — 강남(파랑) / 송파(보라) / 엘리베이터 있음(녹색) / caution(노랑)

### 상세 페이지
- **헤더** — 용도·입찰방식 (좌), 즐겨찾기 + 상태 칩 (우)
- **KPI 4개** — 최저입찰가(강조), 감정가, 할인율 (자동 계산), 유찰 횟수
- **2단 레이아웃** — 좌측 정보 섹션, 우측 sticky 지도
- **기본 정보** — 소재지(지번/도로명), 용도, 건물면적(평), 층수, 사용승인일(+연식+카테고리 칩), 입찰방식, 지분 여부, 물건관리번호
- **입찰 일정** — 입찰 시작/마감 (D-day 칩 부착), 상태, 유찰, **입찰 보증금** (최저가 10% 자동 계산)
- **직장 접근성** — 대중교통/도보 시간, 환승 경로 요약 ("버스 341" / "지하철 2호선 → 분당선 (환승 1회)"), 직선거리
- **유사 매물** — 같은 법정동 다른 매물 (최대 6개)
- **온비드 원문 보기** — 검색 페이지에 물건관리번호 prefill (직접 mvmnCltrDtl.do 접근은 차단되어 우회)

### 카테고리 칩 (한눈에 매물 평가)
- **층수**: 저/중/고 (건축물대장 `grndFlrCnt` 기반 상대 비율, 미확보 시 절대 휴리스틱)
- **건물 연식** (5단계, 매수 타겟 ≤5년 반영):
  - **신축** (<3년, 강한 녹색) / **준신축** (<5년, 연한 녹색) / 일반 (<10년, 회색) / 구축 (<25년, 호박) / 노후 (25년+, 빨강)
- **D-day**: 입찰 시작/마감일 임박 강조 (D-28 / D-Day / D+3)

### 인쇄
- `@media print { … }` — 헤더·툴바·지도·유사매물 숨김, KPI 흰배경 변환 → A4 보고서로 그대로 출력 가능

### 날짜·면적 포맷
- 날짜: `26/6/22 (월) 오후 2:00` (요일 + 12시간제)
- 면적: `29.65㎡ (8.97평)` (1평 = 3.3058㎡)

## 프로젝트 구조

```text
scraper/
  config/             YAML 설정
  filters/
    region.py         송파/강남 화이트리스트, 선릉 3km
    geo.py            Kakao 지오코딩 + Nominatim 폴백
    transit.py        ODsay 대중교통 + 도보 + 휴리스틱
    quality.py        지분/유찰/카테고리/마감
    building.py       건축물대장 표제부 — 층수/엘리베이터/도로명
    elevator.py       엘리베이터 추출 (raw + 상세 + 등본)
  session.py          Playwright 세션 (검색 + 상세 페이지)
  search.py           조건검색 POST
  parse.py            list/detail HTML 파싱
  detail.py           상세 페이지 fetch (Playwright → httpx 폴백)
  db.py               SQLite + idempotent 마이그레이션
  run.py              CLI 진입점

api/main.py           FastAPI REST
web/src/              React + Vite
shared/schemas/       Pydantic
scripts/
  reset_db.py         DB 전체/실패행만 삭제
  backfill_geo.py     Kakao 좌표 백필
  backfill_building.py 건축물대장 백필
  backfill_transit.py ODsay 대중교통 백필
  backfill_all.py     세 가지 한꺼번에
data/onbid.db         SQLite
docs/                 API notes + TODO
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/properties?passes_only=true` | 매물 목록 |
| GET | `/api/properties/{id}` | 매물 상세 |
| POST | `/api/scrape?max_pages=3` | 백그라운드 수집 시작 |
| GET | `/api/scrape/status` | 수집 진행 상태 |

## 외부 API 키 발급

| API | 발급처 | 무료 한도 | 용도 |
|---|---|---|---|
| **Kakao REST API** | https://developers.kakao.com | 한도 넓음 | 주소→좌표·키워드 검색 |
| **공공데이터 건축물대장** | https://www.data.go.kr/data/15044713/openapi.do | 1만건/일 | 지상층수·엘리베이터·도로명·사용승인일 |
| **ODsay 대중교통** | https://lib.odsay.com | 5천건/일 | 환승 최적 경로·시간 |
| **Naver Maps NCP** | https://console.ncloud.com → AI·NAVER API > Maps | 응용에 따라 다름 | 지도 JS SDK (`ncpKeyId`) |

## 알려진 한계

- **온비드 상세 페이지 HTML 직접 접근 불가** — `mvmnCltrDtl.do`가 외부 직접 접근 시 에러 페이지 반환. "온비드 원문 보기" 버튼은 검색 페이지에 물건관리번호 prefill로 우회. 엘리베이터·층수·도로명은 **건축물대장 API**로 대체 확보.
- Naver Maps Client ID 미설정 시 OSM iframe 폴백.
- 외부 API 키 미설정 시 각각 휴리스틱 폴백:
  - Kakao 키 없음 → Nominatim → 동 중심 폴백
  - ODsay 키 없음 → 가까운 역 + 직선거리 환산
  - 건축물대장 키 없음 → 층수 unknown (제목에서 현재 층만 추출)

## 참고 문서

- [`docs/TODO.md`](docs/TODO.md) — 진행 중/예정 작업
- [`docs/onbid-endpoints.md`](docs/onbid-endpoints.md) — 리버스 엔지니어링 결과
- [`docs/probe-results.json`](docs/probe-results.json) — 샘플 응답
- [`docs/probe-request.json`](docs/probe-request.json) — 샘플 POST 페이로드

## 운영 주의사항

- 온비드 약관 준수 — 요청 간격 ≥ 1.5초 유지 (`criteria.yaml` `request_delay_sec`)
- 비상업적 개인 리서치 용도 한정
- `.env`의 API 키는 절대 커밋 금지 (`.gitignore`로 보호됨)
