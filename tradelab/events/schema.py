"""Event record: what was said, by whom, when it was published, and when WE first
saw it. Only first_seen_at may be used as the decision-time availability of an
event; published_at is the source's claim and can be backdated or wrong."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Category(str, Enum):
    MACRO_RELEASE = "macro_release"
    CENTRAL_BANK = "central_bank"
    REGULATORY = "regulatory"
    EXCHANGE_INCIDENT = "exchange_incident"
    ASSET_NEWS = "asset_news"
    GEOPOLITICAL = "geopolitical"
    SOCIAL = "social"
    OTHER = "other"


class Tier(int, Enum):
    """Source reliability, best first."""
    OFFICIAL = 1        # the issuing authority itself (Fed, BLS, SEC, exchange status page about itself)
    MAJOR_OUTLET = 2    # wire services / major newspapers
    CRYPTO_MEDIA = 3    # specialist media, aggregated news of unknown provenance
    SOCIAL = 4          # social posts; lowest trust, disabled by default


class Novelty(str, Enum):
    NEW = "new"
    DUPLICATE = "duplicate"        # same story already stored (same or other source)
    CORRECTION = "correction"      # same source, revised / updated version of a stored story
    RESURFACED = "resurfaced"      # old story re-published or first seen long after publication


ASSETS = frozenset({"BTC", "ETH", "SOL", "LTC", "BCH", "ETC", "USD", "crypto_market"})

# Proposed transmission mechanisms: how an event could plausibly move prices.
MECHANISMS = frozenset({
    "rates_liquidity",          # policy rate / balance-sheet expectations -> risk appetite, USD
    "inflation_surprise",       # CPI/PCE vs expectations -> rate expectations
    "labor_surprise",           # payrolls/unemployment -> rate expectations
    "growth_surprise",          # GDP etc.
    "regulatory_access",        # approvals, bans, enforcement changing who can hold/trade
    "enforcement_flows",        # seizures, forced selling, exchange actions against a firm
    "venue_operational",        # exchange outage, halted deposits/withdrawals on our venue
    "geopolitical_risk_off",    # conflict/sanctions -> broad de-risking
    "capital_controls_demand",  # controls / currency stress -> local crypto demand
    "asset_specific_supply",    # unlocks, hacks, protocol upgrades, ETF flows
    "unclear",
})


@dataclass
class Event:
    source: str                     # registry name, e.g. "fed_press"
    source_url: str                 # canonical URL of the item
    title: str
    published_at: datetime          # as claimed by the source (UTC)
    first_seen_at: datetime         # our clock when the item was first stored (UTC)
    category: Category
    tier: Tier
    body: str = ""                  # excerpt only; never the basis for numbers
    assets: list[str] = field(default_factory=list)
    mechanism: str = "unclear"
    published_at_basis: str = "source"   # "source" | "gdelt_seendate" | "statuspage_created"
    external_id: str | None = None       # id at the source (statuspage incident id, ...)
    status: str | None = None            # incident status, if any
    last_seen_at: datetime | None = None
    novelty: Novelty = Novelty.NEW
    canonical_id: str | None = None      # id of the story this duplicates/corrects
    corroboration: int = 0               # independent sources that carried the same story
    uncertainty: str = "high"            # low | medium | high (derived, see derive_uncertainty)
    classifier: str = "keyword"          # "keyword" | "llm:<model>" | "rule:<source>"
    evidence: list[str] = field(default_factory=list)  # verbatim spans supporting assets/mechanism
    # Macro releases only
    indicator: str | None = None
    actual: float | None = None
    expected: float | None = None
    expected_reason: str | None = None   # why expected is null (e.g. no licensed consensus feed)
    surprise: float | None = None

    @property
    def id(self) -> str:
        key = self.external_id or self.source_url
        return hashlib.sha256(f"{self.source}|{key}".encode()).hexdigest()[:16]


class SchemaError(ValueError):
    pass


def validate(e: Event) -> Event:
    """Reject records that would let bad data reach the risk engine."""
    for name in ("published_at", "first_seen_at"):
        t = getattr(e, name)
        if t is None or t.tzinfo is None:
            raise SchemaError(f"{name} must be timezone-aware")
    if not e.title.strip() or len(e.title) > 500:
        raise SchemaError("title empty or too long")
    if not e.source_url.startswith(("https://", "http://")):
        raise SchemaError("source_url must be http(s)")
    bad = set(e.assets) - ASSETS
    if bad:
        raise SchemaError(f"assets outside allowlist: {sorted(bad)}")
    if e.mechanism not in MECHANISMS:
        raise SchemaError(f"unknown mechanism {e.mechanism!r}")
    if e.category is Category.MACRO_RELEASE and e.expected is None and not e.expected_reason:
        raise SchemaError("macro release without expectation must say why (expected_reason)")
    if e.surprise is not None and (e.actual is None or e.expected is None):
        raise SchemaError("surprise requires both actual and expected")
    return e


def derive_uncertainty(tier: Tier, corroboration: int) -> str:
    if tier is Tier.OFFICIAL:
        return "low"
    if tier is Tier.MAJOR_OUTLET and corroboration >= 1 or corroboration >= 2:
        return "medium"
    return "high"
