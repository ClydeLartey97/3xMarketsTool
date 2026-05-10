"""Congestion-aware risk overlay.

The full FRONTIER.md vision is "DC-OPF per simulated path → congestion
shock → σ inflation". Running the LP 5,000 times per assessment is
both slow and wasteful — most paths produce nearly-identical line
loadings. We approximate the same effect with a small, cached
**congestion-sensitivity table**:

  1. For each market that maps to a topology bus, run DC-OPF over a
     coarse grid of load multipliers (0.6 → 1.4 in 9 steps).
  2. For each scenario, record the line-utilisation of the highest-
     loaded outgoing line from that bus.
  3. Convert utilisation to a σ-multiplier via a monotone curve:
     `1 + alpha * max(0, util - 0.8)^beta`. Lines below 80% of limit
     contribute nothing; lines binding contribute up to `1 + alpha`.

This is conservative — real per-path congestion would be more
granular — but it captures the institutional intuition that "when
the export line to PJM is close to its limit, the marginal cost of
news shocks at NYISO Zone J is higher" without the LP cost.

The output is a `CongestionSensitivity` per market, cached in-process
for 1 hour. Consumers (risk_engine.assess_risk) multiply σ_hourly by
the looked-up factor at the relevant load level.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from app.grid.dc_opf import GridTopology, solve_dc_opf
from app.grid.topology import (
    bundle_to_topology,
    load_topology_bundle,
    market_to_bus,
    seed_topology_bundle,
)


logger = logging.getLogger(__name__)


_CACHE_TTL = timedelta(hours=1)
_cache: dict[str, tuple[datetime, "CongestionSensitivity"]] = {}


# Coarse load-multiplier grid used to characterise the sigma curve.
_LOAD_GRID: tuple[float, ...] = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4)

# σ-multiplier curve constants. With α=0.5, β=1.6, a line at 100% of limit
# contributes a +20% σ inflation; at 90% it adds +1%. Well below the
# 2× tail multipliers driven by news flow but enough to make a binding
# DE↔FR interconnector visibly tighten EPEX_DE risk.
_ALPHA = 0.5
_BETA = 1.6
_UTIL_THRESHOLD = 0.8


@dataclass
class CongestionSensitivity:
    market_code: str
    bus_name: str
    load_grid: list[float]
    sigma_multipliers: list[float]  # parallel to load_grid
    line_utilisations: list[float]   # max outgoing-line utilisation per grid point
    most_loaded_line: list[tuple[str, str]]  # the line that drove each utilisation
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def multiplier_at(self, load_multiplier: float) -> float:
        """Linear interpolate the σ multiplier at an arbitrary load level."""
        if not self.sigma_multipliers:
            return 1.0
        xs = np.asarray(self.load_grid)
        ys = np.asarray(self.sigma_multipliers)
        return float(np.interp(load_multiplier, xs, ys, left=ys[0], right=ys[-1]))


def _utilisation_to_sigma_multiplier(util: float) -> float:
    over = max(0.0, util - _UTIL_THRESHOLD)
    return 1.0 + _ALPHA * (over ** _BETA) / ((1.0 - _UTIL_THRESHOLD) ** _BETA)


def _drive_load_on_bus(topology: GridTopology, bus_name: str, multiplier: float) -> GridTopology:
    """Return a copy of the topology with the named bus's load scaled."""
    out_buses = []
    for b in topology.buses:
        if b.name == bus_name:
            out_buses.append(type(b)(
                name=b.name,
                load_mw=b.load_mw * multiplier if b.load_mw > 0 else 1000.0 * multiplier,
                gen_min_mw=b.gen_min_mw,
                gen_max_mw=b.gen_max_mw,
                gen_cost_per_mwh=b.gen_cost_per_mwh,
                is_reference=b.is_reference,
            ))
        else:
            out_buses.append(b)
    return GridTopology(buses=out_buses, lines=topology.lines)


def _max_outgoing_utilisation(
    topology: GridTopology,
    bus_name: str,
    flows: dict[tuple[str, str], float],
) -> tuple[float, Optional[tuple[str, str]]]:
    """Return the highest |flow|/limit on any line touching `bus_name`."""
    best = 0.0
    best_line: Optional[tuple[str, str]] = None
    for line in topology.lines:
        if line.from_bus != bus_name and line.to_bus != bus_name:
            continue
        flow = flows.get((line.from_bus, line.to_bus), 0.0)
        if line.limit_mw <= 0 or not np.isfinite(line.limit_mw):
            continue
        util = abs(flow) / line.limit_mw
        if util > best:
            best = util
            best_line = (line.from_bus, line.to_bus)
    return float(best), best_line


def compute_sensitivity(
    market_code: str,
    *,
    bundle: Optional[dict] = None,
    load_grid: Optional[tuple[float, ...]] = None,
) -> Optional[CongestionSensitivity]:
    """Compute the σ-multiplier curve for one market against the topology.

    Returns None when the market is not part of the topology (e.g. demo
    markets) or when DC-OPF cannot be solved at any grid point.
    """
    bundle = bundle or load_topology_bundle()
    bus_name = market_to_bus(bundle, market_code)
    if bus_name is None:
        return None

    grid = load_grid or _LOAD_GRID
    topology = bundle_to_topology(bundle)

    sigma_multipliers: list[float] = []
    utilisations: list[float] = []
    most_loaded: list[tuple[str, str]] = []
    any_success = False
    for mult in grid:
        shocked = _drive_load_on_bus(topology, bus_name, mult)
        result = solve_dc_opf(shocked)
        if not result.success:
            sigma_multipliers.append(1.0)
            utilisations.append(0.0)
            most_loaded.append((bus_name, bus_name))
            continue
        util, line = _max_outgoing_utilisation(shocked, bus_name, result.flows_mw)
        sigma_multipliers.append(_utilisation_to_sigma_multiplier(util))
        utilisations.append(util)
        most_loaded.append(line or (bus_name, bus_name))
        any_success = True

    if not any_success:
        return None

    return CongestionSensitivity(
        market_code=market_code,
        bus_name=bus_name,
        load_grid=list(grid),
        sigma_multipliers=sigma_multipliers,
        line_utilisations=utilisations,
        most_loaded_line=most_loaded,
    )


def get_sensitivity(market_code: str, *, force_refresh: bool = False) -> Optional[CongestionSensitivity]:
    """1-hour-cached congestion sensitivity for a market."""
    now = datetime.now(timezone.utc)
    cached = _cache.get(market_code)
    if cached and not force_refresh:
        ts, sens = cached
        if now - ts < _CACHE_TTL:
            return sens
    sens = compute_sensitivity(market_code)
    if sens is not None:
        _cache[market_code] = (now, sens)
    return sens


def invalidate_cache() -> None:
    _cache.clear()
