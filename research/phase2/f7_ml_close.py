"""F7: ML ranking executed at the close (research/phase2/FAMILIES.md, round 2).

    python research/phase2/f7_ml_close.py dev

Decision at 15:30 ET on session t from daily bars through t-1 plus p = the 15:30 price of t (open of the 15:30
bar, from F4's cached 14:30-16:00 windows; top-500 universe). Entry at the close of t, exit at the close of t+1,
both marked at the close of the 15:30 bar (last continuous trade, closing-quote proxy). Training years before the
intraday data (2016-2019) use the daily close as a stand-in for p (labelled in FAMILIES.md).
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import evaluate as ev                               # noqa: E402
from research.phase2 import f6_ml_rank as f6                              # noqa: E402
from research.phase2 import stages, xs                                    # noqa: E402
from research.phase2.data import PANELS                                   # noqa: E402
from research.phase2.f1_reversal import load_panels                       # noqa: E402

FAMILY = "F7"
RESULTS = ROOT / "research" / "phase2" / "results"
DEV = ("2020-01-02", "2022-12-30")
CONFIGS = {"B0": ("ridge_reversal", 20, False, 1), "C1": ("hgb_all", 20, False, 1), "C2": ("hgb_all", 20, True, 1),
           "C3": ("hgb_all", 10, False, 1), "C4": ("hgb_all", 20, False, 2)}


def intraday_prices(index, columns) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(p1530, close_1530bar) panels from F4's table; NaN where the window was not fetched."""
    t = pickle.loads(sorted(PANELS.glob("f4_table_*"))[0].read_bytes())
    t = t[~t.half]
    p = t.pivot_table(index="day", columns="symbol", values="entry").reindex(index=index, columns=columns)
    c = t.pivot_table(index="day", columns="symbol", values="exit").reindex(index=index, columns=columns)
    return p, c


def features_at_1530(a: dict, r: dict, cols: list[str], p: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """F6's feature families with the 15:30 price p of t in place of t's close; everything else through t-1."""
    c_prev = a["close"][cols].shift(1)
    o = a["open"][cols]
    spy_p, spy_c = p["SPY"], a["close"]["SPY"].shift(1)
    lag = {k: v.shift(1) for k, v in f6.feature_panel(a, r, cols).items()}   # vol20, range, liquidity, beta: t-1
    f = {"r1": p / c_prev - 1, "r5": p / a["close"][cols].shift(5) - 1, "gap": o / c_prev - 1, "intraday": p / o - 1,
         "r20": p / a["close"][cols].shift(20) - 1, "r60": p / a["close"][cols].shift(60) - 1,
         "r120": p / a["close"][cols].shift(120) - 1,
         "dist52": p / a["close"][cols].shift(1).rolling(252, min_periods=126).max() - 1,
         "vol20": lag["vol20"], "range": lag["range"], "vol_ratio": lag["vol_ratio"], "log_dvol": lag["log_dvol"],
         "beta60": lag["beta60"]}
    spy_r1 = spy_p / spy_c - 1
    spy_r5 = spy_p / a["close"]["SPY"].shift(5) - 1
    f["r1_mkt"] = f["r1"].sub(spy_r1, axis=0)
    f["r5_mkt"] = f["r5"].sub(spy_r5, axis=0)
    return f


def dev() -> dict:
    a, r, comp = load_panels()
    e500, dvol = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=500)
    elig = e500.shift(1).fillna(False).astype(bool)              # universe known before session t
    cols = sorted(set(elig.columns[elig.any()]) | {"SPY"})
    elig = elig.reindex(columns=cols, fill_value=False)
    elig["SPY"] = False
    p_intra, c_intra = intraday_prices(elig.index, cols)
    p = p_intra.where(p_intra.notna() & (elig.index >= pd.Timestamp("2019-12-02"))[:, None], a["close"][cols])
    p = p.where(~((elig.index >= pd.Timestamp("2019-12-02"))[:, None] & p_intra.isna()), np.nan)
    close_mark = c_intra.where(c_intra.notna(), a["close"][cols])
    f = features_at_1530(a, r, cols, p)
    target = close_mark.pct_change(fill_method=None)              # row s: close(s-1) -> close(s); label uses shift(-1)
    d = f6.long_frame(f, target, elig)
    preds = {name: {y: f6.fit_predict(d, feats, model, y) for y in (2020, 2021, 2022)}
             for name, (model, feats) in {"ridge_reversal": ("ridge", f6.FAMILIES["reversal"]),
                                          "hgb_all": ("hgb", f6.ALL)}.items()}
    ic = {n: {y: f6.daily_ic(d, pr["pred"]) for y, pr in by.items()} for n, by in preds.items()}
    ret = close_mark.shift(-1) / close_mark - 1                   # row t: close t -> close t+1
    hs = ev.measured_half_spread(dvol.reindex(columns=cols), elig, "15:59")
    rt = 2 * (hs + ev.SLIP_BASE + ev.FEES_PER_SIDE)
    keep = (elig.index >= pd.Timestamp(DEV[0])) & (elig.index <= pd.Timestamp(DEV[1]))
    e_ = elig[keep].astype(float)
    cw = e_.div(e_.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    cp = ev.backtest_weights(cw, ret[keep], hs[keep])
    out = {"family": FAMILY, "window": DEV, "rank_ic_dev": ic, "configs": {}}
    quals, metrics = {}, {}
    for cfg, (name, n, cost_filter, hold) in CONFIGS.items():
        pr = pd.concat(preds[name].values())
        sc = pr["pred"].unstack().reindex(index=elig.index, columns=cols)
        if cost_filter:
            sc = sc.where(pr["exp_dem"].unstack().reindex(index=elig.index, columns=cols) > rt)
        rk = sc.rank(axis=1, ascending=False, method="first")
        w = (rk <= n).astype(float) / n                           # row t: decided at 15:30 t, held close t -> t+1
        if hold == 2:
            w = 0.5 * w + 0.5 * w.shift(1).fillna(0.0)
        w = w.where(ret.notna(), 0.0)
        p_ = ev.backtest_weights(w[keep], ret[keep], hs[keep])
        ps = ev.backtest_weights(w[keep], ret[keep], hs[keep], slip=ev.SLIP_STRESS)
        summ = ev.summarise(p_, cp["net"], cp["gross"], ps["net"])
        summ["diagnosis"] = {"model": name, "rank_ic": ic[name], "cash_share": float((w[keep].sum(axis=1) == 0).mean()),
                             "measured_rt_cost_bp_median": float(np.nanmedian(rt[keep].where(w[keep] > 0)) * 1e4)}
        q = ev.dev_qualifies(summ)
        out["configs"][cfg] = {"spec": [name, n, cost_filter, hold], "summary": summ, "qualifiers": q}
        quals[cfg] = q
        metrics[cfg] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"], "model": name}
    stages.record_dev(FAMILY, quals, metrics)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "f7_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


if __name__ == "__main__":
    r = dev()
    print("IC", r["rank_ic_dev"])
    for k, v in r["configs"].items():
        s = v["summary"]
        print(k, v["spec"], f"net {s['net']['mean_bp']:.2f}bp/day [{s['net']['ci_bp'][0]:.1f},{s['net']['ci_bp'][1]:.1f}] "
                 f"gross {s['gross']['mean_bp']:.2f} cost {s['cost_bp_per_day']:.2f} vs_ctrl_gross {s['vs_control_gross_bp']} "
                 f"vs_ctrl_net {s['vs_control_net_bp']} years { {y: round(x * 1e4) for y, x in s['by_year_net'].items()} } "
                 f"top10 {s['top10_days_share']} qual {v['qualifiers']}")
