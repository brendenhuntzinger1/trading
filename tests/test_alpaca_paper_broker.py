"""The paper broker: paper host only, explicit enable switch, hard limits independent of strategies,
long-only, idempotent client ids."""
import pytest

from tradelab.broker.alpaca_paper import AlpacaPaperBroker, BrokerRefused, Limits, check_url


class FakeAlpaca:
    def __init__(self, positions=None):
        self.orders, self.positions = {}, positions or []
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if url.endswith("/positions"):
            return 200, self.positions
        if "/orders:by_client_order_id" in url:
            cid = url.split("client_order_id=")[1]
            return (200, self.orders[cid]) if cid in self.orders else (404, {})
        if url.endswith("/orders") and method == "POST":
            o = {**body, "id": f"o{len(self.orders)}", "status": "accepted"}
            self.orders[body["client_order_id"]] = o
            return 200, o
        if url.endswith("/account"):
            return 200, {"account_number": "PA123", "status": "ACTIVE"}
        return 404, {}


def broker(fake, **kw):
    return AlpacaPaperBroker("k", "s", Limits(**kw) if kw else Limits(), transport=fake, sleep=lambda s: None)


def test_live_and_unlisted_endpoints_are_refused():
    for url in ("https://api.alpaca.markets/v2/orders", "https://paper-api.alpaca.markets/v2/account/configurations",
                "https://broker-api.alpaca.markets/v1/accounts", "https://paper-api.alpaca.markets/v2/watchlists"):
        with pytest.raises(BrokerRefused):
            check_url(url)
    check_url("https://paper-api.alpaca.markets/v2/orders")


def test_from_env_needs_explicit_switch_and_refuses_live(monkeypatch):
    monkeypatch.setenv("TRADELAB_PAPER_APCA_API_KEY_ID", "k")
    monkeypatch.setenv("TRADELAB_PAPER_APCA_API_SECRET_KEY", "s")
    monkeypatch.delenv("TRADELAB_PAPER_BROKER_ENABLED", raising=False)
    with pytest.raises(BrokerRefused, match="disabled"):
        AlpacaPaperBroker.from_env()
    monkeypatch.setenv("TRADELAB_PAPER_BROKER_ENABLED", "1")
    monkeypatch.setenv("TRADELAB_LIVE_KEY", "x")
    with pytest.raises(BrokerRefused, match="live"):
        AlpacaPaperBroker.from_env()
    monkeypatch.delenv("TRADELAB_LIVE_KEY")
    monkeypatch.setenv("TRADELAB_PAPER_APCA_BASE_URL", "https://api.alpaca.markets")
    with pytest.raises(BrokerRefused, match="paper host"):
        AlpacaPaperBroker.from_env()


def test_caps_budget_allowlist_and_no_shorting():
    fake = FakeAlpaca(positions=[{"symbol": "BTCUSD", "qty": "0.001", "market_value": "950"}])
    b = broker(fake)
    with pytest.raises(BrokerRefused, match="per-order cap"):
        b.submit("c1", "BTC/USD", "buy", notional=150)
    with pytest.raises(BrokerRefused, match="budget"):
        b.submit("c2", "BTC/USD", "buy", notional=60)          # 950 + 60 > 1000
    with pytest.raises(BrokerRefused, match="allow-list"):
        b.submit("c3", "DOGE/USD", "buy", notional=10)
    with pytest.raises(BrokerRefused, match="no shorting"):
        b.submit("c4", "BTC/USD", "sell", qty=0.002)
    assert not any(m == "POST" for m, *_ in fake.calls)


def test_resubmitting_a_client_id_never_creates_a_second_order():
    fake = FakeAlpaca()
    b = broker(fake)
    first = b.submit("cid-1", "BTC/USD", "buy", notional=10)
    again = b.submit("cid-1", "BTC/USD", "buy", notional=10)
    assert again["_duplicate"] and again["id"] == first["id"]
    assert sum(m == "POST" for m, *_ in fake.calls) == 1


def test_account_must_be_paper():
    fake = FakeAlpaca()
    fake_live = lambda m, u, h, b: (200, {"account_number": "123"}) if u.endswith("/account") else fake(m, u, h, b)
    with pytest.raises(BrokerRefused, match="not a paper"):
        broker(fake_live).account()
    assert broker(fake).account()["status"] == "ACTIVE"
