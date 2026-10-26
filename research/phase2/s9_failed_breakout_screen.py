"""Screen S9 (FAMILIES.md #9): failed breakouts of the prior-day high/low on SPY and QQQ -- a DESCRIPTIVE event
study, development window 2016-01-04..2022-12-30 only. Not a trading rule; no validation or final window is read.
Counted as one trial in the registry (conservative).

Event (point-in-time, 1-minute SIP bars, 10:00-15:00 ET):
    sweep-high: a bar's high exceeds the prior session's regular high (first breach of the day), and within the next
    30 minutes a bar closes back below that prior high -> event at that close ("failed breakout", expected to
    reverse DOWN according to stop-hunt narratives). sweep-low is the mirror image (expected to reverse UP).
Outcome: return in the expected reversal direction from the event close to +30 min, +60 min and the 15:59 close.
Control: the UNCONDITIONAL forward return of the same instrument from the same clock minute, averaged over all
development sessions, same sign convention -> excess = event - control. (The first version drew random minutes
from the event sessions themselves; those sessions are selected for a later breach, so minutes before the event
inherit look-ahead -- incident 22. Replaced before any conclusion was drawn.) Intervals: session-block bootstrap.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import evaluate as ev                               # noqa: E402
from research.phase2.f3_intraday_momentum import load_minutes             # noqa: E402
from tradelab.research.registry import record                             # noqa: E402

DEV = ("2016-01-04", "2022-12-30")
OUT = ROOT / "research" / "phase2" / "results" / "s9_screen.json"


def events(sym: str) -> pd.DataFrame:
    f = load_minutes(sym)
    f["day"], f["hm"] = f.index.strftime("%Y-%m-%d"), f.index.strftime("%H:%M")
    reg = f[(f.hm >= "09:30") & (f.hm < "16:00") & (f.day >= DEV[0]) & (f.day <= DEV[1])]
    rows, prev = [], None
    rng = np.random.default_rng(9)
    for day, g in reg.groupby("day", sort=True):
        if prev is not None and len(g) > 300:
            close = float(g.close.iloc[-1])
            win = g[(g.hm >= "10:00") & (g.hm < "15:00")]
            for kind, level, sign in (("sweep_high", prev[0], -1), ("sweep_low", prev[1], 1)):
                br = win[win.high > level] if kind == "sweep_high" else win[win.low < level]
                if br.empty:
                    continue
                t0 = br.index[0]
                after = g[(g.index > t0) & (g.index <= t0 + pd.Timedelta(minutes=30))]
                back = after[after.close < level] if kind == "sweep_high" else after[after.close > level]
                if back.empty:
                    continue
                te = back.index[0]
                px = float(back.close.iloc[0])
                def fwd(mins):
                    x = g[g.index <= te + pd.Timedelta(minutes=mins)]
                    return sign * (float(x.close.iloc[-1]) / px - 1)
                rows.append({"day": day, "symbol": sym, "kind": kind, "time": te.strftime("%H:%M"),
                             "r30": fwd(30), "r60": fwd(60), "r_close": sign * (close / px - 1),
                             "sign": sign})
        prev = (float(g.high.max()), float(g.low.min()))
    return pd.DataFrame(rows)


def tod_control(sym: str) -> pd.DataFrame:
    """Unconditional mean forward return (long) from each clock minute 10:00-15:00 over all development sessions."""
    f = load_minutes(sym)
    f["day"], f["hm"] = f.index.strftime("%Y-%m-%d"), f.index.strftime("%H:%M")
    reg = f[(f.hm >= "09:30") & (f.hm < "16:00") & (f.day >= DEV[0]) & (f.day <= DEV[1])]
    c = reg.pivot_table(index="day", columns="hm", values="close")
    c = c.loc[c.notna().sum(axis=1) > 300].ffill(axis=1)
    out = {}
    for h, mins in (("30", 30), ("60", 60)):
        later = c.shift(-mins, axis=1)
        out[h] = (later / c - 1).mean()
    out["_close"] = (c.iloc[:, [-1]].values / c - 1).mean()
    return pd.DataFrame(out)


def main() -> dict:
    parts = []
    for s in ("SPY", "QQQ"):
        e = events(s)
        ctl = tod_control(s)
        for h in ("30", "60", "_close"):
            e[f"c{h}"] = e.sign * e.time.map(ctl[h])
        parts.append(e)
    df = pd.concat(parts, ignore_index=True)
    out = {"window": DEV, "events": int(len(df)), "by": {}}
    for (kind), g in df.groupby("kind"):
        res = {"n": int(len(g)), "sessions": int(g.day.nunique())}
        for h in ("30", "60", "_close"):
            x = (g[f"r{h}"] - g[f"c{h}"]).groupby(pd.to_datetime(g.day)).mean()
            m, lo, hi = ev.mean_ci(x, 0.90)
            res[f"excess{h}_bp"] = {"mean": m * 1e4, "ci90": [lo * 1e4, hi * 1e4],
                                    "raw_mean_bp": float(g[f"r{h}"].mean() * 1e4)}
        res["by_year_excess_close_bp"] = {str(y): float((v.r_close - v.c_close).mean() * 1e4)
                                          for y, v in g.groupby(g.day.str[:4])}
        out["by"][kind] = res
    OUT.write_text(json.dumps(out, indent=1))
    record("result", "p2_S9_screen:failed_breakout", {"symbols": ["SPY", "QQQ"]}, "..".join(DEV),
           "descriptive screen of failed prior-day high/low breakouts (development window only)",
           metrics={"is_trial": True, "events": int(len(df)),
                    "excess_close_bp": {k: v["excess_close_bp"]["mean"] for k, v in out["by"].items()}})
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
