"""Research memory: one searchable view over every hypothesis, trial, result and incident.

    python research/ledger.py search reversal overnight      # any record mentioning all the words
    python research/ledger.py dedup "short-term reversal, daily, US stocks"   # nearest earlier hypotheses
    python research/ledger.py trials                          # cumulative trial count (selection-bias N)
    python research/ledger.py hypotheses                      # one line per distinct hypothesis

Sources (append-only, version-controlled):
    research/hypotheses.jsonl   one record per distinct economic hypothesis (family, scope, status, diagnosis)
    research/registry.jsonl     every pre-registration, change, trial result, reproduction and freeze
    research/incidents.jsonl    every software, data, execution or process failure, with its prevention

`dedup` scores earlier hypotheses by shared informative words across family, idea, market and signal fields,
so a proposal that repeats an earlier test (or a known defect) is visible before any code is written.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYPOTHESES = ROOT / "research" / "hypotheses.jsonl"
REGISTRY = ROOT / "research" / "registry.jsonl"
INCIDENTS = ROOT / "research" / "incidents.jsonl"
STOP = set("a an the of and or in on at to for with by from is are be as it its this that into over under per "
           "than then when vs daily intraday day days stocks stock us".split())


def _rows(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def records() -> list[tuple[str, dict]]:
    return ([("hypothesis", r) for r in _rows(HYPOTHESES)] + [("registry", r) for r in _rows(REGISTRY)]
            + [("incident", r) for r in _rows(INCIDENTS)])


def search(terms: list[str]) -> list[tuple[str, dict]]:
    want = [t.lower() for t in terms]
    return [(k, r) for k, r in records() if all(t in json.dumps(r).lower() for t in want)]


def dedup(proposal: str, top: int = 5) -> list[tuple[float, dict]]:
    pw = _words(proposal)
    scored = []
    for r in _rows(HYPOTHESES):
        hw = _words(" ".join(str(r.get(k, "")) for k in ("family", "idea", "market", "signal", "timeframe")))
        if hw and pw:
            scored.append((len(pw & hw) / len(pw | hw), r))
    return sorted(scored, key=lambda x: -x[0])[:top]


def trial_count() -> dict:
    """Configurations evaluated, by study prefix. Pre-registrations, changes and reproductions are not trials."""
    by: dict[str, int] = {}
    for r in _rows(REGISTRY):
        if r.get("kind") in ("trial", "result") and isinstance(r.get("metrics"), dict) and r["metrics"].get("is_trial"):
            pre = r["name"].split(":")[0]
            by[pre] = by.get(pre, 0) + 1
    counts = [r for r in _rows(REGISTRY) if r.get("kind") == "trial_count"]
    base_n = counts[-1]["params"]["n_trials"] if counts else None           # latest baseline wins
    return {"baseline_before_phase2": base_n, "phase2_trials_by_study": by,
            "total": (base_n or 0) + sum(by.values())}


def main(argv: list[str]) -> None:
    cmd, rest = (argv[0], argv[1:]) if argv else ("hypotheses", [])
    if cmd == "search":
        for k, r in search(rest):
            print(k, json.dumps(r)[:300])
    elif cmd == "dedup":
        for s, r in dedup(" ".join(rest)):
            print(f"{s:.2f}  {r.get('id')}  {r.get('family')}  [{r.get('status')}]  {r.get('idea', '')[:120]}")
    elif cmd == "trials":
        print(json.dumps(trial_count(), indent=1))
    else:
        for r in _rows(HYPOTHESES):
            print(f"{r.get('id'):10s} {r.get('status', ''):13s} {r.get('family', '')[:45]:45s} {r.get('market', '')[:40]}")


if __name__ == "__main__":
    main(sys.argv[1:])
