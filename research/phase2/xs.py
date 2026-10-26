"""Daily cross-sectional framework for US stocks (families F1 reversal and F6 ML ranking).

Timing (point-in-time):
    the signal for session t+1 is computed after the close of session t from bars through t;
    the position is entered at the OPEN of t+1 and held to the OPEN of t+2 (open-to-open return, dividends and
    splits included through the `all` adjustment). Row t+1 of the weight frame holds that position.
Eligibility at t (known at t): raw close >= $5; 20-session mean dollar volume (raw close x volume) >= $20M;
    >= 60 sessions of history; not an ETF/ETN/fund/trust by asset-master name; the next open exists (a stock
    that does not open at t+1 cannot be entered; held positions without a next open are exited at the last
    price, recorded in `exits_without_open`).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

FUND_RX = re.compile(r"\b(ETF|ETN|FUND|TRUST|SHARES|PROSHARES|ISHARES|DIREXION|SPDR|INVESCO QQQ|PORTFOLIO|INDEX)\b", re.I)
MIN_PRICE, MIN_DVOL, MIN_HISTORY = 5.0, 20e6, 60


def operating_companies(asset_master: list[dict]) -> set[str]:
    return {a["symbol"] for a in asset_master if a.get("name") and not FUND_RX.search(a["name"])}


def eligibility(raw_close: pd.DataFrame, volume: pd.DataFrame, allowed: set[str] | None = None,
                top_n: int | None = 1000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(eligible mask at t, 20-day mean dollar volume at t). Columns restricted to `allowed`."""
    cols = [c for c in raw_close.columns if allowed is None or c in allowed]
    px, vol = raw_close[cols], volume[cols]
    dvol = (px * vol).rolling(20, min_periods=20).mean()
    hist = px.notna().cumsum()
    ok = (px >= MIN_PRICE) & (dvol >= MIN_DVOL) & (hist >= MIN_HISTORY)
    if top_n:
        rank = dvol.where(ok).rank(axis=1, ascending=False)
        ok &= rank <= top_n
    return ok, dvol


def open_to_open(adj_open: pd.DataFrame) -> pd.DataFrame:
    """Return earned by a position held from the open of row t to the open of row t+1, stored at row t."""
    return adj_open.shift(-1) / adj_open - 1


def select_weights(score: pd.DataFrame, eligible: pd.DataFrame, n: int, lowest: bool = True) -> pd.DataFrame:
    """Equal weight 1/n in the n eligible names with the lowest (or highest) score at t, shifted so the row is
    the entry session t+1. Ties broken by symbol for determinism."""
    s = score.where(eligible)
    r = s.rank(axis=1, ascending=lowest, method="first")
    w = (r <= n).astype(float) / n
    return w.shift(1).fillna(0.0)


def control_weights(eligible: pd.DataFrame) -> pd.DataFrame:
    """Matched control: equal weight across every eligible name at t, held over the same open-to-open window."""
    e = eligible.astype(float)
    return e.div(e.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0).shift(1).fillna(0.0)
