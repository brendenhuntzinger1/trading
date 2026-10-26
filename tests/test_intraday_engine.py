"""Engine mechanics on synthetic bars. These tests show the engine trades correctly;
they say nothing about whether any strategy has an advantage."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from tradelab.intraday.costs import Costs
from tradelab.intraday.engine import Bar, Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.model import Signal
from tradelab.intraday.replay import Ctx, daily_pnl, replay_bars
from tradelab.intraday.sessions import CryptoSessions, StockSessions

T0 = datetime(2026, 3, 2, tzinfo=timezone.utc)
FREE = Costs(0.0, 0.0)


class Scripted:
    """Emits given signals at given decision times."""
    name = "X"

    def __init__(self, plan):
        self.plan = plan

    def scan(self, t, ctx):
        return self.plan.get(t, [])


def crypto_engine(plan, costs=FREE, **lim):
    L = IntradayLimits(market="crypto", max_weight=0.5, **lim)
    return Engine(L, [Scripted(plan)], {"X": costs}, CryptoSessions(), 1000.0)


def sig(**kw):
    d = dict(setup="X", symbol="BTC-USD", side="long", entry="next_open", reason="test")
    d.update(kw)
    return Signal(**d)


def step(eng, i, bars, step_=timedelta(minutes=5)):
    t = T0 + i * step_
    eng.process_bar(t, t + step_, bars, Ctx(eng.sessions))
    return t + step_


def test_entry_fills_next_bar_open_not_signal_bar():
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, deadline=T0 + timedelta(minutes=15))]})
    step(eng, 0, {"BTC-USD": Bar(100, 101, 99, 100)})
    step(eng, 1, {"BTC-USD": Bar(105, 106, 104, 105)})
    assert eng.s.positions["BTC-USD"].entry_px == 105


def test_stop_assumed_before_target_in_same_bar():
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, stop=95, target=110)]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 1, {"BTC-USD": Bar(100, 112, 94, 101)})
    (t,) = eng.trades
    assert t.exit_reason == "stop" and t.exit_px == 95


def test_gap_through_stop_fills_at_open():
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, stop=95)]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 1, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 2, {"BTC-USD": Bar(90, 91, 88, 90)})
    assert eng.trades[0].exit_px == 90


def test_target_and_time_exits():
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, target=103)]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 1, {"BTC-USD": Bar(100, 104, 99.5, 103.5)})
    assert eng.trades[0].exit_reason == "target" and eng.trades[0].exit_px == 103
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, deadline=T0 + timedelta(minutes=15))]})
    for i in range(4):
        step(eng, i, {"BTC-USD": Bar(100, 100, 100, 100 + i)})
    assert eng.trades[0].exit_reason == "time" and eng.trades[0].exit_px == 102


def test_costs_charged_both_sides_and_cash_reconciles():
    c = Costs(0.0066, 0.0066)
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, deadline=T0 + timedelta(minutes=10))]}, costs=c)
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 1, {"BTC-USD": Bar(100, 100, 100, 110)})
    (t,) = eng.trades
    assert t.cost == pytest.approx(500 * 0.0066 + t.qty * 110 * 0.0066)
    assert eng.equity() == pytest.approx(1000 + t.net_pnl)


def test_limit_touch_is_not_fill_but_through_is():
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(entry="limit", limit=99.0, weight=0.5,
                                                         limit_valid_until=T0 + timedelta(hours=1))]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 1, {"BTC-USD": Bar(100, 100, 99.0, 99.5)})          # touches 99.0 only
    assert "BTC-USD" not in eng.s.positions
    step(eng, 2, {"BTC-USD": Bar(99.5, 99.6, 98.9, 99.2)})        # trades through
    assert eng.s.positions["BTC-USD"].entry_px == 99.0


def test_daily_loss_halts_entries_until_next_day():
    plan = {T0 + timedelta(minutes=5): [sig(weight=0.5)], T0 + timedelta(minutes=15): [sig(symbol="ETH-USD", weight=0.2)]}
    eng = crypto_engine(plan)
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100), "ETH-USD": Bar(10, 10, 10, 10)})
    step(eng, 1, {"BTC-USD": Bar(100, 100, 100, 100), "ETH-USD": Bar(10, 10, 10, 10)})
    step(eng, 2, {"BTC-USD": Bar(100, 100, 90, 90), "ETH-USD": Bar(10, 10, 10, 10)})   # -5% equity
    assert eng.s.halted_today
    assert eng.decisions[-1].outcome == "rejected" and "halted" in eng.decisions[-1].reasons[0]
    eng.process_bar(T0 + timedelta(days=1), T0 + timedelta(days=1, minutes=5), {"BTC-USD": Bar(90, 90, 90, 90)}, Ctx(eng.sessions))
    assert eng.s.halted_today is None


def test_position_count_and_weight_caps():
    sigs = [sig(symbol=s, weight=0.9) for s in ("A", "B", "C")]
    eng = crypto_engine({T0 + timedelta(minutes=5): sigs}, max_positions=2)
    step(eng, 0, {s: Bar(10, 10, 10, 10) for s in "ABC"})
    approved = [d for d in eng.decisions if d.outcome == "approved"]
    assert len(approved) == 2 and all(d.notional <= 500 + 1e-9 for d in approved)       # max_weight 0.5
    assert any("max open positions" in r for d in eng.decisions for r in d.reasons)


def test_risk_sizing_to_stop():
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(stop=98)]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    (d,) = [d for d in eng.decisions if d.outcome == "approved"]
    assert d.notional == pytest.approx(1000 * 0.01 * 100 / 2)                                # 1% risk / 2% stop


def test_crypto_cannot_short_and_unsized_signals_rejected():
    with pytest.raises(ValueError):
        IntradayLimits(market="crypto", allow_short=True).validate()
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(side="short", weight=0.2), sig(symbol="ETH-USD")]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100), "ETH-USD": Bar(1, 1, 1, 1)})
    assert all(d.outcome == "rejected" for d in eng.decisions)


# ---- stocks: real NYSE sessions ---------------------------------------------
def hourly_session(day="2026-10-23", px=100.0):
    s = StockSessions()
    o, c = s.bounds(day)
    idx = pd.date_range(o, c, freq="1h", inclusive="left")
    return s, pd.DataFrame({"open": px, "high": px * 1.001, "low": px * 0.999, "close": px, "volume": 1e6}, index=idx)


def stock_engine(plan, **lim):
    s = StockSessions()
    L = IntradayLimits(market="stocks", **lim)
    return Engine(L, [Scripted(plan)], {"X": Costs(0.0005, 0.0003)}, s, 10_000.0), s


def test_stock_positions_flattened_at_session_close_even_without_exit_rule():
    s, df = hourly_session()
    first_end = df.index[0] + timedelta(hours=1)
    eng, _ = stock_engine({first_end.to_pydatetime(): [sig(setup="X", symbol="AAPL", weight=0.2,
                                                           features={"price": 100, "dollar_volume": 1e9})]})
    replay_bars(eng, {"AAPL": df}, timedelta(hours=1), s)
    (t,) = eng.trades
    assert t.exit_reason == "session_close" and t.exit_time == s.bounds("2026-10-23")[1]


def test_half_day_close_respected():
    s = StockSessions()
    o, c = s.bounds("2026-11-27")                                   # day after Thanksgiving: 13:00 ET close
    assert (c - o) == timedelta(hours=3, minutes=30)


def test_stock_entry_rules_liquidity_price_and_close_proximity():
    s, df = hourly_session()
    close = s.bounds("2026-10-23")[1]
    plan = {(df.index[0] + timedelta(hours=1)).to_pydatetime(): [
                sig(symbol="ILLQ", weight=0.1, features={"price": 50, "dollar_volume": 1e6}),
                sig(symbol="PENY", weight=0.1, features={"price": 3, "dollar_volume": 1e9})],
            close - timedelta(minutes=10): [sig(symbol="LATE", weight=0.1, features={"price": 50, "dollar_volume": 1e9})]}
    eng, _ = stock_engine(plan)
    t1 = (df.index[0] + timedelta(hours=1)).to_pydatetime()
    for sym in ("ILLQ", "PENY"):
        eng.process_bar(t1 - timedelta(hours=1), t1, {sym: Bar(50, 50, 50, 50)}, Ctx(s))
    eng.process_bar(close - timedelta(minutes=40), close - timedelta(minutes=10), {"LATE": Bar(50, 50, 50, 50)}, Ctx(s))
    reasons = {d.symbol: " ".join(d.reasons) for d in eng.decisions}
    assert "liquidity" in reasons["ILLQ"] and "below" in reasons["PENY"] and "close" in reasons["LATE"]


def test_pdt_guard_when_broker_enforces_it():
    s = StockSessions()
    days = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"]
    plan = {}
    for d in days:
        o, _ = s.bounds(d)
        plan[(o + timedelta(hours=1))] = [sig(symbol="AAPL", weight=0.1, features={"price": 100, "dollar_volume": 1e9})]
    eng, _ = stock_engine(plan, pdt_max_day_trades_5d=3)
    frames = []
    for d in days:
        _, df = hourly_session(d)
        frames.append(df)
    replay_bars(eng, {"AAPL": pd.concat(frames)}, timedelta(hours=1), s)
    assert len(eng.trades) == 3
    assert any("day-trade count" in r for d in eng.decisions for r in d.reasons)


def test_daily_pnl_matches_trades_when_flat_each_day():
    s, df = hourly_session()
    first_end = (df.index[0] + timedelta(hours=1)).to_pydatetime()
    df2 = df.copy()
    df2.loc[df2.index[-1], "close"] = 102.0
    eng, _ = stock_engine({first_end: [sig(symbol="AAPL", weight=0.2, features={"price": 100, "dollar_volume": 1e9})]})
    replay_bars(eng, {"AAPL": df2}, timedelta(hours=1), s)
    assert daily_pnl(eng, s).iloc[-1] == pytest.approx(eng.trades[0].net_pnl / 10_000)


def test_missing_liquidity_history_is_rejected_not_passed():
    """Regression (S2 cross-check): a NaN 20-day dollar volume (new listing) slipped through as liquid."""
    s, df = hourly_session()
    t1 = (df.index[0] + timedelta(hours=1)).to_pydatetime()
    eng, _ = stock_engine({t1: [sig(symbol="NEW", weight=0.1, features={"price": 50, "dollar_volume": float("nan")})]})
    eng.process_bar(t1 - timedelta(hours=1), t1, {"NEW": Bar(50, 50, 50, 50)}, Ctx(s))
    (d,) = eng.decisions
    assert d.outcome == "rejected" and "liquidity" in " ".join(d.reasons)


def test_resting_limit_fills_at_limit_not_better_on_gap():
    """Regression (crypto cross-check): a resting buy limit was filled at a lower bar open. A resting
    order fills at its own price when the market trades down through it."""
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(entry="limit", limit=99.0, weight=0.5,
                                                         limit_valid_until=T0 + timedelta(hours=1))]})
    step(eng, 0, {"BTC-USD": Bar(100, 100, 100, 100)})
    step(eng, 1, {"BTC-USD": Bar(97, 98, 96, 97)})               # gaps below the limit
    assert eng.s.positions["BTC-USD"].entry_px == 99.0
