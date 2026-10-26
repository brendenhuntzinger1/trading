"""S1: market intraday momentum (INTRADAY_HYPOTHESES.md).

For session t and symbol i:
  r = close of the 09:30-10:30 ET hourly bar / official close of session t-1 - 1
At 15:30 ET (start of the last hourly bar), long-only: candidates with r >= threshold,
take the `top` largest r (the doc caps positions at 5; ranking by signal strength is
the tie-break when more qualify). Enter at the 15:30 bar's open with a market order
(intraday cost), exit at the official close (MOC cost). Equal weight 1/top, max 20%.
Long/short variant: trade the sign of r when |r| >= threshold, ranked by |r|.
Half days (no 15:30 bar) are skipped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stocks_common import et_to_utc, net_return
from .stocks_data import load

COSTS = {"base": (0.0005, 0.0003), "stress": (0.0015, 0.0009)}   # (entry intraday market, exit MOC)


def hourly_panel(syms: list[str], daily_close: pd.DataFrame, daily_open: pd.DataFrame | None = None,
                 max_open_mismatch: float = 0.02) -> dict[str, pd.DataFrame]:
    """Per session: price at 10:30 (close of the 09:30 bar), open of the 15:30 bar,
    close of the 15:30 bar (for alignment checks), previous official close.
    Sessions whose hourly 09:30 open differs from the official daily open by more
    than `max_open_mismatch` are blanked: the hourly and daily files then describe
    different securities (e.g. a reused ticker). Known at the open, so not look-ahead."""
    p1030, o1530, c1530, o930 = {}, {}, {}, {}
    for s in syms:
        try:
            h = load(s, "hourly")
        except FileNotFoundError:          # e.g. GEV: Yahoo refuses the 730-day range for a 2024 listing
            continue
        h["session"] = pd.to_datetime(h.time_et.str[:10])
        h["hhmm"] = h.time_et.str[11:16]
        p1030[s] = h[h.hhmm == "09:30"].set_index("session").close
        o930[s] = h[h.hhmm == "09:30"].set_index("session").open
        o1530[s] = h[h.hhmm == "15:30"].set_index("session").open
        c1530[s] = h[h.hhmm == "15:30"].set_index("session").close
    f = lambda d: pd.DataFrame({k: v[~v.index.duplicated(keep="last")] for k, v in d.items()}).sort_index()
    p1030, o1530, c1530, o930 = f(p1030), f(o1530), f(c1530), f(o930)
    sessions = p1030.index
    blanked = 0
    if daily_open is not None:
        do = daily_open.reindex(index=sessions, columns=p1030.columns)
        bad = ((o930.reindex(sessions) / do - 1).abs() > max_open_mismatch)
        blanked = int(bad.sum().sum())
        p1030 = p1030.mask(bad)
    dc = daily_close.reindex(columns=p1030.columns)
    prev_close = dc.shift(1).reindex(sessions)
    close = dc.reindex(sessions)
    return {"p1030": p1030, "o1530": o1530.reindex(sessions), "c1530": c1530.reindex(sessions),
            "prev_close": prev_close, "close": close, "blanked_sessions": blanked}


def signal(hp: dict) -> pd.DataFrame:
    """Only data known by 10:30 ET of the session (and earlier sessions)."""
    return hp["p1030"] / hp["prev_close"] - 1


def trades(hp: dict, sessions: pd.DatetimeIndex, threshold: float = 0.0025, top: int = 5, cost: str = "base",
           universe: list[str] | None = None, long_short: bool = False) -> pd.DataFrame:
    r = signal(hp).reindex(sessions)
    if universe is not None:
        r = r[[s for s in r.columns if s in universe]]
    o, c = hp["o1530"], hp["close"]
    rows = []
    for d, row in r.iterrows():
        tradable = o.loc[d].notna() & c.loc[d].notna()
        x = row[tradable.reindex(row.index, fill_value=False)].dropna()
        if long_short:
            x = x[x.abs() >= threshold]
            x = x.reindex(x.abs().sort_values(ascending=False).index)
        else:
            x = x[x >= threshold].sort_values(ascending=False)
        for sym, v in x.iloc[:top].items():
            rows.append((d, sym, "long" if v > 0 else "short", v))
    t = pd.DataFrame(rows, columns=["session", "symbol", "side", "signal"])
    if t.empty:
        return t.assign(entry_px=[], exit_px=[], entry_time_utc=[], exit_time_utc=[], gross_ret=[], net_ret=[], cost=[], size_weight=[])
    t["entry_px"] = [o.at[d, s] for d, s in zip(t.session, t.symbol)]
    t["exit_px"] = [c.at[d, s] for d, s in zip(t.session, t.symbol)]
    t["entry_time_utc"] = et_to_utc(t.session, "15:30").values
    t["exit_time_utc"] = et_to_utc(t.session, "16:00").values
    c_in, c_out = COSTS[cost]
    t["gross_ret"], t["net_ret"] = net_return(t.entry_px, t.exit_px, t.side, c_in, c_out)
    t["cost"] = t.gross_ret - t.net_ret
    t["size_weight"] = min(1.0 / top, 0.20)
    return t


def placebo_totals(hp: dict, strat: pd.DataFrame, sessions: pd.DatetimeIndex, cost: str = "base", reps: int = 1000,
                   seed: int = 7, universe: list[str] | None = None) -> np.ndarray:
    """Same number of trades per trading day, same side and window (15:30 -> close),
    but on a random test session with random symbols (signal ignored)."""
    rng = np.random.default_rng(seed)
    o, c = hp["o1530"].reindex(sessions), hp["close"].reindex(sessions)
    if universe is not None:
        o, c = o[[s for s in o.columns if s in universe]], c[[s for s in c.columns if s in universe]]
    c_in, c_out = COSTS[cost]
    long_net = (c * (1 - c_out)) / (o * (1 + c_in)) - 1
    short_net = (o * (1 - c_in)) / (c * (1 + c_out)) - 1
    L, S = long_net.to_numpy(), short_net.to_numpy()
    valid = [np.flatnonzero(~np.isnan(L[i])) for i in range(len(sessions))]
    days = [i for i in range(len(sessions)) if len(valid[i])]
    per_day = strat.groupby("session").side.apply(list).tolist()
    w = strat.size_weight.iloc[0] if len(strat) else 0.0
    out = np.empty(reps)
    for r in range(reps):
        tot = 0.0
        for sides in per_day:
            i = days[rng.integers(len(days))]
            cols = rng.choice(valid[i], min(len(sides), len(valid[i])), replace=False)
            for side, j in zip(sides, cols):
                tot += w * (L[i, j] if side == "long" else S[i, j])
        out[r] = tot
    return out
