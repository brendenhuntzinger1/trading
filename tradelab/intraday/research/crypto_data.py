"""Coinbase public candles for the crypto intraday study (C1/C2).

Coinbase omits candles for intervals with no trades (and during outages). Those
gaps are kept as gaps: no price is forward-filled into a fill.
Files: data/crypto_intraday/<SYMBOL>_<gran>.csv, columns time(start, UTC), open, high, low, close, volume.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "crypto_intraday"
API = "https://api.exchange.coinbase.com/products/{p}/candles?granularity={g}&start={s}&end={e}"
NAMES = {60: "1m", 300: "5m", 3600: "1h"}


def _get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tradelab-research"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(min(30, 2 ** i))


def fetch(product: str, gran: int, start: datetime, end: datetime, pause: float = 0.12) -> pd.DataFrame:
    rows, t, step = [], start, timedelta(seconds=gran * 300)
    while t < end:
        e = min(t + step, end)
        rows += _get(API.format(p=product, g=gran, s=t.isoformat(), e=e.isoformat()))
        t = e
        time.sleep(pause)
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"]).drop_duplicates("ts")
    df["time"] = pd.to_datetime(df.ts, unit="s", utc=True)
    df = df.sort_values("time").set_index("time")[["open", "high", "low", "close", "volume"]]
    # drop the still-forming bar
    return df[df.index + pd.Timedelta(seconds=gran) <= pd.Timestamp(datetime.now(timezone.utc))]


def path(product: str, gran: int) -> Path:
    return DIR / f"{product}_{NAMES[gran]}.csv"


def load(product: str, gran: int) -> pd.DataFrame:
    df = pd.read_csv(path(product, gran), index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def fetch_full(product: str, gran: int, start: datetime, end: datetime) -> Path:
    """Year-by-year with per-year cache files so an interrupted run resumes."""
    DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    y = start.year
    while datetime(y, 1, 1, tzinfo=timezone.utc) < end:
        s = max(start, datetime(y, 1, 1, tzinfo=timezone.utc))
        e = min(end, datetime(y + 1, 1, 1, tzinfo=timezone.utc))
        part = DIR / "parts" / f"{product}_{NAMES[gran]}_{y}.csv"
        if part.exists() and y < end.year:
            df = pd.read_csv(part, index_col=0)
            df.index = pd.to_datetime(df.index, utc=True)
        else:
            df = fetch(product, gran, s, e)
            part.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(part)
        parts.append(df)
        print(product, NAMES[gran], y, len(df), flush=True)
        y += 1
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated()]
    out.to_csv(path(product, gran))
    return path(product, gran)


def fetch_window(product: str, gran: int, start: datetime, end: datetime) -> pd.DataFrame:
    return fetch(product, gran, start, end, pause=0.12)


if __name__ == "__main__":
    end = datetime(2026, 10, 25, tzinfo=timezone.utc)
    jobs = []
    for p in ["BTC-USD", "ETH-USD", "SOL-USD"]:
        for g in (3600, 300):
            jobs.append((p, g))
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(lambda j: fetch_full(j[0], j[1], datetime(2019, 12, 1, tzinfo=timezone.utc), end), jobs))
    print("done")
