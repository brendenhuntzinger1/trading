import numpy as np
import pandas as pd
import pytest

from tradelab.intraday.research import crypto_rules as R
from tradelab.intraday.research.crypto_eval import daily, e1_bootstrap

T0 = pd.Timestamp("2022-01-01", tz="UTC")


def bars(n, step, seed=0, start=T0, vol=0.002, shock_at=None, shock=-0.08):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, vol, n)
    if shock_at is not None:
        r[shock_at] = shock
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    idx = pd.date_range(start, periods=n, freq=step)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.0005, "low": np.minimum(o, c) * 0.9995,
                         "close": c, "volume": 1.0}, index=idx)


def test_c1_signals_are_causal():
    h1 = bars(2000, "1h", shock_at=1500)
    full = R.c1_signals(h1, R.C1Config(k=4))
    assert (full.index == h1.index[1500] + R.H1).any(), "the shock must fire"
    for cut in (1400, 1500, 1700):
        part = R.c1_signals(h1.iloc[: cut + 1], R.C1Config(k=4))
        known = full[full.index <= h1.index[cut] + R.H1]
        pd.testing.assert_frame_equal(part, known, check_freq=False)
    shocked = h1.copy()
    shocked.iloc[1600:, :4] *= 0.5                     # wild future must not change earlier signals
    a = R.c1_signals(h1, R.C1Config(k=4)); b = R.c1_signals(shocked, R.C1Config(k=4))
    pd.testing.assert_frame_equal(a[a.index <= h1.index[1599]], b[b.index <= h1.index[1599]], check_freq=False)


def test_c1_sigma_excludes_the_signal_bar():
    h1 = bars(2000, "1h", shock_at=1500)
    s = R.c1_signals(h1, R.C1Config(k=4)).iloc[0]
    r = R.contiguous_returns(h1, R.H1)
    assert s.sigma == pytest.approx(r.iloc[780:1500].std())


def test_c2_signals_are_causal():
    m5 = bars(40 * 288, "5min", seed=3, vol=0.003)
    full = R.c2_signals(m5, R.C2Config(m=0.5))
    assert len(full) > 0
    cut_t = full.index[len(full) // 2]
    part = R.c2_signals(m5[m5.index < cut_t], R.C2Config(m=0.5))
    pd.testing.assert_frame_equal(part, full[full.index <= cut_t])


def test_stop_assumed_first_when_bar_spans_both():
    idx = pd.date_range(T0, periods=3, freq="5min")
    b = pd.DataFrame({"open": [100, 100, 100.0], "high": [100.5, 103, 100], "low": [99.5, 97, 100], "close": [100, 100, 100.0]}, index=idx)
    t, px, why = R.walk_exit(b, idx[0], 100, stop=98, target=102, until=idx[-1] + R.M5)
    assert why == "stop" and px == 98 and t == idx[1]


def test_gap_through_stop_fills_at_open():
    idx = pd.date_range(T0, periods=2, freq="5min")
    b = pd.DataFrame({"open": [100, 95.0], "high": [100.2, 96], "low": [99.8, 94], "close": [100, 95.0]}, index=idx)
    assert R.walk_exit(b, idx[0], 100, stop=98, target=None, until=idx[-1] + R.M5)[1] == 95


def test_maker_touch_is_not_a_fill():
    h1 = bars(1000, "1h", shock_at=900)
    H = h1.index[900] + R.H1
    price = h1.close.iloc[900]
    limit = price * (1 - 0.003)
    m1_idx = pd.date_range(H, periods=420, freq="1min")
    def window(low_at_limit):
        lows = np.full(420, price); lows[3] = limit if low_at_limit else limit * 0.999
        return pd.DataFrame({"open": price, "high": price * 1.0001, "low": lows, "close": price, "volume": 1.0}, index=m1_idx)
    m5 = bars(10, "5min", start=H)
    cfg = R.C1Config(k=4, maker=True)
    touch = R.c1_trades("X", h1, m5, cfg, m1_windows=lambda s, a, b: window(True))
    through = R.c1_trades("X", h1, m5, cfg, m1_windows=lambda s, a, b: window(False))
    assert touch.empty and len(through) == 1
    assert through.entry_px.iloc[0] == pytest.approx(limit) and through.entry_cost.iloc[0] == R.MAKER


def test_costs_and_stress():
    h1 = bars(1000, "1h", shock_at=900)
    H = h1.index[900] + R.H1
    m5 = bars(100, "5min", start=H, vol=0.0001)
    t = R.c1_trades("X", h1, m5, R.C1Config(k=4))
    assert len(t) == 1
    assert t.net_ret.iloc[0] == pytest.approx(t.gross_ret.iloc[0] - 2 * 0.0066)
    assert R.restress(t).net_ret.iloc[0] == pytest.approx(t.net_ret.iloc[0] - 0.003)
    assert t.exit_reason.iloc[0] == "time"
    hold = pd.Timestamp(t.exit_time_utc.iloc[0]) - pd.Timestamp(t.entry_time_utc.iloc[0])
    assert hold == pd.Timedelta(hours=6)


def test_missing_entry_bar_beyond_15_minutes_skips_trade():
    h1 = bars(1000, "1h", shock_at=900)
    H = h1.index[900] + R.H1
    m5 = bars(100, "5min", start=H + pd.Timedelta(minutes=20))        # outage right after the signal
    assert R.c1_trades("X", h1, m5, R.C1Config(k=4)).empty


def test_one_position_per_coin():
    h1 = bars(1000, "1h", shock_at=900)
    h1.iloc[901, :4] = h1.iloc[901, :4] * 0.92                          # second shock while still in the trade
    h1.loc[h1.index[901], "open"] = h1.close.iloc[900]
    H = h1.index[900] + R.H1
    m5 = bars(200, "5min", start=H, vol=0.0001)
    sigs = R.c1_signals(h1, R.C1Config(k=4))
    t = R.c1_trades("X", h1, m5, R.C1Config(k=4))
    assert len(sigs) >= 2 and len(t) == 1


def test_e1_daily_accounting():
    tr = pd.DataFrame({"exit_time_utc": pd.to_datetime(["2024-01-02 03:00", "2024-01-02 05:00", "2024-01-05 00:00"], utc=True),
                       "net_ret": [0.01, -0.02, 0.03], "size_weight": [0.1, 0.2, 0.25]})
    dd = daily(tr, "2024-01-01", "2024-01-10")
    assert len(dd) == 9 and dd.n.sum() == 3
    assert dd.pnl.loc["2024-01-02"] == pytest.approx(0.001 - 0.004)
    mean, lb = e1_bootstrap(dd, n_boot=200)
    assert mean == pytest.approx(0.02 / 3)
