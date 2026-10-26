"""Phase-3 strategy research.

  .venv/bin/python research/study_strategies.py dev          # parameter search on 2018-2021 (logged)
  .venv/bin/python research/study_strategies.py validate     # chosen configs on 2022-2023
  .venv/bin/python research/study_strategies.py preregister  # freeze configs + pass criteria (before test)
  .venv/bin/python research/study_strategies.py test         # ONE run on 2024-01-01..2026-10-24 + holdouts + stress

Rules: dev picks parameters; validation and test never feed back into choices. The test phase reads
frozen configurations from the registry, not from this file, and refuses to run twice.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradelab.data.candles import load  # noqa: E402
from tradelab.research.engine import CostModel, ExecModel, simulate, sleeves  # noqa: E402
from tradelab.research.gate import reliability, walk_forward_gate  # noqa: E402
from tradelab.research.metrics import bootstrap, deflated_sharpe  # noqa: E402
from tradelab.research.registry import entries, record  # noqa: E402
from tradelab.research.walkforward import walk_forward, yearly_splits  # noqa: E402
from tradelab.strategies import trend  # noqa: E402
from tradelab.strategies.breakout import breakout  # noqa: E402
from tradelab.strategies.calendar import event_overlay, load_calendar  # noqa: E402
from tradelab.strategies.fixed import fixed  # noqa: E402
from tradelab.strategies.meanrev import meanrev  # noqa: E402
from tradelab.strategies.regime import btc_regimes, regime_selector, trailing_sharpe_selector  # noqa: E402
from tradelab.strategies.relative import rotation  # noqa: E402

OUT = ROOT / "research" / "out"
PAIR = ["BTC-USD", "ETH-USD"]
HOLDOUT = ["LTC-USD", "BCH-USD", "ETC-USD"]
DEV, VAL, TEST = ("2018-01-01", "2021-12-31"), ("2022-01-01", "2023-12-31"), ("2024-01-01", "2026-10-24")
REAL = CostModel(fee=0.006, half_spread=0.0001, slippage=0.0005)          # 0.66%/side
ALT = CostModel(fee=0.006, half_spread=0.0005, slippage=0.0015)           # 0.80%/side: thinner books for alts
STRESS = CostModel(fee=0.010, half_spread=0.0005, slippage=0.0020)        # 1.25%/side
RT = 2 * REAL.per_side

GRIDS = {
    "fixed": [dict(weight=0.33)],      # chosen a priori (~baseline exposure), not searched
    "breakout": [dict(entry_n=n, stop_atr=k) for n in (20, 50, 100) for k in (2.0, 3.0, 4.0)],
    "meanrev": [dict(trend_n=t, entry=e, max_hold=h) for t in (100, 200) for e in (5.0, 10.0, 20.0) for h in (5, 10)],
    "rotation": [dict(lookback=l, top_k=k, rebalance_days=r, market_filter=m)
                 for l in (30, 90) for k in (1, 3) for r in (7, 28) for m in (True, False)],
    "selector_trailing": [dict(margin=m) for m in (0.0, 0.3)],
    "selector_regime": [dict(min_hold=h) for h in (20, 60)],
    "gate": [dict(horizon=20, z=z) for z in (1.0, 1.645)],
    "calendar": [dict(events=["FOMC", "CPI"], days_before=d, scale=x) for d in (1, 2) for x in (0.0, 0.5)],
}


def _calendar(events, days_before, scale):
    cal = load_calendar()
    if cal is None:
        raise FileNotFoundError("data/events/macro_calendar.csv not present")
    return event_overlay(trend.BASELINE, cal, tuple(events), days_before, scale)


FACTORY = {"fixed": fixed, "breakout": breakout, "meanrev": meanrev, "calendar": _calendar}


# ---------------------------------------------------------------- data
def pair_data(assets=PAIR):
    dfs = {a: load(a, "1d") for a in assets}
    close = pd.DataFrame({a: d.close for a, d in dfs.items()}).loc["2018-01-01":]
    fill = pd.DataFrame({a: d.open for a, d in dfs.items()}).loc["2018-01-01":]
    # engine.simulate values a held asset at 0 on a missing candle; carry the last price instead
    return dfs, close.ffill(), fill.fillna(close.ffill())


def universe_data():
    close, vol, opn = {}, {}, {}
    for p in sorted((ROOT / "data" / "universe").glob("*_1d.csv")):
        d = pd.read_csv(p, index_col=0)
        d.index = pd.to_datetime(d.index, utc=True)
        a = p.name.replace("_1d.csv", "")
        close[a], vol[a], opn[a] = d.close, d.volume, d.open
    close, vol, opn = pd.DataFrame(close), pd.DataFrame(vol), pd.DataFrame(opn)
    idx = pd.date_range(pd.Timestamp("2017-01-01", tz="UTC"), pd.Timestamp(TEST[1], tz="UTC"), freq="D")
    return close.reindex(idx), vol.reindex(idx), opn.reindex(idx)


# ---------------------------------------------------------------- runs
def run_pair(signal_fn, dfs, close, fill, cost=REAL, ex=ExecModel()):
    tgt = pd.DataFrame({a: signal_fn(d) for a, d in dfs.items()}).reindex(close.index)
    return sleeves(close, fill, tgt, 1000, cost, ex)


def run_rotation(params, U, cost=ALT, ex=ExecModel()):
    close, vol, opn = U
    w = rotation(**params).weights(close, vol, close["BTC-USD"])
    c = close.ffill().loc["2018-01-01":]
    f = opn.fillna(close.ffill()).loc["2018-01-01":]
    w = w.loc[c.index]
    keep = [a for a in c.columns if (w[a] > 0).any()]   # only simulate coins ever held
    if not keep:
        keep = ["BTC-USD"]
    return simulate(c[keep], f[keep], w[keep], 1000, cost, ex)


def rets(res):
    r = res.equity.pct_change()
    r.iloc[0] = res.equity.iloc[0] / res.capital - 1
    return r


def expo(res):
    return res.weights.sum(axis=1)


def period_stats(r: pd.Series, e: pd.Series | None, trades: pd.DataFrame | None, start, end) -> dict:
    r = r.loc[start:end]
    eq = (1 + r).cumprod()
    yrs = len(r) / 365
    dd = (eq / eq.cummax().clip(lower=1.0) - 1).min()
    out = {"CAGR": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(r.mean() / r.std() * math.sqrt(365)) if r.std() > 0 else 0.0,
           "maxDD": float(dd), "vol": float(r.std() * math.sqrt(365)), "sr_daily": float(r.mean() / r.std()) if r.std() > 0 else 0.0}
    if e is not None:
        out["exposure"] = float(e.loc[start:end].mean())
    if trades is not None and len(trades):
        t = trades[(trades.time >= pd.Timestamp(start, tz="UTC")) & (trades.time <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1))]
        out["orders_per_yr"] = len(t) / yrs
    return out


class Lab:
    """Caches full-sample runs; every period's numbers come from slices of the same run."""

    def __init__(self):
        self.dfs, self.close, self.fill = pair_data()
        self._U = None
        self.cache = {}

    @property
    def U(self):
        if self._U is None:
            self._U = universe_data()
        return self._U

    def single(self, family, params, cost=REAL, ex=ExecModel(), dfs=None, close=None, fill=None):
        key = (family, json.dumps(params, sort_keys=True), cost, ex, id(dfs))
        if key not in self.cache:
            spec = FACTORY[family](**params) if family in FACTORY else params["spec"]
            self.cache[key] = run_pair(spec, dfs or self.dfs, self.close if close is None else close,
                                       self.fill if fill is None else fill, cost, ex)
        return self.cache[key]

    def baseline(self, cost=REAL, ex=ExecModel()):
        return self._named("baseline", trend.BASELINE, cost, ex)

    def _named(self, name, spec, cost=REAL, ex=ExecModel()):
        key = (name, cost, ex)
        if key not in self.cache:
            self.cache[key] = run_pair(spec, self.dfs, self.close, self.fill, cost, ex)
        return self.cache[key]

    def fixed_matched(self, exposure, cost=REAL):
        w = round(float(exposure), 2)
        return self._named(f"fixed_{w}", fixed(w), cost)

    def rotation(self, params, cost=ALT, ex=ExecModel()):
        key = ("rotation", json.dumps(params, sort_keys=True), cost, ex)
        if key not in self.cache:
            self.cache[key] = run_rotation(params, self.U, cost, ex)
        return self.cache[key]

    # selectors combine return streams of the baseline, a fixed allocation and cash
    def candidates(self, cost=REAL):
        b, f = self.baseline(cost), self._named("fixed_0.33", fixed(0.33), cost)
        R = pd.DataFrame({"baseline": rets(b), "fixed_33": rets(f), "cash": 0.0})
        E = pd.DataFrame({"baseline": expo(b), "fixed_33": expo(f), "cash": 0.0})
        return R, E

    def selector(self, kind, params, cost=REAL):
        R, E = self.candidates(cost)
        refits = [f"{y}-01-01" for y in range(2020, 2027)]
        if kind == "selector_trailing":
            r, choice = trailing_sharpe_selector(R, E, refits, margin=params["margin"], switch_cost=cost.per_side)
        else:
            reg = btc_regimes(self.dfs["BTC-USD"])
            r, choice = regime_selector(R, E, reg, refits, min_hold=params["min_hold"], switch_cost=cost.per_side)
        held = choice.shift(1).reindex(R.index)
        e = pd.Series(0.0, index=R.index)
        for n in E.columns:
            e[held == n] = E.loc[held == n, n]
        return r.loc["2020-01-01":], e.loc["2020-01-01":], choice

    def gated(self, params, cost=REAL):
        """Baseline weight kept only on days whose state is approved by the walk-forward gate."""
        out_t, logs = {}, []
        for a, d in self.dfs.items():
            vote, vol = trend.trend_vote(d), trend.realized_vol(d)
            appr, log = walk_forward_gate(d, vote, vol, params["horizon"], 2 * cost.per_side,
                                          list(range(2020, 2027)), z=params["z"])
            out_t[a] = (trend.BASELINE(d) * appr.fillna(0.0)).reindex(self.close.index)
            log["asset"] = a
            logs.append(log)
        res = sleeves(self.close, self.fill, pd.DataFrame(out_t).fillna(0.0), 1000, cost)
        return res, pd.concat(logs, ignore_index=True)


def evaluate(lab: Lab, family: str, params: dict, cost=None, ex=ExecModel()):
    """-> (returns, exposure, trades) over the full available span for this family."""
    if family in FACTORY:
        res = lab.single(family, params, cost or REAL, ex)
        return rets(res), expo(res), res.trades
    if family == "rotation":
        res = lab.rotation(params, cost or ALT, ex)
        return rets(res), expo(res), res.trades
    if family.startswith("selector"):
        r, e, _ = lab.selector(family, params, cost or REAL)
        return r, e, None
    if family == "gate":
        res, _ = lab.gated(params, cost or REAL)
        return rets(res), expo(res), res.trades
    if family.endswith("_wf"):
        return wf_family(lab, family[:-3], cost)
    raise KeyError(family)


def wf_family(lab, base_family, cost=None):
    """Walk-forward parameter selection: each year use the config with the best Sharpe on all prior data."""
    grid = GRIDS[base_family]
    runs, wts, trades = {}, {}, {}
    for i, p in enumerate(grid):
        r, e, t = evaluate(lab, base_family, p, cost)
        runs[i], wts[i], trades[i] = r, e, t
    wf = walk_forward(runs, wts, yearly_splits(2020, 2026, last_end=TEST[1]),
                      switch_cost=(cost or (ALT if base_family == "rotation" else REAL)).per_side)
    e = pd.concat([wts[k].loc[s: (f"{s[:4]}-12-31")] for s, k, _ in wf.chosen])
    tr = pd.concat([trades[k][(trades[k].time >= pd.Timestamp(s, tz="UTC")) &
                              (trades[k].time <= pd.Timestamp(f"{s[:4]}-12-31", tz="UTC"))] for s, k, _ in wf.chosen])
    return wf.returns, e, tr


def compare(lab, r, e, start, end, cost=REAL, n_boot=1000):
    """Strategy vs baseline, buy&hold and fixed allocation at the same average exposure (pair sleeves)."""
    s = period_stats(r, e, None, start, end)
    b = lab.baseline(cost)
    h = lab._named("buy_hold", trend.BUY_HOLD, cost)
    m = lab.fixed_matched(s.get("exposure", 0.33), cost)
    out = {"strategy": s, "baseline": period_stats(rets(b), expo(b), None, start, end),
           "buy_hold": period_stats(rets(h), None, None, start, end),
           "fixed_matched": period_stats(rets(m), expo(m), None, start, end)}
    R = {"s": r.loc[start:end], "m": rets(m).loc[start:end]}
    sr = lambda a, k: a[:, k].mean() / a[:, k].std() * math.sqrt(365) if a[:, k].std() > 0 else 0.0
    cg = lambda a, k: float(np.prod(1 + a[:, k]) ** (365 / len(a)) - 1)
    bt = bootstrap(R, {"dSharpe_vs_fixed": lambda a, c, bb: sr(a, 0) - sr(a, 1),
                       "dCAGR_vs_fixed": lambda a, c, bb: cg(a, 0) - cg(a, 1)}, n_boot=n_boot)
    out["bootstrap"] = bt.round(4).to_dict()
    return out


def passes(c: dict) -> bool:
    s, m = c["strategy"], c["fixed_matched"]
    return bool(s["sharpe"] > m["sharpe"] and s["CAGR"] > m["CAGR"] and s["maxDD"] >= m["maxDD"] - 0.10 and s["CAGR"] > 0)


# ---------------------------------------------------------------- phases
def phase_dev():
    lab = Lab()
    chosen, table = {}, []
    for family, grid in GRIDS.items():
        scored = []
        for p in grid:
            r, e, t = evaluate(lab, family, p)
            start = DEV[0] if not (family.startswith("selector") or family == "gate") else "2020-01-01"
            st = period_stats(r, e, t, start, DEV[1])
            record("result", f"trial:{family}", p, f"{start}..{DEV[1]}", "dev search", metrics=st)
            scored.append((st["sharpe"], p, st))
            table.append({"family": family, "params": json.dumps(p), **{k: round(v, 3) for k, v in st.items()}})
        best = max(scored, key=lambda x: x[0])
        chosen[family] = best[1]
    for fam in ("breakout", "meanrev", "rotation"):     # walk-forward selection procedures (one trial each)
        r, e, t = evaluate(lab, fam + "_wf", {})
        st = period_stats(r, e, t, "2020-01-01", DEV[1])
        record("result", f"trial:{fam}_wf", {"grid": GRIDS[fam]}, f"2020-01-01..{DEV[1]}", "dev search", metrics=st)
        chosen[fam + "_wf"] = {}
        table.append({"family": fam + "_wf", "params": "walk-forward over grid", **{k: round(v, 3) for k, v in st.items()}})
    cal = load_calendar()
    chosen["_calendar_status"] = "available" if cal is not None else "pending: data/events/macro_calendar.csv not present"
    (OUT / "dev_selection.json").write_text(json.dumps(chosen, indent=1))
    pd.DataFrame(table).to_csv(OUT / "dev_trials.csv", index=False)
    print(pd.DataFrame(table).to_string(index=False))
    print(json.dumps(chosen, indent=1))


def phase_dev_finish():
    """Completes an interrupted dev run WITHOUT re-logging trials already in the registry: runs only
    families that have no logged trials yet (the calendar overlay, whose data arrived mid-run), then
    rebuilds the selection (best dev Sharpe per family) from the registry."""
    lab = Lab()
    logged = {}
    for x in entries("result"):
        if x["name"].startswith("trial:") and x["purpose"] == "dev search":
            logged.setdefault(x["name"].split(":", 1)[1], []).append(x)
    for family in [f for f in GRIDS if f not in logged]:
        for p in GRIDS[family]:
            r, e, t = evaluate(lab, family, p)
            st = period_stats(r, e, t, DEV[0], DEV[1])
            logged.setdefault(family, []).append(
                record("result", f"trial:{family}", p, f"{DEV[0]}..{DEV[1]}", "dev search", metrics=st))
    chosen, table = {}, []
    for family, xs in logged.items():
        for x in xs:
            table.append({"family": family, "params": json.dumps(x["params"]), **{k: round(v, 3) for k, v in x["metrics"].items()}})
        best = max(xs, key=lambda x: x["metrics"]["sharpe"])
        chosen[family] = best["params"] if not family.endswith("_wf") else {}
    (OUT / "dev_selection.json").write_text(json.dumps(chosen, indent=1))
    pd.DataFrame(table).to_csv(OUT / "dev_trials.csv", index=False)
    pd.set_option("display.width", 250)
    print(pd.DataFrame(table).to_string(index=False))
    print(json.dumps(chosen, indent=1))
    print("trials logged:", sum(len(v) for v in logged.values()))


def phase_validate():
    lab = Lab()
    chosen = json.loads((OUT / "dev_selection.json").read_text())
    rows, full = {}, {}
    for family, p in chosen.items():
        if family.startswith("_"):
            continue
        r, e, _ = evaluate(lab, family, p)
        c = compare(lab, r, e, *VAL)
        full[family] = c
        rows[family] = {"params": json.dumps(p), "CAGR": c["strategy"]["CAGR"], "sharpe": c["strategy"]["sharpe"],
                        "maxDD": c["strategy"]["maxDD"], "exposure": c["strategy"].get("exposure"),
                        "fixed_CAGR": c["fixed_matched"]["CAGR"], "fixed_sharpe": c["fixed_matched"]["sharpe"],
                        "fixed_maxDD": c["fixed_matched"]["maxDD"], "base_CAGR": c["baseline"]["CAGR"],
                        "base_sharpe": c["baseline"]["sharpe"], "bh_CAGR": c["buy_hold"]["CAGR"],
                        "P(dSharpe>0)": c["bootstrap"]["P(>0)"]["dSharpe_vs_fixed"], "PASS_val": passes(c)}
        record("result", f"validation:{family}", p, f"{VAL[0]}..{VAL[1]}", "validation", metrics=rows[family])
    (OUT / "validation.json").write_text(json.dumps(full, indent=1, default=float))
    df = pd.DataFrame(rows).T
    df.to_csv(OUT / "validation.csv")
    print(df.to_string())


def phase_preregister():
    if any(x["name"].startswith("prereg3:") for x in entries("preregistration")):
        sys.exit("already preregistered")
    chosen = json.loads((OUT / "dev_selection.json").read_text())
    val = pd.read_csv(OUT / "validation.csv", index_col=0)
    for family, p in chosen.items():
        if family.startswith("_"):
            continue
        record("preregistration", f"prereg3:{family}", p, f"{TEST[0]}..{TEST[1]}", "untouched test",
               note=("Frozen config from dev search (2018-2021). Cost: Coinbase taker 0.66%/side (alts 0.80%). "
                     "PASS iff on the test period: Sharpe > fixed allocation at the same average exposure, AND CAGR > "
                     "that benchmark, AND max drawdown no more than 10 points worse, AND CAGR > 0. PROMOTE to paper "
                     "trading only if it also passed validation (2022-2023: "
                     f"{'PASS' if bool(val.loc[family, 'PASS_val']) else 'FAIL'}). Single-asset families also run on "
                     "holdout coins LTC/BCH/ETC (2018-2026): PASS iff Sharpe and CAGR beat the exposure-matched "
                     "fixed allocation on at least 2 of 3. Run once; no tuning afterwards."))
    print("preregistered", [k for k in chosen if not k.startswith("_")])


def phase_test():
    if any(x["name"].startswith("test3:") for x in entries("result")):
        sys.exit("test already run once; refusing to run again")
    pre = {x["name"].split(":", 1)[1]: x["params"] for x in entries("preregistration") if x["name"].startswith("prereg3:")}
    if not pre:
        sys.exit("preregister first")
    val = pd.read_csv(OUT / "validation.csv", index_col=0)
    lab = Lab()
    rows, full, stress, hold = {}, {}, {}, {}
    test_returns = {}
    hdfs = {a: load(a, "1h") for a in PAIR}
    for family, p in pre.items():
        r, e, t = evaluate(lab, family, p)
        c = compare(lab, r, e, *TEST, n_boot=2000)
        full[family] = c
        test_returns[family] = r.loc[TEST[0]:TEST[1]]
        st = period_stats(r, e, t, *TEST)
        rows[family] = {"params": json.dumps(p), "CAGR": st["CAGR"], "sharpe": st["sharpe"], "maxDD": st["maxDD"],
                        "exposure": st.get("exposure"), "orders_per_yr": st.get("orders_per_yr"),
                        "fixed_CAGR": c["fixed_matched"]["CAGR"], "fixed_sharpe": c["fixed_matched"]["sharpe"],
                        "fixed_maxDD": c["fixed_matched"]["maxDD"], "base_CAGR": c["baseline"]["CAGR"],
                        "base_sharpe": c["baseline"]["sharpe"], "base_maxDD": c["baseline"]["maxDD"],
                        "bh_CAGR": c["buy_hold"]["CAGR"], "bh_sharpe": c["buy_hold"]["sharpe"], "bh_maxDD": c["buy_hold"]["maxDD"],
                        "dSharpe_p05": c["bootstrap"]["p05"]["dSharpe_vs_fixed"], "dSharpe_p95": c["bootstrap"]["p95"]["dSharpe_vs_fixed"],
                        "P(dSharpe>0)": c["bootstrap"]["P(>0)"]["dSharpe_vs_fixed"],
                        "PASS_test": passes(c), "PASS_val": bool(val.loc[family, "PASS_val"])}
        # stress: costs, delay (+12h via hourly opens; pair families only), missed fills
        s = {}
        if family in FACTORY or family == "rotation":
            sc = STRESS
            r2, e2, _ = evaluate(lab, family, p, cost=sc)
            s["cost_1.25%"] = period_stats(r2, e2, None, *TEST)["CAGR"]
            r3, e3, _ = evaluate(lab, family, p, ex=ExecModel(miss_prob=0.2, seed=3))
            s["miss_20%"] = period_stats(r3, e3, None, *TEST)["CAGR"]
            if family in FACTORY:
                fd = pd.DataFrame({a: hdfs[a].open.reindex(lab.close.index + pd.Timedelta(hours=12)).to_numpy() for a in PAIR},
                                  index=lab.close.index).fillna(lab.fill)
                spec = FACTORY[family](**p)
                res = run_pair(spec, lab.dfs, lab.close, fd, REAL)
                s["delay_12h"] = period_stats(rets(res), expo(res), None, *TEST)["CAGR"]
        stress[family] = s
        # holdout coins
        if family in FACTORY:
            spec = FACTORY[family](**p)
            hres = {}
            for a in HOLDOUT:
                d = load(a, "1d"); st0 = max(d.index[200], pd.Timestamp("2018-01-01", tz="UTC"))
                c1, f1 = d[["close"]].rename(columns={"close": a}).loc[st0:], d[["open"]].rename(columns={"open": a}).loc[st0:]
                full_idx = pd.date_range(c1.index[0], c1.index[-1], freq="D")
                c1 = c1.reindex(full_idx).ffill(); f1 = f1.reindex(full_idx).fillna(c1)
                sr_ = simulate(c1, f1, pd.DataFrame({a: spec(d)}).reindex(full_idx).fillna(0.0), 1000, REAL)
                ss = period_stats(rets(sr_), expo(sr_), None, c1.index[0], c1.index[-1])
                mr = simulate(c1, f1, pd.DataFrame({a: round(ss["exposure"], 2)}, index=full_idx), 1000, REAL)
                ms = period_stats(rets(mr), None, None, c1.index[0], c1.index[-1])
                hres[a] = {"CAGR": ss["CAGR"], "sharpe": ss["sharpe"], "maxDD": ss["maxDD"], "fixed_CAGR": ms["CAGR"],
                           "fixed_sharpe": ms["sharpe"], "fixed_maxDD": ms["maxDD"],
                           "win": bool(ss["sharpe"] > ms["sharpe"] and ss["CAGR"] > ms["CAGR"])}
            hold[family] = {"assets": hres, "PASS": sum(v["win"] for v in hres.values()) >= 2}
        record("result", f"test3:{family}", p, f"{TEST[0]}..{TEST[1]}", "untouched test (single run)",
               metrics={**rows[family], "stress": stress.get(family), "holdout": hold.get(family)})
    # save the single-run results before any post-processing
    (OUT / "test_partial.json").write_text(json.dumps({"rows": rows, "stress": stress, "holdout": hold, "compare": full},
                                                      indent=1, default=float))
    pd.DataFrame(test_returns).to_csv(OUT / "test_returns_partial.csv")
    # deflated Sharpe across every logged trial
    trials = [x for x in entries("result") if x["name"].startswith("trial:")]
    n_trials = len(trials) + 22
    var_sr = float(np.var([x["metrics"]["sr_daily"] for x in trials]))
    for family, r in test_returns.items():
        rows[family]["DSR"] = deflated_sharpe(r.dropna(), n_trials, var_sr)
    # gate calibration on validation + test years
    _, glog = lab.gated(pre.get("gate", GRIDS["gate"][1]))
    glog = glog[glog.time >= pd.Timestamp("2022-01-01", tz="UTC")]
    rel = reliability(glog)
    out = {"rows": rows, "compare": full, "stress": stress, "holdout": hold, "n_trials": n_trials, "trial_sr_var": var_sr,
           "gate_reliability": rel.reset_index().astype({"bin": str}).to_dict(orient="records")}
    (OUT / "test.json").write_text(json.dumps(out, indent=1, default=float))
    bench = {"baseline": rets(lab.baseline()), "buy_hold": rets(lab._named("buy_hold", trend.BUY_HOLD)),
             "fixed_33": rets(lab._named("fixed_0.33", fixed(0.33)))}
    pd.DataFrame({**test_returns, **{k: v.loc[TEST[0]:TEST[1]] for k, v in bench.items()}}).to_csv(OUT / "test_returns.csv")
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).T.to_string())
    print("\nstress (test-period CAGR):\n", pd.DataFrame(stress).T.to_string())
    print("\nholdout:", json.dumps({k: v["PASS"] for k, v in hold.items()}))
    print("\ntrials:", n_trials, "var:", var_sr)
    print("\ngate reliability (2022+):\n", rel.to_string())


if __name__ == "__main__":
    {"dev": phase_dev, "dev_finish": phase_dev_finish, "validate": phase_validate, "preregister": phase_preregister, "test": phase_test}[sys.argv[1]]()
