"""Heartbeats and missed-run detection for the scheduled paper workflows.

Each workflow writes data/heartbeat/<workflow>.json after a successful run; the file travels with the rest of the
paper state on the `paper-state` branch. The watchdog workflow reads those files and lists every workflow whose
last success is older than its limit in config/alerts.toml.

    python -m tradelab.ops.watchdog beat paper-daily --run-url URL
    python -m tradelab.ops.watchdog check --heartbeats DIR      # prints one JSON line per workflow
"""
from __future__ import annotations

import argparse
import json
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEARTBEATS = ROOT / "data" / "heartbeat"
CONFIG = ROOT / "config" / "alerts.toml"


def beat(name: str, run_url: str = "", now: datetime | None = None, root: Path = HEARTBEATS) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / f"{name}.json"
    p.write_text(json.dumps({"workflow": name, "last_success": (now or datetime.now(timezone.utc)).isoformat(),
                             "run_url": run_url}) + "\n")
    return p


def _market_open(now: datetime) -> bool:
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS", start="1999-01-01")
    return bool(cal.is_open_on_minute(now.replace(second=0, microsecond=0), ignore_breaks=True))


def check(heartbeats: Path, now: datetime, cfg: dict, market_open=_market_open) -> list[dict]:
    out = []
    for name, rule in cfg["missed_run"].items():
        p = heartbeats / f"{name}.json"
        last = datetime.fromisoformat(json.loads(p.read_text())["last_success"]) if p.exists() else None
        limit = timedelta(hours=rule["max_age_hours"])
        judged = not rule.get("market_hours_only") or market_open(now)
        if not judged:
            status, reason = "ok", "market closed: not judged"
        elif last is None:
            status, reason = "missed", "no successful run recorded"
        elif now - last > limit:
            status, reason = "missed", f"last success {last.isoformat()} is older than {rule['max_age_hours']} h"
        else:
            status, reason = "ok", f"last success {last.isoformat()}"
        out.append({"workflow": name, "status": status, "reason": reason})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("beat"); b.add_argument("name"); b.add_argument("--run-url", default="")
    c = sub.add_parser("check"); c.add_argument("--heartbeats", type=Path, default=HEARTBEATS)
    a = ap.parse_args(argv)
    if a.cmd == "beat":
        print(beat(a.name, a.run_url))
        return
    cfg = tomllib.loads(CONFIG.read_text())
    for row in check(a.heartbeats, datetime.now(timezone.utc), cfg):
        print(json.dumps(row))


if __name__ == "__main__":
    main()
