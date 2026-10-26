"""Daily short-term mean reversion inside a longer uptrend."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import StrategySpec


def rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def meanrev_signal(df, trend_n=200, rsi_n=2, entry=10.0, max_hold=10, target_vol=0.40, step=0.25, bpy=365):
    r = rsi(df.close, rsi_n).to_numpy()
    trend = (df.close > df.close.rolling(trend_n).mean()).to_numpy()
    ma5 = df.close.rolling(5).mean().to_numpy()
    vol = (df.close.pct_change().rolling(30).std() * np.sqrt(bpy)).to_numpy()
    close = df.close.to_numpy()
    out = np.zeros(len(df))
    size, held = 0.0, 0
    for i, c in enumerate(close):
        if size == 0.0:
            if trend[i] and r[i] < entry and vol[i] > 0:
                s = round(min(1.0, target_vol / vol[i]) / step) * step
                if s > 0:
                    size, held = s, 0
        else:
            held += 1
            if c > ma5[i] or held >= max_hold or not trend[i]:
                size = 0.0
        out[i] = size
    return pd.Series(out, index=df.index)


def meanrev(trend_n=200, rsi_n=2, entry=10.0, max_hold=10) -> StrategySpec:
    return StrategySpec(
        name=f"meanrev_t{trend_n}_rsi{rsi_n}_{entry:g}_h{max_hold}",
        hypothesis=("Within an established uptrend, sharp 1-3 day selloffs are often liquidity-driven (forced "
                    "selling, liquidations) and partly reverse within days. One buy per dip, no averaging down."),
        entry=f"Close > SMA({trend_n}) and RSI({rsi_n}) < {entry:g}.",
        exit=f"Close > 5-day SMA, or {max_hold} days elapsed, or trend filter turns off.",
        sizing="min(1, 40% / 30-day vol), rounded to 0.25, fixed at entry. A single entry; no adds.",
        holding_period="1-10 days.",
        failure_conditions=("Dips that are the start of a crash (trend filter lags); fee drag from frequent "
                            "round trips (~1.3% per round trip at taker rates)."),
        params={"trend_n": trend_n, "rsi_n": rsi_n, "entry": entry, "max_hold": max_hold},
        signal=lambda df: meanrev_signal(df, trend_n, rsi_n, entry, max_hold),
    )
