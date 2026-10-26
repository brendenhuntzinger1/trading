"""Data-quality checks for the stock files: coverage, invalid rows, and whether the
hourly 15:30 bar's close matches the official daily close (split/adjustment basis)."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tradelab.intraday.research.stocks_data import DIR, load, universe  # noqa: E402

rows = []
for s in universe().yahoo:
    r = {"symbol": s}
    for kind in ("daily", "hourly", "m5"):
        f = DIR / kind / f"{s}.csv"
        if not f.exists():
            r[kind] = "missing"
            continue
        d = load(s, kind)
        r[kind] = f"{d.time_et.iloc[0][:10]}..{d.time_et.iloc[-1][:10]} ({len(d)})"
    if r.get("daily", "missing") != "missing" and r.get("hourly", "missing") != "missing":
        d, h = load(s, "daily"), load(s, "hourly")
        dc = d.set_index(d.time_et.str[:10]).close
        dc = dc[~dc.index.duplicated(keep='last')]
        hh = h[h.time_et.str[11:16] == "15:30"]
        last = hh.set_index(hh.time_et.str[:10]).close
        j = pd.concat([dc, last], axis=1, keys=["daily", "h1530"]).dropna()
        dev = (j.h1530 / j.daily - 1).abs()
        r["hourly_vs_daily_close_median_bp"] = round(float(dev.median() * 1e4), 2)
        r["hourly_vs_daily_close_days_gt_50bp"] = int((dev > 0.005).sum())
    rows.append(r)
df = pd.DataFrame(rows)
out = Path(__file__).resolve().parent / "out" / "data_check.csv"
df.to_csv(out, index=False)
print("symbols:", len(df), "missing daily:", (df.daily == "missing").sum(), "missing hourly:", (df.hourly == "missing").sum(),
      "missing m5:", (df.m5 == "missing").sum())
print("hourly vs daily close: median of medians (bp):", df.hourly_vs_daily_close_median_bp.median(),
      "symbols with >5 days off by >50bp:", (df.hourly_vs_daily_close_days_gt_50bp > 5).sum())
print(df.sort_values("hourly_vs_daily_close_days_gt_50bp", ascending=False).head(5).to_string())
