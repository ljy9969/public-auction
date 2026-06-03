// ==UserScript==
// @name         BidPick · 법원경매 prefill
// @namespace    https://github.com/ljy9969/public-auction
// @version      1.0.0
// @description  BidPick 카드 링크의 URL hash(#cort=...&year=...&sa=...)를 읽어 법원경매정보 물건상세검색 폼을 자동으로 채우고 검색 버튼 클릭
// @match        https://www.courtauction.go.kr/pgj/index.on*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  // 물건상세검색(PGJ151F00) 페이지일 때만 동작 — 다른 메뉴 무시
  if (!location.search.includes("PGJ151F00")) return;

  // URL hash 파싱: #cort=B000214&year=2025&sa=3671
  const params = new URLSearchParams(location.hash.slice(1));
  const cort = params.get("cort");
  const year = params.get("year");
  const sa = params.get("sa");
  if (!cort && !year && !sa) return;

  // WebSquare 입력 필드 ID (사용자 제공 XPath에서 추출)
  const ID = {
    cort: "mf_wfm_mainFrame_sbx_rletCortOfc",   // 법원 select
    year: "mf_wfm_mainFrame_sbx_rletCsYear",    // 사건번호 연도 select
    sa: "mf_wfm_mainFrame_ibx_rletCsNo",        // 타경 번호 input
  };

  // WebSquare는 .value 만 바꿔도 model 바인딩이 안 됨 → input/change 이벤트 강제 발사
  function setAndFire(el, value) {
    if (!el) return false;
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    // 일부 WebSquare 버전은 jQuery 이벤트도 요구
    if (window.jQuery) window.jQuery(el).trigger("change");
    return true;
  }

  function findSearchButton() {
    // 1순위: type=button + value="검색"
    const inputs = document.querySelectorAll('input[type="button"]');
    for (const b of inputs) {
      if ((b.value || "").trim() === "검색") return b;
    }
    // 2순위: button > "검색"
    const buttons = document.querySelectorAll("button");
    for (const b of buttons) {
      if ((b.textContent || "").trim() === "검색") return b;
    }
    return null;
  }

  function tryFill(retries) {
    const elCort = document.getElementById(ID.cort);
    const elYear = document.getElementById(ID.year);
    const elSa = document.getElementById(ID.sa);

    // WebSquare가 lazy 로딩 — 폼이 아직 안 그려졌으면 잠깐 기다림
    if (!elCort || !elYear || !elSa) {
      if (retries > 0) {
        setTimeout(() => tryFill(retries - 1), 300);
      } else {
        console.warn("[BidPick] court prefill: form elements not found after retries");
      }
      return;
    }

    let touched = 0;
    if (cort && setAndFire(elCort, cort)) touched++;
    if (year && setAndFire(elYear, year)) touched++;
    if (sa && setAndFire(elSa, sa)) touched++;
    console.log(`[BidPick] court prefill: ${touched}개 필드 채움 (cort=${cort} year=${year} sa=${sa})`);

    // 잠시 후 검색 버튼 클릭 — WebSquare가 model 반영할 시간 줌
    setTimeout(() => {
      const btn = findSearchButton();
      if (btn) {
        btn.click();
        console.log("[BidPick] court prefill: 검색 버튼 클릭");
      } else {
        console.warn("[BidPick] court prefill: 검색 버튼 못 찾음 — 수동 클릭 필요");
      }
    }, 600);
  }

  // DOM ready 직후엔 WebSquare가 아직 폼 안 그려져 있을 수 있음 — 9초까지 대기 (300ms × 30)
  tryFill(30);
})();
