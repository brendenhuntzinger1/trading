"""P1: cross-sectional crypto return prediction on the Coinbase point-in-time universe.

Pre-registration: P1_PREREGISTRATION.md (original + Amendment 1). Phases, in order, per horizon:

    python research/p1/study.py build                 # features + labels (cached under data/p1/)
    python research/p1/study.py gate --horizon p1a     # development stopping check (A2)
    python research/p1/study.py dev --horizon p1a      # out-of-fold comparison, PBO, candidate selection
    python research/p1/study.py validation --horizon p1a
    python research/p1/study.py final --horizon p1a    # opened once; refuses to run again
    python research/p1/study.py <phase> --horizon p1a --reproduce   # recompute and compare, record nothing new

Every historical number is a Coinbase result with assumed Coinbase costs. Nothing here places orders.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tradelab.pit import crypto_universe as cu                                      # noqa: E402
from tradelab.pit.crypto_bars import HOURLY_DIR, load as load_bars                 # noqa: E402
from tradelab.predict.models import Spec, fit_predict                              # noqa: E402
from tradelab.predict.panel import FAMILIES, _per_symbol_features                  # noqa: E402
from tradelab.research.metrics import deflated_sharpe, stationary_bootstrap_idx    # noqa: E402
from tradelab.research.registry import record                                      # noqa: E402
from tradelab.research.validation import (concentration, cscv_pbo, ece, mean_ci, purged_walk_forward,  # noqa: E402
                                          rank_ic_by_period, reliability, skill_vs_base_rate)

RESULTS = ROOT / "research" / "p1" / "results"
CACHE = ROOT / "data" / "p1"
BASE_RT = 0.0132                    # Coinbase: assumed 0.60% taker + 0.06% spread/slippage per side (unverified fee)
GRID = [0.0050, 0.0080, 0.0106, 0.0132, 0.0192, 0.0252]
GRID_LABEL = {0.0050: "hypothetical lower Coinbase fee level", 0.0080: "hypothetical lower Coinbase fee level",
              0.0106: "hypothetical lower Coinbase fee level", 0.0132: "Coinbase base (assumed)",
              0.0192: "Coinbase stress", 0.0252: "Coinbase stress (1.20% taker tier)"}
K = 3
N_TRIALS_DSR = 100
FEATURES = [f for fam in FAMILIES.values() for f in fam]
PERIODS = {"dev": ("2021-03-01", "2024-06-30"), "validation": ("2024-07-01", "2025-06-30"),
           "final": ("2025-07-01", "2026-10-24")}
HORIZONS = {"p1a": dict(h=24, weekday=None, block=10, ann=365, configs=["B1", "B2", "M1", "M2", "M3"]),
            "p1b": dict(h=168, weekday=0, block=4, ann=52, configs=["B1", "M1", "M3"])}
SPECS = {
    "B1": Spec("B1", "rule", "fwd_ret", rule="r_7d", sign=1.0),
    "B2": Spec("B2", "rule", "fwd_ret", rule="r_24h", sign=-1.0),
    "M1": Spec("M1", "ridge", "fwd_ret", FEATURES, params={"alpha": 100.0}),
    "M2": Spec("M2", "logit", "target_first", FEATURES, params={"C": 0.05}),
    "M3": Spec("M3", "gbt_reg", "fwd_ret", FEATURES, params={"max_depth": 3, "min_samples_leaf": 200}),
}
RETURN_MODELS = {"M1", "M3"}
MODELS = {"M1", "M2", "M3"}


# ================================================================== data ====
def fill_grid(d: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Full hourly grid. An hour without a Coinbase candle had no trades: price carried forward, volume 0."""
    d = d[~d.index.duplicated(keep="last")].sort_index()[["open", "high", "low", "close", "volume"]]
    r = d.reindex(pd.date_range(d.index[0], d.index[-1], freq="h"))
    filled = r.close.isna().to_numpy()
    c = r.close.ffill()
    for col in ("open", "high", "low"):
        r[col] = r[col].fillna(c)
    r["close"], r["volume"] = c, r.volume.fillna(0.0)
    return r, filled


def labels_at(r: pd.DataFrame, filled: np.ndarray, pos: np.ndarray, h: int) -> pd.DataFrame:
    """Labels for decisions at the START of bar i (entry = its open; exit = last close at or before i+h-1)."""
    o, hi, lo, c = (r[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(r)
    vol = (np.log(r.close).diff().rolling(168, min_periods=96).std() * math.sqrt(h)).to_numpy()
    rows = []
    for i in pos:
        end = min(i + h - 1, n - 1)
        entry = o[i]
        x = {"fwd_ret": c[end] / entry - 1, "mae": lo[i:end + 1].min() / entry - 1, "mfe": hi[i:end + 1].max() / entry - 1,
             "carried_hours": int(filled[i:end + 1].sum()), "truncated": bool(i + h - 1 > n - 1),
             "target_first": np.nan, "stop_first": np.nan}
        v = vol[i - 1] if i >= 1 else np.nan
        if np.isfinite(v) and x["carried_hours"] == 0 and not x["truncated"]:      # barrier labels need contiguous bars
            up, dn = entry * (1 + v), entry * (1 - v)
            hd, hu = np.flatnonzero(lo[i:end + 1] <= dn), np.flatnonzero(hi[i:end + 1] >= up)
            fd, fu = (hd[0] if len(hd) else h), (hu[0] if len(hu) else h)
            x["stop_first"] = float(fd <= fu and fd < h)
            x["target_first"] = float(fu < fd)
        rows.append(x)
    return pd.DataFrame(rows, index=r.index[pos])


def decision_times(horizon: str) -> pd.DatetimeIndex:
    cfg = HORIZONS[horizon]
    t = pd.date_range(PERIODS["dev"][0], PERIODS["final"][1], freq="D", tz="UTC")
    return t[t.weekday == cfg["weekday"]] if cfg["weekday"] is not None else t


def build(horizon: str) -> pd.DataFrame:
    path = CACHE / f"panel_{horizon}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    h = HORIZONS[horizon]["h"]
    times = decision_times(horizon)
    u = cu.load()
    u = u[u.eligible & u.date.isin(times.normalize())]
    elig = set(zip(u.date, u["product"]))
    products = sorted(set(u["product"].unique()) | {"BTC-USD"})
    rows, btc = [], None
    for p in products:
        if not (HOURLY_DIR / f"{p}.csv").exists():
            continue
        r, filled = fill_grid(load_bars(p))
        f = _per_symbol_features(r)                       # indexed by bar end
        ts = times[(times >= r.index[0] + pd.Timedelta(hours=1)) & (times <= r.index[-1])]
        if p == "BTC-USD":
            btc = f.reindex(times)[["r_24h", "r_7d"]].rename(columns=lambda k: "btc_" + k)
        ts = pd.DatetimeIndex([t for t in ts if (t.normalize(), p) in elig])
        if len(ts) == 0:
            continue
        pos = r.index.get_indexer(ts)
        x = f.reindex(ts).join(labels_at(r, filled, pos, h))
        x["symbol"], x["decision_time"] = p, ts
        rows.append(x)
    pnl = pd.concat(rows, ignore_index=True)
    pnl = pnl.merge(btc, left_on="decision_time", right_index=True, how="left")
    pnl["rs_btc_24h"], pnl["rs_btc_7d"] = pnl.r_24h - pnl.btc_r_24h, pnl.r_7d - pnl.btc_r_7d
    g = pnl.groupby("decision_time")
    pnl["xs_rank_24h"] = g.r_24h.rank(pct=True)
    pnl["xs_rank_7d"] = g.r_7d.rank(pct=True)
    pnl["breadth_24h"] = g.r_24h.transform(lambda s: (s > 0).mean())
    pnl["xs_dispersion_24h"] = g.r_24h.transform("std")
    pnl["mkt_r_24h"] = g.r_24h.transform("median")
    pnl["label_end"] = pnl.decision_time + pd.Timedelta(hours=h)
    pnl = pnl.drop(columns=["btc_r_24h", "btc_r_7d"]).sort_values(["decision_time", "symbol"]).reset_index(drop=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    pnl.to_pickle(path)
    return pnl


def btc_returns(horizon: str) -> pd.Series:
    h = HORIZONS[horizon]["h"]
    r, filled = fill_grid(load_bars("BTC-USD"))
    ts = decision_times(horizon)
    ts = ts[ts <= r.index[-1]]
    return labels_at(r, filled, r.index.get_indexer(ts), h).fwd_ret


def in_phase(t: pd.Series | pd.DatetimeIndex, phase: str):
    a, b = (pd.Timestamp(x, tz="UTC") for x in PERIODS[phase])
    return (t >= a) & (t <= b)


# ================================================================ policy ====
def simulate(per: dict, periods, rt: float, abstain: bool = False, time_exit: bool = False, ew: bool = False) -> pd.DataFrame:
    """A4 policy. per[t] = DataFrame(symbol, score, pred, ret) of eligible coins with a known return.
    Returns one row per period: gross, cost, net, turnover (one-way), filled slots, entries, positions."""
    w_post: dict[str, float] = {}
    out = []
    for t in periods:
        g = per.get(t)
        target: dict[str, float] = {}
        if g is not None and len(g):
            if ew:
                target = {s: 1.0 / len(g) for s in g.symbol}
            else:
                top = g.dropna(subset=["score"]).sort_values(["score", "symbol"], ascending=[False, True]).head(K)
                if abstain:
                    top = top[[(s in w_post and p > 0) or (s not in w_post and p > rt) for s, p in zip(top.symbol, top.pred)]]
                target = {s: 1.0 / K for s in top.symbol}
        prev = {} if time_exit else w_post
        traded = sum(w_post.values()) + sum(target.values()) if time_exit else \
            sum(abs(target.get(s, 0.0) - prev.get(s, 0.0)) for s in set(target) | set(prev))
        cost = traded * rt / 2
        rets = dict(zip(g.symbol, g.ret)) if g is not None else {}
        gross = sum(w * rets[s] for s, w in target.items())
        out.append({"t": t, "gross": gross, "cost": cost, "net": (1 - cost) * (1 + gross) - 1, "turnover": traded / 2,
                    "filled": len(target) if not ew else K, "entries": len(set(target) - set(prev)),
                    "positions": {s: w * rets[s] for s, w in target.items()}})
        w_post = {s: w * (1 + rets[s]) / (1 + gross) for s, w in target.items()}
    return pd.DataFrame(out).set_index("t")


def per_period(panel: pd.DataFrame, score: pd.Series, pred: pd.Series | None = None) -> dict:
    d = panel.assign(score=score, pred=pred if pred is not None else score, ret=panel.fwd_ret).dropna(subset=["ret"])
    return {t: g[["symbol", "score", "pred", "ret"]].reset_index(drop=True) for t, g in d.groupby("decision_time")}


# =============================================================== metrics ====
def _ci(s: pd.Series, block: float, level: float = 0.90):
    m, lo, hi = mean_ci(s, mean_block=block, level=level)
    return {"mean": m, "ci90": [lo, hi]}


def alpha_beta(r: pd.Series, m: pd.Series, block: float, reps: int = 1000, seed: int = 3) -> dict:
    d = pd.concat([r, m], axis=1).dropna().to_numpy()
    if len(d) < 10 or d[:, 0].std() == 0:
        return {"alpha": 0.0, "beta": 0.0, "alpha_ci90": [0.0, 0.0]}
    def fit(x):
        b = np.cov(x[:, 0], x[:, 1])[0, 1] / x[:, 1].var(ddof=1)
        return x[:, 0].mean() - b * x[:, 1].mean(), b
    a, b = fit(d)
    rng = np.random.default_rng(seed)
    boots = [fit(d[stationary_bootstrap_idx(len(d), block, rng)])[0] for _ in range(reps)]
    return {"alpha": float(a), "beta": float(b), "alpha_ci90": [float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95))]}


def series_stats(r: pd.Series, ann: int) -> dict:
    eq = (1 + r).cumprod()
    sd = r.std()
    return {"mean": float(r.mean()), "vol_ann": float(sd * math.sqrt(ann)),
            "sharpe": float(r.mean() / sd * math.sqrt(ann)) if sd > 0 else 0.0,
            "total_return": float(eq.iloc[-1] - 1), "max_drawdown": float((eq / eq.cummax() - 1).min())}


def evaluate(res: pd.DataFrame, ew: pd.DataFrame, cfg: dict) -> dict:
    block, ann = cfg["block"], cfg["ann"]
    r = res.net
    thirds = np.array_split(r, 3)
    by_year = r.groupby(r.index.year).apply(lambda x: float((1 + x).prod() - 1))
    contrib = pd.Series([v for p in res.positions for v in p.values()], dtype=float)
    coin = pd.Series([s for p in res.positions for s in p], dtype=object)
    coin_pnl = contrib.groupby(coin.to_numpy()).sum().sort_values(ascending=False) if len(contrib) else pd.Series(dtype=float)
    sel_excess = res.gross - res.filled / K * ew.gross.reindex(res.index)
    T = len(r)
    out = {"periods": T, **series_stats(r, ann), "net_per_period": _ci(r, block), "gross_per_period": _ci(res.gross, block),
           "cost_per_period": float(res.cost.mean()), "turnover_per_period": float(res.turnover.mean()),
           "exposure": float(res.filled.mean() / K), "periods_fully_abstained": float((res.filled == 0).mean()),
           "slot_abstention": float(1 - res.filled.mean() / K), "entries": int(res.entries.sum()),
           "thirds_mean_net": [float(x.mean()) for x in thirds], "thirds_positive": int(sum(x.mean() > 0 for x in thirds)),
           "by_year_return": {int(k): v for k, v in by_year.items()},
           "selection_excess_gross": _ci(sel_excess, block),
           "alpha_vs_ew": alpha_beta(r, ew.net.reindex(res.index), block),
           "vol_scaled_to_ew_ann_return": float(r.mean() * (ew.net.reindex(res.index).std() / r.std()) * ann) if r.std() > 0 else 0.0,
           "dsr": float(deflated_sharpe(r, N_TRIALS_DSR, 1.0 / T)) if r.std() > 0 else 0.0,
           "position_concentration": concentration(contrib) if len(contrib) else {},
           "top_coins_share": {k: float(v / coin_pnl.sum()) for k, v in coin_pnl.head(3).items()} if len(coin_pnl) and coin_pnl.sum() else {}}
    return out


def calibration(panel: pd.DataFrame, pred: pd.Series, name: str) -> dict:
    d = panel.assign(pred=pred)
    if name == "M2":
        d = d.dropna(subset=["pred", "target_first"])
        p, y = d.pred.to_numpy(), d.target_first.to_numpy()
        return {"n": len(d), "base_rate": float(y.mean()), "brier_skill_vs_base_rate": float(skill_vs_base_rate(p, y)),
                "ece": float(ece(p, y)), "reliability": reliability(p, y).round(4).to_dict(orient="records")}
    if name in RETURN_MODELS:
        d = d.dropna(subset=["pred", "fwd_ret"])
        q = pd.qcut(d.pred.rank(method="first"), 10, labels=False)
        tab = d.groupby(q).agg(pred=("pred", "mean"), realised=("fwd_ret", "mean"), n=("pred", "size"))
        slope = float(np.polyfit(d.pred, d.fwd_ret, 1)[0]) if d.pred.std() > 0 else float("nan")
        return {"n": len(d), "slope_realised_on_predicted": slope, "share_pred_above_base_rt": float((d.pred > BASE_RT).mean()),
                "deciles": tab.round(5).to_dict(orient="records")}
    return {}


def score_config(name: str, panel: pd.DataFrame, pred: pd.Series, periods, ew_by_rt: dict, cfg: dict, full: bool = True) -> dict:
    """Decision-level evaluation of one configuration over `periods`."""
    per = per_period(panel, pred)
    abst = name in RETURN_MODELS
    res = simulate(per, periods, BASE_RT, abstain=abst)
    out = {"base": evaluate(res, ew_by_rt[BASE_RT], cfg), "_res": res}
    ic = rank_ic_by_period(panel.decision_time, pred, panel.fwd_ret)
    ic = ic[ic.index.isin(periods)]
    out["rank_ic"] = {**_ci(ic, cfg["block"]), "periods": len(ic)}
    if not full:
        return out
    out["cost_grid"] = {}
    for rt in GRID:
        rr = simulate(per, periods, rt, abstain=abst)
        s = series_stats(rr.net, cfg["ann"])
        out["cost_grid"][f"{rt:.4f}"] = {"label": GRID_LABEL[rt], "mean_net": s["mean"], "sharpe": s["sharpe"],
                                         "net_ci90": _ci(rr.net, cfg["block"])["ci90"], "exposure": float(rr.filled.mean() / K),
                                         "ew_mean_net": float(ew_by_rt[rt].net.mean())}
    te = simulate(per, periods, BASE_RT, abstain=abst, time_exit=True)
    out["time_exit_sensitivity"] = series_stats(te.net, cfg["ann"]) | {"turnover": float(te.turnover.mean())}
    out["calibration"] = calibration(panel[panel.decision_time.isin(periods)], pred[panel.decision_time.isin(periods)], name)
    if abst:
        forced = simulate(per, periods, BASE_RT, abstain=False)
        skipped = res.filled < K
        out["abstention_value"] = {
            "abstaining_minus_forced_net": _ci(res.net - forced.net, cfg["block"]),
            "forced_net_mean": float(forced.net.mean()), "forced_sharpe": series_stats(forced.net, cfg["ann"])["sharpe"],
            "periods_with_unfilled_slots": int(skipped.sum()),
            "forced_net_on_those_periods": float(forced.net[skipped].mean()) if skipped.any() else None,
            "forced_net_on_other_periods": float(forced.net[~skipped].mean()) if (~skipped).any() else None}
    return out


def matched_random(per: dict, filled: pd.Series, reps: int = 500, seed: int = 13) -> np.ndarray:
    """Mean gross per period of random coin selections with the same filled slots per period (selection skill only)."""
    rng = np.random.default_rng(seed)
    pools = {t: per[t].ret.to_numpy() for t in filled.index if t in per}
    means = np.empty(reps)
    for j in range(reps):
        tot = 0.0
        for t, n in filled.items():
            n = int(min(n, len(pools.get(t, []))))
            if n:
                tot += rng.choice(pools[t], n, replace=False).sum() / K
        means[j] = tot / len(filled)
    return means


def comparators(panel: pd.DataFrame, periods, horizon: str, cfg: dict) -> tuple[dict, dict]:
    per = per_period(panel, pd.Series(0.0, index=panel.index))
    ew_by_rt = {rt: simulate(per, periods, rt, ew=True) for rt in GRID}
    btc = btc_returns(horizon).reindex(periods).fillna(0.0)
    btc_net = btc.copy()
    btc_net.iloc[0] = (1 - BASE_RT / 2) * (1 + btc_net.iloc[0]) - 1
    btc_net.iloc[-1] = (1 + btc_net.iloc[-1]) * (1 - BASE_RT / 2) - 1
    out = {"no_trade": {"mean": 0.0, "sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0},
           "ew_universe": series_stats(ew_by_rt[BASE_RT].net, cfg["ann"]) | {
               "turnover_per_period": float(ew_by_rt[BASE_RT].turnover.mean()),
               "mean_coins": float(np.mean([len(per[t]) for t in periods if t in per]))},
           "btc_buy_hold": series_stats(btc_net, cfg["ann"])}
    return out, ew_by_rt


# ================================================================= folds ====
def oof_predictions(panel: pd.DataFrame, name: str, periods: pd.DatetimeIndex, h: int) -> tuple[pd.Series, list]:
    spec = SPECS[name]
    pred = pd.Series(np.nan, index=panel.index)
    if spec.kind == "rule":
        pred[:] = fit_predict(spec, panel.iloc[:0], panel)
        return pred, []
    folds = purged_walk_forward(pd.Series(periods), pd.Series(periods + pd.Timedelta(hours=h)), 5, min_train_frac=0.3,
                                embargo=pd.Timedelta(hours=h))
    covered = []
    for f in folds:
        test_p = periods[f.test]
        test_start = test_p[0]
        tr = panel[(panel.label_end < test_start - pd.Timedelta(hours=h)) & panel[spec.target].notna()]
        te = panel.decision_time.isin(test_p)
        pred[te] = fit_predict(spec, tr, panel[te])
        covered.extend(test_p)
    return pred, covered


def frozen_predictions(panel: pd.DataFrame, name: str, train_mask: pd.Series, eval_mask: pd.Series) -> pd.Series:
    spec = SPECS[name]
    pred = pd.Series(np.nan, index=panel.index)
    tr = panel[train_mask & panel[spec.target].notna()] if spec.kind != "rule" else panel.iloc[:0]
    pred[eval_mask] = fit_predict(spec, tr, panel[eval_mask])
    return pred


# ================================================================ phases ====
def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 8)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return o


def gate(horizon: str) -> dict:
    cfg = HORIZONS[horizon]
    panel = build(horizon)
    dev = panel[in_phase(panel.decision_time, "dev")]
    periods = pd.DatetimeIndex(sorted(dev.decision_time.unique()))
    per = per_period(dev, dev.r_7d)
    rng = np.random.default_rng(11)
    rhos = np.round(np.arange(0, 1.0001, 0.01), 2)
    oracle, synth, U, n_coins = [], np.zeros(len(rhos)), [], []
    used = 0
    for t in periods:
        y = per[t].ret.to_numpy()
        n = len(y)
        n_coins.append(n)
        if n <= K:
            continue
        used += 1
        u = y.mean()
        U.append(u)
        oracle.append(np.sort(y)[-K:].mean() - u)
        z = norm.ppf((pd.Series(y).rank(method="average").to_numpy() - 0.5) / n)
        eps = rng.standard_normal((200, n))
        s = rhos[:, None, None] * z[None, None, :] + np.sqrt(1 - rhos[:, None, None] ** 2) * eps[None, :, :]
        top = np.argpartition(-s, K - 1, axis=2)[:, :, :K]
        synth += (y[top].mean(axis=2).mean(axis=1) - u)
    synth /= used
    b1 = simulate(per, periods, BASE_RT)
    tau_b1 = float(b1.turnover.mean())

    def req(tau, rt):
        c = tau * rt
        ok = np.flatnonzero(synth >= c)
        return float(rhos[ok[0]]) if len(ok) else None

    table = {f"{rt:.4f}": {"label": GRID_LABEL[rt],
                           "rho_star_tau1": req(1.0, rt), "rho_star_tau_b1": req(tau_b1, rt), "rho_star_tau025": req(0.25, rt)}
             for rt in GRID}
    base = table[f"{BASE_RT:.4f}"]
    oracle_mean = float(np.mean(oracle))
    stop = base["rho_star_tau_b1"] is None or base["rho_star_tau_b1"] > 0.15 or oracle_mean < tau_b1 * BASE_RT
    out = {"horizon": horizon, "phase": "gate", "periods": len(periods), "periods_used": used,
           "coins_per_period": {"median": float(np.median(n_coins)), "min": int(np.min(n_coins)), "max": int(np.max(n_coins))},
           "ew_universe_mean_gross": float(np.mean(U)), "oracle_selection_excess_mean": oracle_mean,
           "synthetic_excess_by_rho": {f"{r:.2f}": float(v) for r, v in zip(rhos, synth) if round(r * 100) % 5 == 0},
           "b1_turnover_per_period": tau_b1, "required_rho": table,
           "rule": "stop if rho*(B1 turnover, base cost) > 0.15 or oracle < cost at B1 turnover",
           "decision": "STOP" if stop else "PROCEED"}
    return out


def phase_dev(horizon: str) -> dict:
    cfg = HORIZONS[horizon]
    h = cfg["h"]
    panel = build(horizon)
    dev = panel[in_phase(panel.decision_time, "dev")].reset_index(drop=True)
    periods = pd.DatetimeIndex(sorted(dev.decision_time.unique()))
    preds, covered = {}, None
    for name in cfg["configs"]:
        preds[name], cov = oof_predictions(dev, name, periods, h)
        if cov:
            covered = pd.DatetimeIndex(sorted(set(cov))) if covered is None else covered
    covered = covered if covered is not None else periods
    comp, ew_by_rt = comparators(dev, covered, horizon, cfg)
    res = {name: score_config(name, dev, preds[name], covered, ew_by_rt, cfg) for name in cfg["configs"]}
    mat = pd.DataFrame({n: r["_res"].net for n, r in res.items()})
    pbo = cscv_pbo(mat, 16)
    sharpe = {n: r["base"]["sharpe"] for n, r in res.items()}
    baselines = [b for b in ("B1", "B2") if b in sharpe]
    eligible = [m for m in cfg["configs"] if m in MODELS and all(sharpe[m] > sharpe[b] for b in baselines)
                and res[m]["base"]["entries"] > 0]
    candidate = max(eligible, key=lambda m: sharpe[m]) if eligible else None
    return {"horizon": horizon, "phase": "dev", "oof_periods": len(covered),
            "oof_range": [covered[0].isoformat(), covered[-1].isoformat()], "comparators": comp,
            "configs": {n: {k: v for k, v in r.items()} for n, r in res.items()},
            "pbo": {"pbo": pbo.pbo, "n_combinations": pbo.n_combinations, "perf_degradation_slope": pbo.perf_degradation_slope},
            "selection": {"by": "dev OOF net Sharpe at base cost among models beating B1 and B2", "sharpe": sharpe,
                          "eligible": eligible, "candidate": candidate}}


def phase_eval(horizon: str, phase: str) -> dict:
    cfg = HORIZONS[horizon]
    h = cfg["h"]
    panel = build(horizon)
    start = pd.Timestamp(PERIODS[phase][0], tz="UTC")
    train_phases = ["dev"] if phase == "validation" else ["dev", "validation"]
    train_mask = panel.decision_time.apply(lambda t: any(in_phase(pd.DatetimeIndex([t]), p)[0] for p in train_phases))
    train_mask &= panel.label_end < start - pd.Timedelta(hours=h)
    eval_mask = in_phase(panel.decision_time, phase)
    ev = panel[eval_mask]
    periods = pd.DatetimeIndex(sorted(ev.decision_time.unique()))
    comp, ew_by_rt = comparators(ev, periods, horizon, cfg)
    res = {}
    for name in cfg["configs"]:
        pred = frozen_predictions(panel, name, train_mask, eval_mask)[eval_mask]
        res[name] = score_config(name, ev, pred, periods, ew_by_rt, cfg)
    return {"horizon": horizon, "phase": phase, "periods": len(periods), "train_rows": int(train_mask.sum()),
            "range": [periods[0].isoformat(), periods[-1].isoformat()], "comparators": comp, "configs": res,
            "_ev": ev, "_ew": ew_by_rt}


def verdict(out: dict, dev: dict, val: dict, horizon: str) -> dict:
    cfg = HORIZONS[horizon]
    cand = dev["selection"]["candidate"]
    qualified = cand is not None and val["configs"][cand]["base"]["net_per_period"]["mean"] >= 0
    rows = {}
    for name, r in out["configs"].items():
        b = r["base"]
        rows[name] = {"reject_no_useful_effect": b["selection_excess_gross"]["ci90"][1] < b["cost_per_period"]}
    v = {"candidate": cand, "candidate_qualified_after_validation": qualified, "per_config_reject_test": rows}
    if not qualified:
        v["verdict"] = "NO QUALIFYING CANDIDATE: no configuration can pass"
        return v
    r, b = out["configs"][cand], out["configs"][cand]["base"]
    ev, ew = out["_ev"], out["_ew"]
    per = per_period(ev, pd.Series(0.0, index=ev.index))
    rand = matched_random(per, r["_res"].filled)
    b1_diff = _ci(r["_res"].net - out["configs"]["B1"]["_res"].net, cfg["block"])
    checks = {
        "1_net_lower_bound_gt_0": b["net_per_period"]["ci90"][0] > 0,
        "2_sharpe_ge_0.5": b["sharpe"] >= 0.5,
        "3_two_of_three_thirds_positive": b["thirds_positive"] >= 2,
        "4_alpha_vs_ew_lower_bound_gt_0": b["alpha_vs_ew"]["alpha_ci90"][0] > 0,
        "5_gross_above_random_p95": b["gross_per_period"]["mean"] > float(np.quantile(rand, 0.95)),
        "6_beats_b1_paired": b1_diff["ci90"][0] > 0,
        "7_pbo_le_0.05": dev["pbo"]["pbo"] <= 0.05,
        "8_dsr_ge_0.95": b["dsr"] >= 0.95,
        "9_entries_ge_100": b["entries"] >= 100,
    }
    if cand == "M2":
        c = r["calibration"]
        checks["10_m2_calibrated"] = c["brier_skill_vs_base_rate"] > 0 and c["ece"] <= 0.05
    v.update({"checks": checks, "matched_random_gross_p95": float(np.quantile(rand, 0.95)),
              "matched_random_p_value": float((rand >= b["gross_per_period"]["mean"]).mean()), "vs_b1_paired": b1_diff})
    v["verdict"] = "PASS" if all(checks.values()) else ("REJECT (no useful effect)" if rows[cand]["reject_no_useful_effect"]
                                                        else "INCONCLUSIVE")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "gate", "dev", "validation", "final"])
    ap.add_argument("--horizon", choices=list(HORIZONS), default="p1a")
    ap.add_argument("--reproduce", action="store_true")
    a = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if a.phase == "build":
        for hz in HORIZONS:
            p = build(hz)
            print(hz, len(p), "rows", p.decision_time.nunique(), "periods", int(p.carried_hours.gt(0).sum()), "rows with carried hours",
                  int(p.truncated.sum()), "truncated")
        return
    path = RESULTS / f"{a.horizon}_{a.phase}.json"
    prior = {p: RESULTS / f"{a.horizon}_{p}.json" for p in ("gate", "dev", "validation")}
    order = ["gate", "dev", "validation", "final"]
    for need in order[:order.index(a.phase)]:
        if not prior[need].exists():
            sys.exit(f"run {need} first")
    if a.phase != "gate" and json.loads(prior["gate"].read_text())["decision"] == "STOP":
        sys.exit(f"{a.horizon}: development stopping check said STOP; later phases are not run (A2)")
    if path.exists() and not a.reproduce and a.phase == "final":
        sys.exit("final phase already run once; use --reproduce to recompute deterministically")
    if a.phase == "gate":
        out = gate(a.horizon)
    elif a.phase == "dev":
        out = phase_dev(a.horizon)
    else:
        out = phase_eval(a.horizon, a.phase)
        if a.phase == "final":
            dev, val = json.loads(prior["dev"].read_text()), json.loads(prior["validation"].read_text())
            out["verdict"] = verdict(out, dev, val, a.horizon)
    js = jsonable(out)
    if a.reproduce:
        old = json.loads(path.read_text())
        same = json.dumps(old, sort_keys=True) == json.dumps(js, sort_keys=True)
        print("REPRODUCED IDENTICALLY" if same else "DIFFERS")
        record("reproduction", f"p1_{a.horizon}_{a.phase}_reproduction", {"prereg": "prereg_p1"}, "2021-03-01..2026-10-24",
               "deterministic reproduction", metrics={"identical": same})
        return
    path.write_text(json.dumps(js, indent=1, sort_keys=True))
    summary = {"decision": js.get("decision")} if a.phase == "gate" else (
        {"candidate": js["selection"]["candidate"], "pbo": js["pbo"]["pbo"], "sharpe": js["selection"]["sharpe"]} if a.phase == "dev" else
        {n: {"sharpe": c["base"]["sharpe"], "mean_net": c["base"]["mean"]} for n, c in js["configs"].items()})
    if a.phase == "final":
        summary["verdict"] = js["verdict"]["verdict"]
    record("result", f"p1_{a.horizon}_{a.phase}", {"prereg": "prereg_p1", "amendment": "prereg_p1_amendment1"},
           f"{PERIODS.get(a.phase, PERIODS['dev'])[0]}..{PERIODS.get(a.phase, PERIODS['dev'])[1]}",
           f"P1 {a.horizon} {a.phase}", metrics=summary)
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
