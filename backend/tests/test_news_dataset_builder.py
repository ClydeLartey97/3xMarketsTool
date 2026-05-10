from __future__ import annotations

import json

from scripts.build_news_dataset import (
    SourceArticle,
    build_records,
    generate_bootstrap_articles,
    label_article,
)


def test_bootstrap_news_dataset_records_are_silver_labelled() -> None:
    records = build_records([], target_rows=12, min_confidence=0.55)

    assert len(records) == 12
    first = records[0]
    assert set(first) == {"id", "text", "label_dict", "metadata"}
    assert first["label_dict"]["silver_label"] is True
    assert first["label_dict"]["event_type"] != "no_event"
    assert first["label_dict"]["label_confidence"] >= 0.55

    # The generated corpus should be JSONL-safe without custom encoders.
    json.dumps(first)


def test_label_article_filters_low_confidence_irrelevant_text() -> None:
    article = SourceArticle(
        title="Quarterly software subscription update",
        body="The company described customer renewals and had no power-market operating details.",
        source_name="Test Source",
        source_family="unit_test",
        source_url="https://example.invalid/article",
        published_at=generate_bootstrap_articles(1)[0].published_at,
        credibility=50.0,
        market_code="ERCOT_NORTH",
        source_kind="unit_test",
    )

    assert label_article(article, min_confidence=0.55) is None
