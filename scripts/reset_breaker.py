"""Human reset of a latched breaker (reconciliation mismatch, max drawdown, repeated rejections).
Usage: .venv/bin/python scripts/reset_breaker.py ACCOUNT BREAKER --operator NAME --note "what was checked"
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.execution.store import Store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("account")
ap.add_argument("breaker")
ap.add_argument("--operator", required=True)
ap.add_argument("--note", required=True)
ap.add_argument("--journal", default=str(Path(__file__).resolve().parents[1] / "data" / "journal_paper.db"))
ap.add_argument("--mode", default="paper")
a = ap.parse_args()
st = Store(a.journal, a.mode)
active = st.active_latches(a.account)
if a.breaker not in active:
    sys.exit(f"no active latch '{a.breaker}' on {a.account}; active: {sorted(active) or 'none'}")
st.reset_latch(a.account, a.breaker, a.operator, a.note, datetime.now(timezone.utc))
print(f"reset {a.breaker} on {a.account} by {a.operator}: {a.note}")
