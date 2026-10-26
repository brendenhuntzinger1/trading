import numpy as np
import pandas as pd
import pytest

from tradelab.predict.models import Spec, fit_predict
from tradelab.predict.panel import FAMILIES, build_panel, _labels


def bars(n=24 * 60, seed=0, drift=0.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    r = np.random.default_rng(seed).normal(drift, 0.01, n)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.002, "low": np.minimum(o, c) * 0.998, "close": c,
                         "volume": 1000.0}, index=idx)


def test_features_do_not_see_the_entry_bar_or_future():
    b = {"BTC-USD": bars(seed=1), "AAA-USD": bars(seed=2)}
    full = build_panel(b, [0, 12], horizon=24)
    t = full.decision_time.iloc[len(full) // 2]
    cut = {s: d[d.index + pd.Timedelta(hours=1) <= t] for s, d in b.items()}   # only bars ended by t
    part = build_panel(cut, [0, 12], horizon=24)
    cols = [c for fam in FAMILIES.values() for c in fam]
    a = full[full.decision_time == t].set_index("symbol")[cols]
    p = part[part.decision_time == t].set_index("symbol")[cols]
    pd.testing.assert_frame_equal(a.sort_index(), p.sort_index(), check_exact=False, rtol=1e-9)


def test_labels_enter_at_next_open_and_stop_wins_ties():
    d = bars(n=300, seed=3)
    lab = _labels(d, horizon=4, barrier_sd=1.0)
    i = 200
    assert lab.fwd_ret.iloc[i] == pytest.approx(d.close.iloc[i + 3] / d.open.iloc[i] - 1)
    d2 = d.copy()
    d2.iloc[i, d2.columns.get_loc("high")] = d2.open.iloc[i] * 1.5     # both barriers hit in the entry bar
    d2.iloc[i, d2.columns.get_loc("low")] = d2.open.iloc[i] * 0.5
    lab2 = _labels(d2, horizon=4, barrier_sd=1.0)
    assert lab2.stop_first.iloc[i] == 1 and lab2.target_first.iloc[i] == 0
    assert (lab.label_end - lab.index == pd.Timedelta(hours=4)).all()


def test_model_ladder_runs_and_baselines_are_trivial():
    b = {f"S{i}-USD": bars(seed=i) for i in range(6)}
    p = build_panel(b, [0, 6, 12, 18], horizon=24).dropna(subset=["fwd_ret"])
    tr, te = p.iloc[: len(p) // 2], p.iloc[len(p) // 2:]
    feats = [c for fam in FAMILIES.values() for c in fam if c in p]
    assert (fit_predict(Spec("z", "zero", "fwd_ret"), tr, te) == 0).all()
    for spec in (Spec("r", "ridge", "fwd_ret", feats), Spec("g", "gbt_reg", "fwd_ret", feats),
                 Spec("l", "logit", "target_first", feats), Spec("c", "gbt_clf", "target_first", feats)):
        out = fit_predict(spec, tr.dropna(subset=[spec.target]), te)
        assert len(out) == len(te) and np.isfinite(out).all()
