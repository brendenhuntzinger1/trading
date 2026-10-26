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
    "ORB": Entry(Status.PENDING, "none", "pre-registered (prereg_orb); blocked on verifying SIP access; paper's own avg +0.08R ~ 2-5bp < 20bp cost"),
    "S3": Entry(Status.UNTESTABLE, "none", "needs multi-year 5-minute data"),
    # intraday crypto (INTRADAY_CRYPTO.md) - updated when results are final
    "C1": Entry(Status.REJECTED, "experimental", "E1-E6 fail; gross +0.03%/trade vs 1.06% round trip; holdout coins also fail. "
                "Paper run kept only to exercise the engine; not a candidate"),
    "C2": Entry(Status.REJECTED, "experimental", "E1-E7 fail (74 trades); gross +0.35%/trade vs 1.32% round trip. "
                "Paper run kept only to exercise the engine; not a candidate"),
    # crypto cross-sectional prediction (P1_PREREGISTRATION.md + Amendment 1; P1_REPORT.md)
    "P1a": Entry(Status.REJECTED, "none", "daily top-3 ranking of Coinbase coins, 5 configs: all negative net in development; "
                 "candidate M1 lost 0.21%/day in validation -> no qualifying candidate. Rank ICs -0.04..+0.06 vs ~0.10 needed. "
                 "PBO 0.43"),
    "P1b": Entry(Status.REJECTED, "none", "weekly top-3 ranking, 3 configs: no model beat momentum in development -> no candidate; "
                 "low power (122 dev weeks). PBO 0.54"),
}


def live_eligible(name: str) -> bool:
    e = REGISTRY.get(name)
    return bool(e and e.status is Status.PASSED and e.prospective_paper_accepted and e.owner_approval)


def label(name: str) -> str:
    e = REGISTRY.get(name)
    return "UNKNOWN - not allowed" if e is None else f"{e.status.value.upper()} / paper: {e.paper_run}"
