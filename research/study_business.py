"""Business-level view for a $1,000 account: test-period (2024-01-01..2026-10-24) returns after
trading costs, bootstrapped, minus operating costs. Run after `study_strategies.py test`."""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradelab.research.metrics import stationary_bootstrap_idx  # noqa: E402

CAPITAL = 1000.0
OPEX = {  # $/year
    "daily job on GitHub Actions": 0.0,
    "always-on VPS ($6/mo)": 72.0,
}
LLM_PER_YEAR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0   # optional news-classification cost


def main():
    R = pd.read_csv(ROOT / "research" / "out" / "test_returns.csv", index_col=0, parse_dates=True).dropna(how="all").fillna(0.0)
    rng = np.random.default_rng(11)
    a = R.to_numpy()
    boot = []
    for _ in range(2000):
        s = a[stationary_bootstrap_idx(len(a), 20, rng)]
        boot.append(np.prod(1 + s, axis=0) ** (365 / len(s)) - 1)
    boot = pd.DataFrame(boot, columns=R.columns)
    rows = {}
    for col in R.columns:
        g = boot[col] * CAPITAL
        row = {"gross $/yr p05": g.quantile(0.05), "gross $/yr median": g.median(), "gross $/yr p95": g.quantile(0.95),
               "P(gross>0)": (g > 0).mean()}
        for name, cost in OPEX.items():
            net = g - cost - LLM_PER_YEAR
            row[f"net median, {name}"] = net.median()
            row[f"P(net>0), {name}"] = (net > 0).mean()
        rows[col] = row
    df = pd.DataFrame(rows).T.round(2)
    pd.set_option("display.width", 250)
    print(f"Capital ${CAPITAL:,.0f}; LLM cost ${LLM_PER_YEAR:.0f}/yr; test period {R.index[0].date()}..{R.index[-1].date()} "
          f"({len(R)/365:.1f} yrs), stationary bootstrap (mean block 20 d), 2000 resamples.")
    print(df.to_string())
    df.to_csv(ROOT / "research" / "out" / f"business_llm{int(LLM_PER_YEAR)}.csv")


if __name__ == "__main__":
    main()
