"""Quoted spreads measured from NBBO quotes (ORB Amendment 1, B2 and B7.4).

A MEASUREMENT only: the quoted half-spread = (ask - bid) / 2 / mid of the quote in force at the end of a given
minute (the last quote stamped at or before minute_end), if it is not older than `max_age`. Slippage beyond the
touch is an ASSUMPTION and is never added here; see tradelab/stocks/costs.py."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .timeutil import session_bounds

MAX_AGE = pd.Timedelta(seconds=60)


@dataclass(frozen=True)
class HalfSpread:
    value: float | None            # fraction of mid; None when no valid quote
    quote_time: pd.Timestamp | None
    status: str                    # "ok" | "stale" | "none" | "crossed_or_locked" | "invalid"


def half_spread_at(quotes: pd.DataFrame, minute_start: pd.Timestamp, max_age: pd.Timedelta = MAX_AGE) -> HalfSpread:
    """Quote in force at the END of the minute starting at `minute_start` (quotes indexed by UTC time)."""
    end = minute_start + pd.Timedelta(minutes=1)
    q = quotes[quotes.index <= end] if len(quotes) else quotes
    if q.empty:
        return HalfSpread(None, None, "none")
    row, t = q.iloc[-1], q.index[-1]
    if end - t > max_age:
        return HalfSpread(None, t, "stale")
    bid, ask = float(row["bid"]), float(row["ask"])
    if not (np.isfinite(bid) and np.isfinite(ask)) or bid <= 0 or ask <= 0:
        return HalfSpread(None, t, "invalid")
    if ask <= bid:
        return HalfSpread(None, t, "crossed_or_locked")
    mid = (ask + bid) / 2
    return HalfSpread((ask - bid) / 2 / mid, t, "ok")


def minutes_et(day: str, start_hhmm: str, end_hhmm: str) -> list[pd.Timestamp]:
    """UTC minute starts between two ET clock times inclusive, on `day`, clipped to the regular session."""
    b = session_bounds(day)
    if b is None:
        return []
    a = pd.Timestamp(f"{day} {start_hhmm}", tz="America/New_York").tz_convert("UTC")
    z = pd.Timestamp(f"{day} {end_hhmm}", tz="America/New_York").tz_convert("UTC")
    return [m for m in pd.date_range(a, z, freq="min") if b[0] <= m < b[1]]


def close_minute(day: str) -> pd.Timestamp | None:
    """The last regular minute (15:59 ET, or 12:59 ET on a half-day)."""
    b = session_bounds(day)
    return None if b is None else b[1] - pd.Timedelta(minutes=1)


def measure_day(quotes: pd.DataFrame, day: str, max_age: pd.Timedelta = MAX_AGE) -> dict[str, list[HalfSpread]]:
    """Half-spreads at every minute 09:35-10:30 ET (the intended entry window) and at the close minute."""
    entry = [half_spread_at(quotes, m, max_age) for m in minutes_et(day, "09:35", "10:30")]
    cm = close_minute(day)
    return {"entry_window": entry, "close": [half_spread_at(quotes, cm, max_age)] if cm is not None else []}


def summarize(values: list[HalfSpread]) -> dict:
    """Distribution in basis points of the half-spread, with the share of minutes without a usable quote."""
    ok = np.array([v.value for v in values if v.status == "ok"], dtype=float) * 1e4
    counts = {s: sum(v.status == s for v in values) for s in ("ok", "stale", "none", "crossed_or_locked", "invalid")}
    out = {"n_minutes": len(values), "status_counts": counts,
           "share_unusable": float(1 - counts["ok"] / len(values)) if values else None}
    if len(ok):
        out.update({"median_bp": float(np.median(ok)), "p90_bp": float(np.quantile(ok, 0.9)),
                    "mean_bp": float(ok.mean()), "max_bp": float(ok.max())})
    return {"kind": "MEASURED quoted half-spread (no slippage included)", **out}
