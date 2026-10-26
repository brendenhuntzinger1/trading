from datetime import datetime, timedelta, timezone

from tradelab.events.evaluation import fill_outcomes, summary
from tradelab.events.pipeline import ingest_once
from tradelab.events.schema import Category, Event, Tier
from tradelab.events.sources import Source
from tradelab.events.store import EventStore

T = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def _src(name, events=None, boom=False):
    def parser(src, payload, received_at):
        raise AssertionError("not used")

    s = Source(name, "https://example.invalid", Tier.OFFICIAL, parser)
    s.pull = (lambda received_at=None: (_ for _ in ()).throw(RuntimeError("HTTP 503"))) if boom else \
             (lambda received_at=None: list(events))
    return s


def _ev(i):
    return Event(source="ok", source_url=f"https://example.invalid/{i}", title=f"Federal Reserve statement number {i} on policy",
                 published_at=T, first_seen_at=T, category=Category.CENTRAL_BANK, tier=Tier.OFFICIAL,
                 assets=["USD", "crypto_market"], mechanism="rates_liquidity")


def test_failing_source_is_logged_and_others_still_ingest(tmp_path):
    store = EventStore(tmp_path / "e.sqlite")
    res = ingest_once(store, [_src("bad", boom=True), _src("ok", [_ev(1)])], now=T)
    assert "error" in res["bad"] and res["ok"] == {"fetched": 1, "new": 1}
    assert store.db.execute("SELECT count(*) FROM ingest_log WHERE error IS NOT NULL").fetchone()[0] == 1


def test_outcomes_filled_only_after_horizon_and_from_first_seen(tmp_path):
    store = EventStore(tmp_path / "e.sqlite")
    store.add(_ev(1))
    prices = {T: 100.0, T + timedelta(hours=1): 101.0, T + timedelta(hours=4): 99.0, T + timedelta(hours=24): 110.0}
    price = lambda asset, t: prices.get(t)
    assert fill_outcomes(store, T + timedelta(hours=2), price) == 2          # +1h for BTC and ETH only
    assert fill_outcomes(store, T + timedelta(hours=25), price) == 4
    s = summary(store)
    assert round(s[("central_bank", "BTC", 24)]["mean"], 4) == 0.10
