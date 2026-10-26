"""Decompose the 'DSR 0.00 vs 0.95' result: what drives it, and how sensitive is it?"""
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research/intraday"))
from tradelab.research.metrics import psr
from combined import LISTS, daily

N_ = NormalDist()
E = 0.5772156649


def sr0(n, var):
    """Expected maximum per-period Sharpe among n unskilled trials (Bailey & Lopez de Prado 2014)."""
    if n <= 1:
        return 0.0
    return math.sqrt(var) * ((1 - E) * N_.inv_cdf(1 - 1 / n) + E * N_.inv_cdf(1 - 1 / (n * math.e)))


def needed_sr(r, n, var, target=0.95):
    """Smallest per-period SR (same T, skew, kurt) giving DSR >= target."""
    T = len(r); g3 = float(((r - r.mean()) ** 3).mean() / r.std() ** 3); g4 = float(((r - r.mean()) ** 4).mean() / r.std() ** 4)
    z = N_.inv_cdf(target)
    lo, hi = -1.0, 2.0
    for _ in range(80):
        sr = (lo + hi) / 2
        val = (sr - sr0(n, var)) * math.sqrt(T - 1) / math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
        lo, hi = (sr, hi) if val < z else (lo, sr)
    return hi


rows = []
for k, (path, col, freq) in LISTS.items():
    s = daily(path, col, freq)
    bpy = 252 if freq == "B" else 365
    sr = s.mean() / s.std()
    g3 = float(((s - s.mean()) ** 3).mean() / s.std() ** 3); g4 = float(((s - s.mean()) ** 4).mean() / s.std() ** 4)
    se_ann = math.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (len(s) - 1)) * math.sqrt(bpy)
    row = {"strategy": k, "T_days": len(s), "SR_annual_net": round(sr * math.sqrt(bpy), 2),
           "SR_annual_90ci": [round((sr * math.sqrt(bpy)) - 1.645 * se_ann, 2), round((sr * math.sqrt(bpy)) + 1.645 * se_ann, 2)],
           "skew": round(g3, 2), "kurtosis": round(g4, 1), "PSR_vs_0 (=DSR with N=1)": round(psr(s), 3)}
    for n in (6, 22, 91):
        for vname, v in (("var_low", 0.0066), ("var_dev", 0.0278)):
            row[f"DSR N={n} {vname}"] = round(psr(s, sr0(n, v)), 3)
    row["SR0_annual N=91 (var_low / var_dev)"] = [round(sr0(91, 0.0066) * math.sqrt(bpy), 2), round(sr0(91, 0.0278) * math.sqrt(bpy), 2)]
    row["annual SR needed for DSR>=0.95: N=1 / N=91 var_low"] = [round(needed_sr(s, 1, 0.0066) * math.sqrt(bpy), 2), round(needed_sr(s, 91, 0.0066) * math.sqrt(bpy), 2)]
    rows.append(row)
out = Path(__file__).parent / "dsr_audit.json"
out.write_text(json.dumps(rows, indent=1))
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(pd.DataFrame(rows).set_index("strategy").T.to_string())
