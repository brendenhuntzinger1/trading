# Audit of the phase-1 trend bot (`ensemble_vol40`)

Date: 2026-10-25. Reproduce with `.venv/bin/python research/audit.py` (raw output: `research/out/audit.json`).
Baseline code is frozen in `legacy/` (hashes in `legacy/SHA256SUMS`); the reimplementation in
`tradelab/strategies/trend.py` is tested to give identical signals.

## Verdict

**Not validated.** The headline (~22% a year) is arithmetically correct under the phase-1 assumptions, but:

1. The fees assumed were too low for this account size.
2. The strategy and both assets were chosen after seeing the same data used to report the result.
3. On three coins the design never touched, it lost to simply holding the same average amount of the coin.

The strongest claim the evidence supports is: *on BTC/ETH 2018–2026 it cut drawdowns roughly in half
relative to buy-and-hold, and probably, but not conclusively, beat an equally-exposed passive position.*

## Reproduced facts

| Item | Result |
|---|---|
| Phase-1 code, phase-1 costs (0.45%/side) | $1,000 → $6,005, CAGR 22.5%, max DD −36.5% (exact match) |
| Independent unit/cash engine, same costs | $6,027, CAGR 22.6%, max DD −36.6% |
| Compounded (CAGR) vs arithmetic | CAGR 22.6% · mean daily × 365 = 23.4% · mean of calendar years = 28.8% |
| Same for buy-and-hold (shows why the distinction matters) | CAGR 18.6% · arithmetic 41.8% · mean of calendar years 67.4% |

"22% a year" means **compounded** growth. The average of yearly returns (28.8%) is not what an account
experiences.

## Findings

### Costs: understated by ~1.5–2x
- Phase 1 assumed 0.40% fee + 0.05% slippage, citing Kraken. Kraken Pro's current published lowest tier
  ($0+ volume or assets) is **0.40% maker / 0.80% taker**. Coinbase Advanced's lowest tier is
  reported as **0.40% maker / 0.60% taker** by secondary sources; its own page refused automated access, so confirm in-app.
- A $1,000 account stays in the lowest tier (30-day volume ≈ $1,000 × 12 turnover / 12 ≈ $1,000).

| Costs per side | CAGR | Sharpe | Max DD | Cost drag / yr |
|---|---|---|---|---|
| Phase-1 assumption 0.45% | 22.6% | 0.94 | −36.6% | 5.5% |
| **Coinbase taker 0.66%** (default from now on) | **19.8%** | **0.85** | **−38.1%** | **8.0%** |
| Kraken taker 0.86% | 17.2% | 0.76 | −39.6% | 10.3% |
| Stress 1.25% | 12.3% | 0.59 | −42.8% | 14.6% |
| Maker 0.40%, 20% of orders never fill | 22.3% | 0.93 | −36.3% | 4.3% |

Turnover is **12× capital per year**, and fees take 8% of capital a year at Coinbase taker rates. Limit (maker)
orders would help if fills hold up; that needs to be measured in paper trading, not assumed.

### Accounting
- Phase-1 `run()` reset fractional positions to target every bar without charging for it (free daily
  rebalancing). Impact here is small (22.5% vs 22.2% with drift modelled).
- Phase-1 "trades/yr 21.6" measured position change, not orders. Real order count: **~106 orders/yr**
  (two sleeves). With no rebalance band, fee drift alone creates ~400 dust orders/yr. Fixed with a 2% band.
- No spread or partial-fill model existed. At $10–$250 orders on BTC/ETH (spread ≈ 0.01 bp on Kraken today,
  measured), partial fills and impact are immaterial. That stops being true for small coins or larger size.

### Look-ahead and timestamps
- Signals use bar *t* close; fills at bar *t+1* open. Verified by tests: signals are identical when computed
  on truncated data, and shocking future prices doesn't change past signals.
- Coinbase candles are stamped at **start** time (UTC). Executing exactly at 00:00:00 is unrealistic, so
  fills were delayed using hourly data (2020+): +1h → 25.1%, +4h → 24.2%, +12h → 23.2% CAGR vs 24.6% at
  the open. **Not timing-sensitive**: a once-a-day scheduled job is adequate for this strategy.
- Phase-1 dropped the last candle blindly. That was correct for that download only because it ran mid-day.
  The new loader drops a bar only when its end time is after the download time.

### Data
- Daily BTC/ETH/SOL/LTC/ETC: no gaps, duplicates or invalid OHLC. BCH: 4 missing days.
- Hourly: real Coinbase outages (BTC 16 missing hours, longest 5h on 2023-03-04 and 2025-10-25;
  re-downloading returns the same holes). Not relevant to daily signals; relevant to any intraday work.
- Prices are Coinbase; phase 1 charged Kraken fees on Coinbase prices. Default venue is now Coinbase.

### Selection bias (the big one)
- **Asset survivorship:** BTC/ETH were picked in 2026 knowing they are the survivors. On the
  point-in-time Coinbase universe of Jan 2018 (BTC, ETH, LTC, BCH), the same strategy compounds at
  **12.8%**, not 22%.
- **Strategy selection:** the ensemble and the 40% volatility target were chosen after viewing 13 daily and
  7 hourly configurations on the same data. Counting 22 trials, the **deflated Sharpe ratio is 0.86**
  (below the conventional 0.95). The result is not significant after accounting for the search.
- **Pre-registered holdout** (written before running; see `research/registry.jsonl`):
  LTC, BCH, ETC → **FAIL on all three** (Sharpe below buy-and-hold). The registered rule used Sharpe, which
  flatters ultra-volatile buy-and-hold; the result stands regardless.
  Post-hoc check (labelled as such): against **holding the same average exposure** (~20%), the strategy
  **lost on CAGR, drawdown and Sharpe on all three coins**.

| Holdout coin | Strategy CAGR / max DD | Fixed ~20% holding CAGR / max DD |
|---|---|---|
| LTC | 3.2% / −67% | 7.3% / −40% |
| BCH | 0.3% / −48% | 5.2% / −37% |
| ETC | 7.7% / −40% | 8.5% / −25% |

### Benchmarks at comparable risk (BTC+ETH, Coinbase taker, 2018-01 → 2026-10)

| Strategy | CAGR | Vol | Sharpe | Max DD | Exposure | Orders/yr |
|---|---|---|---|---|---|---|
| Baseline `ensemble_vol40` | 19.8% | 25% | 0.85 | −38% | 33% | 106 |
| Buy & hold 100% | 18.6% | 70% | 0.60 | −88% | 100% | 0 |
| Buy & hold, same exposure (33%) | 11.7% | 24% | 0.59 | −47% | 33% | 68 |
| Buy & hold, same volatility (36%) | 12.6% | 25% | 0.59 | −50% | 36% | 72 |
| Above SMA-200 (simplest trend) | 22.5% | 52% | 0.66 | −72% | 53% | 14 |
| Ablation: volatility sizing only | 14.8% | 41% | 0.54 | −64% | 67% | 92 |
| Ablation: trend vote only | 21.7% | 43% | 0.67 | −60% | 50% | 117 |

The trend vote provides the return; volatility sizing provides the drawdown control. Neither alone matches
the combination on risk-adjusted terms *in sample*.

### Uncertainty (paired stationary block bootstrap, 2,000 resamples, mean block 20 days; 90% intervals)

| Statistic | 5th pct | Median | 95th pct | P(>0) |
|---|---|---|---|---|
| Baseline CAGR | 2.1% | 19.6% | 41.7% | 0.97 |
| Baseline Sharpe | 0.21 | 0.85 | 1.45 | 0.98 |
| Sharpe: baseline − buy & hold | −0.16 | +0.22 | +0.64 | 0.82 |
| CAGR: baseline − same-exposure holding | −3.3% | +7.9% | +21.8% | 0.87 |

Even in sample, the advantage over a passive position of equal risk is not statistically established.

### Behaviour by regime
- Calendar years: lost money in 2018 (−21%), 2022 (−25%), 2026 YTD (−7%); trailed buy-and-hold in every bull year.
- Protects in slow crashes (LUNA/3AC −1% vs −55%; May–Jul 2021 −3% vs −43%).
- **Does not** protect in sudden crashes (COVID −19%, worse than the same-exposure holding's −14%; FTX −10% vs −7%).
- Bleeds in quiet or sideways markets (Q3 2023 −12% vs −4%; 2019 H2 −12%).

## Assumptions not verified
- Coinbase fee tier (secondary sources); confirm in your account.
- Zero yield on idle cash; zero taxes. Every rebalance is a taxable event in the US (short-term gains),
  which could matter more than fees. This is not tax advice; ask a tax professional.
- Slippage 5 bp and half-spread 1 bp for $10–$250 orders on BTC/ETH.
- 2017 data used only to warm up indicators.

## What this means
- Do not treat 22% (or 19.8%) as an expected return. The out-of-sample evidence is negative.
- Keep `ensemble_vol40` as the **baseline to beat**, alongside a **fixed-allocation benchmark**
  (hold a constant fraction, rebalance on 2% drift), which won the holdout comparison and costs almost nothing to run.
- The only untouched test left is the future. Paper trading is now the primary validation.
