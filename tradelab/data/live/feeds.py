"""Public WebSocket market-data feeds (Coinbase Advanced Trade, Kraken v2).

Each feed keeps local L2 books and per-symbol FeedHealth, and emits normalized
records (Trade, TopOfBook, VenueNotice) to a callback. `handle()` is a pure
message -> records step so it can be tested from fixtures without a network;
`run()` owns the connection: subscribe, idle watchdog, resync on integrity
failure, and reconnect with jittered exponential backoff.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Callable, Iterable

from .book import OrderBook
from .clock import Clock, measure_offset
from .types import BookSample, DepthSummary, FeedHealth, TopOfBook, Trade, VenueNotice

log = logging.getLogger(__name__)


def parse_ts(s: str) -> datetime:
    """RFC3339 with up to nanoseconds -> aware datetime (microsecond precision)."""
    s = s.replace("Z", "+00:00")
    if "." in s:
        head, rest = s.split(".", 1)
        frac, tz = rest[:-6], rest[-6:]
        s = f"{head}.{frac[:6].ljust(6, '0')}{tz}"
    return datetime.fromisoformat(s)


class _Dedup:
    """Bounded memory of recently seen ids."""
    def __init__(self, size: int = 20000):
        self.seen, self.order = set(), deque()
        self.size = size

    def first_time(self, key) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        self.order.append(key)
        if len(self.order) > self.size:
            self.seen.discard(self.order.popleft())
        return True


class BaseFeed:
    venue = ""
    url = ""
    idle_timeout_s = 15.0       # no message for this long -> treat connection as dead

    def __init__(self, symbols: Iterable[str], *, depth: int = 50, on_record: Callable | None = None,
                 clock: Clock | None = None, connect=None, max_backoff_s: float = 60.0,
                 rng: random.Random | None = None, measure_clock: bool = True):
        self.symbols = list(symbols)
        self.depth = depth
        self.on_record = on_record or (lambda rec: None)
        self.clock = clock or Clock()
        self.books = {s: OrderBook(self._book_depth()) for s in self.symbols}
        self.health = {s: FeedHealth(self.venue, s) for s in self.symbols}
        self.dupes = _Dedup()
        self.duplicates_dropped = 0
        self.resync: set[str] = set()   # symbols whose book must be re-snapshotted
        self.max_backoff_s = max_backoff_s
        self.rng = rng or random.Random()
        self.measure_clock = measure_clock
        if connect is None:
            import websockets
            connect = lambda url: websockets.connect(url, max_size=2 ** 24, open_timeout=15, ping_interval=20)
        self._connect = connect
        self._stop = asyncio.Event()

    # ---- hooks for subclasses ----
    def _book_depth(self) -> int | None:
        return None

    async def _subscribe(self, ws) -> None:
        raise NotImplementedError

    async def _resubscribe_book(self, ws, symbols: list[str]) -> None:
        raise NotImplementedError

    def handle(self, raw: str, received_at: datetime) -> list:
        raise NotImplementedError

    # ---- shared machinery ----
    def backoff(self, attempt: int, base: float = 0.5) -> float:
        """Full-range jitter between 50% and 100% of the capped exponential delay."""
        cap = min(self.max_backoff_s, base * 2 ** attempt)
        return cap * (0.5 + 0.5 * self.rng.random())

    def stop(self) -> None:
        self._stop.set()

    def _touch(self, symbols, received_at: datetime, event_time: datetime | None) -> None:
        for s in symbols:
            h = self.health.get(s)
            if h:
                h.last_message_at = received_at
                if event_time:
                    h.last_event_at = event_time

    def _invalidate(self, symbol: str, why: str) -> None:
        self.books[symbol].reset(why)
        self.health[symbol].book_valid = False
        self.health[symbol].notes.append(why)
        self.resync.add(symbol)
        log.warning("%s %s book invalid: %s", self.venue, symbol, why)

    def _trade(self, rec: Trade) -> Trade | None:
        if not self.dupes.first_time((rec.symbol, rec.trade_id)):
            self.duplicates_dropped += 1
            return None
        return rec

    def top(self, symbol: str) -> TopOfBook | None:
        b, h = self.books[symbol], self.health[symbol]
        if not b.valid:
            return None
        (bp, bq), (ap, aq) = b.best_bid(), b.best_ask()
        return TopOfBook(self.venue, symbol, float(bp), float(bq), float(ap), float(aq), h.last_event_at, h.last_message_at)

    def depth_summary(self, symbol: str, band_bps: float = 10.0) -> DepthSummary | None:
        b, h = self.books[symbol], self.health[symbol]
        if not b.valid:
            return None
        bid, ask = b.depth_within(band_bps)
        return DepthSummary(self.venue, symbol, band_bps, bid, ask, h.last_event_at, h.last_message_at)

    def sample(self, symbol: str, levels: int = 10) -> BookSample:
        b, h = self.books[symbol], self.health[symbol]
        bids, asks = b.levels(levels) if b.valid else ([], [])
        f = lambda side: tuple((float(p), float(q)) for p, q in side)
        return BookSample(self.venue, symbol, f(bids), f(asks), b.valid, h.last_event_at, h.last_message_at)

    async def _calibrate(self) -> None:
        if not self.measure_clock:
            return
        try:
            off, rtt = await asyncio.to_thread(measure_offset, self.venue)
            corrected = self.clock.calibrate(off, rtt, resolution_ms=1000 if self.venue == "kraken" else 0)
            for h in self.health.values():
                h.clock_offset_ms = off
                if corrected:
                    h.notes.append(f"clock corrected by {off:.0f} ms (rtt {rtt:.0f} ms)")
        except Exception as e:  # clock check failing must not stop market data
            for h in self.health.values():
                h.notes.append(f"clock offset unavailable: {e!r}")

    async def run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._calibrate()
                async with self._connect(self.url) as ws:
                    await self._subscribe(ws)
                    for h in self.health.values():
                        h.connected = True
                    attempt = 0
                    while not self._stop.is_set():
                        raw = await asyncio.wait_for(ws.recv(), timeout=self.idle_timeout_s)
                        for rec in self.handle(raw, self.clock.now()):
                            self.on_record(rec)
                        if self.resync:
                            todo, self.resync = sorted(self.resync), set()
                            await self._resubscribe_book(ws, todo)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # network, protocol, idle timeout: all handled by reconnecting
                log.warning("%s feed error %r; reconnecting", self.venue, e)
            for s, h in self.health.items():
                h.connected = False
                self.books[s].reset("disconnected")
                h.book_valid = False
            if self._stop.is_set():
                break
            for h in self.health.values():
                h.reconnects += 1
            delay = self.backoff(attempt)
            attempt += 1
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass


class CoinbaseFeed(BaseFeed):
    """wss://advanced-trade-ws.coinbase.com, public channels (no auth needed).

    `sequence_num` counts every message on the connection across channels
    (verified live 2026-10-25), so a jump means messages were lost somewhere on
    this connection: all books are invalidated and re-snapshotted."""
    venue = "coinbase"
    url = "wss://advanced-trade-ws.coinbase.com"
    CHANNELS = ("heartbeats", "level2", "market_trades", "ticker")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.last_seq: int | None = None

    async def _subscribe(self, ws) -> None:
        self.last_seq = None
        for ch in self.CHANNELS:   # one channel per message; must be sent within 5 s of connecting
            await ws.send(json.dumps({"type": "subscribe", "product_ids": self.symbols, "channel": ch}))

    async def _resubscribe_book(self, ws, symbols) -> None:
        for t in ("unsubscribe", "subscribe"):
            await ws.send(json.dumps({"type": t, "product_ids": symbols, "channel": "level2"}))

    def handle(self, raw: str, received_at: datetime) -> list:
        m = json.loads(raw)
        out = []
        seq = m.get("sequence_num")
        if seq is not None:
            if self.last_seq is not None and seq <= self.last_seq:
                return out                                  # replayed / out of order: ignore
            if self.last_seq is not None and seq != self.last_seq + 1:
                for s in self.symbols:
                    self.health[s].sequence_gaps += 1
                    self._invalidate(s, f"sequence gap {self.last_seq} -> {seq}")
            self.last_seq = seq
        ch = m.get("channel")
        msg_time = parse_ts(m["timestamp"]) if "timestamp" in m else None
        if ch == "heartbeats":
            self._touch(self.symbols, received_at, msg_time)
        elif ch == "l2_data":
            for ev in m.get("events", []):
                s = ev.get("product_id")
                if s not in self.books:
                    continue
                book = self.books[s]
                ups = ev.get("updates", [])
                last_evt = parse_ts(ups[-1]["event_time"]) if ups else msg_time
                if ev.get("type") == "snapshot":
                    book.apply_snapshot([(u["price_level"], u["new_quantity"]) for u in ups if u["side"] == "bid"],
                                        [(u["price_level"], u["new_quantity"]) for u in ups if u["side"] != "bid"])
                elif book.valid:
                    for u in ups:
                        book.apply_update("bid" if u["side"] == "bid" else "ask", u["price_level"], u["new_quantity"])
                    book.finish_batch()
                if ev.get("type") == "snapshot" or book.valid:
                    self.health[s].book_valid = book.valid
                    if not book.valid:
                        self._invalidate(s, book.problem or "invalid")
                self._touch([s], received_at, last_evt)
        elif ch == "market_trades":
            for ev in m.get("events", []):
                for t in ev.get("trades", []):
                    if t.get("product_id") not in self.health:
                        continue
                    rec = self._trade(Trade(self.venue, t["product_id"], str(t["trade_id"]), float(t["price"]),
                                            float(t["size"]), t["side"].lower(), parse_ts(t["time"]), received_at,
                                            ev.get("type") == "snapshot"))
                    if rec:
                        out.append(rec)
                        self._touch([rec.symbol], received_at, rec.event_time)
        elif ch == "ticker":
            for ev in m.get("events", []):
                for t in ev.get("tickers", []):
                    s = t.get("product_id")
                    if s in self.health and t.get("best_bid") and t.get("best_ask"):
                        out.append(TopOfBook(self.venue, s, float(t["best_bid"]), float(t.get("best_bid_quantity") or 0),
                                             float(t["best_ask"]), float(t.get("best_ask_quantity") or 0), msg_time, received_at))
                        self._touch([s], received_at, msg_time)
        return out


def _kraken_symbol(s: str) -> str:
    return s.replace("-", "/")


def _canon(s: str) -> str:
    return s.replace("/", "-")


class KrakenFeed(BaseFeed):
    """wss://ws.kraken.com/v2 public channels. Book integrity is proven by
    Kraken's CRC32 checksum on every snapshot/update."""
    venue = "kraken"
    url = "wss://ws.kraken.com/v2"
    # (price decimals, qty decimals) for checksum formatting, from REST AssetPairs
    PRECISION = {"BTC-USD": (1, 8), "ETH-USD": (2, 8), "SOL-USD": (2, 8)}

    def _book_depth(self) -> int:
        """Smallest depth Kraken offers that covers the request (checksum always uses the top 10)."""
        return next((d for d in (10, 25, 100, 500, 1000) if d >= self.depth), 1000)

    async def _subscribe(self, ws) -> None:
        syms = [_kraken_symbol(s) for s in self.symbols]
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "book", "symbol": syms, "depth": self._book_depth()}}))
        for ch in ("trade", "ticker"):
            await ws.send(json.dumps({"method": "subscribe", "params": {"channel": ch, "symbol": syms}}))

    async def _resubscribe_book(self, ws, symbols) -> None:
        syms = [_kraken_symbol(s) for s in symbols]
        await ws.send(json.dumps({"method": "unsubscribe", "params": {"channel": "book", "symbol": syms, "depth": self._book_depth()}}))
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "book", "symbol": syms, "depth": self._book_depth()}}))

    def handle(self, raw: str, received_at: datetime) -> list:
        m = json.loads(raw, parse_float=Decimal)   # Decimal keeps the exact digits for the checksum
        out = []
        ch = m.get("channel")
        if ch == "heartbeat":
            self._touch(self.symbols, received_at, None)
        elif ch == "status":
            for d in m.get("data", []):
                out.append(VenueNotice(self.venue, d.get("system", "unknown"), "system status", None, None, (),
                                       None, received_at, received_at))
                for mt in d.get("upcoming_maintenance") or []:
                    out.append(VenueNotice(self.venue, "maintenance_scheduled", mt.get("title", ""),
                                           parse_ts(mt["expected_start_utc"]) if mt.get("expected_start_utc") else None,
                                           parse_ts(mt["expected_end_utc"]) if mt.get("expected_end_utc") else None,
                                           tuple(mt.get("affected_services") or ()), mt.get("source_url"),
                                           received_at, received_at))
        elif ch == "book":
            for d in m.get("data", []):
                s = _canon(d["symbol"])
                if s not in self.books:
                    continue
                book = self.books[s]
                evt = parse_ts(d["timestamp"]) if d.get("timestamp") else None
                if m.get("type") == "snapshot":
                    book.apply_snapshot([(l["price"], l["qty"]) for l in d["bids"]], [(l["price"], l["qty"]) for l in d["asks"]])
                elif not book.valid:
                    continue                       # waiting for the resync snapshot
                else:
                    for l in d.get("bids", []):
                        book.apply_update("bid", l["price"], l["qty"])
                    for l in d.get("asks", []):
                        book.apply_update("ask", l["price"], l["qty"])
                    book.finish_batch()
                if book.valid and "checksum" in d:
                    if book.kraken_checksum(*self.PRECISION.get(s, (None, None))) != int(d["checksum"]):
                        self.health[s].checksum_failures += 1
                        self._invalidate(s, "checksum mismatch")
                elif not book.valid:
                    self._invalidate(s, book.problem or "invalid")
                self.health[s].book_valid = book.valid
                self._touch([s], received_at, evt)
        elif ch == "trade":
            for t in m.get("data", []):
                rec = self._trade(Trade(self.venue, _canon(t["symbol"]), str(t["trade_id"]), float(t["price"]),
                                        float(t["qty"]), t["side"], parse_ts(t["timestamp"]), received_at,
                                        m.get("type") == "snapshot"))
                if rec and rec.symbol in self.health:
                    out.append(rec)
                    self._touch([rec.symbol], received_at, rec.event_time)
        elif ch == "ticker":
            for t in m.get("data", []):
                s = _canon(t["symbol"])
                if s in self.health:
                    evt = parse_ts(t["timestamp"]) if t.get("timestamp") else received_at
                    out.append(TopOfBook(self.venue, s, float(t["bid"]), float(t["bid_qty"]), float(t["ask"]),
                                         float(t["ask_qty"]), evt, received_at))
                    self._touch([s], received_at, evt)
        return out


FEEDS = {"coinbase": CoinbaseFeed, "kraken": KrakenFeed}


def make_feed(symbols, venue: str = "coinbase", **kw) -> BaseFeed:
    return FEEDS[venue](symbols, **kw)
