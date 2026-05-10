from __future__ import annotations

from typing import Literal

import pandas as pd

Regime = Literal["calm", "trending", "stressed"]
REGIMES: tuple[Regime, ...] = ("calm", "trending", "stressed")


def classify_regime(row: pd.Series) -> Regime:
    rolling_std = float(row.get("rolling_std_24", 0.0) or 0.0)
    rolling_mean = float(row.get("rolling_mean_24", 0.0) or 0.0)
    event_impact = float(row.get("event_impact", 0.0) or 0.0)
    if rolling_mean <= 0:
        return "calm"
    cv = rolling_std / max(rolling_mean, 1.0)
    if cv > 0.35 or event_impact > 1.0:
        return "stressed"
    if cv > 0.15:
        return "trending"
    return "calm"
