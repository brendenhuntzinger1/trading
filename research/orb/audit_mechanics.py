"""Independent audit of ORB trade mechanics on a few development days (cache only; no rule changes follow).

Re-runs the harness on the given days, then recomputes every primary-rule trade from the raw 1-minute SIP bars
with separate, deliberately simple code:
  * first-candle direction from the 09:30-09:34 bars;
  * entry = first bar starting at or after 09:35 whose high (long) / low (short) crosses the opening-range
    level; fill = max(level, bar open) for longs, min(level, bar open) for shorts;
  * stop = entry -/+ 0.10 x ATR14, checked from the entry bar on (stop first if the entry bar also touches it);
    fill = min(stop, bar open) for longs after the entry bar;
  * exit = close of the last regular-session bar;
  * filters as known at 09:35: open > $5, ADV14 >= 1M, ATR14 > $0.50, RV >= 1.
Prints every mismatch. Usage: python research/orb/audit_mechanics.py 2020-01-02 2020-01-03 ...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.orb import study                                  # noqa: E402
from research.orb.data import AlpacaSource                      # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData                  # noqa: E402
from tradelab.stocks import orb                                 # noqa: E402
from tradelab.stocks.timeutil import session_bounds             # noqa: E402


class DaysSource:
    """Wraps the real source but limits the session list to the audited days."""

    def __init__(self, inner: AlpacaSource, days: list[str]):
        self.inner, self._days = inner, days

    def days(self, start, end):
        return self._days

    def __getattr__(self, name):
        return getattr(self.inner, name)


def recompute(b: pd.DataFrame, o: pd.Timestamp, side: int, level: float, atr: float, stop_frac: float = 0.10) -> dict:
    after = b[b.index >= o + pd.Timedelta(minutes=5)]
    for t, bar in after.iterrows():
        crossed = bar.high >= level if side > 0 else bar.low <= level
        if not crossed:
            continue
        entry = max(level, bar.open) if side > 0 else min(level, bar.open)
        stop = entry - side * stop_frac * atr
        rest = after[after.index >= t]
        for i, (t2, bar2) in enumerate(rest.iterrows()):
            hit = bar2.low <= stop if side > 0 else bar2.high >= stop
            if hit:
                px = stop if i == 0 else (min(stop, bar2.open) if side > 0 else max(stop, bar2.open))
                return {"entry_time": t, "entry_px": entry, "exit_px": px, "exit_reason": "stop"}
        return {"entry_time": t, "entry_px": entry, "exit_px": float(after.close.iloc[-1]), "exit_reason": "close"}
    return {}


def main(days: list[str]):
    src = AlpacaSource(AlpacaData.from_env(), *study.PERIODS["dev"])
    out = study.run_period(DaysSource(src, days), "dev", ["primary"], placebo_reps=10)
    rule = out["configs"]["primary"]["_frames"]["rule"]
    checked, problems = 0, []
    for r in rule.itertuples():
        o, _ = session_bounds(r.day)
        b = src.minute_bars([r.symbol], r.day)[r.symbol]
        orng = b[(b.index >= o) & (b.index < o + pd.Timedelta(minutes=5))]
        d = 1 if orng.close.iloc[-1] > orng.open.iloc[0] else (-1 if orng.close.iloc[-1] < orng.open.iloc[0] else 0)
        level = orng.high.max() if d > 0 else orng.low.min()
        exp = recompute(b, o, d, level, r.atr)
        c = src.candidates(r.day).set_index("symbol").loc[r.symbol]
        checked += 1
        issues = []
        if d != r.side:
            issues.append(f"direction {d} vs {r.side}")
        for k in ("entry_px", "exit_px"):
            if exp and abs(exp[k] - getattr(r, k)) > 1e-6 * max(1, exp[k]):
                issues.append(f"{k} {exp[k]:.4f} vs {getattr(r, k):.4f}")
        if exp and exp["exit_reason"] != ("stop" if str(r.exit_reason).startswith("stop") else r.exit_reason):
            issues.append(f"exit_reason {exp['exit_reason']} vs {r.exit_reason}")
        if pd.Timestamp(r.entry_time) < o + pd.Timedelta(minutes=5):
            issues.append("entry before 09:35")
        if not (c.open > 5 and c.adv >= 1e6 and c.atr > 0.5 and c.rv >= 1):
            issues.append(f"filters open={c.open} adv={c.adv:.0f} atr={c.atr:.2f} rv={c.rv:.2f}")
        if issues:
            problems.append({"day": r.day, "symbol": r.symbol, "issues": issues})
    print(json.dumps({"days": days, "rule_trades_checked": checked, "problems": problems,
                      "abstentions": out["configs"]["primary"]["rule"].get("abstention")}, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:] or ["2020-01-02", "2020-01-03", "2020-01-06"])
