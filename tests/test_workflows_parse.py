"""Incident 7: every workflow must parse as YAML and have the expected shape (a plain scalar containing ': '
once broke the alert steps)."""
import yaml

from tests.conftest import ROOT


def test_every_workflow_parses_and_has_steps():
    for p in (ROOT / ".github" / "workflows").glob("*.yml"):
        d = yaml.safe_load(p.read_text())
        assert d.get(True) or d.get("on"), p.name                        # 'on' parses as True in YAML 1.1
        for job in d["jobs"].values():
            assert job["steps"], p.name
            for s in job["steps"]:
                assert isinstance(s.get("run", ""), str), (p.name, s)
