"""Clock: local UTC time, with offset measured against exchange time endpoints.

The system clock is assumed NTP-synced. We measure offset = exchange - local
(using the request midpoint) and only correct received_at when the skew is
larger than the measurement uncertainty plus a tolerance; either way the
measured offset is recorded in FeedHealth so it can be audited.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.request
from datetime import datetime, timedelta, timezone

TIME_ENDPOINTS = {
    "coinbase": ("https://api.coinbase.com/api/v3/brokerage/time", lambda d: int(d["epochMillis"]) / 1000),
    "kraken": ("https://api.kraken.com/0/public/Time", lambda d: float(d["result"]["unixtime"])),  # 1 s resolution
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def measure_offset(venue: str, samples: int = 3, fetch=None) -> tuple[float, float]:
    """Return (offset_ms, rtt_ms) as the median over samples. offset > 0: exchange ahead."""
    url, parse = TIME_ENDPOINTS[venue]
    fetch = fetch or (lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "tradelab"}), timeout=10)))
    offs, rtts = [], []
    for _ in range(samples):
        t0 = time.time()
        server = parse(fetch(url))
        t1 = time.time()
        offs.append((server - (t0 + t1) / 2) * 1000)
        rtts.append((t1 - t0) * 1000)
    return statistics.median(offs), statistics.median(rtts)


class Clock:
    def __init__(self, tolerance_ms: float = 250.0):
        self.correction = timedelta(0)
        self.tolerance_ms = tolerance_ms

    def now(self) -> datetime:
        return utcnow() + self.correction

    def calibrate(self, offset_ms: float, rtt_ms: float, resolution_ms: float = 0.0) -> bool:
        """Apply a correction only if skew clearly exceeds measurement error. Returns True if corrected."""
        if abs(offset_ms) > self.tolerance_ms + rtt_ms / 2 + resolution_ms:
            self.correction = timedelta(milliseconds=offset_ms)
            return True
        return False
