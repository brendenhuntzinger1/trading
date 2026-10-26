"""Ingestors. Each turns a source response into candidate Events stamped with
our receive time. Parsers are pure functions of (payload, received_at) so they
can be tested on saved fixtures without network access."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from . import classify as kw
from .schema import Category, Event, Tier

USER_AGENT = "tradelab-research/0.1 (research bot; contact via repository owner)"
NO_CONSENSUS = "no licensed consensus/expectations feed configured"
MAJOR_OUTLETS = frozenset({"reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com",
                           "washingtonpost.com", "bbc.co.uk", "bbc.com", "cnbc.com", "theguardian.com",
                           "economist.com", "nikkei.com", "aljazeera.com"})
ATOM = "{http://www.w3.org/2005/Atom}"
MACRO_MECHANISMS = {"rates_liquidity", "inflation_surprise", "labor_surprise", "growth_surprise"}


def fetch(url: str, timeout: int = 30, retry_429: float = 0.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # follows redirects
            return r.read()
    except urllib.error.HTTPError as ex:
        if ex.code == 429 and retry_429:
            time.sleep(retry_429)
            return fetch(url, timeout)
        raise


def _utc(t: datetime) -> datetime:
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _text(s: str | None, limit: int = 2000) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()[:limit]


# ---- feed parsing ----------------------------------------------------------
def parse_feed(payload: bytes) -> list[dict]:
    """RSS 2.0 or Atom -> [{title, link, published, body, guid}]."""
    root = ET.fromstring(payload)
    items = []
    for it in root.iter("item"):
        pub = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")
        items.append({"title": _text(it.findtext("title"), 500), "link": (it.findtext("link") or "").strip(),
                      "published": parsedate_to_datetime(pub) if pub and "," in pub
                      else datetime.fromisoformat(pub) if pub else None,
                      "body": _text(it.findtext("description")), "guid": (it.findtext("guid") or "").strip()})
    for en in root.iter(f"{ATOM}entry"):
        link = en.find(f"{ATOM}link")
        pub = en.findtext(f"{ATOM}published") or en.findtext(f"{ATOM}updated")
        items.append({"title": _text(en.findtext(f"{ATOM}title"), 500), "link": link.get("href") if link is not None else "",
                      "published": datetime.fromisoformat(pub) if pub else None,
                      "body": _text(en.findtext(f"{ATOM}content") or en.findtext(f"{ATOM}summary")),
                      "guid": (en.findtext(f"{ATOM}id") or "").strip()})
    return items


@dataclass
class Source:
    name: str
    url: str
    tier: Tier
    parser: Callable[["Source", bytes, datetime], list[Event]]
    default_category: Category = Category.OTHER
    enabled: bool = True
    min_interval_s: float = 0.0
    params: dict = field(default_factory=dict)

    def pull(self, received_at: datetime | None = None) -> list[Event]:
        received_at = received_at or datetime.now(timezone.utc)
        return self.parser(self, fetch(self.url), received_at)


def feed_parser(src: Source, payload: bytes, received_at: datetime) -> list[Event]:
    out = []
    for it in parse_feed(payload):
        if not it["link"] or not it["title"]:
            continue
        if it["link"].startswith(("www.", "//")):          # scheme-less link with explicit host (seen on BEA)
            it["link"] = "https://" + it["link"].lstrip("/")
        c = kw.classify(it["title"], it["body"], src.default_category)
        e = Event(source=src.name, source_url=it["link"], title=it["title"], body=it["body"],
                  published_at=_utc(it["published"]) if it["published"] else received_at,
                  published_at_basis="source" if it["published"] else "missing_used_first_seen",
                  first_seen_at=received_at, category=c.category, tier=src.tier, assets=c.assets,
                  mechanism=c.mechanism, evidence=c.evidence, external_id=it["guid"] or None,
                  classifier=c.classifier)
        if e.category in (Category.MACRO_RELEASE, Category.CENTRAL_BANK) and e.mechanism in MACRO_MECHANISMS:
            # Proposed transmission, not a text claim: rate expectations -> USD -> crypto risk appetite.
            e.assets = sorted(set(e.assets) | {"USD", "crypto_market"})
        if e.category is Category.MACRO_RELEASE:
            e.expected_reason = NO_CONSENSUS
            if src.params.get("indicator"):
                e.indicator, e.actual, ev = extract_actual(src.params["indicator"], it["title"] + ". " + it["body"])
                if ev:
                    e.evidence.append(ev)
        out.append(e)
    return out


# Official release text -> headline number, with the exact span it came from.
ACTUAL_PATTERNS = {
    "CPI_MoM_SA": r"(?:Consumer Price Index for All Urban Consumers|CPI for all items)[^.]*?(rose|increased|fell|decreased|declined|was unchanged)\s*(\d+(?:\.\d+)?)?\s*(?:percent|%)?",
    "NFP_change": r"nonfarm payroll employment\s*\(([+-][\d,]+)\)",
}


def extract_actual(indicator: str, text: str) -> tuple[str, float | None, str | None]:
    pat = ACTUAL_PATTERNS.get(indicator)
    m = re.search(pat, text, re.I) if pat else None
    if not m:
        return indicator, None, None
    if indicator == "CPI_MoM_SA":
        verb, num = m.group(1).lower(), m.group(2)
        val = 0.0 if "unchanged" in verb else float(num) * (-1 if verb in ("fell", "decreased", "declined") else 1) if num else None
    else:
        val = float(m.group(1).replace(",", ""))
    return indicator, val, m.group(0)


# ---- exchange status pages (Atlassian Statuspage v2) -------------------------
RELEVANT_INFRA = re.compile(r"\b(api|websockets?|fix|trading|orders?|order entry|matching|spot|website|"
                            r"app|login|advanced trade|exchange)\b", re.I)
RELEVANT_FUNDING = re.compile(r"\b(btc|bitcoin|eth|ether|ethereum)\s*(\(\w+\)\s*)?(deposits?|withdrawals?|funding|"
                              r"sends?|receives?)|\b(usd|us dollar|ach|wire|fedwire)\b", re.I)


def venue_relevant(name: str, components: list[str], impact: str | None) -> bool:
    """Our venue's trading path or BTC/ETH/USD funding; not other tokens' funding."""
    text = " ".join([name, *components])
    return bool(RELEVANT_INFRA.search(text) or RELEVANT_FUNDING.search(text)) or impact in ("major", "critical")


def statuspage_parser(src: Source, payload: bytes, received_at: datetime) -> list[Event]:
    d = json.loads(payload)
    rows = d.get("incidents", []) + d.get("scheduled_maintenances", [])
    out = []
    for i in rows:
        comps = [c["name"] for c in i.get("components", [])]
        updates = i.get("incident_updates") or []
        body = _text(updates[0]["body"]) if updates else ""
        relevant = venue_relevant(i["name"], comps, i.get("impact"))
        out.append(Event(
            source=src.name, source_url=i.get("shortlink") or f"{src.url.split('/api/')[0]}/incidents/{i['id']}",
            title=i["name"][:500], body=body, published_at=_utc(datetime.fromisoformat(i["created_at"])),
            published_at_basis="statuspage_created", first_seen_at=received_at,
            category=Category.EXCHANGE_INCIDENT, tier=src.tier,
            assets=["crypto_market"] if relevant else [], mechanism="venue_operational" if relevant else "unclear",
            external_id=i["id"], status=f"{i['status']}|{i.get('impact')}|"
                                        f"{i.get('scheduled_for') or ''}|{i.get('scheduled_until') or ''}",
            evidence=[i["name"]] + ([", ".join(comps)] if comps else []), classifier=f"rule:{src.name}"))
    return out


def incident_open(status: str | None) -> bool:
    return bool(status) and status.split("|")[0] in ("investigating", "identified", "monitoring", "in_progress", "verifying")


# ---- GDELT DOC 2.0 (geopolitical) ------------------------------------------
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc?{q}"
GDELT_QUERIES = [
    '(bitcoin OR cryptocurrency) (sanctions OR seizure OR ban OR war)',
    '("capital controls" OR "currency crisis" OR devaluation)',
    '(sanctions OR invasion OR missile OR blockade) ("oil price" OR markets OR dollar)',
]


def gdelt_url(query: str, timespan: str = "1d", maxrecords: int = 50) -> str:
    q = urllib.parse.urlencode({"query": query + " sourcelang:english", "mode": "artlist", "format": "json",
                                "maxrecords": maxrecords, "timespan": timespan, "sort": "datedesc"})
    return GDELT.format(q=q)


def gdelt_parser(src: Source, payload: bytes, received_at: datetime) -> list[Event]:
    try:
        d = json.loads(payload)
    except json.JSONDecodeError as ex:   # GDELT returns plain-text throttling notices
        raise RuntimeError(f"gdelt non-JSON response: {payload[:120]!r}") from ex
    out = []
    for a in d.get("articles", []):
        dom = (a.get("domain") or "").lower().removeprefix("www.")
        tier = Tier.MAJOR_OUTLET if dom in MAJOR_OUTLETS else Tier.CRYPTO_MEDIA
        seen = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        c = kw.classify(a["title"], "", Category.GEOPOLITICAL)
        out.append(Event(source=src.name, source_url=a["url"], title=_text(a["title"], 500),
                         published_at=seen, published_at_basis="gdelt_seendate", first_seen_at=received_at,
                         category=c.category, tier=tier, assets=c.assets, mechanism=c.mechanism,
                         evidence=c.evidence, classifier=c.classifier))
    return out


class GdeltSource(Source):
    def pull(self, received_at=None):
        received_at = received_at or datetime.now(timezone.utc)
        out = []
        for i, q in enumerate(self.params.get("queries", GDELT_QUERIES)):
            if i:
                time.sleep(6)   # GDELT asks for at most one request per 5 s
            out += self.parser(self, fetch(gdelt_url(q), retry_429=15), received_at)
        return out


# ---- FRED / ALFRED (point-in-time macro vintages; key required) -------------
class MissingCredential(RuntimeError):
    pass


class FredClient:
    """ALFRED real-time periods give the value *as it was known* on a date,
    which is what a point-in-time backtest needs. Requires FRED_API_KEY."""
    BASE = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str | None = None):
        self.key = api_key or os.environ.get("FRED_API_KEY")

    def observations(self, series_id: str, realtime_start: str, realtime_end: str, **kw_) -> list[dict]:
        if not self.key:
            raise MissingCredential("FRED_API_KEY not set (free key: fred.stlouisfed.org/docs/api/api_key.html)")
        q = {"series_id": series_id, "api_key": self.key, "file_type": "json",
             "realtime_start": realtime_start, "realtime_end": realtime_end, **kw_}
        return json.loads(fetch(f"{self.BASE}?{urllib.parse.urlencode(q)}"))["observations"]


# ---- registry ----------------------------------------------------------------
SOURCES: list[Source] = [
    Source("fed_press", "https://www.federalreserve.gov/feeds/press_all.xml", Tier.OFFICIAL, feed_parser, Category.OTHER),
    Source("bls_cpi", "https://www.bls.gov/feed/cpi.rss", Tier.OFFICIAL, feed_parser, Category.MACRO_RELEASE,
           params={"indicator": "CPI_MoM_SA"}),
    Source("bls_empsit", "https://www.bls.gov/feed/empsit.rss", Tier.OFFICIAL, feed_parser, Category.MACRO_RELEASE,
           params={"indicator": "NFP_change"}),
    Source("bea", "https://apps.bea.gov/rss/rss.xml", Tier.OFFICIAL, feed_parser, Category.MACRO_RELEASE),
    Source("sec_press", "https://www.sec.gov/news/pressreleases.rss", Tier.OFFICIAL, feed_parser, Category.REGULATORY),
    Source("cftc_press", "https://www.cftc.gov/RSS/RSSGP/rssgp.xml", Tier.OFFICIAL, feed_parser, Category.REGULATORY),
    Source("coinbase_status", "https://status.coinbase.com/api/v2/incidents.json", Tier.OFFICIAL, statuspage_parser),
    Source("coinbase_maint", "https://status.coinbase.com/api/v2/scheduled-maintenances/upcoming.json", Tier.OFFICIAL, statuspage_parser),
    Source("kraken_status", "https://status.kraken.com/api/v2/incidents.json", Tier.OFFICIAL, statuspage_parser),
    Source("kraken_maint", "https://status.kraken.com/api/v2/scheduled-maintenances/upcoming.json", Tier.OFFICIAL, statuspage_parser),
    # Disabled: from this container GDELT only ever returned its throttling notice / HTTP 429.
    # Enable on the always-on host after a successful live fetch.
    GdeltSource("gdelt_geo", "https://api.gdeltproject.org/api/v2/doc/doc", Tier.CRYPTO_MEDIA, gdelt_parser,
                Category.GEOPOLITICAL, enabled=False),
    Source("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", Tier.CRYPTO_MEDIA, feed_parser, Category.OTHER),
    # Lowest trust; off unless explicitly enabled. Never used for flags.
    Source("reddit_cryptocurrency", "https://www.reddit.com/r/CryptoCurrency/.rss", Tier.SOCIAL, feed_parser,
           Category.SOCIAL, enabled=False),
]
VENUE_SOURCES = {"coinbase": ("coinbase_status", "coinbase_maint"), "kraken": ("kraken_status", "kraken_maint")}
