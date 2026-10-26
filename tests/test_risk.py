from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from tradelab.risk.engine import (Action, AccountState, Breaker, MarketSnapshot, OrderIntent, RiskEngine)
from tradelab.risk.limits import RiskLimits
from tests.conftest import ROOT

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def mkt(**kw):
    d = dict(price=80000, spread_bps=1.0, depth_notional=1e6, received_at=NOW)
    d.update(kw)
    return MarketSnapshot(**d)


def acct(**kw):
    d = dict(equity=1000, start_of_day_equity=1000, peak_equity=1000, weights={})
    d.update(kw)
    return AccountState(**d)


def buy(n, asset="BTC-USD"):
    return OrderIntent(asset, n, "test", "unit test")


def test_config_file_loads_and_is_frozen():
    limits, h = RiskLimits.load(ROOT / "config" / "paper.toml")
    assert len(h) == 12
    with pytest.raises(FrozenInstanceError):
        limits.max_gross_exposure = 5.0


def test_unknown_or_levered_config_rejected(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text("[risk]\nmax_gross_exposur = 0.5\n")
    with pytest.raises(ValueError, match="unknown"):
        RiskLimits.load(p)
    p.write_text("[risk]\nmax_gross_exposure = 2.0\n")
    with pytest.raises(ValueError, match="no leverage"):
        RiskLimits.load(p)


def test_engine_api_has_no_override_parameters():
    for name in ("check", "evaluate"):
        params = inspect.signature(getattr(RiskEngine, name)).parameters
        assert not any(k in params for k in ("override", "force", "limits", "skip"))


def test_position_and_gross_limits_clip_buys():
    eng = RiskEngine(RiskLimits())
    d = eng.check(buy(900), acct(weights={"BTC-USD": 0.4}), mkt())
    assert d.approved and d.notional == pytest.approx(100)          # 0.5 - 0.4 of 1000
    d = eng.check(buy(300, "ETH-USD"), acct(weights={"BTC-USD": 0.5, "ETH-USD": 0.45}), mkt())
    assert d.approved and d.notional == pytest.approx(50)           # gross 1.0 - 0.95


def test_correlated_cluster_limit():
    eng = RiskEngine(RiskLimits(max_cluster_exposure=0.6))
    a = acct(weights={"BTC-USD": 0.5, "ETH-USD": 0.0}, correlations={("BTC-USD", "ETH-USD"): 0.85})
    d = eng.check(buy(300, "ETH-USD"), a, mkt())
    assert d.notional == pytest.approx(100)


def test_sells_allowed_when_new_exposure_halted():
    eng = RiskEngine(RiskLimits())
    acts = eng.evaluate(NOW, acct(), {"BTC-USD": mkt(received_at=NOW - timedelta(minutes=10))})
    assert {Action.HALT_NEW, Action.CANCEL_PENDING} <= acts
    assert not eng.check(buy(100), acct(), mkt()).approved
    assert eng.check(buy(-100), acct(weights={"BTC-USD": 0.3}), mkt()).approved


def test_outage_never_liquidates():
    eng = RiskEngine(RiskLimits())
    acts = eng.evaluate(NOW, acct(weights={"BTC-USD": 0.5}), {"BTC-USD": mkt()}, venue_up=False)
    assert Action.REDUCE not in acts and Action.HALT_NEW in acts


def test_daily_loss_halts_until_next_utc_day():
    eng = RiskEngine(RiskLimits())
    assert Action.HALT_NEW in eng.evaluate(NOW, acct(equity=960), {"BTC-USD": mkt()})
    later = NOW + timedelta(hours=2)
    assert Action.HALT_NEW in eng.evaluate(later, acct(equity=975), {"BTC-USD": mkt(received_at=later)})
    nxt = NOW + timedelta(days=1)
    assert eng.evaluate(nxt, acct(equity=975, start_of_day_equity=975), {"BTC-USD": mkt(received_at=nxt)}) == set()


def test_latched_breakers_need_human_reset():
    eng = RiskEngine(RiskLimits())
    eng.evaluate(NOW, acct(), {"BTC-USD": mkt()}, recon_diff=50)
    assert Action.HALT_NEW in eng.evaluate(NOW, acct(), {"BTC-USD": mkt()}, recon_diff=0)   # still latched
    with pytest.raises(ValueError):
        eng.reset(Breaker.RECONCILIATION_MISMATCH, "", "")
    eng.reset(Breaker.RECONCILIATION_MISMATCH, "owner", "balances checked by hand")
    assert eng.evaluate(NOW, acct(), {"BTC-USD": mkt()}) == set()


def test_drawdown_reduce_only_when_configured():
    a = acct(equity=700, start_of_day_equity=700, peak_equity=1000, weights={"BTC-USD": 0.4})
    off = RiskEngine(RiskLimits())
    assert Action.REDUCE not in off.evaluate(NOW, a, {"BTC-USD": mkt()})
    on = RiskEngine(RiskLimits(reduce_on_max_drawdown=0.5))
    assert Action.REDUCE in on.evaluate(NOW, a, {"BTC-USD": mkt()})
    assert on.reduce_targets({"BTC-USD": 0.4}) == {"BTC-USD": 0.2}


def test_market_quality_and_activity_limits():
    eng = RiskEngine(RiskLimits())
    assert not eng.check(buy(100), acct(), mkt(spread_bps=50)).approved
    assert not eng.check(buy(100), acct(open_orders=4), mkt()).approved
    assert not eng.check(buy(100), acct(orders_today=12), mkt()).approved
    assert not eng.check(buy(100), acct(turnover_30d=2.95), mkt()).approved
    d = eng.check(buy(250), acct(), mkt(depth_notional=1000))
    assert d.notional == pytest.approx(100)                      # 10% of depth
    assert not eng.check(buy(0.5), acct(), mkt()).approved      # below minimum
    assert not eng.check(buy(100), acct(), None).approved


def test_abnormal_volatility_and_rejections_and_model_failure():
    eng = RiskEngine(RiskLimits())
    assert Action.HALT_NEW in eng.evaluate(NOW, acct(), {"BTC-USD": mkt(move_1h=-0.12)})
    eng2 = RiskEngine(RiskLimits())
    acts = eng2.evaluate(NOW, acct(rejections=[NOW - timedelta(minutes=m) for m in (1, 5, 9)]), {"BTC-USD": mkt()})
    assert Action.CANCEL_PENDING in acts
    eng3 = RiskEngine(RiskLimits())
    assert Action.HALT_NEW in eng3.evaluate(NOW, acct(), {"BTC-USD": mkt()}, model_ok=False)


def test_event_flags_ignored_unless_enabled():
    assert RiskEngine(RiskLimits()).evaluate(NOW, acct(), {"BTC-USD": mkt()}, event_flags=["CPI in 30m"]) == set()
    eng = RiskEngine(RiskLimits(block_entries_on_event_flags=True))
    assert Action.HALT_NEW in eng.evaluate(NOW, acct(), {"BTC-USD": mkt()}, event_flags=["CPI in 30m"])
