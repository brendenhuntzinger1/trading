"""RESEARCH-ONLY derivatives inputs (funding, open interest, basis).

These are read-only market signals from Kraken Futures' public API. Nothing
in this module can place orders, and US persons cannot trade these contracts;
the platform remains spot-only. Use as candidate features, evaluated like any
other input before it may influence decisions.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from .feeds import parse_ts

TICKERS = "https://futures.kraken.com/derivatives/api/v3/tickers"
FUNDING_HISTORY = "https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol={sym}"
PERPS = {"BTC-USD": "PF_XBTUSD", "ETH-USD": "PF_ETHUSD", "SOL-USD": "PF_SOLUSD"}


@dataclass(frozen=True)
class PerpSnapshot:
    symbol: str                   # spot symbol this perp maps to
    perp: str
    mark: float
    index: float
    basis: float                  # mark / index - 1
    funding_rate_hourly: float    # relativeFundingRate: fraction of notional per hour
    funding_rate_annualized: float
    open_interest: float          # contracts (1 contract = 1 unit of base for PF_ perps)
    event_time: datetime
    received_at: datetime
    research_only: bool = True


def _get(url: str):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "tradelab-research"}), timeout=15))


def perp_snapshots(symbols=("BTC-USD", "ETH-USD"), fetch=_get) -> list[PerpSnapshot]:
    d = fetch(TICKERS)
    received = datetime.now(timezone.utc)
    by = {t["symbol"]: t for t in d.get("tickers", [])}
    out = []
    for s in symbols:
        t = by.get(PERPS.get(s, ""))
        if not t or t.get("suspended"):
            continue
        rel = float(t.get("relativeFundingRate", 0.0))
        out.append(PerpSnapshot(s, t["symbol"], float(t["markPrice"]), float(t["indexPrice"]),
                                float(t["markPrice"]) / float(t["indexPrice"]) - 1, rel, rel * 24 * 365,
                                float(t.get("openInterest", 0.0)),
                                parse_ts(t["lastTime"]) if t.get("lastTime") else received,
                                received))
    return out


def funding_history(symbol: str = "BTC-USD", fetch=_get) -> list[tuple[datetime, float]]:
    """(funding period timestamp, relative hourly rate). Published after each
    period, so a backtest may use a rate only after its timestamp."""
    d = fetch(FUNDING_HISTORY.format(sym=PERPS[symbol]))
    return [(parse_ts(r["timestamp"]), float(r["relativeFundingRate"])) for r in d.get("rates", [])]
