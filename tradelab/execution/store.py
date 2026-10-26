"""SQLite journal: decisions, orders, fills, equity marks and breaker events.
Written before every external action so a crash can always be recovered."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Fill, Order, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT, at TEXT, mode TEXT, account TEXT, strategy TEXT, strategy_version TEXT,
  asset TEXT, data_as_of TEXT, target_weight REAL, current_weight REAL, intent_notional REAL,
  outcome TEXT, final_notional REAL, reasons TEXT, breakers TEXT, config_hash TEXT, sources TEXT,
  PRIMARY KEY (id, at));
CREATE TABLE IF NOT EXISTS breaker_latch (
  account TEXT, mode TEXT, breaker TEXT, latched_at TEXT, detail TEXT,
  reset_at TEXT, reset_by TEXT, reset_note TEXT);
CREATE TABLE IF NOT EXISTS orders (
  client_id TEXT PRIMARY KEY, account TEXT, mode TEXT, data TEXT, status TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT, client_id TEXT, account TEXT, mode TEXT, asset TEXT, side TEXT,
  base REAL, price REAL, fee REAL, at TEXT, PRIMARY KEY (mode, account, fill_id));
CREATE TABLE IF NOT EXISTS equity (
  at TEXT, mode TEXT, account TEXT, equity REAL, cash REAL, positions TEXT, marks TEXT,
  operating_cost REAL DEFAULT 0, PRIMARY KEY (at, mode, account));
CREATE TABLE IF NOT EXISTS breaker_log (at TEXT, mode TEXT, account TEXT, breaker TEXT, detail TEXT, actions TEXT);
CREATE TABLE IF NOT EXISTS latency (client_id TEXT PRIMARY KEY, decided_to_submit_ms REAL, submit_to_ack_ms REAL,
  ack_to_first_fill_ms REAL, slippage_bps REAL);
"""


def _iso(x):
    return x.isoformat() if isinstance(x, datetime) else x


class Store:
    def __init__(self, path: str | Path, mode: str):
        if mode not in ("paper", "live", "backtest"):
            raise ValueError(mode)
        self.mode = mode
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        self.db.executescript(SCHEMA)

    def _migrate(self):
        """Journals created before 2026-10-25 keyed decisions by id alone, so a re-run
        overwrote the first decision. Re-key them by (id, at), keeping every row."""
        pk = [r[1] for r in self.db.execute("PRAGMA table_info(decisions)") if r[5]]
        if pk == ["id"]:
            self.db.executescript("ALTER TABLE decisions RENAME TO decisions_v1;")
            self.db.executescript(SCHEMA)
            self.db.executescript("INSERT INTO decisions SELECT * FROM decisions_v1; DROP TABLE decisions_v1;")

    # decisions -----------------------------------------------------------
    def decision(self, **row) -> None:
        row = {k: (json.dumps(v) if isinstance(v, (list, dict)) else _iso(v)) for k, v in row.items()}
        row["mode"] = self.mode
        cols = ",".join(row)                     # insert-only: re-runs add rows, never overwrite history
        self.db.execute(f"INSERT OR IGNORE INTO decisions ({cols}) VALUES ({','.join('?' * len(row))})", list(row.values()))

    def approved_today(self, account: str, day: str) -> int:
        return self.db.execute("SELECT COUNT(DISTINCT id) FROM decisions WHERE mode=? AND account=? AND outcome='approved' "
                               "AND substr(at,1,10)=?", (self.mode, account, day)).fetchone()[0]

    # breaker latches ---------------------------------------------------
    def active_latches(self, account: str) -> dict[str, str]:
        return {b: d for b, d in self.db.execute(
            "SELECT breaker, detail FROM breaker_latch WHERE mode=? AND account=? AND reset_at IS NULL", (self.mode, account))}

    def latch(self, account: str, breaker: str, detail: str, at) -> None:
        if breaker not in self.active_latches(account):
            self.db.execute("INSERT INTO breaker_latch VALUES (?,?,?,?,?,NULL,NULL,NULL)", (account, self.mode, breaker, _iso(at), detail))

    def reset_latch(self, account: str, breaker: str, operator: str, note: str, at) -> int:
        if not operator or not note:
            raise ValueError("reset requires an operator name and a note")
        return self.db.execute("UPDATE breaker_latch SET reset_at=?, reset_by=?, reset_note=? WHERE mode=? AND account=? "
                               "AND breaker=? AND reset_at IS NULL", (_iso(at), operator, note, self.mode, account, breaker)).rowcount

    def recent_rejections(self, account: str, since) -> list:
        out = []
        for (data,) in self.db.execute("SELECT data FROM orders WHERE mode=? AND account=? AND status='rejected'", (self.mode, account)):
            o = _load_order(data)
            t = o.submitted_at or o.updated_at
            if t and t >= since and o.reject_reason != "below venue minimum after rounding":
                out.append(t)
        return out

    # orders --------------------------------------------------------------
    def put_order(self, o: Order) -> None:
        o.updated_at = datetime.now(timezone.utc)
        data = json.dumps({k: _iso(v.value if isinstance(v, Status) else v) for k, v in asdict(o).items()})
        self.db.execute("INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?)",
                        (o.client_id, o.account, self.mode, data, o.status.value, _iso(o.updated_at)))

    def get_order(self, client_id: str) -> Order | None:
        r = self.db.execute("SELECT data FROM orders WHERE client_id=?", (client_id,)).fetchone()
        return _load_order(r[0]) if r else None

    def open_orders(self, account: str | None = None) -> list[Order]:
        q = "SELECT data FROM orders WHERE mode=? AND status NOT IN ('filled','cancelled','rejected','not_found')"
        args = [self.mode]
        if account:
            q += " AND account=?"
            args.append(account)
        return [_load_order(r[0]) for r in self.db.execute(q, args)]

    def orders_for_account_day(self, account: str, day: str) -> list[Order]:
        """Orders whose decision belongs to UTC day `day` (decision ids end with the date)."""
        return [_load_order(r[0]) for r in self.db.execute(
            "SELECT data FROM orders WHERE mode=? AND account=? AND json_extract(data,'$.decision_id') LIKE ?",
            (self.mode, account, f"%:{day}"))]

    # fills ---------------------------------------------------------------
    def add_fill(self, account: str, f: Fill) -> bool:
        cur = self.db.execute("INSERT OR IGNORE INTO fills VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (f.fill_id, f.client_id, account, self.mode, f.asset, f.side, f.base, f.price, f.fee, _iso(f.at)))
        return cur.rowcount == 1          # False = duplicate, already recorded

    def positions(self, account: str, initial_cash: float) -> tuple[float, dict[str, float]]:
        cash, pos = initial_cash, {}
        for asset, side, base, price, fee in self.db.execute(
                "SELECT asset, side, base, price, fee FROM fills WHERE mode=? AND account=? ORDER BY at", (self.mode, account)):
            sgn = 1 if side == "buy" else -1
            pos[asset] = pos.get(asset, 0.0) + sgn * base
            cash -= sgn * base * price + fee
        return cash, {a: q for a, q in pos.items() if abs(q) > 1e-12}

    # marks, breakers, latency -------------------------------------------
    def mark(self, at, account, equity, cash, positions, marks, operating_cost=0.0):
        self.db.execute("INSERT OR REPLACE INTO equity VALUES (?,?,?,?,?,?,?,?)",
                        (_iso(at), self.mode, account, equity, cash, json.dumps(positions), json.dumps(marks), operating_cost))

    def breaker(self, at, account, breaker, detail, actions):
        self.db.execute("INSERT INTO breaker_log VALUES (?,?,?,?,?,?)",
                        (_iso(at), self.mode, account, breaker, detail, json.dumps(sorted(actions))))

    def latency(self, client_id, **ms):
        cols = ["client_id"] + list(ms)
        self.db.execute(f"INSERT OR REPLACE INTO latency ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [client_id] + list(ms.values()))


def _load_order(data: str) -> Order:
    d = json.loads(data)
    d["status"] = Status(d["status"])
    for k in ("decided_at", "submitted_at", "acked_at", "first_fill_at", "updated_at"):
        if d.get(k):
            d[k] = datetime.fromisoformat(d[k])
    return Order(**d)
