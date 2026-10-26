from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from tradelab.data.live.analytics import realized_vol, rolling_corr
from tradelab.data.live.bars import build_bars
from tradelab.data.live.recorder import Recorder, read_trades
from tradelab.data.live.types import Trade

T0 = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)
M = timedelta(minutes=1)


def tr(i, sec, price, recv_delay_s=0.1, size=1.0):
    t = T0 + timedelta(seconds=sec)
    return Trade("coinbase", "BTC-USD", str(i), price, size, "buy", t, t + timedelta(seconds=recv_delay_s))


def test_bars_use_only_trades_received_by_bar_end():
    trades = [tr(1, 5, 100), tr(2, 50, 102), tr(3, 59, 105, recv_delay_s=3),  # arrives after 18:01:00
              tr(4, 70, 101)]
    bars = build_bars(trades, M, T0, T0 + 2 * M)
    b0 = bars.iloc[0]
    assert (b0.open, b0.high, b0.close, b0.trades, b0.late_trades) == (100, 102, 102, 2, 1)
    assert bars.index[0] + M == b0.available_at
    assert b0.received_at <= b0.available_at                # never uses information from after the bar


def test_grace_period_is_explicit():
    trades = [tr(1, 59, 105, recv_delay_s=3)]
    assert build_bars(trades, M, T0, T0 + M).iloc[0].trades == 0
    with_grace = build_bars(trades, M, T0, T0 + M, grace=timedelta(seconds=5)).iloc[0]
    assert with_grace.trades == 1 and with_grace.available_at == T0 + M + timedelta(seconds=5)


def test_empty_bars_are_visible_not_filled():
    bars = build_bars([tr(1, 5, 100), tr(2, 125, 101)], M, T0, T0 + 3 * M)
    assert bars.trades.tolist() == [1, 0, 1] and np.isnan(bars.close.iloc[1])


def test_vwap():
    b = build_bars([tr(1, 1, 100, size=1), tr(2, 2, 110, size=3)], M, T0, T0 + M).iloc[0]
    assert b.vwap == pytest.approx(107.5)


def test_recorder_round_trip(tmp_path):
    rec = Recorder(tmp_path)
    for t in [tr(1, 5, 100), tr(2, 6, 101)]:
        rec.write(t)
    rec.close()
    back = list(read_trades("coinbase", "BTC-USD", tmp_path))
    assert back == [tr(1, 5, 100), tr(2, 6, 101)]


def test_realized_vol_and_correlation():
    idx = pd.date_range(T0, periods=200, freq="1min")
    rng = np.random.default_rng(0)
    x = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, 200)))
    a = pd.DataFrame({"close": x, "trades": 1}, index=idx)
    b = pd.DataFrame({"close": x ** 2 / 100, "trades": 1}, index=idx)   # perfectly co-moving
    v = realized_vol(a, 60, 525600)
    assert v.iloc[-1] == pytest.approx(0.001 * np.sqrt(525600), rel=0.25)
    c = rolling_corr({"A": a, "B": b}, 60)
    assert c["A|B"].iloc[-1] == pytest.approx(1.0)


def test_realized_vol_refuses_to_bridge_empty_bars():
    idx = pd.date_range(T0, periods=10, freq="1min")
    a = pd.DataFrame({"close": np.linspace(100, 101, 10), "trades": [1] * 5 + [0] + [1] * 4}, index=idx)
    assert realized_vol(a, 3, 525600).iloc[5:8].isna().all()


def test_unaligned_start_still_buckets_trades():
    """Regression: a start time that is not on a bar boundary used to yield all-empty bars."""
    trades = [tr(1, 5, 100), tr(2, 65, 101)]
    bars = build_bars(trades, M, T0 + timedelta(seconds=3.7), T0 + 2 * M)
    assert bars.trades.tolist() == [1, 1] and bars.index[0] == T0
