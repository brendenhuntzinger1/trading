"""Long-only spot backtester with next-bar-open execution and per-trade costs.

A strategy returns a target position in [0, 1] computed from data up to and
including bar t's close. That position is entered at bar t+1's open, so the
backtest never trades on information it would not have had.
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).parent / "data"

def load(product, tf):
    df = pd.read_csv(DATA / f"{product}_{tf}.csv", index_col=0, parse_dates=True)
    return df.iloc[:-1]  # last bar is still forming

def run(df, target, cost):
    """cost = fraction of traded notional lost per side (fee + slippage)."""
    target = target.reindex(df.index).fillna(0).clip(0, 1)
    held = target.shift(1).fillna(0)          # position during bar t (set at t's open)
    prev = held.shift(1).fillna(0)            # position carried in from bar t-1
    gap = df.open / df.close.shift(1) - 1     # close(t-1) -> open(t), earned by old position
    intra = df.close / df.open - 1            # open(t) -> close(t), earned by new position
    gross = (1 + prev * gap.fillna(0)) * (1 + held * intra) - 1
    turnover = (held - prev).abs()
    net = gross - turnover * cost
    return net, turnover

def stats(net, turnover, bars_per_year):
    eq = (1 + net).cumprod()
    years = len(net) / bars_per_year
    cagr = eq.iloc[-1] ** (1 / years) - 1
    dd = (eq / eq.cummax() - 1).min()
    sd = net.std()
    sharpe = net.mean() / sd * np.sqrt(bars_per_year) if sd > 0 else 0.0
    return {
        "final_$1000": round(1000 * eq.iloc[-1]),
        "CAGR%": round(100 * cagr, 1),
        "maxDD%": round(100 * dd, 1),
        "sharpe": round(sharpe, 2),
        "trades/yr": round(turnover.sum() / years, 1),
    }
