from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class StrategySpec:
    """A strategy is a hypothesis with rules, not just a signal function."""
    name: str
    hypothesis: str
    entry: str
    exit: str
    sizing: str
    holding_period: str
    failure_conditions: str
    params: dict = field(default_factory=dict)
    signal: Callable[[pd.DataFrame], pd.Series] | None = None  # OHLCV -> target weight in [0, 1]

    def __call__(self, df: pd.DataFrame) -> pd.Series:
        return self.signal(df).reindex(df.index).fillna(0.0).clip(0, 1)
