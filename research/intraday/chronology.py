"""Chronological record from the append-only registry: what was registered, run and changed, in order."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in (ROOT / "research/registry.jsonl").read_text().splitlines() if l.strip()]
keep = lambda r: (r["kind"] in ("preregistration", "change") or "frozen" in r["name"] or "test" in r["name"]
                  or "audit" in r["name"] or "holdout" in r["name"] or "crash" in r["name"] or "phase1" in r["name"]
                  or r["name"].startswith(("prereg3", "intraday_")))
out = [f"| {r['at'][:16].replace('T', ' ')} | {r['kind']} | {r['name']} | {(r.get('note') or r.get('purpose') or '')[:150]} |"
       for r in rows if keep(r)]
print(f"{len(rows)} registry entries total; {len(out)} shown")
print("| UTC | kind | entry | note |\n|---|---|---|---|")
print("\n".join(out))
