"""Deterministic pre-trade checks and circuit breakers.

Three distinct actions, never conflated:
  HALT_NEW        refuse orders that increase exposure (reductions still allowed)
  CANCEL_PENDING  cancel every working order
  REDUCE          cut existing positions (only where a policy explicitly says so)
No breaker liquidates everything automatically. During an outage positions are
held, not dumped into a market we cannot see.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .limits import RiskLimits


class Action(str, Enum):
    HALT_NEW = "halt_new"
    CANCEL_PENDING = "cancel_pending"
    REDUCE = "reduce"


class Breaker(str, Enum):
    STALE_DATA = "stale_data"
    EXCHANGE_OUTAGE = "exchange_outage"
    REPEATED_REJECTIONS = "repeated_rejections"
    ABNORMAL_VOLATILITY = "abnormal_volatility"
    MODEL_FAILURE = "model_failure"
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"
    DAILY_LOSS = "daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    EVENT_FLAG = "event_flag"


# breaker -> (actions, latches until a human resets?)
POLICY: dict[Breaker, tuple[frozenset, bool]] = {
    Breaker.STALE_DATA: (frozenset({Action.HALT_NEW, Action.CANCEL_PENDING}), False),
    Breaker.EXCHANGE_OUTAGE: (frozenset({Action.HALT_NEW, Action.CANCEL_PENDING}), False),
    Breaker.REPEATED_REJECTIONS: (frozenset({Action.HALT_NEW, Action.CANCEL_PENDING}), True),
    Breaker.ABNORMAL_VOLATILITY: (frozenset({Action.HALT_NEW}), False),
    Breaker.MODEL_FAILURE: (frozenset({Action.HALT_NEW, Action.CANCEL_PENDING}), False),
    Breaker.RECONCILIATION_MISMATCH: (frozenset({Action.HALT_NEW, Action.CANCEL_PENDING}), True),
    Breaker.DAILY_LOSS: (frozenset({Action.HALT_NEW}), False),       # clears next UTC day
    Breaker.MAX_DRAWDOWN: (frozenset({Action.HALT_NEW}), True),      # REDUCE added only if configured
    Breaker.EVENT_FLAG: (frozenset({Action.HALT_NEW}), False),
}


@dataclass
class MarketSnapshot:
    price: float
    spread_bps: float
    depth_notional: float            # ask-side notional within depth_band_bps (what a buy consumes)
    received_at: datetime
    depth_bid: float | None = None   # bid-side notional (what a sell consumes); falls back to depth_notional
    move_1h: float = 0.0
    vol_ratio: float = 1.0           # short-term vol / 30d median vol


@dataclass
class AccountState:
    equity: float
    start_of_day_equity: float
    peak_equity: float
    weights: dict[str, float]                       # current asset weights
    open_orders: int = 0
    orders_today: int = 0
    turnover_30d: float = 0.0                       # traded notional / equity
    rejections: list[datetime] = field(default_factory=list)
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderIntent:
    asset: str
    notional: float          # + buy / - sell, quote currency
    strategy: str
    reason: str


@dataclass
class Decision:
    approved: bool
    notional: float
    reasons: list[str]
    breakers: list[str]


@dataclass
class BreakerState:
    active: dict[Breaker, str] = field(default_factory=dict)     # breaker -> detail
    latched: set[Breaker] = field(default_factory=set)
    day: str | None = None

    def actions(self, limits: RiskLimits) -> set[Action]:
        acts: set[Action] = set()
        for b in self.active:
            acts |= POLICY[b][0]
            if b is Breaker.MAX_DRAWDOWN and limits.reduce_on_max_drawdown > 0:
                acts.add(Action.REDUCE)
        return acts


class RiskEngine:
    def __init__(self, limits: RiskLimits, config_hash: str = "unknown", latched: dict[str, str] | None = None):
        """latched: breakers still latched from earlier runs (loaded from the journal).
        They can only add restrictions; clearing one needs reset() by a named person."""
        self.limits = limits
        self.config_hash = config_hash
        self.state = BreakerState()
        for name, detail in (latched or {}).items():
            b = Breaker(name)
            self.state.active[b] = detail
            self.state.latched.add(b)

    # --- circuit breakers -------------------------------------------------
    def evaluate(self, now: datetime, acct: AccountState, markets: dict[str, MarketSnapshot],
                 venue_up: bool = True, model_ok: bool = True, recon_diff: float = 0.0,
                 event_flags: list[str] | None = None) -> set[Action]:
        L = self.limits
        day = now.strftime("%Y-%m-%d")
        if self.state.day != day:          # daily-loss breaker resets at the UTC day boundary
            self.state.day = day
            self.state.active.pop(Breaker.DAILY_LOSS, None)
        trips: dict[Breaker, str] = {}
        stale = [a for a, m in markets.items() if (now - m.received_at).total_seconds() > L.stale_data_s]
        if stale:
            trips[Breaker.STALE_DATA] = f"stale: {stale}"
        if not venue_up:
            trips[Breaker.EXCHANGE_OUTAGE] = "venue unreachable or degraded"
        recent = [t for t in acct.rejections if now - t < timedelta(hours=1)]
        if len(recent) >= L.max_rejections_1h:
            trips[Breaker.REPEATED_REJECTIONS] = f"{len(recent)} rejections in 1h"
        wild = [a for a, m in markets.items() if abs(m.move_1h) > L.abnormal_move_1h or m.vol_ratio > L.abnormal_vol_multiple]
        if wild:
            trips[Breaker.ABNORMAL_VOLATILITY] = f"abnormal moves: {wild}"
        if not model_ok:
            trips[Breaker.MODEL_FAILURE] = "strategy output missing/invalid"
        tol = max(L.recon_tolerance_abs, L.recon_tolerance_frac * acct.equity)
        if abs(recon_diff) > tol:
            trips[Breaker.RECONCILIATION_MISMATCH] = f"local vs exchange differ by {recon_diff:.2f}"
        if acct.equity < acct.start_of_day_equity * (1 - L.daily_loss_limit):
            trips[Breaker.DAILY_LOSS] = f"down {1 - acct.equity / acct.start_of_day_equity:.1%} today"
        if acct.equity < acct.peak_equity * (1 - L.max_drawdown_limit):
            trips[Breaker.MAX_DRAWDOWN] = f"drawdown {1 - acct.equity / acct.peak_equity:.1%}"
        if event_flags and L.block_entries_on_event_flags:
            trips[Breaker.EVENT_FLAG] = "; ".join(event_flags)

        # non-latching breakers clear when the condition clears; latching ones need reset()
        for b in list(self.state.active):
            if b not in trips and b not in self.state.latched and b is not Breaker.DAILY_LOSS:
                del self.state.active[b]
        for b, detail in trips.items():
            self.state.active[b] = detail
            if POLICY[b][1]:
                self.state.latched.add(b)
        return self.state.actions(L)

    def reset(self, breaker: Breaker, operator: str, note: str) -> str:
        """Human acknowledgement for latched breakers. Returns an audit line."""
        if not operator or not note:
            raise ValueError("reset requires an operator name and a note")
        self.state.latched.discard(breaker)
        self.state.active.pop(breaker, None)
        return f"{breaker.value} reset by {operator}: {note}"

    def reduce_targets(self, weights: dict[str, float]) -> dict[str, float]:
        """Positions to hold when REDUCE is active (explicit policy only)."""
        f = self.limits.reduce_on_max_drawdown
        return {a: w * f for a, w in weights.items()}

    # --- pre-trade checks -------------------------------------------------
    def check(self, intent: OrderIntent, acct: AccountState, market: MarketSnapshot | None) -> Decision:
        L = self.limits
        reasons: list[str] = []
        acts = self.state.actions(L)
        increases = intent.notional > 0          # long-only spot: buys increase exposure
        n = intent.notional
        if market is None:
            return Decision(False, 0.0, ["no market data for asset"], [b.value for b in self.state.active])
        if increases and Action.HALT_NEW in acts:
            return Decision(False, 0.0, ["breaker active: no new exposure"], [b.value for b in self.state.active])
        if acct.open_orders >= L.max_open_orders:
            reasons.append("too many open orders")
        if acct.orders_today >= L.max_orders_per_day:
            reasons.append("daily order count reached")
        if increases and acct.turnover_30d + abs(n) / acct.equity > L.max_turnover_30d:
            reasons.append("30-day turnover limit")
        if market.spread_bps > L.max_spread_bps:
            reasons.append(f"spread {market.spread_bps:.1f}bp > {L.max_spread_bps}")
        if reasons:
            return Decision(False, 0.0, reasons, [b.value for b in self.state.active])

        notes = []
        if abs(n) > L.max_order_notional:
            n = L.max_order_notional * (1 if n > 0 else -1)
            notes.append("clipped to max order size")
        depth = market.depth_notional if n > 0 or market.depth_bid is None else market.depth_bid
        if abs(n) > L.max_order_vs_depth * depth:
            n = L.max_order_vs_depth * depth * (1 if n > 0 else -1)
            notes.append("clipped to available depth")
        if increases:
            w = acct.weights.get(intent.asset, 0.0)
            room_pos = L.max_position_weight - w
            room_gross = L.max_gross_exposure - sum(acct.weights.values())
            cluster = [a for a in acct.weights if a == intent.asset or
                       acct.correlations.get(tuple(sorted((a, intent.asset))), 0.0) > L.cluster_corr]
            room_cluster = L.max_cluster_exposure - sum(acct.weights[a] for a in cluster if a in acct.weights)
            room = min(room_pos, room_gross, room_cluster) * acct.equity
            if room <= 0:
                return Decision(False, 0.0, ["exposure limit reached"], [b.value for b in self.state.active])
            if n > room:
                n = room
                notes.append("clipped to exposure limits")
        if abs(n) < L.min_order_notional:
            return Decision(False, 0.0, notes + ["below minimum order size after limits"], [b.value for b in self.state.active])
        return Decision(True, n, notes or ["within limits"], [b.value for b in self.state.active])
