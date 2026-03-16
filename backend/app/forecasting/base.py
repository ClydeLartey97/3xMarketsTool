from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class ForecastModel(ABC):
    @abstractmethod
    def train(self, frame: pd.DataFrame) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def predict(self, frame: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    @abstractmethod
    def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def explain(self, row: pd.Series) -> str:
        raise NotImplementedError
