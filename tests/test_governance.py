import json

import numpy as np
import pandas as pd
import pytest

from tradelab.governance import monitor, promotion
from tradelab.service.registry import STRATEGIES, version
from tests.conftest import ROOT


def test_psi_flags_shift_not_noise():
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 5000)
    assert monitor.psi(ref, rng.normal(0, 1, 500)) < 0.1
    assert monitor.psi(ref, rng.normal(1.5, 1, 500)) > 0.25


def test_performance_decay_needs_enough_data_and_detects_collapse():
    rng = np.random.default_rng(1)
    ref = pd.Series(rng.normal(0.001, 0.02, 2000))
    assert monitor.performance_decay(pd.Series(rng.normal(0.001, 0.02, 10)), ref).severity == "info"
    assert monitor.performance_decay(pd.Series(rng.normal(-0.01, 0.02, 120)), ref).severity == "alert"
    assert monitor.performance_decay(pd.Series(rng.normal(0.001, 0.02, 120)), ref) is None


def test_promotion_requires_days_and_evidence():
    rng = np.random.default_rng(2)
    a = pd.Series(rng.normal(0.0005, 0.02, 60))
    v = promotion.evaluate(a, a * 1.0, 1.0, 1.0, 0)
    assert not v.eligible and any("paper days" in r for r in v.reasons)
    champ = pd.Series(rng.normal(0.0, 0.02, 200))
    chall = pd.Series(rng.normal(0.004, 0.01, 200))
    assert promotion.evaluate(champ, chall, 1.0, 1.0, 0).eligible
    assert not promotion.evaluate(champ, chall, 1.0, 3.0, 0).eligible       # churns too much
    assert not promotion.evaluate(champ, chall, 1.0, 1.0, 1).eligible       # had an incident


def test_lock_matches_running_code():
    """If this fails, strategy code changed without a reviewed update to config/strategies.lock."""
    lock = promotion.read_lock()
    for e in [lock["champion"], *lock["benchmarks"], *lock["challengers"]]:
        assert version(STRATEGIES[e["name"]]) == e["version"], e["name"]
