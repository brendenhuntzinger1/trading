"""F5 mechanics: RSI(2) matches a hand computation; the decision uses the 15:45 price, not the close; a position
entered at the close of t earns from t+1; exits after at most 10 sessions."""
import numpy as np
import pandas as pd
import pytest

from research.phase2 import f5_rsi2_pullback as f5


def test_rsi2_wilder_by_hand():
    # changes +1, -1, -2: avg gain/loss start (1, 1)/2... -> ag=(0.5+0)/2=0.25, al=(0.5+2)/2=1.25
    assert f5.rsi2_with(np.array([10.0, 11.0, 10.0]), 8.0) == pytest.approx(100 - 100 / (1 + 0.25 / 1.25))


def test_entry_at_close_earns_from_next_session_and_max_hold():
    idx = pd.bdate_range("2020-01-01", periods=30)
    close = np.r_[np.linspace(100, 110, 15), [105, 100] + list(np.full(13, 100.0))]
    t = pd.DataFrame({"close": close, "p_dec": close, "high": close + 0.1}, index=idx)
    pos = f5.positions(t, {"entry_rsi": 10, "exit": "above_prev_high", "trend": False})
    first = int(np.argmax(pos.to_numpy() > 0))
    assert pos.iloc[:first].sum() == 0 and first >= 16          # signal at the close of the dip, held after
    runs, cur = [], 0
    for v in pos.to_numpy():
        cur = cur + 1 if v else 0
        runs.append(cur)
    assert max(runs) == f5.MAX_HOLD                             # flat prices: held exactly 10 sessions, then exit


def test_decision_uses_the_1545_price_not_the_close():
    idx = pd.bdate_range("2020-01-01", periods=20)
    close = np.r_[np.linspace(100, 110, 16), [100, 100, 100, 100]]
    p_dec = close.copy(); p_dec[16] = 111                        # at 15:45 the dip had not happened yet
    t = pd.DataFrame({"close": close, "p_dec": p_dec, "high": close + 0.1}, index=idx)
    pos = f5.positions(t, {"entry_rsi": 10, "exit": "above_prev_high", "trend": False})
    assert pos.iloc[17] == 0                                    # no entry at day 16's close
