"""Hourly Coinbase candles for every product ever eligible: resumable fetch, a
point-in-time loader, and a data-quality audit.

Storage: data/pit/hourly/<PRODUCT>.csv with columns
  time (bar start, UTC), open, high, low, close, volume, available_at (= start + 1h), received_at.
Coinbase emits no candle for an hour without trades, so a missing hour is either
"no trades" or a venue outage; the audit separates them using BTC-USD as reference.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HOURLY_DIR = ROOT / "data" / "pit" / "hourly"
API = "https://api.exchange.coinbase.com/products/{p}/candles?granularity=3600&start={s}&end={e}"
COLS = ["open", "high", "low", "close", "volume"]
HOUR = pd.Timedelta(hours=1)


class RateLimiter:
    """Shared minimum spacing between requests across threads."""
    def __init__(self, min_interval_s: float = 0.12):
        self.min_interval, self.lock, self.last = min_interval_s, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = self.last + self.min_interval - now
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()


def _get(url: str, limiter: RateLimiter, retries: int = 6):
    for k in range(retries):
        limiter.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tradelab-pit"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if k == retries - 1:
                raise
            time.sleep(min(30, 2 ** k) * (2 if e.code == 429 else 1))
        except Exception:
            if k == retries - 1:
                raise
            time.sleep(min(30, 2 ** k))


def _path(product: str, root: Path = HOURLY_DIR) -> Path:
    return root / f"{product}.csv"


def last_stored(product: str, root: Path = HOURLY_DIR) -> pd.Timestamp | None:
    """Start time of the last stored bar (reads only the file tail)."""
    p = _path(product, root)
    if not p.exists() or p.stat().st_size == 0:
        return None
    with p.open("rb") as f:
        f.seek(max(0, p.stat().st_size - 4096))
        lines = [l for l in f.read().decode().splitlines() if l and not l.startswith("time")]
    return pd.Timestamp(lines[-1].split(",")[0]) if lines else None


def fetch_product(product: str, start: datetime, end: datetime, limiter: RateLimiter,
                  root: Path = HOURLY_DIR, get=_get, chunk_hours: int = 300) -> int:
    """Fetch [start, end) of complete hourly bars, resuming after the last stored bar.
    Appends one chunk at a time, so an interrupted run loses at most one chunk."""
    root.mkdir(parents=True, exist_ok=True)
    path = _path(product, root)
    last = last_stored(product, root)
    t = max(pd.Timestamp(start), last + HOUR) if last is not None else pd.Timestamp(start)
    now_complete = pd.Timestamp(datetime.now(timezone.utc)).floor("h")      # bars ending <= now
    end = min(pd.Timestamp(end), now_complete)
    written = 0
    while t < end:
        e = min(t + chunk_hours * HOUR, end)
        rows = get(API.format(p=product, s=t.isoformat(), e=(e - pd.Timedelta(seconds=1)).isoformat()), limiter) or []
        received = pd.Timestamp(datetime.now(timezone.utc))
        if rows:
            df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"])
            df["time"] = pd.to_datetime(df.ts, unit="s", utc=True)
            df = df[(df.time >= t) & (df.time < e)].drop_duplicates("time").sort_values("time")
            df["available_at"] = df.time + HOUR
            df = df[df.available_at <= received]                              # never store a forming bar
            df["received_at"] = received
            out = df[["time", *COLS, "available_at", "received_at"]]
            out.to_csv(path, mode="a", header=not path.exists() or path.stat().st_size == 0, index=False)
            written += len(out)
        t = e
    return written


class FetchLock:
    """Exclusive lock on the data directory: two fetchers appending to the same files
    would interleave duplicate rows (this happened once; repair() fixes such files)."""
    def __init__(self, root: Path = HOURLY_DIR):
        self.path = Path(root) / ".fetch.lock"

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = self.path.open("w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            raise RuntimeError(f"another fetcher holds {self.path}")
        return self

    def __exit__(self, *exc):
        import fcntl
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def repair(product: str, root: Path = HOURLY_DIR) -> tuple[int, int]:
    """Drop duplicate bar times (keep the first stored), sort, rewrite atomically."""
    p = _path(product, root)
    df = pd.read_csv(p, dtype=str)
    n0 = len(df)
    df = df[df.time != "time"]                                    # header lines written by a concurrent fetcher
    df[COLS] = df[COLS].astype(float)
    df = df.drop_duplicates("time", keep="first").sort_values("time")
    tmp = p.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(p)
    return n0, len(df)


def load(product: str, root: Path = HOURLY_DIR) -> pd.DataFrame:
    df = pd.read_csv(_path(product, root), dtype={c: float for c in COLS})
    for c in ("time", "available_at", "received_at"):
        df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601")
    return df.drop_duplicates("time", keep="last").set_index("time").sort_index()


def load_hourly(products: list[str], start=None, end=None, as_of=None, root: Path = HOURLY_DIR) -> dict[str, pd.DataFrame]:
    """Per-product hourly bars (index = bar start, UTC). With as_of, only bars whose
    available_at <= as_of are returned, i.e. what a decision at as_of could have seen."""
    out = {}
    for p in products:
        if not _path(p, root).exists():
            continue
        df = load(p, root)
        if start is not None:
            df = df[df.index >= pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else df.index >= pd.Timestamp(start)]
        if end is not None:
            df = df[df.index < (pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end))]
        if as_of is not None:
            df = df[df.available_at <= (pd.Timestamp(as_of, tz="UTC") if pd.Timestamp(as_of).tzinfo is None else pd.Timestamp(as_of))]
        out[p] = df
    return out


def panel(products: list[str], field: str = "close", start=None, end=None, as_of=None, root: Path = HOURLY_DIR) -> pd.DataFrame:
    """Aligned hourly panel (index = bar start on a full hourly grid, columns = products).
    Hours without a candle are NaN (no trades or outage) - never forward-filled here."""
    bars = load_hourly(products, start, end, as_of, root)
    if not bars:
        return pd.DataFrame()
    lo = min(b.index.min() for b in bars.values() if len(b))
    hi = max(b.index.max() for b in bars.values() if len(b))
    grid = pd.date_range(lo, hi, freq="h")
    return pd.DataFrame({p: b[field].reindex(grid) for p, b in bars.items()})


# ---------------------------------------------------------------- audit ----
def audit_product(df: pd.DataFrame, btc_hours: pd.DatetimeIndex | None, delisted_status: str | None = None,
                  extreme_abs_logret: float = 0.25, robust_z: float = 12.0, tiny_dollar_volume: float = 100.0) -> dict:
    """Quality metrics for one product's hourly bars. Nothing is deleted; anomalies are counted and flagged."""
    idx = df.index
    grid = pd.date_range(idx.min(), idx.max(), freq="h")
    missing = grid.difference(idx)
    outage = missing.intersection(grid.difference(btc_hours)) if btc_hours is not None else missing[:0]
    lr = np.log(df.close).diff()
    lr = lr[idx.to_series().diff() == HOUR]                                   # consecutive hours only
    mad = (lr - lr.median()).abs().median() or np.nan
    z = (lr - lr.median()).abs() / (1.4826 * mad) if mad and np.isfinite(mad) else lr * 0
    dvol = df.close * df.volume
    bad_ohlc = ((df.low > df[["open", "close"]].min(axis=1)) | (df.high < df[["open", "close"]].max(axis=1))
                | (df[COLS[:4]] <= 0).any(axis=1))
    return {
        "first_bar": idx.min(), "last_bar": idx.max(), "bars": len(df),
        "expected_hours": len(grid), "missing_hours": len(missing), "missing_pct": round(100 * len(missing) / max(1, len(grid)), 2),
        "missing_outage_hours": len(outage), "missing_no_trade_hours": len(missing) - len(outage),
        "duplicates_in_file": 0,  # filled by caller from the raw file
        "invalid_ohlc": int(bad_ohlc.sum()), "zero_volume_bars": int((df.volume <= 0).sum()),
        "tiny_dollar_volume_bars": int((dvol < tiny_dollar_volume).sum()),
        "extreme_abs_logret_bars": int((lr.abs() > extreme_abs_logret).sum()),
        "robust_z_outliers": int((z > robust_z).sum()),
        "max_abs_logret": round(float(lr.abs().max()), 4) if len(lr) else np.nan,
        "status_now": delisted_status,
    }


def audit_all(products: list[str], status: dict | None = None, root: Path = HOURLY_DIR) -> pd.DataFrame:
    btc = load("BTC-USD", root).index if _path("BTC-USD", root).exists() else None
    rows = []
    for p in products:
        if not _path(p, root).exists():
            rows.append({"product": p, "bars": 0})
            continue
        raw = pd.read_csv(_path(p, root), usecols=["time"])
        df = load(p, root)
        r = audit_product(df, btc, (status or {}).get(p))
        r["duplicates_in_file"] = int(raw.time.duplicated().sum())
        r["product"] = p
        rows.append(r)
    return pd.DataFrame(rows).set_index("product")


# Coinbase rebrands seen in the product list: a new product is listed while the old one keeps
# trading for a while, then the old one is delisted. They are separate products with separate
# histories; nothing is spliced.
KNOWN_REBRANDS = {"MATIC-USD": "POL-USD", "RNDR-USD": "RENDER-USD", "MKR-USD": "SKY-USD"}


def rebrand_overlap(old: str, new: str, root: Path = HOURLY_DIR, daily_dir: Path | None = None) -> dict:
    """Overlap between an old and a new product (daily files: first/last candle)."""
    from .crypto_universe import DAILY_DIR, load_daily
    d = daily_dir or DAILY_DIR
    try:
        a, b = load_daily(old, d), load_daily(new, d)
    except FileNotFoundError:
        return {"old": old, "new": new, "note": "missing daily file"}
    return {"old": old, "new": new, "old_first": a.index.min().date(), "old_last": a.index.max().date(),
            "new_first": b.index.min().date(), "overlap_days": int(max(0, (a.index.max() - b.index.min()).days + 1))}
