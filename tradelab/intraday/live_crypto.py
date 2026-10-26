"""Crypto intraday PAPER loop: completed Coinbase 5-minute bars -> engine -> journal.

    .venv/bin/python -m tradelab.intraday.live_crypto [--once] [--minutes N]

Fills are simulated at bar prices with the pre-registered cost model; that
measures the strategy, not real execution quality (which needs the order-book
paper venue or a live venue, neither used here).
"""
from __future__ import annotations

import argparse
import logging
import time
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from tradelab.data.candles import fetch_coinbase
from tradelab.execution.secrets import RedactingFilter, load as load_creds
from .costs import CRYPTO_TAKER
from .engine import Bar, Engine
from .limits import IntradayLimits
from .replay import Ctx
from .sessions import CryptoSessions
from .setups import C1CascadeReversal, C2IntradayMomentum
from .state import Journal, load, save

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "intraday_paper.toml"
STATE = ROOT / "data" / "intraday" / "crypto_state.json"
JOURNAL = ROOT / "data" / "intraday" / "intraday_paper.db"
BAR = timedelta(minutes=5)
log = logging.getLogger("tradelab.intraday.crypto")


def make_setups(names, frames):
    known = {"C1": lambda: C1CascadeReversal(frames), "C2": lambda: C2IntradayMomentum(frames)}
    return [known[n]() for n in names]


def cycle(engine: Engine, frames: dict, last_bar, names, now: datetime, max_age_s: float, fetch=fetch_coinbase):
    """Fetch new complete bars, feed every unprocessed one to the engine in time order."""
    for sym in frames:
        start = (frames[sym].index[-1] - BAR * 3).to_pydatetime()
        new = fetch(sym, "5m", start, now)[["open", "high", "low", "close", "volume"]]
        frames[sym] = pd.concat([frames[sym][~frames[sym].index.isin(new.index)], new]).sort_index()
    newest = max(f.index[-1] for f in frames.values()) + BAR
    age = (now - newest.to_pydatetime()).total_seconds()
    engine.s.blocked = f"newest complete bar is {age / 60:.0f} min old" if age > max_age_s else None
    engine.setups = make_setups(names, frames)                  # features recomputed causally on the new data
    starts = sorted({t for f in frames.values() for t in f.index if last_bar is None or t + BAR > last_bar})
    for t in starts:
        bars = {s: Bar(*f.loc[t, ["open", "high", "low", "close", "volume"]]) for s, f in frames.items() if t in f.index}
        engine.process_bar(t.to_pydatetime(), (t + BAR).to_pydatetime(), bars, Ctx(engine.sessions))
        last_bar = (t + BAR).to_pydatetime()
    return last_bar


def main(once: bool, minutes: float | None):
    cfg = tomllib.loads(CFG.read_text())
    if cfg.get("mode") != "paper":
        raise SystemExit("paper only")
    load_creds("paper")
    limits, cfg_hash = IntradayLimits.load(CFG, "crypto_risk")
    c = cfg["crypto"]
    now = datetime.now(timezone.utc)
    frames = {s: fetch_coinbase(s, "5m", now - timedelta(days=c["history_days"]), now)[["open", "high", "low", "close", "volume"]]
              for s in c["symbols"]}
    engine = Engine(limits, [], {n: CRYPTO_TAKER for n in c["setups"]}, CryptoSessions(), cfg["capital"])
    STATE.parent.mkdir(parents=True, exist_ok=True)
    last_bar = load(engine, STATE)
    if last_bar is None:                                       # first start: begin from now, never replay into "live" P&L
        last_bar = max(f.index[-1] for f in frames.values()).to_pydatetime() + BAR
    journal = Journal(JOURNAL, "paper", f"intraday-crypto-{cfg_hash}")
    end = now + timedelta(minutes=minutes) if minutes else None
    while True:
        now = datetime.now(timezone.utc)
        try:
            last_bar = cycle(engine, frames, last_bar, c["setups"], now, limits.max_bar_age_s)
        except Exception as e:  # network trouble: block entries, keep managing on the next good cycle
            engine.s.blocked = f"data fetch failed: {e!r}"
            log.warning("cycle failed: %r", e)
        journal.sync(engine)
        save(engine, STATE, last_bar)
        log.info("[EXPERIMENTAL PAPER - simulated fills, not eligible for live] equity %.2f positions %s blocked=%s", engine.equity(), list(engine.s.positions), engine.s.blocked)
        if once or (end and now >= end):
            break
        time.sleep(60 - datetime.now(timezone.utc).second + 5)  # a few seconds after each minute


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--minutes", type=float)
    a = ap.parse_args()
    h = logging.StreamHandler(); h.addFilter(RedactingFilter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    main(a.once, a.minutes)
