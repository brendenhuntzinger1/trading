"""Deterministic event flags for the risk engine. Flags describe conditions;
they never place, size or cancel trades. The risk engine decides what a flag
means (e.g. 'no new entries during a macro window')."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import calendar as cal
from .schema import Category, Novelty, Tier
from .sources import VENUE_SOURCES, incident_open
from .store import EventStore


@dataclass(frozen=True)
class FlagConfig:
    venue: str = "coinbase"
    traded_assets: frozenset = frozenset({"BTC", "ETH"})
    macro_kinds: frozenset = frozenset({"fomc_decision", "cpi_release", "nfp_release"})
    macro_before: timedelta = timedelta(hours=2)
    macro_after: timedelta = timedelta(hours=2)
    maintenance_lead: timedelta = timedelta(hours=1)
    incident_max_age: timedelta = timedelta(days=3)     # ignore stale incidents nobody closed
    regulatory_lookback: timedelta = timedelta(hours=24)
    min_corroboration_unofficial: int = 2


@dataclass(frozen=True)
class EventFlag:
    kind: str               # macro_window | venue_incident | venue_maintenance | regulatory_action
    severity: str           # info | caution | critical
    assets: tuple[str, ...]
    starts_at: datetime
    ends_at: datetime | None
    reason: str
    source_ids: tuple[str, ...] = field(default=())   # event ids or calendar rows (kind:reference)
    source_urls: tuple[str, ...] = field(default=())


def _macro(now: datetime, rows: list[cal.CalendarRow], cfg: FlagConfig) -> list[EventFlag]:
    out = []
    for r in cal.scheduled_between(rows, now - cfg.macro_after, now + cfg.macro_before):
        if r.kind not in cfg.macro_kinds:
            continue
        t = datetime.fromisoformat(r.release_utc)
        out.append(EventFlag("macro_window", "caution", ("USD", "crypto_market"), t - cfg.macro_before,
                             t + cfg.macro_after, f"{r.kind} {r.reference} at {r.release_utc}"
                             + (" (time assumed)" if "assumed" in r.release_local else ""),
                             (f"{r.kind}:{r.reference}",), (r.source_url or r.index_url,)))
    return out


def _venue(now: datetime, store: EventStore, cfg: FlagConfig) -> list[EventFlag]:
    out = []
    names = VENUE_SOURCES.get(cfg.venue, ())
    for e in store.events(since=now - timedelta(days=60), until=now, category=Category.EXCHANGE_INCIDENT):
        if e.source not in names or e.mechanism != "venue_operational":
            continue
        status = store.status_as_of(e.id, now) or e.status or ""
        state, impact, start, end = (status.split("|") + ["", "", "", ""])[:4]
        sev = "critical" if impact in ("major", "critical") else "caution"
        if state == "scheduled" or (state == "in_progress" and start):
            s, en = datetime.fromisoformat(start), datetime.fromisoformat(end) if end else None
            if s - cfg.maintenance_lead <= now and (en is None or now <= en):
                out.append(EventFlag("venue_maintenance", sev, ("crypto_market",), s - cfg.maintenance_lead, en,
                                     f"{cfg.venue} maintenance: {e.title}", (e.id,), (e.source_url,)))
        elif incident_open(status) and now - e.published_at <= cfg.incident_max_age:
            out.append(EventFlag("venue_incident", sev, ("crypto_market",), e.published_at, None,
                                 f"{cfg.venue} incident ({state}, impact {impact}): {e.title}", (e.id,), (e.source_url,)))
    return out


def _regulatory(now: datetime, store: EventStore, cfg: FlagConfig) -> list[EventFlag]:
    out = []
    for e in store.events(since=now - cfg.regulatory_lookback, until=now, category=Category.REGULATORY):
        hit = (set(e.assets) & cfg.traded_assets) or ("crypto_market" in e.assets)
        if not hit or e.novelty in (Novelty.DUPLICATE, Novelty.RESURFACED):
            continue
        if e.mechanism not in ("regulatory_access", "enforcement_flows"):
            continue
        if e.tier is not Tier.OFFICIAL and e.corroboration < cfg.min_corroboration_unofficial:
            continue
        out.append(EventFlag("regulatory_action", "info" if e.tier is not Tier.OFFICIAL else "caution",
                             tuple(sorted(e.assets)), e.first_seen_at, e.first_seen_at + cfg.regulatory_lookback,
                             f"{e.source} (tier {int(e.tier)}, corroboration {e.corroboration}): {e.title}",
                             (e.id,), (e.source_url,)))
    return out


def active_flags(now: datetime, store: EventStore, calendar_rows: list[cal.CalendarRow] | None = None,
                 cfg: FlagConfig = FlagConfig()) -> list[EventFlag]:
    """All flags active at `now`, using only information first seen at or before `now`."""
    rows = calendar_rows if calendar_rows is not None else (cal.load() if cal.CAL_PATH.exists() else [])
    return _macro(now, rows, cfg) + _venue(now, store, cfg) + _regulatory(now, store, cfg)
