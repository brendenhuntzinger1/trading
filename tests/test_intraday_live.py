from datetime import timedelta

import pandas as pd

from tradelab.intraday import live_crypto
from tradelab.intraday.costs import CRYPTO_TAKER
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.sessions import CryptoSessions
from tests.test_intraday_setups import crypto5


def setup():
    full = crypto5(n_days=50, crash_at=288 * 45 + 12 * 7)
    eng = Engine(IntradayLimits(market="crypto", max_weight=0.25), [], {"C1": CRYPTO_TAKER, "C2": CRYPTO_TAKER},
                 CryptoSessions(), 1000.0)
    return full, eng


def test_each_bar_processed_once_and_crash_traded():
    full, eng = setup()
    cut = full.index[288 * 45]                                   # live start: day 45 00:00
    frames = {"X": full[full.index < cut]}
    fetch = lambda sym, tf, s, e: full[(full.index >= pd.Timestamp(s)) & (full.index + pd.Timedelta(minutes=5) <= pd.Timestamp(e))]
    last = cut.to_pydatetime()
    seen = []
    orig = eng.process_bar
    eng.process_bar = lambda s, e, b, c: (seen.append(s), orig(s, e, b, c))
    for h in range(1, 20):                                       # 19 hourly polls
        now = (cut + pd.Timedelta(hours=h)).to_pydatetime()
        last = live_crypto.cycle(eng, frames, last, ["C1"], now, 900, fetch=fetch)
    assert len(seen) == len(set(seen)) == 19 * 12
    c1 = [d for d in eng.decisions if d.setup == "C1"]
    assert c1 and c1[0].outcome == "approved"                  # the crash reached the engine and was approved
    # whether the maker limit then fills depends on price trading through it within 15 minutes


def test_stale_feed_blocks_entries():
    full, eng = setup()
    frames = {"X": full.iloc[:-100]}
    fetch = lambda sym, tf, s, e: full.iloc[:-100]                # feed stopped updating
    now = (full.index[-1] + pd.Timedelta(minutes=5)).to_pydatetime()
    live_crypto.cycle(eng, frames, None, ["C1"], now, 900, fetch=fetch)
    assert eng.s.blocked and "min old" in eng.s.blocked
