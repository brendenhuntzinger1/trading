"""C1/C2 rules as pre-registered in INTRADAY_HYPOTHESES.md (crypto section).

Conventions shared with the engine:
- Bar timestamps are bar START times (UTC). A bar starting at t is complete at t + bar length.
- A 1h signal on the bar starting at H-1h is known at H; entries happen at or after H.
- Net return per trade = gross - entry_cost - exit_cost (fractions of notional).
- Intra-bar: if a bar's low reaches the stop and its high reaches the target, the stop is assumed first.
- Stop fill = min(bar open, stop) (gaps through the stop fill at the open); target fill = max(bar open, target).
- Missing bars (Coinbase omits intervals with no trades / outages) are skipped, never filled.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

H1, M5, M1 = pd.Timedelta(hours=1), pd.Timedelta(minutes=5), pd.Timedelta(minutes=1)
TAKER = 0.0066          # 0.60% fee + 1 bp half-spread + 5 bp slippage
MAKER = 0.0040
STRESS_EXTRA = 0.0015


@dataclass(frozen=True)
class C1Config:
    k: float = 4.0
    maker: bool = False
    stop_sig: float = 1.5
    target_sig: float = 1.5
    max_hold: pd.Timedelta = pd.Timedelta(hours=6)
    sigma_bars: int = 720           # 30 days of 1h returns
    sigma_min: int = 600
    limit_offset: float = 0.003     # maker variant: limit 0.3% below signal price
    limit_valid: pd.Timedelta = pd.Timedelta(minutes=15)
    risk: float = 0.01
    max_weight: float = 0.25

    @property
    def name(self):
        return f"C1_k{self.k:g}_{'maker' if self.maker else 'taker'}"


@dataclass(frozen=True)
class C2Config:
    m: float = 1.0
    stop_sig: float = 2.0
    sigma_bars: int = 8640          # 30 days of 5m returns
    sigma_min: int = 7000
    risk: float = 0.01
    max_weight: float = 0.25

    @property
    def name(self):
        return f"C2_m{self.m:g}"


def contiguous_returns(df: pd.DataFrame, step: pd.Timedelta) -> pd.Series:
    """close/prev close - 1 only where the previous bar is exactly one step earlier."""
    prev_t = df.index.to_series().shift(1)
    r = df.close / df.close.shift(1) - 1
    return r.where(df.index.to_series() - prev_t == step)


def c1_signals(h1: pd.DataFrame, cfg: C1Config) -> pd.DataFrame:
    """Signals known at H = (start of 1h bar) + 1h. sigma uses the 720 returns BEFORE the signal bar."""
    r = contiguous_returns(h1, H1)
    sigma = r.rolling(cfg.sigma_bars, min_periods=cfg.sigma_min).std().shift(1)
    sig = (r <= -cfg.k * sigma) & sigma.notna()
    out = pd.DataFrame({"r": r[sig], "sigma": sigma[sig], "price": h1.close[sig]})
    out.index = out.index + H1          # time the signal becomes known
    out.index.name = "known_at"
    return out


def c2_signals(m5: pd.DataFrame, cfg: C2Config) -> pd.DataFrame:
    """One check per UTC day at 06:00. r = close(05:55 bar) / open(00:00 bar) - 1;
    sigma_6h = std of contiguous 5m returns over the prior 30 days (bars ending <= 06:00) x sqrt(72)."""
    r5 = contiguous_returns(m5, M5)
    sd = r5.rolling(cfg.sigma_bars, min_periods=cfg.sigma_min).std()
    rows = []
    days = pd.date_range(m5.index[0].normalize(), m5.index[-1].normalize(), freq="D")
    opens, closes = m5.open, m5.close
    for d in days:
        t0, t6 = d, d + pd.Timedelta(hours=6)
        ref = _price_at_open(opens, closes, t0)
        last = m5.index[(m5.index < t6) & (m5.index >= t6 - pd.Timedelta(minutes=15))]
        if ref is None or len(last) == 0:
            continue
        p6 = closes[last[-1]]
        s = sd.get(last[-1], np.nan)
        if not np.isfinite(s):
            continue
        sig6 = s * np.sqrt(72)
        r = p6 / ref - 1
        if r >= cfg.m * sig6:
            rows.append((t6, r, sig6, p6))
    out = pd.DataFrame(rows, columns=["known_at", "r", "sigma", "price"]).set_index("known_at")
    return out


def _price_at_open(opens, closes, t):
    if t in opens.index:
        return opens[t]
    before = closes.index[(closes.index < t) & (closes.index >= t - pd.Timedelta(minutes=15))]
    return closes[before[-1]] if len(before) else None


def first_bar_at_or_after(bars: pd.DataFrame, t: pd.Timestamp, within: pd.Timedelta):
    i = bars.index.searchsorted(t)
    if i < len(bars) and bars.index[i] - t <= within:
        return bars.index[i]
    return None


def walk_exit(bars: pd.DataFrame, entry_t: pd.Timestamp, entry_px: float, stop: float, target: float | None,
              until: pd.Timestamp, time_exit_at_open: pd.Timestamp | None = None):
    """Walk bars with start in [entry_t, until). Returns (exit_time, exit_px, reason) or None if no data.
    entry_t is the bar start containing the entry (entry at its open) or a minute bar after a maker fill."""
    i0, i1 = bars.index.searchsorted(entry_t), bars.index.searchsorted(until)
    o, h, l, c = (bars[x].to_numpy() for x in ("open", "high", "low", "close"))
    idx = bars.index
    for i in range(i0, i1):
        if l[i] <= stop:
            return idx[i], min(o[i], stop), "stop"
        if target is not None and h[i] >= target:
            return idx[i], max(o[i], target), "target"
    if time_exit_at_open is not None:
        j = bars.index.searchsorted(time_exit_at_open)
        if j < len(bars) and idx[j] - time_exit_at_open <= pd.Timedelta(minutes=15):
            return idx[j], o[j], "time"
    if i1 > i0:
        return idx[i1 - 1], c[i1 - 1], "time"
    return None


def c1_trades(symbol: str, h1: pd.DataFrame, m5: pd.DataFrame, cfg: C1Config, m1_windows=None,
              start=None, end=None) -> pd.DataFrame:
    """Simulate C1 for one coin. m1_windows: callable(symbol, start, end) -> 1m bars (maker variant)."""
    sigs = c1_signals(h1, cfg)
    if start is not None:
        sigs = sigs[(sigs.index >= start) & (sigs.index < end)]
    trades, busy_until = [], pd.Timestamp.min.tz_localize("UTC")
    for H, s in sigs.iterrows():
        if H < busy_until:
            continue                                     # one position per coin
        if cfg.maker:
            limit = s.price * (1 - cfg.limit_offset)
            w = m1_windows(symbol, H, H + cfg.limit_valid + cfg.max_hold + pd.Timedelta(minutes=10))
            win = w[(w.index >= H) & (w.index < H + cfg.limit_valid)]
            hit = win.index[win.low < limit]             # strictly through: a touch is not a fill
            if len(hit) == 0:
                continue
            fill_t = hit[0]
            entry_px, entry_cost, bars, walk_from = limit, MAKER, w, fill_t + M1
        else:
            t = first_bar_at_or_after(m5, H, pd.Timedelta(minutes=15))
            if t is None:
                continue
            fill_t, entry_px, entry_cost, bars, walk_from = t, m5.open[t], TAKER, m5, t
        stop = entry_px * (1 - cfg.stop_sig * s.sigma)
        target = entry_px * (1 + cfg.target_sig * s.sigma)
        until = fill_t + cfg.max_hold
        if cfg.maker and bars.low[fill_t] <= stop:       # fill minute: only the stop can be assumed (stop-first)
            ex = (fill_t, stop, "stop")
        else:
            ex = walk_exit(bars, walk_from, entry_px, stop, target, until)
        if ex is None:
            continue
        xt, xp, why = ex
        exit_time = xt + (M1 if bars is not m5 else M5) if why == "time" else xt
        gross = xp / entry_px - 1
        weight = min(cfg.max_weight, cfg.risk / (cfg.stop_sig * s.sigma))
        trades.append(dict(symbol=symbol, side="long", signal_time_utc=H, entry_time_utc=fill_t, entry_px=entry_px,
                           exit_time_utc=exit_time, exit_px=xp, exit_reason=why, gross_ret=gross,
                           entry_cost=entry_cost, exit_cost=TAKER, sigma=s.sigma, signal_ret=s.r, size_weight=weight))
        busy_until = exit_time
    return _finish(pd.DataFrame(trades))


def c2_trades(symbol: str, m5: pd.DataFrame, cfg: C2Config, start=None, end=None) -> pd.DataFrame:
    sigs = c2_signals(m5, cfg)
    if start is not None:
        sigs = sigs[(sigs.index >= start) & (sigs.index < end)]
    trades = []
    for H, s in sigs.iterrows():
        t = first_bar_at_or_after(m5, H, pd.Timedelta(minutes=15))
        if t is None:
            continue
        entry_px = m5.open[t]
        stop = entry_px * (1 - cfg.stop_sig * s.sigma)
        close_t = H.normalize() + pd.Timedelta(hours=23, minutes=55)
        ex = walk_exit(m5, t, entry_px, stop, None, close_t, time_exit_at_open=close_t)
        if ex is None:
            continue
        xt, xp, why = ex
        trades.append(dict(symbol=symbol, side="long", signal_time_utc=H, entry_time_utc=t, entry_px=entry_px,
                           exit_time_utc=xt, exit_px=xp, exit_reason=why, gross_ret=xp / entry_px - 1,
                           entry_cost=TAKER, exit_cost=TAKER, sigma=s.sigma, signal_ret=s.r,
                           size_weight=min(cfg.max_weight, cfg.risk / (cfg.stop_sig * s.sigma))))
    return _finish(pd.DataFrame(trades))


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "side", "signal_time_utc", "entry_time_utc", "entry_px", "exit_time_utc",
                                     "exit_px", "exit_reason", "gross_ret", "entry_cost", "exit_cost", "cost", "net_ret",
                                     "sigma", "signal_ret", "size_weight"])
    df["cost"] = df.entry_cost + df.exit_cost
    df["net_ret"] = df.gross_ret - df.cost
    return df


def restress(trades: pd.DataFrame, extra: float = STRESS_EXTRA) -> pd.DataFrame:
    t = trades.copy()
    t["cost"] = t.entry_cost + t.exit_cost + 2 * extra
    t["net_ret"] = t.gross_ret - t.cost
    return t
