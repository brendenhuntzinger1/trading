"""S3 (EXPLORATORY ONLY): opening-range breakout in stocks in play, on the 60 days
of 5-minute bars Yahoo serves. It cannot pass the evidence standard; 60 days is
far too short and the window was chosen by data availability, not design.

Session d: first 5-min bar (09:30-09:35 ET). RVOL = its volume / mean first-bar
volume over the previous 14 sessions. Stocks in play: RVOL >= 1, top 20 by RVOL,
price > $5. Long-only: if the first bar closed above its open, buy at the 09:35
bar's open; stop at the first bar's low (filled at the stop, or at the bar open if
it gaps through); otherwise exit at the 15:55 bar's close. Size: 1% of equity at
risk per trade, capped at 20% per position and 100% gross (scaled down pro rata).
Costs 5 bp per side (intraday market orders).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stocks_data import load

COST = 0.0005


def trades(syms: list[str], top: int = 20, lookback: int = 14) -> pd.DataFrame:
    first, bars = {}, {}
    for s in syms:
        try:
            m = load(s, "m5")
        except FileNotFoundError:
            continue
        m["session"] = pd.to_datetime(m.time_et.str[:10])
        m["hhmm"] = m.time_et.str[11:16]
        bars[s] = m
        f = m[m.hhmm == "09:30"].set_index("session")
        first[s] = f[["open", "high", "low", "close", "volume"]]
    vol = pd.DataFrame({s: f.volume for s, f in first.items()})
    rvol = vol / vol.rolling(lookback).mean().shift(1)
    rows = []
    for d in rvol.index[lookback:]:
        cand = rvol.loc[d].dropna()
        cand = cand[cand >= 1.0].sort_values(ascending=False).iloc[:top]
        picks = []
        for s in cand.index:
            fb = first[s].loc[d]
            if fb.close <= fb.open or fb.close < 5:
                continue
            day = bars[s][(bars[s].session == d) & (bars[s].hhmm > "09:30")].sort_values("time_et")
            if day.empty:
                continue
            entry, stop = day.open.iloc[0], fb.low
            if entry <= stop:
                continue
            exit_px, exit_t = day.close.iloc[-1], day.index[-1]
            for t, b in day.iterrows():
                if b.low <= stop:
                    exit_px, exit_t = min(stop, b.open), t
                    break
            w = min(0.01 / ((entry - stop) / entry), 0.20)
            picks.append([d, s, "long", entry, day.index[0], exit_px, exit_t, w])
        tot = sum(p[-1] for p in picks)
        for p in picks:
            if tot > 1.0:
                p[-1] /= tot
            rows.append(p)
    t = pd.DataFrame(rows, columns=["session", "symbol", "side", "entry_px", "entry_time_utc", "exit_px", "exit_time_utc", "size_weight"])
    t["gross_ret"] = t.exit_px / t.entry_px - 1
    t["net_ret"] = t.exit_px * (1 - COST) / (t.entry_px * (1 + COST)) - 1
    t["cost"] = t.gross_ret - t.net_ret
    return t
