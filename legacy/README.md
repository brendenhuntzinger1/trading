# Crypto trading bot — phase 1: backtest

Coinbase public price data (BTC/ETH daily since 2017, SOL since mid-2021; hourly since 2020).
Long-only spot (US retail). Signals on bar close, filled at next bar's open.
Costs: Kraken Pro taker 0.40% + 0.05% slippage = 0.45% per side, unless noted.

## Files
- `fetch_data.py` — downloads candles into `data/`
- `backtest.py` — execution + stats (validated: buy-hold matches price exactly; a lookahead "cheat" shows up as absurd returns)
- `strategies.py` — all candidate strategies, incl. `ensemble`
- `run_all.py 1d|1h [start] [end]` — every strategy x asset x cost level
- `portfolio.py` — 50/50 BTC+ETH ensemble vs buy-and-hold

## Findings
1. **Hourly day trading loses.** All 6 classic setups (EMA cross, RSI(2), Bollinger,
   breakout, momentum) went to ~$0 after fees on BTC, ETH and SOL (2021-07 → now).
   Even with zero fees, almost none beat holding.
2. **Daily trend-following works modestly.** Results vary by coin and period, so
   picking the single best row would be overfitting.
3. **Ensemble (average of 7 trend signals, volatility-sized), 50/50 BTC+ETH, after fees:**

   | period    | strategy       | $1000 → | CAGR  | worst drop |
   |-----------|----------------|---------|-------|------------|
   | 2018–2026 | buy & hold     | $4,529  | 18.7% | −88%       |
   | 2018–2026 | ensemble_vol40 | $6,005  | 22.5% | −37%       |
   | 2018–2021 | buy & hold     | $4,119  | 42.4% | −88%       |
   | 2018–2021 | ensemble_vol40 | $3,637  | 38.1% | −31%       |
   | 2022–2026 | buy & hold     | $1,154  | 3.0%  | −69%       |
   | 2022–2026 | ensemble_vol40 | $1,648  | 10.9% | −28%       |

   It is similar to holding in bull runs and much better in crashes. About 2 trades a month per coin.
   Past results; no guarantee.

## Next (phase 2)
Paper-trade the ensemble daily on live prices for 1–3 months, then a small real
Kraken account (trade-only API key, no withdrawal permission, kill switch).
