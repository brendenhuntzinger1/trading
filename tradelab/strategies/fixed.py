"""Fixed allocation: hold a constant fraction, rebalance only on drift beyond
the engine's band (2% by default)."""
from __future__ import annotations

import pandas as pd

from .base import StrategySpec


def fixed(weight: float) -> StrategySpec:
    return StrategySpec(
        name=f"fixed_{round(weight * 100)}",
        hypothesis=("No timing skill is assumed. A constant, modest allocation to a volatile asset earns its "
                    "long-run drift at a chosen risk level; rebalancing a volatile, partly mean-reverting asset "
                    "back to a fixed weight can add a small rebalancing return. In the audit this beat the trend "
                    "baseline on all three holdout coins."),
        entry="Day 1: buy to the target weight.",
        exit="Never by signal; rebalance to target when drift exceeds the band.",
        sizing=f"{weight:.0%} of the sleeve in the asset, rest in USD cash.",
        holding_period="Indefinite.",
        failure_conditions="Long bear markets (it stays invested); assets that go to zero (it keeps rebalancing into them).",
        params={"weight": weight},
        signal=lambda df: pd.Series(weight, index=df.index),
    )
