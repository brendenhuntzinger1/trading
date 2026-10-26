"""Duplicate, correction and resurfacing detection."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .schema import Event, Novelty

TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|cmpid$|ocid$)")
CORRECTION_MARKERS = re.compile(r"\b(correct(ed|ion)|update[ds]?|revis(ed|ion)|clarif(ied|ication)|amended)\b", re.I)
STOP = frozenset("a an the of to in on for and or is are was were be by with at from as its it this that".split())

NEAR_DUP = 0.6                    # Jaccard on title word-shingles
RESURFACE_AFTER = timedelta(days=7)


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k.lower())]
    path = p.path.rstrip("/") or "/"
    return urlunsplit(("https", p.netloc.lower().removeprefix("www."), path, urlencode(sorted(q)), ""))


def normalize_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = CORRECTION_MARKERS.sub(" ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(w for w in t.split() if w not in STOP)


def title_hash(t: str) -> str:
    return hashlib.sha256(normalize_title(t).encode()).hexdigest()[:16]


def shingles(t: str, n: int = 2) -> set[str]:
    """Word bigrams with numbers masked: a corrected figure is still the same story."""
    w = ["<n>" if re.fullmatch(r"\d+", x) else x for x in normalize_title(t).split()]
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))} if w else set()


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def same_outlet(a: Event, b: Event) -> bool:
    """Same feed AND same publisher domain (aggregators like GDELT carry many outlets)."""
    return a.source == b.source and domain(a.source_url) == domain(b.source_url)


def changed(a: Event, b: Event) -> bool:
    return (a.title.strip() != b.title.strip() or a.status != b.status or a.actual != b.actual
            or a.body.strip()[:500] != b.body.strip()[:500])


def classify(candidate: Event, existing: list[Event], same_item: Event | None = None) -> tuple[Novelty, Event | None]:
    """Decide how `candidate` relates to stored events. Returns (novelty, matched).
    `same_item` is the stored record with the same identity (source + URL/external id),
    looked up across the whole store: a re-fetched item is never 'new' or 'resurfaced'."""
    if same_item is not None:
        return (Novelty.CORRECTION if changed(candidate, same_item) else Novelty.DUPLICATE), same_item
    cu = canonical_url(candidate.source_url)
    cs = shingles(candidate.title)
    best, best_sim = None, 0.0
    exact = title_hash(candidate.title)
    for e in existing:
        if canonical_url(e.source_url) == cu:
            best, best_sim = e, 1.0
            break
        if same_outlet(e, candidate) and not CORRECTION_MARKERS.search(candidate.title):
            # Same source, different item: recurring templated titles ("CPI for all items increases
            # 0.2% in <month>", "Funding Delays") are distinct events. Only an identical title from an
            # item without its own id counts as a republication.
            if candidate.external_id or e.external_id or title_hash(e.title) != exact:
                continue
            best, best_sim = e, 1.0
            break
        sim = jaccard(cs, shingles(e.title))
        if sim > best_sim:
            best, best_sim = e, sim
    stale = candidate.first_seen_at - candidate.published_at > RESURFACE_AFTER
    if best is None or best_sim < NEAR_DUP:
        return (Novelty.RESURFACED if stale else Novelty.NEW), None
    if best.first_seen_at < candidate.first_seen_at - RESURFACE_AFTER:
        return Novelty.RESURFACED, best
    if same_outlet(best, candidate) and (
            changed(candidate, best) and CORRECTION_MARKERS.search(candidate.title + " " + candidate.body[:300])):
        return Novelty.CORRECTION, best
    return Novelty.DUPLICATE, best
