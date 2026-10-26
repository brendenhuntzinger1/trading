"""Out-of-fold prediction, skill metrics and a cost-aware ranking policy."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tradelab.research.validation import (concentration, ece, mean_ci, purged_walk_forward, rank_ic_by_period,
                                          skill_vs_base_rate)
from .models import Spec, fit_predict


def out_of_fold(panel: pd.DataFrame, spec: Spec, n_folds: int, embargo_h: int) -> pd.Series:
    """Predictions for every sample in the test blocks of purged expanding-window folds."""
    p = panel.dropna(subset=[spec.target]).sort_values("decision_time").reset_index()
    folds = purged_walk_forward(p.decision_time, p.label_end, n_folds, embargo=pd.Timedelta(hours=embargo_h))
    out = pd.Series(np.nan, index=p["index"])
    for f in folds:
        if len(f.train) < 500:
            continue
        out.iloc[f.test] = fit_predict(spec, p.iloc[f.train], p.iloc[f.test])
    return out


def fit_then_predict(train: pd.DataFrame, test: pd.DataFrame, spec: Spec) -> pd.Series:
    """Frozen-model evaluation: fit once on all training rows, predict the evaluation rows."""
    tr = train.dropna(subset=[spec.target])
    return pd.Series(fit_predict(spec, tr, test), index=test.index)


def skill(panel: pd.DataFrame, pred: pd.Series, target: str, classifier: bool) -> dict:
    d = panel.assign(pred=pred).dropna(subset=["pred", target])
    ic = rank_ic_by_period(d.decision_time, d.pred, d[target])
    m, lo, hi = mean_ci(ic)
    out = {"n": len(d), "periods": len(ic), "rank_ic": m, "rank_ic_90ci": [lo, hi]}
    if classifier:
        out.update({"brier_skill_vs_base_rate": skill_vs_base_rate(d.pred, d[target]), "ece": ece(d.pred, d[target]),
                    "base_rate": float(d[target].mean())})
    return out


def policy(panel: pd.DataFrame, score: pd.Series, horizon_h: int, interval_h: int, k: int, roundtrip: float,
           predicts_return: bool, ret_col: str = "fwd_ret") -> dict:
    """At each decision time, rank eligible instruments by score; take the top k. A return-predicting model
    abstains from any instrument whose predicted return does not exceed the round-trip cost. Overlapping
    holdings: each decision cohort gets interval/horizon of capital (k equal slots inside it)."""
    d = panel.assign(score=score).dropna(subset=["score", ret_col])
    picks = []
    for t, g in d.groupby("decision_time"):
        g = g.sort_values("score", ascending=False)
        if predicts_return:
            g = g[g.score > roundtrip]
        picks.append(g.head(k))
    tr = pd.concat(picks) if picks else d.iloc[:0]
    cohort_w = min(1.0, interval_h / horizon_h) / k
    tr = tr.assign(gross=tr[ret_col], net=tr[ret_col] - roundtrip, w=cohort_w)
    return summarize(tr, d, cohort_w)


def random_policy(panel: pd.DataFrame, horizon_h: int, interval_h: int, k: int, roundtrip: float, n_trades_by_t: pd.Series,
                  reps: int = 200, seed: int = 0, ret_col: str = "fwd_ret") -> dict:
    """Matched random entries: same number of picks at each decision time, drawn from the same eligible set."""
    rng = np.random.default_rng(seed)
    d = panel.dropna(subset=[ret_col])
    groups = {t: g[ret_col].to_numpy() for t, g in d.groupby("decision_time")}
    means = []
    for _ in range(reps):
        vals = [rng.choice(groups[t], size=min(int(n), len(groups[t])), replace=False) for t, n in n_trades_by_t.items()
                if t in groups and n > 0]
        if vals:
            means.append(np.concatenate(vals).mean() - roundtrip)
    return {"mean_net_per_trade": float(np.mean(means)) if means else float("nan"),
            "p05": float(np.quantile(means, 0.05)) if means else float("nan"),
            "p95": float(np.quantile(means, 0.95)) if means else float("nan"), "samples": means}


def summarize(trades: pd.DataFrame, universe: pd.DataFrame, w: float) -> dict:
    if trades.empty:
        return {"trades": 0, "abstained_all": True}
    day = pd.to_datetime(trades.decision_time).dt.strftime("%Y-%m-%d")
    pnl = (trades.net * trades.w).groupby(day).sum()
    all_days = pd.date_range(universe.decision_time.min(), universe.decision_time.max(), freq="D").strftime("%Y-%m-%d")
    pnl = pnl.reindex(all_days, fill_value=0.0)
    eq = (1 + pnl).cumprod()
    m, lo, hi = mean_ci(trades.groupby(day).net.mean().reindex(all_days).dropna())
    return {"trades": len(trades), "decision_times": int(trades.decision_time.nunique()),
            "abstain_rate": 1 - trades.decision_time.nunique() / universe.decision_time.nunique(),
            "mean_gross_per_trade": float(trades.gross.mean()), "mean_net_per_trade": float(trades.net.mean()),
            "net_per_trade_90ci_by_day": [lo, hi], "hit_rate": float((trades.net > 0).mean()),
            "sharpe_annual": float(pnl.mean() / pnl.std() * math.sqrt(365)) if pnl.std() > 0 else 0.0,
            "total_return": float(eq.iloc[-1] - 1), "max_drawdown": float((eq / eq.cummax() - 1).min()),
            "turnover_per_day": float(trades.w.sum() * 2 / len(all_days)),
            "concentration": concentration(trades.net * trades.w), "n_trades_by_t": trades.groupby("decision_time").size()}
