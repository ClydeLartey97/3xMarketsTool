from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.forecasting.base import ForecastModel


class ChronosForecastModel(ForecastModel):
    _PIPELINE_CACHE: ClassVar[dict[tuple[str, str], Any]] = {}
    _SAMPLE_COUNT = 100

    def __init__(self) -> None:
        self.model_id = self._resolve_model_id()
        self.model_name = f"{self.model_id.removeprefix('amazon/')}-v1"
        self.metrics: dict[str, float] = {}
        self._context = np.array([], dtype=float)
        self.residual_std = 12.0

    def _resolve_model_id(self) -> str:
        settings = get_settings()
        return "amazon/chronos-bolt-small" if settings.chronos_use_small else "amazon/chronos-bolt-tiny"

    def _load_pipeline(self) -> Any:
        settings = get_settings()
        device_map = settings.chronos_device_map.strip().lower() or "cpu"
        cache_key = (self.model_id, device_map)
        cached = self._PIPELINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        import chronos
        import torch

        kwargs: dict[str, Any] = {"device_map": device_map}
        if device_map in {"cuda", "mps"}:
            kwargs["torch_dtype"] = torch.bfloat16
        pipeline = chronos.ChronosBoltPipeline.from_pretrained(self.model_id, **kwargs)
        self._PIPELINE_CACHE[cache_key] = pipeline
        return pipeline

    def train(self, frame: pd.DataFrame) -> dict[str, float]:
        if frame.empty or "price_value" not in frame.columns:
            self._context = np.array([], dtype=float)
            self.metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "spike_precision": 0.0}
            return self.metrics

        self._context = frame["price_value"].astype(float).dropna().tail(2048).to_numpy()
        if "price_lag_24" not in frame.columns:
            self.metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "spike_precision": 0.0}
            return self.metrics

        preds = frame["price_lag_24"].astype(float)
        actual = frame["price_value"].astype(float)
        residuals = actual - preds
        self.residual_std = float(max(residuals.std(ddof=0), 4.0))
        baseline_prev = frame["price_lag_1"].astype(float)
        direction = ((preds - baseline_prev) > 0) == ((actual - baseline_prev) > 0)
        self.metrics = {
            "mae": round(float(np.mean(np.abs(residuals))), 2),
            "rmse": round(float(np.sqrt(np.mean(np.square(residuals)))), 2),
            "directional_accuracy": round(float(direction.mean()), 3),
            "spike_precision": 0.0,
        }
        return self.metrics

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        return self.predict_distribution(frame)["point_estimate"]

    def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
        horizon = int(frame.shape[0])
        columns = ["point_estimate", "lower_bound", "upper_bound", "sigma_price"]
        if horizon == 0:
            return pd.DataFrame(columns=columns, index=frame.index)

        quantile_forecast, quantile_levels = self._chronos_quantiles(horizon, frame)
        samples = self._sample_paths_from_quantiles(quantile_forecast, quantile_levels)
        point = np.quantile(samples, 0.5, axis=0)
        lower = np.quantile(samples, 0.05, axis=0)
        upper = np.quantile(samples, 0.95, axis=0)
        sigma = np.maximum(np.std(samples, axis=0, ddof=0), 1e-6)

        return pd.DataFrame(
            {
                "point_estimate": point,
                "lower_bound": lower,
                "upper_bound": upper,
                "sigma_price": sigma,
            },
            index=frame.index,
        )

    def _chronos_quantiles(self, horizon: int, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        pipeline = self._load_pipeline()
        context = self._context
        if context.size == 0 and "price_lag_24" in frame.columns:
            context = frame["price_lag_24"].astype(float).to_numpy()
        if context.size == 0:
            context = np.zeros(1, dtype=float)

        try:
            import torch

            context_input: Any = torch.tensor(context, dtype=torch.float32)
        except ImportError:
            context_input = context

        raw_forecast = pipeline.predict(context_input, prediction_length=horizon)
        forecast = self._to_numpy(raw_forecast)
        if forecast.ndim == 3:
            forecast = forecast[0]
        if forecast.ndim != 2:
            raise ValueError(f"Chronos forecast must have 2 or 3 dimensions, got {forecast.ndim}")
        if forecast.shape[1] != horizon and forecast.shape[0] == horizon:
            forecast = forecast.T
        if forecast.shape[1] != horizon:
            raise ValueError(f"Chronos forecast horizon mismatch: expected {horizon}, got {forecast.shape[1]}")

        quantile_levels = np.asarray(getattr(pipeline, "quantiles", []), dtype=float)
        if quantile_levels.size != forecast.shape[0]:
            quantile_levels = np.linspace(0.1, 0.9, forecast.shape[0], dtype=float)
        order = np.argsort(quantile_levels)
        return forecast[order], quantile_levels[order]

    def _sample_paths_from_quantiles(self, quantile_forecast: np.ndarray, quantile_levels: np.ndarray) -> np.ndarray:
        sample_levels = (np.arange(self._SAMPLE_COUNT, dtype=float) + 0.5) / self._SAMPLE_COUNT
        samples = np.empty((self._SAMPLE_COUNT, quantile_forecast.shape[1]), dtype=float)
        for step in range(quantile_forecast.shape[1]):
            step_quantiles = quantile_forecast[:, step]
            samples[:, step] = np.interp(
                sample_levels,
                quantile_levels,
                step_quantiles,
                left=float(step_quantiles[0]),
                right=float(step_quantiles[-1]),
            )
        return samples

    def _to_numpy(self, value: Any) -> np.ndarray:
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        return np.asarray(value, dtype=float)

    def explain(self, row: pd.Series) -> str:
        return "Chronos-Bolt zero-shot forecast from recent market price context."
