# News, economic and geopolitical events

Code: `tradelab/events/`. Tests: `tests/test_events_*.py`. Data: `data/events/` (SQLite store, macro calendar, page cache).

## What it is for

It gives the **risk engine** deterministic flags ("FOMC decision in 90 minutes", "our exchange reports a
major API incident", "the SEC announced an enforcement action involving crypto"), and it builds a dataset to
**evaluate news features prospectively**. It does not trade, size or predict anything.

**No historical news performance is claimed.** There is no point-in-time archive of historical news in
this project: feeds only expose recent items, and their timestamps are the publisher's claim. Any
"news signal" must earn its place on events recorded live from now on (`evaluation.py`). The one exception
is the **scheduled macro calendar**. Release dates for FOMC decisions, CPI and payrolls are published in
advance by the issuing agencies, so they are legitimate backtest inputs.

## Event record (`schema.py`)

| Field | Meaning |
|---|---|
| `source`, `source_url` | registry name and canonical item URL |
| `published_at` (+ `published_at_basis`) | the source's own timestamp (`source`), GDELT's crawl time (`gdelt_seendate`) or Statuspage creation time |
| `first_seen_at` | **our** clock when first stored: the only time a backtest or live rule may treat it as known |
| `last_seen_at` | last re-fetch or revision |
| `category` | macro_release, central_bank, regulatory, exchange_incident, asset_news, geopolitical, social, other |
| `assets` | allowlist: BTC, ETH, SOL, LTC, BCH, ETC, USD, crypto_market |
| `mechanism` | fixed vocabulary: rates_liquidity, inflation_surprise, labor_surprise, growth_surprise, regulatory_access, enforcement_flows, venue_operational, geopolitical_risk_off, capital_controls_demand, asset_specific_supply, unclear |
| `tier` | 1 official issuer, 2 wire/major outlet, 3 crypto media / unknown outlet, 4 social |
| `uncertainty` | low (official), medium (major outlet + 1 independent corroboration, or 2+), high otherwise |
| `corroboration` | number of *other domains* that carried the same story |
| `novelty` | new, duplicate, correction, resurfaced |
| `evidence` | verbatim sentences that triggered each label |
| `indicator`, `actual`, `expected`, `expected_reason`, `surprise` | macro releases only. `actual` is parsed from the agency's own release text (evidence kept). `expected` is **null**, and `expected_reason` says why: no licensed consensus feed. `surprise` cannot be computed without one, and the schema rejects a surprise without both values |

Every accepted version is kept in `event_versions`, so an incident's status can be read **as of** any past
time (`EventStore.status_as_of`). Flags use this.

## Novelty rules (`dedupe.py`)

- **Same item re-fetched** (same source and URL or external id, looked up across the whole store) → `duplicate`,
  or `correction` if the title, body, status or value changed. The original `first_seen_at` is never overwritten.
- **Same story, another domain** (title word-bigram Jaccard ≥ 0.6, numbers masked) → `duplicate`, and the
  stored story's corroboration +1. If the new copy is from a **more reliable tier** (e.g. the SEC's own
  release of a story first seen on a crypto site), it is stored as its own record with its own
  `first_seen_at`, linked by `canonical_id`. The official confirmation is dated when it actually arrived.
- **Same outlet, different item:** treated as distinct unless the title is identical, because recurring
  templated titles ("CPI for all items increases 0.2% in …", "Funding Delays") are different events.
  Items with their own ids are never title-merged.
- **Correction:** same outlet, changed content, plus a correction/update marker → replaces content and
  increments `revisions`.
- **Resurfaced:** published more than 7 days before we first saw it, or a near-copy of a story first seen
  more than 7 days ago. On the first ingestion pass almost everything is `resurfaced`. That is correct, since
  those items are stale for trading purposes. Flags ignore resurfaced and duplicate items.

## Sources (`sources.py`), verified from this container on 2026-10-25

| Source | Tier | Endpoint | Status |
|---|---|---|---|
| Federal Reserve press releases | 1 | federalreserve.gov/feeds/press_all.xml | ✅ 20 items |
| BLS CPI (actual parsed from release text) | 1 | bls.gov/feed/cpi.rss (Atom) | ✅ 12 |
| BLS Employment Situation (payrolls parsed) | 1 | bls.gov/feed/empsit.rss | ✅ 12 |
| BEA releases (GDP, PCE, trade) | 1 | apps.bea.gov/rss/rss.xml | ✅ 48 |
| SEC press releases | 1 | sec.gov/news/pressreleases.rss | ✅ 25 |
| CFTC press releases | 1 | cftc.gov/RSS/RSSGP/rssgp.xml | ✅ 10 |
| Coinbase status: incidents / scheduled maintenance | 1 (about itself) | status.coinbase.com/api/v2/… | ✅ 50 / 0 |
| Kraken status: incidents / scheduled maintenance | 1 (about itself) | status.kraken.com/api/v2/… | ✅ 50 / 5 |
| CoinDesk | 3 | coindesk.com/arc/outboundfeeds/rss/ | ✅ 25 |
| GDELT DOC 2.0 (geopolitics) | 2 or 3 by outlet domain | api.gdeltproject.org | ❌ **disabled**: only throttling notices / HTTP 429 from this container. Verify on the always-on host |
| Reddit r/CryptoCurrency | 4 | RSS | off by default; never used for flags |
| FRED / ALFRED (point-in-time vintages) | 1 | api.stlouisfed.org | client implemented; **needs `FRED_API_KEY`** |

Exchange incidents only count for flags when they touch the trading path (API, websocket, FIX, order
entry, website/app) or BTC/ETH/USD funding, or are rated major/critical. Another token's funding delay
does not count.

BLS blocks generic user agents (HTTP 403). The pipeline sends a descriptive one.

## Macro calendar (`calendar.py`, `data/events/macro_calendar.csv`)

Built only from official pages; every row cites the page its date **and** time came from.

| Kind | Coverage | Time source |
|---|---|---|
| FOMC scheduled decisions | 2018–2027 (8 a year; 7 in 2020, March 17-18 cancelled) | "For release at 2:00 p.m. E[S/D]T" on each statement page. The 10 future meetings use the official date with 2:00 p.m. ET **assumed** (marked in the row) |
| FOMC unscheduled / notation votes | 2019 (1), 2020 (2 + 4 notation votes), 2025 (1 notation vote) | statement pages; `known_in_advance = False`, so never used as pre-scheduled flags |
| CPI releases | 2018–2026 from the BLS archive; future releases through Dec 2027 from the BLS schedule | embargo line on each release page ("embargoed until 8:30 a.m. (ET)") |
| Employment Situation | same | same |

Gaps and caveats, from the official listings:
- The BLS archive has **no October 2025** CPI or Employment Situation release. Five releases around it
  (Sep/Nov 2025 CPI; Sep/Nov 2025 and Jan 2026 payrolls) fall on unusual dates and are marked `irregular`.
- Rows use the *actual* release date. If a release was rescheduled after its date was announced, treating it
  as known in advance leaks slightly. Review `irregular` rows before using them in a backtest.

Rebuild: `.venv/bin/python scripts/events_build_calendar.py` (pages are cached in `data/events/cache/`).

## Flags for the risk engine (`flags.py`)

```python
from tradelab.events.flags import active_flags, FlagConfig, EventFlag
from tradelab.events.store import EventStore

flags: list[EventFlag] = active_flags(now, EventStore(), calendar_rows=None, cfg=FlagConfig(venue="coinbase"))
```

`EventFlag(kind, severity, assets, starts_at, ends_at, reason, source_ids, source_urls)`:

| kind | When | severity |
|---|---|---|
| `macro_window` | FOMC decision / CPI / payrolls release within −2h…+2h of `now` (configurable) | caution |
| `venue_incident` | open incident on our venue's status page (seen by `now`, status as of `now`, < 3 days old) | critical if impact major/critical, else caution |
| `venue_maintenance` | scheduled maintenance from 1h before start until end | as above |
| `regulatory_action` | official (tier 1) regulatory/enforcement item touching crypto or traded assets in the last 24h; non-official needs ≥2 corroborations | caution (official) / info |

All flags use only events whose `first_seen_at ≤ now`. What a flag *does* (block new entries, widen
spread limits, nothing) is the risk engine's decision, not this module's.

## Optional LLM classifier (`llm.py`), off by default

Enable with `TRADELAB_LLM_CLASSIFIER=1` plus Anthropic credentials. It is applied only to non-official
items; official sources are labelled by deterministic rules. Defences:
- The article is passed as data inside `<untrusted_article>` tags. Close tags inside the article are
  neutralised, and the system prompt says embedded instructions are content, never commands.
- Structured output with a strict JSON schema; no tools; allowlisted category, assets and mechanism.
- Every claim must quote evidence that appears **verbatim** in the article; any number in a claim must
  appear in its quote. Fields or phrases about price targets, probabilities, confidence or buy/sell advice
  cause **rejection** (not silent removal).
- Refusal, API error, invalid JSON or any validation failure → the deterministic keyword labels are used,
  and the rejection reasons are kept.
- An article over 12,000 characters is classified on its first 12,000 and marked `truncated`.

The LLM never assigns confidence or probabilities. Any calibrated probability must come from measured
outcomes.

### Cost (Anthropic list prices, Oct 2026: Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per M input/output tokens)

Estimate: ~150 non-official items/day once GDELT is enabled (~25–50/day from CoinDesk alone);
~800 input and ~400 output tokens per item (short feed excerpts; output includes low-effort thinking).

| Model | per item | per month (150/day) |
|---|---|---|
| `claude-opus-5-5` | ~$0.011 | ~$50 |
| `claude-sonnet-5-5` | ~$0.006 | ~$25 |
| `claude-haiku-5-5` (code default) | ~$0.0003 | ~$1.30 |

These are estimates; measure actual `usage` before relying on them. For a ~$1,000 account even $25/month
is 30% of capital a year, so the classifier stays off until prospective evaluation shows that the labels
it adds (over the free keyword classifier) change risk decisions for the better. The model is a
constructor argument. Choosing a cheaper one is an owner decision.

## Missing (needed for full functionality)

- **Licensed consensus / expectations data** (e.g. a vendor's economic-calendar feed): without it,
  `expected` and `surprise` stay null.
- **`FRED_API_KEY`** (free) for ALFRED point-in-time vintages.
- **Anthropic API credentials** only if the LLM classifier is enabled.
- **GDELT access** from the always-on host (rate-limited here).

## Running

```bash
.venv/bin/python scripts/events_ingest.py                 # one pass + active flags
.venv/bin/python scripts/events_ingest.py --fill-outcomes # also fill +1h/+4h/+24h BTC/ETH returns
.venv/bin/python -m pytest -q tests/test_events_*.py
```

Suggested cadence on the always-on host: every 5 minutes for status pages, every 15 minutes for the rest.
Fill outcomes hourly.
