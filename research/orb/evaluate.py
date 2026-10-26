"""Decision-quality evaluation for ORB (pre-registration §10-11, Amendment 1 B3-B4, Amendment 2 B9).

All inference is on DAYS: trades on the same day share the market, so intervals come from a stationary block
bootstrap over sessions (mean block 5 days), never from treating trades as independent."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from tradelab.research.metrics import deflated_sharpe, stationary_bootstrap_idx
from tradelab.research.registry import REGISTRY
from tradelab.research.validation import concentration, mean_ci

ANN = 252
BLOCK = 5
SEED = 3


def daily(trades: pd.DataFrame, days: list[str], col: str) -> pd.Series:
    """Portfolio P&L per session: sum of weight x per-trade return; sessions without trades count as 0."""
    if trades.empty:
        return pd.Series(0.0, index=days)
    return (trades.weight * trades[col]).groupby(trades.day).sum().reindex(days, fill_value=0.0)


def trade_mean_ci(trades: pd.DataFrame, col: str, days: list[str], level: float = 0.90, n_boot: int = 2000,
                  seed: int = SEED) -> dict:
    """Mean per trade with a day-block bootstrap interval (resample sessions, keep each session's trades)."""
    t = trades.dropna(subset=[col])
    if t.empty:
        return {"mean": None, "ci": [None, None], "n": 0}
    s = t.groupby("day")[col].agg(["sum", "count"]).reindex(days, fill_value=0)
    sums, counts = s["sum"].to_numpy(float), s["count"].to_numpy(float)
    rng = np.random.default_rng(seed)
    est = []
    for _ in range(n_boot):
        i = stationary_bootstrap_idx(len(days), BLOCK, rng)
        c = counts[i].sum()
        if c:
            est.append(sums[i].sum() / c)
    lo, hi = np.quantile(est, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {"mean": float(t[col].mean()), "ci": [float(lo), float(hi)], "n": int(len(t)), "level": level}


def paired_ci(a: pd.Series, b: pd.Series, level: float = 0.90) -> dict:
    m, lo, hi = mean_ci(a - b.reindex(a.index, fill_value=0.0), mean_block=BLOCK, level=level)
    return {"mean_diff": m, "ci": [lo, hi], "level": level}


def series_stats(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    sd = r.std()
    return {"mean_daily": float(r.mean()), "sharpe": float(r.mean() / sd * math.sqrt(ANN)) if sd > 0 else 0.0,
            "max_drawdown": float((eq / eq.cummax() - 1).min()) if len(r) else 0.0,
            "total_return": float(eq.iloc[-1] - 1) if len(r) else 0.0}


def decision_metrics(trades: pd.DataFrame, days: list[str], spy: pd.Series, abstentions: dict) -> dict:
    """B4: trade, abstention and portfolio metrics, plus years, thirds and RV buckets."""
    out = {"abstention": abstentions}
    if trades.empty:
        return out | {"trades": 0}
    bp = 1e4
    t = trades
    stopped = t.exit_reason.str.startswith("stop")
    out.update({
        "trades": int(len(t)),
        "per_trade_bp": {k: (float(t[k].mean() * bp) if t[k].notna().any() else None)
                         for k in ("gross", "net_spread", "net_all")},
        "per_trade_R": float(t.r.mean()), "hit_rate": float((t.net_all > 0).mean()),
        "mae_bp_mean": float(t.mae.mean() * bp), "mfe_bp_mean": float(t.mfe.mean() * bp),
        "share_stopped": float(stopped.mean()),
        "median_minutes_to_stop": float(((t.exit_time - t.entry_time)[stopped].dt.total_seconds() / 60).median())
        if stopped.any() else None,
        "cost_label": sorted(t.cost_label.unique().tolist()),
        "halted_trades": int(t.halted.sum()),
    })
    pnl = daily(t, days, "net_all")
    out["portfolio"] = series_stats(pnl)
    sp = spy.reindex(days, fill_value=0.0)
    if sp.std() > 0 and pnl.std() > 0:
        out["portfolio"]["beta_to_spy"] = float(np.cov(pnl, sp)[0, 1] / sp.var())
        out["portfolio"]["corr_to_spy"] = float(np.corrcoef(pnl, sp)[0, 1])
    contrib = (t.weight * t.net_all)
    out["portfolio"].update({"largest_day": float(pnl.abs().max()), "concentration": concentration(contrib),
                             "turnover_mean": float(t.groupby("day").weight.sum().reindex(days, fill_value=0).mean()),
                             "positions_mean": float(t.groupby("day").size().reindex(days, fill_value=0).mean())})
    yr = pd.Series(pnl.values, index=pd.to_datetime(pnl.index)).groupby(lambda d: d.year)
    out["by_year_return"] = {int(k): float((1 + v).prod() - 1) for k, v in yr}
    out["thirds_mean_daily"] = [float(x.mean()) for x in np.array_split(pnl, 3)]
    buckets = pd.cut(t.rv, [1, 2, 5, 30, np.inf], right=False, labels=["1-2", "2-5", "5-30", ">30"])
    out["rv_buckets"] = {str(k): {"n": int(len(g)), "gross_bp": float(g.gross.mean() * bp), "R": float(g.r.mean())}
                         for k, g in t.groupby(buckets, observed=True)}
    return out


def placebo_daily(placebo_reps: np.ndarray, days: list[str]) -> pd.Series:
    """Expected placebo daily P&L (mean over replications) as one series, for paired comparisons."""
    return pd.Series(placebo_reps.mean(axis=0), index=days)


def trial_count(registry: Path = REGISTRY) -> int:
    """E6's N from the registry, never typed by hand: entries of kind 'trial' plus params.n_trials of kind
    'trial_count' ledger entries. Raises if the ledger is empty."""
    n = 0
    if registry.exists():
        for line in registry.read_text().splitlines():
            e = json.loads(line)
            if e.get("kind") == "trial":
                n += 1
            elif e.get("kind") == "trial_count":
                n += int(e.get("params", {}).get("n_trials", 0))
    if n <= 0:
        raise RuntimeError("trial ledger empty: record the baseline trial count (kind 'trial_count') before freezing")
    return n


def e_criteria(trades: pd.DataFrame, stress_trades: pd.DataFrame, days: list[str], placebo_means: np.ndarray,
               n_trials: int, cost_measured: bool) -> dict:
    """E1-E7 (INTRADAY_HYPOTHESES.md) on the final window; PASS requires all and measured costs (B2)."""
    e1 = trade_mean_ci(trades, "net_all", days, level=0.90)
    pnl = daily(trades, days, "net_all")
    s = series_stats(pnl)
    obs_gross = float(trades.gross.mean()) if len(trades) else float("nan")
    thirds = [x.sum() for x in np.array_split(pnl, 3)]
    checks = {
        "E1_net_lower_bound_gt_0": e1["ci"][0] is not None and e1["ci"][0] > 0,
        "E2_sharpe_ge_0.5": s["sharpe"] >= 0.5,
        "E3_net_positive_under_stress": len(stress_trades) > 0 and stress_trades.net_all.mean() > 0,
        "E4_two_of_three_thirds": sum(x > 0 for x in thirds) >= 2,
        "E5_beats_placebo_p_lt_0.05": float((placebo_means >= obs_gross).mean()) < 0.05 if len(placebo_means) else False,
        "E6_dsr_ge_0.95": pnl.std() > 0 and deflated_sharpe(pnl, n_trials, 1.0 / len(pnl)) >= 0.95,
        "E7_trades_ge_100": len(trades) >= 100,
    }
    g = trade_mean_ci(trades, "gross", days, level=0.90)          # 90% two-sided = one-sided 95% bounds
    r_ci = trade_mean_ci(trades, "r", days, level=0.90)
    rt = float((trades.gross - trades.net_all).mean()) if len(trades) else float("nan")
    sd_r = float(trades.r.std()) if len(trades) > 1 else float("nan")
    mde_r = 2.49 * sd_r / math.sqrt(len(trades)) if len(trades) > 1 else float("nan")
    reject = bool((g["ci"][1] is not None and g["ci"][1] < rt) or
                  (g["mean"] is not None and g["mean"] <= 0 and r_ci["ci"][1] is not None and r_ci["ci"][1] < mde_r))
    if all(checks.values()):
        verdict = "PASS" if cost_measured else "INCONCLUSIVE (cost assumed, not measured)"
    else:
        verdict = "REJECT (no useful effect)" if reject else "INCONCLUSIVE"
    out = {"checks": checks, "E1": e1, "sharpe": s["sharpe"], "n_trials": n_trials, "cost_measured": cost_measured,
           "gross": g, "R": r_ci, "round_trip_cost_mean": rt, "mde_R": mde_r, "verdict": verdict}
    if verdict.startswith("INCONCLUSIVE") and g["ci"][1] is not None:
        out["effect_still_possible"] = f"gross mean per trade up to {g['ci'][1] * 1e4:.1f} bp (one-sided 95% upper bound)"
    return out
