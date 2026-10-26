"""Validation tools for prediction research: leakage-safe splits, backtest-overfitting
probability, calibration, ranking skill and concentration of results.

References: purging/embargo (López de Prado, *Advances in Financial Machine Learning*, 2018, ch. 7);
CSCV and PBO (Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest Overfitting", 2017).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

from .metrics import stationary_bootstrap_idx


# ---------------------------------------------------------------- splits ----
@dataclass(frozen=True)
class Fold:
    train: np.ndarray        # integer positions
    test: np.ndarray


def purged_walk_forward(decision_time: pd.Series, label_end: pd.Series, n_folds: int,
                        min_train_frac: float = 0.3, embargo: pd.Timedelta = pd.Timedelta(0)) -> list[Fold]:
    """Expanding-window folds over samples ordered by decision time.

    A training sample is kept only if its label is fully known before the test block starts,
    with an extra `embargo` gap: label_end < first test decision time - embargo. This purges
    training labels that overlap the test period and keeps serially correlated features from
    bridging the boundary. Folds only move forward, so no test data ever precedes training data.
    """
    t = pd.to_datetime(decision_time).reset_index(drop=True)
    e = pd.to_datetime(label_end).reset_index(drop=True)
    if not t.is_monotonic_increasing:
        raise ValueError("samples must be sorted by decision time")
    n = len(t)
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    folds = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        test_start = t.iloc[a]
        train = np.flatnonzero((e < test_start - embargo).to_numpy() & (np.arange(n) < a))
        folds.append(Fold(train, np.arange(a, b)))
    return folds


# ------------------------------------------------------------------- PBO ----
@dataclass
class PBOResult:
    pbo: float                     # probability the in-sample best is below the OOS median
    logits: np.ndarray
    n_combinations: int
    oos_rank_of_is_best: np.ndarray   # relative rank in (0, 1)
    perf_degradation_slope: float     # regression slope of OOS on IS performance of the selected config


def cscv_pbo(returns: pd.DataFrame, n_partitions: int = 16, metric=None) -> PBOResult:
    """Combinatorially symmetric cross-validation (Bailey et al. 2017).

    returns: T x N matrix, one column per configuration tried, rows = periods (same dates).
    The rows are split into S equal blocks; for every choice of S/2 blocks as in-sample (IS) and
    the rest as out-of-sample (OOS), pick the best IS configuration and record its OOS relative
    rank w; logit = ln(w / (1 - w)). PBO = share of combinations with logit <= 0.
    """
    if n_partitions % 2:
        raise ValueError("n_partitions must be even")
    M = returns.dropna(how="any").to_numpy(float)
    T, N = M.shape
    if N < 2 or T < n_partitions * 2:
        raise ValueError("need >= 2 configurations and enough rows for the partitions")
    metric = metric or (lambda x: x.mean(axis=0) / (x.std(axis=0, ddof=1) + 1e-12))
    blocks = np.array_split(np.arange(T), n_partitions)
    logits, ranks, is_perf, oos_perf = [], [], [], []
    for combo in combinations(range(n_partitions), n_partitions // 2):
        is_idx = np.concatenate([blocks[i] for i in combo])
        oos_idx = np.concatenate([blocks[i] for i in range(n_partitions) if i not in combo])
        r_is, r_oos = metric(M[is_idx]), metric(M[oos_idx])
        best = int(np.argmax(r_is))
        w = (np.sum(r_oos < r_oos[best]) + 0.5 * np.sum(r_oos == r_oos[best])) / N   # relative rank in (0, 1)
        w = min(max(w, 0.5 / N), 1 - 0.5 / N)
        ranks.append(w)
        logits.append(np.log(w / (1 - w)))
        is_perf.append(r_is[best]); oos_perf.append(r_oos[best])
    logits = np.array(logits)
    slope = float(np.polyfit(is_perf, oos_perf, 1)[0]) if len(set(is_perf)) > 1 else float("nan")
    return PBOResult(float(np.mean(logits <= 0)), logits, len(logits), np.array(ranks), slope)


# ----------------------------------------------------------- calibration ----
def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Predicted vs observed frequency by probability bin (equal-count bins)."""
    d = pd.DataFrame({"p": np.asarray(p, float), "y": np.asarray(y, float)})
    d["bin"] = pd.qcut(d.p.rank(method="first"), q=min(bins, len(d)), labels=False)
    g = d.groupby("bin").agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean"))
    g["gap"] = g.observed - g.predicted
    return g


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    r = reliability(p, y, bins)
    return float(np.sum(r.n * r.gap.abs()) / r.n.sum())


def skill_vs_base_rate(p: np.ndarray, y: np.ndarray) -> float:
    """Brier skill score against always predicting the observed base rate (>0 = better than no-skill)."""
    y = np.asarray(y, float)
    ref = brier(np.full_like(y, y.mean()), y)
    return float(1 - brier(p, y) / ref) if ref > 0 else 0.0


def quantile_coverage(y: np.ndarray, q_pred: dict[float, np.ndarray]) -> dict[float, float]:
    """Share of outcomes at or below each predicted quantile (ideal: equal to the quantile)."""
    y = np.asarray(y, float)
    return {q: float(np.mean(y <= np.asarray(v, float))) for q, v in q_pred.items()}


# --------------------------------------------------------------- ranking ----
def rank_ic_by_period(period: pd.Series, pred: pd.Series, outcome: pd.Series, min_n: int = 5) -> pd.Series:
    """Spearman correlation between prediction and outcome within each period (cross-sectional skill)."""
    d = pd.DataFrame({"g": period.to_numpy(), "p": pred.to_numpy(), "y": outcome.to_numpy()})
    out = {}
    for g, x in d.groupby("g"):
        if len(x) >= min_n and x.p.nunique() > 1 and x.y.nunique() > 1:
            out[g] = x.p.rank().corr(x.y.rank())
    return pd.Series(out, dtype=float)


def mean_ci(series: pd.Series, n_boot: int = 2000, mean_block: float = 5, seed: int = 3, level: float = 0.90):
    """Mean with a stationary-bootstrap interval (respects serial dependence)."""
    a = series.dropna().to_numpy(float)
    if len(a) < 3:
        return float(np.mean(a)) if len(a) else float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    est = [a[stationary_bootstrap_idx(len(a), mean_block, rng)].mean() for _ in range(n_boot)]
    lo, hi = np.quantile(est, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(a.mean()), float(lo), float(hi)


# --------------------------------------------------------- concentration ----
def concentration(pnl: pd.Series) -> dict:
    """How much of the total depends on a few exceptional trades."""
    s = pnl.dropna().sort_values(ascending=False)
    total = s.sum()
    k1, k5 = max(1, int(round(len(s) * 0.01))), max(1, int(round(len(s) * 0.05)))
    return {"n": len(s), "total": float(total), "top1pct_share": float(s.iloc[:k1].sum() / total) if total else float("nan"),
            "top5pct_share": float(s.iloc[:k5].sum() / total) if total else float("nan"),
            "total_without_top5": float(s.iloc[5:].sum()), "best_trade": float(s.iloc[0]) if len(s) else float("nan")}
