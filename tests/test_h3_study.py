"""H3 harness: equal-weight sizing, qualifiers, consumed marking before the read, final refused unless qualified,
and the Amendment 1 development gate (validation untouched unless the corrected 2020-21 check passes)."""
import json
import pickle

import pytest

from research.h3 import study as h3
from research.orb import study as orb_study
from tests.test_orb_study import Fixture, Untouchable


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setattr(h3, "FRAMES", tmp_path / "frames")
    monkeypatch.setattr(h3, "RESULTS", tmp_path / "results")
    led = tmp_path / "consumed.json"
    led.write_text(json.dumps({"entries": []}))
    monkeypatch.setattr(h3, "CONSUMED_LEDGER", led)
    monkeypatch.setattr(h3, "DEV_FRAMES", tmp_path / "dev_frames")
    monkeypatch.setattr(h3, "record", lambda *a, **k: None)
    return tmp_path


def _dev_passed(iso, ok=True):
    (iso / "results").mkdir(exist_ok=True)
    (iso / "results" / "dev_check.json").write_text(json.dumps({"qualifiers": {"qualified": ok}}))


def test_fetch_marks_consumed_first_and_validation_reports_qualifiers(iso):
    _dev_passed(iso)
    h3.fetch("2022", source=Fixture(n_days=8))
    entries = json.loads(h3.CONSUMED_LEDGER.read_text())["entries"]
    assert entries[0]["scope"] == "stocks.us.intraday.first_candle" and entries[0]["start"] == "2022-01-03"
    out = h3.validation()
    assert set(out["qualifiers"]) == {"net_lower_bound_gt_0", "beats_basket_matched", "both_years_positive",
                                      "positive_without_top5pct", "qualified"}
    assert out["H3-L"]["trades"] > 0
    assert out["qualifiers"]["both_years_positive"] is False        # one year of fixture data cannot qualify


def test_final_stays_unread_unless_qualified(iso):
    (iso / "results").mkdir()
    (iso / "results" / "validation.json").write_text(json.dumps({"qualifiers": {"qualified": False}}))
    with pytest.raises(SystemExit, match="UNREAD"):
        h3.final()


@pytest.mark.parametrize("dev_state", ["missing", "failed"])
def test_validation_is_untouched_unless_the_development_check_passed(iso, dev_state):
    """Amendment 1: no ledger entry, no data access and no validation read unless dev_check qualified."""
    if dev_state == "failed":
        _dev_passed(iso, ok=False)
    with pytest.raises(SystemExit, match="UNREAD"):
        h3.fetch("2022", source=Untouchable())
    assert json.loads(h3.CONSUMED_LEDGER.read_text())["entries"] == []
    with pytest.raises(SystemExit, match="UNREAD"):
        h3.validation()


def test_dev_check_uses_the_validation_qualifiers_on_2020_21_frames(iso):
    frames = orb_study.run_period(Fixture(n_days=8), "dev", ["primary"], placebo_reps=0)["configs"]["primary"]["_frames"]
    h3.DEV_FRAMES.mkdir()
    (h3.DEV_FRAMES / "dev_primary_0_of_1.pkl").write_bytes(pickle.dumps(frames))
    out = h3.dev_check()
    assert set(out["qualifiers"]) == {"net_lower_bound_gt_0", "beats_basket_matched", "both_years_positive",
                                      "positive_without_top5pct", "qualified"}
    assert out["H3-L"]["trades"] == len(frames["direction"])
    assert (iso / "results" / "dev_check.json").exists()
    assert out["qualifiers"]["qualified"] is False             # eight fixture days cover one year, not two
    with pytest.raises(SystemExit, match="UNREAD"):
        h3.validation()
