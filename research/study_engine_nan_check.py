"""Quantify the engine's missing-candle valuation bug on the audit's universe test.
engine.simulate marks a held asset at 0 when its close is NaN (BCH has 4 missing days in Nov 2018).
Here the same test is re-run with gaps forward-filled (last known price)."""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from tradelab.data.candles import load
from tradelab.research.engine import CostModel, sleeves
from tradelab.research.metrics import summary
from tradelab.strategies import trend
REAL = CostModel(fee=0.006, half_spread=0.0001, slippage=0.0005)
uni = ["BTC-USD", "ETH-USD", "LTC-USD", "BCH-USD"]
dfs = {a: load(a, "1d") for a in uni}
close = pd.DataFrame({a: d.close for a, d in dfs.items()}).loc["2018-01-01":]
fill = pd.DataFrame({a: d.open for a, d in dfs.items()}).loc["2018-01-01":]
for label, c, f in [("as audited (NaN gaps)", close, fill),
                    ("gaps forward-filled", close.ffill(), fill.fillna(close.ffill()))]:
    tb = pd.DataFrame({a: trend.BASELINE(d) for a, d in dfs.items()}).reindex(c.index)
    b = summary(sleeves(c, f, tb, 1000, REAL)); h = summary(sleeves(c, f, pd.DataFrame(1.0, index=c.index, columns=uni), 1000, REAL))
    print(f"{label:24s} baseline CAGR {b['CAGR']:.3f} sharpe {b['sharpe']:.3f} maxDD {b['maxDD']:.3f} | "
          f"B&H CAGR {h['CAGR']:.3f} sharpe {h['sharpe']:.3f} maxDD {h['maxDD']:.3f} | PASS {b['sharpe'] > h['sharpe'] and b['maxDD'] > h['maxDD']}")
