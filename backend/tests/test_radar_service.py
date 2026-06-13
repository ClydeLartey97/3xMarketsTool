"""Radar service: ranking, splitting, determinism, and failure isolation.

The heavy engine call (`_assess`) and calibration lookup are monkeypatched with
canned values so these tests exercise the radar's assembly logic only — no
Monte Carlo, no forecast models, no network.
"""

from __future__ import annotations

from sqlalchemy import select

import app.services.radar_service as rs
from app.models import Market


def _canned_assess():
    """A deterministic stand-in for `_assess`, keyed by market code/direction."""

    def _assess(db, *, market_code, position_gbp, direction, horizon_hours):
        edges = {"GB_POWER": 0.42, "EPEX_DE": 0.31, "ERCOT": -0.20}
        base = edges.get(market_code, 0.10)
        edge = base if direction == "long" else -base * 0.5
        likely = 0.08 * position_gbp * edge
        action = (
            "block"
            if market_code == "PJM"
            else ("clear" if edge >= 0.25 else "watch")
        )
        return {
            "market_code": market_code,
            "market_name": f"{market_code} name",
            "direction": direction,
            "risk_gbp": 0.50 * position_gbp if market_code == "ERCOT" else 0.12 * position_gbp,
            "likely_gbp": likely,
            "upside_gbp": abs(likely) * 1.6,
            "edge_score": edge,
            "confidence": 0.7,
            "regime": "trending",
            "catalyst_severity": 0.2,
            "decision_gate": {"action": action, "reasons": [f"edge {edge:.2f}"]},
        }

    return _assess


def _honest_cal(db, market_id, **kwargs):
    return {"calibration_status": "honest", "sample_count": 30}


def test_compute_radar_ranks_splits_and_is_deterministic(db_session, monkeypatch):
    monkeypatch.setattr(rs, "_assess", _canned_assess())
    monkeypatch.setattr(rs, "risk_calibration_for_market", _honest_cal)

    snap = rs.compute_radar(db_session, user_id=None, horizon_hours=24)

    assert snap["universe_count"] >= 1
    assert isinstance(snap["opportunities"], list)
    assert isinstance(snap["threats"], list)

    # Opportunities are sorted by radar_score, descending.
    scores = [o["radar_score"] for o in snap["opportunities"]]
    assert scores == sorted(scores, reverse=True)

    # Every opportunity has positive expected P&L and is not gate-blocked.
    assert all(o["likely_gbp"] > 0 for o in snap["opportunities"])

    # A second run on the same data must rank identically (fixed seeds).
    snap2 = rs.compute_radar(db_session, user_id=None, horizon_hours=24)
    assert [o["market_code"] for o in snap["opportunities"]] == [
        o["market_code"] for o in snap2["opportunities"]
    ]

    # A market whose gate hard-blocks must never appear as an opportunity.
    seeded_codes = {o["market_code"] for o in snap["opportunities"]} | {
        t["market_code"] for t in snap["threats"]
    }
    if "PJM" in seeded_codes:
        assert all(o["market_code"] != "PJM" for o in snap["opportunities"])


def test_compute_radar_isolates_a_failing_market(db_session, monkeypatch):
    good = _canned_assess()

    def flaky_assess(db, *, market_code, position_gbp, direction, horizon_hours):
        if market_code == "GB_POWER":
            raise RuntimeError("synthetic engine failure")
        return good(
            db,
            market_code=market_code,
            position_gbp=position_gbp,
            direction=direction,
            horizon_hours=horizon_hours,
        )

    monkeypatch.setattr(rs, "_assess", flaky_assess)
    monkeypatch.setattr(rs, "risk_calibration_for_market", _honest_cal)

    snap = rs.compute_radar(db_session, user_id=None, horizon_hours=24)

    # The failing market is skipped and the rest still rank.
    codes = {i["market_code"] for i in snap["opportunities"] + snap["threats"]}
    assert "GB_POWER" not in codes

    # If GB_POWER is in the seeded universe, it must be reported as failed.
    seeded = {m.code for m in db_session.scalars(select(Market)).all()}
    if "GB_POWER" in seeded:
        assert "GB_POWER" in snap["failed"]


def test_compute_radar_surfaces_open_book_threat(db_session, auth_user, monkeypatch):
    from datetime import datetime, timezone

    from app.models import RiskAssessmentLog

    market = db_session.scalars(select(Market)).first()
    assert market is not None, "seed should provide at least one market"

    # Book an open position with a small recorded risk.
    db_session.add(
        RiskAssessmentLog(
            timestamp=datetime.now(timezone.utc),
            market_id=market.id,
            user_id=auth_user.id,
            position_gbp=100_000.0,
            direction="long",
            horizon_hours=24,
            risk_gbp=1_000.0,
            likely_gbp=500.0,
            upside_gbp=2_000.0,
            kind="diary",
            is_open=True,
            thesis_text="open test position",
        )
    )
    db_session.commit()

    base = _canned_assess()

    def risk_grew_assess(db, *, market_code, position_gbp, direction, horizon_hours):
        result = base(
            db,
            market_code=market_code,
            position_gbp=position_gbp,
            direction=direction,
            horizon_hours=horizon_hours,
        )
        if market_code == market.code:
            result["risk_gbp"] = 50_000.0  # >> booked 1,000 * 1.15 -> risk grew
        return result

    monkeypatch.setattr(rs, "_assess", risk_grew_assess)
    monkeypatch.setattr(rs, "risk_calibration_for_market", _honest_cal)

    snap = rs.compute_radar(db_session, user_id=auth_user.id, horizon_hours=24)

    book = [t for t in snap["threats"] if t["market_code"] == market.code]
    assert book, "an open position whose risk grew should surface as a threat"
    assert "risk rose" in book[0]["reason"].lower()
    # The book threat supersedes any generic read for that market in opportunities.
    assert all(o["market_code"] != market.code for o in snap["opportunities"])
