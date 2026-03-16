def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_endpoint(client) -> None:
    response = client.get("/api/dashboard/ERCOT_NORTH")
    assert response.status_code == 200
    body = response.json()
    assert body["market"]["code"] == "ERCOT_NORTH"
    assert len(body["recent_prices"]) > 0
    assert len(body["recent_news"]) > 0
    assert len(body["tracked_sources"]) >= 20
    assert "avg_price_24h" in body["key_metrics"]


def test_ingest_article(client) -> None:
    response = client.post(
        "/api/articles/ingest",
        json={
            "title": "Transmission outage creates local constraint in Houston",
            "body": "A transmission outage is expected to constrain imports and lift local power prices.",
            "source_name": "Ops Note",
            "source_url": "https://example.com/outage",
            "published_at": "2026-03-16T10:00:00Z",
            "market_code": "ERCOT_HOUSTON",
        },
    )
    assert response.status_code == 200
    assert response.json()["event_type"] == "transmission_outage"
