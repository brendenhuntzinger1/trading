"""Stage gating (PHASE2_PROTOCOL §4): validation is readable only for a frozen dev-qualified configuration, final
only for a validated one; the frozen hash covers code and parameters; dev trials are counted."""
import json

import pytest

from research.phase2 import stages


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setattr(stages, "STATE", tmp_path / "state")
    recs = []
    monkeypatch.setattr(stages, "record", lambda *a, **k: recs.append((a, k)))
    code = tmp_path / "fam.py"
    code.write_text("x = 1\n")
    return tmp_path, recs, code


def test_validation_and_final_are_refused_without_a_frozen_qualified_config(iso):
    _, _, code = iso
    with pytest.raises(stages.StageRefused):
        stages.require("F9", "validation")
    stages.record_dev("F9", {"B0": {"qualified": False}, "C1": {"qualified": False}}, {"B0": {}, "C1": {}})
    with pytest.raises(stages.StageRefused):
        stages.freeze("F9", "C1", {"n": 1}, [code])
    with pytest.raises(stages.StageRefused):
        stages.require("F9", "validation")


def test_freeze_picks_only_a_qualified_config_and_hash_covers_code(iso):
    _, recs, code = iso
    stages.record_dev("F9", {"B0": {"qualified": True}, "C1": {"qualified": False}}, {"B0": {"n": 1}, "C1": {"n": 2}})
    assert sum(1 for a, k in recs if a[0] == "result" and k.get("metrics", {}).get("is_trial")) == 2
    h = stages.freeze("F9", "B0", {"n": 1}, [code])
    stages.require("F9", "validation", params={"n": 1}, code=[code])
    code.write_text("x = 2\n")
    with pytest.raises(stages.StageRefused, match="hash"):
        stages.require("F9", "validation", params={"n": 1}, code=[code])
    assert len(h) == 16


def test_final_needs_a_validated_candidate(iso):
    _, _, code = iso
    stages.record_dev("F9", {"B0": {"qualified": True}}, {"B0": {"n": 1}})
    stages.freeze("F9", "B0", {"n": 1}, [code])
    with pytest.raises(stages.StageRefused):
        stages.require("F9", "final", params={"n": 1}, code=[code])
    stages.record_validation("F9", {"qualified": False}, {})
    with pytest.raises(stages.StageRefused):
        stages.require("F9", "final", params={"n": 1}, code=[code])
    stages.record_validation("F9", {"qualified": True}, {})
    stages.require("F9", "final", params={"n": 1}, code=[code])
