from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import Enum


class Status(str, Enum):
    NEW = "new"                    # persisted, not yet sent
    SUBMITTED = "submitted"        # sent, ack received, working
    PARTIAL = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"        # may carry a partial fill
    REJECTED = "rejected"
    UNKNOWN = "unknown"            # sent, no reliable answer: reconcile before any retry
    NOT_FOUND = "not_found"        # reconciled: the venue never received it

    @property
    def terminal(self) -> bool:
        return self in {Status.FILLED, Status.CANCELLED, Status.REJECTED, Status.NOT_FOUND}


@dataclass(frozen=True)
class ProductRules:
    symbol: str
    base_increment: Decimal
    quote_increment: Decimal
    min_market_funds: Decimal

    def round_size(self, qty: float) -> Decimal:
        return Decimal(str(qty)).quantize(self.base_increment, rounding=ROUND_DOWN)

    def round_price(self, px: float) -> Decimal:
        return Decimal(str(px)).quantize(self.quote_increment, rounding=ROUND_DOWN)


@dataclass
class Order:
    client_id: str
    account: str
    asset: str
    side: str                      # buy | sell
    kind: str                      # market | limit
    quote_size: float | None       # market buys are sized in quote currency
    base_size: float | None        # sells and limit orders in base units
    limit_price: float | None
    decision_id: str
    attempt: int = 1
    status: Status = Status.NEW
    venue_id: str | None = None
    filled_base: float = 0.0
    filled_quote: float = 0.0
    fees: float = 0.0
    reject_reason: str | None = None
    decided_at: datetime | None = None
    submitted_at: datetime | None = None
    acked_at: datetime | None = None
    first_fill_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def avg_price(self) -> float | None:
        return self.filled_quote / self.filled_base if self.filled_base else None


@dataclass(frozen=True)
class Fill:
    fill_id: str
    client_id: str
    asset: str
    side: str
    base: float
    price: float
    fee: float
    at: datetime


def client_order_id(decision_id: str, asset: str, attempt: int = 1) -> str:
    """Deterministic: the same decision always maps to the same id, so a resend
    after a crash or timeout cannot create a second order. The side is deliberately
    not part of it: a same-day re-run whose target flipped must not trade again."""
    h = hashlib.sha256(f"{decision_id}|{asset}|{attempt}".encode()).hexdigest()
    return f"tl-{h[:24]}"
