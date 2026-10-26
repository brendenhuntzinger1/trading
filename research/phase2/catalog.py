"""Update a hypothesis record in research/hypotheses.jsonl (status, periods read, diagnosis) in place."""
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "hypotheses.jsonl"


def update(hid: str, **fields) -> None:
    rows = [json.loads(l) for l in P.read_text().splitlines() if l.strip()]
    for r in rows:
        if r["id"] == hid:
            r.update(fields)
    P.write_text("".join(json.dumps(r) + "\n" for r in rows))
