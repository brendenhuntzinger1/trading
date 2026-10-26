"""Replay historical bars through the live engine code (no separate backtest logic)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from .engine import Bar, Engine


@dataclass
class Ctx:
    sessions: object


def _aligned(frames: dict[str, pd.DataFrame]) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    idx = sorted(set().union(*[f.index for f in frames.values()]))
    idx = pd.DatetimeIndex(idx)
    arrs = {s: f.reindex(idx)[["open", "high", "low", "close", "volume"]].to_numpy(float) for s, f in frames.items()}
    return idx, arrs


def replay_bars(engine: Engine, frames: dict[str, pd.DataFrame], bar: timedelta, sessions, call_open: bool = False,
                start=None, end=None) -> Engine:
    """Drive the engine bar by bar. Stock bars are clipped to the session close (Yahoo's
    last hourly bar is 15:30-16:00). With call_open, the engine's session-open hook
    sees each symbol's opening print (the open of the session's first bar)."""
    idx, arrs = _aligned(frames)
    ctx = Ctx(sessions)
    sel = np.ones(len(idx), bool)
    utc = lambda x: pd.Timestamp(x).tz_localize("UTC") if pd.Timestamp(x).tzinfo is None else pd.Timestamp(x).tz_convert("UTC")
    if start is not None:
        sel &= idx >= utc(start)
    if end is not None:
        sel &= idx < utc(end)
    last_open_day = None
    for i in np.flatnonzero(sel):
        t = idx[i].to_pydatetime()
        e = t + bar
        sess = sessions.session_of(t)
        if sessions.market == "stocks":
            if sess is None:
                continue
            e = min(e, sess[1])
            day = sessions.day_key(t)
            if call_open and t == sess[0] and day != last_open_day:
                opens = {s: a[i, 0] for s, a in arrs.items() if np.isfinite(a[i, 0])}
                engine.process_open(t, opens, ctx)
                last_open_day = day
        bars = {s: Bar(*a[i]) for s, a in arrs.items() if np.isfinite(a[i, 3])}
        engine.process_bar(t, e, bars, ctx)
    return engine


def replay_daily_open_close(engine: Engine, daily: dict[str, pd.DataFrame], sessions, start=None, end=None) -> Engine:
    """Daily bars as one open->close session each: the open hook sees the opening prints,
    then the whole session is one bar ending at the official close."""
    days = sorted(set().union(*[d.index for d in daily.values()]))
    ctx = Ctx(sessions)
    for day in days:
        if (start and day < start) or (end and day >= end):
            continue
        b = sessions.bounds(day)
        if b is None:
            continue
        opens = {s: d.at[day, "open"] for s, d in daily.items() if day in d.index and np.isfinite(d.at[day, "open"])}
        engine.process_open(b[0], opens, ctx)
        bars = {s: Bar(d.at[day, "open"], d.at[day, "high"], d.at[day, "low"], d.at[day, "close"], d.at[day, "volume"])
                for s, d in daily.items() if day in d.index and np.isfinite(d.at[day, "close"])}
        engine.process_bar(b[0], b[1], bars, ctx)
    return engine


def trades_frame(engine: Engine) -> pd.DataFrame:
    rows = [{**t.__dict__, "net_pnl": t.net_pnl, "gross_ret": t.gross_ret, "net_ret": t.net_ret} for t in engine.trades]
    return pd.DataFrame(rows)


def daily_pnl(engine: Engine, sessions) -> pd.Series:
    """Daily change in equity (fraction), from the engine's own equity curve."""
    eq = pd.Series({t: v for t, v in engine.equity_curve})
    eq.index = pd.DatetimeIndex(eq.index)
    by_day = eq.groupby([sessions.day_key(t) for t in eq.index]).last()
    prev = by_day.shift(1).fillna(engine.initial)
    return by_day / prev - 1
