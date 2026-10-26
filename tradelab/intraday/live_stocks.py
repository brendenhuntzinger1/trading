"""US stock intraday PAPER loop: opening prints and completed hourly bars (Yahoo)
-> engine -> journal. Simulated fills with the pre-registered cost model.

    .venv/bin/python -m tradelab.intraday.live_stocks [--once]
"""
from __future__ import annotations

import argparse
import logging
import time
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from tradelab.execution.secrets import RedactingFilter, load as load_creds
from . import yahoo
from .costs import STOCK_AT_OPEN, STOCK_INTRADAY
from .engine import Bar, Engine
from .limits import IntradayLimits
from .replay import Ctx
from .sessions import StockSessions
from .setups import S1IntradayMomentum, S2GapReversal
from .state import Journal, load, save

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "intraday_paper.toml"
STATE = ROOT / "data" / "intraday" / "stocks_state.json"
JOURNAL = ROOT / "data" / "intraday" / "intraday_paper.db"
HOUR = timedelta(hours=1)
log = logging.getLogger("tradelab.intraday.stocks")


def build_setups(names, hourly, daily, sessions):
    out = []
    if "S1" in names:
        out.append(S1IntradayMomentum(hourly, sessions))
    if "S2" in names:
        out.append(S2GapReversal(daily))
    return out


def cycle(engine: Engine, universe: list[str], state: dict, now: datetime, sessions: StockSessions, names,
          fetch=yahoo.bars, max_age_s: float = 900) -> dict:
    """state: {'last_bar': datetime|None, 'opened': 'YYYY-MM-DD'|None}"""
    sess = sessions.session_of(now)
    day = sessions.day_key(now)
    hourly = {s: fetch(s, "1h", "range=60d", now) for s in universe}
    daily = {s: fetch(s, "1d", "range=3mo", now) for s in universe}
    # yesterday's daily bars only: today's daily row is still forming
    daily = {s: d[d.index < day] for s, d in daily.items()}
    engine.setups = build_setups(names, hourly, daily, sessions)
    if sess and state.get("opened") != day and now >= sess[0] + timedelta(minutes=1):
        one = {s: fetch(s, "1m", "range=1d", now) for s in universe}
        opens = {s: float(d.open.iloc[0]) for s, d in one.items() if len(d) and d.index[0] == pd.Timestamp(sess[0])}
        engine.s.blocked = None if len(opens) >= 0.8 * len(universe) else f"opening prints for only {len(opens)}/{len(universe)}"
        engine.process_open(sess[0], opens, Ctx(sessions))
        state["opened"] = day
    starts = sorted({t for d in hourly.values() for t in d.index if state.get("last_bar") is None or t >= state["last_bar"]})
    for t in starts:
        sess_t = sessions.session_of(t.to_pydatetime())
        if sess_t is None:
            continue
        end = min(t + HOUR, pd.Timestamp(sess_t[1])).to_pydatetime()
        bars = {s: Bar(*d.loc[t, ["open", "high", "low", "close", "volume"]]) for s, d in hourly.items() if t in d.index}
        engine.process_bar(t.to_pydatetime(), end, bars, Ctx(sessions))
        state["last_bar"] = (t + HOUR).to_pydatetime()
    return state


def main(once: bool):
    cfg = tomllib.loads(CFG.read_text())
    if cfg.get("mode") != "paper":
        raise SystemExit("paper only")
    load_creds("paper")
    limits, cfg_hash = IntradayLimits.load(CFG, "stocks_risk")
    universe = cfg["stocks"]["universe"]
    names = cfg["stocks"]["setups"]
    sessions = StockSessions()
    costs = {"S1": STOCK_INTRADAY, "S2": STOCK_AT_OPEN}
    engine = Engine(limits, [], {n: costs[n] for n in names}, sessions, cfg["capital"])
    STATE.parent.mkdir(parents=True, exist_ok=True)
    last = load(engine, STATE)
    state = {"last_bar": last or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0), "opened": None}
    journal = Journal(JOURNAL, "paper", f"intraday-stocks-{cfg_hash}")
    while True:
        now = datetime.now(timezone.utc)
        try:
            state = cycle(engine, universe, state, now, sessions, names, max_age_s=limits.max_bar_age_s)
        except Exception as e:
            engine.s.blocked = f"data fetch failed: {e!r}"
            log.warning("cycle failed: %r", e)
        journal.sync(engine)
        save(engine, STATE, state["last_bar"])
        log.info("[EXPERIMENTAL PAPER - simulated fills, not eligible for live] equity %.2f positions %s blocked=%s", engine.equity(), list(engine.s.positions), engine.s.blocked)
        if once:
            break
        time.sleep(120)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    h = logging.StreamHandler(); h.addFilter(RedactingFilter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    main(a.once)
