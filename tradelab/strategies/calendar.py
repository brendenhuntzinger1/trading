"""Scheduled macro-event overlay (FOMC decisions, CPI releases).

Only usable when an official, point-in-time calendar exists at
data/events/macro_calendar.csv (built by the events pipeline from official
sources). Dates are never typed from memory. Scheduled release dates are
published in advance, so a calendar overlay can be backtested without
point-in-time news content; the *content* of releases (surprise vs.
expectation) cannot, and is out of scope here.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import StrategySpec

CALENDAR = Path(__file__).resolve().parents[2] / "data" / "events" / "macro_calendar.csv"


KINDS = {"FOMC": "fomc_decision", "CPI": "cpi_release", "NFP": "nfp_release"}


def load_calendar(path: Path = CALENDAR) -> pd.DataFrame | None:
    """Calendar from the events pipeline: columns kind, release_utc, known_in_advance, source_url, ...
    Only releases whose date was published in advance are usable for a pre-positioning overlay
    (an unscheduled FOMC action cannot be de-risked ahead of time)."""
    if not path.exists():
        return None
    cal = pd.read_csv(path)
    cal["release_time"] = pd.to_datetime(cal.release_utc, utc=True)
    cal = cal[cal.known_in_advance.astype(str).str.lower() == "true"]
    inv = {v: k for k, v in KINDS.items()}
    cal["event"] = cal.kind.map(inv)
    return cal.dropna(subset=["event"])


def event_overlay(base: StrategySpec, cal: pd.DataFrame, events=("FOMC", "CPI"), days_before=1,
                  scale=0.0) -> StrategySpec:
    """Scale the base strategy's weight by `scale` on the `days_before` daily bars whose holding period
    contains a scheduled release, then return to the base weight."""
    times = cal.loc[cal.event.isin(events), "release_time"]

    def signal(df):
        w = base(df).copy()
        days = pd.DatetimeIndex(times.dt.floor("D"))
        for k in range(1, days_before + 1):
            # weight decided at close of day t is held during day t+1; de-risk if a release falls on t+1..t+k
            mask = df.index.isin(days - pd.Timedelta(days=k))
            w[mask] = w[mask] * scale
        return w

    return StrategySpec(
        name=f"{base.name}+macro_{'_'.join(events)}_{days_before}d_x{scale:g}",
        hypothesis=("Scheduled US macro releases (FOMC, CPI) raise short-term crypto volatility without a "
                    "predictable direction; cutting exposure into them lowers drawdowns more than it lowers return."),
        entry="Base strategy rules.",
        exit=f"Exposure multiplied by {scale:g} for the {days_before} day(s) before each scheduled release.",
        sizing="Base sizing x overlay.", holding_period="Base strategy's.",
        failure_conditions="Releases that trigger rallies; extra round-trip costs around every release.",
        params={"events": list(events), "days_before": days_before, "scale": scale}, signal=signal,
    )
