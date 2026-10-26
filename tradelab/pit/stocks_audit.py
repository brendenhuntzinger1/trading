"""Measured facts about our Yahoo stock data (data/stocks/), per symbol.

Everything here is measured from the local files; nothing is downloaded.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STOCKS = ROOT / "data" / "stocks"


def _daily(sym):
    d = pd.read_csv(STOCKS / "daily" / f"{sym}.csv")
    d.index = d.time_et.str[:10]
    return d


def _hourly(sym):
    p = STOCKS / "hourly" / f"{sym}.csv"
    if not p.exists():
        return None
    h = pd.read_csv(p, index_col=0)
    h.index = pd.to_datetime(h.index, utc=True)
    return h


def audit_symbol(sym: str, sessions) -> dict:
    """sessions: tradelab.intraday.sessions.StockSessions (exchange_calendars XNYS)."""
    d = _daily(sym)
    h = _hourly(sym)
    row = {"symbol": sym, "daily_first": d.index.min(), "daily_last": d.index.max(), "daily_bars": len(d),
           "daily_stamp_time_et": d.time_et.str[11:16].mode().iat[0]}
    cal = [s for s in pd.bdate_range(d.index.min(), d.index.max()).strftime("%Y-%m-%d") if s >= "2006-10-25" and sessions.bounds(s)]
    row["daily_missing_sessions_since_2006"] = len(set(cal) - set(d.index))
    if h is None or not len(h):
        row["hourly_bars"] = 0
        return row
    et = h.index.tz_convert("America/New_York")
    hm = et.strftime("%H:%M")
    print_bars = h[(hm == "16:00") | ((hm == "13:00"))]
    row.update({"hourly_first": et.min().strftime("%Y-%m-%d"), "hourly_last": et.max().strftime("%Y-%m-%d"),
                "hourly_bars": len(h), "print_bars_16_or_13": len(print_bars),
                "print_bars_zero_volume": int((print_bars.volume == 0).sum())})
    reg = h[~hm.isin(["16:00", "13:00"]) | ((hm == "13:00") & (h.volume > 0))]
    day = reg.index.tz_convert("America/New_York").strftime("%Y-%m-%d")
    sess_days = sorted(set(day))
    expected, have = 0, 0
    for s in sess_days:
        b = sessions.bounds(s)
        if b:
            expected += int(np.ceil((b[1] - b[0]).total_seconds() / 3600))
    row["hourly_missing_bars_in_covered_sessions"] = expected - len(reg)
    hv = reg.volume.groupby(day).sum()
    dv = d.volume.reindex(hv.index)
    ratio = (hv / dv).replace([np.inf, -np.inf], np.nan).dropna()
    row["hourly_vol_sum_over_daily_median"] = round(float(ratio.median()), 3) if len(ratio) else np.nan
    # consistency of the first hourly open with the official daily open (ticker reuse / bad data detector)
    op = reg.groupby(day).open.first()
    dev = (op / d.open.reindex(op.index) - 1).abs()
    row["days_hourly_open_vs_daily_open_gt_2pct"] = int((dev > 0.02).sum())
    return row


def audit_all(sessions) -> pd.DataFrame:
    syms = sorted(p.stem for p in (STOCKS / "daily").glob("*.csv"))
    return pd.DataFrame([audit_symbol(s, sessions) for s in syms]).set_index("symbol")


def split_check(sym: str, before: str, after: str) -> dict:
    """Close on two sessions around a split: equal scale => history was split-adjusted retrospectively."""
    d = _daily(sym)
    return {"symbol": sym, before: float(d.loc[before, "close"]), after: float(d.loc[after, "close"])}
