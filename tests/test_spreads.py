"""Measured spreads vs assumed slippage are separate; quotes in force at a minute's end; staleness."""
import pandas as pd
import pytest

from tradelab.stocks import costs, spreads

M = pd.Timestamp("2024-07-15 13:35", tz="UTC")


def _q(rows):
    return pd.DataFrame([{"bid": b, "ask": a} for _, b, a in rows], index=pd.DatetimeIndex([t for t, _, _ in rows]))


def test_quote_in_force_is_last_at_or_before_minute_end():
    q = _q([(M + pd.Timedelta(seconds=10), 99.0, 101.0), (M + pd.Timedelta(seconds=59), 99.9, 100.1),
            (M + pd.Timedelta(seconds=61), 50.0, 150.0)])                       # after the minute: ignored
    hs = spreads.half_spread_at(q, M)
    assert hs.status == "ok" and hs.value == pytest.approx(0.1 / 100.0)


def test_stale_crossed_and_missing_quotes_are_not_measurements():
    old = _q([(M - pd.Timedelta(minutes=5), 99.0, 101.0)])
    assert spreads.half_spread_at(old, M).status == "stale"
    crossed = _q([(M + pd.Timedelta(seconds=30), 100.0, 100.0)])
    assert spreads.half_spread_at(crossed, M).status == "crossed_or_locked"
    assert spreads.half_spread_at(_q([]).iloc[:0], M).status == "none"


def test_summary_is_labelled_measured_and_counts_unusable():
    vals = [spreads.HalfSpread(0.0005, M, "ok"), spreads.HalfSpread(0.0010, M, "ok"), spreads.HalfSpread(None, M, "stale")]
    s = spreads.summarize(vals)
    assert s["kind"].startswith("MEASURED") and s["median_bp"] == pytest.approx(7.5) and s["share_unusable"] == pytest.approx(1 / 3)


def test_entry_window_minutes_and_half_day_close_minute():
    m = spreads.minutes_et("2024-07-15", "09:35", "10:30")
    assert len(m) == 56 and m[0] == M
    assert spreads.close_minute("2024-11-29") == pd.Timestamp("2024-11-29 17:59", tz="UTC")     # 12:59 ET half-day


def test_costs_keep_measured_spread_and_assumed_slippage_apart():
    from datetime import date
    c = costs.trade_costs(1, 100.0, 100.0, 100, date(2025, 1, 2), 0.0005, 0.0005)
    assert c["spread_measured"] == pytest.approx(0.0010) and c["slippage_assumed"] == pytest.approx(0.0002)
    assert c["label"] == "measured spread + assumed slippage" and c["fees"] < 1e-5      # SEC fee $0 before 2026-04-04
    a = costs.trade_costs(1, 100.0, 100.0, 100, date(2026, 5, 1), None, None)
    assert a["label"] == "cost assumed, not measured" and a["spread_measured"] is None
    assert a["slippage_assumed"] == pytest.approx(0.0020) and a["fees"] >= costs.SEC_FEE
