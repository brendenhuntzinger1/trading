"""Realized vs unrealized P&L from the fill journal (average-cost method)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Pnl:
    qty: float
    avg_cost: float
    realized: float          # closed trades, after their fees
    unrealized: float        # open position at mark, before exit costs
    fees: float
    est_exit_cost: float     # what closing now would cost at the taker fee


def pnl(fills: list[tuple[str, float, float, float]], mark: float, exit_fee: float = 0.006) -> Pnl:
    """fills: chronological (side, base, price, fee). Buy fees are capitalised
    into cost; sell fees reduce realized P&L."""
    qty = cost = realized = fees = 0.0
    for side, base, price, fee in fills:
        fees += fee
        if side == "buy":
            qty += base
            cost += base * price + fee
        else:
            avg = cost / qty if qty else 0.0
            realized += base * (price - avg) - fee
            cost -= avg * base
            qty -= base
    avg = cost / qty if qty > 1e-12 else 0.0
    return Pnl(qty, avg, realized, qty * (mark - avg), fees, qty * mark * exit_fee)
