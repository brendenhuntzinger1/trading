"""Gross and net effect per trade with day-block bootstrap CIs, for every strategy and period.
Dev/validation trade lists are regenerated with the engine (which reproduces the research test lists
exactly); test lists are the research's own. Run: .venv/bin/python research/intraday/audit/periods.py"""
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research/intraday/crosscheck"))
from tradelab.research.metrics import stationary_bootstrap_idx
import stocks as SX
import crypto as CX
from tradelab.intraday.costs import CRYPTO_MAKER_IN, CRYPTO_TAKER, STOCK_AT_OPEN, STOCK_INTRADAY
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.replay import replay_bars, replay_daily_open_close, trades_frame
from tradelab.intraday.sessions import CryptoSessions
from tradelab.intraday.setups import C1CascadeReversal, C2IntradayMomentum, S1IntradayMomentum, S2GapReversal

OUT = Path(__file__).parent
RT = {"S1": 0.0008, "S2": 0.0008, "S2_etf": 0.0008, "C1": 0.0106, "C2": 0.0132}   # base round trips


def ci(trades: pd.DataFrame, col: str, day_col: str, n_boot=2000, seed=11):
    """Per-trade mean with a 90% CI from a stationary bootstrap over trading days (trades on the same
    day are dependent, so whole days are resampled)."""
    g = trades.groupby(trades[day_col].astype(str).str[:10])[col]
    sums, counts = g.sum().to_numpy(), g.count().to_numpy()
    rng = np.random.default_rng(seed)
    est = []
    for _ in range(n_boot):
        i = stationary_bootstrap_idx(len(sums), 5, rng)
        est.append(sums[i].sum() / counts[i].sum())
    return float(sums.sum() / counts.sum()), float(np.quantile(est, 0.05)), float(np.quantile(est, 0.95))


def stock_lists():
    S = SX.S
    stocks = SX.U[SX.U.kind == "stock"].yahoo.tolist()
    sector = [s for s in ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"] if (SX.D / "daily" / f"{s}.csv").exists()]
    out = {}
    L = IntradayLimits(market="stocks", max_positions=5, max_weight=0.2, max_gross=1.0, daily_loss_limit=0.99,
                       max_entries_per_day=10, no_entries_last_minutes=0)
    for name, syms in (("S2", stocks + sector), ("S2_etf", sector + ["QQQ", "IWM", "DIA"])):
        data = {s: SX.daily(s) for s in syms + ["SPY"]}
        for period, (a, b) in {"dev": ("2000-01-01", "2016-01-01"), "validation": ("2016-01-01", "2021-01-01")}.items():
            eng = Engine(L, [S2GapReversal(data)], {"S2": STOCK_AT_OPEN}, S, 100_000.0)
            replay_daily_open_close(eng, data, S, start=a, end=b)
            t = trades_frame(eng); t["day"] = [S.day_key(x) for x in t.entry_time]
            out[(name, period)] = t
    h = {s: SX.hourly(s) for s in stocks + ["SPY", "QQQ", "IWM", "DIA"]}
    h = {s: v for s, v in h.items() if v is not None}
    dd = {s: SX.daily(s) for s in h}
    eng = Engine(L, [S1IntradayMomentum(h, S, daily=dd)], {"S1": STOCK_INTRADAY}, S, 100_000.0)
    replay_bars(eng, h, timedelta(hours=1), S, end="2025-08-26")
    t = trades_frame(eng); t["day"] = [S.day_key(x) for x in t.entry_time]
    out[("S1", "dev")] = t[t.day <= "2025-01-24"]
    out[("S1", "validation")] = t[(t.day > "2025-01-24") & (t.day <= "2025-08-25")]
    return out


def crypto_lists():
    out = {}
    for name, cls, syms, cost in (("C1", C1CascadeReversal, ["BTC-USD", "ETH-USD", "SOL-USD"], CRYPTO_MAKER_IN),
                                  ("C2", C2IntradayMomentum, ["BTC-USD", "ETH-USD"], CRYPTO_TAKER)):
        frames = {s: CX.bars(s) for s in syms}
        L = IntradayLimits(market="crypto", max_positions=len(syms), max_weight=0.25, max_gross=1.0, daily_loss_limit=0.99, max_entries_per_day=50)
        eng = Engine(L, [cls(frames)], {name: cost}, CryptoSessions(), 100_000.0)
        replay_bars(eng, frames, timedelta(minutes=5), CryptoSessions(), start="2020-01-01", end="2023-01-01")
        t = trades_frame(eng); t["day"] = pd.to_datetime(t.entry_time, utc=True).dt.strftime("%Y-%m-%d")
        out[(name, "dev")] = t
        v = pd.read_csv(ROOT / f"research/intraday/crypto/out/validation_trades_{name}.csv")
        out[(name, "validation")] = v.assign(day=v.entry_time_utc.str[:10])
    return out


def test_lists():
    f = {"S1": "stocks/out/test_trades_S1_default_thr0.25_top5_all.csv", "S2": "stocks/out/test_trades_S2_default_thr1_top5_stocks+sector.csv",
         "S2_etf": "stocks/out/test_trades_S2_etf_only_thr1_top5.csv", "C1": "crypto/out/test_trades_C1_C1_k4_maker.csv",
         "C2": "crypto/out/test_trades_C2_C2_m1.5.csv"}
    out = {}
    for k, p in f.items():
        t = pd.read_csv(ROOT / "research/intraday" / p)
        t["day"] = t["session"] if "session" in t else t.entry_time_utc.str[:10]
        out[(k, "test")] = t
    return out


if __name__ == "__main__":
    lists = {**stock_lists(), **crypto_lists(), **test_lists()}
    rows = []
    for (name, period), t in sorted(lists.items(), key=lambda x: (x[0][0], ["dev", "validation", "test"].index(x[0][1]))):
        m, lo, hi = ci(t, "gross_ret", "day")
        rt = RT[name]
        verdict = ("gross CI entirely below cost: evidence the effect is too small to be useful" if hi < rt else
                   "gross CI entirely above cost" if lo > rt else
                   "CI straddles cost: insufficient evidence either way")
        rows.append({"strategy": name, "period": period, "trades": len(t), "days": t.day.nunique(),
                     "gross_bp": round(m * 1e4, 1), "gross_90ci_bp": [round(lo * 1e4, 1), round(hi * 1e4, 1)],
                     "zero_in_ci": lo <= 0 <= hi, "base_roundtrip_bp": rt * 1e4, "vs_cost": verdict})
    (OUT / "periods.json").write_text(json.dumps(rows, indent=1))
    print(pd.DataFrame(rows).to_string(index=False))
