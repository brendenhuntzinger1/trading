"""Trend following: the phase-1 baseline and its components."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import StrategySpec


def above_sma(df, n):
    return (df.close > df.close.rolling(n).mean()).astype(float)


def momentum(df, n):
    return (df.close.pct_change(n) > 0).astype(float)


def donchian(df, entry, exit_):
    hi = df.high.rolling(entry).max().shift(1).to_numpy()
    lo = df.low.rolling(exit_).min().shift(1).to_numpy()
    pos, out = 0.0, np.zeros(len(df))
    for i, c in enumerate(df.close.to_numpy()):
        if pos == 0 and c > hi[i]:
            pos = 1.0
        elif pos == 1 and c < lo[i]:
            pos = 0.0
        out[i] = pos
    return pd.Series(out, index=df.index)


VOTERS = [("sma", 50), ("sma", 100), ("sma", 200), ("don", (20, 10)), ("don", (55, 20)), ("mom", 30), ("mom", 90)]


def trend_vote(df):
    """Fraction of the 7 trend rules that are long, in [0, 1]."""
    parts = []
    for kind, p in VOTERS:
        parts.append(above_sma(df, p) if kind == "sma" else momentum(df, p) if kind == "mom" else donchian(df, *p))
    return sum(parts) / len(parts)


def realized_vol(df, n=30, bpy=365):
    return df.close.pct_change().rolling(n).std() * np.sqrt(bpy)


def ensemble_signal(df, target_vol=0.40, step=0.25, bpy=365):
    size = trend_vote(df) * (target_vol / realized_vol(df, 30, bpy)).clip(upper=1)
    return (size / step).round() * step


BASELINE = StrategySpec(
    name="ensemble_vol40",
    hypothesis=("Crypto returns show time-series momentum: assets in a multi-week uptrend have "
                "higher subsequent returns and, more importantly, crashes tend to occur after trends "
                "break. Averaging 7 trend rules avoids choosing one lookback in hindsight; scaling to "
                "~40% annualised volatility cuts exposure when risk is highest."),
    entry="Daily close. Weight = (share of 7 trend rules long) x min(1, 40% / 30-day realized vol), rounded to 0.25.",
    exit="Same rule: weight falls as rules turn off or volatility rises; 0 when no rule is long.",
    sizing="Per asset 0-100% of its sleeve; BTC and ETH sleeves 50/50, long-only spot, no leverage.",
    holding_period="Weeks to months; ~2 weight changes per asset per month.",
    failure_conditions=("Choppy sideways markets (whipsaw costs), sharp V-shaped reversals after exits, "
                        "fees above ~1% per side, trend premium disappearing as markets mature."),
    params={"voters": VOTERS, "target_vol": 0.40, "vol_window": 30, "step": 0.25},
    signal=ensemble_signal,
)

BUY_HOLD = StrategySpec(
    name="buy_hold", hypothesis="Benchmark: crypto beta.", entry="Day 1.", exit="Never.",
    sizing="100% of sleeve.", holding_period="Whole sample.", failure_conditions="Bear markets.",
    signal=lambda df: pd.Series(1.0, index=df.index),
)

SMA200 = StrategySpec(
    name="above_sma200", hypothesis="Simplest trend filter benchmark.",
    entry="Close > 200-day SMA.", exit="Close < 200-day SMA.", sizing="0 or 100% of sleeve.",
    holding_period="Months.", failure_conditions="Whipsaw around the average.",
    signal=lambda df: above_sma(df, 200),
)

VOL_ONLY = StrategySpec(
    name="vol_target_only", hypothesis="Ablation: volatility sizing without any trend signal.",
    entry="Always long.", exit="Never fully.", sizing="min(1, 40% / 30-day vol), rounded to 0.25.",
    holding_period="Continuous.", failure_conditions="Bear markets with moderate volatility.",
    signal=lambda df: ((0.40 / realized_vol(df)).clip(upper=1) / 0.25).round() * 0.25,
)

TREND_ONLY = StrategySpec(
    name="trend_vote_only", hypothesis="Ablation: the 7-rule trend vote without volatility sizing.",
    entry="Share of rules long.", exit="As rules turn off.", sizing="Vote fraction, rounded to 0.25.",
    holding_period="Weeks to months.", failure_conditions="Whipsaw; full volatility exposure.",
    signal=lambda df: (trend_vote(df) / 0.25).round() * 0.25,
)
