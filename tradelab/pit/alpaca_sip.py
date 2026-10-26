"""Minimal Alpaca market-data client (historical stock bars, trades, quotes) and
entitlement checks. Paper-account credentials only; never logged or printed.

Credentials come from the environment (see docs/CREDENTIALS_SETUP.md):
  TRADELAB_PAPER_APCA_API_KEY_ID, TRADELAB_PAPER_APCA_API_SECRET_KEY
Nothing in this module can place an order.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

DATA_URL = "https://data.alpaca.markets/v2/stocks"
PAPER_URL = "https://paper-api.alpaca.markets/v2"
LIVE_URL = "https://api.alpaca.markets/v2"          # used ONLY to confirm a paper key is rejected there
IEX_EXCHANGE = "V"                                   # Alpaca exchange code for IEX

Transport = Callable[[str, dict], tuple[int, dict]]


def http_get(url: str, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={**headers, "User-Agent": "tradelab-pit"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except Exception:
            body = {}
        return e.code, body


@dataclass(repr=False)
class AlpacaData:
    key_id: str
    secret: str
    transport: Transport = http_get
    calls: int = field(default=0)

    def __repr__(self):
        return "AlpacaData(key_id=<redacted>, secret=<redacted>)"

    @classmethod
    def from_env(cls, transport: Transport = http_get) -> "AlpacaData":
        k, s = os.environ.get("TRADELAB_PAPER_APCA_API_KEY_ID"), os.environ.get("TRADELAB_PAPER_APCA_API_SECRET_KEY")
        if not k or not s:
            raise RuntimeError("TRADELAB_PAPER_APCA_API_KEY_ID / _SECRET_KEY not set (see docs/CREDENTIALS_SETUP.md)")
        if any(n.startswith("TRADELAB_LIVE_") for n in os.environ):
            raise RuntimeError("live credentials present in a research process; refusing")
        return cls(k, s, transport)

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self.key_id, "APCA-API-SECRET-KEY": self.secret}

    def _get(self, url: str) -> tuple[int, dict]:
        self.calls += 1
        return self.transport(url, self._headers())

    def _paged(self, kind: str, symbol: str, params: dict, max_pages: int = 1000) -> tuple[int, list, dict]:
        """GET /v2/stocks/{kind} with pagination; returns (status, rows, last_body)."""
        rows, token, status, body = [], None, 0, {}
        for _ in range(max_pages):
            q = {"symbols": symbol, "limit": 10000, **params, **({"page_token": token} if token else {})}
            status, body = self._get(f"{DATA_URL}/{kind}?{urllib.parse.urlencode(q)}")
            if status != 200:
                return status, rows, body
            rows += (body.get(kind) or {}).get(symbol, [])
            token = body.get("next_page_token")
            if not token:
                break
        return status, rows, body

    def bars(self, symbol, start, end, timeframe="1Min", feed="sip", adjustment="raw"):
        return self._paged("bars", symbol, {"timeframe": timeframe, "start": _iso(start), "end": _iso(end),
                                            "feed": feed, "adjustment": adjustment})

    def trades(self, symbol, start, end, feed="sip"):
        return self._paged("trades", symbol, {"start": _iso(start), "end": _iso(end), "feed": feed})

    def quotes(self, symbol, start, end, feed="sip"):
        return self._paged("quotes", symbol, {"start": _iso(start), "end": _iso(end), "feed": feed})


def _iso(t) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(t, datetime) else str(t)


def verify_paper_key(client: AlpacaData) -> dict:
    """Confirms the key belongs to a PAPER account without revealing anything secret:
    the paper host must accept it and the live host must reject it."""
    ps, pb = client._get(f"{PAPER_URL}/account")
    ls, _ = client._get(f"{LIVE_URL}/account")
    return {"paper_host_status": ps, "paper_account_status": pb.get("status") if ps == 200 else None,
            "live_host_status": ls, "live_host_rejects_key": ls in (401, 403),
            "is_paper_key": ps == 200 and ls in (401, 403)}


def verify_entitlement(client: AlpacaData, session_open: datetime, session_close: datetime, symbol: str = "SPY") -> dict:
    """Which feed do we actually get for historical stock data? Pass a completed regular
    session at least one day old (e.g. from tradelab.intraday.sessions.StockSessions).
    Checks SIP vs IEX minute-bar volume, and the exchange codes present in one minute of
    SIP quotes and trades (IEX-only data shows only code 'V')."""
    if datetime.now(timezone.utc) - session_close < timedelta(days=1):
        raise ValueError("use a session that closed at least one day ago")
    out = {"symbol": symbol, "session_open": _iso(session_open), "session_close": _iso(session_close)}
    s_st, s_bars, s_body = client.bars(symbol, session_open, session_close, feed="sip")
    i_st, i_bars, _ = client.bars(symbol, session_open, session_close, feed="iex")
    out["sip_bars"] = {"status": s_st, "n": len(s_bars), "volume": sum(b.get("v", 0) for b in s_bars),
                       "message": s_body.get("message") if s_st != 200 else None}
    out["iex_bars"] = {"status": i_st, "n": len(i_bars), "volume": sum(b.get("v", 0) for b in i_bars)}
    if s_st == 200 and out["sip_bars"]["volume"]:
        out["iex_share_of_sip_volume"] = round(out["iex_bars"]["volume"] / out["sip_bars"]["volume"], 4)
    m0 = session_close - timedelta(minutes=61)                       # one minute, 60 minutes before the close
    q_st, q, q_body = client.quotes(symbol, m0, m0 + timedelta(minutes=1), feed="sip")
    t_st, tr, _ = client.trades(symbol, m0, m0 + timedelta(minutes=1), feed="sip")
    q_ex = sorted({r.get("bx") for r in q} | {r.get("ax") for r in q} - {None})
    t_ex = sorted({r.get("x") for r in tr} - {None})
    out["quotes"] = {"status": q_st, "n": len(q), "exchanges": q_ex, "message": q_body.get("message") if q_st != 200 else None}
    out["trades"] = {"status": t_st, "n": len(tr), "exchanges": t_ex, "tapes": sorted({r.get("z") for r in tr} - {None})}
    if s_st == 403 or q_st == 403:
        verdict = "forbidden"
    elif s_st != 200 or q_st != 200 or t_st != 200:
        verdict = "error"
    elif (q_ex and set(q_ex) <= {IEX_EXCHANGE}) or (t_ex and set(t_ex) <= {IEX_EXCHANGE}):
        verdict = "iex_only"
    elif len(set(t_ex) - {IEX_EXCHANGE}) >= 3 and out.get("iex_share_of_sip_volume", 1) < 0.2:
        verdict = "sip"
    else:
        verdict = "unclear"
    out["verdict"] = verdict
    out["api_calls"] = client.calls
    return out
