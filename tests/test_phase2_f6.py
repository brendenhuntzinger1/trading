"""F6 leakage guards: the label is the session AFTER entry (t+1 open -> t+2 open) and never feeds features;
a model predicting year Y is fitted only on earlier years."""
import numpy as np
import pandas as pd

from research.phase2 import f6_ml_rank as f6


def _toy():
    idx = pd.bdate_range("2016-01-01", "2018-12-31")
    rng = np.random.default_rng(0)
    cols = [f"S{i}" for i in range(30)]
    target = pd.DataFrame(rng.normal(0, 0.01, (len(idx), 30)), index=idx, columns=cols)
    feat = {"r1": pd.DataFrame(rng.normal(size=(len(idx), 30)), index=idx, columns=cols)}
    elig = pd.DataFrame(True, index=idx, columns=cols)
    return idx, target, feat, elig


def test_label_is_next_session_return_and_features_are_untouched_by_it():
    idx, target, feat, elig = _toy()
    d = f6.long_frame(feat, target, elig)
    t = idx[10]
    row = target.shift(-1).loc[t]
    dem = row - row.mean()
    assert np.allclose(d.loc[t, "y_dem"].to_numpy(), dem.reindex(d.loc[t].index).to_numpy(), atol=1e-6)
    target2 = target.copy(); target2.iloc[11:] = 0.5
    assert d["r1"].equals(f6.long_frame(feat, target2, elig)["r1"])


def test_walk_forward_trains_only_on_earlier_years(monkeypatch):
    idx, target, feat, elig = _toy()
    d = f6.long_frame(feat, target, elig)
    seen = {}

    class Spy:
        def __init__(self, **k): pass
        def fit(self, X, y): seen["n"] = len(X); return self
        def predict(self, X): return np.zeros(len(X))
    monkeypatch.setattr(f6, "Ridge", lambda alpha: Spy())
    f6.fit_predict(d, ["r1"], "ridge", 2018)
    n_before = int((d.index.get_level_values(0).year < 2018).sum() - d[d.index.get_level_values(0).year < 2018]["y_rank"].isna().sum())
    assert seen["n"] == n_before
