"""Expanding-window walk-forward parameter selection.

Each configuration is simulated once over the full sample (signals are causal,
so the returns on any day depend only on data up to that day). For each test
year the configuration with the best training objective is chosen using data
that ends `embargo_days` before the test year, and that year's returns are
taken from its run. The trade needed to switch configuration at the year
boundary is charged approximately via `switch_cost`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pandas as pd


def sharpe_objective(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.mean() / r.std() * math.sqrt(365)) if len(r) > 30 and r.std() > 0 else float("-inf")


def yearly_splits(first_test_year: int, last_test_year: int, start: str = "2018-01-01", last_end: str | None = None):
    out = []
    for y in range(first_test_year, last_test_year + 1):
        end = f"{y}-12-31" if (y < last_test_year or last_end is None) else last_end
        out.append((start, f"{y - 1}-12-31", f"{y}-01-01", end))
    return out


@dataclass
class WalkForwardResult:
    returns: pd.Series
    chosen: list            # (test_year_start, config index, train objective)
    train_scores: list      # per split: {config index: objective}


def walk_forward(runs: dict[int, pd.Series], weights: dict[int, pd.Series] | None, splits,
                 objective: Callable[[pd.Series], float] = sharpe_objective, embargo_days: int = 0,
                 switch_cost: float = 0.0066) -> WalkForwardResult:
    """runs: config index -> full-sample daily net returns. weights (optional): config index ->
    total exposure series, used to charge the switch at each boundary."""
    pieces, chosen, scores_all, prev = [], [], [], None
    for tr_s, tr_e, te_s, te_e in splits:
        cut = pd.Timestamp(tr_e, tz="UTC") - pd.Timedelta(days=embargo_days)
        begin = pd.Timestamp(tr_s, tz="UTC")
        scores = {k: objective(r.loc[begin:cut]) for k, r in runs.items()}
        best = max(scores, key=scores.get)
        piece = runs[best].loc[te_s:te_e].copy()
        if prev is not None and prev != best and weights is not None and len(piece):
            t0 = piece.index[0]
            dw = abs(weights[best].asof(t0) - weights[prev].asof(t0))
            piece.iloc[0] -= dw * switch_cost
        pieces.append(piece)
        chosen.append((te_s, best, scores[best]))
        scores_all.append(scores)
        prev = best
    return WalkForwardResult(pd.concat(pieces), chosen, scores_all)
