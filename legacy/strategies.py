"""Candidate strategies. Each takes OHLCV and returns a target position in [0, 1]."""
import numpy as np
import pandas as pd

def rsi(close, n):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def buy_hold(df):
    return pd.Series(1.0, index=df.index)

def above_sma(n):
    def f(df):
        return (df.close > df.close.rolling(n).mean()).astype(float)
    f.__name__ = f"above_sma{n}"
    return f

def sma_cross(fast, slow):
    def f(df):
        return (df.close.rolling(fast).mean() > df.close.rolling(slow).mean()).astype(float)
    f.__name__ = f"sma_cross_{fast}_{slow}"
    return f

def momentum(n):
    def f(df):
        return (df.close.pct_change(n) > 0).astype(float)
    f.__name__ = f"momentum_{n}"
    return f

def donchian(entry, exit_):
    def f(df):
        hi = df.high.rolling(entry).max().shift(1)
        lo = df.low.rolling(exit_).min().shift(1)
        pos, out = 0.0, []
        for c, h, l in zip(df.close, hi, lo):
            if pos == 0 and c > h:
                pos = 1.0
            elif pos == 1 and c < l:
                pos = 0.0
            out.append(pos)
        return pd.Series(out, index=df.index)
    f.__name__ = f"donchian_{entry}_{exit_}"
    return f

def trend_voltarget(n, target_vol, bars_per_year):
    """Above-SMA trend filter, sized so expected volatility ~= target_vol."""
    def f(df):
        trend = (df.close > df.close.rolling(n).mean()).astype(float)
        vol = df.close.pct_change().rolling(30).std() * np.sqrt(bars_per_year)
        size = (target_vol / vol).clip(upper=1)
        # rebalance only on meaningful size changes to limit churn
        size = (size / 0.25).round() * 0.25
        return trend * size
    f.__name__ = f"trend{n}_vol{int(target_vol*100)}"
    return f

def rsi2_reversion(trend_n, entry=10, exit_n=5):
    """Buy short-term dips inside an uptrend, sell on bounce."""
    def f(df):
        r = rsi(df.close, 2)
        trend = df.close > df.close.rolling(trend_n).mean()
        exit_ma = df.close.rolling(exit_n).mean()
        pos, out = 0.0, []
        for c, rv, t, ma in zip(df.close, r, trend, exit_ma):
            if pos == 0 and t and rv < entry:
                pos = 1.0
            elif pos == 1 and (c > ma or not t):
                pos = 0.0
            out.append(pos)
        return pd.Series(out, index=df.index)
    f.__name__ = f"rsi2_dip_trend{trend_n}"
    return f

def bollinger_reversion(n=20, k=2.0):
    def f(df):
        ma = df.close.rolling(n).mean()
        sd = df.close.rolling(n).std()
        pos, out = 0.0, []
        for c, m, s in zip(df.close, ma, sd):
            if pos == 0 and c < m - k * s:
                pos = 1.0
            elif pos == 1 and c > m:
                pos = 0.0
            out.append(pos)
        return pd.Series(out, index=df.index)
    f.__name__ = f"bollinger_{n}_{k}"
    return f

def ema_cross(fast, slow):
    def f(df):
        return (df.close.ewm(span=fast).mean() > df.close.ewm(span=slow).mean()).astype(float)
    f.__name__ = f"ema_cross_{fast}_{slow}"
    return f

DAILY = [
    buy_hold,
    above_sma(50), above_sma(100), above_sma(200),
    sma_cross(20, 100), sma_cross(50, 200),
    momentum(30), momentum(90),
    donchian(20, 10), donchian(55, 20),
    trend_voltarget(100, 0.40, 365), trend_voltarget(200, 0.40, 365),
    rsi2_reversion(200),
]

HOURLY = [  # classic "day trading" setups on 1h candles
    buy_hold,
    ema_cross(9, 21), ema_cross(20, 50),
    rsi2_reversion(200),
    bollinger_reversion(20, 2.0),
    donchian(24, 12),
    momentum(24),
]

TREND_VOTERS = [above_sma(50), above_sma(100), above_sma(200),
                donchian(20, 10), donchian(55, 20), momentum(30), momentum(90)]

def ensemble(target_vol=0.40, bars_per_year=365, step=0.25):
    """Average of all trend signals (no picking the winner), volatility-sized,
    rounded to `step` so small wiggles don't cause trades."""
    def f(df):
        vote = sum(v(df) for v in TREND_VOTERS) / len(TREND_VOTERS)
        vol = df.close.pct_change().rolling(30).std() * np.sqrt(bars_per_year)
        size = vote * (target_vol / vol).clip(upper=1)
        return (size / step).round() * step
    f.__name__ = f"ensemble_vol{int(target_vol*100)}"
    return f
