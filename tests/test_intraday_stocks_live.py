from datetime import timedelta

import numpy as np
import pandas as pd

from tradelab.intraday import live_stocks
from tradelab.intraday.costs import STOCK_AT_OPEN, STOCK_INTRADAY
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.sessions import StockSessions

S = StockSessions()
DAYS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-08-03", "2026-10-23") if S.bounds(d.strftime("%Y-%m-%d"))]


def make_data(gap_day, sym_gap=-0.03):
    """Flat prices; on gap_day 'BBB' opens 3% down then recovers 1% by the close."""
    hourly, daily = {}, {}
    for sym, px in (("SPY", 500.0), ("BBB", 100.0)):
        rows_h, rows_d = [], []
        for d in DAYS:
            o, c = S.bounds(d)
            idx = pd.date_range(o, c, freq="1h", inclusive="left")
            op = np.full(len(idx), px)
            cl = np.full(len(idx), px)
            if sym == "BBB" and d == gap_day:
                op = np.linspace(px * (1 + sym_gap), px * 0.98, len(idx))
                cl = np.r_[op[1:], px * (1 + sym_gap) * 1.01]
            rows_h.append(pd.DataFrame({"open": op, "high": np.maximum(op, cl), "low": np.minimum(op, cl), "close": cl, "volume": 2e6}, index=idx))
            rows_d.append(pd.DataFrame({"open": [op[0]], "high": [max(op.max(), cl.max())], "low": [min(op.min(), cl.min())],
                                        "close": [cl[-1]], "volume": [1e7]}, index=[d]))
        hourly[sym], daily[sym] = pd.concat(rows_h), pd.concat(rows_d)
    return hourly, daily


def fake_fetch(hourly, daily):
    def fetch(sym, interval, span, now):
        if interval == "1h":                                      # like the real client: last bar ends at the close
            h = hourly[sym]
            ends = [min(t + pd.Timedelta(hours=1), pd.Timestamp(S.bounds(S.day_key(t))[1])) for t in h.index]
            return h[pd.DatetimeIndex(ends) <= pd.Timestamp(now)]
        if interval == "1d":
            return daily[sym]
        h = hourly[sym]                                           # 1m: first minute of today = opening print
        day = S.day_key(now)
        o = S.bounds(day)[0]
        row = h.loc[[pd.Timestamp(o)]] if pd.Timestamp(o) in h.index else h.iloc[:0]
        return row
    return fetch


def test_gap_reversal_runs_end_to_end_in_paper():
    gap_day = DAYS[-1]
    hourly, daily = make_data(gap_day)
    eng = Engine(IntradayLimits(market="stocks"), [], {"S1": STOCK_INTRADAY, "S2": STOCK_AT_OPEN}, S, 10_000.0)
    o, c = S.bounds(gap_day)
    state = {"last_bar": o, "opened": None}
    fetch = fake_fetch(hourly, daily)
    for minutes in (2, 62, 122, 182, 242, 302, 362, 392):        # polls through the session
        state = live_stocks.cycle(eng, ["SPY", "BBB"], state, o + timedelta(minutes=minutes), S, ["S2"], fetch=fetch)
    (t,) = eng.trades
    assert t.setup == "S2" and t.symbol == "BBB" and t.exit_reason == "session_close"
    assert t.entry_px == hourly["BBB"].loc[pd.Timestamp(o), "open"]
    assert t.gross_pnl > 0 and t.cost > 0
