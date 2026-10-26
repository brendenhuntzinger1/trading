"""Append-only forward-evidence log (PHASE2_PROTOCOL.md §7).

A prediction is written BEFORE its outcome window opens; a late write is refused. Inputs older than the family's
staleness limit, or missing expected symbols, block the decision: the block itself is recorded (status
`stale_data` / `incomplete_data`) so silence can never be mistaken for "no signal". Outcomes are appended as
separate lines after the window closes; the prediction line is never rewritten.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "forward" / "predictions.jsonl"


class LateRecord(RuntimeError):
    """The outcome window had already opened: a prediction written now could have seen the outcome."""


class EarlyOutcome(RuntimeError):
    """The outcome window has not closed yet."""


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def record_prediction(family: str, config_hash: str, decision_time: datetime, outcome_start: datetime,
                      data_asof: datetime, max_age: timedelta, expected_symbols: list[str],
                      received_symbols: list[str], signals: dict, path: Path = DEFAULT,
                      outcome_end: datetime | None = None, now: datetime | None = None, note: str = "") -> dict:
    now = now or datetime.now(timezone.utc)
    if now >= outcome_start:
        raise LateRecord(f"{family}: outcome window opened at {outcome_start.isoformat()}, now {now.isoformat()}")
    missing = sorted(set(expected_symbols) - set(received_symbols))
    age = decision_time - data_asof
    status = "stale_data" if age > max_age else ("incomplete_data" if missing else "recorded")
    row = {"type": "prediction", "family": family, "config_hash": config_hash, "recorded_at": now.isoformat(),
           "decision_time": decision_time.isoformat(), "outcome_start": outcome_start.isoformat(),
           "outcome_end": (outcome_end or outcome_start).isoformat(), "data_asof": data_asof.isoformat(),
           "data_age_s": age.total_seconds(), "max_age_s": max_age.total_seconds(), "status": status,
           "missing": missing, "signals": signals if status == "recorded" else {}, "note": note}
    row["id"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
    _append(path, row)
    return row


def record_outcome(prediction_id: str, outcome: dict, path: Path = DEFAULT, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    pred = next((r for r in _rows(path) if r.get("type") == "prediction" and r["id"] == prediction_id), None)
    if pred is None:
        raise KeyError(prediction_id)
    if now < datetime.fromisoformat(pred["outcome_end"]):
        raise EarlyOutcome(f"{prediction_id}: window closes {pred['outcome_end']}")
    row = {"type": "outcome", "prediction_id": prediction_id, "recorded_at": now.isoformat(), "outcome": outcome}
    _append(path, row)
    return row


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def joined(path: Path = DEFAULT) -> list[dict]:
    """Predictions with their outcome (None while open), in recording order."""
    rows = _rows(path)
    outs = {r["prediction_id"]: r["outcome"] for r in rows if r.get("type") == "outcome"}
    return [{**r, "outcome": outs.get(r["id"])} for r in rows if r.get("type") == "prediction"]
