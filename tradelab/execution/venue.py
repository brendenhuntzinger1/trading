"""Venue interface, public market data, and the live-trading guard."""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from .models import Fill, Order, ProductRules


class VenueRejected(Exception):
    """The venue definitively refused the order."""


class VenueUnknown(Exception):
    """No reliable answer (timeout, dropped connection, 5xx). The order may or
    may not exist. Reconcile before doing anything else."""


@dataclass(frozen=True)
class Book:
    asset: str
    bids: list[tuple[float, float]]     # best first
    asks: list[tuple[float, float]]
    event_time: datetime
    received_at: datetime

    @property
    def mid(self) -> float:
        return (self.bids[0][0] + self.asks[0][0]) / 2

    @property
    def spread_bps(self) -> float:
        return (self.asks[0][0] - self.bids[0][0]) / self.mid * 1e4

    def depth(self, side: str, band_bps: float) -> float:
        """Quote notional within band_bps of mid on the side a taker would consume."""
        levels, lim = (self.asks, self.mid * (1 + band_bps / 1e4)) if side == "buy" else (self.bids, self.mid * (1 - band_bps / 1e4))
        ok = (lambda p: p <= lim) if side == "buy" else (lambda p: p >= lim)
        return sum(p * s for p, s in levels if ok(p))

    def valid(self) -> bool:
        return bool(self.bids and self.asks) and self.bids[0][0] < self.asks[0][0] and \
            all(s > 0 for _, s in self.bids[:50] + self.asks[:50])


class Venue(Protocol):
    name: str
    def rules(self, asset: str) -> ProductRules: ...
    def place(self, order: Order) -> str: ...
    def cancel(self, client_id: str) -> None: ...
    def get_order(self, client_id: str) -> dict | None: ...
    def fills(self, client_id: str) -> list[Fill]: ...
    def balances(self) -> dict[str, float]: ...


class CoinbasePublic:
    """Unauthenticated REST market data (books, product rules, server time)."""
    BASE = "https://api.exchange.coinbase.com"

    def _get(self, path):
        req = urllib.request.Request(self.BASE + path, headers={"User-Agent": "tradelab-paper"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def book(self, asset: str, levels: int = 200) -> Book:
        d = self._get(f"/products/{asset}/book?level=2")
        received = datetime.now(timezone.utc)
        return Book(asset, [(float(p), float(s)) for p, s, _ in d["bids"][:levels]],
                    [(float(p), float(s)) for p, s, _ in d["asks"][:levels]],
                    datetime.fromisoformat(d["time"].replace("Z", "+00:00")[:26] + "+00:00"), received)

    def rules(self, asset: str) -> ProductRules:
        d = self._get(f"/products/{asset}")
        if d.get("trading_disabled") or d.get("status") != "online":
            raise VenueRejected(f"{asset} not tradable: {d.get('status')}")
        return ProductRules(asset, Decimal(d["base_increment"]), Decimal(d["quote_increment"]), Decimal(d["min_market_funds"]))

    def clock_offset_ms(self) -> float:
        before = datetime.now(timezone.utc)
        d = self._get("/time")
        after = datetime.now(timezone.utc)
        local_mid = before + (after - before) / 2
        return (d["epoch"] - local_mid.timestamp()) * 1000


def live_trading_allowed(config_hash: str) -> bool:
    """Live orders require a human-written approval naming the exact config hash.
    No live venue adapter is implemented yet; this exists so that one cannot be
    wired in without the guard."""
    return os.environ.get("TRADELAB_LIVE_APPROVED_CONFIG") == config_hash and \
        os.environ.get("TRADELAB_MODE") == "live"
