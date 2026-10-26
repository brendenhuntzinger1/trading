"""Crypto intraday study driver (C1, C2). Phases: dev | validate | test | holdout.

    .venv/bin/python -m tradelab.intraday.research.crypto_study dev
    .venv/bin/python -m tradelab.intraday.research.crypto_study validate
    .venv/bin/python -m tradelab.intraday.research.crypto_study test      # runs once; refuses to repeat
    .venv/bin/python -m tradelab.intraday.research.crypto_study holdout

Selection rule, fixed before any dev result was seen: per hypothesis, the dev configuration with the
highest Sharpe of daily weighted net P&L (calendar days, zeros included); ties -> the pre-specified default.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from tradelab.research.registry import entries, record

from . import crypto_data as D
from . import crypto_rules as R
from .crypto_eval import daily, evaluate, sharpe

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "intraday" / "crypto" / "out"
M1_CACHE = ROOT / "data" / "crypto_intraday" / "m1_cache"
DEV = ("2020-01-01", "2023-01-01")
VAL = ("2023-01-01", "2024-01-01")
TEST = ("2024-01-01", "2026-10-24")
C1_COINS = ["BTC-USD", "ETH-USD", "SOL-USD"]
C2_COINS = ["BTC-USD", "ETH-USD"]
C1_CONFIGS = [R.C1Config(4, False), R.C1Config(3, False), R.C1Config(4, True), R.C1Config(3, True)]
C2_CONFIGS = [R.C2Config(1.0), R.C2Config(0.5), R.C2Config(1.5)]
DEFAULTS = {"C1": R.C1Config(4, False).name, "C2": R.C2Config(1.0).name}
STOCK_TRIALS_ASSUMED = 18
PRIOR_TRIALS = 73
STABLES = {"USDT", "USDC", "DAI", "PYUSD", "EURC", "GUSD", "PAX", "BUSD", "USDS", "TUSD", "UST", "FDUSD", "RLUSD",
           "USD1", "USDE", "GYEN", "CBETH", "WBTC", "CBBTC", "MSOL", "WETH", "LSETH"}


def ts(x):
    return pd.Timestamp(x, tz="UTC")


_bars: dict = {}


def bars(sym, gran):
    if (sym, gran) not in _bars:
        _bars[sym, gran] = D.load(sym, gran)
    return _bars[sym, gran]


def m1_window(sym, start, end):
    """1m bars for maker fills, cached per window; Coinbase omits empty minutes (kept as gaps)."""
    M1_CACHE.mkdir(parents=True, exist_ok=True)
    f = M1_CACHE / f"{sym}_{start:%Y%m%dT%H%M}.csv"
    if f.exists():
        df = pd.read_csv(f, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    df = D.fetch(sym, 60, start.to_pydatetime(), end.to_pydatetime())
    df.to_csv(f)
    return df


def run_c1(cfg, coins, start, end, h1_of=None, m5_of=None):
    parts = []
    for s in coins:
        h1 = h1_of(s) if h1_of else bars(s, 3600)
        m5 = m5_of(s) if m5_of else bars(s, 300)
        parts.append(R.c1_trades(s, h1, m5, cfg, m1_windows=m1_window, start=ts(start), end=ts(end)))
    t = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else parts[0]
    return t.sort_values("entry_time_utc").reset_index(drop=True) if len(t) else t


def run_c2(cfg, coins, start, end):
    parts = [R.c2_trades(s, bars(s, 300), cfg, start=ts(start), end=ts(end)) for s in coins]
    t = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else parts[0]
    return t.sort_values("entry_time_utc").reset_index(drop=True) if len(t) else t


def summary(t, start, end):
    dd = daily(t, start, end)
    sd = dd.pnl.std()
    return {"n": int(len(t)), "gross_mean": float(t.gross_ret.mean()) if len(t) else None,
            "net_mean": float(t.net_ret.mean()) if len(t) else None,
            "win_rate": float((t.net_ret > 0).mean()) if len(t) else None,
            "sharpe": sharpe(dd.pnl), "sr_per_day": float(dd.pnl.mean() / sd) if sd > 0 else 0.0,
            "total_pnl": float(dd.pnl.sum())}


def cfg_dict(cfg):
    d = asdict(cfg)
    return {k: (str(v) if isinstance(v, pd.Timedelta) else v) for k, v in d.items()}


def dev():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for hyp, cfgs, runner, coins in (("C1", C1_CONFIGS, run_c1, C1_COINS), ("C2", C2_CONFIGS, run_c2, C2_COINS)):
        for cfg in cfgs:
            t = runner(cfg, coins, *DEV)
            s = summary(t, *DEV)
            record("result", f"intraday_crypto_dev:{cfg.name}", cfg_dict(cfg), f"{DEV[0]}..{DEV[1]}",
                   "intraday crypto dev trial (counts toward E6)", metrics=s)
            rows.append({"hyp": hyp, "config": cfg.name, **s})
            print(hyp, cfg.name, s, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "dev_trials.csv", index=False)
    chosen = {}
    for hyp, g in df.groupby("hyp"):
        best = g.sharpe.max()
        tied = g[np.isclose(g.sharpe, best)]
        chosen[hyp] = DEFAULTS[hyp] if DEFAULTS[hyp] in set(tied.config) else tied.config.iloc[0]
    (OUT / "dev_selection.json").write_text(json.dumps(chosen, indent=1))
    print("selected:", chosen)


def _cfg_by_name(name):
    for c in C1_CONFIGS + C2_CONFIGS:
        if c.name == name:
            return c
    raise KeyError(name)


def validate():
    chosen = json.loads((OUT / "dev_selection.json").read_text())
    res = {}
    for hyp, name in chosen.items():
        cfg = _cfg_by_name(name)
        t = (run_c1 if hyp == "C1" else run_c2)(cfg, C1_COINS if hyp == "C1" else C2_COINS, *VAL)
        res[hyp] = {"config": name, **summary(t, *VAL)}
        t.to_csv(OUT / f"validation_trades_{hyp}.csv", index=False)
        record("result", f"intraday_crypto_validation:{name}", cfg_dict(cfg), f"{VAL[0]}..{VAL[1]}",
               "validation (confirm only; no re-selection)", metrics=res[hyp])
    (OUT / "validation.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float))


def trial_stats():
    dev_rows = pd.read_csv(OUT / "dev_trials.csv")
    n_mine = len(dev_rows)
    srs = dev_rows.sr_per_day.to_numpy()
    return PRIOR_TRIALS + n_mine + STOCK_TRIALS_ASSUMED, float(np.var(srs)), n_mine


def test():
    lock = OUT / "test_done.json"
    if lock.exists():
        sys.exit(f"test already run at {json.loads(lock.read_text())['at']}; it runs once")
    chosen = json.loads((OUT / "dev_selection.json").read_text())
    n_trials, var, n_mine = trial_stats()
    for hyp, name in chosen.items():
        record("frozen_config", f"intraday_crypto_frozen:{hyp}", cfg_dict(_cfg_by_name(name)), f"{TEST[0]}..{TEST[1]}",
               "frozen before the single test run", note=f"selected by the pre-stated dev rule; n_trials for E6 = {n_trials}")
    lock.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "chosen": chosen}))
    results = {}
    for hyp, name in chosen.items():
        cfg = _cfg_by_name(name)
        coins = C1_COINS if hyp == "C1" else C2_COINS
        t = (run_c1 if hyp == "C1" else run_c2)(cfg, coins, *TEST)
        cols = ["symbol", "side", "entry_time_utc", "entry_px", "exit_time_utc", "exit_px", "exit_reason",
                "gross_ret", "cost", "net_ret", "size_weight", "signal_time_utc", "sigma", "signal_ret", "entry_cost", "exit_cost"]
        t[cols].to_csv(OUT / f"test_trades_{hyp}_{name}.csv", index=False)
        ev = evaluate(t, {s: bars(s, 300) for s in coins}, ts(TEST[0]), ts(TEST[1]), n_trials, var)
        ev["exit_reasons"] = t.exit_reason.value_counts().to_dict() if len(t) else {}
        ev["per_symbol"] = t.groupby("symbol").net_ret.agg(["count", "mean"]).to_dict() if len(t) else {}
        results[hyp] = {"config": name, **ev}
        record("result", f"intraday_crypto_test:{name}", cfg_dict(cfg), f"{TEST[0]}..{TEST[1]}", "single test run", metrics=ev)
        print(hyp, name, json.dumps(ev, indent=1, default=float), flush=True)
    (OUT / "test.json").write_text(json.dumps(results, indent=1, default=float))


def eligible_holdouts(start, end, min_dv=20e6):
    """Point-in-time: a coin-day is eligible if the median dollar volume of the 30 prior completed days > min_dv."""
    out = {}
    for f in sorted((ROOT / "data" / "universe").glob("*-USD_1d.csv")):
        sym = f.name.replace("_1d.csv", "")
        base = sym.split("-")[0]
        if sym in C1_COINS or base in STABLES:
            continue
        d = pd.read_csv(f, index_col=0)
        d.index = pd.to_datetime(d.index, utc=True)
        dv = (d.volume * d.close).rolling(30, min_periods=30).median().shift(1)
        ok = dv[(dv.index >= ts(start)) & (dv.index < ts(end)) & (dv > min_dv)]
        if len(ok):
            out[sym] = set(ok.index.normalize())
    return out


def holdout():
    chosen = json.loads((OUT / "dev_selection.json").read_text())
    cfg = _cfg_by_name(chosen["C1"])
    elig = eligible_holdouts(*TEST)
    print(len(elig), "holdout coins eligible on at least one test day", flush=True)
    h1s, trades = {}, []
    for sym, days in elig.items():
        h1 = D.fetch(sym, 3600, datetime(2023, 11, 1, tzinfo=timezone.utc), datetime(2026, 10, 24, tzinfo=timezone.utc))
        if len(h1) < 800:
            continue
        sigs = R.c1_signals(h1, cfg)
        sigs = sigs[(sigs.index >= ts(TEST[0])) & (sigs.index < ts(TEST[1]))]
        sigs = sigs[[i.normalize() in days for i in sigs.index]]
        if sigs.empty:
            continue
        # 5m bars only around signals (+ maker 1m windows if the config is maker)
        m5 = pd.concat([D.fetch(sym, 300, (H - pd.Timedelta(minutes=5)).to_pydatetime(),
                                (H + pd.Timedelta(hours=6, minutes=30)).to_pydatetime()) for H in sigs.index])
        m5 = m5[~m5.index.duplicated()].sort_index()
        h1_sig = h1.copy()
        t = R.c1_trades(sym, h1_sig, m5, cfg, m1_windows=m1_window, start=ts(TEST[0]), end=ts(TEST[1]))
        t = t[[pd.Timestamp(x).normalize() in days for x in t.signal_time_utc]] if len(t) else t
        if len(t):
            trades.append(t)
        print(sym, len(sigs), "signals", len(t), "trades", flush=True)
    t = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    t.to_csv(OUT / f"holdout_trades_C1_{cfg.name}.csv", index=False)
    if len(t):
        dd = daily(t, *TEST)
        from .crypto_eval import e1_bootstrap
        mean, lb = e1_bootstrap(dd)
        res = {"config": cfg.name, "coins_traded": int(t.symbol.nunique()), "n": int(len(t)),
               "gross_mean": float(t.gross_ret.mean()), "net_mean": mean, "net_lower95": lb,
               "sharpe": sharpe(dd.pnl), "win_rate": float((t.net_ret > 0).mean())}
    else:
        res = {"config": cfg.name, "n": 0}
    record("result", f"intraday_crypto_holdout:{cfg.name}", cfg_dict(cfg), f"{TEST[0]}..{TEST[1]}",
           "holdout coins (point-in-time liquidity filter)", metrics=res)
    (OUT / "holdout.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    {"dev": dev, "validate": validate, "test": test, "holdout": holdout}[sys.argv[1]]()
