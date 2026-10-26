"""Point-in-time OHLCV bars from recorded trades.

A trade belongs to the bar containing its exchange event_time, but only if we
had received it by the bar's end (plus an optional, explicit grace period).
Trades that arrive later are counted in `late_trades` and excluded, so a
replay never knows more than the live system did at that moment.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from .types import Trade


def build_bars(trades: Iterable[Trade], freq: timedelta, start: datetime, end: datetime,
               grace: timedelta = timedelta(0)) -> pd.DataFrame:
    start = pd.Timestamp(start).floor(freq)       # bars sit on fixed boundaries, whatever start was given
    idx = pd.date_range(start, end, freq=freq, inclusive="left")
    cols = ["open", "high", "low", "close", "volume", "vwap", "trades", "late_trades", "available_at", "received_at"]
    out = pd.DataFrame(index=idx, columns=cols, dtype=float)
    out["received_at"] = pd.NaT
    df = pd.DataFrame([(t.event_time, t.received_at, t.price, t.size) for t in trades if start <= t.event_time < end],
                      columns=["event_time", "received_at", "price", "size"])
    late = pd.Series(dtype=int)
    if len(df):
        df = df.sort_values(["event_time", "received_at"])
        df["bar"] = df.event_time.dt.floor(freq)
        on_time = df[df.received_at <= df.bar + freq + grace]
        late = df[df.received_at > df.bar + freq + grace].groupby("bar").size()
        if len(on_time):
            on_time = on_time.assign(pv=on_time.price * on_time["size"])
            g = on_time.groupby("bar")
            agg = pd.DataFrame({
                "open": g.price.first(), "high": g.price.max(), "low": g.price.min(), "close": g.price.last(),
                "volume": g["size"].sum(), "vwap": g.pv.sum() / g["size"].sum(), "trades": g.size(),
                "received_at": g.received_at.max(),
            })
            out.update(agg.drop(columns="received_at"))
            out["received_at"] = agg.received_at.reindex(idx)
            out["trades"] = agg.trades.reindex(idx)
    out["volume"] = out.volume.fillna(0)
    out["trades"] = out.trades.fillna(0).astype(int)
    out["late_trades"] = late.reindex(idx).fillna(0).astype(int)
    out["available_at"] = idx + freq + grace
    return out[cols]
