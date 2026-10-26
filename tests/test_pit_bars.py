import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from tradelab.pit import crypto_bars as cb


class FakeAPI:
    """Serves synthetic candles for [start, end] like the Coinbase endpoint (newest first)."""
    def __init__(self, missing=()):
        self.missing = {pd.Timestamp(m) for m in missing}
        self.calls = 0

    def __call__(self, url, limiter):
        self.calls += 1
        q = dict(p.split("=", 1) for p in url.split("?")[1].split("&"))
        s, e = pd.Timestamp(q["start"]), pd.Timestamp(q["end"])
        out = []
        for t in pd.date_range(s.ceil("h"), e, freq="h"):
            if t in self.missing:
                continue
            px = 100 + (t.value // 3_600_000_000_000) % 7
            out.append([int(t.timestamp()), px - 1, px + 1, px, px + 0.5, 10.0])
        return out[::-1]


def test_fetch_resumes_without_duplicates_or_gaps(tmp_path):
    api = FakeAPI()
    lim = cb.RateLimiter(0)
    s = pd.Timestamp("2024-01-01", tz="UTC")
    n1 = cb.fetch_product("X-USD", s, s + pd.Timedelta(hours=500), lim, tmp_path, get=api)
    n2 = cb.fetch_product("X-USD", s, s + pd.Timedelta(hours=800), lim, tmp_path, get=api)
    df = cb.load("X-USD", tmp_path)
    assert n1 == 500 and n2 == 300 and len(df) == 800
    assert pd.read_csv(tmp_path / "X-USD.csv").time.duplicated().sum() == 0
    assert (df.available_at - df.index == pd.Timedelta(hours=1)).all()


def test_point_in_time_loader_hides_unavailable_bars(tmp_path):
    s = pd.Timestamp("2024-01-01", tz="UTC")
    cb.fetch_product("X-USD", s, s + pd.Timedelta(hours=48), cb.RateLimiter(0), tmp_path, get=FakeAPI())
    as_of = s + pd.Timedelta(hours=10, minutes=30)
    got = cb.load_hourly(["X-USD"], as_of=as_of, root=tmp_path)["X-USD"]
    assert got.index.max() == s + pd.Timedelta(hours=9)                       # bar 10:00-11:00 not complete at 10:30
    p = cb.panel(["X-USD"], as_of=as_of, root=tmp_path)
    assert p.index.max() == s + pd.Timedelta(hours=9)


def test_audit_separates_outages_from_no_trade_hours(tmp_path):
    s = pd.Timestamp("2024-01-01", tz="UTC")
    outage = [s + pd.Timedelta(hours=h) for h in (5, 6)]
    quiet = [s + pd.Timedelta(hours=h) for h in (20, 21, 22)]
    cb.fetch_product("BTC-USD", s, s + pd.Timedelta(hours=48), cb.RateLimiter(0), tmp_path, get=FakeAPI(outage))
    cb.fetch_product("ALT-USD", s, s + pd.Timedelta(hours=48), cb.RateLimiter(0), tmp_path, get=FakeAPI(outage + quiet))
    a = cb.audit_all(["ALT-USD"], root=tmp_path).loc["ALT-USD"]
    assert a.missing_hours == 5 and a.missing_outage_hours == 2 and a.missing_no_trade_hours == 3
    assert a.invalid_ohlc == 0 and a.duplicates_in_file == 0


def test_audit_flags_but_keeps_anomalies():
    idx = pd.date_range("2024-01-01", periods=100, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, 100)))
    df = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 5.0}, index=idx)
    df.iloc[50, df.columns.get_loc("close")] *= 2.0                            # spike (with a consistent high)
    df.iloc[50, df.columns.get_loc("high")] = df.iloc[50].close
    df.iloc[60, df.columns.get_loc("low")] = df.iloc[60].close * 1.5           # invalid OHLC
    df.iloc[70, df.columns.get_loc("volume")] = 0.0
    r = cb.audit_product(df, None)
    assert r["extreme_abs_logret_bars"] >= 1 and r["invalid_ohlc"] == 1 and r["zero_volume_bars"] == 1
    assert r["bars"] == 100


def test_second_fetcher_refused_and_repair_dedupes(tmp_path):
    with cb.FetchLock(tmp_path):
        with pytest.raises(RuntimeError, match="another fetcher"):
            with cb.FetchLock(tmp_path):
                pass
    s = pd.Timestamp("2024-01-01", tz="UTC")
    cb.fetch_product("X-USD", s, s + pd.Timedelta(hours=10), cb.RateLimiter(0), tmp_path, get=FakeAPI())
    raw = (tmp_path / "X-USD.csv").read_text().splitlines()
    (tmp_path / "X-USD.csv").write_text("\n".join(raw + raw) + "\n")         # duplicate rows and a 2nd header
    assert cb.repair("X-USD", tmp_path) == (21, 10)
    assert len(cb.load("X-USD", tmp_path)) == 10
