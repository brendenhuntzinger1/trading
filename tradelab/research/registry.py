"""Append-only log of every experiment, including failures, so the number of
things tried is known when judging the best result (multiple testing)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[2] / "research" / "registry.jsonl"


def data_hash(paths) -> str:
    h = hashlib.sha256()
    for p in sorted(map(str, paths)):
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


def record(kind: str, name: str, params: dict, period: str, purpose: str, metrics: dict | None = None,
           data: str | None = None, note: str = "") -> dict:
    """kind: 'preregistration' (written BEFORE results are seen) or 'result'."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind, "name": name, "params": params, "period": period, "purpose": purpose,
        "data_sha": data, "metrics": metrics, "note": note,
    }
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as fh:
        fh.write(json.dumps(entry, default=float) + "\n")
    return entry


def entries(kind: str | None = None) -> list[dict]:
    if not REGISTRY.exists():
        return []
    rows = [json.loads(l) for l in REGISTRY.read_text().splitlines() if l.strip()]
    return [r for r in rows if kind is None or r["kind"] == kind]
