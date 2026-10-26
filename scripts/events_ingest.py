"""Run one ingestion pass and print counts per source, plus currently active flags.
Usage: .venv/bin/python scripts/events_ingest.py [--db PATH] [--fill-outcomes]"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.events.evaluation import fill_outcomes  # noqa: E402
from tradelab.events.flags import active_flags  # noqa: E402
from tradelab.events.llm import LLMClassifier  # noqa: E402
from tradelab.events.pipeline import ingest_once  # noqa: E402
from tradelab.events.store import DEFAULT_DB, EventStore  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", default=str(DEFAULT_DB))
ap.add_argument("--fill-outcomes", action="store_true")
a = ap.parse_args()
store = EventStore(a.db)
now = datetime.now(timezone.utc)
for name, c in ingest_once(store, llm=LLMClassifier()).items():
    print(f"{name:24s} {c}")
if a.fill_outcomes:
    print("outcomes filled:", fill_outcomes(store, now))
for f in active_flags(now, store):
    print("FLAG", f.kind, f.severity, f.reason[:120])
