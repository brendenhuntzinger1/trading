"""Append-only JSONL recording of normalized live records.

Layout: data/live/<venue>/<YYYY-MM-DD of received_at>/<kind>.jsonl
Both event_time and received_at are stored for every record, so any replay can
be cut at "what had we actually received by time T".
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .types import BookSample, DepthSummary, FeedHealth, TopOfBook, Trade, VenueNotice

LIVE_DIR = Path(__file__).resolve().parents[3] / "data" / "live"
KINDS = {Trade: "trade", TopOfBook: "top", DepthSummary: "depth", VenueNotice: "notice", BookSample: "book", FeedHealth: "health"}


def _enc(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))


class Recorder:
    def __init__(self, root: Path = LIVE_DIR):
        self.root = Path(root)
        self._files: dict[Path, object] = {}

    def write(self, rec) -> None:
        kind = KINDS[type(rec)]
        stamp = rec.received_at if hasattr(rec, "received_at") else rec.last_message_at
        day = stamp.date().isoformat() if stamp else "undated"
        path = self.root / rec.venue / day / f"{kind}.jsonl"
        fh = self._files.get(path)
        if fh is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = self._files[path] = path.open("a")
        fh.write(json.dumps(dataclasses.asdict(rec), default=_enc) + "\n")

    def flush(self) -> None:
        for fh in self._files.values():
            fh.flush()

    def close(self) -> None:
        for fh in self._files.values():
            fh.close()
        self._files.clear()


def read_trades(venue: str, symbol: str | None = None, root: Path = LIVE_DIR) -> Iterator[Trade]:
    for path in sorted((Path(root) / venue).glob("*/trade.jsonl")):
        for line in path.open():
            d = json.loads(line)
            if symbol and d["symbol"] != symbol:
                continue
            d["event_time"] = datetime.fromisoformat(d["event_time"])
            d["received_at"] = datetime.fromisoformat(d["received_at"])
            yield Trade(**d)
