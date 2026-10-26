"""Phase-2 evaluation: one implementation of the PHASE2_PROTOCOL.md criteria, shared by every family.

Inputs are DAILY portfolio P&L series (fraction of equity per session), already net or gross of costs, indexed
by session date. Inference resamples sessions with a stationary block bootstrap (mean block 5), never trades.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tradelab.research.metrics import deflated_sharpe, stationary_bootstrap_idx

BLOCK = 5
SEED = 11
ANN = 252

# ---------------------------------------------------------------- costs ----
SLIP_BASE, SLIP_STRESS = 1e-4, 5e-4          # beyond-the-touch slippage per side (assumption)
FEES_PER_SIDE = 0.15e-4                       # SEC fee + FINRA TAF on sales, averaged over both sides


def tier_half_spread(dollar_volume: pd.DataFrame | pd.Series, etf_major: set[str] | None = None):
    """Protocol §3 liquidity tiers (assumption where not measured): $ volume = trailing 20-day mean, known at t."""
    hs = pd.DataFrame(np.where(dollar_volume >= 100e6, 2e-4, np.where(dollar_volume >= 20e6, 5e-4, np.nan)),
                      index=dollar_volume.index, columns=getattr(dollar_volume, "columns", None)) \
        if isinstance(dollar_volume, pd.DataFrame) else \
        pd.Series(np.where(dollar_volume >= 100e6, 2e-4, np.where(dollar_volume >= 20e6, 5e-4, np.nan)),
                  index=dollar_volume.index)
    if etf_major and isinstance(hs, pd.DataFrame):
        for s in etf_major & set(hs.columns):
            hs[s] = 0.5e-4
    return hs


SPREAD_SAMPLE = __import__("pathlib").Path(__file__).resolve().parent / "results" / "spread_sample.json"
BANDS = [(1, 100), (101, 200), (201, 500), (501, 1000)]


def measured_half_spread(dvol: pd.DataFrame, eligible: pd.DataFrame, minute: str, min_obs: int = 30,
                         sample: dict | None = None) -> pd.DataFrame:
    """Amendment 1: half-spread = median measured in the name's dollar-volume rank band at the execution minute
    (research/phase2/results/spread_sample.json); the protocol tier where the band has < min_obs observations."""
    import json
    sample = sample or json.loads(SPREAD_SAMPLE.read_text())["by_minute_band"]
    rank = dvol.where(eligible).rank(axis=1, ascending=False)
    out = tier_half_spread(dvol)
    for lo, hi in BANDS:
        cell = sample.get(f"{minute}|{lo}-{hi}")
        if cell and cell["n"] >= min_obs:
            out = out.mask((rank >= lo) & (rank <= hi), cell["median_bp"] / 1e4)
    return out


def backtest_weights(w: pd.DataFrame, ret: pd.DataFrame, half_spread: pd.DataFrame, slip: float = SLIP_BASE,
                     ) -> pd.DataFrame:
    """Target weights w (row t = weights held over the return in ret row t) -> daily gross, cost and net P&L.

    Turnover is measured against the previous day's weights after they drifted with that day's returns, so
    holding a position costs nothing and only trades pay. Cost per unit traded = half-spread + slippage + fees.
    A weight on a symbol without a return that day is an error upstream (the caller must not hold it)."""
    w = w.fillna(0.0)
    r = ret.reindex_like(w).fillna(0.0)
    gross = (w * r).sum(axis=1)
    drifted = (w.shift(1).fillna(0.0) * (1 + r.shift(1).fillna(0.0)))
    denom = 1 + gross.shift(1).fillna(0.0)
    drifted = drifted.div(denom, axis=0)
    trade = (w - drifted).abs()
    unit = half_spread.reindex_like(w).fillna(10e-4) + slip + FEES_PER_SIDE   # unknown spread -> 10 bp penalty
    cost = (trade * unit).sum(axis=1)
    return pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost, "turnover": trade.sum(axis=1),
                         "n_pos": (w.abs() > 0).sum(axis=1), "exposure": w.abs().sum(axis=1)})


# ------------------------------------------------------------- inference ----
def mean_ci(x: pd.Series, level: float, n_boot: int = 2000, seed: int = SEED) -> tuple[float, float, float]:
    a = x.dropna().to_numpy(float)
    if len(a) < 10:
        return float(a.mean()) if len(a) else float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    est = [a[stationary_bootstrap_idx(len(a), BLOCK, rng)].mean() for _ in range(n_boot)]
    lo, hi = np.quantile(est, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(a.mean()), float(lo), float(hi)


def stats(x: pd.Series) -> dict:
    sd = x.std()
    eq = (1 + x).cumprod()
    return {"days": int(len(x)), "mean_bp": float(x.mean() * 1e4), "sharpe": float(x.mean() / sd * math.sqrt(ANN)) if sd > 0 else 0.0,
            "total": float(eq.iloc[-1] - 1) if len(x) else 0.0,
            "max_dd": float((eq / eq.cummax() - 1).min()) if len(x) else 0.0}


def top_days_share(net: pd.Series, k: int = 10) -> float | None:
    tot = net.sum()
    return float(net.sort_values(ascending=False).head(k).sum() / tot) if tot > 0 else None


def by_period(x: pd.Series, freq: str = "Y") -> dict:
    key = x.index.year if freq == "Y" else x.index.year.astype(str) + "H" + np.where(x.index.month <= 6, "1", "2")
    return {str(k): float(v) for k, v in x.groupby(key).sum().items()}


def summarise(pnl: pd.DataFrame, control_net: pd.Series, control_gross: pd.Series, stress_net: pd.Series,
              level: float = 0.90) -> dict:
    """Everything the criteria and the mandatory diagnosis need for one configuration on one window."""
    net, gross = pnl["net"], pnl["gross"]
    m, lo, hi = mean_ci(net, level)
    dm, dlo, dhi = mean_ci(net - control_net.reindex(net.index).fillna(0.0), level)
    gm, glo, ghi = mean_ci(gross - control_gross.reindex(gross.index).fillna(0.0), level)
    turnover = pnl["turnover"].mean()
    return {
        "net": {**stats(net), "ci_bp": [lo * 1e4, hi * 1e4]},
        "gross": stats(gross),
        "cost_bp_per_day": float(pnl["cost"].mean() * 1e4), "turnover_per_day": float(turnover),
        "breakeven_cost_bp_per_unit_traded": float(gross.mean() / turnover * 1e4) if turnover > 0 else None,
        "vs_control_net_bp": {"mean": dm * 1e4, "ci": [dlo * 1e4, dhi * 1e4]},
        "vs_control_gross_bp": {"mean": gm * 1e4, "ci": [glo * 1e4, ghi * 1e4]},
        "control_net": stats(control_net.reindex(net.index).fillna(0.0)),
        "stress_net_mean_bp": float(stress_net.mean() * 1e4),
        "by_year_net": by_period(net, "Y"), "by_half_net": by_period(net, "H"),
        "top10_days_share": top_days_share(net),
        "avg_positions": float(pnl["n_pos"].mean()), "avg_exposure": float(pnl["exposure"].mean()),
    }


def dev_qualifies(s: dict, etf_family: bool = False) -> dict:
    yrs = s["by_year_net"]
    need = 5 if etf_family else 2
    q = {"D1": s["net"]["mean_bp"] > 0 and s["vs_control_net_bp"]["ci"][0] > 0,
         "D2": sum(v > 0 for v in yrs.values()) >= need,
         "D3": s["top10_days_share"] is not None and s["top10_days_share"] < 0.5,
         "D4": s["stress_net_mean_bp"] > 0}
    q["qualified"] = all(q.values())
    return q


def validation_qualifies(s: dict) -> dict:
    halves = list(s["by_half_net"].values())
    v4 = True
    if len(halves) >= 2:
        a, b = sum(halves[: len(halves) // 2]), sum(halves[len(halves) // 2:])
        v4 = not (min(a, b) < -0.5 * max(a, b, 0.0) and max(a, b) > 0) and (a + b) > 0
    q = {"V1": s["net"]["ci_bp"][0] > 0, "V2": s["vs_control_net_bp"]["ci"][0] > 0,
         "V3": s["stress_net_mean_bp"] > 0, "V4": v4}
    q["qualified"] = all(q.values())
    return q


def dsr(net: pd.Series, n_trials: int, trial_sharpes: list[float]) -> float:
    var = float(np.var(np.array(trial_sharpes) / math.sqrt(ANN))) if len(trial_sharpes) > 1 else 0.0
    return deflated_sharpe(net.dropna(), max(n_trials, 2), max(var, 1e-6))
