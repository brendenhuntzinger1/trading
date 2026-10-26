"""Fetch hourly candles for every product ever eligible since 2021 (resumable).
  .venv/bin/python scripts/pit_fetch_hourly.py [--workers 4]"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.pit import crypto_bars as cb, crypto_universe as cu  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--min-interval", type=float, default=0.12)
a = ap.parse_args()

u = cu.load()
ever = json.loads((cu.OUT.parent / "ever_eligible_2021.json").read_text())
if "BTC-USD" not in ever:
    ever.append("BTC-USD")
limiter = cb.RateLimiter(a.min_interval)
plan = {}
for p in ever:
    d = cu.load_daily(p)
    first_el = u[(u["product"] == p) & u.eligible].date.min()
    start = max(pd.Timestamp("2021-01-01", tz="UTC"), first_el - pd.Timedelta(days=60))
    if p == "BTC-USD":
        start = pd.Timestamp("2021-01-01", tz="UTC")                  # outage reference needs full coverage
    plan[p] = (start, d.index.max() + pd.Timedelta(days=1) if p.split("-")[0] else None)
# products still trading: fetch up to now
status = cu.coinbase_status()
for p, (s, e) in plan.items():
    if status.get(p) == "online":
        plan[p] = (s, pd.Timestamp(datetime.now(timezone.utc)))
with cb.FetchLock(), ThreadPoolExecutor(max_workers=a.workers) as ex:
    futs = {ex.submit(cb.fetch_product, p, s, e, limiter): p for p, (s, e) in plan.items()}
    for i, f in enumerate(as_completed(futs), 1):
        p = futs[f]
        try:
            print(f"[{i}/{len(futs)}] {p} +{f.result()} bars", flush=True)
        except Exception as e:
            print(f"[{i}/{len(futs)}] {p} FAILED {e!r}", flush=True)
