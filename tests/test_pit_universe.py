"""Point-in-time universe: eligibility at date d must depend only on candles before d."""
import numpy as np
import pandas as pd
import pytest

from tradelab.pit import crypto_universe as cu


def daily(n=120, start="2024-01-01", dv=20e6, gap=None):
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": dv}, index=idx)
    if gap is not None:
        df = df.drop(idx[gap[0]:gap[1]])
    df["dollar_volume"] = df.close * df.volume
    return df


def elig(df, product="ABC-USD", dates=None):
    dates = dates if dates is not None else pd.date_range(df.index.min(), df.index.max() + pd.Timedelta(days=1), freq="D")
    return cu.product_eligibility(product, df, dates).set_index("date")


def test_needs_60_days_history_and_volume_before_the_date():
    e = elig(daily())
    first = e.index[e.eligible][0]
    assert (first - e.index[0]).days == 60
    assert e.loc[e.index[59], "reason"] == "history_lt_60d"


def test_future_data_cannot_change_past_eligibility():
    full = daily(200)
    a = elig(full)
    cut = full.iloc[:150]
    b = elig(cut, dates=a.index[:151])
    pd.testing.assert_series_equal(a.eligible.iloc[:151], b.eligible, check_names=False)
    shocked = full.copy()
    shocked.loc[shocked.index[150]:, "volume"] = 0.0                           # future volume collapse
    shocked["dollar_volume"] = shocked.close * shocked.volume
    c = elig(shocked)
    assert (c.eligible.iloc[:151] == a.eligible.iloc[:151]).all()


def test_volume_threshold_uses_prior_30_days_median():
    df = daily(120, dv=5e6)
    df.loc[df.index[100]:, "volume"] = 50e6
    df["dollar_volume"] = df.close * df.volume
    e = elig(df)
    d_switch = df.index[100]
    assert not e.loc[d_switch, "eligible"]                                     # day 100 itself not yet in the window
    assert e.loc[d_switch + pd.Timedelta(days=16), "eligible"]                 # median flips after > half the window


def test_not_trading_previous_day_is_ineligible():
    df = daily(120, gap=(80, 82))
    e = elig(df)
    assert e.loc[df.index[79] + pd.Timedelta(days=2), "reason"] == "not_trading_prev_day"


def test_stablecoins_and_wrapped_assets_excluded():
    for p in ("USDT-USD", "WBTC-USD", "CBETH-USD", "PAXG-USD", "JITOSOL-USD"):
        assert cu.excluded(p)
    assert not cu.excluded("BTC-USD")
    assert (elig(daily(), "WBTC-USD").reason == "excluded_asset").all()
