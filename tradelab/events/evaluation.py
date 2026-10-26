"""Prospective evaluation. No point-in-time archive of historical news exists in
this project, so news features are judged only on events we saw live: for each
stored event, the BTC/ETH return from first_seen_at to +1h/+4h/+24h is filled
in once the horizon has passed. Compare against unconditional returns before
drawing any conclusion; small samples prove nothing."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Callable

from .store import EventStore

PRODUCTS = {"BTC": "BTC-USD", "ETH": "ETH-USD"}


def coinbase_price_fn() -> Callable[[str, datetime], float | None]:
    """Open of the hourly candle containing t (~ price available at t). Cached per window."""
    from tradelab.data.candles import fetch_coinbase   # read-only use of the shared data module
    cache: dict = {}

    def price(asset: str, t: datetime) -> float | None:
        hour = t.replace(minute=0, second=0, microsecond=0)
        key = (asset, hour.date())
        if key not in cache:
            start = datetime.combine(hour.date(), datetime.min.time(), tzinfo=timezone.utc)
            cache[key] = fetch_coinbase(PRODUCTS[asset], "1h", start, start + timedelta(days=1))
        df = cache[key]
        return float(df.open.loc[hour]) if hour in df.index else None
    return price


def fill_outcomes(store: EventStore, now: datetime, price: Callable[[str, datetime], float | None] | None = None) -> int:
    price = price or coinbase_price_fn()
    n = 0
    for event_id, asset, h, anchor in store.pending_outcomes(now):
        p0, p1 = price(asset, anchor), price(asset, anchor + timedelta(hours=h))
        store.record_outcome(event_id, asset, h, anchor, (p1 / p0 - 1) if p0 and p1 else None)
        n += 1
    return n


def summary(store: EventStore) -> dict:
    """Mean and mean-absolute return by (category, horizon). Descriptive only."""
    g = defaultdict(list)
    for r in store.outcomes():
        if r["ret"] is not None:
            g[(r["category"], r["asset"], r["horizon_h"])].append(r["ret"])
    return {k: {"n": len(v), "mean": mean(v), "mean_abs": mean(abs(x) for x in v)} for k, v in sorted(g.items())}
