"""Ledger of historical data already used to *evaluate* something, so it cannot be reused to *select* something.

A window is "consumed" for a scope once a study's test/final evaluation has read outcomes in it. Any later
study that wants to choose models, rules or parameters on data in the same scope must call
`check_selection_window`, which raises if the window overlaps consumed data. Re-running a frozen evaluation for
reproduction does not need the check; it changes nothing that is selected.

Scopes are dotted names (e.g. "crypto.coinbase.cross_section"); a check on a scope also matches entries for its
parents and children ("crypto.coinbase" overlaps "crypto.coinbase.cross_section").
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[2] / "research" / "consumed_data.json"


class ConsumedDataError(RuntimeError):
    pass


def load(path: Path = LEDGER) -> list[dict]:
    return json.loads(path.read_text())["entries"] if path.exists() else []


def _d(x) -> date:
    return x if isinstance(x, date) and not isinstance(x, datetime) else date.fromisoformat(str(x)[:10])


def _related(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def overlapping(scope: str, start, end, path: Path = LEDGER) -> list[dict]:
    s, e = _d(start), _d(end)
    return [x for x in load(path) if _related(scope, x["scope"]) and _d(x["start"]) <= e and s <= _d(x["end"])]


def check_selection_window(scope: str, start, end, path: Path = LEDGER) -> None:
    """Raise if [start, end] in `scope` overlaps data already consumed by an evaluation."""
    hits = overlapping(scope, start, end, path)
    if hits:
        names = ", ".join(f"{h['study']} ({h['start']}..{h['end']}, {h['scope']})" for h in hits)
        raise ConsumedDataError(f"selection window {start}..{end} in {scope} overlaps consumed data: {names}")


def mark_consumed(scope: str, start, end, study: str, note: str = "", path: Path = LEDGER) -> dict:
    """Record a consumed window. Idempotent for the same (scope, start, end, study)."""
    doc = json.loads(path.read_text()) if path.exists() else {"entries": []}
    key = (scope, str(_d(start)), str(_d(end)), study)
    for x in doc["entries"]:
        if (x["scope"], x["start"], x["end"], x["study"]) == key:
            return x
    entry = {"scope": scope, "start": key[1], "end": key[2], "study": study, "note": note,
             "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    doc["entries"].append(entry)
    path.write_text(json.dumps(doc, indent=1) + "\n")
    return entry
