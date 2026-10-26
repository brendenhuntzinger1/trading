"""Point-in-time panel: features and labels for (decision time, instrument) pairs.

Bars are indexed by START time. A bar is knowable at start + bar length. A decision at time t
may use only bars whose end <= t; the position is entered at the OPEN of the bar starting at t
(the first price after the decision), so no feature ever sees the entry bar.
Feature families are kept separate so each can be tested for incremental value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FAMILIES = {
    "returns": ["r_1h", "r_4h", "r_24h", "r_72h", "r_7d"],
    "candle": ["body_frac", "upper_wick", "lower_wick", "close_loc_24h"],
    "volume": ["log_dvol_24h", "rel_vol_24h", "amihud_7d"],
    "volatility": ["vol_24h", "vol_7d", "vol_ratio", "range_24h"],
    "trend": ["dist_ma24_sd", "dist_ma168_sd", "dist_vwap24"],
    "relative": ["rs_btc_24h", "rs_btc_7d", "xs_rank_24h", "xs_rank_7d"],
    "breadth": ["breadth_24h", "xs_dispersion_24h", "mkt_r_24h"],
}


def _per_symbol_features(d: pd.DataFrame) -> pd.DataFrame:
    """d: hourly bars of one instrument (index = bar start, contiguous where possible).
    Output indexed by availability time (bar end)."""
    c, o, h, l, v = d.close, d.open, d.high, d.low, d.volume
    lr = np.log(c).diff()
    dv = c * v
    f = pd.DataFrame(index=d.index)
    for k, n in (("r_1h", 1), ("r_4h", 4), ("r_24h", 24), ("r_72h", 72), ("r_7d", 168)):
        f[k] = c / c.shift(n) - 1
    rng = (h - l).replace(0, np.nan)
    f["body_frac"] = (c - o) / rng
    f["upper_wick"] = (h - np.maximum(o, c)) / rng
    f["lower_wick"] = (np.minimum(o, c) - l) / rng
    hi24, lo24 = h.rolling(24).max(), l.rolling(24).min()
    f["close_loc_24h"] = (c - lo24) / (hi24 - lo24).replace(0, np.nan)
    f["log_dvol_24h"] = np.log1p(dv.rolling(24).sum())
    f["rel_vol_24h"] = dv.rolling(24).sum() / (dv.rolling(24 * 30, min_periods=24 * 10).mean() * 24)
    f["amihud_7d"] = (lr.abs() / dv.replace(0, np.nan)).rolling(168, min_periods=48).mean() * 1e6
    f["vol_24h"] = lr.rolling(24).std() * np.sqrt(24)
    f["vol_7d"] = lr.rolling(168, min_periods=96).std() * np.sqrt(24)
    f["vol_ratio"] = f.vol_24h / f.vol_7d
    f["range_24h"] = (hi24 - lo24) / c
    sd = lr.rolling(168, min_periods=96).std() * np.sqrt(24)
    f["dist_ma24_sd"] = (c / c.rolling(24).mean() - 1) / sd
    f["dist_ma168_sd"] = (c / c.rolling(168, min_periods=96).mean() - 1) / sd
    tp = (h + l + c) / 3
    f["dist_vwap24"] = c / ((tp * v).rolling(24).sum() / v.rolling(24).sum()) - 1
    f.index = f.index + pd.Timedelta(hours=1)          # available at bar end
    return f


def _labels(d: pd.DataFrame, horizon: int, barrier_sd: float) -> pd.DataFrame:
    """Labels for a decision at availability time t = bar_end: enter at the open of the bar starting
    at t, hold `horizon` bars. Target/stop at +/- barrier_sd x (24h vol scaled to the horizon);
    if one bar touches both, the stop is assumed first (conservative)."""
    o, h, l, c = d.open.to_numpy(), d.high.to_numpy(), d.low.to_numpy(), d.close.to_numpy()
    starts = d.index
    lr = np.log(d.close).diff()
    vol_h = (lr.rolling(168, min_periods=96).std() * np.sqrt(horizon)).to_numpy()
    n = len(d)
    out = {k: np.full(n, np.nan) for k in ("fwd_ret", "mae", "mfe", "target_first", "stop_first", "barrier_ret")}
    contiguous = (starts.to_series().diff() == pd.Timedelta(hours=1)).to_numpy()
    for i in range(1, n - horizon):
        # decision at end of bar i-1 == start of bar i; entry = open of bar i
        if not contiguous[i:i + horizon].all() or not np.isfinite(vol_h[i - 1]):
            continue
        entry = o[i]
        hh, ll = h[i:i + horizon], l[i:i + horizon]
        out["fwd_ret"][i] = c[i + horizon - 1] / entry - 1
        out["mae"][i] = ll.min() / entry - 1
        out["mfe"][i] = hh.max() / entry - 1
        up, dn = entry * (1 + barrier_sd * vol_h[i - 1]), entry * (1 - barrier_sd * vol_h[i - 1])
        hit_dn = np.flatnonzero(ll <= dn)
        hit_up = np.flatnonzero(hh >= up)
        first_dn = hit_dn[0] if len(hit_dn) else horizon
        first_up = hit_up[0] if len(hit_up) else horizon
        if first_dn <= first_up and first_dn < horizon:       # ties -> stop first
            out["stop_first"][i], out["target_first"][i] = 1, 0
            out["barrier_ret"][i] = dn / entry - 1
        elif first_up < horizon:
            out["stop_first"][i], out["target_first"][i] = 0, 1
            out["barrier_ret"][i] = up / entry - 1
        else:
            out["stop_first"][i], out["target_first"][i] = 0, 0
            out["barrier_ret"][i] = out["fwd_ret"][i]
    lab = pd.DataFrame(out, index=starts)                 # index = decision time (= entry bar start)
    lab["label_end"] = lab.index + pd.Timedelta(hours=horizon)
    return lab


def build_panel(bars: dict[str, pd.DataFrame], decision_hours: list[int], horizon: int,
                eligible=None, benchmark: str = "BTC-USD", barrier_sd: float = 1.0) -> pd.DataFrame:
    """Rows = (decision_time, symbol) at the given UTC hours. `eligible(symbol, t) -> bool` applies the
    point-in-time universe. Cross-sectional features use only symbols eligible at t."""
    feats, labs = {}, {}
    for s, d in bars.items():
        d = d[~d.index.duplicated()].sort_index()
        feats[s] = _per_symbol_features(d)
        labs[s] = _labels(d, horizon, barrier_sd)
    rows = []
    for s in bars:
        f, lab = feats[s], labs[s]
        idx = f.index[f.index.hour.isin(decision_hours)]
        x = f.loc[idx].join(lab, how="left")
        x["symbol"] = s
        x["decision_time"] = idx
        rows.append(x)
    p = pd.concat(rows, ignore_index=True)
    if eligible is not None:
        p = p[[eligible(s, t) for s, t in zip(p.symbol, p.decision_time)]]
    if benchmark in bars:
        b = feats[benchmark][["r_24h", "r_7d"]].rename(columns=lambda k: "btc_" + k)
        p = p.merge(b, left_on="decision_time", right_index=True, how="left")
        p["rs_btc_24h"] = p.r_24h - p.btc_r_24h
        p["rs_btc_7d"] = p.r_7d - p.btc_r_7d
        p = p.drop(columns=["btc_r_24h", "btc_r_7d"])
    g = p.groupby("decision_time")
    p["xs_rank_24h"] = g.r_24h.rank(pct=True)
    p["xs_rank_7d"] = g.r_7d.rank(pct=True)
    p["breadth_24h"] = g.r_24h.transform(lambda x: (x > 0).mean())
    p["xs_dispersion_24h"] = g.r_24h.transform("std")
    p["mkt_r_24h"] = g.r_24h.transform("median")
    return p.sort_values(["decision_time", "symbol"]).reset_index(drop=True)
