"""Intraday trading engine (paper and replay share this code).

Per execution bar (in this order):
  1. fill pending entries (next_open at the bar open; limits only if price trades through)
  2. manage open positions on the bar: stop before target when both are touched,
     stops gapped through fill at the open, time exits at the bar close,
     stock positions always close at the session close
  3. mark equity
  4. ask setups for signals using only data available at the bar's end,
     then approve/size/reject each one against the risk limits
Setups propose; the engine decides. A setup cannot change limits or sizing caps.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime

from .costs import Costs
from .limits import IntradayLimits
from .model import Decision, Order, Position, Signal, Trade


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class EngineState:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    pending: list[Order] = field(default_factory=list)
    marks: dict[str, float] = field(default_factory=dict)
    day: str | None = None
    day_start_equity: float = 0.0
    entries_today: int = 0
    halted_today: str | None = None              # reason new entries are blocked until the next day
    blocked: str | None = None                   # temporary block set by the runner (stale data, outage)
    day_trades: deque = field(default_factory=lambda: deque(maxlen=64))   # (session day) per round trip


class Engine:
    def __init__(self, limits: IntradayLimits, setups: list, costs: dict[str, Costs], sessions, equity: float):
        self.L, self.setups, self.costs, self.sessions = limits, setups, costs, sessions
        self.initial = equity
        self.s = EngineState(cash=equity, day_start_equity=equity)
        self.trades: list[Trade] = []
        self.decisions: list[Decision] = []
        self.equity_curve: list[tuple[datetime, float]] = []

    # ---- accounting -------------------------------------------------------
    def equity(self) -> float:
        return self.s.cash + sum(p.qty * self.s.marks.get(sym, p.entry_px) * (1 if p.signal.side == "long" else -1)
                                 + (0 if p.signal.side == "long" else 2 * p.qty * p.entry_px)
                                 for sym, p in self.s.positions.items())

    def gross(self) -> float:
        eq = self.equity()
        return sum(p.qty * self.s.marks.get(sym, p.entry_px) for sym, p in self.s.positions.items()) / eq if eq > 0 else 0

    def _new_day(self, t: datetime):
        day = self.sessions.day_key(t)
        if day != self.s.day:
            self.s.day, self.s.entries_today, self.s.halted_today = day, 0, None
            self.s.day_start_equity = self.equity()

    def _open(self, o: Order, px: float, t: datetime):
        sig = o.signal
        c = self.costs[sig.setup]
        qty = o.notional / px
        cost = o.notional * c.entry
        self.s.cash -= (o.notional if sig.side == "long" else o.notional) + cost   # shorts post notional as collateral
        self.s.positions[sig.symbol] = Position(sig, qty, px, t, cost)
        self.s.marks[sig.symbol] = px
        self.s.entries_today += 1

    def _close(self, sym: str, px: float, t: datetime, reason: str, stop_hit: bool = False):
        p = self.s.positions.pop(sym)
        c = self.costs[p.signal.setup]
        slip = c.stop_slippage if stop_hit else 0.0
        px = px * (1 - slip) if p.signal.side == "long" else px * (1 + slip)
        sign = 1 if p.signal.side == "long" else -1
        gross = sign * p.qty * (px - p.entry_px)
        exit_cost = p.qty * px * c.exit
        self.s.cash += p.qty * p.entry_px + gross - exit_cost
        self.trades.append(Trade(p.signal.setup, sym, p.signal.side, p.entry_time, p.entry_px, t, px, reason,
                                 p.qty, gross, p.entry_cost + exit_cost))
        if self.sessions.day_key(p.entry_time) == self.sessions.day_key(t):
            self.s.day_trades.append(self.sessions.day_key(t))

    # ---- session-open hook (stocks): signals priced off the opening print ----
    def process_open(self, t: datetime, opens: dict[str, float], ctx) -> None:
        self._new_day(t)
        for setup in self.setups:
            if not hasattr(setup, "scan_open"):
                continue
            for sig in setup.scan_open(t, opens, ctx):
                o = self._approve(sig, t, opens.get(sig.symbol))
                if o:
                    self._open(o, opens[sig.symbol], t)

    # ---- per execution bar -------------------------------------------------
    def process_bar(self, start: datetime, end: datetime, bars: dict[str, Bar], ctx) -> None:
        self._new_day(start)
        # 1. pending entries
        still = []
        for o in self.s.pending:
            b = bars.get(o.signal.symbol)
            sig = o.signal
            if o.kind == "next_open":
                if b is None:
                    self._decide(start, sig, "rejected", ["no bar to fill the entry (venue gap)"])
                    continue
                if sig.symbol in self.s.positions:
                    continue
                self._open(o, b.open, start)
            elif o.kind == "limit":
                if sig.limit_valid_until and start >= sig.limit_valid_until:
                    self._decide(start, sig, "skipped", ["limit expired unfilled"])
                    continue
                through = b is not None and (b.low < sig.limit if sig.side == "long" else b.high > sig.limit)
                if through and sig.symbol not in self.s.positions:
                    self._open(o, sig.limit, start)        # a resting order fills at its own price
                else:
                    still.append(o)
        self.s.pending = still
        # 2. manage positions
        for sym in list(self.s.positions):
            p, b = self.s.positions[sym], bars.get(sym)
            if b is None:
                continue
            sig, long_ = p.signal, p.signal.side == "long"
            hit_stop = sig.stop is not None and (b.low <= sig.stop if long_ else b.high >= sig.stop)
            hit_tgt = sig.target is not None and (b.high > sig.target if long_ else b.low < sig.target)
            if hit_stop:                                   # stop first when both are touched
                px = min(b.open, sig.stop) if long_ else max(b.open, sig.stop)
                self._close(sym, px, start if px == b.open else end, "stop", stop_hit=True)
                continue
            if hit_tgt:
                px = max(b.open, sig.target) if long_ else min(b.open, sig.target)
                self._close(sym, px, end, "target")
                continue
            sess = self.sessions.session_of(start)
            at_close = self.L.market == "stocks" and sess is not None and end >= sess[1]
            if at_close and (sig.exit_at_close or self.L.flatten_at_close):
                self._close(sym, b.close, end, "session_close")
            elif sig.deadline is not None and end >= sig.deadline:
                self._close(sym, b.close, end, "time")
        # 3. mark
        for sym, b in bars.items():
            self.s.marks[sym] = b.close
        eq = self.equity()
        self.equity_curve.append((end, eq))
        if self.s.halted_today is None and eq < self.s.day_start_equity * (1 - self.L.daily_loss_limit):
            self.s.halted_today = f"daily loss {1 - eq / self.s.day_start_equity:.2%} ≥ {self.L.daily_loss_limit:.0%}"
        # 4. new signals at the bar's end
        for setup in self.setups:
            for sig in setup.scan(end, ctx):
                o = self._approve(sig, end, self.s.marks.get(sig.symbol))
                if o:
                    o.kind = "limit" if sig.entry == "limit" else "next_open"
                    self.s.pending.append(o)

    # ---- risk gate ---------------------------------------------------------
    def _decide(self, t, sig, outcome, reasons, notional=0.0):
        self.decisions.append(Decision(t, sig.setup, sig.symbol, outcome, tuple(reasons), notional))

    def _approve(self, sig: Signal, t: datetime, ref_px: float | None) -> Order | None:
        L, reasons = self.L, []
        eq = self.equity()
        if ref_px is None or ref_px <= 0:
            reasons.append("no reference price")
        if sig.side == "short" and not L.allow_short:
            reasons.append("shorting disabled")
        if L.allowed_symbols and sig.symbol not in L.allowed_symbols:
            reasons.append("not in the broker-supported universe")
        if self.s.halted_today:
            reasons.append(f"entries halted today: {self.s.halted_today}")
        if self.s.blocked:
            reasons.append(f"entries blocked: {self.s.blocked}")
        if self.s.entries_today >= L.max_entries_per_day:
            reasons.append("max entries per day reached")
        if L.one_position_per_symbol and (sig.symbol in self.s.positions or any(o.signal.symbol == sig.symbol for o in self.s.pending)):
            reasons.append("already positioned or pending in this symbol")
        if len(self.s.positions) + len(self.s.pending) >= L.max_positions:
            reasons.append("max open positions reached")
        if L.market == "stocks":
            px, dv = sig.features.get("price", ref_px), sig.features.get("dollar_volume")
            if px is not None and px < L.min_price:
                reasons.append(f"price {px:.2f} below {L.min_price}")
            if dv is None or not dv == dv or dv < L.min_dollar_volume:      # NaN (no history) counts as unknown
                reasons.append("liquidity unknown or below minimum")
            sess = self.sessions.session_of(t)
            if sess is None:
                reasons.append("market closed")
            elif (sess[1] - t).total_seconds() < L.no_entries_last_minutes * 60:
                reasons.append("too close to the session close")
            if L.pdt_max_day_trades_5d:
                recent = set(sorted(set(self.s.day_trades))[-5:])
                if sum(1 for d in self.s.day_trades if d in recent) >= L.pdt_max_day_trades_5d:
                    reasons.append("day-trade count limit (broker PDT setting)")
        if reasons:
            self._decide(t, sig, "rejected", reasons)
            return None
        # size: fixed weight, or risk-to-stop; then cap by per-position weight and gross room
        if sig.weight is not None:
            w = sig.weight
        elif sig.stop is not None and ref_px and abs(ref_px - sig.stop) > 0:
            w = L.risk_per_trade * ref_px / abs(ref_px - sig.stop)
        else:
            self._decide(t, sig, "rejected", ["no stop and no fixed weight: cannot size"])
            return None
        committed = sum(o.notional for o in self.s.pending) / eq if eq > 0 else 1
        w = min(w, L.max_weight, L.max_gross - self.gross() - committed)
        notional = w * eq
        cash_room = self.s.cash - sum(o.notional for o in self.s.pending)
        notional = min(notional, cash_room / (1 + self.costs[sig.setup].entry))
        if notional < 1.0:
            self._decide(t, sig, "rejected", ["no room under exposure or cash limits"])
            return None
        self._decide(t, sig, "approved", [sig.reason], notional)
        return Order(sig, notional, t, sig.entry)
