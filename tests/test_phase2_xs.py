"""Cross-sectional framework: no look-ahead (weights entered the session after the signal), eligibility uses
only trailing raw data, funds excluded by name, control is the equal-weight eligible set."""
import numpy as np
import pandas as pd

from research.phase2 import xs

IDX = pd.bdate_range("2020-01-01", periods=80)


def _panel():
    rng = np.random.default_rng(1)
    px = pd.DataFrame(50 * np.exp(np.cumsum(rng.normal(0, 0.01, (80, 4)), axis=0)), index=IDX, columns=list("ABCD"))
    vol = pd.DataFrame(1e6, index=IDX, columns=list("ABCD"))
    vol["D"] = 1e3                                         # illiquid
    return px, vol


def test_eligibility_needs_history_price_and_dollar_volume():
    px, vol = _panel()
    ok, dvol = xs.eligibility(px, vol)
    assert not ok.iloc[:59].any().any()                    # < 60 sessions of history
    assert ok.iloc[-1][["A", "B", "C"]].all() and not ok.iloc[-1]["D"]


def test_signal_at_t_is_held_from_the_next_session():
    px, vol = _panel()
    ok, _ = xs.eligibility(px, vol)
    score = px.pct_change()
    w = xs.select_weights(score, ok, 1)
    t = IDX[70]
    loser = score.loc[t].where(ok.loc[t]).idxmin()
    assert w.loc[IDX[71], loser] == 1.0 and w.loc[t].sum() <= 1.0
    # changing the future does not change the weight decided at t
    px2 = px.copy(); px2.iloc[72:] *= 3
    w2 = xs.select_weights(px2.pct_change(), ok, 1)
    assert w2.loc[IDX[71]].equals(w.loc[IDX[71]])


def test_funds_are_excluded_by_name():
    m = [{"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust"}, {"symbol": "AAPL", "name": "Apple Inc. Common Stock"},
         {"symbol": "TQQQ", "name": "ProShares UltraPro QQQ"}]
    assert xs.operating_companies(m) == {"AAPL"}


def test_control_is_equal_weight_over_eligible_names_next_session():
    px, vol = _panel()
    ok, _ = xs.eligibility(px, vol)
    c = xs.control_weights(ok)
    assert c.loc[IDX[71]].sum() == 1.0 and c.loc[IDX[71], "D"] == 0.0
