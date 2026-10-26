"""Shared helpers for the exploratory decision-quality study (DECISION_QUALITY.md)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research/intraday/crosscheck"))
from tradelab.research.metrics import stationary_bootstrap_idx  # noqa: E402

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
RT = {"S1": 0.0008, "S2": 0.0008, "S2_etf": 0.0008, "C1": 0.0106, "C2": 0.0132}   # base round trips (COSTS.md)
PERIODS = {"S2": [("dev", "2000-01-01", "2016-01-01"), ("validation", "2016-01-01", "2021-01-01"), ("test", "2021-01-01", "2027-01-01")],
           "C": [("dev", "2020-01-01", "2023-01-01"), ("validation", "2023-01-01", "2024-01-01"), ("test", "2024-01-01", "2027-01-01")]}


def period_of(day: str, kind: str) -> str:
    for name, a, b in PERIODS[kind]:
        if a <= day < b:
            return name
    return "other"


def boot_mean(values, days, n_boot: int = 2000, block: float = 10, seed: int = 0, stat=np.mean):
    """Stationary block bootstrap over days (trades on the same day stay together).
    Returns (estimate, lo95, hi95)."""
    df = pd.DataFrame({"v": np.asarray(values, float), "d": np.asarray(days)}).dropna()
    if len(df) < 3:
        return (float(df.v.mean()) if len(df) else np.nan, np.nan, np.nan)
    groups = [g.v.to_numpy() for _, g in df.groupby("d", sort=True)]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        idx = stationary_bootstrap_idx(len(groups), block, rng)
        out.append(stat(np.concatenate([groups[i] for i in idx])))
    return float(stat(df.v.to_numpy())), float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def boot_spearman(x, y, days, n_boot: int = 1000, block: float = 10, seed: int = 1):
    df = pd.DataFrame({"x": x, "y": y, "d": days}).dropna()
    if len(df) < 10:
        return (np.nan, np.nan, np.nan)
    groups = [g for _, g in df.groupby("d", sort=True)]
    rng = np.random.default_rng(seed)
    sp = lambda a, b: a.rank().corr(b.rank())             # Spearman = Pearson on ranks (no scipy needed)
    est = sp(df.x, df.y)
    out = []
    for _ in range(n_boot):
        idx = stationary_bootstrap_idx(len(groups), block, rng)
        s = pd.concat([groups[i] for i in idx])
        out.append(sp(s.x, s.y))
    return float(est), float(np.nanquantile(out, 0.025)), float(np.nanquantile(out, 0.975))


def fmt(t, pct=True, dp=3):
    k = 100 if pct else 1
    return f"{t[0] * k:+.{dp}f} [{t[1] * k:+.{dp}f}, {t[2] * k:+.{dp}f}]"


def prior_regimes(daily_close: pd.Series) -> pd.DataFrame:
    """Regime features for each day using ONLY data before that day:
    trailing 20-day realised vol of daily returns, and prior close vs its 50-day SMA."""
    r = daily_close.pct_change()
    vol = r.rolling(20).std().shift(1)
    trend = (daily_close > daily_close.rolling(50).mean()).shift(1)
    return pd.DataFrame({"vol20": vol, "trend_up": trend})
