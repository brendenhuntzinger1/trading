"""50/50 BTC+ETH, each half run independently (no rebalancing between them)."""
import pandas as pd
from backtest import load, run, stats
from strategies import buy_hold, ensemble

def portfolio(strategy, cost, start, end=None):
    eqs, tos = [], []
    for p in ["BTC-USD", "ETH-USD"]:
        df = load(p, "1d")
        sig = strategy(df)
        d = df.loc[start:end]
        net, to = run(d, sig.loc[d.index], cost)
        eqs.append((1 + net).cumprod() * 0.5)
        tos.append(to * 0.5)
    eq = sum(eqs)
    net = eq.pct_change().fillna(eq.iloc[0] - 1)
    return stats(net, sum(tos) * 2, 365)  # trades/yr counted per sleeve

if __name__ == "__main__":
    rows = []
    for label, (s, e) in {"2018-2026": ("2018-01-01", None), "2018-2021": ("2018-01-01", "2021-12-31"),
                          "2022-2026": ("2022-01-01", None)}.items():
        for strat in [buy_hold, ensemble(0.40), ensemble(0.30)]:
            rows.append({"period": label, "strategy": strat.__name__, **portfolio(strat, 0.0045, s, e)})
    print(pd.DataFrame(rows).to_string(index=False))
