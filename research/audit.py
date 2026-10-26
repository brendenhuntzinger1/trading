"""Phase-2 audit of the phase-1 baseline. Run: .venv/bin/python research/audit.py"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradelab.data.candles import load
from tradelab.research.engine import CostModel, ExecModel, simulate, sleeves
from tradelab.research.metrics import summary, bootstrap, deflated_sharpe, psr, sharpe
from tradelab.research.registry import record
from tradelab.strategies import trend

pd.set_option("display.width", 220)
OUT = ROOT / "research" / "out"
START = "2018-01-01"
COSTS = {
    "phase1_assumed_0.45%": CostModel(fee=0.0040, half_spread=0.0, slippage=0.0005),
    "coinbase_taker_0.66%": CostModel(fee=0.0060, half_spread=0.0001, slippage=0.0005),
    "kraken_taker_0.86%": CostModel(fee=0.0080, half_spread=0.0001, slippage=0.0005),
    "stress_1.25%": CostModel(fee=0.0100, half_spread=0.0005, slippage=0.0020),
}
REAL = COSTS["coinbase_taker_0.66%"]


def frames(assets, start=START, tf="1d"):
    dfs = {a: load(a, tf) for a in assets}
    close = pd.DataFrame({a: d.close for a, d in dfs.items()})
    fill = pd.DataFrame({a: d.open for a, d in dfs.items()})
    return dfs, close.loc[start:], fill.loc[start:]


def targets(spec, dfs, index):
    # signals computed on full history (causal; tested), then cut to the sample
    return pd.DataFrame({a: spec(d) for a, d in dfs.items()}).reindex(index)


def fmt(d):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def main():
    report = {}
    pair = ["BTC-USD", "ETH-USD"]
    dfs, close, fill = frames(pair)

    # 1. Reproduce the reported figure with the frozen phase-1 code
    spec = importlib.util.spec_from_file_location("legacy_portfolio", ROOT / "legacy" / "portfolio.py")
    sys.path.insert(0, str(ROOT / "legacy"))
    lp = importlib.util.module_from_spec(spec); spec.loader.exec_module(lp)
    import strategies as lstrat  # legacy module
    legacy = lp.portfolio(lstrat.ensemble(0.40), 0.0045, START)
    report["1_legacy_reproduction"] = legacy
    print("1. phase-1 code, phase-1 costs:", legacy)

    # 2. Independent engine, same assumptions, then corrected accounting
    tgt = targets(trend.BASELINE, dfs, close.index)
    rows = {}
    for label, ex in [("independent engine, band=0 (closest to phase-1)", ExecModel(band=0.0)),
                      ("independent engine, band=0.02", ExecModel())]:
        r = sleeves(close, fill, tgt, 1000, COSTS["phase1_assumed_0.45%"], ex)
        rows[label] = fmt(summary(r))
    report["2_independent_reproduction"] = rows
    print("\n2. independent engine at phase-1 costs:\n", pd.DataFrame(rows).T[["final", "CAGR", "arith_mean_annual", "mean_calendar_year", "sharpe", "maxDD", "orders_per_yr"]])

    # 3. Cost reality
    rows = {}
    for label, c in COSTS.items():
        rows[label] = fmt(summary(sleeves(close, fill, tgt, 1000, c)))
    for miss in (0.2, 0.5):   # maker-only limit orders: cheaper but some never fill
        rows[f"maker_0.40%_miss{int(miss*100)}%"] = fmt(summary(sleeves(close, fill, tgt, 1000,
            CostModel(fee=0.004, half_spread=0, slippage=0), ExecModel(miss_prob=miss))))
    report["3_costs"] = rows
    print("\n3. baseline under realistic costs:\n", pd.DataFrame(rows).T[["final", "CAGR", "sharpe", "maxDD", "exposure", "turnover_x_per_yr", "cost_drag_per_yr"]])

    # 4. Benchmarks at comparable risk (all at Coinbase taker cost)
    base = sleeves(close, fill, tgt, 1000, REAL)
    bh = sleeves(close, fill, targets(trend.BUY_HOLD, dfs, close.index), 1000, REAL)
    expo = summary(base)["exposure"]
    volratio = summary(base)["vol"] / summary(bh)["vol"]
    bench = {
        "baseline ensemble_vol40": base,
        "buy & hold 100%": bh,
        f"buy & hold at same avg exposure ({expo:.0%})": sleeves(close, fill, pd.DataFrame(expo, index=close.index, columns=pair), 1000, REAL),
        f"buy & hold at same volatility ({volratio:.0%})": sleeves(close, fill, pd.DataFrame(volratio, index=close.index, columns=pair), 1000, REAL),
        "above SMA200 (simple trend)": sleeves(close, fill, targets(trend.SMA200, dfs, close.index), 1000, REAL),
        "ablation: vol sizing only": sleeves(close, fill, targets(trend.VOL_ONLY, dfs, close.index), 1000, REAL),
        "ablation: trend vote only": sleeves(close, fill, targets(trend.TREND_ONLY, dfs, close.index), 1000, REAL),
    }
    rows = {k: fmt(summary(v)) for k, v in bench.items()}
    report["4_benchmarks"] = rows
    print("\n4. comparable-risk benchmarks (Coinbase taker):\n", pd.DataFrame(rows).T[["final", "CAGR", "vol", "sharpe", "maxDD", "exposure", "orders_per_yr"]])

    # 5. Uncertainty: paired stationary block bootstrap (mean block 20 days)
    names = list(bench)
    rets = {k: bench[k].returns for k in names}
    def cagr(a, cols, bpy, k): return float(np.prod(1 + a[:, k]) ** (bpy / len(a)) - 1)
    def sr(a, cols, bpy, k): return float(a[:, k].mean() / a[:, k].std() * math.sqrt(bpy))
    i_b, i_h, i_e = 0, 1, 2
    stats = {
        "baseline CAGR": lambda a, c, b: cagr(a, c, b, i_b),
        "buy&hold CAGR": lambda a, c, b: cagr(a, c, b, i_h),
        "baseline Sharpe": lambda a, c, b: sr(a, c, b, i_b),
        "buy&hold Sharpe": lambda a, c, b: sr(a, c, b, i_h),
        "Sharpe: baseline - buy&hold": lambda a, c, b: sr(a, c, b, i_b) - sr(a, c, b, i_h),
        "Sharpe: baseline - exposure-matched B&H": lambda a, c, b: sr(a, c, b, i_b) - sr(a, c, b, i_e),
        "CAGR: baseline - exposure-matched B&H": lambda a, c, b: cagr(a, c, b, i_b) - cagr(a, c, b, i_e),
    }
    boot = bootstrap(rets, stats, n_boot=2000)
    report["5_bootstrap_90pct"] = boot.round(3).to_dict()
    print("\n5. bootstrap 90% intervals:\n", boot.round(3))

    # 6. Multiple testing: deflated Sharpe over the strategy configurations tried in phase 1
    import strategies as L
    trial_srs = []
    for s in L.DAILY + [L.ensemble(0.40), L.ensemble(0.30)]:
        t = pd.DataFrame({a: s(d) for a, d in dfs.items()}).reindex(close.index).clip(0, 1)
        r = sleeves(close, fill, t, 1000, REAL).returns
        trial_srs.append(r.mean() / r.std())
    n_trials = len(trial_srs) + 7  # + hourly configs also tried
    dsr = deflated_sharpe(base.returns, n_trials, float(np.var(trial_srs)))
    report["6_multiple_testing"] = {"n_trials": n_trials, "PSR_vs_0": psr(base.returns), "DSR": dsr,
                                    "annual_sharpe_of_trials": sorted(round(x * math.sqrt(365), 2) for x in trial_srs)}
    print("\n6. multiple testing:", fmt(report["6_multiple_testing"]))

    # 7. Execution timing: fill N hours after the daily close instead of at the open
    hdfs = {a: load(a, "1h") for a in pair}
    rows = {}
    c2, f2 = close.loc["2020-02-01":], fill.loc["2020-02-01":]
    t2 = tgt.loc[c2.index]
    for delay in (0, 1, 4, 12):
        fd = pd.DataFrame({a: hdfs[a].open.reindex(c2.index + pd.Timedelta(hours=delay)).to_numpy() for a in pair}, index=c2.index)
        fd = fd.fillna(f2)  # outage hour: fall back to daily open, flagged by count below
        rows[f"fill +{delay}h after close"] = fmt(summary(sleeves(c2, fd, t2, 1000, REAL)))
    report["7_execution_delay_2020+"] = rows
    print("\n7. execution delay (2020-02 onward):\n", pd.DataFrame(rows).T[["final", "CAGR", "sharpe", "maxDD"]])

    # 8. Calendar years
    yr = pd.DataFrame({k: (1 + bench[k].returns).groupby(bench[k].returns.index.year).prod() - 1
                       for k in ["baseline ensemble_vol40", "buy & hold 100%", names[2]]})
    report["8_calendar_years"] = yr.round(3).to_dict()
    print("\n8. calendar-year returns:\n", (yr * 100).round(1))

    # 9. Stress windows
    windows = {"COVID crash": ("2020-02-15", "2020-03-31"), "May-Jul 2021 crash": ("2021-05-01", "2021-07-20"),
               "LUNA/3AC": ("2022-05-01", "2022-06-30"), "FTX": ("2022-11-01", "2022-12-31"),
               "post-FTX rebound (reversal)": ("2023-01-01", "2023-03-31"), "sideways 2019H2": ("2019-07-01", "2019-12-31"),
               "Aug 2024 unwind": ("2024-07-28", "2024-08-10"), "quiet 2023 Q3": ("2023-07-01", "2023-09-30")}
    rows = {}
    for w, (s, e) in windows.items():
        rows[w] = {k: round(float((1 + bench[k].returns.loc[s:e]).prod() - 1), 3)
                   for k in ["baseline ensemble_vol40", "buy & hold 100%", names[2]]}
    report["9_stress_windows"] = rows
    print("\n9. stress windows (period return):\n", (pd.DataFrame(rows).T * 100).round(1))

    # 10. Pre-registered holdouts
    rows = {}
    for a in ["LTC-USD", "BCH-USD", "ETC-USD"]:
        d = load(a, "1d"); start = d.index[200]
        c, f = d[["close"]].rename(columns={"close": a}).loc[start:], d[["open"]].rename(columns={"open": a}).loc[start:]
        b = simulate(c, f, pd.DataFrame({a: trend.BASELINE(d)}).loc[start:], 1000, REAL)
        h = simulate(c, f, pd.DataFrame({a: 1.0}, index=c.index), 1000, REAL)
        sb, sh = summary(b), summary(h)
        rows[a] = {"from": str(start.date()), "base_CAGR": sb["CAGR"], "bh_CAGR": sh["CAGR"], "base_sharpe": sb["sharpe"],
                   "bh_sharpe": sh["sharpe"], "base_maxDD": sb["maxDD"], "bh_maxDD": sh["maxDD"],
                   "PASS": bool(sb["sharpe"] > sh["sharpe"] and sb["maxDD"] > sh["maxDD"])}
    uni = ["BTC-USD", "ETH-USD", "LTC-USD", "BCH-USD"]
    udfs, uc, uf = frames(uni)
    ub = sleeves(uc, uf, targets(trend.BASELINE, udfs, uc.index), 1000, REAL)
    uh = sleeves(uc, uf, targets(trend.BUY_HOLD, udfs, uc.index), 1000, REAL)
    sb, sh = summary(ub), summary(uh)
    rows["universe BTC+ETH+LTC+BCH"] = {"from": START, "base_CAGR": sb["CAGR"], "bh_CAGR": sh["CAGR"], "base_sharpe": sb["sharpe"],
                                        "bh_sharpe": sh["sharpe"], "base_maxDD": sb["maxDD"], "bh_maxDD": sh["maxDD"],
                                        "PASS": bool(sb["sharpe"] > sh["sharpe"] and sb["maxDD"] > sh["maxDD"])}
    report["10_holdouts"] = rows
    print("\n10. pre-registered holdouts (Coinbase taker):\n", pd.DataFrame(rows).T)
    for name in ["holdout_single_assets", "holdout_point_in_time_universe"]:
        keep = {k: v for k, v in rows.items() if (k.startswith("universe") == name.endswith("universe"))}
        record("result", name, {"strategy": "ensemble_vol40"}, "see preregistration", "holdout", metrics=keep)

    record("result", "audit_baseline", {"strategy": "ensemble_vol40", "pair": pair}, f"{START}..2026-10-24",
           "audit (in-sample)", metrics={k: report["3_costs"][k] for k in report["3_costs"]})
    (OUT / "audit.json").write_text(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
