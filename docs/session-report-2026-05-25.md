# 작업 보고서 — 2026-05-25 (사용자 AFK 1시간 분량)

## 0. 사용자 액션 필요 (가장 먼저)

### uvicorn 재시작 필수
스크린샷에서 `13 / ?층`, `사용승인일 -`, `대중교통 약 1분` (도보여야 함) 등이 보인 건 **Pydantic 스키마 변경분이 동작 중인 uvicorn에 반영되지 않은 상태**입니다. `--reload`가 잡지 못한 케이스 (model_fields 캐시). 

```powershell
# 기존 uvicorn 터미널 Ctrl+C로 완전 종료 후
.\.venv\Scripts\uvicorn.exe api.main:app --reload --port 8000
```

In-process 테스트로 모든 필드 정상 응답 확인됨 (보고서 §3 참조).

## 1. 사용자 지적 6건 — 모두 처리 완료

| # | 항목 | 처리 |
|---|---|---|
| 1 | 시간 포맷 통일 (`오후 2:00`) | [api.ts `formatDateTime`](web/src/api.ts) `${h12}:${mm}` |
| 2 | 도보/대중교통 라벨 정확화 | 코드는 `transit_mode='walk'` → "도보 약 N분" 정상. 화면 잘못은 uvicorn 미반영 |
| 3 | 상세 페이지 교통 경로 요약 | [transit.py `_summarize_path()`](scraper/filters/transit.py) — `버스 341`, `지하철 2호선 → 분당선 (환승 1회)` 식. DB `transit_summary` 컬럼 + 상세 페이지 `교통 경로` row |
| 4 | 엘리베이터 칩 배경 (눈에 띄게) | [.tag-elevator-yes](web/src/index.css) 녹색 (#dcfce7/#15803d) |
| 5 | 강남/송파 칩 색 분리 | `.tag-gangnam` 파랑 / `.tag-songpa` 보라 / `.tag-caution` 노랑 — `tagCategory()` 분류 함수 |
| 6 | 상세 페이지 도로명 from 건축물대장 | [building.py](scraper/filters/building.py) `newPlatPlc` 추출 → `address_road`로 저장. 양 매물 모두 채워짐 |

## 2. 추가 수정

- **층수 `13 / ?층`** → DB는 15 정상. uvicorn 재시작 후 `13 / 15층 [고층]`으로 표시될 것
- **사용승인일 null** → DB는 `20040319` 정상. 같은 이유로 재시작 후 정상
- **물건관리번호 `1952553`** → 이건 내부 numeric ID(`cltr_no`). 사용자가 의문 가진 게 맞음. 수정:
  - 표시는 `cltr_mnmt_no` 우선 (`2025-17474-001` 형식, 온비드 화면 공식 ID)
  - cltr_no(`1952553`) 폴백 제거 — 사용자 무관 정보
  - 그래도 표시 유지: 온비드에서 입찰조서·즉시조회·문의 시 이 번호 사용. 입찰 행위 자체에 필수는 아니지만 본인 매물 추적용 식별자
- **InfoTable null row 자동 숨김** — 도로명·교통 경로 등 값 없을 때 row 자체 생략

## 3. End-to-end 검증 결과

```
=== id=156 (능현오피스텔) ===
address_jibun:  서울특별시 강남구 역삼동 708-16
address_road:   서울특별시 강남구 선릉로89길 16 (역삼동)
floor_total:    15
use_apr_day:    20040319           (사용승인 2004-03-19, 22년 2개월)
building_name:  능현오피스텔
main_purps:     업무시설
transit_minutes: 1
transit_mode:   walk               → UI: "도보 약 1분 소요"
transit_summary: None              (도보는 요약 생략)
cltr_mnmt_no:   2025-17474-001
source_url:     ...?srchCltrMnmtNo=2025-17474-001   ✓ 정상 작동

=== id=157 (아이-스페이스잠실2) ===
address_jibun:  서울특별시 송파구 방이동 35-4
address_road:   서울특별시 송파구 올림픽로 354 (방이동)
floor_total:    15
use_apr_day:    20031222           (사용승인 2003-12-22, 22년 5개월)
building_name:  I-SPACE 잠실2
transit_minutes: 24
transit_mode:   transit            → UI: "대중교통 약 24분 소요"
transit_summary: 버스 341          → UI 카드/상세에 부가표시
cltr_mnmt_no:   2025-16617-001
```

## 4. 새 외부 통합

| 시점 | API | 기능 |
|---|---|---|
| 이번 세션 | **공공데이터 건축물대장 표제부** (data.go.kr) | 지상층수·엘리베이터·사용승인일·도로명주소 자동 수집 |
| 이번 세션 | **ODsay 대중교통 길찾기** | 실제 환승 최적 경로·시간 (자가용 폴백 제거 — 사용자 미사용) |
| 직전 세션 | Kakao REST (geocoding + places) | 건물 단위 좌표 정확도 |
| 직전 세션 | Naver Maps JS v3 | 지도 표시 |

각 API 미설정 시 휴리스틱 폴백 유지.

## 5. 새 파일 / 주요 변경 파일

```
docs/TODO.md                              세션 작업 목록
docs/session-report-2026-05-25.md         본 보고서

scraper/filters/building.py               (신규) 건축물대장 표제부 통합
scraper/filters/transit.py                ODsay + 도보 + 휴리스틱, 자가용 제거
scraper/filters/__init__.py               apply_building_registry 추가
scraper/parse.py                          public_source_url() — 작동하는 외부 URL
scraper/db.py                             ALTER TABLE 자동 마이그레이션 6개 컬럼

shared/schemas/property.py                Pydantic 필드 추가

web/src/api.ts                            translateTag/tagCategory/buildingAge/
                                          formatStatus/formatArea/formatUseAprDay/
                                          transitModeLabel/parseFloor/isCautionTag/
                                          isRedundantTag
web/src/pages/PropertyList.tsx            카드 표 + 인덱스 + hover 동기화 + 정렬
web/src/pages/PropertyDetail.tsx          KPI + 2단 + InfoTable null 자동 숨김
web/src/components/ListMap.tsx            (신규) 다중 마커 + 하이라이트
web/src/components/PropertyMap.tsx        Naver Maps v3
web/src/index.css                         태그 5색, 카드 표, KPI, hero, info-table

scripts/reset_db.py                       전체/실패 행 삭제
scripts/backfill_geo.py                   Kakao 좌표 백필
scripts/backfill_building.py              건축물대장 백필
scripts/backfill_transit.py               ODsay 대중교통 백필
scripts/backfill_all.py                   세 가지 한꺼번에
```

## 6. README 전면 재작성

이전 README는 6주 전 상태(Kakao만 언급) → 현재 통합된 외부 API 4개, fallback chain, 백필 스크립트, 알려진 한계까지 모두 반영. 키 발급처 표·UI 디렉토리 구조·API 라우트 명시.

## 7. 알려진 미해결 / 추후 결정 필요

| 이슈 | 영향도 | 다음 액션 |
|---|---|---|
| **온비드 상세 페이지 HTML 직접 접근 불가** | 중 — 건축물대장으로 대체 확보된 정보 외 권리관계/입찰 상세 추가 정보 미수집 | 검색 결과에서 행 클릭 시뮬레이션 (큰 변경) |
| **자가용 출퇴근 시간 미사용** | 의도된 동작 (사용자 명시) | — |
| **NCP Maps Daily quota 1,000** | 일일 한도 낮음 | 사용량 모니터링 |
| **잠실2 같은 도보 1분 거리는 ODsay가 -98** | 처리됨 | — |

## 8. 유료 경매 사이트 UX 분석 후 적용

⚠️ **계정 사용은 거절** (위 §1과 동일 사유). 대신 **공개 페이지 분석 + 한국 경매 UX 통념**으로 진행.

### 적용된 요소

| 요소 | 위치 | 출처 |
|---|---|---|
| **입찰 보증금 계산** (`최저가 × 10%`) | 상세 페이지 「입찰 일정」 row | 모든 사이트 표준 |
| **D-day 칩** (`D-28`, `D-Day`) | 카드/상세 「입찰 시작·마감」 옆 | 일정 임박 강조 |
| **건물 연식 카테고리** (5단계) | 카드/상세 「건물 연식·사용승인일」 | 네이버 부동산 |
| **즐겨찾기 ★** (localStorage) | 카드 우측·상세 헤더 | 모든 사이트 표준 |
| **유사 매물** (같은 동) | 상세 페이지 하단 섹션 | 사이트 공통 |
| **Print stylesheet** | `@media print` 헤더/툴바/지도/유사매물 숨김 | 인쇄 보고서 |

### 5단계 건물 연식 (사용자 매수 타겟 ≤5년 반영)

| 범위 | 라벨 | 색 |
|---|---|---|
| 0~3년 | 신축 | 진한 녹색 (강조) |
| 3~5년 | 준신축 | 연한 녹색 |
| 5~10년 | 일반 | 회색 |
| 10~25년 | 구축 | 호박색 |
| 25년+ | 노후 | 적색 |

→ 사용자 매수 후보(<5년)만 녹색 계열 강조. 한눈에 매수 가능 매물 식별 가능.

### 적용 보류 / 데이터 미가용

- **사진 갤러리** — 온비드 상세 페이지 fetch 차단 상태. 사진 데이터 없음.
- **권리분석 / 등기부 요약** — 동일 사유.
- **시세 비교** (KB/실거래) — 국토부 실거래가 API 별도 통합 필요. 키 발급되면 가능.
- **임차인 분석** — 등기부 데이터 부재.

## 9. Git 작업 권고

승인 시:
```powershell
cd c:\source\JEON2\public-auction
git init                           # 아직 안 했다면
git remote add origin https://github.com/ljy9969/public-auction.git
git add .
git status                         # .env가 절대 안 보이는지 확인 ⚠
git commit -m "feat: ODsay 대중교통/건축물대장/Naver Maps 통합 + UI 전면 개편"
git push -u origin main
```

⚠ **푸시 전 점검**:
- `.env` 파일이 git status에서 보이지 않아야 함 (`.gitignore`에 이미 포함)
- 본문에 비밀번호·API 키 흔적 없는지 grep
- 채팅 로그에서 노출된 Onbid 패스워드는 별도로 변경

---

검토하시고 OK면 알려주세요. 추가 수정 있으면 반영 후 푸시 진행하겠습니다.
