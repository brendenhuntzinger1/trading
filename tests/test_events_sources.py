from datetime import datetime, timezone
from pathlib import Path

from tradelab.events.schema import Category, Tier
from tradelab.events.sources import (SOURCES, extract_actual, feed_parser, gdelt_parser, statuspage_parser,
                                     venue_relevant)

FIX = Path(__file__).parent / "fixtures" / "events"
NOW = datetime(2026, 10, 25, 18, tzinfo=timezone.utc)
SRC = {s.name: s for s in SOURCES}


def test_rss_feed_parsed_with_utc_times_and_macro_assets():
    [e] = feed_parser(SRC["fed_press"], (FIX / "fed_rss.xml").read_bytes(), NOW)
    assert e.published_at == datetime(2026, 10, 28, 18, tzinfo=timezone.utc)
    assert e.first_seen_at == NOW and e.tier is Tier.OFFICIAL
    assert e.category is Category.CENTRAL_BANK and e.mechanism == "rates_liquidity"
    assert set(e.assets) == {"USD", "crypto_market"}


def test_atom_cpi_actual_extracted_with_verbatim_evidence_and_null_expectation_reason():
    evs = feed_parser(SRC["bls_cpi"], (FIX / "bls_cpi_atom.xml").read_bytes(), NOW)
    assert [e.actual for e in evs] == [0.6, -0.1]
    e = evs[0]
    assert e.expected is None and e.expected_reason and e.surprise is None
    assert any("rose 0.6 percent" in s for s in e.evidence)
    assert e.published_at.utcoffset().total_seconds() == 0


def test_extract_actual_variants():
    assert extract_actual("CPI_MoM_SA", "the CPI for all items was unchanged in May")[1] == 0.0
    assert extract_actual("NFP_change", "nonfarm payroll employment (-12,000) changed little")[1] == -12000
    assert extract_actual("NFP_change", "no number here")[1] is None


def test_statuspage_relevance_and_maintenance_window():
    evs = {e.external_id: e for e in statuspage_parser(SRC["coinbase_status"], (FIX / "statuspage.json").read_bytes(), NOW)}
    assert evs["inc1"].mechanism == "venue_operational" and evs["inc1"].status.startswith("investigating|major")
    assert evs["inc2"].mechanism == "unclear" and evs["inc2"].assets == []        # another token's funding
    assert evs["m1"].status.split("|")[2] == "2026-10-28T06:00:00Z"


def test_venue_relevance_rules():
    assert venue_relevant("Order Entry System Maintenance", ["FIX"], "maintenance")
    assert venue_relevant("Bitcoin (BTC) Funding Delays", [], "minor")
    assert not venue_relevant("VANRY withdrawals on Ethereum blockchain halted.", [], "minor")
    assert venue_relevant("Some unrelated thing", [], "critical")


def test_gdelt_tiers_by_domain_and_seendate_basis():
    evs = gdelt_parser(SRC["gdelt_geo"], (FIX / "gdelt.json").read_bytes(), NOW)
    assert [e.tier for e in evs] == [Tier.MAJOR_OUTLET, Tier.CRYPTO_MEDIA]
    assert all(e.published_at_basis == "gdelt_seendate" for e in evs)
    assert evs[0].mechanism in ("geopolitical_risk_off", "enforcement_flows", "regulatory_access")


def test_social_source_disabled_by_default():
    assert not SRC["reddit_cryptocurrency"].enabled and SRC["reddit_cryptocurrency"].tier is Tier.SOCIAL
