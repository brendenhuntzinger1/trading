"""Alpaca PAPER broker adapter: the only code in the repository that sends orders, and only to Alpaca's
paper-trading host (simulated money). Fills from it are labelled "broker paper fills": Alpaca simulates them
against real quotes, so they are still simulations, not evidence of live execution quality.

Hard limits live here, independent of any strategy or model, and cannot be raised by a caller at run time:
  * paper host only; a TRADELAB_LIVE_* variable in the environment refuses start-up;
  * TRADELAB_PAPER_BROKER_ENABLED=1 must be set explicitly;
  * a provisional budget (default $1,000, an ASSUMPTION, not the paper account's $100k balance) caps the
    market value we may hold, and a per-order cap limits each order;
  * long-only: a sell may not exceed the position held; no leverage;
  * an allow-list of symbols;
  * deterministic client order ids: a resend after a crash finds the existing order instead of duplicating it.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

PAPER = "https://paper-api.alpaca.markets/v2"
DATA = "https://data.alpaca.markets"
ALLOWED = {  # exact (host, path) pairs: a prefix match would let /v2/account/configurations through
    ("paper-api.alpaca.markets", "/v2/orders"), ("paper-api.alpaca.markets", "/v2/orders:by_client_order_id"),
    ("paper-api.alpaca.markets", "/v2/account"), ("paper-api.alpaca.markets", "/v2/positions"),
    ("paper-api.alpaca.markets", "/v2/clock"),
    ("data.alpaca.markets", "/v1beta3/crypto/us/latest/quotes"), ("data.alpaca.markets", "/v2/stocks/quotes/latest"),
}


class BrokerRefused(RuntimeError):
    pass


def check_url(url: str) -> None:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or (u.netloc, u.path) not in ALLOWED:
        raise BrokerRefused(f"refusing endpoint outside the paper allow-list: {u.netloc}{u.path}")


Transport = Callable[[str, str, dict, dict | None], tuple[int, dict | list]]


def http_request(method: str, url: str, headers: dict, body: dict | None = None) -> tuple[int, dict | list]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={**headers, "Content-Type": "application/json", "User-Agent": "tradelab-paper"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


@dataclass(frozen=True)
class Limits:
    budget_usd: float = 1000.0                 # provisional paper budget (assumption)
    max_order_usd: float = 100.0
    symbols: tuple[str, ...] = ("BTC/USD", "ETH/USD", "SPY")


@dataclass(repr=False)
class AlpacaPaperBroker:
    key_id: str
    secret: str
    limits: Limits = field(default_factory=Limits)
    transport: Transport = http_request
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    log: list = field(default_factory=list)    # every request: method, path, status, sent/received timestamps

    def __repr__(self):
        return "AlpacaPaperBroker(key_id=<redacted>, secret=<redacted>)"

    @classmethod
    def from_env(cls, limits: Limits = Limits(), transport: Transport = http_request) -> "AlpacaPaperBroker":
        if os.environ.get("TRADELAB_PAPER_BROKER_ENABLED") != "1":
            raise BrokerRefused("paper broker disabled: set TRADELAB_PAPER_BROKER_ENABLED=1 explicitly")
        if any(n.startswith("TRADELAB_LIVE_") for n in os.environ):
            raise BrokerRefused("live credentials present; refusing to start")
        base = os.environ.get("TRADELAB_PAPER_APCA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
        if base.removesuffix("/v2") != PAPER.removesuffix("/v2"):
            raise BrokerRefused("TRADELAB_PAPER_APCA_BASE_URL must be the paper host")
        k, s = os.environ.get("TRADELAB_PAPER_APCA_API_KEY_ID"), os.environ.get("TRADELAB_PAPER_APCA_API_SECRET_KEY")
        if not k or not s:
            raise BrokerRefused("paper key not configured (docs/CREDENTIALS_SETUP.md)")
        return cls(k, s, limits, transport)

    # ----------------------------------------------------------------- http ----
    def _call(self, method: str, url: str, body: dict | None = None) -> tuple[int, dict | list]:
        check_url(url)
        t0 = self.clock()
        st, out = self.transport(method, url, {"APCA-API-KEY-ID": self.key_id, "APCA-API-SECRET-KEY": self.secret}, body)
        self.log.append({"method": method, "path": urllib.parse.urlsplit(url).path, "status": st,
                         "sent": t0, "received": self.clock()})
        return st, out

    # ----------------------------------------------------------- read-only ----
    def account(self) -> dict:
        st, a = self._call("GET", f"{PAPER}/account")
        if st != 200:
            raise BrokerRefused(f"account HTTP {st}")
        if not str(a.get("account_number", "")).startswith("PA"):
            raise BrokerRefused("not a paper account")
        return a

    def positions(self) -> dict[str, dict]:
        st, rows = self._call("GET", f"{PAPER}/positions")
        if st != 200:
            raise BrokerRefused(f"positions HTTP {st}")
        return {r["symbol"]: r for r in rows}

    def order_by_client_id(self, cid: str) -> dict | None:
        st, o = self._call("GET", f"{PAPER}/orders:by_client_order_id?{urllib.parse.urlencode({'client_order_id': cid})}")
        return o if st == 200 else None

    def latest_quote(self, symbol: str) -> dict:
        if "/" in symbol:
            st, b = self._call("GET", f"{DATA}/v1beta3/crypto/us/latest/quotes?{urllib.parse.urlencode({'symbols': symbol})}")
            return (b.get("quotes") or {}).get(symbol, {}) if st == 200 else {}
        st, b = self._call("GET", f"{DATA}/v2/stocks/quotes/latest?{urllib.parse.urlencode({'symbols': symbol, 'feed': 'iex'})}")
        return (b.get("quotes") or {}).get(symbol, {}) if st == 200 else {}

    # --------------------------------------------------------------- orders ----
    @staticmethod
    def _pos_key(symbol: str) -> str:
        return symbol.replace("/", "")

    def _exposure(self, pos: dict[str, dict]) -> float:
        tracked = {self._pos_key(s) for s in self.limits.symbols}
        return sum(abs(float(p.get("market_value", 0))) for k, p in pos.items() if k in tracked)

    def pre_trade_check(self, symbol: str, side: str, notional: float | None, qty: float | None) -> None:
        """Hard limits, independent of the strategy. Raises BrokerRefused."""
        if symbol not in self.limits.symbols:
            raise BrokerRefused(f"{symbol} not in the allow-list")
        if side not in ("buy", "sell"):
            raise BrokerRefused(side)
        pos = self.positions()
        if side == "buy":
            if notional is None or notional <= 0:
                raise BrokerRefused("buys are sized by notional")
            if notional > self.limits.max_order_usd:
                raise BrokerRefused(f"order ${notional:.2f} exceeds the per-order cap ${self.limits.max_order_usd:.2f}")
            if self._exposure(pos) + notional > self.limits.budget_usd:
                raise BrokerRefused("order would exceed the provisional budget")
        else:
            held = float(pos.get(self._pos_key(symbol), {}).get("qty", 0))
            if qty is None or qty <= 0 or qty > held + 1e-12:
                raise BrokerRefused(f"sell of {qty} exceeds the position held ({held}); no shorting")

    def submit(self, client_order_id: str, symbol: str, side: str, notional: float | None = None,
               qty: float | None = None, order_type: str = "market", limit_price: float | None = None,
               tif: str | None = None) -> dict:
        """Idempotent: an existing order with this client id is returned instead of a second order."""
        existing = self.order_by_client_id(client_order_id)
        if existing:
            return {**existing, "_duplicate": True}
        self.pre_trade_check(symbol, side, notional, qty)
        body = {"symbol": symbol, "side": side, "type": order_type, "client_order_id": client_order_id,
                "time_in_force": tif or ("gtc" if "/" in symbol else "day")}
        if notional is not None:
            body["notional"] = f"{notional:.2f}"
        if qty is not None:
            body["qty"] = f"{qty:.9f}".rstrip("0").rstrip(".")
        if order_type == "limit":
            body["limit_price"] = f"{limit_price}"
        st, o = self._call("POST", f"{PAPER}/orders", body)
        if st in (200, 201):
            return o
        if st == 422 and "client_order_id" in json.dumps(o):
            return {**(self.order_by_client_id(client_order_id) or {}), "_duplicate": True}
        raise BrokerRefused(f"order rejected HTTP {st}: {o}")

    def wait_terminal(self, client_order_id: str, timeout_s: float = 60.0, poll_s: float = 0.5) -> dict:
        end = self.clock() + timeout_s
        o: dict = {}
        while self.clock() < end:
            o = self.order_by_client_id(client_order_id) or {}
            if o.get("status") in ("filled", "canceled", "expired", "rejected"):
                return o
            self.sleep(poll_s)
        return o
