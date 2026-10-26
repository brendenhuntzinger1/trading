"""Stock intraday study: S1, S2, S3 per INTRADAY_HYPOTHESES.md (+ Amendment 1).

    .venv/bin/python research/intraday/stocks/study.py dev
    .venv/bin/python research/intraday/stocks/study.py val
    .venv/bin/python research/intraday/stocks/study.py freeze
    .venv/bin/python research/intraday/stocks/study.py test       # refuses to run twice
    .venv/bin/python research/intraday/stocks/study.py explore    # S3, 60 days, exploratory
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tradelab.intraday.research import stocks_s1 as S1, stocks_s2 as S2, stocks_s3 as S3  # noqa: E402
from tradelab.intraday.research.stocks_common import SPLITS, daily_panel, symbols  # noqa: E402
from tradelab.intraday.research.stocks_eval import daily_pnl, evaluate, sharpe  # noqa: E402
from tradelab.research.registry import entries, record  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)
PRIOR_TRIALS, CRYPTO_TRIALS_ASSUMED = 73, 12
STOCKS = symbols("stock")
INDEX = [s for s in symbols("index_etf")]
SECTOR = [s for s in symbols("sector_etf")]
S2_UNIVERSE = STOCKS + SECTOR
S2_ETF_ONLY = SECTOR + [s for s in INDEX if s != "SPY"]
S1_UNIVERSE = STOCKS + INDEX

# Dev configurations (<= 6 per hypothesis). The doc's default is listed first and is what the test runs.
S1_CONFIGS = {
    "S1_default_thr0.25_top5_all": dict(threshold=0.0025, top=5, universe=S1_UNIVERSE),
    "S1_thr0.50_top5_all": dict(threshold=0.005, top=5, universe=S1_UNIVERSE),
    "S1_thr0.25_index_etfs": dict(threshold=0.0025, top=4, universe=INDEX),
    "S1_thr0.25_spy_only": dict(threshold=0.0025, top=1, universe=["SPY"]),
    "S1_longshort_thr0.25_top5_all": dict(threshold=0.0025, top=5, universe=S1_UNIVERSE, long_short=True),
}
S2_CONFIGS = {
    "S2_default_thr1_top5_stocks+sector": dict(threshold=0.01, top=5, universe=S2_UNIVERSE),
    "S2_thr2_top5_stocks+sector": dict(threshold=0.02, top=5, universe=S2_UNIVERSE),
    "S2_thr1_top3_stocks+sector": dict(threshold=0.01, top=3, universe=S2_UNIVERSE),
    "S2_etf_only_thr1_top5": dict(threshold=0.01, top=5, universe=S2_ETF_ONLY),
}


def panels():
    px = daily_panel(sorted(set(S2_UNIVERSE + INDEX)))
    hp = S1.hourly_panel(sorted(set(S1_UNIVERSE)), px["close"], px["open"])
    print("S1 hourly sessions blanked (hourly/daily open mismatch > 2%):", hp["blanked_sessions"])
    return px, hp


def daily_sessions(px, start, end):
    return px["close"]["SPY"].dropna().loc[start:end].index


def hourly_splits(hp):
    s = hp["p1030"].index
    n = len(s)
    a, b = int(n * 0.4), int(n * 0.6)
    return {"dev": s[:a], "val": s[a:b], "test": s[b:]}


def summarize(t, sessions):
    p = daily_pnl(t, sessions)
    return {"n_trades": len(t), "mean_net": float(t.net_ret.mean()) if len(t) else None,
            "mean_gross": float(t.gross_ret.mean()) if len(t) else None,
            "win_rate": float((t.net_ret > 0).mean()) if len(t) else None,
            "daily_sharpe_ann": sharpe(p), "daily_sr_per_period": float(p.mean() / p.std()) if p.std() > 0 else 0.0,
            "sum_daily_pnl": float(p.sum()), "first": str(sessions[0].date()), "last": str(sessions[-1].date())}


def s1_run(hp, name, sessions, cost="base"):
    cfg = dict(S1_CONFIGS[name])
    return S1.trades(hp, sessions, cost=cost, **cfg)


def s2_run(px, name, start, end, cost="base"):
    cfg = dict(S2_CONFIGS[name])
    return S2.trades(px, start, end, cost=cost, **cfg)


def phase_dev():
    px, hp = panels()
    print("bad daily rows blanked:", px["bad_rows"])
    hs = hourly_splits(hp)
    res = {}
    for name in S1_CONFIGS:
        t = s1_run(hp, name, hs["dev"])
        res[name] = summarize(t, hs["dev"])
        record("result", f"intraday_stocks_trial:{name}", S1_CONFIGS[name] | {"universe": len(S1_CONFIGS[name]["universe"])},
               f"{hs['dev'][0].date()}..{hs['dev'][-1].date()}", "intraday stocks dev trial", metrics=res[name])
    ds = daily_sessions(px, *SPLITS["dev"])
    for name in S2_CONFIGS:
        t = s2_run(px, name, *SPLITS["dev"])
        res[name] = summarize(t, ds)
        record("result", f"intraday_stocks_trial:{name}", S2_CONFIGS[name] | {"universe": len(S2_CONFIGS[name]["universe"]),
               "costs": "Amendment 1: entry 5bp marketable after open, exit MOC 3bp"},
               f"{SPLITS['dev'][0]}..{SPLITS['dev'][1]}", "intraday stocks dev trial", metrics=res[name])
    (OUT / "dev.json").write_text(json.dumps(res, indent=1, default=str))
    print(pd.DataFrame(res).T[["n_trades", "mean_gross", "mean_net", "win_rate", "daily_sharpe_ann", "first", "last"]].to_string())


def phase_val():
    px, hp = panels()
    hs = hourly_splits(hp)
    res = {}
    for name in ["S1_default_thr0.25_top5_all", "S1_longshort_thr0.25_top5_all"]:
        res[name] = summarize(s1_run(hp, name, hs["val"]), hs["val"])
    vs = daily_sessions(px, *SPLITS["val"])
    for name in ["S2_default_thr1_top5_stocks+sector", "S2_etf_only_thr1_top5"]:
        res[name] = summarize(s2_run(px, name, *SPLITS["val"]), vs)
    for k, v in res.items():
        record("result", f"intraday_stocks_validation:{k}", {}, f"{v['first']}..{v['last']}", "intraday stocks validation (confirm only)", metrics=v)
    (OUT / "validation.json").write_text(json.dumps(res, indent=1, default=str))
    print(pd.DataFrame(res).T[["n_trades", "mean_gross", "mean_net", "win_rate", "daily_sharpe_ann", "first", "last"]].to_string())


TEST_CONFIGS = ["S1_default_thr0.25_top5_all", "S1_longshort_thr0.25_top5_all",
                "S2_default_thr1_top5_stocks+sector", "S2_etf_only_thr1_top5"]


def phase_freeze():
    for name in TEST_CONFIGS:
        cfg = (S1_CONFIGS | S2_CONFIGS)[name]
        record("frozen_config", f"intraday_stocks_frozen:{name}",
               {k: (v if k != "universe" else sorted(v)) for k, v in cfg.items()}, "test",
               "frozen before the single test run",
               note="Doc default (primary) or required/labelled variant; no parameter chosen from dev results.")
    print("frozen:", TEST_CONFIGS)


def trial_stats():
    trials = [e for e in entries("result") if e["name"].startswith("intraday_stocks_trial:")]
    srs = [e["metrics"]["daily_sr_per_period"] for e in trials if e["metrics"] and e["metrics"].get("daily_sr_per_period") is not None]
    n_mine = len({e["name"] for e in trials})
    return n_mine, float(np.var(srs)) if len(srs) > 1 else 0.0


def save_trades(t, name):
    cols = ["session", "symbol", "side", "signal", "entry_time_utc", "entry_px", "exit_time_utc", "exit_px",
            "gross_ret", "cost", "net_ret", "size_weight"]
    t[[c for c in cols if c in t.columns]].to_csv(OUT / f"test_trades_{name}.csv", index=False)


def phase_test():
    if any(e["name"].startswith("intraday_stocks_test:") for e in entries("result")):
        sys.exit("test already run once; refusing to run again")
    if not all(any(e["name"] == f"intraday_stocks_frozen:{n}" for e in entries("frozen_config")) for n in TEST_CONFIGS):
        sys.exit("freeze first")
    # S2 stop variant is an extra (labelled) trial: count it before computing E6
    record("result", "intraday_stocks_trial:S2_stopvariant_hourly_window", {"stop": -0.03, "window": "hourly data only"},
           "test window, hourly-data part", "labelled secondary variant (counts as a trial)", metrics=None)
    record("result", "intraday_stocks_trial:S3_exploratory_orb", {"window": "60 days 5m"}, "last 60 days", "exploratory", metrics=None)
    n_mine, var = trial_stats()
    n_trials = PRIOR_TRIALS + n_mine + CRYPTO_TRIALS_ASSUMED
    px, hp = panels()
    hs = hourly_splits(hp)
    results = {}
    # S1
    for name in TEST_CONFIGS[:2]:
        sess = hs["test"]
        t = s1_run(hp, name, sess)
        ts = s1_run(hp, name, sess, cost="stress")
        cfg = S1_CONFIGS[name]
        plac = S1.placebo_totals(hp, t, sess, reps=1000, universe=cfg["universe"])
        results[name] = evaluate(t, ts, sess, plac, n_trials, var) | {"first": str(sess[0].date()), "last": str(sess[-1].date())}
        save_trades(t, name)
    # S2
    sess = daily_sessions(px, *SPLITS["test"])
    for name in TEST_CONFIGS[2:]:
        t = s2_run(px, name, *SPLITS["test"])
        ts = s2_run(px, name, *SPLITS["test"], cost="stress")
        tw = s2_run(px, name, *SPLITS["test"], cost="wide_open")
        plac = S2.placebo_totals(px, t, reps=1000, universe=S2_CONFIGS[name]["universe"])
        r = evaluate(t, ts, sess, plac, n_trials, var)
        r["sensitivity_entry10bp_mean_net"] = float(tw.net_ret.mean()) if len(tw) else None
        r["sensitivity_entry10bp_sharpe"] = sharpe(daily_pnl(tw, sess))
        results[name] = r | {"first": str(sess[0].date()), "last": str(sess[-1].date())}
        save_trades(t, name)
    # S2 stop variant (secondary): -3% stop checked on hourly bars, only where hourly data exists
    results["S2_stopvariant_hourly_window"] = s2_stop_variant(px, hp)
    for k, v in results.items():
        record("result", f"intraday_stocks_test:{k}", {}, f"{v.get('first')}..{v.get('last')}", "intraday stocks TEST (single run)", metrics=v)
    (OUT / "test.json").write_text(json.dumps(results, indent=1, default=str))
    show = ["n_trades", "mean_gross_per_trade", "mean_net_per_trade", "win_rate", "E1_lower_bound", "E1", "E2_sharpe", "E2",
            "E3_stress_mean", "E3", "E4_thirds", "E4", "E5_placebo_p", "E5", "E6_dsr", "E6", "E7", "ALL_PASS"]
    df = pd.DataFrame({k: v for k, v in results.items() if "E1" in v}).T
    print(df[[c for c in show if c in df.columns]].to_string())
    print("n_trials used for DSR:", n_trials, "trial SR var:", var)


def s2_stop_variant(px, hp, stop=-0.03):
    """Default S2 picks inside the hourly window; if an hourly low breaches entry*(1+stop), exit at the
    close of that hourly bar (bar-close fill: hourly data cannot time the stop more precisely)."""
    from tradelab.intraday.research.stocks_data import load
    sess = hp["p1030"].index
    t = s2_run(px, "S2_default_thr1_top5_stocks+sector", str(sess[0].date()), str(sess[-1].date()))
    if t.empty:
        return {"n_trades": 0}
    cache = {}
    out = []
    for _, r in t.iterrows():
        if r.symbol not in cache:
            try:
                h = load(r.symbol, "hourly")
                h["session"] = pd.to_datetime(h.time_et.str[:10])
            except FileNotFoundError:           # no hourly file: the stop cannot be checked, exit stays at the close
                h = None
            cache[r.symbol] = h
        h = cache[r.symbol]
        if h is None:
            out.append(r.exit_px)
            continue
        day = h[h.session == r.session].sort_values("time_et")
        exit_px = r.exit_px
        for _, b in day.iterrows():
            if b.low <= r.entry_px * (1 + stop):
                exit_px = b.close
                break
        out.append(exit_px)
    t["exit_px"] = out
    c_in, c_out = 0.0005, 0.0005        # a stop exit is an intraday market order
    t["gross_ret"] = t.exit_px / t.entry_px - 1
    t["net_ret"] = t.exit_px * (1 - c_out) / (t.entry_px * (1 + c_in)) - 1
    sessions = sess
    return {"label": "secondary; hourly-data window only; stop filled at hourly bar close",
            "n_trades": len(t), "mean_net_per_trade": float(t.net_ret.mean()),
            "daily_sharpe_ann": sharpe(daily_pnl(t, sessions)), "first": str(sess[0].date()), "last": str(sess[-1].date())}


def phase_explore():
    syms = sorted(set(STOCKS + INDEX + SECTOR))
    t = S3.trades(syms)
    if t.empty:
        print("no S3 trades"); return
    sess = pd.DatetimeIndex(sorted(t.session.unique()))
    p = daily_pnl(t, sess)
    res = {"label": "EXPLORATORY ONLY - cannot pass (60 days of 5m data)", "n_trades": len(t),
           "mean_gross": float(t.gross_ret.mean()), "mean_net": float(t.net_ret.mean()),
           "win_rate": float((t.net_ret > 0).mean()), "sum_daily_pnl": float(p.sum()),
           "daily_sharpe_ann_unreliable": sharpe(p), "first": str(sess[0].date()), "last": str(sess[-1].date())}
    record("result", "intraday_stocks_explore:S3", {}, f"{res['first']}..{res['last']}", "exploratory", metrics=res)
    t.to_csv(OUT / "explore_trades_S3.csv", index=False)
    (OUT / "explore_S3.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    {"dev": phase_dev, "val": phase_val, "freeze": phase_freeze, "test": phase_test, "explore": phase_explore}[sys.argv[1]]()
