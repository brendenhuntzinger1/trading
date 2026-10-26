"""Core intraday types: signals, orders, positions, trades."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Signal:
    """A setup's proposal. The engine decides whether, and how big."""
    setup: str
    symbol: str
    side: str                    # "long" (default) | "short" (only if the market config allows)
    entry: str                   # "next_open" | "at_open" (just after the opening print) | "limit"
    reason: str
    stop: float | None = None
    target: float | None = None
    limit: float | None = None
    limit_valid_until: datetime | None = None
    deadline: datetime | None = None          # maximum holding time
    exit_at_close: bool = False               # stocks: exit at the closing auction
    weight: float | None = None               # fixed-weight setups; otherwise sized by risk to the stop
    features: dict = field(default_factory=dict)


@dataclass
class Order:
    signal: Signal
    notional: float
    created_at: datetime
    kind: str                    # next_open | at_open | limit


@dataclass
class Position:
    signal: Signal
    qty: float
    entry_px: float
    entry_time: datetime
    entry_cost: float            # quote currency


@dataclass(frozen=True)
class Trade:
    setup: str
    symbol: str
    side: str
    entry_time: datetime
    entry_px: float
    exit_time: datetime
    exit_px: float
    exit_reason: str
    qty: float
    gross_pnl: float
    cost: float

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.cost

    @property
    def gross_ret(self) -> float:
        return self.gross_pnl / (self.qty * self.entry_px)

    @property
    def net_ret(self) -> float:
        return self.net_pnl / (self.qty * self.entry_px)


@dataclass(frozen=True)
class Decision:
    at: datetime
    setup: str
    symbol: str
    outcome: str                 # approved | rejected | skipped
    reasons: tuple[str, ...]
    notional: float = 0.0
