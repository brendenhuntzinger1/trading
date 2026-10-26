"""Timestamps and sessions for US stocks.

Alpaca bars are stamped at the bar START in UTC (docs/ALPACA_DATA_AUDIT.md, source C). Sessions, half-days and
daylight saving come from exchange_calendars XNYS (tradelab.intraday.sessions)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from tradelab.intraday.sessions import StockSessions
from tradelab.pit.alpaca_sip import parse_ts

ET = "America/New_York"
_SESSIONS: StockSessions | None = None


def sessions() -> StockSessions:
    global _SESSIONS
    if _SESSIONS is None:
        _SESSIONS = StockSessions()
    return _SESSIONS


def session_bounds(day: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """(open, close) as UTC Timestamps for 'YYYY-MM-DD', or None when the market is closed.
    Half-days close at 13:00 ET."""
    b = sessions().bounds(day)
    return None if b is None else (pd.Timestamp(b[0]), pd.Timestamp(b[1]))


def session_days(start: str, end: str) -> list[str]:
    cal = sessions().cal
    return [d.strftime("%Y-%m-%d") for d in cal.sessions_in_range(start, end)]


def to_et(t) -> pd.Timestamp:
    return pd.Timestamp(t).tz_convert(ET)


def bars_frame(rows: list[dict]) -> pd.DataFrame:
    """Alpaca bar dicts (t, o, h, l, c, v, n, vw) -> DataFrame indexed by UTC bar start, sorted, de-duplicated."""
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame(rows).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
                                             "n": "trades", "vw": "vwap"})
    df.index = pd.DatetimeIndex([pd.Timestamp(parse_ts(t)) for t in df.pop("t")], name="t")
    return df[~df.index.duplicated(keep="last")].sort_index()


def quotes_frame(rows: list[dict]) -> pd.DataFrame:
    """Alpaca quote dicts (t, bp, bs, ap, as, bx, ax, c, z) -> DataFrame indexed by UTC quote time."""
    if not rows:
        return pd.DataFrame(columns=["bid", "ask", "bid_size", "ask_size"], index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame(rows).rename(columns={"bp": "bid", "ap": "ask", "bs": "bid_size", "as": "ask_size",
                                             "bx": "bid_exchange", "ax": "ask_exchange", "c": "conditions", "z": "tape"})
    df.index = pd.DatetimeIndex([pd.Timestamp(parse_ts(t)) for t in df.pop("t")], name="t")
    return df.sort_index(kind="stable")


def regular_minutes(bars: pd.DataFrame, day: str) -> pd.DataFrame:
    """1-minute bars of the regular session only: start >= open and start < close."""
    b = session_bounds(day)
    if b is None or bars.empty:
        return bars.iloc[:0]
    return bars[(bars.index >= b[0]) & (bars.index < b[1])]


def first_bar_et(bars: pd.DataFrame) -> str | None:
    return None if bars.empty else to_et(bars.index[0]).strftime("%H:%M")


def utc(dt: datetime | str) -> pd.Timestamp:
    t = pd.Timestamp(dt)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
