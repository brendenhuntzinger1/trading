"""One ingestion pass over all enabled sources."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .llm import LLMClassifier
from .schema import SchemaError, Tier
from .sources import SOURCES, Source
from .store import EventStore


def ingest_once(store: EventStore, sources: list[Source] = SOURCES, llm: LLMClassifier | None = None,
                now: datetime | None = None) -> dict[str, dict]:
    results = {}
    for src in sources:
        if not src.enabled:
            continue
        counts: Counter = Counter()
        try:
            events = src.pull(now or datetime.now(timezone.utc))
        except Exception as ex:   # one broken source must not stop the others
            store.log_ingest(src.name, {}, f"{type(ex).__name__}: {ex}"[:300])
            results[src.name] = {"error": f"{type(ex).__name__}: {ex}"[:200]}
            continue
        counts["fetched"] = len(events)
        for e in events:
            if llm is not None and llm.enabled and e.tier is not Tier.OFFICIAL and store.get(e.id) is None:
                r = llm.classify(e.title, e.body)   # falls back to keyword labels on any rejection
                e.category, e.assets, e.mechanism, e.evidence, e.classifier = (
                    r.category, r.assets, r.mechanism, r.evidence, r.classifier)
            try:
                counts[store.add(e).value] += 1
            except SchemaError:
                counts["rejected"] += 1
        store.log_ingest(src.name, counts)
        results[src.name] = dict(counts)
    return results
