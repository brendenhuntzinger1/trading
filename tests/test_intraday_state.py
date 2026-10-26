from datetime import timedelta

import pytest

from tradelab.intraday.engine import Bar
from tradelab.intraday.replay import Ctx
from tradelab.intraday.state import Journal, load, save
from tests.test_intraday_engine import T0, crypto_engine, sig, step


def test_restart_resumes_open_position_and_pending_order(tmp_path):
    plan = {T0 + timedelta(minutes=5): [sig(weight=0.5, stop=90, deadline=T0 + timedelta(hours=1))],
            T0 + timedelta(minutes=10): [sig(symbol="ETH-USD", weight=0.2, deadline=T0 + timedelta(hours=1))]}
    a = crypto_engine(plan)
    step(a, 0, {"BTC-USD": Bar(100, 100, 100, 100), "ETH-USD": Bar(10, 10, 10, 10)})
    step(a, 1, {"BTC-USD": Bar(101, 101, 101, 101), "ETH-USD": Bar(10, 10, 10, 10)})   # BTC filled, ETH pending
    save(a, tmp_path / "s.json", T0 + timedelta(minutes=10))
    b = crypto_engine(plan)
    assert load(b, tmp_path / "s.json") == T0 + timedelta(minutes=10)
    assert b.s.positions["BTC-USD"].entry_px == 101 and b.s.pending[0].signal.symbol == "ETH-USD"
    assert b.equity() == pytest.approx(a.equity())
    step(b, 2, {"BTC-USD": Bar(89, 89, 89, 89), "ETH-USD": Bar(11, 11, 11, 11)})       # stop hit after restart
    assert b.trades[0].exit_reason == "stop" and "ETH-USD" in b.s.positions


def test_journal_is_append_only_and_idempotent(tmp_path):
    eng = crypto_engine({T0 + timedelta(minutes=5): [sig(weight=0.5, deadline=T0 + timedelta(minutes=10))]})
    j = Journal(tmp_path / "j.db", "paper", "acct")
    for i in range(3):
        step(eng, i, {"BTC-USD": Bar(100, 100, 100, 100 + i)})
        j.sync(eng)
    j.sync(eng)
    assert j.db.execute("select count(*) from intraday_trades").fetchone()[0] == 1
    with pytest.raises(ValueError):
        Journal(tmp_path / "x.db", "live", "acct")
