"""Phase-E.4 tests: congestion-aware σ overlay."""
from __future__ import annotations

from app.grid.congestion import (
    _utilisation_to_sigma_multiplier,
    compute_sensitivity,
    get_sensitivity,
    invalidate_cache,
)
from app.grid.topology import seed_topology_bundle


def setup_function() -> None:
    invalidate_cache()


def test_utilisation_to_sigma_multiplier_is_monotone() -> None:
    """σ multiplier must be non-decreasing in line utilisation."""
    utils = [0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05]
    multipliers = [_utilisation_to_sigma_multiplier(u) for u in utils]
    assert multipliers == sorted(multipliers)
    # Below the 0.8 threshold, multiplier is exactly 1.0
    assert _utilisation_to_sigma_multiplier(0.5) == 1.0
    assert _utilisation_to_sigma_multiplier(0.0) == 1.0
    # Binding line gives a strictly elevated multiplier
    assert _utilisation_to_sigma_multiplier(1.0) > 1.0


def test_compute_sensitivity_for_topology_market() -> None:
    """A market that maps to a topology bus produces a sensitivity curve."""
    sens = compute_sensitivity("GB_POWER")
    assert sens is not None
    assert sens.market_code == "GB_POWER"
    assert sens.bus_name == "GB_POWER"
    assert len(sens.load_grid) == len(sens.sigma_multipliers) == len(sens.line_utilisations)
    # All multipliers should be in [1.0, 1.6]
    for m in sens.sigma_multipliers:
        assert 1.0 <= m <= 1.6


def test_compute_sensitivity_for_unknown_market_is_none() -> None:
    assert compute_sensitivity("NOT_A_MARKET") is None


def test_multiplier_at_clips_to_grid_bounds() -> None:
    sens = compute_sensitivity("GB_POWER")
    assert sens is not None
    # Multipliers at the extremes should clamp to the first/last grid points
    low = sens.multiplier_at(0.1)
    high = sens.multiplier_at(2.0)
    assert low == sens.sigma_multipliers[0]
    assert high == sens.sigma_multipliers[-1]


def test_get_sensitivity_caches_per_market() -> None:
    sens1 = get_sensitivity("GB_POWER")
    sens2 = get_sensitivity("GB_POWER")
    assert sens1 is sens2  # cache hit returns the same instance


def test_sensitivity_curve_covers_full_grid() -> None:
    sens = compute_sensitivity("EPEX_DE")
    assert sens is not None
    # Should have a multiplier per grid point regardless of OPF feasibility
    assert len(sens.sigma_multipliers) == len(sens.load_grid)
    # And the most-loaded line list should be populated
    assert len(sens.most_loaded_line) == len(sens.load_grid)
