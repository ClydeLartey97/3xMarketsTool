from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import get_settings
from app.services import llm_scorer
from app.services.llm_scorer import ScoredArticle, invalidate_llm_cache, score_news_context


def test_domain_scorer_provider_round_trips_valid_schema(monkeypatch) -> None:
    monkeypatch.setenv("LLM_SCORER_PROVIDER", "domain")
    get_settings.cache_clear()
    invalidate_llm_cache()

    def fake_generate(*_args, **_kwargs) -> str:
        return """
        {
          "catalyst_severity": 0.72,
          "asymmetry": 0.44,
          "tail_multiplier": 1.84,
          "regime": "stressed",
          "confidence": 0.81,
          "rationale": "Outage and weather catalysts are reinforcing."
        }
        """

    monkeypatch.setattr(llm_scorer, "_generate_domain_response", fake_generate)

    result = score_news_context(
        "GB_POWER",
        "Great Britain Power",
        "Great Britain",
        [
            ScoredArticle(
                title="GB generator outage removes 900 MW before peak",
                summary="A forced outage tightened the evening ramp.",
                source="unit",
                published_at=datetime.now(timezone.utc),
                credibility=95,
            )
        ],
        [{"event_type": "generator_outage", "severity": "high", "title": "900 MW outage"}],
    )

    assert result == {
        "catalyst_severity": 0.72,
        "asymmetry": 0.44,
        "tail_multiplier": 1.84,
        "regime": "stressed",
        "confidence": 0.81,
        "rationale": "Outage and weather catalysts are reinforcing.",
        "provider": "domain",
    }
    get_settings.cache_clear()
    invalidate_llm_cache()
