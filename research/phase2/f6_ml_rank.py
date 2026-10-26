"""F6: machine-learning ranking of next-day (open-to-open) returns, liquid US stocks (research/phase2/FAMILIES.md).

    python research/phase2/f6_ml_rank.py dev

Same opportunity set and execution as F1 (top-1,000 liquid operating companies; signal after the close of t;
market-on-open entry at t+1; exit at the open of t+2). Models never place orders.

Walk-forward: for each year Y in 2017..2022 a model is fitted on all eligible rows of 2016..Y-1 and predicts Y.
2017-2019 predictions are used only to choose C3's single feature family (mean daily rank IC) and are reported
as diagnostics; development performance is read on 2020-2022 predictions. 2016-2019 is survivorship-affected
and used for training only (PHASE2_PROTOCOL §2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import evaluate as ev                               # noqa: E402
from research.phase2 import stages, xs                                    # noqa: E402
from research.phase2.f1_reversal import load_panels, open_to_open_with_exit   # noqa: E402

FAMILY = "F6"
RESULTS = ROOT / "research" / "phase2" / "results"
DEV = ("2020-01-02", "2022-12-30")
N = 20
FAMILIES = {
    "reversal": ["r1", "r5", "gap", "intraday"],
    "momentum": ["r20", "r60", "r120", "dist52"],
    "volatility": ["vol20", "range"],
    "liquidity": ["vol_ratio", "log_dvol"],
    "market_relative": ["r1_mkt", "r5_mkt", "beta60"],
}
ALL = [f for fs in FAMILIES.values() for f in fs]
HGB = dict(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=200, random_state=0)


def feature_panel(a: dict, r: dict, cols: list[str]) -> dict[str, pd.DataFrame]:
    o, h, l, c = (a[k][cols].astype("float32") for k in ("open", "high", "low", "close"))
    v = r["volume"][cols].astype("float32")
    ret1 = c.pct_change(fill_method=None)
    spy = a["close"]["SPY"].pct_change(fill_method=None)
    f = {"r1": ret1, "r5": c.pct_change(5, fill_method=None), "gap": o / c.shift(1) - 1, "intraday": c / o - 1,
         "r20": c.pct_change(20, fill_method=None), "r60": c.pct_change(60, fill_method=None),
         "r120": c.pct_change(120, fill_method=None), "dist52": c / c.rolling(252, min_periods=126).max() - 1,
         "vol20": ret1.rolling(20, min_periods=20).std(), "range": (h - l) / c,
         "vol_ratio": v / v.shift(1).rolling(20, min_periods=20).mean(),
         "log_dvol": np.log((r["close"][cols] * r["volume"][cols]).rolling(20, min_periods=20).mean().astype("float64") + 1),
         "r1_mkt": ret1.sub(spy, axis=0),
         "r5_mkt": c.pct_change(5, fill_method=None).sub(a["close"]["SPY"].pct_change(5, fill_method=None), axis=0)}
    cov = ret1.rolling(60, min_periods=40).cov(spy)
    f["beta60"] = cov.div(spy.rolling(60, min_periods=40).var(), axis=0)
    return f


def long_frame(f: dict, target: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    """One row per eligible (date t, symbol): cross-sectional pct-ranks of every feature at t, and the rank of
    the demeaned next-session open-to-open return (the label; it lies entirely after t)."""
    mask = eligible.stack()
    mask = mask[mask].index
    cols = {}
    for k, df in f.items():
        x = df.where(eligible).rank(axis=1, pct=True)
        cols[k] = x.stack().reindex(mask).astype("float32")
    fwd = target.shift(-1)                                       # entered at t+1 open, exited at t+2 open
    dem = fwd.where(eligible).sub(fwd.where(eligible).mean(axis=1), axis=0)
    cols["y_rank"] = dem.rank(axis=1, pct=True).stack().reindex(mask).astype("float32")
    cols["y_dem"] = dem.stack().reindex(mask).astype("float32")
    d = pd.DataFrame(cols)
    d.index.names = ["date", "symbol"]
    return d


def fit_predict(d: pd.DataFrame, feats: list[str], model: str, year: int) -> pd.Series:
    tr = d[(d.index.get_level_values(0).year < year)].dropna(subset=feats + ["y_rank"])
    te = d[(d.index.get_level_values(0).year == year)].dropna(subset=feats)
    X, y = tr[feats].fillna(0.5).to_numpy(), tr["y_rank"].to_numpy()
    m = Ridge(alpha=1.0) if model == "ridge" else HistGradientBoostingRegressor(**HGB)
    m.fit(X, y)
    pred = pd.Series(m.predict(te[feats].fillna(0.5).to_numpy()), index=te.index)
    # calibration table from the training fit: predicted-rank decile -> mean realised demeaned return
    tp = pd.Series(m.predict(X), index=tr.index)
    dec = pd.qcut(tp.rank(method="first"), 10, labels=False)
    cal = tr["y_dem"].groupby(dec.to_numpy()).mean()
    edges = np.quantile(tp, np.linspace(0, 1, 11))
    exp_ret = pd.Series(cal.reindex(np.clip(np.searchsorted(edges, pred.to_numpy(), side="right") - 1, 0, 9)).to_numpy(),
                        index=pred.index)
    return pd.DataFrame({"pred": pred, "exp_dem": exp_ret})


def daily_ic(d: pd.DataFrame, pred: pd.Series) -> float:
    x = pd.DataFrame({"p": pred, "y": d["y_rank"].reindex(pred.index)}).dropna()
    return float(x.groupby(level=0).apply(lambda g: g.p.corr(g.y, method="spearman")).mean())


def weights_from(pred: pd.DataFrame, shape_like: pd.DataFrame, cost_cut: pd.DataFrame | None = None) -> pd.DataFrame:
    """Top-N by prediction at t, entered at t+1. `cost_cut` (date t x symbol): a name is held only if its
    calibrated expected demeaned return exceeds its own modelled round-trip cost (C4)."""
    p = pred["pred"].unstack()
    if cost_cut is not None:
        p = p.where(pred["exp_dem"].unstack() > cost_cut.reindex_like(p))
    r = p.rank(axis=1, ascending=False, method="first")
    w = (r <= N).astype(float) / N
    return w.reindex(index=shape_like.index, columns=shape_like.columns).fillna(0.0).shift(1).fillna(0.0)


def dev(only: list[str] | None = None) -> dict:
    a, r, comp = load_panels()
    elig, dvol = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=1000)
    cols = list(elig.columns[elig.any()])
    elig = elig[cols]
    f = feature_panel(a, r, cols)
    target = open_to_open_with_exit({"open": a["open"][cols], "close": a["close"][cols]})
    d = long_frame(f, target, elig)
    years = range(2017, 2023)
    preds: dict[str, dict[int, pd.DataFrame]] = {}
    specs = {"ridge_reversal": ("ridge", FAMILIES["reversal"]), "ridge_all": ("ridge", ALL), "hgb_all": ("hgb", ALL)}
    for fam, feats in FAMILIES.items():
        specs[f"hgb_{fam}"] = ("hgb", feats)
    if only:
        need = {configs_needed for c, configs_needed in {"B0": "ridge_reversal", "C1": "ridge_all", "C2": "hgb_all",
                                                           "C4": "hgb_all"}.items() if c in only}
        specs = {k: v for k, v in specs.items() if k in need}
    for name, (model, feats) in specs.items():
        preds[name] = {y: fit_predict(d, feats, model, y) for y in years}
    ic = {name: {y: daily_ic(d, p["pred"]) for y, p in by.items()} for name, by in preds.items()}
    pre = {k: float(np.mean([ic[f"hgb_{k}"][y] for y in (2017, 2018, 2019)])) for k in FAMILIES if f"hgb_{k}" in ic}
    best = max(pre, key=pre.get) if pre else "momentum"
    configs = {"B0": "ridge_reversal", "C1": "ridge_all", "C2": "hgb_all", "C3": f"hgb_{best}", "C4": "hgb_all"}
    opens = a["open"][cols]
    ret = target
    hs = ev.measured_half_spread(dvol[cols], elig, "09:31").shift(1)   # Amendment 1
    # C4: the modelled round trip per name, known at t (Amendment 1 measured band median at 09:31, both sides).
    # The first F6 run used a flat 2 bp half-spread here, which is not the registered cost model (correction noted
    # in research/phase2/results/f6_dev.json -> c4_correction).
    rt_cost = 2 * (ev.measured_half_spread(dvol[cols], elig, "09:31") + ev.SLIP_BASE + ev.FEES_PER_SIDE)
    cw = xs.control_weights(elig).where(opens.notna(), 0.0)
    keep = (elig.index >= pd.Timestamp(DEV[0])) & (elig.index <= pd.Timestamp(DEV[1]))
    cp = ev.backtest_weights(cw[keep], ret[keep], hs[keep])
    out = {"family": FAMILY, "window": DEV, "c3_family_chosen_on_2017_2019_ic": {"chosen": best, "ic": pre},
           "rank_ic_by_year": ic, "configs": {}}
    quals, metrics = {}, {}
    for cfg, name in configs.items():
        if only and cfg not in only:
            continue
        pr = pd.concat([preds[name][y] for y in (2020, 2021, 2022)])
        w = weights_from(pr, elig, cost_cut=rt_cost if cfg == "C4" else None).where(opens.notna(), 0.0)
        p = ev.backtest_weights(w[keep], ret[keep], hs[keep])
        ps = ev.backtest_weights(w[keep], ret[keep], hs[keep], slip=ev.SLIP_STRESS)
        summ = ev.summarise(p, cp["net"], cp["gross"], ps["net"])
        dec = pd.qcut(pr["pred"].groupby(level=0).rank(pct=True), 10, labels=False)
        summ["diagnosis"] = {"model": name, "rank_ic_dev": {y: ic[name][y] for y in (2020, 2021, 2022)},
                             "decile_mean_demeaned_bp": {int(k): float(v * 1e4) for k, v in
                                                         d["y_dem"].reindex(pr.index).groupby(dec.to_numpy()).mean().items()},
                             "cash_share": float((w[keep].sum(axis=1) == 0).mean())}
        q = ev.dev_qualifies(summ)
        out["configs"][cfg] = {"spec": name, "summary": summ, "qualifiers": q}
        quals[cfg] = q
        metrics[cfg] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"], "model": name}
    RESULTS.mkdir(parents=True, exist_ok=True)
    if only:                                     # correction run: merge into the full development result
        full = json.loads((RESULTS / "f6_dev.json").read_text())
        for cfg in only:
            full["configs"][f"{cfg}_first_run_superseded"] = full["configs"][cfg]
            full["configs"][cfg] = out["configs"][cfg]
        full["c4_correction"] = ("C4's cost filter first used a flat 2 bp half-spread instead of the registered "
                                 "Amendment-1 per-name measured cost; rerun with the registered cost model.")
        (RESULTS / "f6_dev.json").write_text(json.dumps(full, indent=1, default=float))
        allq = {k: v["qualifiers"] for k, v in full["configs"].items() if "_superseded" not in k}
        stages._save(FAMILY, {**stages._load(FAMILY), "dev": {"qualifiers": allq}})
        from tradelab.research.registry import record
        for cfg in only:
            record("result", f"p2_{FAMILY}_dev_correction:{cfg}", {"family": FAMILY, "config": cfg}, "development",
                   "implementation correction of a registered config (not a new trial)",
                   metrics={"is_trial": False, "qualifiers": quals[cfg], **metrics[cfg]})
        return full
    stages.record_dev(FAMILY, quals, metrics)
    (RESULTS / "f6_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


if __name__ == "__main__":
    r = dev(sys.argv[1].split(",") if len(sys.argv) > 1 else None)
    print("C3 family:", r["c3_family_chosen_on_2017_2019_ic"])
    for k, v in r["configs"].items():
        s = v["summary"]
        print(k, v["spec"], f"net {s['net']['mean_bp']:.2f}bp/day sh {s['net']['sharpe']:.2f} gross {s['gross']['mean_bp']:.2f} "
                 f"vs_ctrl_net {s['vs_control_net_bp']} ic {s['diagnosis']['rank_ic_dev']} qual {v['qualifiers']}")
