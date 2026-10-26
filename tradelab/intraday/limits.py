"""Intraday risk limits: loaded from TOML, frozen, independent of setups."""
from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class IntradayLimits:
    market: str = "stocks"                  # stocks | crypto
    max_positions: int = 5
    max_weight: float = 0.20                # per position, fraction of equity
    max_gross: float = 1.00                 # no leverage
    risk_per_trade: float = 0.01            # equity lost if the stop is hit (risk-sized setups)
    daily_loss_limit: float = 0.02          # stop opening new positions for the rest of the day
    max_entries_per_day: int = 10
    one_position_per_symbol: bool = True
    allow_short: bool = False
    min_price: float = 10.0                 # stocks only
    min_dollar_volume: float = 50e6         # 20-day median, scanner filter
    no_entries_last_minutes: int = 15       # stocks: no new entries this close to the session end
    flatten_at_close: bool = True           # stocks: every position closes in the closing auction
    pdt_max_day_trades_5d: int = 0          # 0 = no limit; set 3 if the broker still enforces the old rule
    max_bar_age_s: float = 600.0            # live: newest bar older than this halts entries
    allowed_symbols: tuple[str, ...] = ()   # broker-supported universe; empty = any symbol given to the scanner

    @classmethod
    def load(cls, path: str | Path, section: str) -> tuple["IntradayLimits", str]:
        raw = Path(path).read_bytes()
        data = tomllib.loads(raw.decode()).get(section, {})
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown intraday risk settings: {sorted(unknown)}")
        if "allowed_symbols" in data:
            data["allowed_symbols"] = tuple(data["allowed_symbols"])
        lim = cls(**data)
        lim.validate()
        return lim, hashlib.sha256(raw).hexdigest()[:12]

    def validate(self):
        if not 0 < self.max_weight <= self.max_gross <= 1.0:
            raise ValueError("need 0 < max_weight <= max_gross <= 1 (no leverage)")
        if not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("risk_per_trade must be in (0, 5%]")
        if self.market not in ("stocks", "crypto"):
            raise ValueError("market must be stocks or crypto")
        if self.allow_short and self.market == "crypto":
            raise ValueError("crypto is spot-only: no shorting")
