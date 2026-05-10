"""
LLM-driven news scorer for the risk engine.

Provider-agnostic: Gemini by default (free tier via AI Studio), with a
deterministic heuristic fallback when no API key is configured. The scorer
turns recent news/events into a small structured feature vector that the
quant risk engine consumes.

Output shape (per market, cached for ~10 min):
    {
        "catalyst_severity": float in [0, 1],   # how loaded the news flow is
        "asymmetry": float in [-1, 1],          # negative = downside-skewed, positive = upside-skewed
        "tail_multiplier": float in [0.7, 2.5], # multiplier on tail-risk vol
        "regime": "calm" | "trending" | "stressed",
        "confidence": float in [0, 1],          # how confident the scorer is in the read
        "rationale": str,                       # short explanation, surfaced in UI
    }
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── Cache ────────────────────────────────────────────────────────────────────
_score_cache: dict[str, tuple[dict[str, Any], datetime]] = {}
_CACHE_TTL = timedelta(minutes=10)
_domain_runtime: tuple[Any, Any] | None = None
_domain_runtime_key: tuple[str, str, str] | None = None


def _cache_key(provider: str, market_code: str) -> str:
    return f"{provider}:{market_code}"


def _cache_get(provider: str, market_code: str) -> dict[str, Any] | None:
    entry = _score_cache.get(_cache_key(provider, market_code))
    if not entry:
        return None
    payload, cached_at = entry
    if datetime.now(timezone.utc) - cached_at < _CACHE_TTL:
        return payload
    return None


def _cache_set(provider: str, market_code: str, payload: dict[str, Any]) -> None:
    _score_cache[_cache_key(provider, market_code)] = (payload, datetime.now(timezone.utc))


def invalidate_llm_cache(market_code: str | None = None) -> None:
    if market_code:
        for key in list(_score_cache):
            if key.endswith(f":{market_code}"):
                _score_cache.pop(key, None)
    else:
        _score_cache.clear()


# ── Public API ───────────────────────────────────────────────────────────────
@dataclass
class ScoredArticle:
    title: str
    summary: str
    source: str
    published_at: datetime
    credibility: float


def score_news_context(
    market_code: str,
    market_name: str,
    region: str,
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score the current news/event context for a market.

    Uses the configured provider (`heuristic`, `gemini`, or `domain`) and falls
    back to deterministic heuristic scoring if a remote/local provider is not
    available. Always returns a valid payload.
    """
    settings = get_settings()
    provider = settings.llm_scorer_provider.strip().lower() or "heuristic"
    if provider not in {"heuristic", "gemini", "domain"}:
        logger.warning("Unknown LLM_SCORER_PROVIDER=%s; using heuristic", provider)
        provider = "heuristic"

    cached = _cache_get(provider, market_code)
    if cached:
        return cached

    payload: dict[str, Any] | None = None

    if provider == "domain" and articles:
        try:
            payload = _score_with_domain(settings, market_name, region, articles, events_summary)
        except Exception as exc:  # noqa: BLE001 - scorer must never crash the risk engine
            logger.warning("Domain news scoring failed for %s, falling back. err=%s", market_code, exc)
            payload = None

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if payload is None and provider == "gemini" and api_key and articles:
        try:
            payload = _score_with_gemini(api_key, market_code, market_name, region, articles, events_summary)
        except Exception as exc:  # noqa: BLE001 — never let scorer crash the app
            logger.warning("Gemini scoring failed for %s, falling back. err=%s", market_code, exc)
            payload = None

    if payload is None:
        payload = _score_heuristic(articles, events_summary)

    _cache_set(provider, market_code, payload)
    return payload


# ── Gemini provider ──────────────────────────────────────────────────────────
_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)


def _build_gemini_prompt(
    market_name: str,
    region: str,
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> str:
    article_lines = []
    for idx, article in enumerate(articles[:12], start=1):
        age_hours = (datetime.now(timezone.utc) - article.published_at).total_seconds() / 3600
        article_lines.append(
            f"[{idx}] ({article.source}, {age_hours:.0f}h ago, cred {article.credibility:.0f})"
            f" {article.title} — {article.summary[:280]}"
        )

    event_lines = []
    for event in events_summary[:8]:
        event_lines.append(
            f"- {event.get('event_type', 'event')} ({event.get('severity', 'med')})"
            f" in {event.get('affected_region', region)}: {event.get('title', '')[:140]}"
        )

    return f"""You are a power-market risk analyst. Read the news and events below for {market_name} ({region}) and output a strict JSON object scoring the risk environment.

NEWS ARTICLES:
{chr(10).join(article_lines) if article_lines else "(none)"}

ACTIVE EVENTS:
{chr(10).join(event_lines) if event_lines else "(none)"}

Return ONLY a JSON object with this exact schema (no prose, no markdown fence):
{{
  "catalyst_severity": <float 0-1, how loaded the news flow is with price-moving catalysts>,
  "asymmetry": <float -1 to 1, negative = downside skew, positive = upside skew>,
  "tail_multiplier": <float 0.7-2.5, multiplier on tail-risk volatility>,
  "regime": <"calm" | "trending" | "stressed">,
  "confidence": <float 0-1, your confidence in this read>,
  "rationale": <string, 1-2 short sentences explaining the read>
}}"""


def _score_with_gemini(
    api_key: str,
    market_code: str,
    market_name: str,
    region: str,
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = _build_gemini_prompt(market_name, region, articles, events_summary)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(f"{_GEMINI_URL}?key={api_key}", json=body)
        resp.raise_for_status()
        data = resp.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = _parse_json_loose(text)
    return _validate_score(parsed, provider="gemini")


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _validate_score(parsed: dict[str, Any], *, provider: str) -> dict[str, Any]:
    def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, v))

    regime = parsed.get("regime", "calm")
    if regime not in {"calm", "trending", "stressed"}:
        regime = "calm"

    return {
        "catalyst_severity": _clamp(parsed.get("catalyst_severity"), 0.0, 1.0, 0.3),
        "asymmetry": _clamp(parsed.get("asymmetry"), -1.0, 1.0, 0.0),
        "tail_multiplier": _clamp(parsed.get("tail_multiplier"), 0.7, 2.5, 1.0),
        "regime": regime,
        "confidence": _clamp(parsed.get("confidence"), 0.0, 1.0, 0.5),
        "rationale": str(parsed.get("rationale", ""))[:400] or "LLM read",
        "provider": provider,
    }


# ── Domain LoRA provider ─────────────────────────────────────────────────────
def _build_domain_prompt(
    market_name: str,
    region: str,
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> str:
    article_text = "\n\n".join(
        f"NEWS ARTICLE:\n{article.title}\n{article.summary[:1200]}" for article in articles[:6]
    )
    event_text = "\n".join(
        f"- {event.get('event_type', 'event')} {event.get('severity', 'low')} {event.get('title', '')}"
        for event in events_summary[:6]
    )
    return (
        "<s>[INST] <<SYS>>\n"
        "You are a power-market news scorer. Return only compact JSON with keys "
        "catalyst_severity, asymmetry, tail_multiplier, regime, confidence, and rationale.\n"
        "<</SYS>>\n\n"
        f"Market: {market_name} ({region})\n\n"
        f"{article_text or 'NEWS ARTICLE:\n(none)'}\n\n"
        f"ACTIVE EVENTS:\n{event_text or '(none)'}\n\n"
        "Return the score JSON. [/INST]\n"
    )


def _score_with_domain(
    settings: Any,
    market_name: str,
    region: str,
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    generated = _generate_domain_response(settings, market_name, region, articles, events_summary)
    parsed = _parse_json_loose(generated)
    return _validate_score(parsed, provider="domain")


def _generate_domain_response(
    settings: Any,
    market_name: str,
    region: str,
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> str:
    tokenizer, model = _load_domain_runtime(settings)
    prompt = _build_domain_prompt(market_name, region, articles, events_summary)
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1536)

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - training deps are optional in app env
        raise RuntimeError("torch is required for domain scorer inference") from exc

    device = next(model.parameters()).device
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=384,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated_ids = output[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def _load_domain_runtime(settings: Any) -> tuple[Any, Any]:
    global _domain_runtime, _domain_runtime_key

    key = (
        str(settings.domain_scorer_model_dir),
        str(settings.domain_scorer_base_model),
        str(settings.domain_scorer_device_map),
    )
    if _domain_runtime is not None and _domain_runtime_key == key:
        return _domain_runtime

    model_dir = Path(settings.domain_scorer_model_dir)
    if not model_dir.is_absolute():
        model_dir = Path(__file__).resolve().parents[2] / model_dir
    adapter_config = model_dir / "adapter_config.json"
    adapter_weights = model_dir / "adapter_model.safetensors"
    if not adapter_config.exists() or not adapter_weights.exists():
        raise RuntimeError(f"domain LoRA adapter weights not found in {model_dir}")

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - train deps are optional in runtime tests
        raise RuntimeError("domain scorer dependencies are not installed") from exc

    tokenizer_source = model_dir if (model_dir / "tokenizer_config.json").exists() else settings.domain_scorer_base_model
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, use_fast=True, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    cuda_available = bool(torch.cuda.is_available())
    model = AutoModelForCausalLM.from_pretrained(
        settings.domain_scorer_base_model,
        device_map=settings.domain_scorer_device_map if cuda_available else None,
        torch_dtype=torch.bfloat16 if cuda_available else torch.float32,
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, model_dir)
    model.eval()
    _domain_runtime = (tokenizer, model)
    _domain_runtime_key = key
    return _domain_runtime


# ── Heuristic fallback ───────────────────────────────────────────────────────
_BULL_TERMS = {
    "heatwave", "heat wave", "outage", "shutdown", "shortage", "cold snap",
    "polar vortex", "drought", "spike", "surge", "soar", "rally", "tight",
    "scarcity", "deficit", "low wind", "sanctions", "supply cut",
}
_BEAR_TERMS = {
    "mild", "ample", "oversupply", "surplus", "drop", "plunge", "fall",
    "warm winter", "high renewables", "wind surge", "solar peak",
    "demand drop", "lower demand",
}


def _score_heuristic(
    articles: list[ScoredArticle],
    events_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    if not articles and not events_summary:
        return {
            "catalyst_severity": 0.15,
            "asymmetry": 0.0,
            "tail_multiplier": 0.9,
            "regime": "calm",
            "confidence": 0.4,
            "rationale": "No fresh catalysts. Using baseline volatility profile.",
            "provider": "heuristic",
        }

    bull_hits = 0.0
    bear_hits = 0.0
    weight_total = 0.0
    now = datetime.now(timezone.utc)

    for article in articles[:15]:
        text = f"{article.title} {article.summary}".lower()
        age_hours = max(1.0, (now - article.published_at).total_seconds() / 3600)
        freshness = max(0.2, 1.0 - age_hours / 168.0)
        weight = freshness * (article.credibility / 100.0)
        weight_total += weight
        for term in _BULL_TERMS:
            if term in text:
                bull_hits += weight
        for term in _BEAR_TERMS:
            if term in text:
                bear_hits += weight

    severity_from_events = 0.0
    for event in events_summary[:10]:
        sev = event.get("severity", "low")
        severity_from_events += {"high": 0.35, "medium": 0.18, "low": 0.06}.get(sev, 0.06)

    raw_severity = (bull_hits + bear_hits) / max(weight_total, 1.0) + severity_from_events
    catalyst_severity = max(0.0, min(1.0, raw_severity * 0.55))

    net = bull_hits - bear_hits
    denom = max(bull_hits + bear_hits, 0.5)
    asymmetry = max(-1.0, min(1.0, net / denom))

    if catalyst_severity > 0.6:
        regime = "stressed"
        tail_multiplier = 1.6 + min(0.8, catalyst_severity - 0.6)
    elif catalyst_severity > 0.3 or abs(asymmetry) > 0.4:
        regime = "trending"
        tail_multiplier = 1.15 + catalyst_severity * 0.4
    else:
        regime = "calm"
        tail_multiplier = 0.9 + catalyst_severity * 0.3

    rationale_bits = []
    if bull_hits > bear_hits * 1.3:
        rationale_bits.append("upside catalysts dominate the news flow")
    elif bear_hits > bull_hits * 1.3:
        rationale_bits.append("downside catalysts dominate the news flow")
    else:
        rationale_bits.append("news flow is two-sided")
    rationale_bits.append(f"regime read: {regime}")
    if severity_from_events > 0.3:
        rationale_bits.append("active high-severity events lifting tail risk")

    return {
        "catalyst_severity": round(catalyst_severity, 3),
        "asymmetry": round(asymmetry, 3),
        "tail_multiplier": round(tail_multiplier, 3),
        "regime": regime,
        "confidence": round(min(0.85, 0.4 + weight_total * 0.05), 3),
        "rationale": "; ".join(rationale_bits) + ".",
        "provider": "heuristic",
    }
