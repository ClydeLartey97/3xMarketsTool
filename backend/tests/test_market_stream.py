from __future__ import annotations

from datetime import datetime, timezone

from app.main import app
from app.services.market_stream import encode_market_message, market_stream_channel


def test_market_stream_channel_and_encoding() -> None:
    assert market_stream_channel("gb_power") == "market-stream:GB_POWER"
    payload = encode_market_message(
        {
            "type": "price_tick",
            "market_code": "GB_POWER",
            "timestamp": datetime(2026, 5, 11, 12, tzinfo=timezone.utc),
            "price_value": 81.5,
        }
    )
    assert '"type":"price_tick"' in payload
    assert '"timestamp":"2026-05-11T12:00:00+00:00"' in payload


def test_market_websocket_route_registered() -> None:
    assert any(getattr(route, "path", "") == "/ws/markets/{market_code}" for route in app.routes)
