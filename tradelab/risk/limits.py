"""Hard risk limits, loaded once from a TOML file and frozen.

Nothing downstream of this module (strategies, models, LLM output) can change
a limit at runtime: the dataclass is immutable, the engine takes no override
arguments, and the loaded file's hash is logged with every decision."""
from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class RiskLimits:
    # exposure
    max_position_weight: float = 0.50       # any single asset, fraction of equity
    max_gross_exposure: float = 1.00        # sum of long weights (no leverage)
    max_cluster_exposure: float = 0.80      # assets whose correlation > cluster_corr count together
    cluster_corr: float = 0.70
    # losses
    daily_loss_limit: float = 0.03          # vs start-of-UTC-day equity -> stop opening for the day
    max_drawdown_limit: float = 0.25        # vs peak equity -> stop opening until a human resets
    reduce_on_max_drawdown: float = 0.0     # 0 = off; else cut exposure to this fraction of current
    # activity
    max_orders_per_day: int = 12
    max_turnover_30d: float = 3.0           # traded notional / equity over 30 days
    max_open_orders: int = 4
    max_order_notional: float = 300.0
    min_order_notional: float = 1.0
    # market quality
    max_spread_bps: float = 20.0
    max_expected_slippage_bps: float = 50.0
    max_order_vs_depth: float = 0.10        # order <= 10% of book notional within depth_band_bps
    depth_band_bps: float = 25.0
    # circuit breakers
    stale_data_s: float = 120.0
    max_rejections_1h: int = 3
    abnormal_move_1h: float = 0.08          # |1h return| above this -> stop opening
    abnormal_vol_multiple: float = 3.0      # short-term vol vs 30d median
    recon_tolerance_frac: float = 0.005     # local vs exchange balance mismatch
    recon_tolerance_abs: float = 2.0        # quote currency
    # event flags (from tradelab.events) only block entries when research supports it
    block_entries_on_event_flags: bool = False

    @classmethod
    def load(cls, path: str | Path) -> tuple["RiskLimits", str]:
        raw = Path(path).read_bytes()
        data = tomllib.loads(raw.decode()).get("risk", {})
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown risk settings (typo?): {sorted(unknown)}")
        limits = cls(**data)
        limits.validate()
        return limits, hashlib.sha256(raw).hexdigest()[:12]

    def validate(self) -> None:
        if not 0 < self.max_position_weight <= self.max_gross_exposure <= 1.0:
            raise ValueError("need 0 < max_position_weight <= max_gross_exposure <= 1 (no leverage)")
        if not 0 < self.daily_loss_limit < 1 or not 0 < self.max_drawdown_limit < 1:
            raise ValueError("loss limits must be fractions in (0, 1)")
        if not 0 <= self.reduce_on_max_drawdown < 1:
            raise ValueError("reduce_on_max_drawdown must be in [0, 1)")
        if self.min_order_notional > self.max_order_notional:
            raise ValueError("min_order_notional > max_order_notional")
