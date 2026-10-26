import numpy as np
import pandas as pd
import pytest

from tradelab.data.candles import load
from tradelab.research.engine import CostModel, simulate
from tradelab.research.gate import estimate, forward_return, walk_forward_gate
from tradelab.research.walkforward import walk_forward, yearly_splits
from tradelab.strategies import trend
from tradelab.strategies.breakout import breakout
from tradelab.strategies.fixed import fixed
from tradelab.strategies.meanrev import meanrev
from tradelab.strategies.regime import _apply_choices, regime_selector
from tradelab.strategies.relative import eligible, rotation_weights


@pytest.fixture(scope="module")
def btc():
    return load("BTC-USD", "1d")


@pytest.mark.parametrize("spec", [fixed(0.3), breakout(50, 3.0), breakout(20, 2.0), meanrev(200, 2, 10.0, 10)])
def test_new_strategies_never_use_future_bars(btc, spec):
    full = spec(btc)
    for cut in [400, 1500, 2600, len(btc) - 20]:
        assert spec(btc.iloc[: cut + 1]).iloc[-1] == pytest.approx(full.iloc[cut]), spec.name


@pytest.mark.parametrize("spec", [breakout(50, 3.0), meanrev(200, 2, 10.0, 10)])
def test_signals_are_long_only_unlevered(btc, spec):
    s = spec(btc)
    assert s.min() >= 0 and s.max() <= 1


def test_meanrev_does_not_average_down(btc):
    s = meanrev(200, 2, 30.0, 10)(btc)
    # once in a trade the size never increases until it is flat again
    in_trade = s > 0
    grows = (s.diff() > 0) & in_trade.shift(1, fill_value=False)
    assert not grows.any()


def _panel():
    idx = pd.date_range("2020-01-01", periods=900, freq="D", tz="UTC")
    rng = np.random.default_rng(1)
    close = pd.DataFrame(np.exp(np.cumsum(rng.normal(0, 0.03, (900, 4)), axis=0)) * 10, index=idx, columns=list("ABCD"))
    close.loc[: idx[500], "D"] = np.nan          # listed later
    close.loc[idx[700]:, "C"] = np.nan           # delisted
    vol = pd.DataFrame(1e7, index=idx, columns=close.columns)
    return close, vol


def test_rotation_point_in_time_and_eligibility():
    close, vol = _panel()
    w = rotation_weights(close, vol, close["A"], lookback=30, top_k=2, rebalance_days=7, market_filter=False)
    el = eligible(close, vol)
    assert not ((~el) & (w != 0)).any().any()             # never holds ineligible coins
    assert (w.sum(axis=1) <= 1 + 1e-9).all()
    assert (w.loc[: close.index[500 + 364], "D"] == 0).all()  # needs a year of history first
    cut = 800
    w2 = rotation_weights(close.iloc[: cut + 1], vol.iloc[: cut + 1], close["A"].iloc[: cut + 1], 30, 2, 7, False)
    pd.testing.assert_series_equal(w2.iloc[-1], w.iloc[cut], check_names=False)


def test_walk_forward_picks_using_training_data_only():
    idx = pd.date_range("2018-01-01", "2021-12-31", freq="D", tz="UTC")
    good_early = pd.Series(np.where(idx.year < 2020, 0.002, -0.002), index=idx) + np.random.default_rng(0).normal(0, 0.01, len(idx))
    good_late = -good_early
    res = walk_forward({0: good_early, 1: good_late}, None, yearly_splits(2020, 2021))
    assert res.chosen[0][1] == 0     # in 2020 only 2018-19 is visible, where config 0 looked better
    assert res.returns.index.min() == pd.Timestamp("2020-01-01", tz="UTC")


def test_gate_estimates_are_unchanged_by_data_after_the_test_year(btc):
    vote = trend.trend_vote(btc)
    vol = trend.realized_vol(btc)
    a, _ = walk_forward_gate(btc, vote, vol, 20, 0.0132, [2021])
    shocked = btc.copy()
    shocked.loc["2022-01-01":, ["open", "high", "low", "close"]] *= 5
    b, _ = walk_forward_gate(shocked, trend.trend_vote(shocked), trend.realized_vol(shocked), 20, 0.0132, [2021])
    pd.testing.assert_series_equal(a.loc["2021"], b.loc["2021"])


def test_gate_rejects_states_whose_lower_bound_is_below_cost():
    idx = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC")
    fwd = pd.Series(0.005, index=idx) + np.random.default_rng(0).normal(0, 0.05, 400)
    st = pd.Series("s", index=idx)
    est = estimate(fwd, st, 20, cost_round_trip=0.0132)
    assert not est["s"].approved     # +0.5% mean edge is below the 1.32% round-trip cost


def test_selector_charges_switching_cost():
    idx = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    rets = pd.DataFrame({"a": 0.0, "cash": 0.0}, index=idx)
    expo = pd.DataFrame({"a": 1.0, "cash": 0.0}, index=idx)
    choice = pd.Series(["cash", "a", "a", "cash", "cash"], index=idx)
    r = _apply_choices(choice, rets, expo, 0.01)
    assert r.sum() == pytest.approx(-0.02)   # one switch in, one switch out
