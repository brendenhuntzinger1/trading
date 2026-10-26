"""Forward evidence log: predictions are written before their outcome window opens, stale or incomplete inputs
block the decision (recorded, never silently skipped), records are append-only and outcomes are filled later
without touching the prediction."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from tradelab.forward import recorder as fr

T0 = datetime(2026, 10, 27, 13, 0, tzinfo=timezone.utc)


def _rec(tmp_path, **kw):
    args = dict(family="F1", config_hash="abc", decision_time=T0, outcome_start=T0 + timedelta(minutes=30),
                data_asof=T0 - timedelta(minutes=5), max_age=timedelta(minutes=20),
                expected_symbols=["A", "B"], received_symbols=["A", "B"], signals={"A": 1.0, "B": -0.5},
                path=tmp_path / "fwd.jsonl", now=T0)
    args.update(kw)
    return fr.record_prediction(**args)


def test_prediction_is_recorded_before_the_outcome_window(tmp_path):
    r = _rec(tmp_path)
    assert r["status"] == "recorded" and r["signals"] == {"A": 1.0, "B": -0.5}
    assert json.loads((tmp_path / "fwd.jsonl").read_text().splitlines()[0])["id"] == r["id"]


def test_recording_after_the_outcome_window_opened_is_refused(tmp_path):
    with pytest.raises(fr.LateRecord):
        _rec(tmp_path, now=T0 + timedelta(minutes=31))
    assert not (tmp_path / "fwd.jsonl").exists()


def test_stale_data_blocks_the_decision_and_is_logged(tmp_path):
    r = _rec(tmp_path, data_asof=T0 - timedelta(minutes=45))
    assert r["status"] == "stale_data" and r["signals"] == {}


def test_incomplete_data_blocks_the_decision(tmp_path):
    r = _rec(tmp_path, received_symbols=["A"])
    assert r["status"] == "incomplete_data" and r["missing"] == ["B"] and r["signals"] == {}


def test_outcome_is_appended_without_rewriting_the_prediction(tmp_path):
    r = _rec(tmp_path)
    before = (tmp_path / "fwd.jsonl").read_text()
    fr.record_outcome(r["id"], {"A": 0.01, "B": -0.02}, path=tmp_path / "fwd.jsonl",
                      now=T0 + timedelta(days=1))
    lines = (tmp_path / "fwd.jsonl").read_text().splitlines()
    assert (tmp_path / "fwd.jsonl").read_text().startswith(before) and len(lines) == 2
    joined = fr.joined(tmp_path / "fwd.jsonl")
    assert joined[0]["outcome"] == {"A": 0.01, "B": -0.02}


def test_outcome_before_the_window_closes_is_refused(tmp_path):
    r = _rec(tmp_path)
    with pytest.raises(fr.EarlyOutcome):
        fr.record_outcome(r["id"], {"A": 0.0}, path=tmp_path / "fwd.jsonl", now=T0 + timedelta(minutes=10))
