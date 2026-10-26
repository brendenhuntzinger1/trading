"""Helpers behind DECISION_QUALITY.md: bootstrap intervals, rank correlation, regime causality."""
import sys

import numpy as np
import pandas as pd

from tests.conftest import ROOT

sys.path.insert(0, str(ROOT / "research/intraday/decision"))
from common import boot_mean, boot_spearman, period_of, prior_regimes  # noqa: E402


def test_bootstrap_interval_covers_known_mean_and_widens_with_noise():
    rng = np.random.default_rng(0)
    days = np.repeat(np.arange(300), 2)
    v = rng.normal(0.001, 0.01, len(days))
    est, lo, hi = boot_mean(v, days, n_boot=500)
    assert lo < 0.001 < hi and lo < est < hi
    _, lo2, hi2 = boot_mean(rng.normal(0.001, 0.05, len(days)), days, n_boot=500)
    assert (hi2 - lo2) > (hi - lo)


def test_spearman_detects_monotone_and_null():
    rng = np.random.default_rng(1)
    x = rng.normal(size=400)
    days = np.arange(400)
    est, lo, hi = boot_spearman(x, x ** 3, days, n_boot=200)
    assert est > 0.99 and lo > 0.9
    est, lo, hi = boot_spearman(x, rng.normal(size=400), days, n_boot=200)
    assert lo < 0 < hi


def test_regimes_use_only_prior_days():
    idx = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=120)]
    c = pd.Series(100 + np.cumsum(np.random.default_rng(2).normal(0, 1, 120)), index=idx)
    a = prior_regimes(c)
    shocked = c.copy(); shocked.iloc[80:] *= 3
    b = prior_regimes(shocked)
    pd.testing.assert_frame_equal(a.iloc[:81], b.iloc[:81])     # day 80's regime uses days < 80 only


def test_period_boundaries():
    assert period_of("2015-12-31", "S2") == "dev" and period_of("2016-01-04", "S2") == "validation"
    assert period_of("2023-12-31", "C") == "validation" and period_of("2024-01-01", "C") == "test"
