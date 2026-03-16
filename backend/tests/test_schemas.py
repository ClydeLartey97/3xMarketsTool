from pydantic import ValidationError
import pytest

from app.schemas.domain import ArticleIngestRequest


def test_article_ingest_schema_validation() -> None:
    payload = ArticleIngestRequest(
        title="Heat advisory in ERCOT",
        body="Extreme heat alert raises power demand expectations.",
        source_name="Weather Desk",
        source_url="https://example.com/weather",
        published_at="2026-03-16T12:00:00Z",
        market_code="ERCOT_NORTH",
    )
    assert payload.market_code == "ERCOT_NORTH"


def test_article_ingest_schema_requires_title() -> None:
    with pytest.raises(ValidationError):
        ArticleIngestRequest(
            title="",
            body="Body",
            source_name="Desk",
            source_url="https://example.com",
            published_at="2026-03-16T12:00:00Z",
        )
