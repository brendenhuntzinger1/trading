"""Persist engine state and journal trades/decisions, so a restart resumes exactly."""
from __future__ import annotations

import json
import sqlite3
from collections import deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .engine import Engine, EngineState
from .model import Order, Position, Signal


def _enc(o):
    if isinstance(o, datetime):
        return {"__dt__": o.isoformat()}
    raise TypeError(type(o))


def _dec(d):
    return datetime.fromisoformat(d["__dt__"]) if "__dt__" in d else d


def _sig(d) -> Signal:
    return Signal(**d)


def save(engine: Engine, path: Path, last_bar: datetime | None) -> None:
    s = engine.s
    blob = {"cash": s.cash, "marks": s.marks, "day": s.day, "day_start_equity": s.day_start_equity,
            "entries_today": s.entries_today, "halted_today": s.halted_today, "day_trades": list(s.day_trades),
            "positions": {k: {**asdict(p), "signal": asdict(p.signal)} for k, p in s.positions.items()},
            "pending": [{**asdict(o), "signal": asdict(o.signal)} for o in s.pending],
            "initial": engine.initial, "last_bar": last_bar}
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, default=_enc))
    tmp.replace(path)                                   # atomic


def load(engine: Engine, path: Path) -> datetime | None:
    p = Path(path)
    if not p.exists():
        return None
    b = json.loads(p.read_text(), object_hook=_dec)
    engine.initial = b["initial"]
    engine.s = EngineState(cash=b["cash"], marks=b["marks"], day=b["day"], day_start_equity=b["day_start_equity"],
                           entries_today=b["entries_today"], halted_today=b["halted_today"],
                           day_trades=deque(b["day_trades"], maxlen=64))
    engine.s.positions = {k: Position(**{**v, "signal": _sig(v["signal"])}) for k, v in b["positions"].items()}
    engine.s.pending = [Order(**{**o, "signal": _sig(o["signal"])}) for o in b["pending"]]
    return b["last_bar"]


SCHEMA = """
CREATE TABLE IF NOT EXISTS intraday_trades (mode TEXT, account TEXT, setup TEXT, symbol TEXT, side TEXT,
  entry_time TEXT, entry_px REAL, exit_time TEXT, exit_px REAL, exit_reason TEXT, qty REAL, gross_pnl REAL, cost REAL,
  PRIMARY KEY (mode, account, symbol, entry_time));
CREATE TABLE IF NOT EXISTS intraday_decisions (mode TEXT, account TEXT, at TEXT, setup TEXT, symbol TEXT, outcome TEXT,
  reasons TEXT, notional REAL);
CREATE TABLE IF NOT EXISTS intraday_equity (mode TEXT, account TEXT, at TEXT, equity REAL, positions INTEGER,
  PRIMARY KEY (mode, account, at));
"""


class Journal:
    def __init__(self, path: Path, mode: str, account: str):
        if mode not in ("paper", "replay"):
            raise ValueError("intraday journal supports paper and replay only")
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.mode, self.account = mode, account
        self._n_trades = self._n_dec = 0

    def sync(self, engine: Engine) -> None:
        """Append what the engine produced since the last sync (idempotent on trades)."""
        for t in engine.trades[self._n_trades:]:
            self.db.execute("INSERT OR IGNORE INTO intraday_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (self.mode, self.account, t.setup, t.symbol, t.side, t.entry_time.isoformat(), t.entry_px,
                             t.exit_time.isoformat(), t.exit_px, t.exit_reason, t.qty, t.gross_pnl, t.cost))
        for d in engine.decisions[self._n_dec:]:
            self.db.execute("INSERT INTO intraday_decisions VALUES (?,?,?,?,?,?,?,?)",
                            (self.mode, self.account, d.at.isoformat(), d.setup, d.symbol, d.outcome, json.dumps(d.reasons), d.notional))
        for at, eq in engine.equity_curve[-1:]:
            self.db.execute("INSERT OR REPLACE INTO intraday_equity VALUES (?,?,?,?,?)",
                            (self.mode, self.account, at.isoformat(), eq, len(engine.s.positions)))
        self._n_trades, self._n_dec = len(engine.trades), len(engine.decisions)
