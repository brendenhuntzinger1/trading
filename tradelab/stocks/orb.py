"""5-minute opening-range breakout on Stocks in Play: the rules of ORB_PREREGISTRATION.md (with Amendment 1).

Pure functions on DataFrames; no network. Prices are RAW (unadjusted) intraday SIP prices, as in the paper. Daily
filters use point-in-time split adjustment: history is rescaled only for splits between that history and the
decision day, never with factors from later splits (that would leak future corporate actions).

Timing: the decision is at 09:35 ET from bars that started 09:30-09:34. Orders are active from the 09:35 bar.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

LONG, SHORT = 1, -1


@dataclass(frozen=True)
class ORBConfig:
    name: str = "primary"
    min_open: float = 5.0             # opening price > $5
    adv_days: int = 14
    min_adv: float = 1_000_000        # shares/day, previous 14 sessions
    atr_days: int = 14
    min_atr: float = 0.50             # dollars, previous 14 sessions, split-adjusted to the decision day
    rv_days: int = 14
    min_rv: float = 1.0               # relative opening-range volume
    top_n: int = 20
    or_minutes: int = 5
    stop_atr_frac: float = 0.10       # stop 10% of ATR14 from the executed entry
    risk_per_trade: float = 0.01      # lose 1% of equity at the stop
    max_gross: float = 1.0            # total gross exposure cap (paper allows 4x; ours 1x)
    long_only: bool = True            # primary; long/short is a labelled secondary study
    halt_gap_minutes: int = 5         # >= 5 consecutive missing minutes in a position = halt flag
    release_capacity: bool = False    # exposure of a closed position is NOT re-used the same day (conservative)

    def as_dict(self) -> dict:
        return asdict(self)


# Trial set (pre-registration §9: <= 6 configurations). Fixed before any ORB data was obtained.
CONFIGS = {
    "primary": ORBConfig(),
    "long_short": ORBConfig(name="long_short", long_only=False),        # labelled secondary; borrow not modelled
    "dev_rv2_top20": ORBConfig(name="dev_rv2_top20", min_rv=2.0),
    "dev_rv5_top20": ORBConfig(name="dev_rv5_top20", min_rv=5.0),
    "dev_rv1_top10": ORBConfig(name="dev_rv1_top10", top_n=10),
    "dev_rv2_top10": ORBConfig(name="dev_rv2_top10", min_rv=2.0, top_n=10),
}


# ------------------------------------------------------------------ daily ----
def pit_adjust(raw: pd.DataFrame, adjusted: pd.DataFrame, day) -> pd.DataFrame:
    """Daily bars before `day`, split-adjusted AS OF `day`.

    raw / adjusted: daily bars (index = session date) from Alpaca with adjustment=raw and adjustment=split.
    factor(d) = raw_close(d) / adjusted_close(d) changes only at splits; rescaling d's prices by
    factor(day) / factor(d) undoes every split after `day` and keeps those between d and `day`."""
    day = pd.Timestamp(day)
    r = raw[raw.index < day]
    if r.empty:
        return r
    fac = (raw.close / adjusted.close.reindex(raw.index))
    f_day = fac[fac.index <= day].iloc[-1] if (fac.index <= day).any() else fac.iloc[-1]
    scale = fac.reindex(r.index) / f_day                # price divisor: prices / scale ; volume * scale
    out = r.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = r[c] / scale
    out["volume"] = r["volume"] * scale
    return out


def atr(daily: pd.DataFrame, n: int) -> float:
    """Simple mean of the last n true ranges (needs n + 1 sessions)."""
    if len(daily) < n + 1:
        return float("nan")
    d = daily.iloc[-(n + 1):]
    pc = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1).iloc[1:]
    return float(tr.mean())


def adv(daily: pd.DataFrame, n: int) -> float:
    return float(daily.volume.iloc[-n:].mean()) if len(daily) >= n else float("nan")


def relative_volume(or_volume_today: float, or_volume_history: pd.Series, n: int) -> float:
    """RV = today's first-5-minute volume / mean first-5-minute volume of the previous n sessions."""
    h = or_volume_history.iloc[-n:]
    if len(h) < n or h.mean() <= 0:
        return float("nan")
    return float(or_volume_today / h.mean())


# ------------------------------------------------------------ opening range ----
@dataclass(frozen=True)
class OpeningRange:
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def direction(self) -> int:
        return LONG if self.close > self.open else SHORT if self.close < self.open else 0


def opening_range(bars: pd.DataFrame, session_open: pd.Timestamp, minutes: int = 5) -> OpeningRange | None:
    """From 1-minute bars starting in [open, open + minutes). None if there is no bar AT the open
    (pre-registration §5: no 09:30 SIP bar -> the stock-day is excluded)."""
    w = bars[(bars.index >= session_open) & (bars.index < session_open + pd.Timedelta(minutes=minutes))]
    if w.empty or w.index[0] != session_open:
        return None
    return OpeningRange(float(w.open.iloc[0]), float(w.high.max()), float(w.low.min()), float(w.close.iloc[-1]),
                        float(w.volume.sum()))


# ------------------------------------------------------------------ selection ----
def select(candidates: pd.DataFrame, cfg: ORBConfig) -> pd.DataFrame:
    """candidates: one row per stock with columns symbol, open, adv, atr, rv, direction, corporate_action, has_open_bar.
    Returns the top_n by RV after the filters, with `action` = 'long' | 'short' | abstention reason."""
    c = candidates
    ok = ((c.open > cfg.min_open) & (c.adv >= cfg.min_adv) & (c.atr > cfg.min_atr) & (c.rv >= cfg.min_rv)
          & ~c.corporate_action.astype(bool) & c.has_open_bar.astype(bool))
    s = c[ok].sort_values(["rv", "symbol"], ascending=[False, True]).head(cfg.top_n).copy()
    s["action"] = np.where(s.direction == 0, "abstain_doji",
                           np.where(s.direction > 0, "long",
                                    "abstain_short_long_only" if cfg.long_only else "short"))
    return s


# ---------------------------------------------------------------------- trade ----
@dataclass
class Trade:
    triggered: bool
    side: int
    entry_time: pd.Timestamp | None = None
    entry_px: float = float("nan")
    stop_px: float = float("nan")
    exit_time: pd.Timestamp | None = None
    exit_px: float = float("nan")
    exit_reason: str = ""
    gross: float = float("nan")          # signed return on entry notional
    r: float = float("nan")              # in units of R = stop distance
    mae: float = float("nan")
    mfe: float = float("nan")
    halted: bool = False
    close_from_earlier_bar: bool = False


def simulate(bars: pd.DataFrame, session_open: pd.Timestamp, session_close: pd.Timestamp, side: int, atr_value: float,
             entry: str = "stop", level: float | None = None, entry_minute: pd.Timestamp | None = None,
             use_stop: bool = True, stop_frac: float = 0.10, or_minutes: int = 5, halt_gap: int = 5) -> Trade:
    """One trade on regular-session 1-minute bars (index = bar start, UTC).

    entry='stop':   stop order at `level` (OR high long / OR low short) active from the 09:35 bar; triggers on the
                    first bar whose high > level (low < level); fill = max(level, bar open) (min for shorts), so a
                    gap through the level fills at the open.
    entry='market': at the open of the first bar at/after `entry_minute` (default 09:35).
    Stop: stop_frac x ATR from the executed price. In the entry minute, a touch of the stop counts as hit (stop
    first). Afterwards a bar opening beyond the stop fills at its open (gap through), else at the stop.
    Exit: the close of the last regular bar (15:59, or 12:59 on half-days)."""
    t0 = session_open + pd.Timedelta(minutes=or_minutes)
    b = bars[(bars.index >= t0) & (bars.index < session_close)]
    tr = Trade(False, side)
    if b.empty or not np.isfinite(atr_value) or atr_value <= 0:
        return tr
    o, h, lo, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    idx = b.index
    if entry == "stop":
        hit = np.flatnonzero(h > level) if side == LONG else np.flatnonzero(lo < level)
        if not len(hit):
            return tr
        k = int(hit[0])
        px = max(level, o[k]) if side == LONG else min(level, o[k])
    elif entry == "market":
        m = entry_minute if entry_minute is not None else t0
        pos = np.flatnonzero(idx >= m)
        if not len(pos):
            return tr
        k = int(pos[0])
        px = o[k]
    else:
        raise ValueError(entry)
    dist = stop_frac * atr_value
    stop = px - side * dist
    tr.triggered, tr.entry_time, tr.entry_px, tr.stop_px = True, idx[k], px, stop
    exit_px, exit_k, reason = None, None, "close"
    if use_stop:
        if (side == LONG and lo[k] <= stop) or (side == SHORT and h[k] >= stop):
            exit_px, exit_k, reason = stop, k, "stop_same_minute"
        else:
            for j in range(k + 1, len(b)):
                if side == LONG:
                    if o[j] <= stop:
                        exit_px, exit_k, reason = o[j], j, "stop_gap"
                    elif lo[j] <= stop:
                        exit_px, exit_k, reason = stop, j, "stop"
                else:
                    if o[j] >= stop:
                        exit_px, exit_k, reason = o[j], j, "stop_gap"
                    elif h[j] >= stop:
                        exit_px, exit_k, reason = stop, j, "stop"
                if exit_px is not None:
                    break
    if exit_px is None:
        exit_k = len(b) - 1
        exit_px = c[exit_k]
        tr.close_from_earlier_bar = idx[exit_k] != session_close - pd.Timedelta(minutes=1)
    span = idx[k:exit_k + 1]
    tr.halted = bool(len(span) > 1 and ((span[1:] - span[:-1]) / pd.Timedelta(minutes=1)).max() > halt_gap)
    tr.exit_time, tr.exit_px, tr.exit_reason = idx[exit_k], float(exit_px), reason
    tr.gross = side * (exit_px / px - 1)
    tr.r = side * (exit_px - px) / dist
    hh, ll = h[k:exit_k + 1].max(), lo[k:exit_k + 1].min()
    tr.mfe = (hh / px - 1) if side == LONG else (1 - ll / px)
    tr.mae = (ll / px - 1) if side == LONG else (1 - hh / px)
    return tr


# ------------------------------------------------------------------- sizing ----
def allocate(trades: pd.DataFrame, cfg: ORBConfig) -> pd.Series:
    """Weights (fraction of equity notional) for one day's triggered trades, in entry-time order.

    Risk sizing asks for risk_per_trade x entry / (stop_frac x ATR) of equity per position; the total gross
    exposure cap (1x) binds first in practice. With release_capacity=False an exited position's exposure is
    not re-used that day."""
    w = pd.Series(0.0, index=trades.index)
    if trades.empty:
        return w
    order = trades.sort_values(["entry_time", "symbol"]).index
    open_pos: list[tuple[pd.Timestamp, float]] = []
    used = 0.0
    for i in order:
        t = trades.at[i, "entry_time"]
        if cfg.release_capacity:
            used -= sum(x for e, x in open_pos if e <= t)
            open_pos = [(e, x) for e, x in open_pos if e > t]
        want = cfg.risk_per_trade * trades.at[i, "entry_px"] / (cfg.stop_atr_frac * trades.at[i, "atr"])
        take = max(0.0, min(want, cfg.max_gross - used))
        w[i] = take
        used += take
        open_pos.append((trades.at[i, "exit_time"], take))
    return w
