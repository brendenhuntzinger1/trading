from datetime import datetime, timedelta, timezone

import pytest

from tradelab.events.calendar import CalendarRow, meeting_end
from tradelab.events.flags import FlagConfig, active_flags
from tradelab.events.schema import Category, Event, Tier
from tradelab.events.store import EventStore

T = datetime(2026, 10, 28, 18, tzinfo=timezone.utc)   # FOMC statement time (2:00 p.m. EDT)
ROWS = [
    CalendarRow("fomc_decision", "October 27-28 - 2026", T.isoformat(), "2:00 p.m. EDT", True, False, "https://fed/x", "https://fed"),
    CalendarRow("fomc_unscheduled", "March 15 (unscheduled)", (T + timedelta(minutes=30)).isoformat(), "", False, False, "u", "u"),
]


@pytest.fixture
def store(tmp_path):
    return EventStore(tmp_path / "e.sqlite")


def kinds(fl):
    return sorted(f.kind for f in fl)


def test_macro_window_bounds_and_unscheduled_excluded(store):
    assert kinds(active_flags(T - timedelta(hours=1), store, ROWS)) == ["macro_window"]
    assert kinds(active_flags(T + timedelta(hours=1, minutes=59), store, ROWS)) == ["macro_window"]
    assert active_flags(T - timedelta(hours=3), store, ROWS) == []
    f = active_flags(T, store, ROWS)
    assert len(f) == 1 and f[0].source_urls == ("https://fed/x",)


def _incident(store, status, seen, ext="inc1", src="coinbase_status"):
    store.add(Event(source=src, source_url=f"https://stspg.io/{ext}", title="Advanced Trade API degraded",
                    published_at=T - timedelta(hours=5), first_seen_at=seen, category=Category.EXCHANGE_INCIDENT,
                    tier=Tier.OFFICIAL, assets=["crypto_market"], mechanism="venue_operational", external_id=ext,
                    status=status, published_at_basis="statuspage_created"))


def test_venue_incident_open_then_resolved_is_point_in_time(store):
    _incident(store, "investigating|major||", T - timedelta(hours=4))
    _incident(store, "resolved|major||", T - timedelta(hours=1))
    assert kinds(active_flags(T - timedelta(hours=2), store, [])) == ["venue_incident"]
    assert active_flags(T - timedelta(hours=2), store, [])[0].severity == "critical"
    assert active_flags(T, store, []) == []
    assert active_flags(T - timedelta(hours=5), store, []) == []    # not yet seen


def test_other_venue_ignored(store):
    _incident(store, "investigating|major||", T - timedelta(hours=1), src="kraken_status")
    assert active_flags(T, store, []) == []
    assert kinds(active_flags(T, store, [], FlagConfig(venue="kraken"))) == ["venue_incident"]


def test_maintenance_flag_window(store):
    store.add(Event(source="coinbase_maint", source_url="https://stspg.io/m1", title="Order Entry System Maintenance",
                    published_at=T - timedelta(days=3), first_seen_at=T - timedelta(days=3),
                    category=Category.EXCHANGE_INCIDENT, tier=Tier.OFFICIAL, assets=["crypto_market"],
                    mechanism="venue_operational", external_id="m1",
                    status=f"scheduled|maintenance|{(T + timedelta(hours=2)).isoformat()}|{(T + timedelta(hours=3)).isoformat()}"))
    assert active_flags(T, store, []) == []
    assert kinds(active_flags(T + timedelta(hours=1, minutes=30), store, [])) == ["venue_maintenance"]
    assert active_flags(T + timedelta(hours=4), store, []) == []


def _reg(store, tier, corroboration=0, url="https://www.sec.gov/a"):
    store.add(Event(source="sec_press" if tier is Tier.OFFICIAL else "coindesk", source_url=url,
                    title="SEC sues exchange over unregistered crypto trading", published_at=T, first_seen_at=T,
                    category=Category.REGULATORY, tier=tier, assets=["crypto_market"], mechanism="enforcement_flows",
                    corroboration=corroboration))


def test_regulatory_flag_needs_official_source_or_corroboration(store):
    _reg(store, Tier.CRYPTO_MEDIA, url="https://coindesk.com/x")
    assert active_flags(T + timedelta(hours=1), store, []) == []
    _reg(store, Tier.OFFICIAL)
    fl = active_flags(T + timedelta(hours=1), store, [])
    assert kinds(fl) == ["regulatory_action"] and fl[0].severity == "caution"


def test_meeting_end_parsing():
    assert str(meeting_end("Apr/May 30-1 - 2027")) == "2027-05-01"
    assert str(meeting_end("December 8-9* - 2026")) == "2026-12-09"
    assert str(meeting_end("March 15 (unscheduled) Meeting - 2020")) == "2020-03-15"
