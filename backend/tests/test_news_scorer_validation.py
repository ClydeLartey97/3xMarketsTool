from __future__ import annotations

import pytest

from app.services.news_scorer_validation import (
    adapter_weights_present,
    compare_predictors,
    domain_lora_predict,
    load_golden_records,
)


def test_news_golden_set_has_50_hand_curated_rows() -> None:
    records = load_golden_records()

    assert len(records) == 50
    assert {record.label_dict["event_type"] for record in records} >= {
        "generator_outage",
        "transmission_outage",
        "extreme_weather_alert",
        "renewable_forecast_revision",
        "demand_shock",
        "regulatory_policy_announcement",
        "no_event",
    }


def test_validation_harness_detects_domain_improvement() -> None:
    records = load_golden_records()[:10]

    def weak_heuristic(_record):
        return {"event_type": "no_event", "price_direction": "neutral", "severity": "low", "regime": "calm"}

    def exact_domain(record):
        return record.label_dict

    result = compare_predictors(records, domain_predictor=exact_domain, heuristic_predictor=weak_heuristic)

    assert result.passed is True
    assert result.improvement_pp >= 15.0


def test_domain_lora_beats_heuristic_when_adapter_present() -> None:
    if not adapter_weights_present():
        pytest.skip("Domain LoRA adapter weights are not present; D.6 remains blocked.")

    result = compare_predictors(load_golden_records(), domain_predictor=domain_lora_predict)

    assert result.sample_count == 50
    assert result.improvement_pp >= 15.0
