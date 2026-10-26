"""Evidence status of every strategy, and the only path to live eligibility.

A strategy is live-eligible only if ALL hold: status == PASSED on its pre-registered
backtest standard, prospective paper evidence has been accepted, and the owner has
approved it in writing (recorded here by a reviewed commit). Inconclusive, pending,
rejected, untestable and benchmark strategies are never eligible.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    PASSED = "passed"                     # met the pre-registered backtest standard (still not 'profitable')
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"         # not rejected, insufficient evidence
    UNTESTABLE = "untestable"             # the data needed does not exist here
    PENDING = "pending"                   # result not yet available
    BENCHMARK = "benchmark"               # comparison only, never a candidate


@dataclass(frozen=True)
class Entry:
    status: Status
    paper_run: str                        # "experimental" | "benchmark" | "none"
    evidence: str
    prospective_paper_accepted: bool = False
    owner_approval: str | None = None     # e.g. "approved 2027-01-15 by <name>, config <hash>"


REGISTRY: dict[str, Entry] = {
    # daily (RESEARCH.md / AUDIT.md)
    "ensemble_vol40": Entry(Status.INCONCLUSIVE, "experimental", "in-sample only; lost to fixed allocation on holdout coins"),
    "fixed_allocation": Entry(Status.BENCHMARK, "benchmark", "passive benchmark"),
    "buy_hold": Entry(Status.BENCHMARK, "benchmark", "passive benchmark"),
    "breakout_20_atr3_vol40": Entry(Status.REJECTED, "experimental", "failed pre-registered 2024-2026 test; shadow only"),
    # intraday stocks (INTRADAY_STOCKS.md)
    "S1": Entry(Status.REJECTED, "none", "E1-E6 fail; worse than placebo"),
    "S2": Entry(Status.REJECTED, "none", "stock universe: E1-E6 fail; dev edge vanished in validation"),
    "S2_etf": Entry(Status.REJECTED, "experimental", "own test inconclusive (gross +12.6bp, CI 2.3-23.0); pre-registered "
                    "out-of-universe replication S2X on 29 new ETFs: gross -2.7bp, 95% upper 4.8bp < 8bp cost -> no useful effect. "
                    "Paper run kept only to exercise the engine; not a candidate"),
    "S2X": Entry(Status.REJECTED, "none", "29 untouched ETFs 2016-2026: gross -2.7bp [-8.9, 3.9]; placebo p 0.86"),
    "ORB": Entry(Status.REJECTED, "none", "pre-registered (prereg_orb + Amendments 1-5). Development 2020-21 on SIP data with measured "
                 "spreads: primary 4,048 trades, gross -9 bp, net -35 bp per trade; loses to placebo and to direction-only; sanity "
                 "gate failed (-0.22R vs paper +0.08R). Stopped after development (B16); validation and final windows unread"),
    "S3": Entry(Status.UNTESTABLE, "none", "needs multi-year 5-minute data"),
    # intraday crypto (INTRADAY_CRYPTO.md) - updated when results are final
    "C1": Entry(Status.REJECTED, "experimental", "E1-E6 fail; gross +0.03%/trade vs 1.06% round trip; holdout coins also fail. "
                "Paper run kept only to exercise the engine; not a candidate"),
    "C2": Entry(Status.REJECTED, "experimental", "E1-E7 fail (74 trades); gross +0.35%/trade vs 1.32% round trip. "
                "Paper run kept only to exercise the engine; not a candidate"),
    # crypto cross-sectional prediction (P1_PREREGISTRATION.md + Amendment 1; P1_REPORT.md)
    "P1a": Entry(Status.REJECTED, "none", "5 tested configs (B1, B2, ridge, logistic, GBT; daily top-3, Coinbase point-in-time "
                 "universe, assumed 1.32% round trip) all negative net in development; candidate M1 failed validation. "
                 "Claim limited to these configs, data and costs (P1_METHODS_AND_AUDIT.md). Frozen; reproducible, not re-selectable"),
    "P1b": Entry(Status.REJECTED, "none", "3 tested configs (B1, ridge, GBT; weekly top-3): no model beat momentum in development, "
                 "so no candidate; low power. Claim limited to these configs, data and costs. Frozen"),
}


def live_eligible(name: str) -> bool:
    e = REGISTRY.get(name)
    return bool(e and e.status is Status.PASSED and e.prospective_paper_accepted and e.owner_approval)


def label(name: str) -> str:
    e = REGISTRY.get(name)
    return "UNKNOWN - not allowed" if e is None else f"{e.status.value.upper()} / paper: {e.paper_run}"
