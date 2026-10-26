"""Order lifecycle with idempotent submission and reconcile-before-retry."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from .models import Order, Status, client_order_id
from .store import Store
from .venue import Venue, VenueRejected

VENUE_STATUS = {"open": Status.SUBMITTED, "filled": Status.FILLED, "cancelled": Status.CANCELLED,
                "rejected": Status.REJECTED}


class OrderManager:
    def __init__(self, store: Store, venue: Venue, account: str, unknown_grace: timedelta = timedelta(minutes=2),
                 min_request_interval_s: float = 0.2, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.store, self.venue, self.account = store, venue, account
        self.grace, self.min_interval, self.clock = unknown_grace, min_request_interval_s, clock
        self.rejections: list[datetime] = []
        self._last_request = 0.0

    def _throttle(self):
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def submit(self, decision_id: str, asset: str, notional: float, ref_price: float,
               decided_at: datetime | None = None, attempt: int = 1) -> Order:
        side = "buy" if notional > 0 else "sell"
        cid = client_order_id(f"{self.account}|{decision_id}", asset, attempt)
        if existing := self.store.get_order(cid):
            return existing                                       # idempotent: never send twice
        rules = self.venue.rules(asset)
        o = Order(cid, self.account, asset, side, "market", None, None, None, decision_id, attempt, decided_at=decided_at)
        if side == "buy":
            o.quote_size = float(rules.round_price(notional))
            too_small = o.quote_size < float(rules.min_market_funds)
        else:
            o.base_size = float(rules.round_size(-notional / ref_price))
            too_small = o.base_size * ref_price < float(rules.min_market_funds) or o.base_size <= 0
        if too_small:
            o.status, o.reject_reason = Status.REJECTED, "below venue minimum after rounding"
            self.store.put_order(o)
            return o
        o.submitted_at = self.clock()                             # start of the attempt, used for the grace period
        self.store.put_order(o)                                   # journal BEFORE sending
        self._throttle()
        try:
            o.venue_id = self.venue.place(o)
            o.acked_at = self.clock()
            o.status = Status.SUBMITTED
        except VenueRejected as e:
            o.status, o.reject_reason = Status.REJECTED, str(e)
            self.rejections.append(self.clock())
        except Exception as e:  # anything but a definite rejection: the order may exist, so reconcile
            o.status, o.reject_reason = Status.UNKNOWN, f"{type(e).__name__}: {e}"
        self.store.put_order(o)
        if o.status is Status.SUBMITTED:
            self.sync(o, ref_price)
        return o

    def sync(self, o: Order, ref_price: float | None = None) -> Order:
        """Pull authoritative state and fills from the venue."""
        self._throttle()
        r = self.venue.get_order(o.client_id)
        if r is None:                                             # NEW: crashed between journal and send
            if o.status in (Status.UNKNOWN, Status.NEW) and o.submitted_at and self.clock() - o.submitted_at > self.grace:
                o.status = Status.NOT_FOUND                     # safe to retry with attempt + 1
            self.store.put_order(o)
            return o
        o.venue_id = r["venue_id"]
        o.filled_base, o.filled_quote, o.fees = r["filled_base"], r["filled_quote"], r["fees"]
        o.status = VENUE_STATUS[r["status"]]
        if o.status is Status.SUBMITTED and o.filled_base > 0:
            o.status = Status.PARTIAL
        for f in self.venue.fills(o.client_id):
            if self.store.add_fill(self.account, f) and o.first_fill_at is None:
                o.first_fill_at = f.at
        self.store.put_order(o)
        if o.first_fill_at and o.acked_at:
            slip = None
            if ref_price and o.avg_price:
                slip = (o.avg_price / ref_price - 1) * 1e4 * (1 if o.side == "buy" else -1)
            ms = lambda a, b: (b - a).total_seconds() * 1000 if a and b else None
            self.store.latency(o.client_id, decided_to_submit_ms=ms(o.decided_at, o.submitted_at),
                               submit_to_ack_ms=ms(o.submitted_at, o.acked_at),
                               ack_to_first_fill_ms=ms(o.acked_at, o.first_fill_at), slippage_bps=slip)
        return o

    def recover(self) -> list[Order]:
        """On startup: reconcile every non-terminal order before any new decision."""
        return [self.sync(o) for o in self.store.open_orders(self.account)]

    def retry(self, o: Order, ref_price: float) -> Order:
        if o.status is not Status.NOT_FOUND:
            raise RuntimeError(f"refusing to retry an order in state {o.status.value}; reconcile first")
        notional = o.quote_size if o.side == "buy" else -o.base_size * ref_price
        return self.submit(o.decision_id, o.asset, notional, ref_price, o.decided_at, o.attempt + 1)

    def cancel_all(self) -> list[Order]:
        out = []
        for o in self.store.open_orders(self.account):
            if o.status in (Status.SUBMITTED, Status.PARTIAL):
                self._throttle()
                self.venue.cancel(o.client_id)
            out.append(self.sync(o))
        return out

    def reconcile_balances(self, initial_cash: float, marks: dict[str, float]) -> float:
        """Largest quote-currency difference between our journal and the venue."""
        cash, pos = self.store.positions(self.account, initial_cash)
        bal = self.venue.balances()
        diffs = [abs(cash - bal.get("USD", 0.0))]
        for a in set(pos) | {k for k in bal if k != "USD"}:
            diffs.append(abs(pos.get(a, 0.0) - bal.get(a, 0.0)) * marks.get(a, 0.0))
        return max(diffs)
