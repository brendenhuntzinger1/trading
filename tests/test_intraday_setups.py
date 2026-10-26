"""Setups may only use bars that ended at or before the decision time."""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from tradelab.intraday.replay import Ctx
from tradelab.intraday.sessions import StockSessions
from tradelab.intraday.setups import C1CascadeReversal, C2IntradayMomentum, S1IntradayMomentum, S2GapReversal


def crypto5(n_days=60, seed=1, crash_at=None):
    idx = pd.date_range("2024-01-01", periods=n_days * 288, freq="5min", tz="UTC")
    r = np.random.default_rng(seed).normal(0, 0.002, len(idx))
    if crash_at is not None:
        r[crash_at:crash_at + 12] = -0.01                       # ~ -11% over one hour
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.0005, "low": np.minimum(o, c) * 0.9995, "close": c, "volume": 1.0}, index=idx)


def signals_over(setup_cls, df, times, **kw):
    s = setup_cls({"X": df}, **kw)
    return {t: [(x.symbol, round(x.stop or 0, 8), round(x.target or 0, 8)) for x in s.scan(t, None)] for t in times}


@pytest.mark.parametrize("cls", [C1CascadeReversal, C2IntradayMomentum])
def test_crypto_setups_ignore_the_future(cls):
    crash = 288 * 45 + 12 * 7                                   # day 45, 07:00
    full = crypto5(crash_at=crash)
    times = [ts.to_pydatetime() for ts in full.index[288 * 40::12][:200]]
    a = signals_over(cls, full, times)
    assert any(a.values()), "test is vacuous unless the setup actually fires"
    for t in times[::25]:
        cut = full[full.index + pd.Timedelta(minutes=5) <= t]   # only bars that had ended by t
        b = signals_over(cls, cut, [t])
        assert a[t] == b[t], f"{cls.__name__} signal at {t} changes when later bars are removed"


def test_c1_fires_on_the_crash_hour():
    full = crypto5(crash_at=288 * 45 + 12 * 7)
    s = C1CascadeReversal({"X": full})
    t = (full.index[288 * 45 + 12 * 8]).to_pydatetime()         # end of the crash hour
    (sig,) = s.scan(t, None)
    assert sig.stop < sig.features["price"] < sig.target and sig.deadline == t + timedelta(hours=6)


def stock_hourly(days, seed=2):
    s = StockSessions()
    frames, rng, px = [], np.random.default_rng(seed), 100.0
    for d in days:
        o, c = s.bounds(d)
        idx = pd.date_range(o, c, freq="1h", inclusive="left")
        r = rng.normal(0, 0.004, len(idx))
        cl = px * np.exp(np.cumsum(r))
        op = np.r_[px, cl[:-1]]
        frames.append(pd.DataFrame({"open": op, "high": np.maximum(op, cl), "low": np.minimum(op, cl), "close": cl, "volume": 1e6}, index=idx))
        px = cl[-1]
    return s, pd.concat(frames)


def test_s1_ignores_the_future():
    sess = StockSessions()
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", "2026-04-30") if sess.bounds(d.strftime("%Y-%m-%d"))]
    s, df = stock_hourly(days)
    full = S1IntradayMomentum({"A": df}, s, threshold=0.0)
    fired = 0
    for d in days[30::10]:
        b = s.bounds(d)
        if not b:
            continue
        t = b[1] - timedelta(minutes=30)
        cut = S1IntradayMomentum({"A": df[df.index + pd.Timedelta(hours=1) <= t]}, s, threshold=0.0)
        got = [x.reason for x in full.scan(t, None)]
        assert got == [x.reason for x in cut.scan(t, None)]
        fired += bool(got)
    assert fired >= 2, "test is vacuous unless the setup actually fires"


def test_s2_uses_previous_close_and_todays_open_only():
    idx = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=30)]
    mk = lambda c: pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1e7}, index=idx)
    spy, a = mk(np.full(30, 100.0)), mk(np.full(30, 50.0))
    s = S2GapReversal({"SPY": spy, "A": a})
    sess = StockSessions()
    t = sess.bounds(idx[25])[0]
    (sig,) = s.scan_open(t, {"SPY": 100.0, "A": 49.0}, Ctx(sess))       # -2% gap vs flat market
    assert sig.symbol == "A" and "-2.00%" in sig.reason and sig.entry == "at_open"
    a2 = a.copy(); a2.loc[idx[26]:, "close"] = 999.0                  # changing later days changes nothing
    s2 = S2GapReversal({"SPY": spy, "A": a2})
    assert [x.reason for x in s2.scan_open(t, {"SPY": 100.0, "A": 49.0}, Ctx(sess))] == [sig.reason]


def test_s2_ranks_only_eligible_candidates():
    """Regression (S2 cross-check): a sub-$10 stock with the biggest gap took a top-5 slot, was then
    rejected by the engine, and crowded out an eligible candidate."""
    idx = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=30)]
    mk = lambda c, v=1e7: pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": v}, index=idx)
    data = {"SPY": mk(np.full(30, 100.0)), "PENNY": mk(np.full(30, 5.0), 1e9), "THIN": mk(np.full(30, 50.0), 1.0)}
    data.update({f"S{i}": mk(np.full(30, 50.0)) for i in range(6)})
    s = S2GapReversal(data)
    sess = StockSessions()
    t = sess.bounds(idx[25])[0]
    opens = {"SPY": 100.0, "PENNY": 4.0, "THIN": 40.0, **{f"S{i}": 50.0 * (0.98 - 0.001 * i) for i in range(6)}}
    got = [x.symbol for x in s.scan_open(t, opens, Ctx(sess))]
    assert "PENNY" not in got and "THIN" not in got and len(got) == 5
