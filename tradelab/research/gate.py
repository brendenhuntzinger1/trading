"""Evidence-based trade gate.

For a strategy that holds a position in some states, estimate from past data
only (walk-forward, with an embargo equal to the label horizon):
  * the expected forward return over the intended holding period, per state,
  * its uncertainty (standard error using the effective number of
    non-overlapping observations),
  * the probability and average size of a loss,
  * the round-trip cost.
A state is approved only if the conservative estimate (mean - z * se) exceeds
the round-trip cost. Predictions are recorded so they can be checked against
what actually happened (calibration).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


def forward_return(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Return from the next open (first realistic fill) over `horizon` days."""
    o = df.open
    return o.shift(-(horizon + 1)) / o.shift(-1) - 1


def states(vote: pd.Series, vol: pd.Series, vol_edges: tuple[float, float]) -> pd.Series:
    vb = pd.cut(vol, [-np.inf, vol_edges[0], vol_edges[1], np.inf], labels=["lowvol", "midvol", "hivol"])
    tb = pd.cut(vote, [-0.01, 0.0, 0.5, 1.0], labels=["none", "weak", "strong"])
    return (tb.astype(str) + "_" + vb.astype(str)).where(vote.notna() & vol.notna())


@dataclass
class StateEstimate:
    state: str
    n: int
    n_eff: float
    mean: float
    se: float
    p_gain: float
    avg_loss: float
    approved: bool


def estimate(fwd: pd.Series, st: pd.Series, horizon: int, cost_round_trip: float, z: float = 1.645,
             min_eff: float = 8.0) -> dict[str, StateEstimate]:
    out = {}
    d = pd.DataFrame({"f": fwd, "s": st}).dropna()
    for s, g in d.groupby("s"):
        n = len(g)
        n_eff = n / horizon
        mean = g.f.mean()
        se = g.f.std() / math.sqrt(max(n_eff, 1.0))
        losses = g.f[g.f < 0]
        ok = n_eff >= min_eff and (mean - z * se) > cost_round_trip
        out[s] = StateEstimate(s, n, n_eff, float(mean), float(se), float((g.f > 0).mean()),
                               float(losses.mean()) if len(losses) else 0.0, bool(ok))
    return out


def walk_forward_gate(df: pd.DataFrame, vote: pd.Series, vol: pd.Series, horizon: int, cost_round_trip: float,
                      test_years: list[int], z: float = 1.645) -> tuple[pd.Series, pd.DataFrame]:
    """Returns (approved flag per day, prediction log). Estimates for year Y use labels fully
    realised before Y starts (embargo = horizon + 1 days)."""
    fwd = forward_return(df, horizon)
    approved = pd.Series(np.nan, index=df.index)
    log = []
    for y in test_years:
        start = pd.Timestamp(f"{y}-01-01", tz="UTC")
        train_end = start - pd.Timedelta(days=horizon + 2)
        tr_vol = vol.loc[:train_end].dropna()
        edges = (float(tr_vol.quantile(1 / 3)), float(tr_vol.quantile(2 / 3)))
        st = states(vote, vol, edges)
        est = estimate(fwd.loc[:train_end], st.loc[:train_end], horizon, cost_round_trip, z)
        span = df.loc[f"{y}-01-01":f"{y}-12-31"].index
        s_y = st.loc[span]
        approved.loc[span] = s_y.map(lambda s: est[s].approved if s in est else False).astype(float)
        for t in span:
            s = s_y.loc[t]
            if s in est:
                e = est[s]
                log.append({"time": t, "state": s, "pred_mean": e.mean, "pred_se": e.se, "pred_p_gain": e.p_gain,
                            "approved": e.approved, "realized": fwd.loc[t]})
    return approved, pd.DataFrame(log)


def reliability(log: pd.DataFrame, bins=(0.0, 0.45, 0.5, 0.55, 0.6, 0.65, 1.0)) -> pd.DataFrame:
    """Predicted probability of a gain vs the realised frequency, and predicted vs realised mean.
    Overlapping horizons mean observations are not independent; n_eff is reported."""
    d = log.dropna(subset=["realized"]).copy()
    d["bin"] = pd.cut(d.pred_p_gain, list(bins))
    g = d.groupby("bin", observed=True)
    return pd.DataFrame({
        "n_days": g.size(),
        "pred_p_gain": g.pred_p_gain.mean(),
        "realized_p_gain": g.realized.apply(lambda x: (x > 0).mean()),
        "pred_mean": g.pred_mean.mean(),
        "realized_mean": g.realized.mean(),
    })
