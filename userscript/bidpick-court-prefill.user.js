// ==UserScript==
// @name         BidPick · 법원경매 prefill
// @namespace    https://github.com/ljy9969/public-auction
// @version      1.3.0
// @description  BidPick 카드 링크의 URL hash(#cort=...&year=...&sa=...)를 읽어 법원경매정보 물건상세검색 폼을 자동으로 채우고 검색 버튼 클릭
// @match        https://www.courtauction.go.kr/pgj/index.on*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  console.log("[BidPick] userscript v1.3.0 loaded on", location.href);

  // 물건상세검색(PGJ151F00) 페이지일 때만 동작 — 다른 메뉴 무시
  if (!location.search.includes("PGJ151F00")) {
    console.log("[BidPick] skip: not PGJ151F00");
    return;
  }

  // URL hash 파싱: #cort=B000250&name=수원지방법원&year=2025&sa=863
  const params = new URLSearchParams(location.hash.slice(1));
  const cort = params.get("cort");
  const cortName = params.get("name");
  const year = params.get("year");
  const sa = params.get("sa");
  console.log("[BidPick] hash params:", { cort, cortName, year, sa });
  if (!cort && !cortName && !year && !sa) {
    console.log("[BidPick] skip: no params");
    return;
  }

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
    if (window.jQuery) window.jQuery(el).trigger("change");
    return true;
  }

  function findSearchButton() {
    const inputs = document.querySelectorAll('input[type="button"]');
    for (const b of inputs) {
      if ((b.value || "").trim() === "검색") return b;
    }
    const buttons = document.querySelectorAll("button");
    for (const b of buttons) {
      if ((b.textContent || "").trim() === "검색") return b;
    }
    return null;
  }

  // select에서 우리가 원하는 option의 실제 value 찾기.
  // 1순위: option.value === code (예 'B000250') — 우리 API 코드와 매칭
  // 2순위: option.text === name (예 '수원지방법원') — 시각 텍스트로 폴백
  //   ★ 2026-06-03: 법원 select의 option value 형식이 API 코드와 다른 사이트라
  //                  text 폴백 없으면 매칭 실패. 한국어명을 hash에 같이 박아 해결.
  function findOptionValue(el, code, name) {
    if (!el || !el.options) return null;
    if (code) {
      for (const opt of el.options) {
        if (opt.value === code) return opt.value;
      }
    }
    if (name) {
      const target = name.trim();
      for (const opt of el.options) {
        if ((opt.text || "").trim() === target) return opt.value;
      }
    }
    return null;
  }

  function tryFill(retries) {
    const elCort = document.getElementById(ID.cort);
    const elYear = document.getElementById(ID.year);
    const elSa = document.getElementById(ID.sa);

    // 요소 자체 존재 + 법원 select의 option이 충분히 로드됐는지 확인.
    //   - elCort 없거나 option < 5개(기본 placeholder만) → 더 기다림
    //   - cort/name 매칭되는 option 있으면 진행
    const elementsReady = elCort && elYear && elSa;
    const cortMatchValue = (cort || cortName) ? findOptionValue(elCort, cort, cortName) : null;
    const cortReady = (!cort && !cortName) || (
      elCort && elCort.options && elCort.options.length > 5 && cortMatchValue !== null
    );
    const yearReady = !year || (elYear && elYear.options && elYear.options.length > 1);

    if (!elementsReady || !cortReady || !yearReady) {
      if (retries > 0) {
        setTimeout(() => tryFill(retries - 1), 300);
      } else {
        // 디버깅 — 실제 option들이 어떤 값인지 console에 dump
        console.warn(
          "[BidPick] prefill TIMEOUT — elements=%s cortReady=%s yearReady=%s",
          !!elementsReady, cortReady, yearReady,
        );
        if (elCort && elCort.options) {
          console.log("[BidPick] elCort options:",
            Array.from(elCort.options).map(o => ({ value: o.value, text: o.text })));
        }
        if (elYear && elYear.options) {
          console.log("[BidPick] elYear options:",
            Array.from(elYear.options).map(o => ({ value: o.value, text: o.text })));
        }
        // 폴백: cort 매칭 실패해도 year + sa만 채우기 시도
        if (year && elYear) setAndFire(elYear, year);
        if (sa && elSa) setAndFire(elSa, sa);
        console.log("[BidPick] 폴백 — cort 제외하고 year/sa만 채움");
      }
      return;
    }

    let touched = 0;
    if (cortMatchValue && setAndFire(elCort, cortMatchValue)) touched++;
    if (year && setAndFire(elYear, year)) touched++;
    if (sa && setAndFire(elSa, sa)) touched++;
    console.log(
      `[BidPick] prefill: ${touched}개 필드 채움 (cort=${cortMatchValue} year=${year} sa=${sa})`
    );

    // 검증 — 의도한 값이 실제로 들어갔는지 확인. 다르면 한 번 더.
    setTimeout(() => {
      if (cortMatchValue && elCort.value !== cortMatchValue) {
        console.warn(
          "[BidPick] prefill: 법원 값 불일치 (expected=%s actual=%s) — 재시도",
          cortMatchValue,
          elCort.value,
        );
        setAndFire(elCort, cortMatchValue);
        setTimeout(triggerSearch, 400);
      } else {
        triggerSearch();
      }
    }, 250);

    function triggerSearch() {
      const btn = findSearchButton();
      if (btn) {
        btn.click();
        console.log("[BidPick] prefill: 검색 버튼 클릭");
      } else {
        console.warn("[BidPick] prefill: 검색 버튼 못 찾음 — 수동 클릭 필요");
      }
    }
  }

  // 폼 + 법원 옵션 ajax 로딩 대기 — 15초까지 (300ms × 50)
  tryFill(50);
})();
