"""Strategies the service may run. Adding one here is a code change that goes
through review; the running service cannot add or modify strategies itself."""
from __future__ import annotations

import dataclasses
import hashlib
import inspect

from tradelab.strategies import trend
from tradelab.strategies.base import StrategySpec
from tradelab.strategies.breakout import breakout
from tradelab.strategies.fixed import fixed

# Same rule as RESEARCH.md fixed_33; account name kept from the first paper day.
FIXED_33 = dataclasses.replace(fixed(0.33), name="fixed_allocation")

# breakout_20_atr3_vol40: shadow challenger from RESEARCH.md (failed its holdout; paper only, for forward evidence)
STRATEGIES: dict[str, StrategySpec] = {s.name: s for s in [trend.BASELINE, FIXED_33, trend.BUY_HOLD, breakout(20, 3.0)]}


def version(spec: StrategySpec) -> str:
    """Code+params fingerprint recorded with every decision."""
    src = inspect.getsource(spec.signal) if spec.signal else ""
    mod = inspect.getsource(inspect.getmodule(spec.signal)) if spec.signal else ""
    wrapper = inspect.getsource(StrategySpec.__call__)       # the clip/fill applied to every signal
    return hashlib.sha256((src + mod + wrapper + repr(spec.params)).encode()).hexdigest()[:10]
