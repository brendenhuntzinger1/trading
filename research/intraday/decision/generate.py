"""Replay every strategy over ALL periods through the engine and attach signal features.
Dev periods were used for development by the research workers; validation and test periods
have already been examined, so everything downstream is exploratory."""
from datetime import timedelta

import numpy as np
import pandas as pd

from common import OUT, ROOT
from stocks import U, daily, hourly
import exchange_calendars as xc
from tradelab.intraday.sessions import StockSessions


class LongSessions(StockSessions):
    """Same NYSE calendar, extended back to 1999 for the 2000-2015 development period."""
    def __init__(self):
        self.cal = xc.get_calendar("XNYS", start="1999-01-01")


S = LongSessions()
from crypto import bars
from tradelab.intraday.costs import CRYPTO_MAKER_IN, CRYPTO_TAKER, STOCK_AT_OPEN, STOCK_INTRADAY
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.replay import replay_bars, replay_daily_open_close, trades_frame
from tradelab.intraday.sessions import CryptoSessions
from tradelab.intraday.setups import C1CascadeReversal, C2IntradayMomentum, S1IntradayMomentum, S2GapReversal

LIM = dict(max_weight=0.2, max_gross=1.0, daily_loss_limit=0.99, max_entries_per_day=50)
SECTOR = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]


def s2(label, symbols):
    data = {s: daily(s) for s in symbols + ["SPY"]}
    eng = Engine(IntradayLimits(market="stocks", max_positions=5, no_entries_last_minutes=0, **LIM), [S2GapReversal(data)],
                 {"S2": STOCK_AT_OPEN}, S, 100_000.0)
    replay_daily_open_close(eng, data, S)
    t = trades_frame(eng)
    t["day"] = [S.day_key(x) for x in t.entry_time]
    gap = {}
    spy = data["SPY"]
    mg = spy.open / spy.close.shift(1) - 1
    for s in set(t.symbol):
        d = data[s]
        gap[s] = d.open / d.close.shift(1) - 1 - mg.reindex(d.index)
    t["feature"] = [gap[s].get(d) for s, d in zip(t.symbol, t.day)]
    t["strategy"] = label
    return t


def s1():
    syms = U[U.kind == "stock"].yahoo.tolist() + ["SPY", "QQQ", "IWM", "DIA"]
    h = {s: hourly(s) for s in syms}
    h = {s: v for s, v in h.items() if v is not None}
    dd = {s: daily(s) for s in h}
    setup = S1IntradayMomentum(h, S, daily=dd)
    eng = Engine(IntradayLimits(market="stocks", max_positions=5, no_entries_last_minutes=0, **LIM), [setup],
                 {"S1": STOCK_INTRADAY}, S, 100_000.0)
    replay_bars(eng, h, timedelta(hours=1), S)
    t = trades_frame(eng)
    t["day"] = [S.day_key(x) for x in t.entry_time]
    t["feature"] = [setup.feat[s].at[d, "r"] if d in setup.feat[s].index else np.nan for s, d in zip(t.symbol, t.day)]
    t["strategy"] = "S1"
    return t


def crypto(name, cls, syms, costs):
    frames = {s: bars(s) for s in syms}
    setup = cls(frames)
    eng = Engine(IntradayLimits(market="crypto", max_positions=len(syms), max_weight=0.25, max_gross=1.0,
                                daily_loss_limit=0.99, max_entries_per_day=50), [setup], {name: costs}, CryptoSessions(), 100_000.0)
    replay_bars(eng, frames, timedelta(minutes=5), CryptoSessions(), start="2020-02-15")
    t = trades_frame(eng)
    dec = pd.DataFrame([d.__dict__ for d in eng.decisions if d.outcome == "approved"])
    sig_t, feat, sig = [], [], []
    for s, et in zip(t.symbol, t.entry_time):
        d = dec[(dec.symbol == s) & (dec["at"] <= et)]
        at = d["at"].iloc[-1]
        sig_t.append(at)
        f = setup.feat[s]
        key = pd.Timestamp(at) if name == "C1" else pd.Timestamp(at).normalize()
        feat.append(f.at[key, "r"] / f.at[key, "sigma"])
        sig.append(f.at[key, "sigma"])
    t["signal_time"], t["feature"], t["sigma"] = sig_t, feat, sig
    t["day"] = [pd.Timestamp(x).strftime("%Y-%m-%d") for x in t.entry_time]
    t["strategy"] = name
    return t


if __name__ == "__main__":
    stocks = U[U.kind == "stock"].yahoo.tolist()
    jobs = {"S2": lambda: s2("S2", stocks + SECTOR), "S2_etf": lambda: s2("S2_etf", SECTOR + ["QQQ", "IWM", "DIA"]),
            "S1": s1, "C1": lambda: crypto("C1", C1CascadeReversal, ["BTC-USD", "ETH-USD", "SOL-USD"], CRYPTO_MAKER_IN),
            "C2": lambda: crypto("C2", C2IntradayMomentum, ["BTC-USD", "ETH-USD"], CRYPTO_TAKER)}
    for k, f in jobs.items():
        t = f()
        t.to_csv(OUT / f"trades_{k}.csv", index=False)
        print(k, len(t), t.day.min(), t.day.max(), "gross mean %", round(t.gross_ret.mean() * 100, 4), flush=True)
