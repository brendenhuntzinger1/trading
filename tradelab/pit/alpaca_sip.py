"""Minimal Alpaca market-data client (historical stock bars, trades, quotes, asset master) and
entitlement checks. Paper-account credentials only; never logged or printed.

Credentials come from the environment (see docs/CREDENTIALS_SETUP.md):
  TRADELAB_PAPER_APCA_API_KEY_ID, TRADELAB_PAPER_APCA_API_SECRET_KEY, TRADELAB_PAPER_APCA_BASE_URL (optional)
Nothing in this module can place an order: every request is a GET, and `_get` refuses any URL outside an
explicit allow-list of read-only market-data / reference endpoints (orders, positions, watchlists and account
configuration are rejected before any network call).
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

DATA_URL = "https://data.alpaca.markets/v2/stocks"
CORP_ACTIONS_URL = "https://data.alpaca.markets/v1/corporate-actions"
NEWS_URL = "https://data.alpaca.markets/v1beta1/news"           # Benzinga headlines, read-only
PAPER_URL = "https://paper-api.alpaca.markets/v2"
LIVE_URL = "https://api.alpaca.markets/v2"          # used ONLY to confirm a paper key is rejected there
IEX_EXCHANGE = "V"                                   # Alpaca exchange code for IEX

Transport = Callable[[str, dict], tuple[int, dict]]

# Read-only endpoints this client may call. Anything else raises ForbiddenEndpoint before a request is made.
ALLOWED_PREFIXES = (
    f"{DATA_URL}/bars?", f"{DATA_URL}/quotes?", f"{DATA_URL}/trades?", f"{CORP_ACTIONS_URL}?", f"{NEWS_URL}?",
    f"{PAPER_URL}/assets", f"{PAPER_URL}/account", f"{LIVE_URL}/account", f"{PAPER_URL}/calendar",
)
FORBIDDEN_FRAGMENTS = ("/orders", "/positions", "/watchlists", "/account/configurations", "/account/activities")
SIP_MIN_AGE = timedelta(minutes=16)                  # free plan: SIP history must end >= 15 minutes ago


class ForbiddenEndpoint(PermissionError):
    """Raised for any URL that is not a read-only market-data / reference endpoint."""


def check_endpoint(url: str) -> None:
    path = urllib.parse.urlsplit(url).path
    if any(f in path for f in FORBIDDEN_FRAGMENTS) or not url.startswith(ALLOWED_PREFIXES):
        raise ForbiddenEndpoint(f"refusing non-read-only endpoint: {urllib.parse.urlsplit(url).netloc}{path}")


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
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, json.JSONDecodeError) as e:
        # A dropped connection or proxy restart is transient: report it as a retryable 599 so the caller's
        # backoff applies, instead of aborting an hours-long download (incident 16).
        return 599, {"message": f"transport error: {type(e).__name__}"}


TICKER = re.compile(r"^[A-Z]{1,5}([.][A-Z]{1,2})?$")
INVALID_SYMBOL = re.compile(r"invalid symbol: (\S+)")


def is_ticker(s: str) -> bool:
    """Exchange tickers only. The asset master also lists CUSIP-like codes (rights, CVRs, escrows) and
    `<TICKER>_DELISTED` placeholders, which the market-data API rejects as symbols."""
    return bool(TICKER.match(s))


@dataclass(repr=False)
class AlpacaData:
    key_id: str
    secret: str
    transport: Transport = http_get
    calls: int = field(default=0)
    rejected_symbols: set = field(default_factory=set)
    min_interval: float = 0.0          # seconds between calls (from_env: 200/min free-plan limit, with margin)
    retries: int = 8                   # on 429, 5xx and transport errors (599), exponential backoff capped at 60 s
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last: float = field(default=-1e18)

    def __repr__(self):
        return "AlpacaData(key_id=<redacted>, secret=<redacted>)"

    @classmethod
    def from_env(cls, transport: Transport = http_get) -> "AlpacaData":
        k, s = os.environ.get("TRADELAB_PAPER_APCA_API_KEY_ID"), os.environ.get("TRADELAB_PAPER_APCA_API_SECRET_KEY")
        if not k or not s:
            raise RuntimeError("TRADELAB_PAPER_APCA_API_KEY_ID / _SECRET_KEY not set (see docs/CREDENTIALS_SETUP.md)")
        if any(n.startswith("TRADELAB_LIVE_") for n in os.environ):
            raise RuntimeError("live credentials present in a research process; refusing")
        base = os.environ.get("TRADELAB_PAPER_APCA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
        if base.removesuffix("/v2") != PAPER_URL.removesuffix("/v2"):
            raise RuntimeError("TRADELAB_PAPER_APCA_BASE_URL must be the paper host (https://paper-api.alpaca.markets)")
        return cls(k, s, transport, min_interval=0.31)

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self.key_id, "APCA-API-SECRET-KEY": self.secret}

    def _get(self, url: str) -> tuple[int, dict]:
        check_endpoint(url)
        status, body = 0, {}
        for attempt in range(self.retries + 1):
            wait = self._last + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            self.calls += 1
            status, body = self.transport(url, self._headers())
            if status != 429 and status < 500:
                return status, body
            if attempt < self.retries:
                self.sleep(min(60.0, 2.0 ** attempt))
        return status, body

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

    def bars(self, symbol, start, end, timeframe="1Min", feed="sip", adjustment="raw", asof: str | None = None):
        q = {"timeframe": timeframe, "start": _iso(start), "end": _iso(end), "feed": feed, "adjustment": adjustment}
        if asof is not None:
            q["asof"] = asof                         # "-" disables symbol mapping; a date maps renamed symbols
        return self._paged("bars", symbol, q)

    def trades(self, symbol, start, end, feed="sip"):
        return self._paged("trades", symbol, {"start": _iso(start), "end": _iso(end), "feed": feed})

    def quotes_multi(self, symbols: list[str], start, end, feed="sip", max_pages: int = 1000) -> tuple[int, dict[str, list]]:
        """Quotes for several symbols in one paged request (Alpaca's 10,000-row limit spans all symbols)."""
        out: dict[str, list] = {}
        token, status = None, 0
        for _ in range(max_pages):
            q = {"symbols": ",".join(symbols), "start": _iso(start), "end": _iso(end), "feed": feed, "limit": 10000,
                 **({"page_token": token} if token else {})}
            status, body = self._get(f"{DATA_URL}/quotes?{urllib.parse.urlencode(q)}")
            if status != 200:
                return status, out
            for sym, rows in (body.get("quotes") or {}).items():
                out.setdefault(sym, []).extend(rows)
            token = body.get("next_page_token")
            if not token:
                break
        return status, out

    def quotes(self, symbol, start, end, feed="sip"):
        return self._paged("quotes", symbol, {"start": _iso(start), "end": _iso(end), "feed": feed})


    def bars_multi(self, symbols: list[str], start, end, timeframe="1Min", feed="sip", adjustment="raw",
                   max_pages: int = 10000) -> tuple[int, dict[str, list]]:
        """Several symbols per request (Alpaca's limit of 10,000 points is across symbols); pages merged."""
        out: dict[str, list] = {}
        token, status = None, 0
        symbols = [s for s in symbols if is_ticker(s)]
        if not symbols:
            return 200, out
        for _ in range(max_pages):
            q = {"symbols": ",".join(symbols), "timeframe": timeframe, "start": _iso(start), "end": _iso(end),
                 "feed": feed, "adjustment": adjustment, "limit": 10000, **({"page_token": token} if token else {})}
            status, body = self._get(f"{DATA_URL}/bars?{urllib.parse.urlencode(q)}")
            bad = INVALID_SYMBOL.match(str((body or {}).get("message", ""))) if status == 400 and token is None else None
            if bad and bad.group(1) in symbols:
                # Alpaca rejects the whole request for one symbol it does not recognise: drop it and retry.
                self.rejected_symbols.add(bad.group(1))
                symbols = [s for s in symbols if s != bad.group(1)]
                if not symbols:
                    return 200, out
                continue
            if status != 200:
                return status, out
            for sym, rows in (body.get("bars") or {}).items():
                out.setdefault(sym, []).extend(rows)
            token = body.get("next_page_token")
            if not token:
                break
        return status, out

    def news(self, symbols: list[str], start, end, max_pages: int = 10000) -> tuple[int, list[dict]]:
        """News headlines (id, headline, summary, symbols, created_at, source), oldest first, paged."""
        out: list[dict] = []
        token, status = None, 0
        for _ in range(max_pages):
            q = {"symbols": ",".join(symbols), "start": _iso(start), "end": _iso(end), "limit": 50, "sort": "asc",
                 "include_content": "false", **({"page_token": token} if token else {})}
            status, body = self._get(f"{NEWS_URL}?{urllib.parse.urlencode(q)}")
            if status != 200:
                return status, out
            out.extend(body.get("news") or [])
            token = body.get("next_page_token")
            if not token:
                break
        return status, out

    def corporate_actions(self, types: list[str], start, end, max_pages: int = 1000) -> tuple[int, dict[str, list]]:
        """Corporate actions by type (mergers, name changes, worthless removals, splits...), paged, read-only."""
        out: dict[str, list] = {}
        token, status = None, 0
        for _ in range(max_pages):
            q = {"types": ",".join(types), "start": str(start)[:10], "end": str(end)[:10], "limit": 1000,
                 **({"page_token": token} if token else {})}
            status, body = self._get(f"{CORP_ACTIONS_URL}?{urllib.parse.urlencode(q)}")
            if status != 200:
                return status, out
            for kind, rows in (body.get("corporate_actions") or {}).items():
                out.setdefault(kind, []).extend(rows)
            token = body.get("next_page_token")
            if not token:
                break
        return status, out

    def assets(self, status: str | None = None, asset_class: str = "us_equity") -> tuple[int, list]:
        """Asset master. Without `status` Alpaca returns every status, including inactive (source F)."""
        q = {"asset_class": asset_class, **({"status": status} if status else {})}
        st, body = self._get(f"{PAPER_URL}/assets?{urllib.parse.urlencode(q)}")
        return st, (body if isinstance(body, list) else [])


def require_old_enough(end: datetime, now: datetime | None = None) -> None:
    """Free-plan SIP history must end >= 15 minutes ago; also guarantees a request never reaches data that
    could not have been known at `end` + 15 minutes."""
    now = now or datetime.now(timezone.utc)
    if end > now - SIP_MIN_AGE:
        raise ValueError(f"SIP request end {end.isoformat()} is less than {SIP_MIN_AGE} old")


def available_bars(rows: list[dict], as_of: datetime, bar_minutes: int = 1) -> list[dict]:
    """As-of filter: bars are stamped at their START, so a bar is known only once start + length <= as_of."""
    return [r for r in rows if parse_ts(r["t"]) + timedelta(minutes=bar_minutes) <= as_of]


def available_quotes(rows: list[dict], as_of: datetime) -> list[dict]:
    return [r for r in rows if parse_ts(r["t"]) <= as_of]


def parse_ts(s: str) -> datetime:
    """RFC-3339 with up to nanosecond precision -> aware UTC datetime (microseconds; sub-microsecond dropped)."""
    s = s.replace("Z", "+00:00")
    if "." in s:
        head, rest = s.split(".", 1)
        frac = "".join(ch for ch in rest if ch.isdigit())
        tz = rest[len(frac):]
        s = f"{head}.{frac[:6].ljust(6, '0')}{tz}"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


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
