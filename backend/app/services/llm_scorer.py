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
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── Cache ────────────────────────────────────────────────────────────────────
_score_cache: dict[str, tuple[dict[str, Any], datetime]] = {}
_CACHE_TTL = timedelta(minutes=10)


def _cache_get(market_code: str) -> dict[str, Any] | None:
    entry = _score_cache.get(market_code)
    if not entry:
        return None
    payload, cached_at = entry
    if datetime.now(timezone.utc) - cached_at < _CACHE_TTL:
        return payload
    return None


def _cache_set(market_code: str, payload: dict[str, Any]) -> None:
    _score_cache[market_code] = (payload, datetime.now(timezone.utc))


def invalidate_llm_cache(market_code: str | None = None) -> None:
    if market_code:
        _score_cache.pop(market_code, None)
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

    Tries Gemini if `GEMINI_API_KEY` is set, otherwise falls back to a
    deterministic heuristic scoring. Always returns a valid payload.
    """
    cached = _cache_get(market_code)
    if cached:
        return cached

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    payload: dict[str, Any] | None = None

    if api_key and articles:
        try:
            payload = _score_with_gemini(api_key, market_code, market_name, region, articles, events_summary)
        except Exception as exc:  # noqa: BLE001 — never let scorer crash the app
            logger.warning("Gemini scoring failed for %s, falling back. err=%s", market_code, exc)
            payload = None

    if payload is None:
        payload = _score_heuristic(articles, events_summary)

    _cache_set(market_code, payload)
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
    return _validate_score(parsed)


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _validate_score(parsed: dict[str, Any]) -> dict[str, Any]:
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
        "provider": "gemini",
    }


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
