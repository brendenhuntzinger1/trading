"""Drift monitors: performance decay, input distribution shift, execution quality.
They raise flags for a human; they never change strategies or risk settings."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Flag:
    name: str
    severity: str        # info | warn | alert
    detail: str


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population stability index of `actual` against `expected` (quantile bins)."""
    expected, actual = np.asarray(expected, float), np.asarray(actual, float)
    edges = np.unique(np.quantile(expected[~np.isnan(expected)], np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / max(1, np.isfinite(expected).sum())
    a = np.histogram(actual, edges)[0] / max(1, np.isfinite(actual).sum())
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def performance_decay(live: pd.Series, reference: pd.Series, min_days: int = 30) -> Flag | None:
    """Is the live mean daily return implausibly far below the backtest's, given
    the backtest's own volatility? One-sided z-test on the mean (approximate:
    crypto returns are fat-tailed, so treat as a prompt to investigate)."""
    live = live.dropna()
    if len(live) < min_days:
        return Flag("performance_decay", "info", f"{len(live)} days of paper data; need {min_days} to test")
    z = (live.mean() - reference.mean()) / (reference.std() / math.sqrt(len(live)))
    if z < -2.33:
        return Flag("performance_decay", "alert", f"paper mean return z={z:.2f} vs backtest (p<0.01)")
    if z < -1.64:
        return Flag("performance_decay", "warn", f"paper mean return z={z:.2f} vs backtest (p<0.05)")
    return None


def input_drift(reference: pd.DataFrame, recent: pd.DataFrame) -> list[Flag]:
    """PSI per feature: <0.1 stable, 0.1-0.25 moderate shift, >0.25 large shift."""
    out = []
    for c in reference.columns.intersection(recent.columns):
        v = psi(reference[c].to_numpy(), recent[c].to_numpy())
        if v > 0.25:
            out.append(Flag(f"input_drift:{c}", "alert", f"PSI {v:.2f}"))
        elif v > 0.10:
            out.append(Flag(f"input_drift:{c}", "warn", f"PSI {v:.2f}"))
    return out


def execution_quality(slippage_bps: pd.Series, assumed_bps: float, latency_ms: pd.Series,
                      max_latency_ms: float = 60_000) -> list[Flag]:
    out = []
    s = slippage_bps.dropna()
    if len(s) >= 10 and s.mean() > 2 * assumed_bps:
        out.append(Flag("execution_slippage", "alert", f"mean slippage {s.mean():.1f}bp vs {assumed_bps}bp assumed"))
    lat = latency_ms.dropna()
    if len(lat) and lat.quantile(0.9) > max_latency_ms:
        out.append(Flag("execution_latency", "warn", f"p90 decision-to-submit {lat.quantile(0.9) / 1000:.0f}s"))
    return out
