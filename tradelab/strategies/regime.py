"""Regime detection and strategy selection between existing return streams.

Selectors combine the daily net returns of candidate strategies (e.g. trend
baseline, fixed allocation, cash). Choices are made with data available before
the day they apply, switches pay `switch_cost` times the change in exposure,
and a minimum holding time limits churn."""
from __future__ import annotations

import numpy as np
import pandas as pd


def btc_regimes(btc: pd.DataFrame) -> pd.Series:
    """4 regimes from information up to each close: trend (close vs 200d SMA) x volatility
    (30d realized vol vs its trailing 365d median)."""
    up = btc.close > btc.close.rolling(200).mean()
    vol = btc.close.pct_change().rolling(30).std()
    hi = vol > vol.rolling(365, min_periods=180).median()
    reg = np.where(up, "up", "down").astype(object) + "_" + np.where(hi, "hivol", "lovol").astype(object)
    return pd.Series(reg, index=btc.index).where(btc.close.rolling(365).count() >= 365)


def _apply_choices(choice: pd.Series, rets: pd.DataFrame, expo: pd.DataFrame, switch_cost: float) -> pd.Series:
    """choice[t] is decided at close t and applied to returns on t+1."""
    held = choice.shift(1).reindex(rets.index)
    r = pd.Series(0.0, index=rets.index)
    for name in rets.columns:
        r[held == name] = rets.loc[held == name, name]
    e = pd.Series(0.0, index=rets.index)
    for name in expo.columns:
        e[held == name] = expo.loc[held == name, name]
    sw = e.diff().abs().fillna(0.0)
    return r - sw * switch_cost


def trailing_sharpe_selector(rets: pd.DataFrame, expo: pd.DataFrame, refit_dates, window=365, margin=0.3,
                             switch_cost=0.0066) -> tuple[pd.Series, pd.Series]:
    """At each refit date pick the candidate with the best trailing Sharpe; switch only if it beats
    the current choice by `margin` (annualised Sharpe). Holds until the next refit (>= 1 year)."""
    choice = pd.Series(np.nan, index=rets.index, dtype=object)
    current = None
    for d in refit_dates:
        d = pd.Timestamp(d, tz="UTC")
        hist = rets.loc[d - pd.Timedelta(days=window): d - pd.Timedelta(days=1)]
        sr = hist.mean() / hist.std().replace(0, np.nan) * np.sqrt(365)
        sr = sr.fillna(0.0)                                   # cash has zero std -> Sharpe 0
        best = sr.idxmax()
        if current is None or sr[best] > sr.get(current, -np.inf) + margin:
            current = best
        choice.loc[d:] = current
    choice = choice.ffill()
    return _apply_choices(choice, rets, expo, switch_cost), choice


def regime_selector(rets: pd.DataFrame, expo: pd.DataFrame, regimes: pd.Series, refit_dates, min_days=60,
                    min_hold=20, switch_cost=0.0066, default="cash") -> tuple[pd.Series, pd.Series]:
    """At each yearly refit, map every regime to the candidate with the highest mean daily return on
    training days in that regime (>= min_days observations, else `default`). Daily, follow the map
    for the current regime, but keep any choice for at least `min_hold` days."""
    regimes = regimes.reindex(rets.index)
    choice = pd.Series(np.nan, index=rets.index, dtype=object)
    refits = [pd.Timestamp(d, tz="UTC") for d in refit_dates]
    for k, d in enumerate(refits):
        end = refits[k + 1] if k + 1 < len(refits) else rets.index[-1] + pd.Timedelta(days=1)
        # training labels are next-day returns of days <= d-2 (regime known at close, return the day after)
        lab = rets.shift(-1).loc[: d - pd.Timedelta(days=2)]
        reg = regimes.loc[lab.index]
        mapping = {}
        for g in reg.dropna().unique():
            sub = lab[reg == g]
            mapping[g] = sub.mean().idxmax() if len(sub) >= min_days else default
        span = rets.loc[d: end - pd.Timedelta(days=1)].index
        choice.loc[span] = regimes.loc[span].map(mapping).fillna(default)
    # minimum holding time
    out, last, since = [], None, 10**9
    for c in choice:
        if last is None or (c != last and since >= min_hold):
            last, since = c, 0
        out.append(last)
        since += 1
    choice = pd.Series(out, index=choice.index)
    return _apply_choices(choice, rets, expo, switch_cost), choice
