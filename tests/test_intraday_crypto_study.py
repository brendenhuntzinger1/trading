import json

import numpy as np
import pandas as pd
import pytest

from tradelab.intraday.research import crypto_study as S


def test_holdout_liquidity_filter_is_point_in_time(tmp_path, monkeypatch):
    (tmp_path / "data" / "universe").mkdir(parents=True)
    idx = pd.date_range("2023-11-01", periods=120, freq="D", tz="UTC")
    vol = np.full(120, 1.0)
    vol[100:] = 1e9                          # volume explodes on day 100
    pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": vol}, index=idx).to_csv(
        tmp_path / "data" / "universe" / "ABC-USD_1d.csv")
    pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1e12}, index=idx).to_csv(
        tmp_path / "data" / "universe" / "USDC-USD_1d.csv")
    monkeypatch.setattr(S, "ROOT", tmp_path)
    el = S.eligible_holdouts("2023-11-01", "2024-03-01")
    assert "USDC-USD" not in el                        # stablecoins excluded
    days = sorted(el["ABC-USD"])
    # median of the 30 PRIOR days (even count: mean of 15th and 16th) first exceeds $20M when 15 of
    # them are high-volume, i.e. on day 115; day 100 itself (the spike) is not yet known
    assert days[0] == idx[115]


def test_test_phase_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "OUT", tmp_path)
    (tmp_path / "test_done.json").write_text(json.dumps({"at": "2026-10-25T00:00:00"}))
    with pytest.raises(SystemExit, match="runs once"):
        S.test()
