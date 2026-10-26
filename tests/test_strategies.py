import importlib.util
import numpy as np
import pandas as pd
import pytest

from tradelab.data.candles import load
from tradelab.strategies import trend
from tests.conftest import ROOT


def _legacy():
    spec = importlib.util.spec_from_file_location("legacy_strategies", ROOT / "legacy" / "strategies.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def btc():
    return load("BTC-USD", "1d")


def test_baseline_matches_frozen_phase1_code(btc):
    legacy = _legacy().ensemble(0.40)(btc)
    new = trend.BASELINE(btc)
    pd.testing.assert_series_equal(new.fillna(0), legacy.fillna(0).clip(0, 1), check_names=False)


@pytest.mark.parametrize("spec", [trend.BASELINE, trend.SMA200, trend.VOL_ONLY, trend.TREND_ONLY, trend.BUY_HOLD])
def test_signals_never_use_future_bars(btc, spec):
    """Signal at bar t must be identical whether or not later bars exist."""
    full = spec(btc)
    for cut in [400, 1200, 2500, len(btc) - 30]:
        partial = spec(btc.iloc[: cut + 1])
        assert partial.iloc[-1] == pytest.approx(full.iloc[cut]), f"{spec.name} leaks future data at bar {cut}"


def test_future_shock_does_not_change_past_signal(btc):
    shocked = btc.copy()
    shocked.iloc[2000:, :4] *= 3.0
    a, b = trend.BASELINE(btc), trend.BASELINE(shocked)
    assert np.allclose(a.iloc[:2000], b.iloc[:2000])
