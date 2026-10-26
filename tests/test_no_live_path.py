"""Merge gate: nothing in the repository can activate live execution.

- every config runs in paper mode;
- no workflow reads repository secrets (only the automatic GITHUB_TOKEN, for the paper-state branch and alerts);
- the only code allowed to send state-changing HTTP requests is the Alpaca PAPER broker adapter, which is
  pinned to the paper host;
- the live-trading guard is closed without a human-written approval of an exact config hash.
"""
import re
import tomllib
from pathlib import Path

from tests.conftest import ROOT
from tradelab.execution.venue import live_trading_allowed

ALLOWED_WRITERS = {"tradelab/broker/alpaca_paper.py"}


def test_every_config_is_paper():
    for p in (ROOT / "config").glob("*.toml"):
        cfg = tomllib.loads(p.read_text())
        if "mode" in cfg:
            assert cfg["mode"] == "paper", p


def test_workflows_read_no_repository_secrets_and_run_in_paper_mode():
    for p in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = p.read_text()
        assert "secrets." not in text, f"{p.name} reads a repository secret"
        for m in re.findall(r"TRADELAB_MODE:\s*(\S+)", text):
            assert m == "paper", p.name


def test_only_the_paper_broker_sends_state_changing_requests():
    pat = re.compile(r"method\s*=\s*['\"](POST|DELETE|PUT|PATCH)['\"]|\.post\(|\.delete\(|requests\.(post|delete|put|patch)")
    offenders = []
    for p in list((ROOT / "tradelab").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "research").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if rel not in ALLOWED_WRITERS and pat.search(p.read_text()):
            offenders.append(rel)
    assert not offenders, offenders


def test_live_guard_is_closed(monkeypatch):
    monkeypatch.delenv("TRADELAB_LIVE_APPROVED_CONFIG", raising=False)
    monkeypatch.setenv("TRADELAB_MODE", "live")
    assert live_trading_allowed("anything") is False
