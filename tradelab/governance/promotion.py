"""Champion/challenger promotion with evidence thresholds fixed in advance.

The service may *evaluate* a challenger; only a human-reviewed change to
config/strategies.lock (a git commit, so it can be reverted) promotes one.
Nothing here writes that file."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from tradelab.research.metrics import stationary_bootstrap_idx

LOCK = Path(__file__).resolve().parents[2] / "config" / "strategies.lock"


@dataclass(frozen=True)
class Criteria:
    min_paper_days: int = 90                 # untouched, forward-only evidence
    min_prob_sharpe_better: float = 0.90     # paired block bootstrap
    max_drawdown_worse_by: float = 0.0       # challenger max DD must not be worse
    max_turnover_ratio: float = 1.5          # vs champion
    max_breaker_incidents: int = 0           # latched breakers during the trial


@dataclass
class Verdict:
    eligible: bool
    reasons: list[str]
    evidence: dict


def evaluate(champion: pd.Series, challenger: pd.Series, champ_turnover: float, chall_turnover: float,
             breaker_incidents: int, c: Criteria = Criteria(), n_boot: int = 2000, seed: int = 3) -> Verdict:
    df = pd.DataFrame({"a": champion, "b": challenger}).dropna()
    reasons, ev = [], {"days": len(df)}
    if len(df) < c.min_paper_days:
        reasons.append(f"only {len(df)} paper days (need {c.min_paper_days})")
    if len(df) >= 20:
        rng, a = np.random.default_rng(seed), df.to_numpy()
        better = 0
        for _ in range(n_boot):
            s = a[stationary_bootstrap_idx(len(a), 10, rng)]
            sr = s.mean(0) / s.std(0)
            better += sr[1] > sr[0]
        ev["prob_sharpe_better"] = better / n_boot
        if ev["prob_sharpe_better"] < c.min_prob_sharpe_better:
            reasons.append(f"P(Sharpe better)={ev['prob_sharpe_better']:.2f} < {c.min_prob_sharpe_better}")
    dd = lambda r: float(((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min())
    ev["maxdd_champion"], ev["maxdd_challenger"] = dd(df.a), dd(df.b)
    if ev["maxdd_challenger"] < ev["maxdd_champion"] - c.max_drawdown_worse_by:
        reasons.append("challenger drawdown worse than champion")
    if champ_turnover > 0 and chall_turnover / champ_turnover > c.max_turnover_ratio:
        reasons.append(f"turnover {chall_turnover / champ_turnover:.1f}x champion")
    if breaker_incidents > c.max_breaker_incidents:
        reasons.append(f"{breaker_incidents} latched breaker incidents")
    return Verdict(not reasons, reasons or ["meets all pre-set criteria; promotion still requires a human commit"], ev)


def read_lock() -> dict:
    return json.loads(LOCK.read_text())
