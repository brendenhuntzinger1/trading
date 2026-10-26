"""Rolling realized volatility and cross-asset correlation from live bars."""
from __future__ import annotations

import math

import pandas as pd


def log_returns(close: pd.Series) -> pd.Series:
    import numpy as np
    return np.log(close.ffill()).diff()


def realized_vol(bars: pd.DataFrame, window: int, bars_per_year: float) -> pd.Series:
    """Annualized rolling volatility of close-to-close log returns. Windows
    containing empty bars (no trades) are NaN rather than silently filled."""
    r = log_returns(bars.close)
    r[bars.trades == 0] = float("nan")
    return r.rolling(window, min_periods=window).std() * math.sqrt(bars_per_year)


def rolling_corr(bars_by_symbol: dict[str, pd.DataFrame], window: int) -> pd.DataFrame:
    """Pairwise rolling correlation of log returns, columns 'A|B'."""
    rets = pd.DataFrame({s: log_returns(b.close) for s, b in bars_by_symbol.items()})
    syms = list(rets.columns)
    out = {}
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            out[f"{a}|{b}"] = rets[a].rolling(window, min_periods=window).corr(rets[b])
    return pd.DataFrame(out)
