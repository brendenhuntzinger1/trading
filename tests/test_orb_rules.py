"""ORB rules on synthetic 1-minute bars: timestamps (DST), opening range, stop entry with gap-through fills,
never-triggered orders, stop-first in the entry minute, gap-through stops, half-day exits, sizing cap,
point-in-time split adjustment and selection."""
import numpy as np
import pandas as pd
import pytest

from tradelab.stocks import orb
from tradelab.stocks.timeutil import bars_frame, session_bounds, to_et

DAY = "2024-07-15"
O, C = session_bounds(DAY)


def minute_bars(day=DAY, rows=None, base=100.0, after=None, switch=11):
    """Flat bars at `base` until minute offset `switch`, then at `after` (default: base);
    `rows` overrides {minute_offset: (o, h, l, c)}."""
    o, c = session_bounds(day)
    idx = pd.date_range(o, c - pd.Timedelta(minutes=1), freq="min")
    px = np.where(np.arange(len(idx)) < switch, base, base if after is None else after)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    for k, (a, h, l, cl) in (rows or {}).items():
        df.iloc[k, :4] = [a, h, l, cl]
    return df


def test_dst_and_standard_time_open_at_0930_et():
    assert O == pd.Timestamp("2024-07-15 13:30", tz="UTC")
    assert session_bounds("2024-01-16")[0] == pd.Timestamp("2024-01-16 14:30", tz="UTC")
    f = bars_frame([{"t": "2024-01-16T14:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}])
    assert to_et(f.index[0]).strftime("%H:%M") == "09:30"


def test_opening_range_needs_the_0930_bar_and_gives_direction():
    b = minute_bars(rows={0: (100, 101, 99.5, 100.5), 4: (100.5, 102, 100, 101.5)})
    r = orb.opening_range(b, O)
    assert (r.high, r.low, r.direction) == (102, 99.5, orb.LONG)
    assert orb.opening_range(b.iloc[1:], O) is None
    doji = orb.opening_range(minute_bars(), O)
    assert doji.direction == 0


def test_stop_entry_fills_at_level_or_at_open_when_gapped_through():
    b = minute_bars(rows={10: (101.0, 102.5, 100.9, 102.0)})            # trades through 102 intrabar
    t = orb.simulate(b, O, C, orb.LONG, atr_value=2.0, level=102.0)
    assert t.triggered and t.entry_px == 102.0 and t.entry_time == O + pd.Timedelta(minutes=10)
    g = minute_bars(rows={10: (103.0, 103.5, 102.9, 103.2)})            # opens above the level
    t2 = orb.simulate(g, O, C, orb.LONG, atr_value=2.0, level=102.0)
    assert t2.entry_px == 103.0


def test_never_triggered_means_no_trade():
    assert not orb.simulate(minute_bars(), O, C, orb.LONG, atr_value=2.0, level=105.0).triggered


def test_stop_first_when_entry_and_stop_share_a_minute():
    b = minute_bars(rows={10: (101.0, 102.5, 101.7, 102.0)})            # stop = 102 - 0.2 = 101.8 > low
    t = orb.simulate(b, O, C, orb.LONG, atr_value=2.0, level=102.0)
    assert t.exit_reason == "stop_same_minute" and t.exit_px == pytest.approx(101.8) and t.r == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_the_open_and_close_exit_otherwise():
    b = minute_bars(rows={10: (101.0, 102.5, 101.9, 102.3), 20: (101.0, 101.2, 100.8, 101.1)}, after=102.3)
    t = orb.simulate(b, O, C, orb.LONG, atr_value=2.0, level=102.0)
    assert t.exit_reason == "stop_gap" and t.exit_px == 101.0 and t.r < -1.0
    up = minute_bars(rows={10: (101.0, 102.5, 101.9, 102.3)}, after=103.0)
    t2 = orb.simulate(up, O, C, orb.LONG, atr_value=2.0, level=102.0)
    assert t2.exit_reason == "close" and t2.exit_time == C - pd.Timedelta(minutes=1) and t2.gross == pytest.approx(103 / 102 - 1)


def test_short_side_is_mirrored():
    b = minute_bars(rows={10: (98.1, 98.15, 97.5, 97.8)}, after=97.0)      # stop 98.2 not touched in the entry minute
    t = orb.simulate(b, O, C, orb.SHORT, atr_value=2.0, level=98.0)
    assert t.entry_px == 98.0 and t.exit_reason == "close" and t.gross == pytest.approx(1 - 97.0 / 98.0)


def test_half_day_exit_is_the_1259_bar():
    day = "2024-11-29"
    o, c = session_bounds(day)
    assert to_et(c).strftime("%H:%M") == "13:00"
    b = minute_bars(day, rows={10: (101.0, 102.5, 101.9, 102.3)}, after=104.0)
    t = orb.simulate(b, o, c, orb.LONG, atr_value=2.0, level=102.0)
    assert to_et(t.exit_time).strftime("%H:%M") == "12:59" and t.exit_px == 104.0


def test_halt_is_flagged():
    b = minute_bars(rows={10: (101.0, 102.5, 101.9, 102.3)}, after=103.0).drop(
        pd.date_range(O + pd.Timedelta(minutes=30), periods=10, freq="min"))
    assert orb.simulate(b, O, C, orb.LONG, atr_value=2.0, level=102.0).halted


def test_exposure_cap_binds_in_entry_order():
    t = pd.DataFrame({"symbol": ["A", "B", "C"], "entry_px": [100.0] * 3, "atr": [2.0] * 3,
                      "entry_time": [O + pd.Timedelta(minutes=m) for m in (12, 5, 30)],
                      "exit_time": [O + pd.Timedelta(minutes=m) for m in (40, 6, 50)]})
    w = orb.allocate(t, orb.ORBConfig())        # each wants 0.01*100/0.2 = 5x equity
    assert w.sum() == pytest.approx(1.0) and w[1] == pytest.approx(1.0) and w[0] == 0 and w[2] == 0
    w2 = orb.allocate(t, orb.ORBConfig(release_capacity=True))
    assert w2[1] == pytest.approx(1.0) and w2[0] == pytest.approx(1.0)        # B exited before A entered


def test_point_in_time_split_adjustment_ignores_later_splits():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    raw = pd.DataFrame({"open": [200, 200, 100, 100.0], "high": [202, 202, 101, 101.0], "low": [198, 198, 99, 99.0],
                        "close": [200, 200, 100, 100.0], "volume": [1e6, 1e6, 2e6, 2e6]}, index=idx)
    adj = raw.copy()
    adj.loc[idx[:2], ["open", "high", "low", "close"]] /= 2                # 2:1 split effective 2024-01-04
    before = orb.pit_adjust(raw, adj, "2024-01-03")                        # decision before the split
    assert before.close.iloc[-1] == 200 and before.volume.iloc[-1] == 1e6
    after = orb.pit_adjust(raw, adj, "2024-01-05")
    assert after.close.iloc[0] == pytest.approx(100) and after.volume.iloc[0] == pytest.approx(2e6)


def test_selection_filters_ranks_and_marks_abstentions():
    c = pd.DataFrame({"symbol": list("ABCDE"), "open": [10, 10, 4, 10, 10], "adv": [2e6] * 5, "atr": [1.0] * 5,
                      "rv": [5.0, 3.0, 9.0, 0.5, 2.0], "direction": [1, -1, 1, 1, 0], "corporate_action": [False] * 5,
                      "has_open_bar": [True] * 5})
    s = orb.select(c, orb.ORBConfig(top_n=3))
    assert s.symbol.tolist() == ["A", "B", "E"]                            # C under $5, D RV < 1
    assert s.action.tolist() == ["long", "abstain_short_long_only", "abstain_doji"]
    assert orb.select(c, orb.ORBConfig(top_n=3, long_only=False)).action.tolist()[1] == "short"
