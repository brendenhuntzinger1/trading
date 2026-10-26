"""Evidence criteria E1-E7 (INTRADAY_HYPOTHESES.md) for a crypto trade list."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tradelab.research.metrics import deflated_sharpe, stationary_bootstrap_idx

from .crypto_rules import restress


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def daily(trades: pd.DataFrame, start, end) -> pd.DataFrame:
    """Per calendar day (UTC, by exit date): weighted P&L, sum of per-trade net returns, trade count."""
    days = pd.date_range(_utc(start).normalize(), _utc(end).normalize() - pd.Timedelta(days=1), freq="D")
    if trades.empty:
        return pd.DataFrame(0.0, index=days, columns=["pnl", "net_sum", "n"])
    d = pd.to_datetime(trades.exit_time_utc, utc=True).dt.normalize().dt.tz_localize(None)
    g = pd.DataFrame({"pnl": trades.size_weight * trades.net_ret, "net_sum": trades.net_ret, "n": 1.0}).groupby(d.values).sum()
    g.index = pd.DatetimeIndex(g.index).tz_localize("UTC")
    return g.reindex(days, fill_value=0.0)


def sharpe(pnl: pd.Series) -> float:
    sd = pnl.std()
    return float(pnl.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0


def e1_bootstrap(dd: pd.DataFrame, n_boot: int = 2000, mean_block: float = 5, seed: int = 11) -> tuple[float, float]:
    """Mean net per trade and its one-sided 95% lower bound, resampling days (stationary bootstrap)."""
    a, n = dd.net_sum.to_numpy(), dd.n.to_numpy()
    if n.sum() == 0:
        return float("nan"), float("nan")
    rng, stats = np.random.default_rng(seed), []
    for _ in range(n_boot):
        i = stationary_bootstrap_idx(len(a), mean_block, rng)
        if n[i].sum() > 0:
            stats.append(a[i].sum() / n[i].sum())
    return float(a.sum() / n.sum()), float(np.quantile(stats, 0.05))


def placebo(trades: pd.DataFrame, bars: dict[str, pd.DataFrame], start, end, reps: int = 1000, seed: int = 5):
    """Random entries: same coin, count, time of day and holding time; long; same costs; no stop/target.
    Returns (p_value, placebo_means)."""
    if trades.empty:
        return float("nan"), np.array([])
    rng = np.random.default_rng(seed)
    days = pd.date_range(_utc(start).normalize(), _utc(end).normalize() - pd.Timedelta(days=2), freq="D")
    arr = {s: (b.index.asi8, b.open.to_numpy(), b.close.to_numpy()) for s, b in bars.items()}
    et = pd.to_datetime(trades.entry_time_utc, utc=True)
    tod = (et - et.dt.normalize()).to_numpy().astype("timedelta64[ns]").astype(np.int64)
    hold = (pd.to_datetime(trades.exit_time_utc, utc=True) - et).to_numpy().astype("timedelta64[ns]").astype(np.int64)
    cost = (trades.entry_cost + trades.exit_cost).to_numpy()
    syms = trades.symbol.to_numpy()
    day_ns = days.asi8
    tol = pd.Timedelta(minutes=15).value
    means = np.empty(reps)
    for r in range(reps):
        d = day_ns[rng.integers(0, len(day_ns), len(trades))]
        nets = []
        for j in range(len(trades)):
            t_ns, o, c = arr[syms[j]]
            t_in = d[j] + tod[j]
            i = np.searchsorted(t_ns, t_in)
            if i >= len(t_ns) or t_ns[i] - t_in > tol:
                continue
            k = np.searchsorted(t_ns, t_ns[i] + hold[j]) - 1          # last bar starting before exit time
            if k < i:
                continue
            nets.append(c[k] / o[i] - 1 - cost[j])
        means[r] = np.mean(nets) if nets else np.nan
    means = means[np.isfinite(means)]
    actual = trades.net_ret.mean()
    return float((np.sum(means >= actual) + 1) / (len(means) + 1)), means


def evaluate(trades: pd.DataFrame, bars: dict[str, pd.DataFrame], start, end, n_trials: int, trial_sr_var: float,
             placebo_reps: int = 1000) -> dict:
    dd = daily(trades, start, end)
    mean, lb = e1_bootstrap(dd)
    sr = sharpe(dd.pnl)
    st = restress(trades) if not trades.empty else trades
    dds = daily(st, start, end)
    # three equal sub-periods
    edges = pd.date_range(_utc(start), _utc(end), periods=4)
    subs = [float(dd.pnl[(dd.index >= edges[i]) & (dd.index < edges[i + 1])].sum()) for i in range(3)]
    p, _ = placebo(trades, bars, start, end, placebo_reps)
    dsr = deflated_sharpe(dd.pnl, n_trials, trial_sr_var) if dd.pnl.std() > 0 else float("nan")
    res = {
        "n_trades": int(len(trades)),
        "gross_mean": float(trades.gross_ret.mean()) if len(trades) else float("nan"),
        "gross_median": float(trades.gross_ret.median()) if len(trades) else float("nan"),
        "round_trip_cost_mean": float(trades.cost.mean()) if len(trades) else float("nan"),
        "net_mean": mean, "E1_lower95": lb,
        "sharpe_daily": sr,
        "stress_net_mean": float(st.net_ret.mean()) if len(st) else float("nan"),
        "stress_sharpe": sharpe(dds.pnl),
        "subperiod_pnl": subs,
        "placebo_p": p,
        "DSR": dsr, "n_trials": n_trials, "trial_sr_var": trial_sr_var,
        "win_rate": float((trades.net_ret > 0).mean()) if len(trades) else float("nan"),
        "total_weighted_pnl": float(dd.pnl.sum()),
    }
    res["E"] = {
        "E1": bool(np.isfinite(lb) and lb > 0),
        "E2": bool(sr >= 0.5),
        "E3": bool(len(st) and st.net_ret.mean() > 0),
        "E4": bool(sum(x > 0 for x in subs) >= 2),
        "E5": bool(np.isfinite(p) and p < 0.05),
        "E6": bool(np.isfinite(dsr) and dsr >= 0.95),
        "E7": bool(len(trades) >= 100),
    }
    res["all_pass"] = all(res["E"].values())
    return res
