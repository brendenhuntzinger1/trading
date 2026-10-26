"""Local L2 order book with integrity checks.

Prices and sizes are kept as Decimal (parsed from the exchange's text) so
checksums are computed on exactly what the exchange sent.
"""
from __future__ import annotations

import zlib
from decimal import Decimal


class BookIntegrityError(Exception):
    pass


class OrderBook:
    def __init__(self, depth: int | None = None):
        self.depth = depth          # truncate to this many levels per side (Kraken requires it)
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.valid = False          # True only after a snapshot, False after any integrity failure
        self.problem: str | None = None

    def reset(self, reason: str) -> None:
        self.bids.clear()
        self.asks.clear()
        self.valid = False
        self.problem = reason

    def apply_snapshot(self, bids, asks) -> None:
        self.bids = {Decimal(p): Decimal(q) for p, q in bids if Decimal(q) > 0}
        self.asks = {Decimal(p): Decimal(q) for p, q in asks if Decimal(q) > 0}
        self.valid, self.problem = True, None
        self._truncate()
        self.check()

    def apply_update(self, side: str, price, qty) -> None:
        price, qty = Decimal(price), Decimal(qty)
        if qty < 0 or price <= 0:
            self._fail(f"non-positive level {side} {price} {qty}")
            return
        book = self.bids if side in ("bid", "buy", "bids") else self.asks
        if qty == 0:
            book.pop(price, None)
        else:
            book[price] = qty

    def finish_batch(self) -> None:
        """Call after all updates in one message: truncate, then verify."""
        self._truncate()
        self.check()

    def _truncate(self) -> None:
        if self.depth:
            for book, rev in ((self.bids, True), (self.asks, False)):
                for p in sorted(book, reverse=rev)[self.depth:]:
                    del book[p]

    def _fail(self, why: str) -> None:
        self.valid = False
        self.problem = why

    def check(self) -> bool:
        if not self.valid:
            return False
        if not self.bids or not self.asks:
            self._fail("empty side")
        elif self.best_bid()[0] >= self.best_ask()[0]:
            self._fail(f"crossed/locked book bid {self.best_bid()[0]} >= ask {self.best_ask()[0]}")
        return self.valid

    def best_bid(self):
        p = max(self.bids)
        return p, self.bids[p]

    def best_ask(self):
        p = min(self.asks)
        return p, self.asks[p]

    def levels(self, n: int = 10):
        bids = [(p, self.bids[p]) for p in sorted(self.bids, reverse=True)[:n]]
        asks = [(p, self.asks[p]) for p in sorted(self.asks)[:n]]
        return bids, asks

    def mid(self) -> float:
        return float((self.best_bid()[0] + self.best_ask()[0]) / 2)

    def spread_bps(self) -> float:
        b, a = self.best_bid()[0], self.best_ask()[0]
        return float((a - b) / ((a + b) / 2) * 10000)

    def depth_within(self, band_bps: float) -> tuple[float, float]:
        """Quote-currency notional resting within band_bps of mid, (bid, ask)."""
        mid = Decimal(str(self.mid()))
        band = Decimal(str(band_bps)) / Decimal(10000)
        lo, hi = mid * (1 - band), mid * (1 + band)
        bid = sum((p * q for p, q in self.bids.items() if p >= lo), Decimal(0))
        ask = sum((p * q for p, q in self.asks.items() if p <= hi), Decimal(0))
        return float(bid), float(ask)

    def kraken_checksum(self, price_dp: int | None = None, qty_dp: int | None = None) -> int:
        """CRC32 over the top 10 asks (low->high) then top 10 bids (high->low);
        each level is price then qty with the decimal point and leading zeros removed."""
        def fmt(x: Decimal, dp):
            s = f"{x:.{dp}f}" if dp is not None else format(x, "f")
            return s.replace(".", "").lstrip("0") or "0"
        bids, asks = self.levels(10)
        s = "".join(fmt(p, price_dp) + fmt(q, qty_dp) for p, q in asks)
        s += "".join(fmt(p, price_dp) + fmt(q, qty_dp) for p, q in bids)
        return zlib.crc32(s.encode()) & 0xFFFFFFFF
