"""Rebuild data/events/macro_calendar.csv from official Fed and BLS pages."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.events.calendar import build  # noqa: E402

rows = build()
by = Counter((r.kind, r.release_utc[:4] or "tbd") for r in rows)
for k in sorted(by):
    print(k, by[k])
print("missing times:", sum(1 for r in rows if not r.release_utc and r.kind != "fomc_cancelled"),
      "irregular:", [(r.kind, r.reference, r.release_utc[:10]) for r in rows if r.irregular])
