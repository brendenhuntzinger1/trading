"""Per-side trading cost models, from INTRADAY_HYPOTHESES.md (incl. Amendment 1)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Costs:
    entry: float        # fraction of notional per side
    exit: float
    stop_slippage: float = 0.0   # extra adverse slippage when a stop is triggered

    def scaled(self, k: float) -> "Costs":
        return Costs(self.entry * k, self.exit * k, self.stop_slippage * k)


STOCK_AT_OPEN = Costs(entry=0.0005, exit=0.0003, stop_slippage=0.0005)   # marketable after open print; MOC exit
STOCK_INTRADAY = Costs(entry=0.0005, exit=0.0003, stop_slippage=0.0005)  # market in, MOC out
CRYPTO_TAKER = Costs(entry=0.0066, exit=0.0066, stop_slippage=0.0)
CRYPTO_MAKER_IN = Costs(entry=0.0040, exit=0.0066, stop_slippage=0.0)
