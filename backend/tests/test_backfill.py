from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select

from app.ingestion import real_data
from app.models import Market, PricePoint


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _parse_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_eia_history_fetches_per_month(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, _url: str, params: dict):
            calls.append(params.copy())
            return _FakeResponse({"response": {"data": [{"period": params["start"], "value": "100"}]}})

    monkeypatch.setattr(real_data.httpx, "Client", FakeClient)

    start = datetime(2024, 1, 15, tzinfo=timezone.utc)
    end = datetime(2024, 3, 2, tzinfo=timezone.utc)
    frame = real_data.fetch_eia_demand_history("ERCO", "key", start, end)

    assert len(calls) == 3
    assert [call["start"] for call in calls] == ["2024-01-15T00", "2024-02-01T00", "2024-03-01T00"]
    assert not frame.empty
    assert list(frame.columns) == ["timestamp", "demand_mw"]


def test_elexon_history_fetches_in_seven_day_windows(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, _url: str, params: dict):
            calls.append(params.copy())
            return _FakeResponse({
                "data": [{
                    "dataset": "MID",
                    "startTime": params["from"],
                    "settlementDate": params["from"][:10],
                    "settlementPeriod": 1,
                    "price": 50.0,
                    "volume": 10.0,
                }]
            })

    monkeypatch.setattr(real_data.httpx, "Client", FakeClient)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    frame = real_data.fetch_elexon_prices_between(start, end)

    assert len(calls) == 3
    assert all(_parse_z(call["to"]) - _parse_z(call["from"]) <= timedelta(days=7) for call in calls)
    assert len(frame) == 3
    assert set(frame.columns) == {"timestamp", "price_gbp_mwh"}


def test_backfill_market_is_rerunnable_and_dedupes(db_session, monkeypatch) -> None:
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)
    expected_hours = pd.date_range(end - timedelta(days=2), end, freq="h", inclusive="left", tz="UTC")

    def fake_weather_archive(_lat: float, _lon: float, start: datetime, finish: datetime) -> pd.DataFrame:
        times = pd.date_range(start, finish, freq="h", inclusive="left", tz="UTC")
        return pd.DataFrame({
            "timestamp": times,
            "temperature_c": [12.0] * len(times),
            "wind_speed": [8.0] * len(times),
            "direct_radiation": [100.0] * len(times),
            "precipitation": [0.0] * len(times),
        })

    def fake_elexon_prices(start: datetime, finish: datetime, window_days: int = 7) -> pd.DataFrame:
        times = pd.date_range(start, finish, freq="h", inclusive="left", tz="UTC")
        return pd.DataFrame({"timestamp": times, "price_gbp_mwh": [70.0] * len(times)})

    monkeypatch.setattr(real_data, "fetch_weather_archive", fake_weather_archive)
    monkeypatch.setattr(real_data, "fetch_elexon_prices_between", fake_elexon_prices)
    monkeypatch.setattr(real_data, "get_ttf_gas_price_eur_mwh", lambda: 38.0)

    first = real_data.backfill_market("GB_POWER", lookback_days=2, db=db_session, eia_api_key="", end=end)
    second = real_data.backfill_market("GB_POWER", lookback_days=2, db=db_session, eia_api_key="", end=end)

    market = db_session.scalar(select(Market).where(Market.code == "GB_POWER"))
    assert market is not None
    points = list(db_session.scalars(
        select(PricePoint).where(
            PricePoint.market_id == market.id,
            PricePoint.timestamp >= expected_hours[0].to_pydatetime(),
            PricePoint.timestamp < end,
        )
    ).all())

    assert first["inserted"] == len(expected_hours)
    assert second["inserted"] == 0
    assert len(points) == len(expected_hours)
    assert {point.source for point in points} == {"elexon-bmrs"}
