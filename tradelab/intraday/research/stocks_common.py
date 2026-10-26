"""Shared panel loading and trade construction for the stock studies."""
from __future__ import annotations

import pandas as pd

from .stocks_data import DIR, TZ, load, universe

SPLITS = {"dev": ("2000-01-01", "2015-12-31"), "val": ("2016-01-01", "2020-12-31"), "test": ("2021-01-01", "2026-10-23")}


def symbols(kind: str | None = None) -> list[str]:
    u = universe()
    if kind:
        u = u[u.kind == kind]
    return [s for s in u.yahoo if (DIR / "daily" / f"{s}.csv").exists()]


def daily_panel(syms: list[str]) -> dict[str, pd.DataFrame]:
    """Wide frames (session date x symbol) of open, high, low, close, volume.
    Rows with impossible values (open outside [low, high], non-positive prices,
    zero volume) are blanked and counted."""
    cols = {k: {} for k in ("open", "high", "low", "close", "volume")}
    bad = 0
    for s in syms:
        d = load(s, "daily")
        d.index = pd.to_datetime(d.time_et.str[:10])
        d = d[~d.index.duplicated(keep="last")]
        invalid = (d.open <= 0) | (d.close <= 0) | (d.volume <= 0) | (d.open > d.high * 1.0001) | (d.open < d.low * 0.9999)
        bad += int(invalid.sum())
        d = d[~invalid]
        for k in cols:
            cols[k][s] = d[k]
    out = {k: pd.DataFrame(v).sort_index() for k, v in cols.items()}
    out["bad_rows"] = bad
    return out


def et_to_utc(dates: pd.Series | pd.DatetimeIndex, hhmm: str) -> pd.Series:
    ts = pd.to_datetime(pd.Series(pd.DatetimeIndex(dates).strftime("%Y-%m-%d")) + " " + hhmm)
    return ts.dt.tz_localize(TZ).dt.tz_convert("UTC")


def net_return(entry: pd.Series, exit_: pd.Series, side: pd.Series, c_in: float, c_out: float) -> tuple[pd.Series, pd.Series]:
    """Per-unit gross and net returns. Long pays c_in on the buy and c_out on the
    sell; short is the mirror image (sell first at entry, buy back at exit)."""
    long = side == "long"
    gross = (exit_ / entry - 1).where(long, entry / exit_ - 1)
    net_long = exit_ * (1 - c_out) / (entry * (1 + c_in)) - 1
    net_short = entry * (1 - c_in) / (exit_ * (1 + c_out)) - 1
    return gross, net_long.where(long, net_short)
