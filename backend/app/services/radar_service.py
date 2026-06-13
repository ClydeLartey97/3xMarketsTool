"""Radar — proactive cross-market opportunity & threat scan.

The workbench is pull-based: a trader enters a position and reads the three
numbers. The Radar inverts that. It runs the existing risk engine across every
market at a standardised unit position (both directions), ranks each market by a
transparent composite of *edge*, *imminent-catalyst proximity*, and *calibration
confidence*, and splits the result into Opportunities and Threats. It also scans
the signed-in user's open book and surfaces positions whose risk has grown or
that face a maturing catalyst.

No new risk math lives here. The Radar is an assembly layer over:
  - ``assess_risk``               -> edge_score, catalyst_severity, decision_gate
  - ``risk_calibration_for_market`` -> Kupiec calibration status (the trust gate)
  - the ``events`` table          -> imminent catalyst + human-readable reason
  - ``list_decisions``            -> the user's open positions (book-aware threats)

The composite ``radar_score`` is deliberately simple and explainable so it holds
to the same glass-box standard as the rest of the product (see ``_score_item``).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Market
from app.services.decision_diary import list_decisions
from app.services.risk_calibration import risk_calibration_for_market

# NOTE: `risk_engine` is imported lazily inside `_assess` (not at module top).
# It transitively loads the forecast/ML stack, so a top-level import would make
# every `import radar_service` pay that cost — and makes the module hard to test.
# This mirrors the route handlers, which also import `risk_engine` inside the
# request function (see app/api/routes.py).

logger = logging.getLogger(__name__)

# Standardised notional used to compare markets on equal footing.
RADAR_UNIT_POSITION_GBP = 100_000.0
RADAR_DEFAULT_HORIZON_H = 24
# Lighter than the 5,000-path interactive default — this is a periodic sweep,
# not a single decision read, and runs off the request path in the worker.
RADAR_SCAN_N_PATHS = 2_000
RADAR_TOP_N = 8
# An open position is flagged when its live risk exceeds the booked risk by >15%.
_BOOK_RISK_THREAT_RATIO = 1.15

# Event.severity is a free-form string; map to an ordinal for "most severe imminent".
_SEVERITY_RANK = {
    "critical": 4,
    "severe": 4,
    "high": 3,
    "elevated": 3,
    "medium": 2,
    "moderate": 2,
    "low": 1,
    "minor": 1,
}

# How much to trust a market's edge given its calibration status. "honest" is
# fully trusted; "overstating" (risk looks too conservative vs realised breaches)
# is discounted hardest because it inflates apparent edge.
_CAL_GATE = {
    "honest": 1.0,
    "understating": 0.6,
    "collecting": 0.6,
    "unknown": 0.6,
    "overstating": 0.3,
}


@dataclass
class RadarItem:
    market_code: str
    market_name: str
    direction: str            # the higher-edge side chosen for this market
    risk_gbp: float
    likely_gbp: float
    upside_gbp: float
    edge_score: float         # reused verbatim from assess_risk
    confidence: float
    regime: str
    catalyst_severity: float
    calibration_status: str   # honest | understating | overstating | collecting | unknown
    hours_to_catalyst: float | None
    radar_score: float        # composite ranking key (see _score_item)
    kind: str                 # "opportunity" | "threat"
    reason: str               # short human string


def _stable_seed(market_code: str) -> int:
    """Deterministic per-market seed so repeated scans rank identically."""
    digest = hashlib.sha256(market_code.encode("utf-8")).hexdigest()
    return int(digest, 16) % (2**31)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cal_status(db: Session, market_id: int | None) -> str:
    if market_id is None:
        return "unknown"
    try:
        return str(risk_calibration_for_market(db, market_id)["calibration_status"])
    except Exception as exc:  # noqa: BLE001 - calibration must never sink a scan
        logger.debug("radar calibration lookup failed for market %s: %s", market_id, exc)
        return "unknown"


def _imminent_event(
    db: Session, market_id: int | None, now: datetime, horizon_hours: int
) -> tuple[float | None, str | None]:
    """Most severe catalyst maturing within the horizon for this market.

    Returns ``(hours_to_catalyst, reason)`` or ``(None, None)``. Events with an
    explicit ``start_time`` inside ``[now, now + horizon]`` count; events without
    a start time count only if created within the horizon window (treated as
    active now). Ties on severity break toward the nearer event.
    """
    if market_id is None:
        return None, None
    horizon_end = now + timedelta(hours=horizon_hours)
    rows = list(
        db.scalars(
            select(Event)
            .where(Event.market_id == market_id)
            .order_by(Event.created_at.desc())
            .limit(50)
        ).all()
    )
    best: Event | None = None
    best_rank = -1
    best_hours: float | None = None
    for ev in rows:
        when = _as_utc(ev.start_time)
        if when is not None:
            if when < now or when > horizon_end:
                continue
            hours = (when - now).total_seconds() / 3600.0
        else:
            created = _as_utc(ev.created_at)
            if created is None or (now - created).total_seconds() > horizon_hours * 3600:
                continue
            hours = 0.0
        rank = _SEVERITY_RANK.get((ev.severity or "").strip().lower(), 1)
        nearer = best_hours is None or hours < best_hours
        if rank > best_rank or (rank == best_rank and nearer):
            best, best_rank, best_hours = ev, rank, hours
    if best is None:
        return None, None
    label = (best.title or best.event_type or "event").strip().replace("_", " ")
    if best_hours and best_hours >= 1:
        reason = f"{label} catalyst in {best_hours:.0f}h"
    else:
        reason = f"{label} catalyst active now"
    hours_out = round(best_hours, 1) if best_hours is not None else None
    return hours_out, reason


def _default_reason(result: dict[str, Any], kind: str) -> str:
    edge = float(result.get("edge_score", 0.0) or 0.0)
    gate = result.get("decision_gate") or {}
    if kind == "opportunity":
        return f"Reward/risk edge {edge:.2f}; gate: {gate.get('action', 'watch')}"
    reasons = gate.get("reasons") or []
    if reasons:
        return str(reasons[0])
    return f"Thin or negative edge ({edge:.2f})"


def _score_item(
    result: dict[str, Any],
    cal_status: str,
    hours_to_catalyst: float | None,
    reason: str | None,
    horizon_hours: int,
) -> RadarItem:
    """Build a ranked RadarItem from an assessment.

    Composite:
        base        = edge_score                          # already risk-normalised
        cal_gate    = trust multiplier from calibration   # _CAL_GATE
        catalyst    = catalyst_severity * proximity       # proximity in [0,1]
        radar_score = base * cal_gate + 0.5 * catalyst
    """
    edge = float(result.get("edge_score", 0.0) or 0.0)
    catalyst_sev = float(result.get("catalyst_severity", 0.0) or 0.0)
    cal_gate = _CAL_GATE.get(cal_status, 0.6)
    if hours_to_catalyst is None:
        catalyst_term = 0.0
    else:
        proximity = max(0.0, 1.0 - (hours_to_catalyst / max(horizon_hours, 1)))
        catalyst_term = catalyst_sev * proximity
    radar_score = edge * cal_gate + 0.5 * catalyst_term

    gate = result.get("decision_gate") or {}
    blocked = gate.get("action") == "block"
    likely = float(result.get("likely_gbp", 0.0) or 0.0)
    is_opportunity = (likely > 0) and (radar_score > 0) and not blocked
    kind = "opportunity" if is_opportunity else "threat"
    resolved_reason = reason or _default_reason(result, kind)

    return RadarItem(
        market_code=result["market_code"],
        market_name=str(result.get("market_name", result["market_code"])),
        direction=str(result.get("direction", "long")),
        risk_gbp=float(result.get("risk_gbp", 0.0) or 0.0),
        likely_gbp=likely,
        upside_gbp=float(result.get("upside_gbp", 0.0) or 0.0),
        edge_score=round(edge, 3),
        confidence=round(float(result.get("confidence", 0.0) or 0.0), 3),
        regime=str(result.get("regime", "unknown")),
        catalyst_severity=round(catalyst_sev, 3),
        calibration_status=cal_status,
        hours_to_catalyst=hours_to_catalyst,
        radar_score=round(radar_score, 4),
        kind=kind,
        reason=resolved_reason,
    )


def _assess(
    db: Session,
    *,
    market_code: str,
    position_gbp: float,
    direction: str,
    horizon_hours: int,
) -> dict[str, Any] | None:
    from app.services.risk_engine import RiskInputs, assess_risk  # lazy: see module note

    try:
        return assess_risk(
            db,
            RiskInputs(
                market_code=market_code,
                position_gbp=position_gbp,
                horizon_hours=horizon_hours,
                target_timestamp=None,
                direction=direction,
                position_unit="GBP",
                hedge_ratio=1.0,
                n_paths=RADAR_SCAN_N_PATHS,
                random_seed=_stable_seed(market_code),
            ),
        )
    except Exception as exc:  # noqa: BLE001 - one bad market must not sink the scan
        logger.warning("radar assess failed for %s/%s: %s", market_code, direction, exc)
        return None


def _scan_market(
    db: Session, market: Market, *, horizon_hours: int, unit_position_gbp: float, now: datetime
) -> RadarItem | None:
    """Assess both directions at a unit position; keep the higher-edge side."""
    best: dict[str, Any] | None = None
    for direction in ("long", "short"):
        result = _assess(
            db,
            market_code=market.code,
            position_gbp=unit_position_gbp,
            direction=direction,
            horizon_hours=horizon_hours,
        )
        if result is None:
            continue
        if best is None or float(result.get("edge_score", -1e9) or -1e9) > float(
            best.get("edge_score", -1e9) or -1e9
        ):
            best = result
    if best is None:
        return None
    cal_status = _cal_status(db, market.id)
    hours_to_catalyst, reason = _imminent_event(db, market.id, now, horizon_hours)
    return _score_item(best, cal_status, hours_to_catalyst, reason, horizon_hours)


def _book_threats(
    db: Session, user_id: int | None, *, horizon_hours: int, now: datetime
) -> list[RadarItem]:
    """Threats derived from the user's OPEN positions: risk that has grown
    versus the booked read, or a maturing catalyst on a held market."""
    if user_id is None:
        return []
    try:
        decisions = list_decisions(db, user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("radar book lookup failed: %s", exc)
        return []

    threats: list[RadarItem] = []
    for d in decisions:
        if not d.get("is_open"):
            continue
        code = d["market_code"]
        result = _assess(
            db,
            market_code=code,
            position_gbp=float(d.get("position_gbp") or 0.0),
            direction=str(d.get("direction", "long")),
            horizon_hours=int(d.get("horizon_hours") or horizon_hours),
        )
        if result is None:
            continue
        booked_risk = float(d.get("risk_gbp") or 0.0)
        live_risk = float(result.get("risk_gbp", 0.0) or 0.0)
        hours_to_catalyst, ev_reason = _imminent_event(db, d.get("market_id"), now, horizon_hours)
        risk_grew = booked_risk > 0 and live_risk > booked_risk * _BOOK_RISK_THREAT_RATIO
        if not (risk_grew or hours_to_catalyst is not None):
            continue
        if risk_grew:
            reason = (
                f"Open {d.get('direction', 'long')} risk rose to "
                f"£{live_risk:,.0f} (booked £{booked_risk:,.0f})"
            )
        else:
            reason = ev_reason or "Catalyst maturing on an open position"
        cal_status = _cal_status(db, d.get("market_id"))
        item = _score_item(result, cal_status, hours_to_catalyst, reason, horizon_hours)
        item.kind = "threat"
        item.reason = reason
        threats.append(item)
    return threats


def compute_radar(
    db: Session,
    *,
    user_id: int | None = None,
    horizon_hours: int = RADAR_DEFAULT_HORIZON_H,
    unit_position_gbp: float = RADAR_UNIT_POSITION_GBP,
) -> dict[str, Any]:
    """Scan every market and return ranked Opportunities and Threats.

    Shape:
        {
          "generated_at": datetime,
          "horizon_hours": int,
          "universe_count": int,
          "failed": list[str],          # market codes that errored out
          "opportunities": list[dict],  # RadarItem dicts, radar_score desc
          "threats": list[dict],        # RadarItem dicts, catalyst-first then risk
        }
    """
    now = datetime.now(timezone.utc)
    markets = list(db.scalars(select(Market).order_by(Market.code.asc())).all())
    opportunities: list[RadarItem] = []
    generic_threats: list[RadarItem] = []
    failed: list[str] = []

    for market in markets:
        try:
            item = _scan_market(
                db,
                market,
                horizon_hours=horizon_hours,
                unit_position_gbp=unit_position_gbp,
                now=now,
            )
        except Exception as exc:  # noqa: BLE001 - isolate per-market failures
            logger.warning("radar market scan errored for %s: %s", market.code, exc)
            item = None
        if item is None:
            failed.append(market.code)
            continue
        (opportunities if item.kind == "opportunity" else generic_threats).append(item)

    book_threats = _book_threats(db, user_id, horizon_hours=horizon_hours, now=now)
    book_codes = {t.market_code for t in book_threats}
    # A book threat supersedes a generic read for the same market, in both lists.
    threats = book_threats + [t for t in generic_threats if t.market_code not in book_codes]
    opportunities = [o for o in opportunities if o.market_code not in book_codes]

    opportunities.sort(key=lambda i: i.radar_score, reverse=True)
    threats.sort(
        key=lambda i: (0 if i.hours_to_catalyst is None else 1, i.risk_gbp),
        reverse=True,
    )

    return {
        "generated_at": now,
        "horizon_hours": horizon_hours,
        "universe_count": len(markets),
        "failed": failed,
        "opportunities": [asdict(i) for i in opportunities[:RADAR_TOP_N]],
        "threats": [asdict(i) for i in threats[:RADAR_TOP_N]],
    }
