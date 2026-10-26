"""Corrections to analysis.py found on review (both are data-consistency issues, not new analyses):
1. S2 hourly-window checks mixed daily entry/exit prices with hourly bars; BNY's hourly series is a
   different security before 2026. Use hourly prices for every leg and require the hourly session
   open to agree with the daily open within 2% (the S1 validity rule).
2. C1 1-minute delays covered only the 43 signals with a cached 1m window; compare every delay on
   that same subset, and the 5-minute delays on all signals."""
import json
from datetime import timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from common import OUT, ROOT, boot_mean, fmt
from stocks import hourly as _hourly
from crypto import bars as _bars

hourly, bars = lru_cache(None)(_hourly), lru_cache(None)(_bars)
R = json.loads((OUT / "decision_quality.json").read_text())

# --- 1. S2 hourly window, consistent prices
t = pd.read_csv(OUT / "annotated_S2.csv", parse_dates=["entry_time", "exit_time"])
rows = []
for _, x in t[t.day >= "2023-11-27"].iterrows():
    h = hourly(x.symbol)
    o = pd.Timestamp(x.entry_time)
    if h is None or o not in h.index:
        continue
    day = h[(h.index >= o) & (h.index < o + timedelta(hours=7))]
    if len(day) < 2 or abs(day.open.iloc[0] / x.entry_px - 1) > 0.02:       # hourly vs official open must agree
        continue
    entry, first_close, last_close = day.open.iloc[0], day.close.iloc[0], day.close.iloc[-1]
    hold = last_close / entry - 1
    abandon = first_close < entry
    rule = (first_close / entry - 1 - 0.0002) if abandon else hold
    plus60 = last_close / day.open.iloc[1] - 1
    rows.append((x.day, hold, rule, abandon, plus60))
s = pd.DataFrame(rows, columns=["day", "hold", "rule", "abandon", "plus60"])
dropped = int((t.day >= "2023-11-27").sum() - len(s))
R["Q3_holding_vs_abandon_pct"]["S2_abandon_at_1030"] = {
    "n": len(s), "dropped_inconsistent_or_missing_hourly": dropped, "abandoned": int(s.abandon.sum()),
    "window": "2023-11-27 -> 2026-10-23 (inside the already-seen test period)",
    "hold_to_close_gross": fmt(boot_mean(s.hold, s.day)),
    "rule_minus_hold": fmt(boot_mean(s.rule - s.hold, s.day)),
    "hold_gross_of_trades_rule_would_abandon": fmt(boot_mean(s.hold[s.abandon], s.day[s.abandon]))}
R["decay_gross_pct"]["S2"] = {"n": len(s), "+0m (open)": fmt(boot_mean(s.hold, s.day)),
                              "+60m (10:30)": fmt(boot_mean(s.plus60, s.day)), "difference": fmt(boot_mean(s.plus60 - s.hold, s.day))}

# --- 2. C1 delays on matched samples
c1 = pd.read_csv(OUT / "annotated_C1.csv", parse_dates=["entry_time", "exit_time", "signal_time"])


def gross(x, dmin, need_m1):
    b = bars(x.symbol)
    st = x.signal_time + timedelta(minutes=dmin)
    end = x.signal_time + timedelta(hours=6)
    f = ROOT / "data/crypto_intraday/m1_cache" / f"{x.symbol}_{(x.signal_time - timedelta(hours=1)).strftime('%Y%m%dT%H%M')}.csv"
    if need_m1 or dmin % 5:
        if not f.exists():
            return np.nan
        m1 = pd.read_csv(f, index_col=0); m1.index = pd.to_datetime(m1.index, utc=True)
        if st not in m1.index:
            return np.nan
        px = m1.loc[st, "open"]
    else:
        if st not in b.index:
            return np.nan
        px = b.loc[st, "open"]
    path = b[(b.index >= st) & (b.index < end)]
    return path.close.iloc[-1] / px - 1 if len(path) else np.nan


sub = {d: np.array([gross(x, d, True) for _, x in c1.iterrows()]) for d in (0, 1, 2, 5, 10, 15)}
ok = np.all([np.isfinite(v) for v in sub.values()], axis=0)
full = {d: np.array([gross(x, d, False) for _, x in c1.iterrows()]) for d in (0, 5, 10, 15, 30, 60)}
okf = np.all([np.isfinite(v) for v in full.values()], axis=0)
R["decay_gross_pct"]["C1"] = {
    "all_signals_5m_resolution": {f"+{d}m": f"n={int(okf.sum())} " + fmt(boot_mean(v[okf], c1.day[okf])) for d, v in full.items()},
    "subset_with_1m_data": {f"+{d}m": f"n={int(ok.sum())} " + fmt(boot_mean(v[ok], c1.day[ok])) for d, v in sub.items()},
    "note": "1m cache exists only around test-period maker signals, so the subset is not representative of all signals"}
(OUT / "decision_quality.json").write_text(json.dumps(R, indent=1, default=str))
print(json.dumps({"S2_abandon": R["Q3_holding_vs_abandon_pct"]["S2_abandon_at_1030"], "decay": R["decay_gross_pct"]}, indent=1))
