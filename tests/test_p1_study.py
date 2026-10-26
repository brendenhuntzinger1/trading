"""P1 study mechanics: policy accounting (hold/entry/exit/abstain, costs on actual turnover), label timing
with carried-forward prices, and feature causality on the filled hourly grid."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("p1study", Path(__file__).resolve().parents[1] / "research" / "p1" / "study.py")
p1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p1)


def _per(rows):
    return {t: pd.DataFrame(r, columns=["symbol", "score", "pred", "ret"]) for t, r in rows.items()}


T = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")


def test_hold_costs_nothing_and_rotation_costs_turnover():
    rows = {t: [("A", 5, 0, 0.0), ("B", 4, 0, 0.0), ("C", 3, 0, 0.0), ("D", 1, 0, 0.0)] for t in T}
    rows[T[2]] = [("A", 5, 0, 0.0), ("B", 4, 0, 0.0), ("C", 1, 0, 0.0), ("D", 3, 0, 0.0)]   # C out, D in
    res = p1.simulate(_per(rows), T, rt=0.01)
    assert res.cost.iloc[0] == pytest.approx(1.0 * 0.01 / 2)        # buy 3 x 1/3
    assert res.cost.iloc[1] == pytest.approx(0.0)                   # same picks, zero returns -> no trade
    assert res.cost.iloc[2] == pytest.approx((2 / 3) * 0.01 / 2)     # sell C 1/3, buy D 1/3
    assert res.turnover.iloc[2] == pytest.approx(1 / 3)
    te = p1.simulate(_per(rows), T, rt=0.01, time_exit=True)
    assert te.cost.iloc[1] == pytest.approx(2.0 * 0.01 / 2)          # everything sold and rebought


def test_abstention_entry_needs_cost_hold_needs_positive():
    rows = {T[0]: [("A", 0.02, 0.02, 0.0), ("B", 0.005, 0.005, 0.0), ("C", -0.01, -0.01, 0.0)],
            T[1]: [("A", 0.004, 0.004, 0.0), ("B", 0.005, 0.005, 0.0), ("C", -0.01, -0.01, 0.0)]}
    res = p1.simulate(_per(rows), T[:2], rt=0.01, abstain=True)
    assert res.filled.tolist() == [1, 1]                  # day 1: only A clears 1%; day 2: A held (pred > 0), B can't enter
    assert res.entries.tolist() == [1, 0]


def test_drift_rebalance_is_charged_and_net_compounds():
    rows = {T[0]: [("A", 3, 0, 0.10), ("B", 2, 0, 0.0), ("C", 1, 0, 0.0)],
            T[1]: [("A", 3, 0, 0.0), ("B", 2, 0, 0.0), ("C", 1, 0, 0.0)]}
    res = p1.simulate(_per(rows), T[:2], rt=0.01)
    assert res.gross.iloc[0] == pytest.approx(0.10 / 3)
    wa = (1 / 3 * 1.1) / (1 + 0.10 / 3)
    assert res.turnover.iloc[1] == pytest.approx((abs(wa - 1 / 3) + 2 * abs((1 / 3) / (1 + 0.10 / 3) - 1 / 3)) / 2)
    assert res.net.iloc[0] == pytest.approx((1 - 0.005) * (1 + 0.10 / 3) - 1)


def _bars(n=400, gap=None):
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    d = pd.DataFrame({"open": np.r_[100, c[:-1]], "high": c * 1.002, "low": c * 0.998, "close": c, "volume": 1.0}, index=idx)
    return d.drop(idx[gap]) if gap is not None else d


def test_labels_enter_at_decision_open_and_carry_missing_hours():
    d = _bars(gap=slice(250, 253))                       # 3 hours without trades
    r, filled = p1.fill_grid(d)
    assert filled.sum() == 3 and r.close.iloc[250] == r.close.iloc[249] and r.volume.iloc[250] == 0
    i = 240
    lab = p1.labels_at(r, filled, np.array([i]), 24).iloc[0]
    assert lab.fwd_ret == pytest.approx(r.close.iloc[i + 23] / r.open.iloc[i] - 1)
    assert lab.carried_hours == 3 and np.isnan(lab.target_first)       # barrier label needs contiguous bars
    lab2 = p1.labels_at(r, filled, np.array([300]), 24).iloc[0]
    assert lab2.carried_hours == 0 and lab2.target_first in (0.0, 1.0)


def test_features_at_decision_ignore_later_bars():
    d = _bars()
    r, _ = p1.fill_grid(d)
    t = r.index[300]                                       # decision at start of bar 300
    full = p1._per_symbol_features(r).loc[t]
    cut = p1._per_symbol_features(r.iloc[:300]).loc[t]    # only bars ending <= t
    pd.testing.assert_series_equal(full, cut)


def test_frozen_p1_refuses_a_changed_configuration(tmp_path, monkeypatch):
    import dataclasses
    import json
    import sys as _sys
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps({"hash": p1.config_hash()}))
    monkeypatch.setattr(p1, "FROZEN", frozen)
    monkeypatch.setattr(p1, "record", lambda *a, **k: None)
    monkeypatch.setitem(p1.SPECS, "M1", dataclasses.replace(p1.SPECS["M1"], params={"alpha": 10.0}))   # "tuned" after the fact
    monkeypatch.setattr(_sys, "argv", ["study.py", "final", "--horizon", "p1a"])
    with pytest.raises(SystemExit) as e:
        p1.main()
    assert "REFUSED" in str(e.value)


def test_repository_p1_is_frozen_at_current_code():
    import json
    assert json.loads(p1.FROZEN.read_text())["hash"] == p1.config_hash()
