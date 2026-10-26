import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradelab.execution.manager import OrderManager
from tradelab.execution.models import ProductRules, Status, client_order_id
from tradelab.execution.paper import PaperExchange
from tradelab.execution.secrets import RedactingFilter, assert_least_privilege, load, redact
from tradelab.execution.store import Store
from tradelab.execution.venue import Book, VenueUnknown

T0 = datetime(2026, 10, 25, tzinfo=timezone.utc)
RULES = ProductRules("BTC-USD", Decimal("0.00000001"), Decimal("0.01"), Decimal("1"))


def book(asks=((100.0, 1.0), (101.0, 1.0)), bids=((99.0, 1.0), (98.0, 1.0))):
    return Book("BTC-USD", list(bids), list(asks), T0, T0)


class Clock:
    def __init__(self):
        self.t = T0
    def __call__(self):
        return self.t


def setup(tmp_path, b=None, **kw):
    clock = Clock()
    ex = PaperExchange(lambda a: b or book(), lambda a: RULES, cash=1000, clock=clock, **kw)
    store = Store(tmp_path / "j.db", "paper")
    return OrderManager(store, ex, "acct", min_request_interval_s=0, clock=clock), ex, store, clock


def test_client_id_is_deterministic_attempt_specific_and_side_free():
    assert client_order_id("d1", "BTC-USD") == client_order_id("d1", "BTC-USD")
    assert client_order_id("d1", "BTC-USD", 2) != client_order_id("d1", "BTC-USD", 1)


def test_unexpected_exception_from_venue_is_unknown_not_crash(tmp_path):
    import urllib.error
    om, ex, store, clock = setup(tmp_path)
    def boom(o):
        raise urllib.error.URLError("connection reset")
    ex.place = boom
    o = om.submit("d1", "BTC-USD", 50.0, 100.0)
    assert o.status is Status.UNKNOWN


def test_order_journalled_but_never_sent_resolves_to_not_found(tmp_path):
    from tradelab.execution.models import Order
    om, ex, store, clock = setup(tmp_path)
    o = Order("tl-x", "acct", "BTC-USD", "buy", "market", 50.0, None, None, "d9", submitted_at=clock())
    store.put_order(o)                                             # crash right after journalling
    clock.t += timedelta(minutes=5)
    (o,) = om.recover()
    assert o.status is Status.NOT_FOUND


def test_market_buy_walks_book_and_pays_taker_fee(tmp_path):
    om, ex, store, _ = setup(tmp_path)
    o = om.submit("d1", "BTC-USD", 150.0, ref_price=100.0)
    assert o.status is Status.FILLED
    assert o.filled_base == pytest.approx(1.0 + 50 / 101)          # 1 BTC at 100, rest at 101
    assert o.fees == pytest.approx(150 * 0.006)
    cash, pos = store.positions("acct", 1000)
    assert cash == pytest.approx(ex.balances()["USD"]) and pos["BTC-USD"] == pytest.approx(ex.balances()["BTC-USD"])


def test_resubmitting_same_decision_never_creates_second_order(tmp_path):
    om, ex, store, _ = setup(tmp_path)
    a = om.submit("d1", "BTC-USD", 50.0, 100.0)
    b = om.submit("d1", "BTC-USD", 50.0, 100.0)
    assert a.client_id == b.client_id and len(ex.orders) == 1


def test_thin_book_gives_partial_fill_then_cancel(tmp_path):
    om, *_ = setup(tmp_path, b=book(asks=((100.0, 0.5),)))
    o = om.submit("d1", "BTC-USD", 200.0, 100.0)
    assert o.status is Status.CANCELLED and o.filled_base == pytest.approx(0.5)


def test_below_minimum_rejected_locally(tmp_path):
    om, ex, *_ = setup(tmp_path)
    o = om.submit("d1", "BTC-USD", 0.5, 100.0)
    assert o.status is Status.REJECTED and not ex.orders


def test_lost_ack_is_unknown_then_reconciled_without_resend(tmp_path):
    om, ex, store, _ = setup(tmp_path, lost_ack_prob=1.0)
    o = om.submit("d1", "BTC-USD", 50.0, 100.0)
    assert o.status is Status.UNKNOWN
    with pytest.raises(RuntimeError):
        om.retry(o, 100.0)                                         # must reconcile first
    (o,) = om.recover()
    assert o.status is Status.FILLED and len(ex.orders) == 1


def test_lost_request_becomes_not_found_then_retry_once(tmp_path):
    om, ex, store, clock = setup(tmp_path, lost_request_prob=1.0)
    o = om.submit("d1", "BTC-USD", 50.0, 100.0)
    assert o.status is Status.UNKNOWN
    (o,) = om.recover()
    assert o.status is Status.UNKNOWN                              # within grace: keep waiting
    clock.t += timedelta(minutes=5)
    (o,) = om.recover()
    assert o.status is Status.NOT_FOUND
    ex.lost_request_prob = 0.0
    r = om.retry(o, 100.0)
    assert r.status is Status.FILLED and r.attempt == 2 and len(ex.orders) == 1


def test_crash_recovery_from_journal(tmp_path):
    om, ex, store, clock = setup(tmp_path, lost_ack_prob=1.0)
    om.submit("d1", "BTC-USD", 50.0, 100.0)
    om2 = OrderManager(Store(tmp_path / "j.db", "paper"), ex, "acct", min_request_interval_s=0, clock=clock)
    (o,) = om2.recover()                                           # fresh process, same journal
    assert o.status is Status.FILLED
    assert om2.reconcile_balances(1000, {"BTC-USD": 100.0}) < 1e-6


def test_reconciliation_detects_divergence(tmp_path):
    om, ex, *_ = setup(tmp_path)
    om.submit("d1", "BTC-USD", 50.0, 100.0)
    ex.bal["USD"] -= 25                                            # venue disagrees with our journal
    assert om.reconcile_balances(1000, {"BTC-USD": 100.0}) == pytest.approx(25)


def test_rejections_recorded_for_risk_engine(tmp_path):
    om, *_ = setup(tmp_path, reject_prob=1.0)
    o = om.submit("d1", "BTC-USD", 50.0, 100.0)
    assert o.status is Status.REJECTED and len(om.rejections) == 1


def test_limit_order_touch_is_not_a_fill():
    ex = PaperExchange(lambda a: book(bids=((99.0, 2.0),)), lambda a: RULES, cash=1000)
    from tradelab.execution.models import Order
    o = Order("c1", "acct", "BTC-USD", "buy", "limit", None, 1.0, 99.0, "d")
    ex.place(o)
    ex.on_trades("BTC-USD", [(99.0, 1.5)])                         # touches, but 2.0 queued ahead
    assert ex.get_order("c1")["filled_base"] == 0
    ex.on_trades("BTC-USD", [(99.0, 1.0)])                         # queue exhausted -> 0.5 fills
    assert ex.get_order("c1")["filled_base"] == pytest.approx(0.5)
    ex.on_trades("BTC-USD", [(98.5, 3.0)])                         # trades through -> rest fills
    assert ex.get_order("c1")["status"] == "filled"


def test_post_only_crossing_rejected():
    from tradelab.execution.models import Order
    from tradelab.execution.venue import VenueRejected
    ex = PaperExchange(lambda a: book(), lambda a: RULES, cash=1000)
    with pytest.raises(VenueRejected):
        ex.place(Order("c2", "acct", "BTC-USD", "buy", "limit", None, 1.0, 100.0, "d"))


def test_secrets_redacted_and_paper_refuses_live_keys(monkeypatch):
    assert "<redacted>" in redact('{"api_key": "abc123", "x": 1}')
    assert "PRIVATE KEY" not in redact("-----BEGIN EC PRIVATE KEY-----\nMHcC\n-----END EC PRIVATE KEY-----")
    rec = logging.LogRecord("t", logging.INFO, "", 0, "secret=%s", ("hunter2",), None)
    RedactingFilter().filter(rec)
    assert "hunter2" not in rec.msg
    monkeypatch.setenv("TRADELAB_LIVE_PRIVATE_KEY", "x")
    with pytest.raises(RuntimeError):
        load("paper")


def test_key_with_withdrawal_permission_refused():
    with pytest.raises(RuntimeError):
        assert_least_privilege({"can_view": True, "can_trade": True, "can_transfer": True})
    assert_least_privilege({"can_view": True, "can_trade": True, "can_transfer": False})


def test_same_fill_id_in_two_accounts_is_not_a_duplicate(tmp_path):
    """Regression: per-account paper venues both emit fill id 'pf-1'; the second was dropped."""
    store = Store(tmp_path / "j.db", "paper")
    clock = Clock()
    for acct in ("a", "b"):
        ex = PaperExchange(lambda a: book(), lambda a: RULES, cash=1000, clock=clock)
        OrderManager(store, ex, acct, min_request_interval_s=0, clock=clock).submit("d1", "BTC-USD", 50.0, 100.0)
    for acct in ("a", "b"):
        cash, pos = store.positions(acct, 1000)
        assert pos.get("BTC-USD", 0) > 0, f"fills for account {acct} were lost"


def test_paper_venue_never_sells_more_than_free_balance():
    from tradelab.execution.models import Order
    from tradelab.execution.venue import VenueRejected
    ex = PaperExchange(lambda a: book(bids=((99.0, 5.0),), asks=((101.0, 5.0),)), lambda a: RULES, cash=1000)
    ex.bal["BTC-USD"] = 1.0
    ex.place(Order("s1", "acct", "BTC-USD", "sell", "limit", None, 1.0, 102.0, "d"))      # reserves the 1.0
    with pytest.raises(VenueRejected):
        ex.place(Order("s2", "acct", "BTC-USD", "sell", "market", None, 1.0, None, "d"))
    assert ex.balances()["BTC-USD"] == pytest.approx(1.0)                                 # totals include holds
    ex.cancel("s1")
    assert ex.bal["BTC-USD"] == pytest.approx(1.0)


def test_resting_limit_buy_does_not_look_like_a_reconciliation_gap(tmp_path):
    from tradelab.execution.models import Order
    om, ex, store, _ = setup(tmp_path, b=book(bids=((99.0, 5.0),), asks=((101.0, 5.0),)))
    ex.place(Order("l1", "acct", "BTC-USD", "buy", "limit", None, 1.0, 98.0, "d"))
    assert om.reconcile_balances(1000, {"BTC-USD": 100.0}) < 1e-6


def test_bearer_tokens_and_tracebacks_are_redacted():
    assert "eyJhbGciOi.payload.sig" not in redact("Authorization: Bearer eyJhbGciOi.payload.sig")
    try:
        raise RuntimeError("secret=hunter2")
    except RuntimeError:
        import sys
        rec = logging.LogRecord("t", logging.ERROR, "", 0, "failed", (), sys.exc_info())
    RedactingFilter().filter(rec)
    assert "hunter2" not in rec.getMessage() and not rec.exc_info