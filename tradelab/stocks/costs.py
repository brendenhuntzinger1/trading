"""Per-trade cost components for US stocks, kept SEPARATE (ORB Amendment 1, B2):

  measured   - quoted half-spread at entry and exit from SIP NBBO quotes (tradelab/stocks/spreads.py)
  assumed    - slippage beyond the touch (1 bp base, 5 bp stress per side), commission ($0 base; $0.0035/share
               secondary/stress)
  fees       - SEC fee on sells (0.21 bp from 2026-04-04, verified; $0 before per the pre-registration), FINRA TAF
               ($0.000166/share on sells, capped $8.30; sourced, not re-checked)

When no measured spread exists the whole per-side cost falls back to the pre-registered ASSUMPTION
(10 bp base / 25 bp stress per side) and the result is labelled "cost assumed, not measured"."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date

SEC_FEE_FROM = date(2026, 4, 4)
SEC_FEE = 0.21e-4
TAF_PER_SHARE = 0.000166
TAF_CAP = 8.30


@dataclass(frozen=True)
class CostModel:
    name: str = "base"
    slippage_per_side: float = 1e-4          # ASSUMED
    commission_per_share: float = 0.0        # ASSUMED ($0 Alpaca; $0.0035 secondary)
    assumed_per_side_if_unmeasured: float = 10e-4

    def as_dict(self) -> dict:
        return asdict(self)


BASE = CostModel()
STRESS = CostModel("stress", slippage_per_side=5e-4, commission_per_share=0.0035, assumed_per_side_if_unmeasured=25e-4)


def trade_costs(side: int, entry_px: float, exit_px: float, shares: float, day: date,
                half_spread_entry: float | None, half_spread_exit: float | None, model: CostModel = BASE) -> dict:
    """Costs as fractions of entry notional, by component. side = +1 long, -1 short."""
    notional = entry_px * shares
    sell_px = exit_px if side > 0 else entry_px                     # long sells at exit; short sells at entry
    sec = SEC_FEE * sell_px * shares / notional if day >= SEC_FEE_FROM else 0.0
    taf = min(TAF_PER_SHARE * shares, TAF_CAP) / notional if notional else 0.0
    commission = 2 * model.commission_per_share * shares / notional if notional else 0.0
    measured = half_spread_entry is not None and half_spread_exit is not None
    if measured:
        spread = half_spread_entry + half_spread_exit * exit_px / entry_px
        slippage = model.slippage_per_side * (1 + exit_px / entry_px)
        label = "measured spread + assumed slippage"
    else:
        spread, slippage = 0.0, model.assumed_per_side_if_unmeasured * (1 + exit_px / entry_px)
        label = "cost assumed, not measured"
    return {"spread_measured": spread if measured else None, "slippage_assumed": slippage, "fees": sec + taf,
            "commission": commission, "net_of_spread_only_cost": spread if measured else None,
            "total": spread + slippage + sec + taf + commission, "label": label, "model": model.name}
