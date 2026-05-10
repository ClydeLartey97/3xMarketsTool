from __future__ import annotations

import math

from app.services.correlation import get_correlation_matrix


def test_cross_market_correlation_matrix_has_gb_vs_ercot(db_session) -> None:
    matrix = get_correlation_matrix(db_session, lookback_hours=24 * 30, force_refresh=True)

    assert "GB_POWER" in matrix
    assert "ERCOT_NORTH" in matrix["GB_POWER"]
    value = matrix["GB_POWER"]["ERCOT_NORTH"]
    assert math.isfinite(value)
    assert -1.0 <= value <= 1.0
    assert abs(value) > 1e-6
