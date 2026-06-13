"""GET /api/radar: serves the cached snapshot and computes on a cold cache.

The radar service functions are monkeypatched so the endpoint test never runs
the real engine (no Monte Carlo, no network).
"""

from __future__ import annotations

import app.services.radar_service as rs

_SNAPSHOT = {
    "generated_at": "2026-06-13T00:00:00+00:00",
    "horizon_hours": 24,
    "universe_count": 9,
    "failed": [],
    "opportunities": [],
    "threats": [],
}


def test_radar_endpoint_serves_cached_snapshot(client, monkeypatch):
    monkeypatch.setattr(rs, "read_radar_snapshot", lambda *, user_id=None: dict(_SNAPSHOT))

    resp = client.get("/api/radar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is False
    assert body["universe_count"] == 9
    assert body["opportunities"] == []
    assert body["threats"] == []


def test_radar_endpoint_computes_on_cold_cache(client, monkeypatch):
    computed = dict(_SNAPSHOT)
    computed["universe_count"] = 3

    monkeypatch.setattr(rs, "read_radar_snapshot", lambda *, user_id=None: None)
    monkeypatch.setattr(rs, "compute_radar", lambda db, *, user_id=None, **kw: dict(computed))
    monkeypatch.setattr(rs, "cache_radar_snapshot", lambda snap, *, user_id=None: None)

    resp = client.get("/api/radar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert body["universe_count"] == 3
