from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn


MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "deep_hedger.pt"


@dataclass
class HedgeFeatures:
    spot: float
    sigma_hourly: float
    drift_hourly: float
    tail_multiplier: float
    asymmetry: float
    catalyst_severity: float
    horizon_hours: float


class DeepHedgePolicy(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(7, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.net(features).squeeze(-1)


def feature_tensor(features: HedgeFeatures | list[HedgeFeatures]) -> torch.Tensor:
    items = features if isinstance(features, list) else [features]
    rows = [
        [
            item.spot / 250.0,
            item.sigma_hourly * 20.0,
            item.drift_hourly * 200.0,
            item.tail_multiplier / 2.5,
            item.asymmetry,
            item.catalyst_severity,
            item.horizon_hours / 168.0,
        ]
        for item in items
    ]
    return torch.tensor(rows, dtype=torch.float32)


def recommend_hedge_ratio(features: HedgeFeatures, model_path: Path = MODEL_PATH) -> float:
    policy = load_policy(model_path)
    with torch.no_grad():
        ratio = float(policy(feature_tensor(features))[0].item())
    return float(np.clip(ratio, 0.0, 1.0))


def load_policy(model_path: Path = MODEL_PATH) -> DeepHedgePolicy:
    policy = DeepHedgePolicy()
    if model_path.exists():
        state = torch.load(model_path, map_location="cpu")
        policy.load_state_dict(state)
    else:
        _initialize_conservative_policy(policy)
    policy.eval()
    return policy


def train_policy(
    *,
    n_scenarios: int = 50_000,
    epochs: int = 80,
    batch_size: int = 512,
    seed: int = 7,
    output_path: Path = MODEL_PATH,
) -> DeepHedgePolicy:
    torch.manual_seed(seed)
    policy = DeepHedgePolicy()
    optimizer = torch.optim.Adam(policy.parameters(), lr=0.01)
    features, raw_returns = _sample_training_scenarios(n_scenarios, seed=seed)

    for _ in range(epochs):
        order = torch.randperm(features.shape[0])
        for start in range(0, features.shape[0], batch_size):
            idx = order[start : start + batch_size]
            batch_features = features[idx]
            batch_returns = raw_returns[idx]
            hedge = policy(batch_features).unsqueeze(1)
            hedged_pnl = (1.0 - hedge) * batch_returns
            losses = -hedged_pnl
            var95 = torch.quantile(losses, 0.95, dim=1, keepdim=True)
            tail_losses = torch.where(losses >= var95, losses, torch.zeros_like(losses))
            tail_counts = torch.clamp((losses >= var95).sum(dim=1).float(), min=1.0)
            cvar95 = tail_losses.sum(dim=1) / tail_counts
            loss = cvar95.mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(policy.state_dict(), output_path)
    policy.eval()
    return policy


def evaluate_policy_cvar(
    policy: DeepHedgePolicy,
    *,
    n_scenarios: int = 2048,
    seed: int = 101,
    random_hedge: bool = False,
) -> float:
    features, raw_returns = _sample_training_scenarios(n_scenarios, seed=seed)
    with torch.no_grad():
        if random_hedge:
            generator = torch.Generator().manual_seed(seed + 99)
            hedge = torch.rand((n_scenarios, 1), generator=generator)
        else:
            hedge = policy(features).unsqueeze(1)
        hedged_pnl = (1.0 - hedge) * raw_returns
        losses = -hedged_pnl
        var95 = torch.quantile(losses, 0.95, dim=1, keepdim=True)
        tail_losses = torch.where(losses >= var95, losses, torch.zeros_like(losses))
        tail_counts = torch.clamp((losses >= var95).sum(dim=1).float(), min=1.0)
        cvar95 = tail_losses.sum(dim=1) / tail_counts
    return float(cvar95.mean().item())


def _sample_training_scenarios(n_scenarios: int, *, seed: int) -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator().manual_seed(seed)
    spot = torch.empty(n_scenarios, 1).uniform_(30.0, 180.0, generator=generator)
    sigma_hourly = torch.empty(n_scenarios, 1).uniform_(0.005, 0.12, generator=generator)
    drift_hourly = torch.empty(n_scenarios, 1).uniform_(-0.012, 0.012, generator=generator)
    tail_multiplier = torch.empty(n_scenarios, 1).uniform_(1.0, 2.0, generator=generator)
    asymmetry = torch.empty(n_scenarios, 1).uniform_(-1.0, 1.0, generator=generator)
    catalyst = torch.empty(n_scenarios, 1).uniform_(0.0, 1.0, generator=generator)
    horizon = torch.randint(1, 73, (n_scenarios, 1), generator=generator).float()

    features = torch.cat(
        [
            spot / 250.0,
            sigma_hourly * 20.0,
            drift_hourly * 200.0,
            tail_multiplier / 2.5,
            asymmetry,
            catalyst,
            horizon / 168.0,
        ],
        dim=1,
    )

    n_paths = 96
    shocks = torch.randn((n_scenarios, n_paths), generator=generator)
    tail_scale = tail_multiplier * sigma_hourly * torch.sqrt(horizon)
    directional_bias = asymmetry * catalyst * sigma_hourly * horizon * 0.05
    horizon_return = (drift_hourly * horizon) + directional_bias + tail_scale * shocks
    raw_pnl = 10_000.0 * horizon_return
    return features, raw_pnl


def _initialize_conservative_policy(policy: DeepHedgePolicy) -> None:
    with torch.no_grad():
        for param in policy.parameters():
            param.zero_()
        final_layer = policy.net[-2]
        if isinstance(final_layer, nn.Linear):
            final_layer.bias.fill_(1.2)


def hedge_features_from_assessment(assessment: dict[str, Any]) -> HedgeFeatures:
    horizon = max(float(assessment.get("horizon_hours", 1.0) or 1.0), 1.0)
    return HedgeFeatures(
        spot=float(assessment.get("spot_price", 100.0) or 100.0),
        sigma_hourly=float(assessment.get("sigma_hourly_pct", 0.0) or 0.0) / 100.0,
        drift_hourly=(float(assessment.get("expected_return_pct", 0.0) or 0.0) / 100.0) / horizon,
        tail_multiplier=float(assessment.get("tail_multiplier", 1.0) or 1.0),
        asymmetry=float(assessment.get("asymmetry", 0.0) or 0.0),
        catalyst_severity=float(assessment.get("catalyst_severity", 0.0) or 0.0),
        horizon_hours=horizon,
    )
