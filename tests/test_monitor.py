import json
from datetime import datetime, timedelta, timezone

from tradelab.data.live.feeds import make_feed
from tradelab.risk.limits import RiskLimits
from tradelab.service.monitor import Mids, status
from tests.conftest import ROOT


def _fed_feed():
    feed = make_feed(["BTC-USD", "ETH-USD"], "coinbase", measure_clock=False)
    t = None
    for line in (ROOT / "tests" / "fixtures" / "coinbase_raw.jsonl").read_text().splitlines():
        row = json.loads(line)
        raw = row.get("raw", line) if isinstance(row, dict) else line
        t = datetime.fromisoformat(row["received_at"]) if isinstance(row, dict) and "received_at" in row else datetime.now(timezone.utc)
        feed.handle(raw if isinstance(raw, str) else json.dumps(raw), t)
    for h in feed.health.values():
        h.connected = True
    return feed, t


def test_healthy_feed_has_no_breakers():
    feed, t = _fed_feed()
    st = status(feed, t, RiskLimits(), Mids(), [])
    valid = [s for s, r in st["symbols"].items() if r["book_valid"]]
    assert valid, "fixture should produce at least one valid book"
    if len(valid) == 2:
        assert st["breakers"] == {}


def test_silence_trips_stale_and_outage():
    feed, t = _fed_feed()
    st = status(feed, t + timedelta(minutes=10), RiskLimits(), Mids(), [])
    assert "stale_data" in st["breakers"]
    for h in feed.health.values():
        h.connected = False
    st = status(feed, t, RiskLimits(), Mids(), [])
    assert "exchange_outage" in st["breakers"]


def test_one_hour_move():
    m, t0 = Mids(), datetime(2026, 1, 1, tzinfo=timezone.utc)
    m.add("BTC-USD", t0, 100.0)
    m.add("BTC-USD", t0 + timedelta(minutes=30), 95.0)
    m.add("BTC-USD", t0 + timedelta(minutes=59), 90.0)
    assert abs(m.move("BTC-USD", t0 + timedelta(minutes=59)) + 0.10) < 1e-9
