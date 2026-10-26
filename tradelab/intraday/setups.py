"""Setups from INTRADAY_HYPOTHESES.md. A setup proposes Signals; the engine decides.

Each setup precomputes causal features once (`prepare`) and looks them up at
decision time using only bars whose end is <= the decision time. Defaults are
the pre-registered ones; dev-selected values are passed in explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .model import Signal


def _asof(series: pd.Series, t) -> float | None:
    """Last value whose index (= availability time) is <= t."""
    i = series.index.searchsorted(pd.Timestamp(t), side="right") - 1
    return None if i < 0 else series.iloc[i]


# ---------------------------------------------------------------- stocks ----
@dataclass
class S1IntradayMomentum:
    """Prev close -> 10:30 ET return predicts the last half hour. Long-only default."""
    hourly: dict                         # symbol -> hourly bars (index = bar start UTC)
    sessions: object
    daily: dict | None = None            # symbol -> daily bars by session date: official open/close
    max_open_dev: float = 0.02           # skip a session if the hourly open disagrees with the official open
    min_price: float = 10.0              # eligibility before ranking; the engine re-checks independently
    min_dollar_volume: float = 50e6
    threshold: float = 0.0025
    weight: float = 0.20
    max_signals: int = 5
    name: str = "S1"

    def __post_init__(self):
        self.feat = {}
        for sym, df in self.hourly.items():
            d = df.copy()
            d["day"] = [self.sessions.day_key(t) for t in d.index]
            opening = [t == self.sessions.bounds(day)[0] if self.sessions.bounds(day) else False for t, day in zip(d.index, d.day)]
            first = d[opening].groupby("day").close.first()   # close of the 09:30-10:30 bar = price at 10:30
            prev_close = d.groupby("day").close.last().shift(1)
            dv = (d.close * d.volume).groupby(d.day).sum().rolling(20).median().shift(1)
            ok = pd.Series(True, index=first.index)
            if self.daily is not None and sym in self.daily:
                dd = self.daily[sym].sort_index()
                prev_close = dd.close.shift(1)
                hourly_open = d[opening].groupby("day").open.first()
                ok = (hourly_open / dd.open.reindex(hourly_open.index) - 1).abs() <= self.max_open_dev
                dv = (dd.close * dd.volume).rolling(20, min_periods=15).median().shift(1)
            r = first / prev_close.reindex(first.index) - 1
            self.feat[sym] = pd.DataFrame({"r": r.where(ok.reindex(first.index, fill_value=False)),
                                           "dv": dv.reindex(first.index), "px": first})

    def scan(self, t: datetime, ctx) -> list[Signal]:
        sess = self.sessions.session_of(t - timedelta(seconds=1))
        if sess is None or t != sess[1] - timedelta(minutes=30):
            return []
        if pd.Timestamp(t).tz_convert("America/New_York").strftime("%H:%M") != "15:30":
            return []                                    # pre-registered at 15:30 ET: half-days have no such bar
        day = self.sessions.day_key(t)
        cands = []
        for sym, f in self.feat.items():
            if day in f.index and np.isfinite(f.at[day, "r"]) and f.at[day, "r"] >= self.threshold \
                    and np.isfinite(f.at[day, "dv"]) and f.at[day, "dv"] > self.min_dollar_volume and f.at[day, "px"] > self.min_price:
                cands.append((f.at[day, "r"], sym, f.loc[day]))
        cands.sort(reverse=True)
        return [Signal(self.name, sym, "long", "next_open", f"r(prev close->10:30)={r:+.2%}", exit_at_close=True,
                       weight=self.weight, features={"price": row.px, "dollar_volume": row.dv})
                for r, sym, row in cands[: self.max_signals]]


@dataclass
class S2GapReversal:
    """Buy the most negative market-relative opening gaps right after the open; exit at the close."""
    daily: dict                          # symbol -> daily bars indexed by session date (YYYY-MM-DD)
    market: str = "SPY"
    gap_threshold: float = -0.01
    weight: float = 0.20
    max_signals: int = 5
    min_price: float = 10.0              # eligibility is applied BEFORE ranking (pre-registered rule);
    min_dollar_volume: float = 50e6      # the engine re-checks independently
    name: str = "S2"

    def __post_init__(self):
        # Lookups are strictly before the session date, so they work whether or not
        # today's (still forming) daily row is present.
        self.close = {s: d.close.sort_index() for s, d in self.daily.items()}
        self.dvol = {s: (d.close * d.volume).sort_index().rolling(20, min_periods=15).median() for s, d in self.daily.items()}

    @staticmethod
    def _before(series: pd.Series, day: str):
        i = series.index.searchsorted(day, side="left") - 1
        return None if i < 0 else series.iloc[i]

    def scan_open(self, t: datetime, opens: dict[str, float], ctx) -> list[Signal]:
        day = ctx.sessions.day_key(t)
        pc = lambda s: self._before(self.close[s], day) if s in self.close else None
        mkt_pc = pc(self.market)
        if mkt_pc is None or self.market not in opens or not np.isfinite(mkt_pc):
            return []
        mgap = opens[self.market] / mkt_pc - 1
        cands = []
        for s, o in opens.items():
            p = pc(s)
            if s == self.market or p is None or not np.isfinite(p):
                continue
            g = o / p - 1 - mgap
            dv = self._before(self.dvol[s], day)
            eligible = p > self.min_price and dv is not None and np.isfinite(dv) and dv > self.min_dollar_volume
            if eligible and self.gap_threshold >= g > -0.5:   # |gap| >= 50%: spin-off or bad print, not a signal
                cands.append((g, s, p, dv))
        cands.sort()
        return [Signal(self.name, s, "long", "at_open", f"gap vs {self.market} {g:+.2%}", exit_at_close=True,
                       weight=self.weight, features={"price": p, "dollar_volume": dv})     # price test on prev close
                for g, s, p, dv in cands[: self.max_signals]]

    def scan(self, t, ctx):
        return []


# ---------------------------------------------------------------- crypto ----
@dataclass
class C1CascadeReversal:
    """Buy after a 1-hour drop beyond k sigma; target/stop at 1.5 sigma; 6-hour limit.
    Frozen research config C1_k4_maker: limit 0.3% below the signal close, valid 15 minutes."""
    bars5: dict                          # symbol -> 5-minute bars (index = bar start UTC)
    k: float = 4.0
    band: float = 1.5
    hold: timedelta = timedelta(hours=6)
    window: int = 720                    # contiguous 1h returns before the signal bar
    min_obs: int = 600
    entry: str = "maker"                 # maker (limit) | taker (next bar open)
    limit_offset: float = 0.003
    limit_valid: timedelta = timedelta(minutes=15)
    risk: float = 0.01
    max_weight: float = 0.25
    name: str = "C1"

    def __post_init__(self):
        self.feat = {}
        for sym, d in self.bars5.items():
            c = d.close.copy()
            c.index = c.index + pd.Timedelta(minutes=5)       # index by availability (bar end)
            h = c[c.index.minute == 0]                         # hourly closes on the hour
            h = h[~h.index.duplicated()]
            r = h.pct_change()
            r = r[h.index.to_series().diff() == pd.Timedelta(hours=1)]   # contiguous hours only
            sigma = r.rolling(self.window, min_periods=self.min_obs).std().shift(1)   # prior hours only
            self.feat[sym] = pd.DataFrame({"r": r, "sigma": sigma, "px": h.reindex(r.index)})

    def scan(self, t: datetime, ctx) -> list[Signal]:
        if t.minute != 0:
            return []
        out = []
        for sym, f in self.feat.items():
            ts = pd.Timestamp(t)
            if ts not in f.index:
                continue
            r, s, px = f.at[ts, "r"], f.at[ts, "sigma"], f.at[ts, "px"]
            if np.isfinite(r) and np.isfinite(s) and s > 0 and r <= -self.k * s:
                ref = px * (1 - self.limit_offset) if self.entry == "maker" else px
                w = min(self.max_weight, self.risk / (self.band * s))
                kw = dict(entry="limit", limit=ref, limit_valid_until=t + self.limit_valid) if self.entry == "maker" else dict(entry="next_open")
                out.append(Signal(self.name, sym, "long", reason=f"1h {r:+.2%} = {r / s:.1f} sigma",
                                  stop=ref * (1 - self.band * s), target=ref * (1 + self.band * s),
                                  deadline=t + self.hold, weight=w, features={"price": px, "sigma": s}, **kw))
        return out


@dataclass
class C2IntradayMomentum:
    """Long if the 00:00->06:00 UTC return >= z * sigma_6h; exit 23:55 UTC or a 2-sigma stop.
    Frozen research config C2_m1.5: sigma_6h = std of the prior 8,640 5-minute returns x sqrt(72)."""
    bars5: dict
    z: float = 1.5
    stop_sigma: float = 2.0
    window: int = 8640
    min_obs: int = 7000
    risk: float = 0.01
    max_weight: float = 0.25
    name: str = "C2"

    def __post_init__(self):
        self.feat = {}
        for sym, d in self.bars5.items():
            ret5 = d.close.pct_change()
            ret5 = ret5[d.index.to_series().diff() == pd.Timedelta(minutes=5)]
            sig5 = ret5.rolling(self.window, min_periods=self.min_obs).std() * np.sqrt(72)
            c = d.close.copy()
            c.index = c.index + pd.Timedelta(minutes=5)
            six = c[(c.index.hour == 6) & (c.index.minute == 0)]                    # close of the 05:55 bar
            day_open = d.open[(d.index.hour == 0) & (d.index.minute == 0)]
            day_open.index = day_open.index.normalize()
            six_day = pd.Series(six.values, index=six.index.normalize())
            sig_at6 = sig5.reindex(six.index - pd.Timedelta(minutes=5)).to_numpy()   # through the 05:55 bar
            self.feat[sym] = pd.DataFrame({"r": six_day / day_open.reindex(six_day.index) - 1,
                                           "sigma": sig_at6, "px": six_day}).dropna(subset=["r"])

    def scan(self, t: datetime, ctx) -> list[Signal]:
        if not (t.hour == 6 and t.minute == 0):
            return []
        out, day = [], pd.Timestamp(t).normalize()
        for sym, f in self.feat.items():
            if day not in f.index:
                continue
            r, s, px = f.at[day, "r"], f.at[day, "sigma"], f.at[day, "px"]
            if np.isfinite(r) and np.isfinite(s) and s > 0 and r >= self.z * s:
                out.append(Signal(self.name, sym, "long", "next_open", f"00-06 UTC {r:+.2%} = {r / s:.1f} sigma",
                                  stop=px * (1 - self.stop_sigma * s),
                                  deadline=day.to_pydatetime() + timedelta(hours=23, minutes=55),
                                  weight=min(self.max_weight, self.risk / (self.stop_sigma * s)),
                                  features={"price": px, "sigma": s}))
        return out
