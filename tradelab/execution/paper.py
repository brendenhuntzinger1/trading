"""Paper exchange: fills simulated against real order books, conservatively.

* Market orders walk the book captured AFTER submission (so latency costs
  something) and fill only the displayed depth; the rest is cancelled (IOC).
* Resting limit orders fill only when later trades print THROUGH the price,
  or when volume at the price exceeds the queue that was ahead of us. A
  touch is not a fill.
* Failure injection (rejects, lost acknowledgements, lost requests) exercises
  the same recovery paths the live system needs.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from .models import Fill, Order, ProductRules
from .venue import Book, VenueRejected, VenueUnknown


@dataclass
class _Working:
    order: Order
    status: str = "open"
    filled_base: float = 0.0
    filled_quote: float = 0.0
    fees: float = 0.0
    fills: list[Fill] = field(default_factory=list)
    queue_ahead: float = 0.0


class PaperExchange:
    name = "paper"

    def __init__(self, book_source: Callable[[str], Book], rules: Callable[[str], ProductRules], cash: float,
                 taker_fee: float = 0.006, maker_fee: float = 0.004, reject_prob: float = 0.0,
                 lost_ack_prob: float = 0.0, lost_request_prob: float = 0.0, seed: int = 0,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.book_source, self._rules, self.clock = book_source, rules, clock
        self.taker_fee, self.maker_fee = taker_fee, maker_fee
        self.reject_prob, self.lost_ack_prob, self.lost_request_prob = reject_prob, lost_ack_prob, lost_request_prob
        self.rng = random.Random(seed)
        self.bal: dict[str, float] = {"USD": cash}          # free balances
        self.held: dict[str, float] = {}                      # reserved by resting orders
        self.orders: dict[str, _Working] = {}
        self._fill_seq = 0

    # --- venue API ---------------------------------------------------------
    def rules(self, asset):
        return self._rules(asset)

    def balances(self):
        """Totals (free + held), as an exchange reports account balances."""
        return {k: self.bal.get(k, 0.0) + self.held.get(k, 0.0) for k in set(self.bal) | set(self.held)}

    def _hold(self, ccy: str, amt: float):
        self.bal[ccy] = self.bal.get(ccy, 0.0) - amt
        self.held[ccy] = self.held.get(ccy, 0.0) + amt

    def get_order(self, client_id):
        w = self.orders.get(client_id)
        if not w:
            return None
        return {"status": w.status, "filled_base": w.filled_base, "filled_quote": w.filled_quote,
                "fees": w.fees, "venue_id": f"paper-{client_id}"}

    def fills(self, client_id):
        w = self.orders.get(client_id)
        return list(w.fills) if w else []

    def cancel(self, client_id):
        w = self.orders.get(client_id)
        if w and w.status == "open":
            w.status = "cancelled"
            left = w.order.base_size - w.filled_base
            if w.order.side == "buy":
                self._hold("USD", -left * w.order.limit_price * (1 + self.maker_fee))
            else:
                self._hold(w.order.asset, -left)

    def place(self, o: Order) -> str:
        if self.rng.random() < self.lost_request_prob:
            raise VenueUnknown("request timed out (never reached venue)")
        if client_id_seen := self.orders.get(o.client_id):
            return f"paper-{client_id_seen.order.client_id}"          # venues dedupe on client id
        if self.rng.random() < self.reject_prob:
            raise VenueRejected("simulated venue rejection")
        self._validate(o)
        w = _Working(o)
        self.orders[o.client_id] = w
        if o.kind == "market":
            self._take(w, self.book_source(o.asset))
        else:
            self._rest(w, self.book_source(o.asset))
        if self.rng.random() < self.lost_ack_prob:
            raise VenueUnknown("acknowledgement lost (order exists at venue)")
        return f"paper-{o.client_id}"

    # --- simulation --------------------------------------------------------
    def _validate(self, o: Order):
        r = self._rules(o.asset)
        if o.kind == "market" and o.side == "buy":
            if Decimal(str(o.quote_size)) < r.min_market_funds:
                raise VenueRejected("below min_market_funds")
            if o.quote_size * (1 + self.taker_fee) > self.bal["USD"] + 1e-9:
                raise VenueRejected("insufficient funds")
        else:
            if o.base_size <= 0 or Decimal(str(o.base_size)) % r.base_increment != 0:
                raise VenueRejected("size not a multiple of base_increment")
            if o.side == "sell" and o.base_size > self.bal.get(o.asset, 0.0) + 1e-12:
                raise VenueRejected("insufficient free balance")
            if o.side == "buy" and o.base_size * o.limit_price * (1 + self.maker_fee) > self.bal["USD"] + 1e-9:
                raise VenueRejected("insufficient funds")

    def _fill(self, w: _Working, base: float, price: float, fee_rate: float):
        fee = base * price * fee_rate
        self._fill_seq += 1
        f = Fill(f"pf-{w.order.client_id}-{self._fill_seq}", w.order.client_id, w.order.asset, w.order.side, base, price, fee, self.clock())
        w.fills.append(f)
        w.filled_base += base
        w.filled_quote += base * price
        w.fees += fee
        a, limit = w.order.asset, w.order.kind == "limit"
        if w.order.side == "buy":
            self.bal[a] = self.bal.get(a, 0.0) + base
            if limit:
                self.held["USD"] -= base * price + fee
            else:
                self.bal["USD"] -= base * price + fee
        else:
            if limit:
                self.held[a] -= base
            else:
                self.bal[a] -= base
            self.bal["USD"] += base * price - fee

    def _take(self, w: _Working, book: Book):
        o = w.order
        if o.side == "buy":
            budget = o.quote_size
            for px, sz in book.asks:
                if budget <= 1e-9:
                    break
                take = min(sz, budget / px)
                self._fill(w, take, px, self.taker_fee)
                budget -= take * px
        else:
            left = o.base_size
            for px, sz in book.bids:
                if left <= 1e-12:
                    break
                take = min(sz, left)
                self._fill(w, take, px, self.taker_fee)
                left -= take
        done = (o.side == "buy" and w.filled_quote >= o.quote_size - 0.01) or \
               (o.side == "sell" and w.filled_base >= o.base_size - 1e-12)
        w.status = "filled" if done else "cancelled"      # IOC: unfilled remainder is cancelled

    def _rest(self, w: _Working, book: Book):
        o = w.order
        crosses = o.limit_price >= book.asks[0][0] if o.side == "buy" else o.limit_price <= book.bids[0][0]
        if crosses:
            del self.orders[o.client_id]
            raise VenueRejected("post-only limit would cross the book")
        side = book.bids if o.side == "buy" else book.asks
        w.queue_ahead = sum(s for p, s in side if p == o.limit_price)
        if o.side == "buy":
            self._hold("USD", o.base_size * o.limit_price * (1 + self.maker_fee))
        else:
            self._hold(o.asset, o.base_size)

    def on_trades(self, asset: str, trades: list[tuple[float, float]]):
        """Feed public trades (price, size) after placement to advance resting orders."""
        for w in self.orders.values():
            o = w.order
            if w.status != "open" or o.asset != asset or o.kind != "limit":
                continue
            for px, sz in trades:
                left = o.base_size - w.filled_base
                if left <= 1e-12:
                    break
                through = px < o.limit_price if o.side == "buy" else px > o.limit_price
                at_level = px == o.limit_price
                if through:
                    self._fill(w, min(left, sz), o.limit_price, self.maker_fee)
                elif at_level:
                    if w.queue_ahead >= sz:
                        w.queue_ahead -= sz
                    else:
                        avail, w.queue_ahead = sz - w.queue_ahead, 0.0
                        self._fill(w, min(left, avail), o.limit_price, self.maker_fee)
            if o.base_size - w.filled_base <= 1e-12:
                w.status = "filled"


def save_state(ex: PaperExchange, path) -> None:
    """Persist the simulated venue separately from our journal, so reconciling
    one against the other stays meaningful across runs."""
    import json
    from dataclasses import asdict
    from pathlib import Path
    orders = {cid: {"order": {**asdict(w.order), "status": w.order.status.value,
                              **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                 for k, v in asdict(w.order).items() if k.endswith("_at")}},
                    "status": w.status, "filled_base": w.filled_base, "filled_quote": w.filled_quote, "fees": w.fees,
                    "queue_ahead": w.queue_ahead,
                    "fills": [{**asdict(f), "at": f.at.isoformat()} for f in w.fills]}
              for cid, w in ex.orders.items()}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"bal": ex.bal, "held": ex.held, "fill_seq": ex._fill_seq, "orders": orders}))


def load_state(ex: PaperExchange, path) -> PaperExchange:
    import json
    from pathlib import Path
    from .models import Status
    p = Path(path)
    if not p.exists():
        return ex
    d = json.loads(p.read_text())
    ex.bal, ex.held, ex._fill_seq = d["bal"], d.get("held", {}), d["fill_seq"]
    for cid, w in d["orders"].items():
        od = w["order"]
        od["status"] = Status(od["status"])
        for k in [k for k in od if k.endswith("_at")]:
            od[k] = datetime.fromisoformat(od[k]) if od[k] else None
        ww = _Working(Order(**od), w["status"], w["filled_base"], w["filled_quote"], w["fees"],
                      [Fill(**{**f, "at": datetime.fromisoformat(f["at"])}) for f in w["fills"]], w["queue_ahead"])
        ex.orders[cid] = ww
    return ex
