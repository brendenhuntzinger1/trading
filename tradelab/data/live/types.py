"""Shared live market-data types. Every record carries the exchange's event
time AND our receive time (both UTC, timezone-aware); decisions may only use
records whose received_at <= decision time."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Trade:
    venue: str
    symbol: str            # canonical, e.g. "BTC-USD"
    trade_id: str
    price: float
    size: float
    side: str              # taker side: "buy" | "sell"
    event_time: datetime   # exchange timestamp
    received_at: datetime  # our clock, after clock-offset correction
    from_snapshot: bool = False  # delivered in a subscribe snapshot (historical), not as a live print


@dataclass(frozen=True)
class TopOfBook:
    venue: str
    symbol: str
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    event_time: datetime
    received_at: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 1e4


@dataclass(frozen=True)
class DepthSummary:
    """Liquidity available within `band_bps` of mid, in quote currency."""
    venue: str
    symbol: str
    band_bps: float
    bid_notional: float
    ask_notional: float
    event_time: datetime
    received_at: datetime


@dataclass
class FeedHealth:
    venue: str
    symbol: str
    connected: bool = False
    last_message_at: datetime | None = None     # our receive time of the last message
    last_event_at: datetime | None = None       # exchange time of the last message
    reconnects: int = 0
    sequence_gaps: int = 0
    checksum_failures: int = 0
    book_valid: bool = False                    # False until a snapshot is applied and verified
    clock_offset_ms: float | None = None        # exchange_time - local_time, from the venue's time endpoint
    notes: list[str] = field(default_factory=list)

    def stale(self, now: datetime, max_age_s: float) -> bool:
        return self.last_message_at is None or (now - self.last_message_at).total_seconds() > max_age_s


@dataclass(frozen=True)
class VenueNotice:
    """Exchange status / maintenance announcements, as published by the venue."""
    venue: str
    status: str                 # e.g. "online", "maintenance", "cancel_only", "post_only", "limit_only"
    title: str
    starts_at: datetime | None
    ends_at: datetime | None
    affected: tuple[str, ...]
    source_url: str | None
    event_time: datetime
    received_at: datetime


@dataclass(frozen=True)
class BookSample:
    """Point-in-time sample of a locally maintained order book (for recording)."""
    venue: str
    symbol: str
    bids: tuple[tuple[float, float], ...]   # best first, (price, size)
    asks: tuple[tuple[float, float], ...]
    valid: bool
    event_time: datetime
    received_at: datetime
