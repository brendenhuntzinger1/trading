"""Replay the stock research test periods through the live engine and compare
with the independent research trade lists. Run: .venv/bin/python research/intraday/crosscheck/stocks.py"""
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tradelab.intraday.costs import STOCK_AT_OPEN, STOCK_INTRADAY
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.replay import replay_bars, replay_daily_open_close, trades_frame
from tradelab.intraday.sessions import StockSessions
from tradelab.intraday.setups import S1IntradayMomentum, S2GapReversal

D = ROOT / "data" / "stocks"
OUT = ROOT / "research" / "intraday" / "stocks" / "out"
S = StockSessions()
U = pd.read_csv(D / "universe.csv")


def daily(sym):
    df = pd.read_csv(D / "daily" / f"{sym}.csv")
    df.index = df.time_et.str[:10]
    return df[["open", "high", "low", "close", "volume"]]


def hourly(sym):
    p = D / "hourly" / f"{sym}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "close"])


def compare(eng_trades: pd.DataFrame, research: pd.DataFrame, label: str) -> dict:
    e = eng_trades.assign(session=[S.day_key(t) for t in eng_trades.entry_time])
    k = ["session", "symbol"]
    m = e.merge(research, on=k, suffixes=("_eng", "_res"))
    out = {"label": label, "engine_trades": len(e), "research_trades": len(research), "matched": len(m),
           "match_rate_vs_research": round(len(m) / max(1, len(research)), 4),
           "engine_mean_net": float(e.net_ret.mean()), "research_mean_net": float(research.net_ret.mean()),
           "matched_mean_net_eng": float(m.net_ret_eng.mean()) if len(m) else None,
           "matched_mean_net_res": float(m.net_ret_res.mean()) if len(m) else None,
           "matched_net_corr": float(np.corrcoef(m.net_ret_eng, m.net_ret_res)[0, 1]) if len(m) > 2 else None,
           "matched_entry_px_max_abs_diff_pct": float((m.entry_px_eng / m.entry_px_res - 1).abs().max()) if len(m) else None}
    only_eng = e.merge(research[k], on=k, how="left", indicator=True).query("_merge == 'left_only'")
    only_res = research.merge(e[k], on=k, how="left", indicator=True).query("_merge == 'left_only'")
    out["examples_engine_only"] = only_eng[k].head(5).values.tolist()
    out["examples_research_only"] = only_res[k].head(5).values.tolist()
    return out


def run_s2(label, symbols, research_file, start="2021-01-04", end="2026-10-24"):
    data = {s: daily(s) for s in symbols + ["SPY"]}
    L = IntradayLimits(market="stocks", max_positions=5, max_weight=0.2, max_gross=1.0, daily_loss_limit=0.99,
                       max_entries_per_day=10, no_entries_last_minutes=0)
    eng = Engine(L, [S2GapReversal(data)], {"S2": STOCK_AT_OPEN}, S, 100_000.0)
    replay_daily_open_close(eng, data, S, start=start, end=end)
    return compare(trades_frame(eng), pd.read_csv(OUT / research_file), label)


def run_s1(label, symbols, research_file):
    h = {s: hourly(s) for s in symbols}
    h = {s: v for s, v in h.items() if v is not None}
    dd = {s: daily(s) for s in h}
    res = pd.read_csv(OUT / research_file)
    start = pd.Timestamp(res.session.min()).tz_localize("America/New_York").tz_convert("UTC")
    L = IntradayLimits(market="stocks", max_positions=5, max_weight=0.2, max_gross=1.0, daily_loss_limit=0.99,
                       max_entries_per_day=10, no_entries_last_minutes=0)
    eng = Engine(L, [S1IntradayMomentum(h, S, daily=dd)], {"S1": STOCK_INTRADAY}, S, 100_000.0)
    replay_bars(eng, h, timedelta(hours=1), S, start=start - pd.Timedelta(days=1))
    t = trades_frame(eng)
    t = t[[S.day_key(x) >= res.session.min() for x in t.entry_time]]
    return compare(t, res, label)


if __name__ == "__main__":
    stocks = U[U.kind == "stock"].yahoo.tolist()
    sector = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]
    sector = [s for s in sector if (D / "daily" / f"{s}.csv").exists()]
    results = [
        run_s2("S2 default (stocks + sector ETFs)", stocks + sector, "test_trades_S2_default_thr1_top5_stocks+sector.csv"),
        run_s2("S2 ETF-only", sector + ["QQQ", "IWM", "DIA"], "test_trades_S2_etf_only_thr1_top5.csv"),
        run_s1("S1 default", stocks + ["SPY", "QQQ", "IWM", "DIA"], "test_trades_S1_default_thr0.25_top5_all.csv"),
    ]
    (ROOT / "research" / "intraday" / "crosscheck" / "stocks.json").write_text(json.dumps(results, indent=1, default=str))
    for r in results:
        print(json.dumps(r, default=str))
