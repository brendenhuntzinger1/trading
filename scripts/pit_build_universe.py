"""Build the point-in-time Coinbase universe: .venv/bin/python scripts/pit_build_universe.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.pit import crypto_universe as cu  # noqa: E402

u = cu.build()
p = cu.save(u)
s = cu.summary(u)
print(p, len(u), "rows")
print(s.round(1).to_string())
ever = sorted(u.loc[u.eligible & (u.date >= "2021-01-01"), "product"].unique())
(cu.OUT.parent / "ever_eligible_2021.json").write_text(json.dumps(ever))
print("ever eligible since 2021:", len(ever))
