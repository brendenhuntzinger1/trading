"""Inventory every local dataset: first and last timestamp, resolution, venue/source, row/file counts and freshness.

    python scripts/data_inventory.py            # writes research/phase2/data_inventory.json and prints a table

Reads only local files (no network). Timestamps come from the data itself (first/last row) or, for the Alpaca
caches, from the date stamped in each cached file name. Freshness = hours between the last timestamp and now.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "research" / "phase2" / "data_inventory.json"

# (glob, label, resolution, venue/source, adjusted?, used by)
CSV_SETS = [
    ("*-USD_1d.csv", "Crypto daily (BTC, ETH, SOL; holdout LTC, BCH, ETC)", "1 day", "Coinbase Exchange public candles", "unadjusted", "daily crypto strategies, holdout"),
    ("*-USD_1h.csv", "Crypto hourly (BTC, ETH, SOL)", "1 hour", "Coinbase Exchange public candles", "unadjusted", "C1/C2 context"),
    ("crypto_intraday/*_5m.csv", "Crypto 5-minute (BTC, ETH, SOL)", "5 min", "Coinbase Exchange public candles", "unadjusted", "C1, C2"),
    ("crypto_intraday/*_1h.csv", "Crypto hourly (intraday set)", "1 hour", "Coinbase Exchange public candles", "unadjusted", "C1, C2"),
    ("universe/*.csv", "Coinbase USD universe, daily (473 products incl. delisted)", "1 day", "Coinbase Exchange public candles", "unadjusted", "P1, holdout universe"),
    ("stocks/daily/*.csv", "US stocks daily (S&P 100 + 15 ETFs)", "1 day", "Yahoo chart API (unofficial)", "split-adjusted by Yahoo", "S2, S2-ETF"),
    ("stocks/hourly/*.csv", "US stocks hourly (S&P 100 + ETFs)", "1 hour", "Yahoo chart API (unofficial)", "split-adjusted by Yahoo", "S1, S2"),
    ("stocks/m5/*.csv", "US stocks 5-minute (last 60 sessions)", "5 min", "Yahoo chart API (unofficial)", "split-adjusted by Yahoo", "S3 exploratory"),
    ("s2x/*.csv", "29 ETFs daily (S2X replication)", "1 day", "Yahoo chart API (unofficial)", "split-adjusted by Yahoo", "S2X"),
    ("pit/hourly/*.csv", "Crypto hourly point-in-time panel (P1)", "1 hour", "Coinbase Exchange public candles", "unadjusted", "P1a/P1b"),
    ("paper/*.csv", "Paper runner daily candles", "1 day", "Coinbase Exchange public candles", "unadjusted", "paper-daily"),
]


def _first_last(path: Path) -> tuple[str | None, str | None, int]:
    with path.open() as fh:
        header = fh.readline()
        first = fh.readline()
        n = 1 if first.strip() else 0
        last = first
        for line in fh:
            if line.strip():
                last = line
                n += 1
    if not first.strip():
        return None, None, 0
    col = 0
    h = header.strip().split(",")
    for i, name in enumerate(h):
        if name.lower() in ("time", "time_utc", "date", "timestamp", ""):
            col = i
            break
    return first.split(",")[col].strip(), last.split(",")[col].strip(), n


def _parse(ts: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(ts.replace("+00:00", "+0000"), fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except ValueError:
        return None


def csv_sets(now: datetime) -> list[dict]:
    rows = []
    for pattern, label, res, venue, adj, used in CSV_SETS:
        files = [p for p in DATA.glob(pattern) if p.is_file()]
        if not files:
            continue
        firsts, lasts, n = [], [], 0
        for p in files:
            f, l, k = _first_last(p)
            if f:
                firsts.append(_parse(f)); lasts.append(_parse(l)); n += k
        firsts = [x for x in firsts if x]; lasts = [x for x in lasts if x]
        last = max(lasts) if lasts else None
        rows.append({"dataset": label, "path": f"data/{pattern}", "files": len(files), "rows": n, "resolution": res,
                     "venue": venue, "adjustment": adj, "first": min(firsts).isoformat() if firsts else None,
                     "last": last.isoformat() if last else None,
                     "last_min_across_files": min(lasts).isoformat() if lasts else None,
                     "freshness_hours": round((now - last).total_seconds() / 3600, 1) if last else None,
                     "used_by": used})
    return rows


def alpaca_caches(now: datetime) -> list[dict]:
    c = DATA / "stocks" / "cache"
    out = []
    spec = [("min1", r"^(\d{4}-\d{2}-\d{2})_", "1 minute bars, selected stocks-in-play only", "1 min"),
            ("or5", r"^(\d{4}-\d{2}-\d{2})\.json", "09:30-09:34 opening bars, whole universe (one file per session)", "1 min x 5"),
            ("quotes", r"_(\d{8})T\d{4}", "NBBO quotes around single minutes (entry/exit spreads)", "tick (NBBO)")]
    for sub, rx, label, res in spec:
        dates = []
        for p in (c / sub).iterdir() if (c / sub).exists() else []:
            m = re.search(rx, p.name)
            if m:
                s = m.group(1)
                dates.append(s if "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:]}")
        if dates:
            out.append({"dataset": f"Alpaca SIP: {label}", "path": f"data/stocks/cache/{sub}/", "files": len(dates),
                        "rows": None, "resolution": res, "venue": "Alpaca market data v2, feed=sip (consolidated)",
                        "adjustment": "raw (unadjusted)", "first": min(dates), "last": max(dates),
                        "freshness_hours": round((now - _parse(max(dates))).total_seconds() / 3600, 1),
                        "used_by": "ORB development, H3 development check, data gates"})
    ranges = {}
    for p in (c / "daily").iterdir() if (c / "daily").exists() else []:
        m = re.match(r"^(raw|split)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_", p.name)
        if m:
            ranges.setdefault((m.group(2), m.group(3)), 0)
            ranges[(m.group(2), m.group(3))] += 1
    for (a, b), k in sorted(ranges.items()):
        out.append({"dataset": f"Alpaca SIP daily bars, whole universe (batches of 100 symbols), {a} to {b}",
                    "path": "data/stocks/cache/daily/", "files": k, "rows": None, "resolution": "1 day",
                    "venue": "Alpaca market data v2, feed=sip", "adjustment": "raw and split-adjusted copies",
                    "first": a, "last": b, "freshness_hours": round((now - _parse(b)).total_seconds() / 3600, 1),
                    "used_by": "ORB/H3 candidate selection (ADV, ATR, relative volume)"})
    return out


def other(now: datetime) -> list[dict]:
    out = []
    live = sorted((DATA / "live").rglob("*.jsonl"))
    if live:
        days = sorted({p.parent.name for p in live})
        out.append({"dataset": "Live order-book / trade recordings (smoke tests)", "path": "data/live/", "files": len(live),
                    "rows": None, "resolution": "tick", "venue": "Coinbase / Kraken public WebSockets", "adjustment": "n/a",
                    "first": days[0], "last": days[-1], "freshness_hours": None, "used_by": "none yet (prospective)"})
    ev = list((DATA / "events").rglob("*"))
    if ev:
        out.append({"dataset": "Macro/event calendar and cached release pages", "path": "data/events/", "files": len(ev),
                    "rows": None, "resolution": "event", "venue": "Fed, BLS, BEA, SEC, CFTC, exchange status, CoinDesk RSS",
                    "adjustment": "n/a", "first": "2018 (calendar)", "last": "2027 (calendar); news from 2026-10-25",
                    "freshness_hours": None, "used_by": "event pipeline; macro calendar used by the calendar de-risking strategy (trial:calendar, test3:calendar)"})
    return out


def main():
    now = datetime.now(timezone.utc)
    rows = csv_sets(now) + alpaca_caches(now) + other(now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": now.isoformat(timespec="seconds"), "datasets": rows}, indent=1))
    for r in rows:
        print(f"{r['dataset'][:70]:70s} {str(r['first'])[:19]:19s} -> {str(r['last'])[:19]:19s} {r['resolution']:10s} "
              f"files={r['files']} fresh_h={r['freshness_hours']}")
    return rows


if __name__ == "__main__":
    sys.exit(main() and 0)
