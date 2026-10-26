"""Channel breakout with a volatility-based trailing stop."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import StrategySpec


def atr(df: pd.DataFrame, n: int = 20) -> pd.Series:
    prev = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - prev).abs(), (df.low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def breakout_signal(df, entry_n=50, stop_atr=3.0, target_vol=0.40, step=0.25, bpy=365):
    hi = df.high.rolling(entry_n).max().shift(1).to_numpy()
    a = atr(df).to_numpy()
    vol = (df.close.pct_change().rolling(30).std() * np.sqrt(bpy)).to_numpy()
    close = df.close.to_numpy()
    out = np.zeros(len(df))
    size, peak = 0.0, 0.0
    for i, c in enumerate(close):
        if size == 0.0:
            if not np.isnan(hi[i]) and c > hi[i] and not np.isnan(vol[i]) and vol[i] > 0:
                s = round(min(1.0, target_vol / vol[i]) / step) * step   # size fixed at entry
                if s > 0:
                    size, peak = s, c
        else:
            peak = max(peak, c)
            if c < peak - stop_atr * a[i]:
                size = 0.0
        out[i] = size
    return pd.Series(out, index=df.index)


def breakout(entry_n=50, stop_atr=3.0, target_vol=0.40) -> StrategySpec:
    return StrategySpec(
        name=f"breakout_{entry_n}_atr{stop_atr:g}_vol{round(target_vol * 100)}",
        hypothesis=("New multi-week highs mark the start of persistent moves (trend continuation driven by "
                    "slow-moving capital and momentum flows). Unlike the baseline's continuous vote, this trades "
                    "rarely: one entry per breakout, held until a volatility-scaled trailing stop, so fewer "
                    "orders and lower fee drag."),
        entry=f"Daily close above the highest high of the previous {entry_n} days.",
        exit=f"Daily close below (highest close since entry - {stop_atr:g} x ATR(20)).",
        sizing=f"min(1, {target_vol:.0%} / 30-day realized vol), rounded to 0.25, fixed for the life of the trade.",
        holding_period="Weeks to a few months.",
        failure_conditions="False breakouts in ranges; gap-downs through the stop; sideways markets.",
        params={"entry_n": entry_n, "stop_atr": stop_atr, "target_vol": target_vol},
        signal=lambda df: breakout_signal(df, entry_n, stop_atr, target_vol),
    )
