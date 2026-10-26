"""F1 mechanics on a synthetic panel: losers chosen at t are bought at the open of t+1; an unfilled open keeps
cash; a held name without a next open exits at its last close; stress-only trades only in stress."""
import numpy as np
import pandas as pd

from research.phase2 import f1_reversal as f1


def test_exit_without_next_open_uses_last_close():
    idx = pd.bdate_range("2020-01-01", periods=3)
    o = pd.DataFrame({"A": [10.0, 11.0, np.nan]}, index=idx)
    c = pd.DataFrame({"A": [10.5, 12.0, np.nan]}, index=idx)
    r = f1.open_to_open_with_exit({"open": o, "close": c})
    assert r.loc[idx[0], "A"] == 11.0 / 10.0 - 1 and r.loc[idx[1], "A"] == 12.0 / 11.0 - 1


def test_unfilled_open_keeps_cash_and_stress_filter_zeroes_calm_days():
    idx = pd.bdate_range("2020-01-01", periods=4)
    cols = list("ABC")
    sig = pd.DataFrame([[-0.1, 0.0, 0.1]] * 4, index=idx, columns=cols)
    elig = pd.DataFrame(True, index=idx, columns=cols)
    opens = pd.DataFrame(1.0, index=idx, columns=cols)
    opens.loc[idx[2], "A"] = np.nan
    f = {"r1_mkt": sig, "vol_ratio": sig * 0, "stress": pd.Series([True, False, True, True], index=idx)}
    w = f1.weights({"signal": "r1_mkt", "no_news": False, "stress_only": False}, f, elig, opens)
    assert w.loc[idx[1], "A"] == 1 / f1.N and w.loc[idx[2], "A"] == 0.0     # A did not open on idx[2]
    ws = f1.weights({"signal": "r1_mkt", "no_news": False, "stress_only": True}, f, elig, opens)
    assert ws.loc[idx[2]].sum() == 0.0                                       # decided on calm idx[1]
    assert ws.loc[idx[1], "A"] == 1 / f1.N                                   # decided on stressed idx[0]
