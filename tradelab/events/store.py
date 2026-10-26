"""SQLite event store with novelty handling and prospective outcome logging."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import dedupe
from .schema import Category, Event, Novelty, Tier, derive_uncertainty, validate

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "events" / "events.sqlite"
MATCH_WINDOW = timedelta(days=30)   # how far back to look for duplicates

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, source_url TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT, published_at TEXT NOT NULL, published_at_basis TEXT, first_seen_at TEXT NOT NULL,
  last_seen_at TEXT, category TEXT NOT NULL, tier INTEGER NOT NULL, assets TEXT, mechanism TEXT,
  external_id TEXT, status TEXT, novelty TEXT NOT NULL, canonical_id TEXT, corroboration INTEGER,
  uncertainty TEXT, classifier TEXT, evidence TEXT, indicator TEXT, actual REAL, expected REAL,
  expected_reason TEXT, surprise REAL, revisions INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ev_seen ON events(first_seen_at);
CREATE INDEX IF NOT EXISTS ev_cat ON events(category, first_seen_at);
CREATE TABLE IF NOT EXISTS event_versions (
  event_id TEXT, seen_at TEXT, novelty TEXT, status TEXT, title TEXT, body TEXT, actual REAL
);
CREATE INDEX IF NOT EXISTS ver_id ON event_versions(event_id, seen_at);
CREATE TABLE IF NOT EXISTS outcomes (
  event_id TEXT, asset TEXT, horizon_h INTEGER, anchor_at TEXT, ret REAL, filled_at TEXT,
  PRIMARY KEY (event_id, asset, horizon_h)
);
CREATE TABLE IF NOT EXISTS ingest_log (
  at TEXT, source TEXT, fetched INTEGER, new INTEGER, duplicate INTEGER, correction INTEGER,
  resurfaced INTEGER, rejected INTEGER, error TEXT
);
"""
COLS = ["id", "source", "source_url", "title", "body", "published_at", "published_at_basis", "first_seen_at",
        "last_seen_at", "category", "tier", "assets", "mechanism", "external_id", "status", "novelty",
        "canonical_id", "corroboration", "uncertainty", "classifier", "evidence", "indicator", "actual",
        "expected", "expected_reason", "surprise"]
HORIZONS_H = (1, 4, 24)


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(timezone.utc).isoformat() if t else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class EventStore:
    def __init__(self, path: str | Path = DEFAULT_DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---- write -----------------------------------------------------------
    def add(self, e: Event) -> Novelty:
        """Store a candidate. Duplicates are not stored as new rows: they bump the
        canonical story's corroboration (if from another source) and last_seen."""
        validate(e)
        e.last_seen_at = e.last_seen_at or e.first_seen_at
        same = self.get(e.id)
        window = [] if same else self.events(since=e.first_seen_at - MATCH_WINDOW, until=None)
        novelty, match = dedupe.classify(e, window, same_item=same)
        e.novelty = novelty
        if match is not None and novelty is Novelty.DUPLICATE and e.id != match.id and e.tier < match.tier:
            # A more reliable source (e.g. the regulator itself) confirms a story first seen elsewhere:
            # keep it as its own record, seen at its own time, linked to the original.
            self.db.execute("UPDATE events SET corroboration=corroboration+1 WHERE id=?", (match.id,))
            e.novelty, e.canonical_id = Novelty.NEW, match.canonical_id or match.id
            e.corroboration = match.corroboration + 1
            e.uncertainty = derive_uncertainty(e.tier, e.corroboration)
            self._insert(e)
            return e.novelty
        if match is not None and novelty is Novelty.DUPLICATE:
            other_source = dedupe.domain(match.source_url) != dedupe.domain(e.source_url)
            self.db.execute("UPDATE events SET last_seen_at=?, corroboration=corroboration+? WHERE id=?",
                            (_iso(e.first_seen_at), int(other_source), match.id))
            row = self.get(match.id)
            self.db.execute("UPDATE events SET uncertainty=? WHERE id=?",
                            (derive_uncertainty(row.tier, row.corroboration), match.id))
            self.db.commit()
            return novelty
        if match is not None and novelty is Novelty.CORRECTION:
            # keep the original first_seen_at (when the story became known) and its novelty
            # history; the content becomes the revision. Revision time is last_seen_at.
            e.first_seen_at = match.first_seen_at
            e.canonical_id = match.canonical_id or (match.id if match.id != e.id else None)
            e.corroboration = match.corroboration
            prior = self.db.execute("SELECT revisions FROM events WHERE id=?", (match.id,)).fetchone()[0] or 0
            self.db.execute("DELETE FROM events WHERE id=?", (match.id,))
            e.uncertainty = derive_uncertainty(e.tier, e.corroboration)
            self._insert(e, revisions=prior + 1)
            return novelty
        if match is not None:   # resurfaced copy of an older story
            e.canonical_id = match.canonical_id or match.id
        e.uncertainty = derive_uncertainty(e.tier, e.corroboration)
        self._insert(e)
        return novelty

    def _insert(self, e: Event, revisions: int = 0):
        # every accepted version is kept, so status can be read as of any past time
        self.db.execute("INSERT INTO event_versions VALUES (?,?,?,?,?,?,?)",
                        (e.id, _iso(e.last_seen_at or e.first_seen_at), e.novelty.value, e.status, e.title,
                         e.body, e.actual))
        d = asdict(e)
        d.update(id=e.id, category=e.category.value, tier=int(e.tier), novelty=e.novelty.value,
                 assets=json.dumps(e.assets), evidence=json.dumps(e.evidence),
                 published_at=_iso(e.published_at), first_seen_at=_iso(e.first_seen_at),
                 last_seen_at=_iso(e.last_seen_at))
        self.db.execute(f"INSERT OR REPLACE INTO events ({','.join(COLS)}, revisions) VALUES "
                        f"({','.join('?' * len(COLS))}, ?)", [d[c] for c in COLS] + [revisions])
        self.db.commit()

    def log_ingest(self, source: str, counts: dict, error: str | None = None):
        self.db.execute("INSERT INTO ingest_log VALUES (?,?,?,?,?,?,?,?,?)",
                        (_iso(datetime.now(timezone.utc)), source, counts.get("fetched", 0), counts.get("new", 0),
                         counts.get("duplicate", 0), counts.get("correction", 0), counts.get("resurfaced", 0),
                         counts.get("rejected", 0), error))
        self.db.commit()

    # ---- read ------------------------------------------------------------
    def _row(self, r) -> Event:
        return Event(
            source=r["source"], source_url=r["source_url"], title=r["title"], body=r["body"] or "",
            published_at=_dt(r["published_at"]), first_seen_at=_dt(r["first_seen_at"]),
            last_seen_at=_dt(r["last_seen_at"]), category=Category(r["category"]), tier=Tier(r["tier"]),
            assets=json.loads(r["assets"] or "[]"), mechanism=r["mechanism"],
            published_at_basis=r["published_at_basis"], external_id=r["external_id"], status=r["status"],
            novelty=Novelty(r["novelty"]), canonical_id=r["canonical_id"], corroboration=r["corroboration"] or 0,
            uncertainty=r["uncertainty"], classifier=r["classifier"], evidence=json.loads(r["evidence"] or "[]"),
            indicator=r["indicator"], actual=r["actual"], expected=r["expected"],
            expected_reason=r["expected_reason"], surprise=r["surprise"],
        )

    def status_as_of(self, event_id: str, t: datetime) -> str | None:
        """Point-in-time status: the latest version we had seen at time t."""
        r = self.db.execute("SELECT status FROM event_versions WHERE event_id=? AND seen_at<=? "
                            "ORDER BY seen_at DESC LIMIT 1", (event_id, _iso(t))).fetchone()
        return r[0] if r else None

    def revisions(self, event_id: str) -> int:
        r = self.db.execute("SELECT revisions FROM events WHERE id=?", (event_id,)).fetchone()
        return r[0] if r else 0

    def get(self, event_id: str) -> Event | None:
        r = self.db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._row(r) if r else None

    def events(self, since: datetime | None = None, until: datetime | None = None,
               category: Category | None = None) -> list[Event]:
        """Point-in-time query on first_seen_at: `until` excludes anything we had not seen yet."""
        q, a = "SELECT * FROM events WHERE 1=1", []
        if since:
            q += " AND first_seen_at >= ?"; a.append(_iso(since))
        if until:
            q += " AND first_seen_at <= ?"; a.append(_iso(until))
        if category:
            q += " AND category = ?"; a.append(category.value)
        return [self._row(r) for r in self.db.execute(q + " ORDER BY first_seen_at", a)]

    # ---- prospective evaluation ------------------------------------------
    def pending_outcomes(self, now: datetime, assets=("BTC", "ETH")) -> list[tuple[str, str, int, datetime]]:
        """(event_id, asset, horizon_h, anchor) whose horizon has elapsed but is not filled."""
        out = []
        for e in self.events(until=now):
            if e.novelty is Novelty.DUPLICATE:
                continue
            for a in assets:
                for h in HORIZONS_H:
                    if e.first_seen_at + timedelta(hours=h) <= now and not self.db.execute(
                            "SELECT 1 FROM outcomes WHERE event_id=? AND asset=? AND horizon_h=?", (e.id, a, h)).fetchone():
                        out.append((e.id, a, h, e.first_seen_at))
        return out

    def record_outcome(self, event_id: str, asset: str, horizon_h: int, anchor: datetime, ret: float | None):
        self.db.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?,?,?)",
                        (event_id, asset, horizon_h, _iso(anchor), ret, _iso(datetime.now(timezone.utc))))
        self.db.commit()

    def outcomes(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT o.*, e.category, e.tier, e.source FROM outcomes o JOIN events e "
                               "ON e.id=o.event_id").fetchall()
