"""Cross-asset relative strength rotation on a point-in-time universe."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MIN_HISTORY_DAYS = 365
MIN_MEDIAN_DOLLAR_VOL = 2_000_000


def eligible(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time eligibility, fixed before any testing: an asset may be held on day t only if
    it has >= 365 days of Coinbase history, a 30-day median dollar volume >= $2M, and a candle on t.
    Uses only data up to t, and includes assets that were later delisted."""
    age = close.notna().cumsum()
    dollar = (close * volume).rolling(30, min_periods=20).median()
    return (age >= MIN_HISTORY_DAYS) & (dollar >= MIN_MEDIAN_DOLLAR_VOL) & close.notna()


@dataclass(frozen=True)
class PanelStrategySpec:
    name: str
    hypothesis: str
    entry: str
    exit: str
    sizing: str
    holding_period: str
    failure_conditions: str
    params: dict = field(default_factory=dict)

    def weights(self, close: pd.DataFrame, volume: pd.DataFrame, market: pd.Series) -> pd.DataFrame:
        return rotation_weights(close, volume, market, **self.params)


def rotation_weights(close, volume, market, lookback=90, top_k=3, rebalance_days=28, market_filter=True,
                     vol_n=30) -> pd.DataFrame:
    """market: BTC-USD close, used for the optional market filter (BTC > 200-day SMA)."""
    elig = eligible(close, volume)
    ret = close / close.shift(lookback) - 1
    vol = close.pct_change(fill_method=None).rolling(vol_n).std()
    score = (ret / (vol * np.sqrt(lookback))).where(elig)          # risk-adjusted momentum
    mkt_ok = (market > market.rolling(200).mean()).reindex(close.index).fillna(False)
    w = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    current = pd.Series(0.0, index=close.columns)
    for i, t in enumerate(close.index):
        if i % rebalance_days == 0:
            current = pd.Series(0.0, index=close.columns)
            if not market_filter or mkt_ok.loc[t]:
                s = score.loc[t].dropna()
                s = s[s > 0].nlargest(top_k)                         # absolute momentum must be positive too
                if len(s):
                    current[s.index] = 1.0 / top_k                  # unfilled slots stay in cash
        # a holding that stops being eligible (delisting, illiquidity) is sold at the next bar
        current = current.where(elig.loc[t], 0.0)
        w.loc[t] = current
    return w


def rotation(lookback=90, top_k=3, rebalance_days=28, market_filter=True) -> PanelStrategySpec:
    return PanelStrategySpec(
        name=f"rotation_l{lookback}_k{top_k}_r{rebalance_days}_{'mf' if market_filter else 'nomf'}",
        hypothesis=("Cross-sectional momentum: coins with the strongest recent risk-adjusted returns keep "
                    "outperforming over the following weeks as attention and capital rotate into them. Absolute "
                    "momentum and an optional BTC trend filter move to cash in broad bear markets."),
        entry=(f"Every {rebalance_days} days, rank eligible coins by {lookback}-day return / volatility; buy the top "
               f"{top_k} with positive score{' while BTC > 200-day SMA' if market_filter else ''}."),
        exit="Next rebalance if no longer ranked; immediately if the coin loses eligibility.",
        sizing=f"1/{top_k} of capital per coin, never more than 100% in total.",
        holding_period=f"{rebalance_days} days per decision.",
        failure_conditions=("Momentum crashes (sharp leader reversals); small-coin delistings; spread and "
                            "slippage on less liquid coins larger than modelled."),
        params={"lookback": lookback, "top_k": top_k, "rebalance_days": rebalance_days, "market_filter": market_filter},
    )
