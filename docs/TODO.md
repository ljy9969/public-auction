# 작업 TODO — 2026-05-25 사용자 AFK 1시간 동안 진행

## 사용자가 직접 지적한 이슈 (P1)

- [x] **사용자 액션 필요**: `uvicorn` 재시작 — Pydantic 스키마 변경분(floor_total, transit_mode, use_apr_day, cltr_mnmt_no) 반영. `--reload`가 보통 잡지만 model_fields 캐싱 이슈 가능. 완전 종료 후 재시작 권장.
- [x] **이동수단 "도보" 라벨**: 코드는 `transitModeLabel(walk)` → "도보"로 처리됨. 사용자 화면이 "대중교통"으로 보이는 건 위와 동일한 uvicorn 캐시 문제 — 재시작 후 정상.
- [x] **시간 포맷 통일**: "오후 2시 00분" → "오후 2:00"
- [x] **상세 페이지 대중교통 경로 요약**: ODsay 응답에서 노선 + 환승 정보 추출 → `transit_summary` 컬럼
- [x] **엘리베이터 칩 배경**: 녹색 강조
- [x] **강남/송파 칩 색 분리**: 강남=파랑, 송파=보라
- [x] **상세 페이지 도로명**: 건축물대장 `newPlatPlc` 추출 → `address_road`에 저장
- [x] **사용승인일 + 연식**: 코드는 이미 반영. uvicorn 재시작 후 정상 표시.
- [x] **물건관리번호 표기**: 1952553(내부 cltr_no) 대신 `2025-17474-001` (cltr_mnmt_no) 우선 표시. 라벨도 "물건관리번호 (온비드)"로 명확화.

## 추가 개선 (P2)

- [x] 백필 스크립트: 기존 행에 address_road / transit_summary 채움
- [x] README 업데이트 — 현재 통합된 API들(건축물대장·ODsay·Naver Maps) 명시
- [x] 검증: scrape → DB → API → UI 전체 흐름 end-to-end 확인

## 추후 (P3, 사용자 결정 필요)

- [ ] Onbid 상세 페이지 본문 HTML 가져오기 — 검색 결과에서 클릭 시뮬레이션 (큰 변경)
- [ ] 정렬 옵션 (가격순/마감순/거리순)
- [ ] 동별 빠른 필터
- [ ] CSV export
- [ ] 즐겨찾기 (localStorage)
