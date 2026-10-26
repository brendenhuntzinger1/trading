"""Daily runner end-to-end with fake market data (no network)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

import tradelab.service.daily as daily
from tradelab.execution.models import ProductRules
from tradelab.execution.venue import Book
from tests.conftest import ROOT

NOW = datetime(2026, 10, 25, 0, 20, tzinfo=timezone.utc)


def candles(tf, end, n, start_px=100.0, drift=0.002, stale_hours=0, crash=0.0):
    step = pd.Timedelta(days=1) if tf == "1d" else pd.Timedelta(hours=1)
    last_start = pd.Timestamp(end).floor("D" if tf == "1d" else "h") - step - pd.Timedelta(hours=stale_hours)
    idx = pd.date_range(end=last_start, periods=n, freq=step, tz="UTC")
    noise = np.random.default_rng(42).normal(0, 0.01, n)          # same noise for every asset: correlation ~1
    px = start_px * np.exp(np.cumsum(np.full(n, drift) + noise))
    if crash:
        px[-1] *= 1 - crash
    df = pd.DataFrame({"open": px, "high": px * 1.01, "low": px * 0.99, "close": px, "volume": 1.0}, index=idx)
    df["available_at"] = df.index + step
    df["received_at"] = pd.Timestamp(end)
    return df


class FakePublic:
    up = True
    fail_calls = ()        # book() call numbers that raise like the real urllib client
    px_mult = 1.0
    received_offset = timedelta(0)

    def __init__(self):
        self.calls = 0
        self.now = NOW                 # set to each run's time by run_at()

    def book(self, asset):
        import urllib.error
        self.calls += 1
        if not self.up:
            raise urllib.error.URLError("venue down")
        if self.calls in self.fail_calls:
            raise urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None)
        px = float(candles("1d", NOW, 1000).close.iloc[-1]) * self.px_mult
        return Book(asset, [(px * 0.9999, 50.0)], [(px * 1.0001, 50.0)], self.now, self.now + self.received_offset)
    def rules(self, asset):
        return ProductRules(asset, Decimal("0.00000001"), Decimal("0.01"), Decimal("1"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "ROOT", tmp_path)
    monkeypatch.setattr(daily, "LIVE_DATA", tmp_path / "data" / "paper")
    (tmp_path / "data").mkdir()
    state = {"stale": 0, "crash": 0.0}
    monkeypatch.setattr(daily, "fetch_coinbase", lambda a, tf, s, e=None: candles(
        tf, e or NOW, 1000 if tf == "1d" else 800, stale_hours=state["stale"], crash=state["crash"] if tf == "1d" else 0.0))
    pub = FakePublic()
    monkeypatch.setattr(daily, "CoinbasePublic", lambda: pub)
    return tmp_path, state, pub


def run_at(env, t, cfg=None, **kw):
    """One cycle at logical time t, with the fake venue's books stamped at t."""
    tmp, _, pub = env
    pub.now = t
    return daily.run(cfg or ROOT / "config" / "paper.toml", t, tmp / "j.db", **kw)


def test_daily_cycle_trades_once_per_day(env):
    tmp, *_ = env
    s1 = run_at(env, NOW)
    assert s1["accounts"]["paper-ensemble_vol40"]["orders"], "uptrend should produce buys"
    s2 = run_at(env, NOW + timedelta(minutes=5))
    assert all(not v["orders"] or all(o[1] == "filled" for o in v["orders"]) for v in s2["accounts"].values())
    import sqlite3
    n_orders = sqlite3.connect(tmp / "j.db").execute("select count(*) from orders").fetchone()[0]
    assert n_orders == sum(len(v["orders"]) for v in s1["accounts"].values())


def test_stale_candles_block_new_trades(env):
    tmp, state, _ = env
    state["stale"] = 72
    s = run_at(env, NOW)
    assert all(not v["orders"] for v in s["accounts"].values())
    assert any("data not ok" in n for n in s["notes"])
    assert all("model_failure" in v["breakers"] for v in s["accounts"].values())


def test_venue_outage_holds_positions_and_places_nothing(env):
    tmp, _, pub = env
    run_at(env, NOW)
    pub.up = False
    s = run_at(env, NOW + timedelta(days=1))
    for v in s["accounts"].values():
        assert not v["orders"]
        assert "exchange_outage" in v["breakers"]


def test_outage_does_not_mark_positions_at_zero(env):
    """Regression: missing prices were treated as 0, faking a drawdown that would latch the breaker."""
    tmp, _, pub = env
    s1 = run_at(env, NOW)
    pub.up = False
    s2 = run_at(env, NOW + timedelta(days=1))
    for acct, v in s2["accounts"].items():
        assert v["equity"] == pytest.approx(s1["accounts"][acct]["equity"], rel=0.01)
        assert "max_drawdown" not in v["breakers"]


def test_unlocked_strategy_code_is_not_traded(env, monkeypatch):
    tmp, *_ = env
    import tradelab.governance.promotion as promo
    lock = promo.read_lock()
    lock["champion"]["version"] = "tampered00"
    monkeypatch.setattr(daily, "read_lock", lambda: lock)
    s = run_at(env, NOW)
    assert not s["accounts"]["paper-ensemble_vol40"]["orders"]
    assert s["accounts"]["paper-fixed_allocation"]["orders"]
    assert any("not in config/strategies.lock" in n for n in s["notes"])


# ---- regressions from the independent review -------------------------------------------

def _journal(tmp):
    import sqlite3
    return sqlite3.connect(tmp / "j.db")


def test_network_error_mid_run_is_contained_and_recovers(env):
    """A real-client HTTP error inside one account's order must not abort the run or strand the account."""
    tmp, _, pub = env
    pub.fail_calls = (4,)                                    # 2 snapshot calls, then ensemble BTC ok, ETH fails
    s = run_at(env, NOW)
    assert s["accounts"]["paper-fixed_allocation"]["orders"], "other accounts must still trade"
    pub.fail_calls = ()
    s2 = run_at(env, NOW + timedelta(days=1))
    assert "reconciliation_mismatch" not in s2["accounts"]["paper-ensemble_vol40"]["breakers"]
    stuck = _journal(tmp).execute("select count(*) from orders where status in ('new','unknown')").fetchone()[0]
    assert stuck == 0


def test_rerun_after_target_flip_does_not_trade_twice(env):
    tmp, state, _ = env
    run_at(env, NOW)
    n1 = _journal(tmp).execute("select count(*) from orders").fetchone()[0]
    state["crash"] = 0.30                                     # same UTC day, new data flips targets to sell
    run_at(env, NOW + timedelta(hours=6))
    db = _journal(tmp)
    assert db.execute("select count(*) from orders").fetchone()[0] == n1
    assert db.execute("select count(*) from decisions").fetchone()[0] > db.execute("select count(distinct id) from decisions").fetchone()[0]


def test_latched_breaker_persists_until_human_reset(env):
    import json
    tmp, _, _ = env
    cfg = ROOT / "config" / "paper.toml"
    run_at(env, NOW)
    vp = tmp / "data" / "paper_venue" / "paper-fixed_allocation.json"
    good = vp.read_text()
    bad = json.loads(good); bad["bal"]["USD"] -= 50
    vp.write_text(json.dumps(bad))
    s = run_at(env, NOW + timedelta(days=1))
    assert "reconciliation_mismatch" in s["accounts"]["paper-fixed_allocation"]["breakers"]
    vp.write_text(good.replace('"bal"', '"bal"'))
    s = run_at(env, NOW + timedelta(days=2))
    assert "reconciliation_mismatch" in s["accounts"]["paper-fixed_allocation"]["breakers"], "latch must survive"
    from tradelab.execution.store import Store
    Store(tmp / "j.db", "paper").reset_latch("paper-fixed_allocation", "reconciliation_mismatch", "owner", "venue checked", NOW)
    s = run_at(env, NOW + timedelta(days=3))
    assert "reconciliation_mismatch" not in s["accounts"]["paper-fixed_allocation"]["breakers"]


def test_cluster_limit_holds_across_assets_in_one_cycle(env):
    import json
    tmp, _, pub = env
    cfg = ROOT / "config" / "paper.toml"
    run_at(env, NOW)
    pub.px_mult = 1.10
    run_at(env, NOW + timedelta(days=1))
    row = _journal(tmp).execute("select equity, positions, marks from equity where account='paper-buy_hold' order by at desc limit 1").fetchone()
    pos, marks = json.loads(row[1]), json.loads(row[2])
    gross = sum(q * marks[a] for a, q in pos.items()) / row[0]
    assert gross <= 0.80 + 0.01


def test_rejections_in_journal_trip_breaker(env):
    from tradelab.execution.models import Order, Status
    from tradelab.execution.store import Store
    tmp, _, _ = env
    st = Store(tmp / "j.db", "paper")
    for i in range(3):
        st.put_order(Order(f"r{i}", "paper-fixed_allocation", "BTC-USD", "buy", "market", 10.0, None, None, f"d{i}",
                           status=Status.REJECTED, submitted_at=NOW - timedelta(minutes=5)))
    s = run_at(env, NOW)
    assert "repeated_rejections" in s["accounts"]["paper-fixed_allocation"]["breakers"]


def test_snapshot_age_measured_at_decision_time(env):
    """Books are stamped when fetched; if the decision happens 10 min later (slow run), they are stale."""
    ticks = iter([NOW] + [NOW + timedelta(minutes=10)] * 1000)
    s = run_at(env, NOW, clock=lambda: next(ticks))
    assert all("stale_data" in v["breakers"] for v in s["accounts"].values())


def test_previous_days_bar_must_be_published(env):
    tmp, state, _ = env
    state["stale"] = 24                                     # newest bar ended yesterday 00:00, not today 00:00
    s = run_at(env, NOW)
    assert all(not v["orders"] for v in s["accounts"].values())


def test_configured_reduce_policy_is_executed(env):
    """REDUCE on max drawdown must actually cut positions when (and only when) configured."""
    import json
    tmp, _, pub = env
    cfg = tmp / "reduce.toml"
    cfg.write_text((ROOT / "config" / "paper.toml").read_text().replace("reduce_on_max_drawdown = 0.0", "reduce_on_max_drawdown = 0.5"))
    run_at(env, NOW, cfg)
    pub.px_mult = 0.40                                       # -60% on held coins -> drawdown beyond 25%
    s = run_at(env, NOW + timedelta(days=1), cfg)
    bh = s["accounts"]["paper-buy_hold"]
    assert "max_drawdown" in bh["breakers"]
    assert any(o[0] and o[1] == "filled" for o in bh["orders"]), "REDUCE should have sold"
    row = _journal(tmp).execute("select notional from (select json_extract(data,'$.quote_size') notional, json_extract(data,'$.side') side "
                                "from orders where account='paper-buy_hold') where side='sell'").fetchall()
    assert row
