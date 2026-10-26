"""Unit-and-cash portfolio simulator.

Target weights are decided from information available at bar t's close and
executed at bar t+1's fill price (the open by default, or a delayed price).
Holdings are tracked in units, so weights drift between trades and every
rebalance, however small, is charged. No free daily rebalancing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    fee: float = 0.006          # exchange fee per side (Coinbase Advanced lowest tier, taker)
    half_spread: float = 0.0001
    slippage: float = 0.0005
    min_notional: float = 1.0   # exchange minimum order value, quote currency

    @property
    def per_side(self) -> float:
        return self.fee + self.half_spread + self.slippage


@dataclass(frozen=True)
class ExecModel:
    band: float = 0.02          # skip rebalances smaller than this weight change (exits always allowed)
    miss_prob: float = 0.0      # probability an order does not fill at all that bar
    seed: int = 0


@dataclass
class Result:
    equity: pd.Series
    weights: pd.DataFrame       # end-of-bar weights after drift
    trades: pd.DataFrame
    fees: float
    capital: float
    meta: dict = field(default_factory=dict)

    @property
    def returns(self) -> pd.Series:
        r = self.equity.pct_change()
        r.iloc[0] = self.equity.iloc[0] / self.capital - 1
        return r


def simulate(close: pd.DataFrame, fill: pd.DataFrame, target: pd.DataFrame, capital: float = 1000.0,
             cost: CostModel = CostModel(), ex: ExecModel = ExecModel()) -> Result:
    """close/fill/target: same index (bars) and columns (assets). target row t is
    the weight wanted after observing close t; it is traded at fill row t+1."""
    assets = list(close.columns)
    target = target.reindex(index=close.index, columns=assets).fillna(0.0).clip(lower=0.0)
    if (target.sum(axis=1) > 1 + 1e-9).any():
        raise ValueError("long-only, unlevered: target weights must sum to <= 1")
    rng = np.random.default_rng(ex.seed)
    units = np.zeros(len(assets))
    cash = capital
    eq, wts, trades, fees = [], [], [], 0.0
    c = close.ffill().to_numpy(float)        # a gap bar is marked at the last known price, never at 0
    f, w = fill.to_numpy(float), target.to_numpy(float)
    for i in range(len(close.index)):
        if i > 0:
            px = f[i]
            ok = ~np.isnan(px)
            value = cash + np.nansum(units * np.where(ok, px, c[i - 1]))
            cur_w = np.where(ok, units * px / value, 0.0)
            want = w[i - 1]
            for j in np.argsort(want - cur_w):           # sells first, so buys have cash
                if not ok[j] or abs(want[j] - cur_w[j]) <= ex.band and want[j] > 0:
                    continue
                if ex.miss_prob and rng.random() < ex.miss_prob:
                    continue
                notional = (want[j] - cur_w[j]) * value
                if notional > 0:                          # never spend cash we don't have
                    notional = min(notional, cash / (1 + cost.per_side))
                if abs(notional) < cost.min_notional:
                    continue
                q = notional / px[j]
                fee = abs(notional) * cost.per_side
                units[j] += q
                cash -= notional + fee
                fees += fee
                trades.append((close.index[i], assets[j], q, px[j], notional, fee))
        mark = np.where(np.isnan(c[i]), 0.0, c[i])
        value = cash + float(np.sum(units * mark))
        eq.append(value)
        wts.append(units * mark / value if value > 0 else units * 0)
    return Result(
        equity=pd.Series(eq, index=close.index, name="equity"),
        weights=pd.DataFrame(wts, index=close.index, columns=assets),
        trades=pd.DataFrame(trades, columns=["time", "asset", "qty", "price", "notional", "cost"]),
        fees=fees, capital=capital,
    )


def sleeves(close, fill, target, capital, cost=CostModel(), ex=ExecModel()) -> Result:
    """Equal independent sleeves per asset (no cross-asset rebalancing): the
    phase-1 portfolio convention, kept for like-for-like reproduction."""
    parts = [simulate(close[[a]], fill[[a]], target[[a]].clip(upper=1), capital / len(close.columns), cost, ex)
             for a in close.columns]
    eq = sum(p.equity for p in parts)
    w = pd.concat([p.weights * p.equity.values[:, None] for p in parts], axis=1).div(eq, axis=0)
    return Result(eq, w, pd.concat([p.trades for p in parts], ignore_index=True), sum(p.fees for p in parts), capital)
