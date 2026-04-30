"""Monte Carlo price-path simulator for the risk engine.

Generates `n_paths` simulated forward price paths over `horizon_hours`,
respecting:

  - hourly volatility (in log-return space, scaled by tail_multiplier)
  - hourly drift (log-return space)
  - heavy-tail mixing (Student-t(5)) when tail_multiplier > 1.2
  - one-sided asymmetry shift (small per-step bias driven by LLM read)

The output is a `(n_paths, horizon_hours + 1)` array of prices where
column 0 is the spot. Downstream code computes empirical P&L distributions
from this — no closed-form Gaussian assumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class SimConfig:
    n_paths: int = 5_000
    horizon_hours: int = 24
    spot: float = 100.0
    sigma_hourly: float = 0.05  # log-return σ per hour, pre-tail multiplier
    drift_hourly: float = 0.0   # log-return drift per hour
    tail_multiplier: float = 1.0
    asymmetry: float = 0.0      # in [-1, 1]; nudges drift up/down
    seed: Optional[int] = None


@dataclass
class SimResult:
    paths: np.ndarray             # (n_paths, horizon + 1)
    config: SimConfig = field(repr=False)

    @property
    def terminal_prices(self) -> np.ndarray:
        return self.paths[:, -1]

    @property
    def returns_terminal(self) -> np.ndarray:
        return (self.terminal_prices - self.config.spot) / self.config.spot


def _heavy_tail_shocks(
    rng: np.random.Generator,
    shape: tuple[int, int],
    tail_multiplier: float,
) -> np.ndarray:
    """Return unit-variance shocks. Mixes Normal and t(5) when tails inflate.

    The t(5) draw is rescaled to unit variance (t(ν) variance = ν/(ν-2)),
    so the only effect of mixing is on the kurtosis, not the σ. Variance
    inflation is separately handled by the caller via tail_multiplier on σ.
    """
    z = rng.standard_normal(size=shape)
    if tail_multiplier <= 1.2:
        return z
    # Linear blend toward t(5) as tail_multiplier rises from 1.2 → 2.0.
    weight = float(np.clip((tail_multiplier - 1.2) / 0.8, 0.0, 1.0))
    t5 = rng.standard_t(df=5, size=shape) / np.sqrt(5.0 / 3.0)  # rescale to var=1
    return (1.0 - weight) * z + weight * t5


def simulate_price_paths(cfg: SimConfig) -> SimResult:
    rng = np.random.default_rng(cfg.seed)
    h = max(1, int(cfg.horizon_hours))
    n = max(1, int(cfg.n_paths))

    sigma = max(0.0, cfg.sigma_hourly * cfg.tail_multiplier)
    # Asymmetry contributes a small per-step drift bias.
    asym_drift = 0.05 * sigma * float(np.clip(cfg.asymmetry, -1.0, 1.0))
    drift = cfg.drift_hourly + asym_drift

    shocks = _heavy_tail_shocks(rng, (n, h), cfg.tail_multiplier)
    log_returns = drift + sigma * shocks
    log_paths = np.cumsum(log_returns, axis=1)

    # Prepend a column of zeros so paths[:, 0] == spot.
    log_paths = np.concatenate([np.zeros((n, 1)), log_paths], axis=1)
    paths = max(cfg.spot, 1e-6) * np.exp(log_paths)
    return SimResult(paths=paths, config=cfg)


def pnl_from_paths(
    result: SimResult,
    *,
    direction_sign: float,
    position_native: float,
    position_unit: str = "GBP",
) -> np.ndarray:
    """Convert a path array into a P&L vector in the market's NATIVE currency.

    - position_unit == "MWh": pnl = position_mwh × (P_T − P_0) × sign
    - position_unit == "GBP" (legacy): pnl = position × (P_T − P_0)/P_0 × sign

    Returned vector is in the market's native price currency. The risk engine
    then applies FX to GBP separately.
    """
    P_T = result.terminal_prices
    P_0 = result.paths[:, 0]
    if position_unit == "MWh":
        return direction_sign * position_native * (P_T - P_0)
    # Legacy notional return-based P&L
    return direction_sign * position_native * (P_T - P_0) / np.where(P_0 == 0, 1.0, P_0)


def empirical_risk_metrics(pnl_gbp: np.ndarray) -> dict[str, float]:
    """Standard distribution summary used for the headline risk numbers."""
    if pnl_gbp.size == 0:
        return {
            "likely_gbp": 0.0,
            "upside_gbp": 0.0,
            "var95_gbp": 0.0,
            "cvar95_gbp": 0.0,
            "prob_loss": 0.0,
        }
    likely = float(np.mean(pnl_gbp))
    upside = float(np.percentile(pnl_gbp, 95))
    var_floor = float(np.percentile(pnl_gbp, 5))
    var95 = max(0.0, -var_floor)
    tail = pnl_gbp[pnl_gbp <= var_floor]
    cvar95 = max(0.0, -float(np.mean(tail))) if tail.size else var95
    prob_loss = float(np.mean(pnl_gbp < 0))
    return {
        "likely_gbp": likely,
        "upside_gbp": upside,
        "var95_gbp": var95,
        "cvar95_gbp": cvar95,
        "prob_loss": prob_loss,
    }


def empirical_max_drawdown(
    result: SimResult,
    *,
    direction_sign: float,
    position_native: float,
    position_unit: str,
    fx_to_gbp: float,
    percentile: float = 95.0,
) -> float:
    """95th-percentile worst path-running loss, in GBP."""
    P = result.paths
    P_0 = P[:, :1]
    if position_unit == "MWh":
        running_pnl = direction_sign * position_native * (P - P_0)
    else:
        running_pnl = direction_sign * position_native * (P - P_0) / np.where(P_0 == 0, 1.0, P_0)
    running_pnl_gbp = running_pnl * fx_to_gbp
    path_min = np.min(running_pnl_gbp, axis=1)
    return max(0.0, -float(np.percentile(path_min, 100 - percentile)))
