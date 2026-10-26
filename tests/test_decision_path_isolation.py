"""Risk checks and order decisions must never wait on a language model or the network."""
import ast
from pathlib import Path

from tests.conftest import ROOT

DECISION_PATH = ["tradelab/intraday/engine.py", "tradelab/intraday/setups.py", "tradelab/intraday/limits.py",
                 "tradelab/intraday/costs.py", "tradelab/intraday/model.py", "tradelab/risk/engine.py",
                 "tradelab/risk/limits.py", "tradelab/governance/status.py"]
FORBIDDEN = ("anthropic", "openai", "tradelab.events", "urllib", "requests", "httpx", "websockets", "socket")


def imports(path):
    tree = ast.parse((ROOT / path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield ("." * node.level) + (node.module or "")


def test_decision_path_has_no_llm_or_network_imports():
    for p in DECISION_PATH:
        bad = [m for m in imports(p) if any(m.lstrip(".").startswith(f) for f in FORBIDDEN) or m.startswith("..events")]
        assert not bad, f"{p} imports {bad}"
