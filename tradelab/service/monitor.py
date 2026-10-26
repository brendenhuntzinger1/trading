"""Always-on market monitor (paper mode). Records the live feed, checks data
freshness, book integrity and abnormal moves every few seconds, and publishes
data/live/status.json for the dashboard and the daily runner. It places no
orders: the daily strategies trade once a day, and only after this status and
their own checks pass.

    .venv/bin/python -m tradelab.service.monitor [--seconds 60]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import tomllib
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradelab.data.live.feeds import make_feed
from tradelab.data.live.recorder import LIVE_DIR, Recorder
from tradelab.data.live.types import TopOfBook, Trade, VenueNotice
from tradelab.execution.secrets import RedactingFilter
from tradelab.risk.engine import AccountState, MarketSnapshot, RiskEngine
from tradelab.risk.limits import RiskLimits

ROOT = Path(__file__).resolve().parents[2]
STATUS = LIVE_DIR / "status.json"
log = logging.getLogger("tradelab.monitor")


class Mids:
    """Rolling mid-price history per symbol, for 1h moves."""
    def __init__(self, keep: timedelta = timedelta(hours=2)):
        self.keep, self.h = keep, {}

    def add(self, sym: str, t: datetime, mid: float):
        d = self.h.setdefault(sym, deque())
        if not d or (t - d[-1][0]).total_seconds() >= 1:
            d.append((t, mid))
        while d and t - d[0][0] > self.keep:
            d.popleft()

    def move(self, sym: str, now: datetime, span: timedelta = timedelta(hours=1)) -> float:
        d = self.h.get(sym)
        if not d:
            return 0.0
        past = next((m for t, m in d if now - t <= span), d[0][1])
        return d[-1][1] / past - 1


def status(feed, now: datetime, limits: RiskLimits, mids: Mids, notices: list) -> dict:
    markets, rows = {}, {}
    for s in feed.symbols:
        h, top, dep = feed.health[s], feed.top(s), feed.depth_summary(s, limits.depth_band_bps)
        stale = h.stale(now, limits.stale_data_s)
        rows[s] = {"connected": h.connected, "book_valid": h.book_valid, "stale": stale,
                   "last_message_at": h.last_message_at.isoformat() if h.last_message_at else None,
                   "sequence_gaps": h.sequence_gaps, "checksum_failures": h.checksum_failures,
                   "reconnects": h.reconnects, "clock_offset_ms": h.clock_offset_ms,
                   "spread_bps": top.spread_bps if top else None,
                   "depth_bid": dep.bid_notional if dep else None, "depth_ask": dep.ask_notional if dep else None,
                   "move_1h": mids.move(s, now)}
        if top:
            markets[s] = MarketSnapshot(top.mid, top.spread_bps, dep.ask_notional if dep else 0.0,
                                        h.last_message_at, move_1h=rows[s]["move_1h"])
    venue_up = all(r["connected"] and r["book_valid"] for r in rows.values())
    eng = RiskEngine(limits)
    probe = AccountState(equity=1.0, start_of_day_equity=1.0, peak_equity=1.0, weights={})
    acts = eng.evaluate(now, probe, markets if markets else {s: MarketSnapshot(0, 0, 0, now - timedelta(days=1)) for s in feed.symbols},
                        venue_up=venue_up)
    return {"at": now.isoformat(), "venue": feed.venue, "symbols": rows,
            "breakers": {b.value: d for b, d in eng.state.active.items()},
            "actions": sorted(a.value for a in acts), "notices": notices[-10:]}


async def main(seconds: float | None, config: Path):
    cfg = tomllib.loads(config.read_text())
    limits, _ = RiskLimits.load(config)
    rec, mids, notices = Recorder(), Mids(), []

    def on_record(r):
        if isinstance(r, TopOfBook):
            mids.add(r.symbol, r.received_at, r.mid)
        elif isinstance(r, VenueNotice):
            notices.append({"at": r.received_at.isoformat(), "text": str(r)})
        if isinstance(r, (Trade, VenueNotice)):
            rec.write(r)

    feed = make_feed(["BTC-USD", "ETH-USD"], cfg.get("venue", "coinbase"), on_record=on_record)
    task = asyncio.create_task(feed.run())
    end = datetime.now(timezone.utc) + timedelta(seconds=seconds) if seconds else None
    last_sample = datetime.min.replace(tzinfo=timezone.utc)
    try:
        while not end or datetime.now(timezone.utc) < end:
            await asyncio.sleep(5)
            now = feed.clock.now()
            st = status(feed, now, limits, mids, notices)
            STATUS.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATUS.with_suffix(".tmp")
            tmp.write_text(json.dumps(st, default=str, indent=1))
            tmp.replace(STATUS)                         # atomic: readers never see half a file
            if now - last_sample > timedelta(minutes=1):  # book samples for prospective order-book research
                for s in feed.symbols:
                    rec.write(feed.sample(s, 25))
                last_sample = now
            rec.flush()
            if st["breakers"]:
                log.warning("market breakers: %s", st["breakers"])
    finally:
        feed.stop()
        task.cancel()
        rec.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--config", default=str(ROOT / "config" / "paper.toml"))
    a = ap.parse_args()
    h = logging.StreamHandler()
    h.addFilter(RedactingFilter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    asyncio.run(main(a.seconds, Path(a.config)))
