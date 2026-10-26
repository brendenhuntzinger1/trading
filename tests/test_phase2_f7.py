"""F7 point-in-time features: at 15:30 of t only p (the 15:30 price) and data through t-1 are used; the label
is close t -> close t+1."""
import numpy as np
import pandas as pd

from research.phase2 import f7_ml_close as f7


def test_features_use_only_the_1530_price_and_prior_closes():
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(0)
    cols = ["A", "B", "SPY"]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (300, 3)), axis=0)), index=idx, columns=cols)
    a = {"open": close * 0.999, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": close * 0 + 1e6}
    r = {"close": close, "volume": a["volume"]}
    p = close * 1.001
    f = f7.features_at_1530(a, r, cols, p)
    t = idx[200]
    a2 = {k: v.copy() for k, v in a.items()}
    a2["close"].loc[t] *= 5                                     # today's close is unknown at 15:30
    f2 = f7.features_at_1530(a2, {"close": a2["close"], "volume": a2["volume"]}, cols, p)
    for k in f:
        assert np.allclose(f[k].loc[t].to_numpy(dtype=float), f2[k].loc[t].to_numpy(dtype=float), equal_nan=True), k
    assert np.isclose(f["r1"].loc[t, "A"], p.loc[t, "A"] / close.shift(1).loc[t, "A"] - 1)
