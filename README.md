# Onbid 공매 — 맞춤 물건 브라우저

[온비드 조건검색](https://www.onbid.co.kr/op/cltrpbancinf/cltr/cltrcdtnsrch/CltrCdtnSrchController/mvmnCltrCdtnSrchClg.do) 기반 Playwright 스크래퍼 + 송파/강남 선릉역 인근 후처리 필터 + React UI + FastAPI 백엔드.

매물 1건당:
- **건축물대장**으로 지상층수·엘리베이터·사용승인일·도로명주소
- **ODsay 대중교통 API**로 출퇴근 시간 + 경로 요약 (지하철/버스/환승)
- **Kakao Local API**로 정확한 좌표
- **Naver Maps**으로 지도 마커
- **국토부 실거래가 5종**으로 시세 검증 (매매 중앙값/최저~최고, 같은 단지·면적·층 우선)
- **국토부 오피스텔 전월세**로 임대 수익률 추정 (보증금 차감 후 연 수익률)
- **온비드 사진 다건**(atchSn 2~6) — 갤러리 + lightbox 큰 사진(CLG)
- **온비드 상세 페이지 자동 fetch** — `fn_goCltrDetail()` POST 우회로 면적정보 표 파싱 (건물지분 자동 분류)
- 카테고리별 지역 분기 + 매물별 유찰 cap 분기 등 다중 후처리 필터

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
#   DATA_GO_KR_API_KEY      — data.go.kr 마스터 키 (건축물대장 + 실거래가 5종 모두 통과)
#   ODSAY_API_KEY           — 대중교통 경로 (lib.odsay.com)
# 옵션:
#   ONBID_USER / ONBID_PASS — 향후 상세 페이지 fetch 통합 시 사용

# web/.env (Naver Maps JS 키)
copy web\.env.example web\.env
# VITE_NAVER_MAP_CLIENT_ID — NCP > AI·NAVER API > Maps Application > Client ID
```

## 실행

### 한 번에 기동 (권장) — `start-all.ps1`

매물 수집 + 백필(건축물대장·ODsay·**국토부 실거래가 시세**) + 백엔드·프론트·Cloudflare 터널을 **백그라운드(숨김)로 한 번에** 기동:

```powershell
# 수집(max-pages 10) + backfill_all + backfill_realprice(시세) + 서버 3종 + Discord 알림
powershell -ExecutionPolicy Bypass -File .\start-all.ps1

# 수집 건너뛰고 서버만 (이미 DB 채워져 있을 때)
powershell -ExecutionPolicy Bypass -File .\start-all.ps1 -SkipScrape

# 종료 (3개 서비스 + 자식 프로세스 트리 모두 kill)
powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
```

- 실행 후 콘솔에 외부 접속 URL(`*.trycloudflare.com`) 자동 표시 + 클립보드 복사
- **수집+백필 완료 시 Discord 웹훅 알림** 자동 전송 (소요 시간 + 매물 수·시세·카테고리 요약). `.env`의 `DISCORD_WEBHOOK` 설정 시
- 로그: `.backend.log` / `.frontend.log` / `.cloudflared.log`
- PID: `.run-pids.txt` (stop-all.ps1이 이걸 읽어 종료)
- cloudflared는 `%USERPROFILE%\cloudflared.exe`에 설치돼 있어야 함

### 수동 기동 (단계별)

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

- **검색 키워드**: 서울 25개 자치구 + **전국 16개 시도**(토지/도로 전용) 키워드 반복 호출 (`srchArrayRgn`이 무시되는 이슈 우회). 페이지당 **100건**(`page_unit`) × max-pages로 누락 최소화
- **온비드 검색폼**: 부동산·매각·전자입찰·일반경쟁·최저 ≤3억·**건물 ≥23㎡**·입찰기간 90일·**유찰 0~5회**(검색 단계부터 좁힘 — `srchUsbdNftBgng/End` 둘 다 전송)
- **용도 코드**: 주거용건물(0007) + 용도복합용건물(0005) + 토지(0001) 모두 수집 — UI 탭으로 분류
- **용도 화이트리스트** (post-filter):
  - **주거용건물 7종**만: 아파트·주상복합·빌라·단독주택·다세대주택·도시형생활주택·전원주택 (다가구·연립·기타주거용 등 제외)
  - **토지 14종**만: 대지·전·답·임야·잡종지·창고용지·주차장·주택부지·기타토지·공장용지·과수원·목장용지·초지·도로 (학교·종교·철도용지 등 제외)
  - 오피스텔·용도복합은 화이트리스트 우회 (별도 지역 분기)
- **카테고리별 지역 분기**:
  - **오피스텔/용도복합** → 2개 영역: **쪈**(송파 7동 + 강남 7동 + 선릉 3km) **OR** **쪠**(영등포구 + 서대문역 8km) — 둘 중 하나면 통과. 영역별 직장(선릉/서대문역) 기준 ODsay 30분
  - **주거/주거지분** → 서울 전체
  - **토지/도로** → 전국 (소액 토지는 지방 집중)
- **유찰 cap**: 모든 용도 **≤5회** 통일
- **가격 cap**: 단독 건물 ≤3억 / 주거 지분 ≤5천만 / 토지·도로 ≤1천만. **최저가·감정가 둘 다 비공개면 제외**
- **지하층 제외**: 제목 또는 상세(위치/이용현황)에 '지하층' 표기 시 제외 (정규식으로 '지하철' 오매칭 회피)
- **Post-filter**: 입찰 마감 제외, 입찰 시작 지난 매물 UI 숨김, 상가용및업무용 제외
- **지분 비율**: 면적정보 표 비고에서 추출 (10분의9 → 90%, 1분의1은 단독). `building_share_ratio` 컬럼
- **지오코딩**: Kakao address → Kakao keyword → Nominatim → 동 중심 폴백
- **상세 페이지 fetch**: 검색 페이지의 `fn_goCltrDetail()` JS 함수를 `page.evaluate`로 호출 — POST submit으로 detail HTML(792KB+) 정상 수신 후 면적정보 표 파싱 (PC table + 모바일 `.op_mobile_tbl01 ul li.col_item` 양쪽 지원)
- **건축물대장 보강**: 지상층수, 엘리베이터 대수, 사용승인일, 도로명주소 자동 수집

## 주요 UI 기능 (목록 / 상세 페이지)

### 목록 페이지
- **탭 5개** — 용도복합·오피스텔 **쪈**(송파·강남) / **쪠**(영등포·서대문역) / 주거 / 주거 지분 / 토지. 쪈/쪠는 원형 배지로 구분 (쪈 연보라·쪠 하늘색), 기본 탭은 쪈
- **좌측 sticky 지도** (Naver Maps) — 매물별 번호 마커, 카드 hover 시 빨강·확대 활성화, **마커 클릭 시 우측 카드로 부드러운 스크롤**
- **카드 표** — 용도(+지분%) / 최저가 / 감정가 / 건물면적(평) / 층수 / 건물 연식 / 입찰일 (D-day) / 직장까지(오피스텔은 목적지 라벨: 쪈 선릉역·쪠 서대문역)
- **필터 바 (2줄)** — 1줄: 즐겨찾기 / 지역 / 최저가 / 연식 / 층수 / 용도 상세 / **임차인 인수**(위험 유·무) + 유찰 ≤ N · 총 건수(우측). 2줄: 정렬 토글(우측)
- **정렬 토글** — 최저가 / 건물면적 / 직장까지 / 입찰 시작 / 유찰횟수 (각각 오름·내림 토글, 화살표 표시)
- **자동 제외** — 입찰 시작이 이미 지난 매물(D+1 이상)은 목록·탭 카운트에서 숨김
- **카드 우측 별 ★** — 즐겨찾기 토글 (localStorage, 카드 클릭 navigation과 분리)
- **태그 색상 구분** — 강남(파랑) / 송파(보라) / 엘리베이터 있음(녹색) / caution(노랑), 초기화 버튼 연한 빨강

### 상세 페이지
- **헤더** — 용도·입찰방식 (좌), 즐겨찾기 + 상태 칩 (우)
- **사진 갤러리** — 다건 썸네일(ELGM 20KB) + 좌우 nav, 클릭 시 lightbox 큰 사진(CLG ~300KB) + ESC/화살표 키
- **KPI 4개** — 최저입찰가(강조), 감정가, 할인율 (자동 계산), 유찰 횟수
- **2단 레이아웃** — 좌측 정보 섹션, 우측 sticky 지도
- **기본 정보** — 소재지(지번/도로명), 용도, 건물면적(평), 층수, 사용승인일(+연식+카테고리 칩), 입찰방식, 지분 여부, 물건관리번호
- **입찰 일정** — 입찰 시작/마감 (D-day 칩 부착), 상태, 유찰, **입찰 보증금** (최저가 10% 자동 계산)
- **직장 접근성** — 대중교통/도보 시간, 환승 경로 요약 ("버스 341" / "지하철 2호선 → 분당선 (환승 1회)"), 직선거리
- **시세 검증** — 국토부 실거래가 기반 중앙값·최저~최고, 우리 매물 vs 시세 ±% (저렴/근접/상회), SVG 가로 막대 차트, 거래 샘플 표(당해연도 전체 스크롤·최저 녹색/최고 빨강·**같은 단지+면적+층 매칭은 bold**)
- **예상 임대 수익률** — 오피스텔 전월세 12개월, 월세 중앙값 × 12 ÷ (매수가 − 평균 보증금), 5%↑ 녹색 / 3~5% 호박 / 3%↓ 빨강
- **외부 시세 링크** — KB부동산·네이버 부동산 단지/매물 검색 (`building_name` prefill)
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
  backfill_realprice.py 국토부 실거래가(시세) 백필
  backfill_analysis.py  권리분석·낙찰가 예측 백필 (#9/#10)
  notify_discord.py   재수집 완료 Discord 웹훅 알림
  notify_dday.py      입찰 D-day 임박 매물 Discord 알림 (#3)
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
| **data.go.kr 마스터 키** | https://www.data.go.kr | 1만건/일/데이터셋 | 8종 데이터셋 동시 사용 (단일 키) |
| ├ 건축물대장 표제부 | `15044713` | | 지상층수·엘리베이터·도로명·사용승인일 |
| ├ 아파트 매매 실거래가 + 상세 | | | 단지명/면적/층 포함 시세 |
| ├ 연립다세대·단독다가구·토지 | | | 매물 카테고리별 시세 보강 |
| ├ 오피스텔 매매 실거래가 | | | 우리 매물 핵심 시세 |
| └ 오피스텔 전월세 실거래가 | | | 임대 수익률 계산 |
| **ODsay 대중교통** | https://lib.odsay.com | 5천건/일 | 환승 최적 경로·시간 |
| **Naver Maps NCP** | https://console.ncloud.com → AI·NAVER API > Maps | 응용에 따라 다름 | 지도 JS SDK (`ncpClientId`) |

## 외부에서 접속 (Cloudflare Tunnel)

> **가장 쉬운 방법**: `start-all.ps1` 실행 — 서버 3종 + 터널을 백그라운드로 띄우고 URL을 자동 출력/클립보드 복사 ([실행](#한-번에-기동-권장--start-allps1) 참고).

수동으로 하려면, 로컬 dev 서버를 외부 URL로 노출하려면 [cloudflared](https://github.com/cloudflare/cloudflared/releases/latest)를 설치 후:

```powershell
# 임시 URL (TryCloudflare, 도메인 불필요)
cloudflared tunnel --url http://localhost:5173
# → https://xxx-xxx-xxx.trycloudflare.com 발급 (cloudflared 재시작 시 변경됨)

# 고정 도메인 (Cloudflare에서 .com 구매 ~₩13,500/년)
cloudflared tunnel login
cloudflared tunnel create auction-app
cloudflared tunnel route dns auction-app auction.yourdomain.com
cloudflared tunnel run auction-app
```

[`web/vite.config.ts`](web/vite.config.ts)에 `host: true` + `allowedHosts: [".trycloudflare.com", ".cfargotunnel.com"]` 적용됨 — Vite는 그대로 사용.

**Naver Maps NCP 주의**: NCP는 hostname 와일드카드 미지원이라 매번 URL이 바뀌면 콘솔에 재등록 필요. 고정 도메인 사용 권장.

## 알려진 한계

- **온비드 상세 페이지 직접 GET 차단** — `mvmnCltrDtl.do`는 외부 직접 접근 시 에러 페이지(2558 byte) 반환. **검색 페이지의 `fn_goCltrDetail()` JS 함수를 `page.evaluate`로 호출하면 POST submit으로 정상 페이지(792KB+) 수신 가능** ([scraper/detail.py](scraper/detail.py)).
- **온비드 검색폼 일부 필터가 서버에서 무시됨** — `srchArrayRgn`(지역), `srchShrYn`(지분 여부), `srch_prpt_types` 세부 카테고리는 서버 응답에 적용 X. 우회: 25개 자치구 키워드 반복 호출 + post-filter로 카테고리/지분 분류.
- Naver Maps Client ID 미설정 시 OSM iframe 폴백.
- 외부 API 키 미설정 시 각각 휴리스틱 폴백:
  - Kakao 키 없음 → Nominatim → 동 중심 폴백
  - ODsay 키 없음 → 가까운 역 + 직선거리 환산
  - 건축물대장 키 없음 → 층수 unknown (제목에서 현재 층만 추출)

## 로드맵 — 유료 빅3(지지옥션·두인경매·스피드옥션) 갭 분석 기반

> 2026-05 조사: 3사 공통 제공 기능 중 우리 앱에 없는 갭 10개. 우선순위는 도입 난이도·차별 가치 기준.

- [ ] **#1 역세권 검색** (지하철역 반경/도보권/노선) — 3/3, 난이도 중
- [ ] **#2 법원·처분기관·매각기일 필터 + 오늘 신건/마감 임박 빠른 진입** — 3/3, 난이도 하
- [x] **#3 매물 캘린더 뷰 + D-day Discord 푸시 알림** — 3/3, 난이도 중 *(2026-05-29 구현 — Task Scheduler 일일 등록 권장)*
- [x] **#4 낙찰 통계 대시보드** (현재 매물 기반 할인율·예측 낙찰가율) — 2/3, 난이도 중 *(2026-05-29 구현 — 실 낙찰가 시계열은 온비드 낙찰결과 별도 수집 필요)*
- [x] **#5 특수권리 태깅 보강** (지분/유치권/법정지상권/분묘기지권/대항력 임차인/NPL) — 3/3, 난이도 중 *(2026-05-29 구현)*
- [ ] **#6 추천/인기 매물 큐레이션** (조회수·테마 큐레이션) — 2/3, 난이도 하
- [ ] **#7 사건번호/물건관리번호 직접 검색 진입점** — 3/3, 난이도 하
- [x] **#8 모의입찰 시뮬레이션** (보증금·취득세·명도비·총비용·시세비) — 2/3, 난이도 하 *(2026-05-29 구현)*
- [x] **#9 권리분석 자동 판정** (말소기준권리 + 말소/인수 자동) — 3/3, 난이도 상 *(2026-05-29 휴리스틱 구현)*
- [x] **#10 낙찰가 예측** (유찰 회차별 잔존가율 + 시세 보정) — 1/3, 난이도 상 *(2026-05-29 통계 휴리스틱 구현)*

## 참고 문서

- [`docs/TODO.md`](docs/TODO.md) — 진행 중/예정 작업
- [`docs/onbid-endpoints.md`](docs/onbid-endpoints.md) — 리버스 엔지니어링 결과
- [`docs/probe-results.json`](docs/probe-results.json) — 샘플 응답
- [`docs/probe-request.json`](docs/probe-request.json) — 샘플 POST 페이로드

## 운영 주의사항

- 온비드 약관 준수 — 요청 간격 ≥ 1.5초 유지 (`criteria.yaml` `request_delay_sec`)
- 비상업적 개인 리서치 용도 한정
- `.env`의 API 키는 절대 커밋 금지 (`.gitignore`로 보호됨)
