"""Connect to real public feeds for ~60 s and report data quality.

Usage: .venv/bin/python scripts/live_smoke.py [--venue coinbase|kraken|both] [--seconds 60] [--record]
"""
import argparse
import asyncio
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.data.live.analytics import realized_vol
from tradelab.data.live.bars import build_bars
from tradelab.data.live.derivatives import perp_snapshots
from tradelab.data.live.feeds import make_feed
from tradelab.data.live.recorder import Recorder
from tradelab.data.live.types import Trade


async def smoke(venue: str, seconds: float, record: bool):
    syms = ["BTC-USD", "ETH-USD"]
    counts, trades, latencies = Counter(), [], []
    rec = Recorder() if record else None

    def on_record(r):
        counts[type(r).__name__] += 1
        if isinstance(r, Trade):
            trades.append(r)
            if not r.from_snapshot:
                latencies.append((r.received_at - r.event_time).total_seconds() * 1000)
        if rec:
            rec.write(r)

    f = make_feed(syms, venue, on_record=on_record, depth=10 if venue == "kraken" else 50)
    raw_count = 0
    orig = f.handle

    def counting(raw, t):
        nonlocal raw_count
        raw_count += 1
        return orig(raw, t)

    f.handle = counting
    start = datetime.now(timezone.utc)
    t0 = time.time()
    task = asyncio.create_task(f.run())
    stale_checks = 0
    while time.time() - t0 < seconds:
        await asyncio.sleep(5)
        now = datetime.now(timezone.utc)
        stale_checks += sum(h.stale(now, 5) for h in f.health.values())
    el = time.time() - t0
    print(f"\n=== {venue}: {el:.0f}s, {raw_count} raw msgs ({raw_count / el:.1f}/s), records {dict(counts)}, "
          f"duplicates dropped {f.duplicates_dropped}, stale observations {stale_checks}")
    for s in syms:
        h, b = f.health[s], f.books[s]
        line = f"{s}: book_valid={b.valid} gaps={h.sequence_gaps} checksum_fail={h.checksum_failures} reconnects={h.reconnects} clock_offset_ms={h.clock_offset_ms}"
        if b.valid:
            d = f.depth_summary(s, 10)
            line += f" spread={b.spread_bps():.3f}bps depth±10bps bid=${d.bid_notional:,.0f} ask=${d.ask_notional:,.0f}"
        print(line, "| notes:", h.notes[-3:])
    if latencies:
        lat = sorted(latencies)
        print(f"trade event->receive latency ms: p50={lat[len(lat)//2]:.0f} p95={lat[int(len(lat)*.95)]:.0f} (includes exchange batching; clock offset not removed)")
    from datetime import timedelta
    for s in syms:
        bars = build_bars([t for t in trades if t.symbol == s], timedelta(seconds=10), start, datetime.now(timezone.utc))
        v = realized_vol(bars, 3, 365 * 24 * 360)
        print(f"{s} 10s bars: {len(bars)}, empty {int((bars.trades == 0).sum())}, late trades {int(bars.late_trades.sum())}, last 30s vol (annualized, noisy) {v.dropna().iloc[-1] if v.notna().any() else float('nan'):.2f}")

    if rec:
        for s in syms:
            rec.write(f.sample(s))
            rec.write(f.health[s])
        rec.close()
    f.stop()
    await asyncio.wait_for(task, 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", default="both")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    for v in (["coinbase", "kraken"] if a.venue == "both" else [a.venue]):
        asyncio.run(smoke(v, a.seconds, a.record))
    try:
        for p in perp_snapshots():
            print(f"[research-only] {p.perp}: basis {p.basis * 1e4:.2f} bps, funding {p.funding_rate_annualized:.2%}/yr, OI {p.open_interest:,.0f}")
    except Exception as e:
        print("derivatives research input unavailable:", e)


if __name__ == "__main__":
    main()
