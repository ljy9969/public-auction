"""AI 예상 낙찰가 — 상세 페이지 'AI 예상가' 버튼 on-demand 호출.

provider-agnostic: 환경변수로 Claude(Anthropic) / Gemini(Google) 중 선택.
  - ANTHROPIC_API_KEY 있으면 Claude Sonnet (기본, 품질 우선)
  - GEMINI_API_KEY 있으면 Gemini (OctaLink 키 재사용 시 — 저렴/무료티어)
  - AI_PROVIDER=claude|gemini 로 강제 가능
SDK 의존성 없이 httpx REST 직접 호출 (requirements 추가 불필요).

매물의 감정가·최저가·유찰·시세통계·국토부 실거래가 샘플·권리분석·통계 예측을
컨텍스트로 주고, JSON {low, median, high, reasoning, confidence} 를 받는다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_FALLBACK_CLAUDE_MODEL = "claude-sonnet-4-6"
_FALLBACK_GEMINI_MODEL = "gemini-2.5-pro"


def _claude_model() -> str:
    # 호출 시점에 읽어 .env 로드 순서에 무관하게 최신 값 반영
    return os.environ.get("ANTHROPIC_MODEL", _FALLBACK_CLAUDE_MODEL)


def _gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", _FALLBACK_GEMINI_MODEL)

_SYSTEM = (
    "당신은 대한민국 법원경매·공매 낙찰가 분석 전문가입니다. "
    "주어진 매물 정보(감정가, 현재 최저가, 유찰 횟수, 카테고리, 면적, 건축 연식, "
    "국토부 실거래가 시세 통계와 개별 거래 샘플, 권리분석 요약, 통계 기반 예측치)를 "
    "종합해 '예상 낙찰가'를 추정합니다. 한국 경매 시장의 카테고리별 낙찰가율과 "
    "유찰에 따른 하락, 시세 대비 할인, 권리상 위험을 반영하세요. "
    "반드시 아래 JSON 스키마로만 답하세요(설명·마크다운 금지):\n"
    '{"low": <정수 원>, "median": <정수 원>, "high": <정수 원>, '
    '"confidence": "low|medium|high", "reasoning": "<한국어 3~5문장 근거>"}'
)


class AiEstimateError(RuntimeError):
    """키 미설정·API 실패 등."""


def provider_in_use() -> str | None:
    forced = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if forced in ("claude", "anthropic"):
        return "claude" if os.environ.get("ANTHROPIC_API_KEY") else None
    if forced == "gemini":
        return "gemini" if os.environ.get("GEMINI_API_KEY") else None
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return None


def _won(v: Any) -> str:
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return "미상"


def _market_samples(prop: dict[str, Any]) -> list[dict[str, Any]]:
    raw = prop.get("market_samples")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
    return raw if isinstance(raw, list) else []


def build_user_prompt(prop: dict[str, Any]) -> str:
    lines: list[str] = ["[매물 정보]"]
    lines.append(f"- 제목: {prop.get('title') or '-'}")
    lines.append(f"- 카테고리: {prop.get('category') or '-'}")
    lines.append(f"- 소재지: {prop.get('address_jibun') or prop.get('region_line') or '-'}")
    lines.append(f"- 감정가: {_won(prop.get('appraisal_price'))}")
    lines.append(f"- 현재 최저가: {_won(prop.get('min_price'))}")
    lines.append(f"- 유찰 횟수: {prop.get('fail_count') or 0}회")
    area = prop.get("area_build_m2")
    lines.append(f"- 건물 면적: {area}㎡" if area else "- 건물 면적: 미상")
    if prop.get("use_apr_day"):
        lines.append(f"- 사용승인일: {prop.get('use_apr_day')}")
    if prop.get("share_yn") == "Y":
        lines.append("- 지분 매물(공유지분)")

    # 시세/실거래가 통계
    if prop.get("market_median_price"):
        lines.append("\n[국토부 실거래가 시세]")
        lines.append(
            f"- 중앙값 {_won(prop.get('market_median_price'))} "
            f"(범위 {_won(prop.get('market_min_price'))}~{_won(prop.get('market_max_price'))}, "
            f"표본 {prop.get('market_sample_count') or 0}건, {prop.get('market_match_kind') or ''})"
        )
        if prop.get("market_diff_percent") is not None:
            lines.append(f"- 우리 매물 최저가의 시세 대비: {prop.get('market_diff_percent')}%")
        samples = _market_samples(prop)[:8]
        if samples:
            lines.append("- 개별 실거래:")
            for s in samples:
                lines.append(
                    f"   · {s.get('deal_date','')} {s.get('name','')} "
                    f"{s.get('area_m2','?')}㎡ {s.get('floor','?')}층 → {_won(s.get('deal_amount'))}"
                )

    # 권리분석 요약
    ra = prop.get("rights_analysis")
    if isinstance(ra, str):
        try:
            ra = json.loads(ra)
        except (TypeError, json.JSONDecodeError):
            ra = None
    if isinstance(ra, dict):
        flags = ra.get("flags") or []
        flag_txt = ", ".join(f.get("label", "") for f in flags if isinstance(f, dict)) or "특이사항 없음"
        lines.append("\n[권리분석]")
        lines.append(f"- 위험도: {ra.get('risk_label') or ra.get('risk_level') or '-'} / {flag_txt}")

    # 통계 기반 예측(참고용)
    if prop.get("predicted_price_median"):
        lines.append("\n[참고: 통계 휴리스틱 예측]")
        lines.append(
            f"- {_won(prop.get('predicted_price_low'))} ~ "
            f"{_won(prop.get('predicted_price_median'))} ~ "
            f"{_won(prop.get('predicted_price_high'))}"
        )
        if prop.get("predicted_price_basis"):
            lines.append(f"  근거: {prop.get('predicted_price_basis')}")

    lines.append(
        "\n위 정보를 종합해 예상 낙찰가(low/median/high)와 근거를 JSON으로만 답하세요."
    )
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # 코드펜스 제거
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise AiEstimateError("AI 응답에서 JSON을 찾지 못했습니다")


def _call_claude(user_prompt: str) -> tuple[dict[str, Any], str]:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = _claude_model()
    with httpx.Client(timeout=40.0) as c:
        r = c.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 800,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
    if r.status_code != 200:
        raise AiEstimateError(f"Anthropic API 오류 {r.status_code}: {r.text[:200]}")
    data = r.json()
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return _extract_json(text), model


def _call_gemini(user_prompt: str) -> tuple[dict[str, Any], str]:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = _gemini_model()
    url = GEMINI_URL.format(model=model)
    gen_cfg: dict[str, Any] = {
        "temperature": 0.4,
        "maxOutputTokens": 2048,
        "responseMimeType": "application/json",
    }
    # Gemini 2.5 계열은 기본 'thinking'이 출력 토큰을 소모해 본문(JSON)이 비어버릴 수 있음.
    # flash 계열은 thinking 0으로 비활성화(저렴/빠름). pro는 thinking 필요해 토큰만 넉넉히.
    if "flash" in model:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            url,
            params={"key": key},
            headers={"content-type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": _SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": gen_cfg,
            },
        )
    if r.status_code != 200:
        raise AiEstimateError(f"Gemini API 오류 {r.status_code}: {r.text[:200]}")
    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        # 프롬프트 차단(safety) 등
        raise AiEstimateError(f"Gemini 응답에 candidates 없음: {str(data)[:200]}")
    cand = cands[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise AiEstimateError(
            f"Gemini 응답 본문 비어있음 (finishReason={cand.get('finishReason')})"
        )
    return _extract_json(text), model


def estimate(prop: dict[str, Any]) -> dict[str, Any]:
    """매물 dict → AI 예상가. provider 미설정 시 AiEstimateError."""
    provider = provider_in_use()
    if not provider:
        raise AiEstimateError(
            "AI 키가 설정되지 않았습니다. .env에 ANTHROPIC_API_KEY 또는 GEMINI_API_KEY 추가 필요."
        )
    user_prompt = build_user_prompt(prop)
    parsed, model = _call_claude(user_prompt) if provider == "claude" else _call_gemini(user_prompt)

    def _int(v: Any) -> int | None:
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    result = {
        "low": _int(parsed.get("low")),
        "median": _int(parsed.get("median")),
        "high": _int(parsed.get("high")),
        "confidence": parsed.get("confidence"),
        "reasoning": (parsed.get("reasoning") or "").strip(),
        "provider": provider,
        "model": model,
    }
    if result["median"] is None:
        raise AiEstimateError("AI 응답에 median 가격이 없습니다")
    return result
