"""Combined multiple-testing analysis across every configuration tried (daily phases 1-3, stock and crypto intraday)."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tradelab.research.metrics import deflated_sharpe, psr

TRIALS = {"daily phase 1 (exploration)": 22, "daily phase 3 (RESEARCH.md)": 51,
          "stock intraday (dev + variants)": 11, "crypto intraday (dev)": 7}
N = sum(TRIALS.values())
LISTS = {
    "S1 default": ("research/intraday/stocks/out/test_trades_S1_default_thr0.25_top5_all.csv", "session", "B"),
    "S1 long/short": ("research/intraday/stocks/out/test_trades_S1_longshort_thr0.25_top5_all.csv", "session", "B"),
    "S2 stocks+ETFs": ("research/intraday/stocks/out/test_trades_S2_default_thr1_top5_stocks+sector.csv", "session", "B"),
    "S2 ETF-only": ("research/intraday/stocks/out/test_trades_S2_etf_only_thr1_top5.csv", "session", "B"),
    "C1 maker": ("research/intraday/crypto/out/test_trades_C1_C1_k4_maker.csv", "entry_time_utc", "D"),
    "C2": ("research/intraday/crypto/out/test_trades_C2_C2_m1.5.csv", "entry_time_utc", "D"),
}


def daily(path, col, freq):
    t = pd.read_csv(ROOT / path)
    day = t[col].astype(str).str[:10]
    pnl = (t.size_weight * t.net_ret).groupby(day).sum()
    span = pd.date_range(day.min(), day.max(), freq=freq).strftime("%Y-%m-%d")
    return pnl.reindex(span, fill_value=0.0)


series = {k: daily(*v) for k, v in LISTS.items()}
srs = [s.mean() / s.std() for s in series.values()]
var_observed = float(np.var(srs))
out = {"trial_counts": TRIALS, "n_trials_total": N, "var_per_period_sr_used": {}, "strategies": {}}
for label, var in (("observed across these 6 test configs", var_observed), ("stock worker's dev-trial variance", 0.0278)):
    out["var_per_period_sr_used"][label] = var
for k, s in series.items():
    bpy = 252 if LISTS[k][2] == "B" else 365
    out["strategies"][k] = {
        "days": len(s), "annual_sharpe": round(s.mean() / s.std() * math.sqrt(bpy), 2),
        "PSR_vs_0": round(psr(s), 3),
        "DSR_observed_var": round(deflated_sharpe(s, N, var_observed), 3),
        "DSR_dev_var": round(deflated_sharpe(s, N, 0.0278), 3),
        "passes_E6 (DSR>=0.95)": bool(deflated_sharpe(s, N, var_observed) >= 0.95)}
(ROOT / "research/intraday/combined.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
