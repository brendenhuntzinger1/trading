"""F2 event timing: the reaction session is the first session that OPENS after the headline; parsing of verdicts."""
import pandas as pd

from research.phase2 import f2_earnings_drift as f2

SESS = pd.DatetimeIndex(pd.to_datetime(["2021-07-26", "2021-07-27", "2021-07-28"]))


def test_reaction_session_timing():
    pre = pd.Timestamp("2021-07-27 11:00", tz="UTC")       # 07:00 ET, before the open -> same day
    post = pd.Timestamp("2021-07-27 20:05", tz="UTC")      # 16:05 ET, after the close -> next session
    mid = pd.Timestamp("2021-07-27 15:00", tz="UTC")       # 11:00 ET, during the session -> next session
    assert f2.reaction_session(pre, SESS) == pd.Timestamp("2021-07-27")
    assert f2.reaction_session(post, SESS) == pd.Timestamp("2021-07-28")
    assert f2.reaction_session(mid, SESS) == pd.Timestamp("2021-07-28")


def test_verdict_parsing():
    h = "Snap Q2 Adj. EPS $0.10 Beats $(0.01) Estimate, Sales $982.11M Beat $844.98M Estimate"
    assert f2.verdict(f2.EPS_RX.search(h).group(1)) == "beat"
    assert f2.verdict(f2.SALES_RX.search(h).group(2)) == "beat"
    h2 = "Foo Q1 EPS $0.20 Misses $0.25 Estimate, Sales $1.0B Beat $0.9B Estimate"
    assert f2.verdict(f2.EPS_RX.search(h2).group(1)) == "miss"
