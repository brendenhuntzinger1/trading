"""One daily paper-trading cycle. Safe to re-run: decision ids are per day,
so a second run the same day finds its orders already journalled.

    .venv/bin/python -m tradelab.service.daily --config config/paper.toml
"""
from __future__ import annotations

import argparse
import logging
import tomllib
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from tradelab.data.candles import fetch_coinbase, quality
from tradelab.execution.manager import OrderManager
from tradelab.execution.paper import PaperExchange, load_state, save_state
from tradelab.execution.secrets import RedactingFilter, load as load_creds
from tradelab.execution.store import Store
from tradelab.execution.venue import CoinbasePublic
from tradelab.risk.engine import AccountState, Action, MarketSnapshot, OrderIntent, RiskEngine
from tradelab.risk.limits import RiskLimits
from tradelab.governance.promotion import read_lock
from tradelab.service.registry import STRATEGIES, version

ROOT = Path(__file__).resolve().parents[2]
LIVE_DATA = ROOT / "data" / "paper"
ASSETS = ["BTC-USD", "ETH-USD"]
SLEEVE = 0.5
BAND = 0.02
log = logging.getLogger("tradelab.daily")


def refresh_daily(asset: str, now: datetime) -> pd.DataFrame:
    """Keep a point-in-time daily file for the service, separate from research data."""
    path = LIVE_DATA / f"{asset}_1d.csv"
    if path.exists():
        old = pd.read_csv(path, index_col=0, parse_dates=["available_at", "received_at"])
        old.index = pd.to_datetime(old.index, utc=True)
        start = old.index[-3].to_pydatetime()
    else:
        old, start = None, datetime(2017, 1, 1, tzinfo=timezone.utc)
    new = fetch_coinbase(asset, "1d", start, now)
    df = new if old is None else pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    LIVE_DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return df


def snapshot(pub: CoinbasePublic, asset: str, now: datetime, band_bps: float):
    b = pub.book(asset)
    h = fetch_coinbase(asset, "1h", now - timedelta(days=31), now)
    r = h.close.pct_change().dropna()
    short = r.iloc[-24:].std()
    med = r.rolling(24).std().iloc[-30 * 24:].median()
    move = float(h.close.iloc[-1] / h.close.iloc[-2] - 1) if len(h) > 1 else 0.0
    return b, MarketSnapshot(price=b.mid, spread_bps=b.spread_bps, depth_notional=b.depth("buy", band_bps),
                             received_at=b.received_at, move_1h=move, vol_ratio=float(short / med) if med else 1.0,
                             depth_bid=b.depth("sell", band_bps))


def correlations(daily: dict[str, pd.DataFrame]) -> dict:
    r = pd.DataFrame({a: d.close.pct_change() for a, d in daily.items()}).iloc[-90:]
    c = r.corr()
    return {tuple(sorted((a, b))): float(c.loc[a, b]) for a in c for b in c if a < b}


def run(config_path: Path, now: datetime | None = None, journal: Path | None = None,
        clock=lambda: datetime.now(timezone.utc)) -> dict:
    """One cycle at logical time `now`. `clock` measures real elapsed time, so data
    fetched early in a slow run is judged stale at the moment each decision is made."""
    t0 = clock()
    now = now or t0
    decision_time = lambda: now + (clock() - t0)
    cfg = tomllib.loads(Path(config_path).read_text())
    if cfg.get("mode") != "paper":
        raise SystemExit("this runner only trades paper accounts")
    load_creds("paper")                                  # refuses if live keys are in the environment
    limits, cfg_hash = RiskLimits.load(config_path)
    store = Store(journal or ROOT / "data" / "journal_paper.db", "paper")
    pub = CoinbasePublic()
    summary = {"at": now.isoformat(), "config_hash": cfg_hash, "accounts": {}}
    day = now.strftime("%Y-%m-%d")
    today_close = pd.Timestamp(now).floor("D")           # the daily bar that closed at 00:00 UTC today

    daily, data_ok, notes = {}, True, []
    for a in ASSETS:
        try:
            df = refresh_daily(a, now)
            q = quality(df.drop(columns=["available_at", "received_at"]), "1d", pd.Timestamp(now))
            last = df.available_at.iloc[-1]
            if not q.ok or last < today_close:
                data_ok = False
                notes.append(f"{a}: data not ok (quality={q.ok}, newest bar closed {last:%Y-%m-%d %H:%M}, need {today_close:%Y-%m-%d %H:%M})")
            daily[a] = df
        except Exception as e:
            data_ok = False
            notes.append(f"{a}: candle fetch failed: {e!r}")
    markets, venue_up = {}, True
    for a in ASSETS:
        try:
            book, markets[a] = snapshot(pub, a, now, limits.depth_band_bps)
            if not book.valid():
                venue_up = False
                notes.append(f"{a}: invalid book")
        except Exception as e:
            venue_up = False
            notes.append(f"{a}: market data failed: {e!r}")
    flags = event_flags(now)
    flag_text = [f"{f.kind}/{f.severity}: {f.reason}" for f in flags]
    summary["event_flags"] = flag_text
    rules_cache: dict = {}

    def rules(a):
        if a not in rules_cache:
            rules_cache[a] = pub.rules(a)
        return rules_cache[a]

    corr = correlations(daily) if len(daily) == len(ASSETS) else {}
    lock = read_lock()
    approved = {e["name"]: e["version"] for e in [lock["champion"], *lock["benchmarks"], *lock["challengers"]]}

    for name in cfg["strategies"]:
        account = f"paper-{name}"
        state_path = ROOT / "data" / "paper_venue" / f"{account}.json"
        ex = load_state(PaperExchange(lambda a: pub.book(a), rules, cash=cfg["capital"]), state_path)
        try:
            summary["accounts"][account] = _cycle_account(
                name, account, cfg, limits, cfg_hash, store, ex, markets, venue_up, data_ok, daily, corr,
                flags, flag_text, approved, notes, now, day, decision_time)
        except Exception as e:  # one account failing must not stop the others
            notes.append(f"{account}: cycle aborted: {e!r}")
            store.breaker(now, account, "model_failure", f"cycle aborted: {e!r}", {"halt_new"})
            summary["accounts"][account] = {"error": repr(e), "orders": [], "breakers": {"model_failure": repr(e)}}
        finally:
            save_state(ex, state_path)                   # the simulated venue must never lose what it executed
    summary["notes"] = notes
    return summary


def _cycle_account(name, account, cfg, limits, cfg_hash, store, ex, markets, venue_up, data_ok, daily, corr,
                   flags, flag_text, approved, notes, now, day, decision_time) -> dict:
    spec = STRATEGIES[name]
    locked_ok = approved.get(name) == version(spec)
    if not locked_ok:
        notes.append(f"{name}: code version {version(spec)} is not in config/strategies.lock; not trading it")
    om = OrderManager(store, ex, account)
    om.recover()                                         # reconcile anything left from a previous run
    marks, stale_marks = last_marks(store, account, {a: m.price for a, m in markets.items()})
    if stale_marks:
        notes.append(f"{account}: valued with last known prices for {stale_marks}")
    cash, pos = store.positions(account, cfg["capital"])
    equity = cash + sum(q * marks.get(a, 0.0) for a, q in pos.items())
    hist = store.db.execute("SELECT at, equity FROM equity WHERE mode='paper' AND account=? ORDER BY at", (account,)).fetchall()
    peak = max([equity] + [e for _, e in hist])
    sod = next((e for at, e in reversed(hist) if at[:10] < day), equity)
    weights = {a: pos.get(a, 0.0) * marks.get(a, 0.0) / equity for a in ASSETS} if equity > 0 else {}
    acct = AccountState(equity=equity, start_of_day_equity=sod, peak_equity=peak, weights=dict(weights),
                        open_orders=len(store.open_orders(account)),
                        orders_today=store.approved_today(account, day),
                        turnover_30d=_turnover(store, account, now, equity),
                        rejections=store.recent_rejections(account, now - timedelta(hours=1)), correlations=corr)

    targets, model_ok, sources = {}, data_ok and locked_ok, {}
    if model_ok:
        try:
            for a in ASSETS:
                df = daily[a][daily[a].available_at <= pd.Timestamp(now)]
                w = float(spec(df).iloc[-1])
                if not np.isfinite(w) or not 0 <= w <= 1:
                    raise ValueError(f"{name} produced invalid weight {w} for {a}")
                targets[a] = w * SLEEVE
                sources[a] = {"data_as_of": df.index[-1].isoformat(), "received_at": df.received_at.iloc[-1].isoformat()}
        except Exception:
            model_ok = False
            targets, sources = {}, {}
            notes.append(f"{name}: strategy failure: {traceback.format_exc(limit=1)}")
    recon = om.reconcile_balances(cfg["capital"], marks) if marks else 0.0
    eng = RiskEngine(limits, cfg_hash, latched=store.active_latches(account))

    def evaluate():
        acts = eng.evaluate(decision_time(), acct, markets, venue_up=venue_up, model_ok=model_ok, recon_diff=recon,
                            event_flags=[t for f, t in zip(flags, flag_text) if f.severity != "info"])
        for b in eng.state.latched:
            store.latch(account, b.value, eng.state.active.get(b, ""), now)
        return acts

    acts = evaluate()
    for a in sources:
        sources[a]["event_flags"] = [{"kind": f.kind, "reason": f.reason, "source_ids": list(f.source_ids)}
                                     for f in flags if a.split("-")[0] in f.assets or "crypto_market" in f.assets]
    for b, detail in eng.state.active.items():
        store.breaker(now, account, b.value, detail, {x.value for x in acts})
    if Action.CANCEL_PENDING in acts:
        om.cancel_all()
    if Action.REDUCE in acts and targets:                # explicit drawdown policy, only if configured
        cut = eng.reduce_targets(weights)
        targets = {a: min(t, cut.get(a, 0.0)) for a, t in targets.items()}
        notes.append(f"{account}: REDUCE active, targets capped at {cut}")

    results = []
    for a in ASSETS:
        did = f"{account}:{a}:{day}"
        row = dict(id=did, at=decision_time(), account=account, strategy=name, strategy_version=version(spec), asset=a,
                   data_as_of=sources.get(a, {}).get("data_as_of"), target_weight=targets.get(a),
                   current_weight=acct.weights.get(a, 0.0), config_hash=cfg_hash, sources=sources.get(a, {}))
        active = [b.value for b in eng.state.active]
        if a not in targets:
            store.decision(**row, intent_notional=0, outcome="skipped", final_notional=0,
                           reasons=["no valid target"] + notes, breakers=active)
            continue
        if any(o.decision_id == did for o in store.orders_for_account_day(account, day)):
            store.decision(**row, intent_notional=0, outcome="skipped", final_notional=0,
                           reasons=["already acted on this asset today (one decision per asset per UTC day)"], breakers=active)
            continue
        delta = targets[a] - acct.weights.get(a, 0.0)
        if abs(delta) <= BAND and targets[a] > 0:
            store.decision(**row, intent_notional=0, outcome="skipped", final_notional=0,
                           reasons=[f"within {BAND:.0%} band"], breakers=active)
            continue
        notional = delta * equity
        if notional < 0:                                 # never sell more than we hold
            notional = max(notional, -pos.get(a, 0.0) * marks[a])
        acts = evaluate()                                # re-check breakers at the moment of each decision
        d = eng.check(OrderIntent(a, notional, name, f"target {targets[a]:.3f} vs {acct.weights.get(a, 0):.3f}"),
                      acct, markets.get(a))
        store.decision(**row, intent_notional=notional, outcome="approved" if d.approved else "rejected",
                       final_notional=d.notional, reasons=d.reasons, breakers=d.breakers)
        if d.approved:
            o = om.submit(did, a, d.notional, marks[a], decided_at=row["at"])
            results.append((a, o.status.value, round(o.filled_quote, 2), round(o.fees, 4)))
            # the next asset's checks must see this order: exposure, counts, turnover, rejections
            acct.weights[a] = acct.weights.get(a, 0.0) + d.notional / equity
            acct.orders_today += 1
            acct.turnover_30d += abs(d.notional) / equity
            acct.rejections = acct.rejections + om.rejections[-1:] if o.status.value == "rejected" else acct.rejections
            if o.status.value not in ("filled", "cancelled", "rejected", "not_found"):
                acct.open_orders += 1
    cash, pos = store.positions(account, cfg["capital"])
    equity = cash + sum(q * marks.get(a, 0.0) for a, q in pos.items())
    if not stale_marks:                                  # never journal equity built on missing prices
        store.mark(now, account, equity, cash, pos, marks, operating_cost=cfg.get("operating_cost_per_day", 0.0))
    return {"equity": round(equity, 2), "targets": targets, "orders": results,
            "breakers": {b.value: d for b, d in eng.state.active.items()}}


def event_flags(now: datetime) -> list:
    """Event flags from tradelab.events, logged with every decision. They block
    entries only if risk.block_entries_on_event_flags is enabled (off until the
    prospective evaluation shows they help)."""
    try:
        from tradelab.events.flags import active_flags
        from tradelab.events.store import EventStore
        return active_flags(now, EventStore())
    except Exception as e:  # event intelligence failing must not stop or skew the daily cycle
        log.warning("event flags unavailable: %r", e)
        return []


def last_marks(store: Store, account: str, fresh: dict[str, float]) -> tuple[dict[str, float], list[str]]:
    """Fresh prices where available, else the last journalled ones (reported as stale)."""
    import json
    row = store.db.execute("SELECT marks FROM equity WHERE mode='paper' AND account=? ORDER BY at DESC LIMIT 1", (account,)).fetchone()
    prev = json.loads(row[0]) if row else {}
    stale = [a for a in ASSETS if a not in fresh]
    return {**prev, **fresh}, stale


def _turnover(store: Store, account: str, now: datetime, equity: float) -> float:
    since = (now - timedelta(days=30)).isoformat()
    t = store.db.execute("SELECT COALESCE(SUM(base*price),0) FROM fills WHERE account=? AND at>=?", (account, since)).fetchone()[0]
    return t / equity if equity > 0 else 0.0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "paper.toml"))
    args = ap.parse_args()
    h = logging.StreamHandler()
    h.addFilter(RedactingFilter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    import json
    print(json.dumps(run(Path(args.config)), indent=1, default=str))
