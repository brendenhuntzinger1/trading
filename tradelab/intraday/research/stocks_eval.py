"""Evidence criteria E1-E7 from INTRADAY_HYPOTHESES.md for trade lists.

A trade list has one row per trade: session (date), symbol, side, entry/exit
times and prices, gross_ret, cost, net_ret (per unit traded), size_weight
(fraction of equity). Daily P&L = sum(size_weight * net_ret) per session; days
without trades count as zero.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tradelab.research.metrics import deflated_sharpe, stationary_bootstrap_idx

BPY = 252


def daily_pnl(trades: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.Series:
    p = (trades.size_weight * trades.net_ret).groupby(trades.session).sum() if len(trades) else pd.Series(dtype=float)
    return p.reindex(sessions, fill_value=0.0)


def e1_lower_bound(trades: pd.DataFrame, sessions: pd.DatetimeIndex, n_boot=2000, block=10, seed=11) -> float:
    """One-sided 95% lower bound of mean net per-trade return, resampling whole
    trading days in blocks (stationary bootstrap) so within-day and serial
    dependence are kept."""
    if not len(trades):
        return float("nan")
    s = trades.net_ret.groupby(trades.session).sum().reindex(sessions, fill_value=0.0).to_numpy()
    n = trades.net_ret.groupby(trades.session).size().reindex(sessions, fill_value=0).to_numpy()
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        i = stationary_bootstrap_idx(len(s), block, rng)
        k = n[i].sum()
        out.append(s[i].sum() / k if k else 0.0)
    return float(np.quantile(out, 0.05))


def sharpe(p: pd.Series) -> float:
    sd = p.std()
    return float(p.mean() / sd * math.sqrt(BPY)) if sd > 0 else 0.0


def thirds(p: pd.Series) -> list[float]:
    k = len(p) // 3
    return [float(p.iloc[:k].sum()), float(p.iloc[k:2 * k].sum()), float(p.iloc[2 * k:].sum())]


def evaluate(trades: pd.DataFrame, stress_trades: pd.DataFrame, sessions: pd.DatetimeIndex,
             placebo_totals: np.ndarray, n_trials: int, trial_sr_var: float) -> dict:
    p = daily_pnl(trades, sessions)
    lb = e1_lower_bound(trades, sessions)
    sr = sharpe(p)
    stress_mean = float(stress_trades.net_ret.mean()) if len(stress_trades) else float("nan")
    th = thirds(p)
    total = float(p.sum())
    pval = float((np.sum(placebo_totals >= total) + 1) / (len(placebo_totals) + 1)) if len(placebo_totals) else float("nan")
    dsr = float(deflated_sharpe(p, n_trials, trial_sr_var)) if p.std() > 0 else float("nan")
    res = {
        "n_trades": int(len(trades)), "n_sessions": int(len(sessions)), "days_with_trades": int((p != 0).sum()),
        "mean_net_per_trade": float(trades.net_ret.mean()) if len(trades) else float("nan"),
        "mean_gross_per_trade": float(trades.gross_ret.mean()) if len(trades) else float("nan"),
        "win_rate": float((trades.net_ret > 0).mean()) if len(trades) else float("nan"),
        "E1_lower_bound": lb, "E1": bool(lb > 0),
        "E2_sharpe": sr, "E2": bool(sr >= 0.5),
        "E3_stress_mean": stress_mean, "E3": bool(stress_mean > 0),
        "E4_thirds": th, "E4": bool(sum(x > 0 for x in th) >= 2),
        "E5_placebo_p": pval, "E5": bool(pval < 0.05),
        "E6_dsr": dsr, "E6": bool(dsr >= 0.95), "E6_n_trials": n_trials, "E6_trial_sr_var": trial_sr_var,
        "E7": bool(len(trades) >= 100),
        "total_return_sum": total, "daily_mean": float(p.mean()), "daily_std": float(p.std()),
        "daily_skew": float(p.skew()), "daily_kurt": float(p.kurt() + 3),
    }
    res["ALL_PASS"] = all(res[f"E{i}"] for i in range(1, 8))
    return res
