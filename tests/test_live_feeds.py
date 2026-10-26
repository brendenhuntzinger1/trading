"""Live market-data tests. Fixtures are short real captures (2026-10-25); no network."""
import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tradelab.data.live.book import OrderBook
from tradelab.data.live.feeds import CoinbaseFeed, KrakenFeed, parse_ts
from tradelab.data.live.types import FeedHealth, Trade, TopOfBook, VenueNotice

FIX = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)


def lines(name):
    return (FIX / name).read_text().splitlines()


def feed(cls, syms=("BTC-USD",)):
    return cls(list(syms), connect=lambda url: None, measure_clock=False)


# ---- Kraken: real stream verifies, corruption is caught ----

def test_kraken_real_stream_passes_every_checksum():
    f = feed(KrakenFeed)
    recs = [r for l in lines("kraken_raw.jsonl") for r in f.handle(l, T0)]
    h = f.health["BTC-USD"]
    assert h.checksum_failures == 0 and h.book_valid
    assert f.top("BTC-USD").spread_bps < 5
    assert any(isinstance(r, Trade) for r in recs)
    assert any(isinstance(r, VenueNotice) and r.status == "maintenance_scheduled" for r in recs)


def test_kraken_bad_checksum_invalidates_and_requests_resync():
    f = feed(KrakenFeed)
    ls = lines("kraken_raw.jsonl")
    snap_i = next(i for i, l in enumerate(ls) if '"type":"snapshot"' in l and '"channel":"book"' in l)
    for l in ls[: snap_i + 1]:
        f.handle(l, T0)
    upd = json.loads(next(l for l in ls[snap_i + 1:] if '"channel":"book"' in l))
    upd["data"][0]["checksum"] += 1                      # corrupted / missed message
    f.handle(json.dumps(upd), T0)
    assert f.health["BTC-USD"].checksum_failures == 1
    assert not f.books["BTC-USD"].valid and "BTC-USD" in f.resync
    assert f.top("BTC-USD") is None                       # nothing served from a bad book
    f.handle(ls[snap_i], T0)                              # resync snapshot restores it
    assert f.books["BTC-USD"].valid


def test_kraken_updates_ignored_until_snapshot():
    f = feed(KrakenFeed)
    upd = next(l for l in lines("kraken_raw.jsonl") if '"channel":"book","type":"update"' in l)
    f.handle(upd, T0)
    assert not f.books["BTC-USD"].valid and f.health["BTC-USD"].checksum_failures == 0


# ---- Coinbase: connection-level sequence numbers ----

def test_coinbase_real_stream_builds_valid_book():
    f = feed(CoinbaseFeed)
    for l in lines("coinbase_raw.jsonl"):
        f.handle(l, T0)
    assert f.books["BTC-USD"].valid and f.health["BTC-USD"].sequence_gaps == 0
    top = f.top("BTC-USD")
    assert top.bid < top.ask
    bid_n, ask_n = f.depth_summary("BTC-USD", 10).bid_notional, f.depth_summary("BTC-USD", 10).ask_notional
    assert bid_n > 0 and ask_n > 0


def test_coinbase_sequence_gap_invalidates_until_new_snapshot():
    f = feed(CoinbaseFeed)
    ls = lines("coinbase_raw.jsonl")
    for l in ls[:5]:
        f.handle(l, T0)
    assert f.books["BTC-USD"].valid
    f.handle(ls[7], T0)                                   # skip messages 5-6: gap
    assert f.health["BTC-USD"].sequence_gaps == 1
    assert not f.books["BTC-USD"].valid and "BTC-USD" in f.resync
    snap = json.loads(ls[1]); snap["sequence_num"] = 10**6  # resubscribe delivers a fresh snapshot
    f.handle(json.dumps(snap), T0)
    assert f.books["BTC-USD"].valid


def test_coinbase_out_of_order_message_ignored():
    f = feed(CoinbaseFeed)
    ls = lines("coinbase_raw.jsonl")
    for l in ls[:6]:
        f.handle(l, T0)
    before = dict(f.books["BTC-USD"].bids)
    f.handle(ls[3], T0)                                    # replayed old message
    assert f.books["BTC-USD"].bids == before and f.health["BTC-USD"].sequence_gaps == 0


def _cb_trades(seq, trade_ids, t="2026-10-25T18:00:01Z"):
    return json.dumps({"channel": "market_trades", "timestamp": t, "sequence_num": seq, "events": [{"type": "update", "trades": [
        {"product_id": "BTC-USD", "trade_id": str(i), "price": "100", "size": "1", "time": t, "side": "BUY"} for i in trade_ids]}]})


def test_duplicate_trades_dropped():
    f = feed(CoinbaseFeed)
    a = f.handle(_cb_trades(1, [1, 2]), T0)
    b = f.handle(_cb_trades(2, [2, 3]), T0)                # trade 2 repeated (e.g. snapshot after reconnect)
    assert [t.trade_id for t in a + b] == ["1", "2", "3"] and f.duplicates_dropped == 1


def test_records_carry_event_and_receive_time():
    f = feed(CoinbaseFeed)
    rec = f.handle(_cb_trades(1, [9], "2026-10-25T17:59:59.123456789Z"), T0)[0]
    assert rec.event_time == datetime(2026, 10, 25, 17, 59, 59, 123456, tzinfo=timezone.utc)
    assert rec.received_at == T0


# ---- book integrity ----

def test_crossed_book_flagged():
    b = OrderBook()
    b.apply_snapshot([("100", "1")], [("101", "1")])
    b.apply_update("bid", "101.5", "1")
    b.finish_batch()
    assert not b.valid and "crossed" in b.problem


def test_negative_size_flagged():
    b = OrderBook()
    b.apply_snapshot([("100", "1")], [("101", "1")])
    b.apply_update("ask", "101", "-1")
    assert not b.valid


def test_kraken_checksum_matches_documented_example_formatting():
    b = OrderBook(depth=10)
    b.apply_snapshot([("45283.5", "0.10000000")], [("45285.2", "0.00100000")])
    # asks then bids, '.' removed, leading zeros stripped
    import zlib
    assert b.kraken_checksum(1, 8) == zlib.crc32(b"452852100000" b"452835" b"10000000")


def test_depth_within_band():
    b = OrderBook()
    b.apply_snapshot([("99.95", "2"), ("90", "100")], [("100.05", "3"), ("110", "100")])
    bid, ask = b.depth_within(10)                       # +-0.1% of mid 100
    assert bid == pytest.approx(199.9) and ask == pytest.approx(300.15)


# ---- health / staleness ----

def test_stale_detection():
    h = FeedHealth("coinbase", "BTC-USD")
    assert h.stale(T0, 5)                                # never received anything
    h.last_message_at = T0
    assert not h.stale(T0 + timedelta(seconds=4), 5)
    assert h.stale(T0 + timedelta(seconds=6), 5)


def test_parse_ts_nanoseconds():
    assert parse_ts("2026-10-25T18:11:58.839534911Z").microsecond == 839534


# ---- reconnect loop with a scripted fake connection ----

class FakeWS:
    def __init__(self, script):
        self.script, self.sent = list(script), []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, m):
        self.sent.append(json.loads(m))

    async def recv(self):
        if not self.script:
            raise ConnectionError("server closed")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_reconnects_with_backoff_and_resubscribes():
    ls = lines("coinbase_raw.jsonl")
    conns = [OSError("connect refused"), FakeWS(ls[:3]), FakeWS(ls[:3])]
    made, got = [], []

    def connect(url):
        c = conns.pop(0)
        if isinstance(c, Exception):
            raise c
        made.append(c)
        if not conns:
            f.stop()
        return c

    f = CoinbaseFeed(["BTC-USD"], connect=connect, measure_clock=False, rng=random.Random(1), on_record=got.append)
    f.backoff = lambda attempt: 0.001
    asyncio.run(asyncio.wait_for(f.run(), 5))
    assert len(made) == 2
    assert all(len([m for m in c.sent if m["type"] == "subscribe"]) == 4 for c in made)
    assert f.health["BTC-USD"].reconnects >= 2 and not f.health["BTC-USD"].connected


def test_backoff_is_capped_and_jittered():
    f = CoinbaseFeed(["BTC-USD"], connect=lambda u: None, measure_clock=False, rng=random.Random(0), max_backoff_s=30)
    ds = [f.backoff(a) for a in range(12)]
    assert all(d <= 30 for d in ds) and ds[-1] >= 15
    assert len({round(d, 6) for d in ds[8:]}) > 1           # jitter: capped delays still differ


def test_resync_request_sent_on_live_connection():
    ls = lines("kraken_raw.jsonl")
    snap_i = next(i for i, l in enumerate(ls) if '"type":"snapshot"' in l and '"channel":"book"' in l)
    bad = json.loads(next(l for l in ls[snap_i + 1:] if '"channel":"book"' in l)); bad["data"][0]["checksum"] += 1
    ws = FakeWS(ls[: snap_i + 1] + [json.dumps(bad), '{"channel":"heartbeat"}'])
    calls = []

    def connect(url):
        calls.append(url)
        if len(calls) > 1:              # second connection attempt: end the test
            f.stop()
            raise OSError("done")
        return ws

    f = KrakenFeed(["BTC-USD"], connect=connect, measure_clock=False)
    f.backoff = lambda a: 0.001
    asyncio.run(asyncio.wait_for(f.run(), 5))
    methods = [(m["method"], m["params"]["channel"]) for m in ws.sent]
    assert ("unsubscribe", "book") in methods and methods.count(("subscribe", "book")) == 2


def test_subscription_snapshot_trades_are_flagged():
    f = feed(CoinbaseFeed)
    snap = json.loads(_cb_trades(1, [5])); snap["events"][0]["type"] = "snapshot"
    (t,) = f.handle(json.dumps(snap), T0)
    assert t.from_snapshot


def test_kraken_depth_rounds_up_to_supported_level():
    assert KrakenFeed(["BTC-USD"], depth=50, connect=lambda u: None, measure_clock=False).books["BTC-USD"].depth == 100
