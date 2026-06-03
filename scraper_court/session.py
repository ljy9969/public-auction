"""법원경매정보 세션 — httpx + JSESSIONID 확보.

정찰 결과: CSRF 토큰 없음, JSESSIONID 쿠키 + Referer 헤더로 충분.
UA 검증이 있으므로 Chrome UA 명시 필요.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE = "https://www.courtauction.go.kr"
ENTRY_URL = f"{BASE}/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
SEARCH_URL = f"{BASE}/pgj/pgjsearch/searchControllerMain.on"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 정찰에서 응답 헤더에 "ipcheck": true 관측 — IP 모니터링.
# 안전 마진으로 요청 간격 ≥2초, 최대 동시 1세션.
DEFAULT_DELAY = 2.0


class CourtSession:
    """JSESSIONID 보관 httpx.Client wrapper."""

    def __init__(self, delay_sec: float = DEFAULT_DELAY) -> None:
        self.client = httpx.Client(
            base_url=BASE,
            headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Origin": BASE,
                "Referer": ENTRY_URL,
            },
            timeout=20.0,
            follow_redirects=True,
        )
        self.delay_sec = delay_sec
        self._last_post = 0.0
        self._jsessionid: str | None = None

    def warm_up(self) -> None:
        """진입 페이지 GET — JSESSIONID 발급."""
        logger.info("Warming up court session (GET entry)")
        resp = self.client.get(ENTRY_URL)
        resp.raise_for_status()
        cookies = self.client.cookies
        self._jsessionid = cookies.get("JSESSIONID")
        if not self._jsessionid:
            raise RuntimeError("JSESSIONID not received from entry page")
        logger.info("Got JSESSIONID=%s...", self._jsessionid[:10])

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        submission_id: str = "mf_wfm_mainFrame_sbm_selectGdsDtlSrch",
        sc_userid: str = "SYSTEM",
    ) -> dict[str, Any]:
        """검색/상세 컨트롤러 호출 — JSON POST.

        WebSquare가 다음 두 헤더를 검증 (정찰에서 확보):
        - submissionid : WebSquare submission 식별자
        - sc-userid    : 검색은 'SYSTEM', 상세(물건사진)는 'NONUSER' 관측 — 호출부가 지정
        """
        # rate limit
        delta = time.monotonic() - self._last_post
        if delta < self.delay_sec:
            time.sleep(self.delay_sec - delta)

        if not self._jsessionid:
            self.warm_up()

        url = path if path.startswith("http") else f"{BASE}{path}"
        resp = self.client.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json",
                "submissionid": submission_id,
                "sc-userid": sc_userid,
            },
        )
        self._last_post = time.monotonic()
        if resp.status_code >= 400:
            logger.error("HTTP %s response body: %s", resp.status_code, resp.text[:1000])
        resp.raise_for_status()
        # 응답 인코딩은 항상 UTF-8
        data = resp.json()
        # ipcheck=false면 차단 가능성 — 로그 경고
        if isinstance(data.get("data"), dict) and data["data"].get("ipcheck") is False:
            logger.warning("court ipcheck=false at %s (rate limit hit?)", url)
        return data

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "CourtSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
