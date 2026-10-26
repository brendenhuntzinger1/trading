"""Point-in-time OHLCV candles.

Every bar carries three times:
  * ``time``          candle start (exchange convention, UTC)
  * ``available_at``  candle end: the earliest moment the full bar is knowable
  * ``received_at``   when this system actually stored it

Backtests may only act on a bar at or after ``available_at``. Bars whose end
lies after the fetch time are incomplete and are never stored.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
COINBASE_CANDLES = "https://api.exchange.coinbase.com/products/{p}/candles?granularity={g}&start={s}&end={e}"
GRANULARITY = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400}


def _get_json(url: str, retries: int = 5):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tradelab-research"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:  # network errors and 429s: back off and retry
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def fetch_coinbase(product: str, tf: str, start: datetime, end: datetime | None = None) -> pd.DataFrame:
    """Download complete candles only, stamped with available_at and received_at."""
    g = GRANULARITY[tf]
    now = datetime.now(timezone.utc)
    end = min(end or now, now)
    rows, t = [], start
    while t < end:
        e = min(t + timedelta(seconds=g * 300), end)
        rows += _get_json(COINBASE_CANDLES.format(p=product, g=g, s=t.isoformat(), e=e.isoformat()))
        t = e
        time.sleep(0.12)
    received = pd.Timestamp(datetime.now(timezone.utc))
    df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"]).drop_duplicates("ts")
    df["time"] = pd.to_datetime(df.ts, unit="s", utc=True)
    df = df.sort_values("time").set_index("time")[["open", "high", "low", "close", "volume"]]
    df["available_at"] = df.index + pd.Timedelta(seconds=g)
    df = df[df.available_at <= received]          # drop the still-forming bar
    df["received_at"] = received
    return df


def save(df: pd.DataFrame, product: str, tf: str) -> Path:
    path = DATA_DIR / f"{product}_{tf}.csv"
    df.to_csv(path)
    return path


def load(product: str, tf: str, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Load candles. Files from the phase-1 fetcher lack availability columns; for
    those, available_at is reconstructed and the final bar is checked for
    completeness against the file's modification time instead of blindly dropped."""
    path = DATA_DIR / f"{product}_{tf}.csv"
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    step = pd.Timedelta(seconds=GRANULARITY[tf])
    if "available_at" not in df.columns:
        df["available_at"] = df.index + step
        df["received_at"] = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
    else:
        df["available_at"] = pd.to_datetime(df.available_at, utc=True)
        df["received_at"] = pd.to_datetime(df.received_at, utc=True)
    df = df[df.available_at <= df.received_at]
    if as_of is not None:
        df = df[df.available_at <= as_of]
    return df


@dataclass
class QualityReport:
    bars: int
    missing: list
    duplicates: int
    bad_ohlc: int
    nonpositive: int
    stale_runs: int          # runs of >=3 identical closes with zero range
    incomplete_tail: bool

    @property
    def ok(self) -> bool:
        return not (self.duplicates or self.bad_ohlc or self.nonpositive or self.incomplete_tail)


def quality(df: pd.DataFrame, tf: str, now: pd.Timestamp | None = None) -> QualityReport:
    step = pd.Timedelta(seconds=GRANULARITY[tf])
    idx = df.index
    full = pd.date_range(idx.min(), idx.max(), freq=step)
    flat = (df.high == df.low) & (df.close == df.close.shift(1))
    runs = (flat.astype(int).groupby((~flat).cumsum()).sum() >= 3).sum()
    now = now or pd.Timestamp.now(tz="UTC")
    return QualityReport(
        bars=len(df),
        missing=list(full.difference(idx)),
        duplicates=int(idx.duplicated().sum()),
        bad_ohlc=int(((df.low > df[["open", "close"]].min(axis=1)) | (df.high < df[["open", "close"]].max(axis=1))).sum()),
        nonpositive=int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
        stale_runs=int(runs),
        incomplete_tail=bool(len(df) and idx[-1] + step > now),
    )
