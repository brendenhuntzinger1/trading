from datetime import datetime, timedelta, timezone

import pytest

from tradelab.events.schema import Category, Event, Novelty, SchemaError, Tier, validate
from tradelab.events.store import EventStore

T0 = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def ev(**kw):
    base = dict(source="sec_press", source_url="https://www.sec.gov/news/press-release/2026-101",
                title="SEC charges crypto lender with fraud", published_at=T0, first_seen_at=T0,
                category=Category.REGULATORY, tier=Tier.OFFICIAL, assets=["crypto_market"],
                mechanism="enforcement_flows")
    base.update(kw)
    return Event(**base)


@pytest.fixture
def store(tmp_path):
    return EventStore(tmp_path / "e.sqlite")


def test_schema_rejects_naive_times_unknown_assets_and_unexplained_missing_expectation():
    with pytest.raises(SchemaError):
        validate(ev(published_at=datetime(2026, 10, 25)))
    with pytest.raises(SchemaError):
        validate(ev(assets=["DOGE"]))
    with pytest.raises(SchemaError):
        validate(ev(mechanism="moon"))
    with pytest.raises(SchemaError):
        validate(ev(category=Category.MACRO_RELEASE, indicator="CPI_MoM_SA", actual=0.3))
    with pytest.raises(SchemaError):
        validate(ev(category=Category.MACRO_RELEASE, actual=0.3, surprise=0.1, expected_reason="none"))
    validate(ev(category=Category.MACRO_RELEASE, actual=0.3, expected_reason="no licensed consensus"))


def test_refetching_same_item_is_duplicate_and_keeps_first_seen(store):
    assert store.add(ev()) is Novelty.NEW
    later = T0 + timedelta(days=45)    # beyond the 30-day similarity window
    assert store.add(ev(first_seen_at=later)) is Novelty.DUPLICATE
    stored = store.events()
    assert len(stored) == 1 and stored[0].first_seen_at == T0 and stored[0].novelty is Novelty.NEW


def test_same_story_from_another_outlet_corroborates(store):
    store.add(ev(source="gdelt_geo", source_url="https://www.reuters.com/a", tier=Tier.MAJOR_OUTLET,
                 title="SEC charges crypto lender with fraud over reserves"))
    n = store.add(ev(source="gdelt_geo", source_url="https://apnews.com/b", tier=Tier.MAJOR_OUTLET,
                     title="SEC charges crypto lender with fraud over reserves claims",
                     first_seen_at=T0 + timedelta(minutes=20)))
    assert n is Novelty.DUPLICATE
    [e] = store.events()
    assert e.corroboration == 1 and e.uncertainty == "medium"


def test_same_outlet_republishing_does_not_corroborate(store):
    store.add(ev(source="coindesk", source_url="https://www.coindesk.com/a", tier=Tier.CRYPTO_MEDIA,
                 title="Exchange halts withdrawals after hack"))
    store.add(ev(source="coindesk", source_url="https://www.coindesk.com/a-2", tier=Tier.CRYPTO_MEDIA,
                 title="Exchange halts withdrawals after hack", first_seen_at=T0 + timedelta(hours=1)))
    assert store.events()[0].corroboration == 0


def test_correction_from_same_source_replaces_content_keeps_first_seen(store):
    store.add(ev(source="coindesk", source_url="https://www.coindesk.com/a", tier=Tier.CRYPTO_MEDIA,
                 title="Exchange loses $40 million in hack of hot wallet"))
    n = store.add(ev(source="coindesk", source_url="https://www.coindesk.com/a-corrected", tier=Tier.CRYPTO_MEDIA,
                     title="CORRECTION: Exchange loses $4 million in hack of hot wallet",
                     first_seen_at=T0 + timedelta(hours=3)))
    assert n is Novelty.CORRECTION
    [e] = store.events()
    assert "$4 million" in e.title and e.first_seen_at == T0 and store.revisions(e.id) == 1


def test_statuspage_status_change_is_correction_with_point_in_time_history(store):
    a = ev(source="coinbase_status", source_url="https://stspg.io/x", external_id="inc1", status="investigating|major||",
           category=Category.EXCHANGE_INCIDENT, mechanism="venue_operational", title="API degraded")
    store.add(a)
    b = ev(source="coinbase_status", source_url="https://stspg.io/x", external_id="inc1", status="resolved|major||",
           category=Category.EXCHANGE_INCIDENT, mechanism="venue_operational", title="API degraded",
           first_seen_at=T0 + timedelta(hours=2))
    assert store.add(b) is Novelty.CORRECTION
    assert store.status_as_of(a.id, T0 + timedelta(hours=1)).startswith("investigating")
    assert store.status_as_of(a.id, T0 + timedelta(hours=3)).startswith("resolved")


def test_old_story_first_seen_now_is_resurfaced(store):
    assert store.add(ev(published_at=T0 - timedelta(days=30))) is Novelty.RESURFACED


def test_near_duplicate_of_old_story_is_resurfaced_and_linked(store):
    store.add(ev(source="gdelt_geo", source_url="https://site-a.example/x", tier=Tier.CRYPTO_MEDIA))
    n = store.add(ev(source="gdelt_geo", source_url="https://site-b.example/y", tier=Tier.CRYPTO_MEDIA,
                     first_seen_at=T0 + timedelta(days=10), published_at=T0 + timedelta(days=10)))
    assert n is Novelty.RESURFACED
    assert [e.canonical_id for e in store.events()][1] == store.events()[0].id


def test_point_in_time_query_excludes_events_not_yet_seen(store):
    store.add(ev())
    assert store.events(until=T0 - timedelta(seconds=1)) == []


def test_official_confirmation_of_media_story_is_kept_as_own_record(store):
    store.add(ev(source="coindesk", source_url="https://www.coindesk.com/a", tier=Tier.CRYPTO_MEDIA))
    n = store.add(ev(first_seen_at=T0 + timedelta(hours=2)))      # SEC's own release, same story
    assert n is Novelty.NEW
    media, official = store.events()
    assert official.tier is Tier.OFFICIAL and official.canonical_id == media.id
    assert official.first_seen_at == T0 + timedelta(hours=2)        # point-in-time: confirmation came later
    assert media.corroboration == 1


def test_recurring_templated_releases_from_same_source_stay_distinct(store):
    store.add(ev(source="bls_cpi", source_url="https://www.bls.gov/cpi_09112026.htm",
                 title="CPI for all items increases 0.4% in August; shelter rises"))
    n = store.add(ev(source="bls_cpi", source_url="https://www.bls.gov/cpi_10142026.htm",
                     title="CPI for all items increases 0.6% in September; gasoline rises",
                     first_seen_at=T0 + timedelta(days=1)))
    assert n is Novelty.NEW and len(store.events()) == 2


def test_recurring_incidents_with_own_ids_stay_distinct(store):
    for i in (1, 2):
        store.add(ev(source="kraken_status", source_url=f"https://stspg.io/{i}", external_id=f"id{i}",
                     title="Tezos (XTZ) Funding Delays", category=Category.EXCHANGE_INCIDENT,
                     first_seen_at=T0 + timedelta(hours=i)))
    assert len(store.events()) == 2
