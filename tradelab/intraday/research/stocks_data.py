"""US stock data for intraday research (Yahoo chart API, unofficial).

Every file stores exchange-local time (America/New_York) and UTC, plus the
fetch time. Prices are split-adjusted by Yahoo (not dividend-adjusted), which
is what open-to-close and gap calculations need.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "stocks"
UA = {"User-Agent": "Mozilla/5.0"}   # a full browser UA string is rate-limited (429); the short form is not
WIKI = "https://en.wikipedia.org/wiki/S%26P_100"
INDEX_ETFS = ["SPY", "QQQ", "IWM", "DIA"]
SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?{q}"
TZ = "America/New_York"


def _get(url: str, tries: int = 5):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 ** k)


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.cur, self.row, self.cell, self.depth = [], None, None, None, 0

    def handle_starttag(self, t, a):
        if t == "table":
            self.depth += 1
            if self.depth == 1:
                self.cur = []
        elif t == "tr" and self.cur is not None:
            self.row = []
        elif t in ("td", "th") and self.row is not None:
            self.cell = ""

    def handle_endtag(self, t):
        if t in ("td", "th") and self.cell is not None:
            self.row.append(self.cell.strip()); self.cell = None
        elif t == "tr" and self.row is not None:
            self.cur.append(self.row); self.row = None
        elif t == "table":
            self.depth -= 1
            if self.depth == 0:
                self.tables.append(self.cur); self.cur = None

    def handle_data(self, d):
        if self.cell is not None:
            self.cell += d


def fetch_universe() -> pd.DataFrame:
    p = _Tables(); p.feed(_get(WIKI).decode())
    t = next(t for t in p.tables if t and t[0][:3] == ["Symbol", "Name", "Sector"])
    df = pd.DataFrame(t[1:], columns=t[0])
    df["yahoo"] = df.Symbol.str.replace(".", "-", regex=False)
    df["kind"] = "stock"
    etf = pd.DataFrame({"Symbol": INDEX_ETFS + SECTOR_ETFS, "Name": "", "Sector": "ETF",
                        "yahoo": INDEX_ETFS + SECTOR_ETFS, "kind": ["index_etf"] * 4 + ["sector_etf"] * 11})
    out = pd.concat([df, etf], ignore_index=True)
    out["source"] = WIKI
    out["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(DIR / "universe.csv", index=False)
    return out


def _chart(sym: str, query: str) -> pd.DataFrame:
    d = json.loads(_get(CHART.format(s=sym, q=query)))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]},
                      index=pd.to_datetime(d["timestamp"], unit="s", utc=True))
    df.index.name = "time_utc"
    df = df.dropna(subset=["open", "close"])
    df = df[~df.index.duplicated(keep="last")]
    df["time_et"] = df.index.tz_convert(TZ).strftime("%Y-%m-%d %H:%M")
    df["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return df


def fetch(sym: str, kind: str) -> pd.DataFrame:
    q = {"daily": "interval=1d&period1=946684800&period2=1792800000",
         "hourly": "interval=1h&range=730d", "m5": "interval=5m&range=60d"}[kind]
    df = _chart(sym, q)
    (DIR / kind).mkdir(parents=True, exist_ok=True)
    df.to_csv(DIR / kind / f"{sym}.csv")
    return df


def load(sym: str, kind: str) -> pd.DataFrame:
    df = pd.read_csv(DIR / kind / f"{sym}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def universe() -> pd.DataFrame:
    return pd.read_csv(DIR / "universe.csv")


def daily_session_dates(df: pd.DataFrame) -> pd.Series:
    """Exchange-local session date of each daily bar."""
    return pd.to_datetime(df.time_et.str[:10])


if __name__ == "__main__":
    u = fetch_universe()
    print("universe", len(u))
    failed = []
    for s in u.yahoo:
        for kind in ("daily", "hourly", "m5"):
            try:
                fetch(s, kind)
            except Exception as e:
                failed.append((s, kind, repr(e)[:80]))
            time.sleep(0.4)
    print("failed", failed)
