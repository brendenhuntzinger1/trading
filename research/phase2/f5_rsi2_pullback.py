"""F5: trend pullback, RSI(2) inside a 200-day uptrend, index and sector ETFs (research/phase2/FAMILIES.md).

    python research/phase2/f5_rsi2_pullback.py table     # daily decision/close table from SIP 1-minute bars
    python research/phase2/f5_rsi2_pullback.py dev       # baseline + 4 configs on 2016-01-04..2022-12-30

Point-in-time: each session's decision is taken at (close - 15 min), i.e. 15:45 ET (12:45 on half-days), using
that minute's price as "today's close" in RSI(2) and the 200-day SMA (built from earlier 15:59 closes). Entries
and exits execute at the close (15:59 bar close as the closing-quote proxy). A position entered at the close of
t earns the close-to-close return of t+1 onwards.
"""
from __future__ import annotations

import gzip
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import evaluate as ev                               # noqa: E402
from research.phase2 import stages                                       # noqa: E402
from tradelab.stocks.timeutil import ET, bars_frame, session_bounds      # noqa: E402

FAMILY = "F5"
CACHE = ROOT / "data" / "stocks" / "p2cache" / "intraday"
TABLE = ROOT / "data" / "stocks" / "p2panels" / "f5_table.pkl"
RESULTS = ROOT / "research" / "phase2" / "results"
MAJORS = ["SPY", "QQQ", "IWM", "DIA"]
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
DEV = ("2016-01-04", "2022-12-30")
HALF_SPREAD = {**{s: 0.5e-4 for s in MAJORS}, **{s: 2e-4 for s in SECTORS}}   # protocol §3 tiers (assumption)

CONFIGS = {
    "B0": {"symbols": MAJORS, "entry_rsi": 10, "exit": "above_prev_high", "trend": True},
    "C1": {"symbols": MAJORS, "entry_rsi": 10, "exit": "rsi_above_70", "trend": True},
    "C2": {"symbols": MAJORS, "entry_rsi": 5, "exit": "above_prev_high", "trend": True},
    "C3": {"symbols": SECTORS, "entry_rsi": 10, "exit": "above_prev_high", "trend": True},
    "C4": {"symbols": MAJORS, "entry_rsi": 10, "exit": "above_prev_high", "trend": False},
}
MAX_HOLD = 10


def daily_table(symbol: str) -> pd.DataFrame:
    rows = []
    for p in sorted(CACHE.glob("1Min_all_*")):
        if symbol in p.name:
            rows.extend(json.loads(gzip.decompress(p.read_bytes())).get(symbol, []))
    f = bars_frame(rows)
    out = []
    for day, g in f.groupby(f.index.tz_convert(ET).strftime("%Y-%m-%d")):
        b = session_bounds(day)
        if b is None:
            continue
        g = g[(g.index >= b[0]) & (g.index < b[1])]
        dec = g[g.index < b[1] - pd.Timedelta(minutes=15)]
        if g.empty or dec.empty:
            continue
        out.append({"day": day, "p_dec": float(dec.close.iloc[-1]), "close": float(g.close.iloc[-1]),
                    "high": float(g.high.max()), "n_bars": len(g)})
    t = pd.DataFrame(out).set_index("day")
    t.index = pd.to_datetime(t.index)
    return t


def build_table() -> dict[str, pd.DataFrame]:
    tabs = {s: daily_table(s) for s in MAJORS + SECTORS}
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_bytes(pickle.dumps(tabs))
    return tabs


def rsi2_with(closes: np.ndarray, today: float) -> float:
    """Wilder RSI(2) over closes[...] with `today` appended as the latest close."""
    x = np.append(closes, today)
    d = np.diff(x)
    if len(d) < 2:
        return np.nan
    up, dn = np.maximum(d, 0), np.maximum(-d, 0)
    ag, al = up[:2].mean(), dn[:2].mean()
    for u, v in zip(up[2:], dn[2:]):
        ag, al = (ag + u) / 2, (al + v) / 2
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def positions(t: pd.DataFrame, cfg: dict) -> pd.Series:
    """1 on sessions whose close-to-close return is held (entered at an earlier close), else 0."""
    closes = t.close.to_numpy()
    hold = np.zeros(len(t))
    in_pos, held = False, 0
    for i in range(len(t)):
        p = t.p_dec.iloc[i]
        hist = closes[max(0, i - 60):i]                     # RSI(2) converges within a few dozen bars
        r = rsi2_with(hist, p) if i >= 3 else np.nan
        if in_pos:
            hold[i] = 1.0                                   # this session's return accrues to the position
            held += 1
            ex = (p > t.high.iloc[i - 1]) if cfg["exit"] == "above_prev_high" else (r > 70)
            if ex or held >= MAX_HOLD:
                in_pos, held = False, 0                     # sell at this close
            continue
        sma_ok = True
        if cfg["trend"]:
            sma_ok = i >= 199 and p > np.mean(np.append(closes[i - 199:i], p))
        if not np.isnan(r) and r < cfg["entry_rsi"] and sma_ok:
            in_pos, held = True, 0                          # buy at this close
    return pd.Series(hold, index=t.index)


def run(tabs: dict, cfg: dict, lo: str, hi: str, slip: float = ev.SLIP_BASE):
    syms = cfg["symbols"]
    n = len(syms)
    idx = sorted(set().union(*[tabs[s].index for s in syms]))
    ret = pd.DataFrame({s: tabs[s].close.pct_change() for s in syms}).reindex(idx)
    w = pd.DataFrame({s: positions(tabs[s], cfg) / n for s in syms}).reindex(idx).fillna(0.0)
    hs = pd.DataFrame({s: HALF_SPREAD[s] for s in syms}, index=idx)
    keep = (ret.index >= pd.Timestamp(lo)) & (ret.index <= pd.Timestamp(hi))
    p = ev.backtest_weights(w[keep], ret[keep], hs[keep], slip=slip)
    exposure = p.exposure.mean()
    bh = ret[keep].fillna(0.0).mean(axis=1)
    control = bh * exposure                                   # buy-and-hold at matched exposure (no trading cost)
    trades = int(sum(((w[s] > 0) & (w[s].shift(1).fillna(0) == 0))[keep].sum() for s in syms))
    return p, control, trades, w[keep], ret[keep]


def random_entry_control(w: pd.DataFrame, ret: pd.DataFrame, reps: int = 200, seed: int = 5) -> dict:
    """Same number of trades and holding lengths per ETF, random start dates: mean gross daily P&L."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(reps):
        tot = pd.Series(0.0, index=ret.index)
        for s in w.columns:
            h = (w[s] > 0).astype(int).to_numpy()
            lengths = []
            run_len = 0
            for v in h:
                if v:
                    run_len += 1
                elif run_len:
                    lengths.append(run_len); run_len = 0
            if run_len:
                lengths.append(run_len)
            sim = np.zeros(len(h))
            for L in lengths:
                st = rng.integers(0, max(1, len(h) - L))
                sim[st:st + L] = 1
            tot += sim * w[s].max() * ret[s].fillna(0.0).to_numpy()
        out.append(tot.mean())
    return {"mean_gross_bp": float(np.mean(out) * 1e4), "p95_gross_bp": float(np.quantile(out, 0.95) * 1e4)}


def dev() -> dict:
    tabs = pickle.loads(TABLE.read_bytes()) if TABLE.exists() else build_table()
    out, quals, metrics = {"family": FAMILY, "window": DEV, "configs": {}}, {}, {}
    for name, cfg in CONFIGS.items():
        p, control, trades, w, ret = run(tabs, cfg, *DEV)
        ps, _, _, _, _ = run(tabs, cfg, *DEV, slip=ev.SLIP_STRESS)
        summ = ev.summarise(p, control, control, ps["net"])
        summ["diagnosis"] = {"trades": trades, "time_in_market": float(p.exposure.mean()),
                             "gross_bp_per_trade": float(p.gross.sum() / max(trades, 1) * 1e4 * len(cfg["symbols"])),
                             "random_entry_control": random_entry_control(w, ret),
                             "first_signal_day": str(w[(w > 0).any(axis=1)].index.min())[:10]}
        q = ev.dev_qualifies(summ, etf_family=True)
        out["configs"][name] = {"params": cfg, "summary": summ, "qualifiers": q}
        quals[name] = q
        metrics[name] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"], "trades": trades}
    stages.record_dev(FAMILY, quals, metrics)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "f5_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "table":
        print({k: len(v) for k, v in build_table().items()})
    elif sys.argv[1] == "dev":
        r = dev()
        for k, v in r["configs"].items():
            s = v["summary"]
            print(k, f"net {s['net']['mean_bp']:.2f}bp/day sharpe {s['net']['sharpe']:.2f} trades {s['diagnosis']['trades']} "
                     f"tim {s['diagnosis']['time_in_market']:.2f} vs_ctrl {s['vs_control_net_bp']} years "
                     f"{ {y: round(x * 1e4) for y, x in s['by_year_net'].items()} } rand {s['diagnosis']['random_entry_control']} "
                     f"qual {v['qualifiers']}")
