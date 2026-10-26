"""Post-test add-on on FROZEN configurations (no tuning): stress for families the test phase did not
stress (gate, selectors), and the gate vs the ungated baseline it filters."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research"))
import study_strategies as S  # noqa: E402
from tradelab.research.engine import ExecModel, sleeves  # noqa: E402
from tradelab.research.gate import walk_forward_gate  # noqa: E402
from tradelab.research.metrics import bootstrap  # noqa: E402
from tradelab.research.registry import entries, record  # noqa: E402
from tradelab.strategies import trend  # noqa: E402

pre = {x["name"].split(":", 1)[1]: x["params"] for x in entries("preregistration") if x["name"].startswith("prereg3:")}
lab = S.Lab()
T = S.TEST
out = {}


def gated_run(cost, ex):
    p = pre["gate"]
    tg = {}
    for a, d in lab.dfs.items():
        appr, _ = walk_forward_gate(d, trend.trend_vote(d), trend.realized_vol(d), p["horizon"], 2 * cost.per_side,
                                    list(range(2020, 2027)), z=p["z"])
        tg[a] = (trend.BASELINE(d) * appr.fillna(0.0)).reindex(lab.close.index)
    return sleeves(lab.close, lab.fill, pd.DataFrame(tg).fillna(0.0), 1000, cost, ex)


out["gate"] = {"cost_1.25%": S.period_stats(S.rets(gated_run(S.STRESS, ExecModel())), None, None, *T)["CAGR"],
               "miss_20%": S.period_stats(S.rets(gated_run(S.REAL, ExecModel(miss_prob=0.2, seed=3))), None, None, *T)["CAGR"]}
for fam in ("selector_trailing", "selector_regime"):
    r, e, _ = lab.selector(fam, pre[fam], S.STRESS)
    out[fam] = {"cost_1.25%": S.period_stats(r, e, None, *T)["CAGR"]}
base = lab.baseline()
out["baseline"] = {"cost_1.25%": S.period_stats(S.rets(lab.baseline(S.STRESS)), None, None, *T)["CAGR"],
                   "miss_20%": S.period_stats(S.rets(lab.baseline(ex=ExecModel(miss_prob=0.2, seed=3))), None, None, *T)["CAGR"]}

g = gated_run(S.REAL, ExecModel())
R = {"gate": S.rets(g).loc[T[0]:T[1]], "baseline": S.rets(base).loc[T[0]:T[1]]}
sr = lambda a, k: a[:, k].mean() / a[:, k].std() * math.sqrt(365)
cg = lambda a, k: float(np.prod(1 + a[:, k]) ** (365 / len(a)) - 1)
bt = bootstrap(R, {"dSharpe_gate_minus_baseline": lambda a, c, b: sr(a, 0) - sr(a, 1),
                   "dCAGR_gate_minus_baseline": lambda a, c, b: cg(a, 0) - cg(a, 1)}, n_boot=2000)
out["gate_vs_baseline"] = {"gate": S.period_stats(S.rets(g), S.expo(g), g.trades, *T),
                           "baseline": S.period_stats(S.rets(base), S.expo(base), base.trades, *T),
                           "bootstrap": bt.round(4).to_dict()}
record("result", "test3_addon", {"configs": "frozen prereg3"}, f"{T[0]}..{T[1]}", "post-test stress add-on (no tuning)", metrics=out)
(S.OUT / "test_addon.json").write_text(json.dumps(out, indent=1, default=float))
print(json.dumps(out, indent=1, default=lambda x: round(float(x), 4)))
