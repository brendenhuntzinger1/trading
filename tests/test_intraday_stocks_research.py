import numpy as np
import pandas as pd
import pytest

from tradelab.intraday.research import stocks_s1 as S1, stocks_s2 as S2
from tradelab.intraday.research.stocks_common import net_return
from tradelab.intraday.research.stocks_eval import daily_pnl, e1_lower_bound, evaluate, thirds


def _daily_px(n=60, syms=("SPY", "AAA", "BBB", "CCC"), seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n)
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, len(syms))), axis=0)), idx, list(syms))
    open_ = close.shift(1) * np.exp(rng.normal(0, 0.015, (n, len(syms))))
    open_.iloc[0] = close.iloc[0]
    vol = pd.DataFrame(5e6, idx, list(syms))
    return {"open": open_, "close": close, "volume": vol, "high": np.maximum(open_, close) * 1.01, "low": np.minimum(open_, close) * 0.99}


def test_s2_signal_uses_nothing_after_the_open():
    px = _daily_px()
    base = S2.signals(px, threshold=0.0)
    shocked = {k: v.copy() for k, v in px.items()}
    for k in ("close", "high", "low"):
        shocked[k].iloc[30:] *= 3.0             # same-day close and everything after session 30 changes
    shocked["open"].iloc[31:] *= 3.0
    pd.testing.assert_frame_equal(base.iloc[:31], S2.signals(shocked, threshold=0.0).iloc[:31])


def test_s2_picks_most_negative_relative_gaps_and_charges_amended_costs():
    px = _daily_px()
    t = S2.trades(px, "2024-01-01", "2024-12-31", top=1, threshold=0.0)
    assert (t.side == "long").all() and (t.size_weight == 0.2).all()
    d = t.session.iloc[0]
    rel = S2.signals(px, threshold=0.0).loc[d]
    assert t.symbol.iloc[0] == rel.idxmin()
    r = t.iloc[0]
    assert r.net_ret == pytest.approx(r.exit_px * (1 - 0.0003) / (r.entry_px * (1 + 0.0005)) - 1)


def test_net_return_long_and_short():
    e, x = pd.Series([100.0, 100.0]), pd.Series([110.0, 90.0])
    g, n = net_return(e, x, pd.Series(["long", "short"]), 0.001, 0.002)
    assert g.tolist() == pytest.approx([0.10, 100 / 90 - 1])
    assert n.iloc[0] == pytest.approx(110 * 0.998 / (100 * 1.001) - 1)
    assert n.iloc[1] == pytest.approx(100 * 0.999 / (90 * 1.002) - 1)


def test_s1_signal_only_uses_1030_price_and_prior_close():
    idx = pd.bdate_range("2024-03-01", periods=5)
    hp = {"p1030": pd.DataFrame({"A": [101, 102, 103, 104, 105.0]}, idx),
          "prev_close": pd.DataFrame({"A": [100, 101, 102, 103, 104.0]}, idx),
          "o1530": pd.DataFrame({"A": [101.0] * 5}, idx), "close": pd.DataFrame({"A": [1e9] * 5}, idx)}
    sig = S1.signal(hp)
    hp2 = dict(hp, close=hp["close"] * 0 + 1, o1530=hp["o1530"] * 7)     # change everything after 10:30
    pd.testing.assert_frame_equal(sig, S1.signal(hp2))
    t = S1.trades(hp, idx, threshold=0.0025, top=5)
    assert len(t) == 5 and (t.entry_px == 101.0).all()


def test_eval_criteria_on_known_inputs():
    sess = pd.bdate_range("2024-01-02", periods=300)
    rng = np.random.default_rng(3)
    good = pd.DataFrame({"session": sess, "net_ret": 0.004 + rng.normal(0, 0.002, 300), "size_weight": 0.2})
    good["gross_ret"] = good.net_ret + 0.0008
    assert e1_lower_bound(good, sess) > 0
    r = evaluate(good, good.assign(net_ret=good.net_ret - 0.001), sess, np.zeros(1000), n_trials=96, trial_sr_var=1e-4)
    assert r["E1"] and r["E2"] and r["E3"] and r["E4"] and r["E5"] and r["E7"]
    bad = good.assign(net_ret=-good.net_ret)
    r = evaluate(bad, bad, sess, np.zeros(1000), 96, 1e-4)
    assert not r["E1"] and not r["E5"] and not r["ALL_PASS"]


def test_daily_pnl_counts_no_trade_days_as_zero():
    sess = pd.bdate_range("2024-01-02", periods=10)
    t = pd.DataFrame({"session": [sess[2]], "net_ret": [0.01], "size_weight": [0.2], "gross_ret": [0.011]})
    p = daily_pnl(t, sess)
    assert len(p) == 10 and p.sum() == pytest.approx(0.002) and (p == 0).sum() == 9
    assert thirds(p) == pytest.approx([0.002, 0.0, 0.0])
