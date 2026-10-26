"""S2: overnight gap reversal in large caps (INTRADAY_HYPOTHESES.md, with Amendment 1).

At the official open of session t (signal known only after the opening print):
  gap_i = open_t / close_{t-1} - 1 - (SPY open_t / SPY close_{t-1} - 1)
Eligible: close_{t-1} > $10, median(close*volume) over the 20 sessions ending t-1 > $50M,
          gap_i <= -threshold.
Buy the `top` most negative with a marketable order right after the open (filled at
the official open + intraday market-order cost), sell at the close auction (MOC).
Equal weight 1/top of equity each (at most 20%); unused slots stay in cash.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stocks_common import et_to_utc, net_return

COSTS = {  # per side: (entry marketable after open, exit MOC)
    "base": (0.0005, 0.0003), "stress": (0.0015, 0.0009), "wide_open": (0.0010, 0.0003),
}


def signals(px: dict, market: str = "SPY", threshold: float = 0.01, min_price: float = 10.0,
            min_dollar_vol: float = 50e6) -> pd.DataFrame:
    """Relative gap per (session, symbol) where eligible, else NaN. Uses only
    data up to and including the session's open."""
    o, c, v = px["open"], px["close"], px["volume"]
    prev_c = c.shift(1)
    gap = o / prev_c - 1
    mgap = gap[market]
    rel = gap.sub(mgap, axis=0).drop(columns=[market], errors="ignore")
    dv = (c * v).rolling(20, min_periods=15).median().shift(1)
    ok = (prev_c > min_price) & (dv > min_dollar_vol) & (rel <= -threshold)
    ok &= o.notna() & c.notna()
    rel = rel.where(ok[rel.columns])
    rel = rel.where(rel.abs() < 0.5)          # >50% relative gaps on large caps are treated as data errors
    return rel


def eligible_mask(px: dict, market: str = "SPY", min_price: float = 10.0, min_dollar_vol: float = 50e6) -> pd.DataFrame:
    """Symbols tradable on the session (same liquidity filters, no gap condition): placebo pool."""
    o, c, v = px["open"], px["close"], px["volume"]
    dv = (c * v).rolling(20, min_periods=15).median().shift(1)
    m = (c.shift(1) > min_price) & (dv > min_dollar_vol) & o.notna() & c.notna()
    return m.drop(columns=[market], errors="ignore")


def trades(px: dict, start: str, end: str, top: int = 5, threshold: float = 0.01, cost: str = "base",
           universe: list[str] | None = None) -> pd.DataFrame:
    rel = signals(px, threshold=threshold)
    if universe is not None:
        rel = rel[[s for s in rel.columns if s in universe]]
    rel = rel.loc[start:end]
    picks = []
    for day, row in rel.iterrows():
        r = row.dropna().sort_values()
        for sym, g in r.iloc[:top].items():
            picks.append((day, sym, g))
    if not picks:
        return pd.DataFrame(columns=["session", "symbol", "side", "signal", "entry_time_utc", "entry_px", "exit_time_utc",
                                     "exit_px", "gross_ret", "cost", "net_ret", "size_weight"])
    t = pd.DataFrame(picks, columns=["session", "symbol", "signal"])
    t["side"] = "long"
    t["entry_px"] = [px["open"].at[d, s] for d, s in zip(t.session, t.symbol)]
    t["exit_px"] = [px["close"].at[d, s] for d, s in zip(t.session, t.symbol)]
    t["entry_time_utc"] = et_to_utc(t.session, "09:30").values
    t["exit_time_utc"] = et_to_utc(t.session, "16:00").values
    c_in, c_out = COSTS[cost]
    t["gross_ret"], t["net_ret"] = net_return(t.entry_px, t.exit_px, t.side, c_in, c_out)
    t["cost"] = t.gross_ret - t.net_ret
    t["size_weight"] = min(1.0 / top, 0.20)
    return t


def placebo_totals(px: dict, strat: pd.DataFrame, cost: str = "base", reps: int = 1000, seed: int = 5,
                   universe: list[str] | None = None) -> np.ndarray:
    """Same sessions, same number of positions per session, same side and holding
    (open -> close), but symbols drawn at random from the eligible pool."""
    rng = np.random.default_rng(seed)
    elig = eligible_mask(px)
    if universe is not None:
        elig = elig[[s for s in elig.columns if s in universe]]
    c_in, c_out = COSTS[cost]
    net = (px["close"] * (1 - c_out)) / (px["open"] * (1 + c_in)) - 1
    counts = strat.groupby("session").size()
    w = strat.size_weight.iloc[0] if len(strat) else 0.0
    pools = []
    for d, k in counts.items():
        pool = net.loc[d, elig.loc[d][elig.loc[d]].index].dropna().to_numpy()
        pools.append((pool, min(k, len(pool))))
    out = np.empty(reps)
    for r in range(reps):
        tot = 0.0
        for pool, k in pools:
            if k:
                tot += w * pool[rng.choice(len(pool), k, replace=False)].sum()
        out[r] = tot
    return out
