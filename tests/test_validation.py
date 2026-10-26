import numpy as np
import pandas as pd
import pytest

from tradelab.research.validation import (brier, cscv_pbo, concentration, ece, mean_ci, purged_walk_forward,
                                          quantile_coverage, rank_ic_by_period, reliability, skill_vs_base_rate)


def test_purged_folds_never_train_on_labels_that_overlap_the_test():
    t = pd.Series(pd.date_range("2024-01-01", periods=200, freq="h"))
    end = t + pd.Timedelta(hours=24)                        # each label spans the next 24 hours
    for f in purged_walk_forward(t, end, n_folds=4, embargo=pd.Timedelta(hours=2)):
        assert f.train.max() < f.test.min()
        assert (end.iloc[f.train] < t.iloc[f.test.min()]).all()
        assert t.iloc[f.test.min()] - end.iloc[f.train].max() > pd.Timedelta(hours=2)


def test_pbo_high_for_pure_noise_low_for_real_skill():
    rng = np.random.default_rng(0)
    noise = pd.DataFrame(rng.normal(0, 1, (480, 40)))
    assert cscv_pbo(noise, 8).pbo > 0.3
    skill = noise.copy()
    skill[0] += 0.5                                         # one configuration genuinely better everywhere
    assert cscv_pbo(skill, 8).pbo < 0.05


def test_calibration_metrics_reward_honest_probabilities():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 20000)
    y = rng.uniform(0, 1, 20000) < p                        # perfectly calibrated
    assert ece(p, y) < 0.02 and skill_vs_base_rate(p, y) > 0.2
    overconfident = np.clip(p * 1.6 - 0.3, 0, 1)
    assert ece(overconfident, y) > ece(p, y) and brier(overconfident, y) > brier(p, y)
    r = reliability(p, y)
    assert len(r) == 10 and abs(r.gap).max() < 0.05


def test_quantile_coverage_and_rank_ic():
    rng = np.random.default_rng(2)
    y = rng.normal(0, 1, 5000)
    cov = quantile_coverage(y, {0.1: np.full(5000, -1.2816), 0.9: np.full(5000, 1.2816)})
    assert abs(cov[0.1] - 0.1) < 0.02 and abs(cov[0.9] - 0.9) < 0.02
    per = pd.Series(np.repeat(np.arange(100), 20))
    x = rng.normal(0, 1, 2000)
    ic = rank_ic_by_period(per, pd.Series(x), pd.Series(x + rng.normal(0, 1, 2000)))
    m, lo, hi = mean_ci(ic)
    assert lo > 0.5 and len(ic) == 100


def test_concentration_flags_dependence_on_few_trades():
    pnl = pd.Series([0.0] * 95 + [-0.1] * 4 + [10.0])
    c = concentration(pnl)
    assert c["top1pct_share"] > 1.0 and c["total_without_top5"] < 0
