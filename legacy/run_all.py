import sys
import pandas as pd
from backtest import load, run, stats
from strategies import DAILY, HOURLY

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 500)

COSTS = {"no_fees": 0.0, "kraken_maker": 0.0030, "kraken_taker": 0.0045}  # fee + ~5bp slippage, per side

def table(tf, strategies, bpy, start=None, end=None):
    rows = []
    for p in ["BTC-USD", "ETH-USD", "SOL-USD"]:
        df = load(p, tf)
        sigs = {s.__name__: s(df) for s in strategies}  # signals use full history (no peeking: they are causal)
        d = df.loc[start:end]
        for name, sig in sigs.items():
            for cname, c in COSTS.items():
                net, to = run(d, sig.loc[d.index], c)
                rows.append({"asset": p, "strategy": name, "costs": cname, **stats(net, to, bpy)})
    return pd.DataFrame(rows)

if __name__ == "__main__":
    tf = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None
    strategies, bpy = (DAILY, 365) if tf == "1d" else (HOURLY, 8760)
    t = table(tf, strategies, bpy, start, end)
    t.to_csv(f"results_{tf}_{start or 'all'}_{end or 'now'}.csv", index=False)
    print(t[t.costs == "kraken_taker"].drop(columns="costs").to_string(index=False))
