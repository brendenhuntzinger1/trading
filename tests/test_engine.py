import numpy as np
import pandas as pd
import pytest

from tradelab.research.engine import CostModel, ExecModel, simulate


def _px(vals):
    idx = pd.date_range("2024-01-01", periods=len(vals), freq="D", tz="UTC")
    s = pd.DataFrame({"A": vals}, index=idx, dtype=float)
    return s, s.copy()


def test_buy_and_hold_tracks_price_minus_one_fee():
    close, fill = _px([100, 100, 110, 121])
    tgt = pd.DataFrame({"A": 1.0}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(fee=0.01, half_spread=0, slippage=0))
    # buys at bar 1 open (100) with 1000/(1.01); ends at 121
    assert r.equity.iloc[-1] == pytest.approx(1000 / 1.01 * 1.21)
    assert len(r.trades) == 1


def test_trades_execute_next_bar_not_same_bar():
    close, fill = _px([100, 200, 200])
    fill.iloc[1, 0] = 150   # bar 1 opens at 150 then closes 200
    tgt = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(fee=0, half_spread=0, slippage=0))
    assert r.trades.price.iloc[0] == 150
    assert r.equity.iloc[0] == 1000          # nothing held during bar 0


def test_weights_drift_and_rebalance_is_charged():
    close, fill = _px([100, 100, 200, 200])
    tgt = pd.DataFrame({"A": 0.5}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(fee=0.01, half_spread=0, slippage=0))
    assert len(r.trades) == 2               # initial buy + rebalance after the doubling, no dust trades
    assert r.trades.notional.iloc[1] < 0


def test_zero_band_churns_dust_trades():
    """Documents why the default band exists: fee drift re-triggers tiny trades forever."""
    close, fill = _px([100, 100, 200, 200, 200, 200])
    tgt = pd.DataFrame({"A": 0.5}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(fee=0.01, half_spread=0, slippage=0, min_notional=0), ExecModel(band=0))
    assert len(r.trades) > 3
    assert r.trades.notional.iloc[1] < 0


def test_band_suppresses_small_rebalances_but_not_exits():
    close, fill = _px([100, 100, 104, 104, 104])
    tgt = pd.DataFrame({"A": [0.5, 0.5, 0.5, 0.0, 0.0]}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(fee=0, half_spread=0, slippage=0), ExecModel(band=0.05))
    assert list(np.sign(r.trades.notional)) == [1, -1]


def test_cannot_spend_more_than_cash_or_lever():
    close, fill = _px([100, 100])
    with pytest.raises(ValueError):
        simulate(pd.concat([close, close.rename(columns={"A": "B"})], axis=1),
                 pd.concat([fill, fill.rename(columns={"A": "B"})], axis=1),
                 pd.DataFrame({"A": 0.7, "B": 0.7}, index=close.index))


def test_min_notional_skips_dust_orders():
    close, fill = _px([100, 100, 100])
    tgt = pd.DataFrame({"A": 0.0005}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(min_notional=1.0))
    assert r.trades.empty


def test_missing_close_carries_last_price_not_zero():
    """Regression: a held asset was valued at $0 on bars with no close (exchange gap)."""
    close, fill = _px([100, 100, 100, 100])
    close.iloc[2, 0] = np.nan
    fill.iloc[2, 0] = np.nan
    tgt = pd.DataFrame({"A": 1.0}, index=close.index)
    r = simulate(close, fill, tgt, 1000, CostModel(fee=0, half_spread=0, slippage=0))
    assert r.equity.min() == pytest.approx(1000)
