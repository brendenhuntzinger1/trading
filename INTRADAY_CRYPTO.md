# Crypto intraday research: C1 and C2

Date: 2026-10-25. Hypotheses, rules, splits, costs and criteria E1–E7 are those pre-registered in
`INTRADAY_HYPOTHESES.md` (registry `prereg_intraday:C1`, `prereg_intraday:C2`). That file later gained an
amendment that concerns S2 only; its crypto section is unchanged. All results are backtests on
Coinbase spot data. **None of them is a trading result.**

## Verdict

| Hypothesis | Verdict | Why, in one line |
|---|---|---|
| **C1** liquidation-cascade reversal | **Rejected** | The rebound isn't there even before fees: +0.03% gross per trade (90% interval −0.11% to +0.17%) against a 1.06% round trip. The placebo did as well (p = 0.54). |
| **C2** intraday time-series momentum | **Rejected** | Gross +0.35% per trade (interval −0.37% to +1.19%), below the 1.32% round trip. Not distinguishable from random entries (p = 0.11), and only 74 test trades. |

Neither strategy meets the backtest evidence standard. Neither should trade with money, and paper trading
them would only measure the engine, not an edge. At Coinbase's lowest fee tier the round trip is about 1.3%
(taker) or 1.06% (maker entry, taker exit). Effects of this size cannot clear that.

## Reproduce

    .venv/bin/python -m tradelab.intraday.research.crypto_data           # download (resumable)
    .venv/bin/python -m tradelab.intraday.research.crypto_study dev
    .venv/bin/python -m tradelab.intraday.research.crypto_study validate
    .venv/bin/python -m tradelab.intraday.research.crypto_study test      # refuses to run twice
    .venv/bin/python -m tradelab.intraday.research.crypto_study holdout
    .venv/bin/python -m pytest -q tests/test_intraday_crypto_*.py         # 12 tests

Code: `tradelab/intraday/research/crypto_{data,rules,eval,study}.py`. Outputs: `research/intraday/crypto/out/`.

## Data

| Series | Source | Coverage | Gaps |
|---|---|---|---|
| BTC-USD, ETH-USD 1h and 5m | Coinbase Exchange public candles | 2019-12-01 → 2026-10-25 | 16 1h bars, ~360 5m bars (0.05%) |
| SOL-USD 1h and 5m | same | 2021-06-17 → 2026-10-25 | 15 1h bars, 274 5m bars |
| 1m bars | same, fetched per signal (15-minute maker window + 6h trade) | maker variants only | cached in `data/crypto_intraday/m1_cache/` |
| Holdout coins | same, 1h from 2023-11-01 plus 5m/1m windows around signals | 51 coins eligible on ≥1 test day | — |

- **Bar size.** I used 5m bars for history and 1m only where timing requires it (maker fills), instead of 1m
  for everything. Full 1m history would be ~2.9M bars per coin. Taker entries happen at a 5m bar open, and
  stops and targets are checked on 5m highs and lows with stop-first ambiguity. So 1m would change fills only
  inside a bar, where the stop-first rule is already the conservative choice.
- **Missing candles** (Coinbase omits intervals without trades, plus outages) are left as gaps. A return
  across a gap is not computed. An entry needs a bar within 15 minutes of the signal, otherwise there is no
  trade. Exits never fill on a missing bar.
- **Holdout liquidity filter (point-in-time).** A coin-day qualifies if the median dollar volume
  (volume × close) of the 30 *prior* completed days exceeds $20M. Stablecoins and wrapped/staked tokens are
  excluded.

## Dev trials (2020-01-01 → 2022-12-31), all logged in the registry

Selection rule, fixed before any result: the highest Sharpe of daily weighted net P&L, with ties going to
the pre-specified default.

| Config | Trades | Gross mean | Net mean | Win rate | Sharpe (daily) |
|---|---|---|---|---|---|
| C1 k=4 taker (pre-specified default) | 286 | +0.03% | −1.29% | 19% | −4.42 |
| C1 k=3 taker | 649 | −0.04% | −1.36% | 19% | −6.27 |
| **C1 k=4 maker** (selected) | 221 | +0.04% | −1.02% | 31% | −3.94 |
| C1 k=3 maker | 482 | +0.02% | −1.04% | 34% | −5.11 |
| C2 m=1.0 (pre-specified default) | 196 | +0.75% | −0.57% | 44% | −1.04 |
| C2 m=0.5 | 470 | +0.50% | −0.82% | 38% | −2.23 |
| **C2 m=1.5** (selected) | 88 | +0.47% | −0.85% | 41% | −0.92 |

Every dev configuration lost money after costs. The selected ones are simply the least negative.

## Validation (2023, confirmation only)

| Config | Trades | Gross mean | Net mean | Sharpe |
|---|---|---|---|---|
| C1 k=4 maker | 70 | +0.23% | −0.83% | −3.99 |
| C2 m=1.5 | 32 | +0.61% | −0.71% | −1.31 |

## Untouched test (2024-01-01 → 2026-10-24), run once after `intraday_crypto_frozen:*`

| Criterion | C1 k=4 maker | | C2 m=1.5 | |
|---|---|---|---|---|
| E1 mean net per trade; one-sided 95% lower bound > 0 | −1.03%; LB −1.17% | **FAIL** | −0.97%; LB −1.69% | **FAIL** |
| E2 Sharpe of daily net P&L ≥ 0.5 | −4.11 | **FAIL** | −1.17 | **FAIL** |
| E3 net mean > 0 at stress (+0.15%/side) | −1.33% | **FAIL** | −1.27% | **FAIL** |
| E4 positive in ≥ 2 of 3 sub-periods | −21.5%, −17.4%, −15.9% weighted P&L | **FAIL** | −3.0%, −5.6%, −9.4% | **FAIL** |
| E5 beats random entries, p < 0.05 (1,000 reps) | p = 0.54 | **FAIL** | p = 0.11 | **FAIL** |
| E6 deflated Sharpe ≥ 0.95 (98 trials) | 0.00 | **FAIL** | 0.00 | **FAIL** |
| E7 ≥ 100 test trades | 212 | pass | 74 | **FAIL** (the rule fires ~27 times a year; not loosened) |

- **Trades.** C1 had 212 (BTC 76, ETH 76, SOL 60; 107 targets, 105 stops). C2 had 74 (BTC 39, ETH 35; 48 time exits, 26 stops).
- **Win rates.** C1 18%, C2 31%. Every C1 target exit earns about +1% gross, which is less than its 1.06% cost.
- **E6 inputs.** n_trials = 73 (phases 1–3) + 7 (this study) + 18 (assumed for stocks) = 98. Trial SR variance
  0.0100 is per-day SR across the 7 dev configurations. Both Sharpes are negative, so the deflated Sharpe is 0
  whatever the count.

## Gross effect vs fees (the crux)

Diagnostic on the test trades with costs set to zero. The rules are unchanged, so this is not a new trial:

| | Gross mean per trade | 90% interval (block bootstrap) | Round-trip cost | Break-even cost per side |
|---|---|---|---|---|
| C1 | +0.03% | −0.11% to +0.17% | 1.06% (0.40% maker entry + 0.66% taker exit) | 0.01% |
| C2 | +0.35% | −0.37% to +1.19% | 1.32% (taker both ways) | 0.18% |

- **C1.** Even the optimistic end of the interval (+0.17%) is far below the 1.06% round trip. This meets
  C1's extra rejection rule ("gross rebound smaller than round-trip cost"). Under a ±1.5σ bracket, targets and
  stops are hit about equally often at about ±1%, so the rule is a coin flip that pays two fees.
- **C2.** The point estimate is positive in dev, validation and test (+0.47% / +0.61% / +0.35%). It is never
  significant (zero-cost placebo p = 0.11). Break-even needs ≤ 0.18% per side, a fee level Coinbase reserves for
  far higher monthly volume than a small account generates. Part of the gross figure could be ordinary upward drift while
  long BTC/ETH; the placebo, which is also long at the same times of day, does about as well (p = 0.11).

## Holdout coins (C1, frozen config k=4 maker)

Test period, point-in-time liquidity filter, signals counted only on days the coin qualified.

| Coins traded | Trades | Gross mean | Net mean (one-sided 95% LB) | Sharpe (daily) | Win rate |
|---|---|---|---|---|---|
| 31 of 51 eligible | 342 | +0.01% | −1.05% (−1.29%) | −2.37 | 42% |

The same picture appears on coins the rule was never developed on: zero gross rebound, a net loss equal to the fees.
C1 is rejected on holdout coins too.

## Limitations

- Fees are Coinbase Advanced's lowest tier as reported by secondary sources (0.60% taker / 0.40% maker).
  Your actual tier may differ. C2 would need roughly a 4× lower fee to break even at its point estimate.
- 5m bars: a stop and a target inside one bar are resolved stop-first (conservative). Stops fill at the stop
  or the bar open if it gapped through (no extra stop slippage beyond the 5 bp in the taker cost).
- Maker fills need a 1m low strictly below the limit; queue position isn't modelled beyond that, so maker
  fills are if anything optimistic.
- Target exits are charged taker (conservative). A resting maker target would save 0.26% on target exits.
  That still leaves C1's gross (+0.03%) far below cost.
- Sizing (1% risk at the stop, ≤ 25% per trade) affects E2/E4 only. E1/E3/E5 use per-trade returns.
- No order-book or derivatives inputs. No historical L2 data exists, and funding history covers ~1 year.

## Rules the engine must implement to reproduce the trade lists

Shared conventions:
- Bars are labelled by **start** time, UTC.
- Net = gross − entry_cost − exit_cost. Taker cost is 0.66% per side; maker entry is 0.40%.
- Stop fill = min(bar open, stop). Target fill = max(bar open, target).
- If one bar reaches both stop and target, the **stop** wins.
- Missing bars are skipped, never filled.

**C1 frozen: `C1_k4_maker`** (coins BTC-USD, ETH-USD, SOL-USD)
1. **Bars:** 1h for the signal, 1m for the maker fill and trade management (the taker variant uses 5m).
2. **σ:** standard deviation of the 720 contiguous 1h returns *before* the signal bar (at least 600 required).
   A return exists only if the previous 1h bar is exactly one hour earlier.
3. **Signal:** on the 1h bar starting at H−1h, r = close/prev close − 1. Fire if r ≤ −4σ. The signal is known at H.
4. **Entry (maker):** limit at signal close × (1 − 0.003), valid for 1m bars starting in [H, H+15m). It fills at
   the limit on the first 1m bar whose low is **strictly below** the limit. No fill means no trade.
5. **Exits:** stop = entry × (1 − 1.5σ), target = entry × (1 + 1.5σ).
   - Fill minute: if its low ≤ stop, exit at the stop.
   - Then walk 1m bars from fill+1m through fill+6h. Stop first, then target.
   - Otherwise, time exit at the close of the last 1m bar starting before fill+6h.
6. **One position per coin:** signals before the current trade's exit are ignored.
7. **Size:** weight = min(0.25, 0.01 / (1.5σ)) of equity. Daily P&L is weight × net, booked on the exit date (UTC).
   - Taker variant: entry at the open of the first 5m bar starting in [H, H+15m); walk 5m bars from the entry
     bar, including it.

**C2 frozen: `C2_m1.5`** (coins BTC-USD, ETH-USD; 5m bars)
1. **Reference price:** the open of the 00:00 UTC bar, or else the close of the last bar in [23:45, 00:00).
2. **p6:** the close of the last bar starting in [05:45, 06:00).
3. **σ_6h:** std of the 8,640 contiguous 5m returns ending at that bar (at least 7,000), × √72.
4. **Signal:** at 06:00, if p6/ref − 1 ≥ 1.5·σ_6h, buy at the open of the first bar starting in [06:00, 06:15) (taker).
5. **Stop:** entry × (1 − 2σ_6h), checked on bars starting in [entry, 23:55).
6. **Time exit:** at the open of the 23:55 bar (taker), or else the close of the last bar before it.
7. **Size:** min(0.25, 0.01 / (2σ_6h)).

## Trade lists

- `research/intraday/crypto/out/test_trades_C1_C1_k4_maker.csv` (212 trades)
- `research/intraday/crypto/out/test_trades_C2_C2_m1.5.csv` (74 trades)
- `research/intraday/crypto/out/validation_trades_C{1,2}.csv`, `holdout_trades_C1_C1_k4_maker.csv`

Columns:
- symbol, side, entry_time_utc, entry_px, exit_time_utc, exit_px, exit_reason
- gross_ret, cost, net_ret, size_weight
- extra: signal_time_utc, sigma, signal_ret, entry_cost, exit_cost

Other files:
- test metrics: `test.json`
- dev table: `dev_trials.csv`
- zero-cost diagnostic: `diagnostic_zero_cost.json`
