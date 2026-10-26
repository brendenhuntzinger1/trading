"""Yahoo chart API client (unofficial, no key). Research and paper only: no SLA,
possibly delayed, and its terms limit use. A broker data feed replaces it for live."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval={i}&{span}&includePrePost=false"
STEP = {"1m": pd.Timedelta(minutes=1), "5m": pd.Timedelta(minutes=5), "1h": pd.Timedelta(hours=1), "1d": pd.Timedelta(days=1)}


def bars(symbol: str, interval: str, span: str, now: datetime | None = None, retries: int = 4) -> pd.DataFrame:
    """Complete bars only (a bar still forming is dropped). Index = bar start (UTC).
    span: e.g. 'range=5d' or 'period1=...&period2=...'."""
    for k in range(retries):
        try:
            req = urllib.request.Request(URL.format(s=symbol, i=interval, span=span), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.load(r)["chart"]["result"][0]
            break
        except Exception:
            if k == retries - 1:
                raise
            time.sleep(2 ** k)
    q = res["indicators"]["quote"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    df = pd.DataFrame({c: q[c] for c in ("open", "high", "low", "close", "volume")}, index=idx).dropna(subset=["open", "close"])
    df = df[~df.index.duplicated(keep="last")]
    if interval != "1d":
        et = df.index.tz_convert("America/New_York")
        mins = et.hour * 60 + et.minute
        df = df[(mins >= 9 * 60 + 30) & (mins < 16 * 60)]          # regular session only (drops the 16:00 print bar)
        now = now or datetime.now(timezone.utc)
        close_t = res["meta"].get("currentTradingPeriod", {}).get("regular", {}).get("end")
        ends = df.index + STEP[interval]
        if close_t:
            ends = ends.where(ends <= pd.Timestamp(close_t, unit="s", tz="UTC"), pd.Timestamp(close_t, unit="s", tz="UTC"))
        df = df[ends <= pd.Timestamp(now)]
    else:
        tz = res["meta"].get("exchangeTimezoneName", "America/New_York")
        df.index = df.index.tz_convert(tz).strftime("%Y-%m-%d")
    df.attrs["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return df
