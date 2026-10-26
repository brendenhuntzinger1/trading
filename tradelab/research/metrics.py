"""Performance statistics, with uncertainty that respects time dependence."""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

N = NormalDist()


def summary(res, bars_per_year: int = 365) -> dict:
    r = res.returns
    eq = res.equity
    years = len(r) / bars_per_year
    cagr = (eq.iloc[-1] / res.capital) ** (1 / years) - 1
    dd = eq / np.maximum.accumulate(np.r_[res.capital, eq.to_numpy()])[1:] - 1
    cal = (1 + r).groupby(r.index.year).prod() - 1
    traded = res.trades.notional.abs().sum() if len(res.trades) else 0.0
    return {
        "final": round(float(eq.iloc[-1]), 2),
        "CAGR": cagr,                                         # compounded growth
        "arith_mean_annual": r.mean() * bars_per_year,         # mean daily return x 365
        "mean_calendar_year": cal.mean(),                      # simple average of yearly returns
        "vol": r.std() * math.sqrt(bars_per_year),
        "sharpe": sharpe(r, bars_per_year),
        "sortino": r.mean() / r[r < 0].std() * math.sqrt(bars_per_year) if (r < 0).any() else float("nan"),
        "maxDD": float(dd.min()),
        "longest_DD_days": longest_underwater(eq),
        "exposure": float(res.weights.sum(axis=1).mean()),
        "turnover_x_per_yr": traded / eq.mean() / years,
        "orders_per_yr": len(res.trades) / years,
        "cost_drag_per_yr": res.fees / eq.mean() / years,
        "years": years,
    }


def sharpe(r: pd.Series, bpy: int = 365) -> float:
    sd = r.std()
    return float(r.mean() / sd * math.sqrt(bpy)) if sd > 0 else 0.0


def longest_underwater(eq: pd.Series) -> int:
    peak = eq.cummax()
    under = eq < peak
    runs = under.groupby((~under).cumsum()).sum()
    return int(runs.max()) if len(runs) else 0


def stationary_bootstrap_idx(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap indices (random block lengths)."""
    idx = np.empty(n, dtype=int)
    p = 1.0 / mean_block
    idx[0] = rng.integers(n)
    for t in range(1, n):
        idx[t] = rng.integers(n) if rng.random() < p else (idx[t - 1] + 1) % n
    return idx


def bootstrap(returns: dict[str, pd.Series], stats: dict, n_boot: int = 1000, mean_block: float = 20,
              seed: int = 7, bpy: int = 365) -> pd.DataFrame:
    """Paired bootstrap: the same resampled days for every series, so the
    differences between strategies keep their correlation."""
    df = pd.DataFrame(returns).dropna()
    rng = np.random.default_rng(seed)
    a = df.to_numpy()
    out = []
    for _ in range(n_boot):
        s = a[stationary_bootstrap_idx(len(a), mean_block, rng)]
        out.append({k: f(s, df.columns, bpy) for k, f in stats.items()})
    res = pd.DataFrame(out)
    q = res.quantile([0.05, 0.5, 0.95]).T
    q.columns = ["p05", "median", "p95"]
    q["P(>0)"] = (res > 0).mean()
    return q


def psr(r: pd.Series, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe ratio (per-period SR), Bailey & Lopez de Prado 2012."""
    sr = r.mean() / r.std()
    g3 = float(((r - r.mean()) ** 3).mean() / r.std() ** 3)
    g4 = float(((r - r.mean()) ** 4).mean() / r.std() ** 4)
    z = (sr - sr_benchmark) * math.sqrt(len(r) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return N.cdf(z)


def deflated_sharpe(r: pd.Series, n_trials: int, trial_sr_var: float) -> float:
    """Deflated Sharpe ratio (Bailey & Lopez de Prado 2014): PSR against the Sharpe
    the best of n_trials unskilled strategies would show by luck.
    trial_sr_var is the variance of per-period Sharpe ratios across trials."""
    e = 0.5772156649
    sr0 = math.sqrt(trial_sr_var) * ((1 - e) * N.inv_cdf(1 - 1 / n_trials) + e * N.inv_cdf(1 - 1 / (n_trials * math.e)))
    return psr(r, sr0)
