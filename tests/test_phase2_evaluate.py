"""Phase-2 evaluation: turnover-based costs (holding is free, trading pays), protocol criteria on known inputs."""
import numpy as np
import pandas as pd
import pytest

from research.phase2 import evaluate as ev

IDX = pd.bdate_range("2020-01-01", periods=5)


def test_holding_is_free_and_trading_pays_spread_slippage_and_fees():
    w = pd.DataFrame({"A": [0.5, 0.5, 0, 0, 0], "B": [0, 0.5, 0.5, 0.5, 0]}, index=IDX)
    r = pd.DataFrame({"A": [0.01, 0.0, 0.02, 0, 0], "B": [0, 0.01, -0.01, 0.0, 0]}, index=IDX)
    hs = pd.DataFrame(2e-4, index=IDX, columns=["A", "B"])
    p = ev.backtest_weights(w, r, hs)
    unit = 2e-4 + ev.SLIP_BASE + ev.FEES_PER_SIDE
    assert p.gross.tolist() == pytest.approx([0.005, 0.005, -0.005, 0.0, 0.0])
    # day 2: A drifted 0.5*1.01/1.005 -> rebalanced to 0.5 (tiny trade); B bought 0.5
    assert p.turnover.iloc[1] == pytest.approx(0.5 * 1.01 / 1.005 - 0.5 + 0.5)
    assert p.cost.iloc[1] == pytest.approx(p.turnover.iloc[1] * unit)
    assert p.turnover.iloc[3] == pytest.approx(0.5 - 0.5 * 0.99 / 0.995)        # holding B: drift only


def test_unknown_spread_is_penalised_not_free():
    w = pd.DataFrame({"A": [1.0, 0, 0, 0, 0]}, index=IDX)
    p = ev.backtest_weights(w, pd.DataFrame({"A": [0.0] * 5}, index=IDX), pd.DataFrame(index=IDX, columns=["A"]))
    assert p.cost.iloc[0] == pytest.approx(10e-4 + ev.SLIP_BASE + ev.FEES_PER_SIDE)


def test_dev_criteria_need_control_beating_years_concentration_and_stress():
    idx = pd.bdate_range("2020-01-01", "2022-12-30")
    rng = np.random.default_rng(0)
    net = pd.Series(rng.normal(5e-4, 5e-3, len(idx)), index=idx)
    pnl = pd.DataFrame({"gross": net + 1e-4, "cost": 1e-4, "net": net, "turnover": 0.2, "n_pos": 10, "exposure": 1.0})
    s = ev.summarise(pnl, pd.Series(0.0, index=idx), pd.Series(0.0, index=idx), net - 1e-4)
    q = ev.dev_qualifies(s)
    assert q["qualified"] and s["vs_control_net_bp"]["ci"][0] > 0
    s2 = ev.summarise(pnl, net, net, net - 1e-4)          # identical to its control: no skill
    assert not ev.dev_qualifies(s2)["D1"]


def test_measured_band_medians_replace_the_tier_with_fallback():
    idx = pd.bdate_range("2020-01-01", periods=1)
    cols = [f"S{i}" for i in range(150)]
    dvol = pd.DataFrame([np.linspace(5e9, 3e7, 150)], index=idx, columns=cols)   # ranks 1..150
    sample = {"09:31|1-100": {"n": 50, "median_bp": 1.2}, "09:31|101-200": {"n": 5, "median_bp": 9.0}}
    hs = ev.measured_half_spread(dvol, dvol > 0, "09:31", sample=sample)
    assert hs.loc[idx[0], "S0"] == pytest.approx(1.2e-4)            # band 1-100, measured
    assert hs.loc[idx[0], "S99"] == pytest.approx(1.2e-4)
    tier = ev.tier_half_spread(dvol).loc[idx[0], "S149"]
    assert hs.loc[idx[0], "S149"] == pytest.approx(tier)            # band 101-200 has n < 30: tier fallback
