"""H3 harness: equal-weight sizing, qualifiers, consumed marking before the read, final refused unless qualified."""
import json

import pytest

from research.h3 import study as h3
from tests.test_orb_study import Fixture


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setattr(h3, "FRAMES", tmp_path / "frames")
    monkeypatch.setattr(h3, "RESULTS", tmp_path / "results")
    led = tmp_path / "consumed.json"
    led.write_text(json.dumps({"entries": []}))
    monkeypatch.setattr(h3, "CONSUMED_LEDGER", led)
    monkeypatch.setattr(h3, "record", lambda *a, **k: None)
    return tmp_path


def test_fetch_marks_consumed_first_and_validation_reports_qualifiers(iso):
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
