# Intraday research: combined report

> **Superseded in part (2026-10-26).** "S2-ETF inconclusive" below is out of date: the pre-registered out-of-universe replication (S2X) found no useful effect, and S2-ETF is now REJECTED. The current status of every strategy is in `STATUS.md` and `EVIDENCE_BOARD.md`.


Date: 2026-10-25. Paper mode only; no real orders exist or can be placed.
Details: `INTRADAY_HYPOTHESES.md` (pre-registration), `INTRADAY_STOCKS.md`, `INTRADAY_CRYPTO.md`,
`COSTS.md`, `DATA_LIMITS.md`, `docs/S1_TIMING.md`.

## Bottom line

**No strategy has demonstrated an advantage.** None passed the pre-registered evidence standard (E1–E7) on
untouched test data. One variant (S2 on ETFs) is inconclusive. Everything else is rejected or untestable with
the data available. **Nothing is eligible for live trading,** and this is enforced in code
(`tradelab/governance/status.py`, tested).

## Two separate questions

| Question | Answer | Evidence |
|---|---|---|
| Does the engine work? | **Yes, in paper and replay.** It scans, sizes, enters, manages stops, targets and time limits, flattens stock positions at the close, enforces risk limits and resumes after restarts. | 204 passing tests; engine replay reproduces the independent research trade lists exactly (below). |
| Does any strategy have an advantage? | **No.** | E1–E7 tables below. A working engine says nothing about edge. |

## Results by status

### Passed: none

### Inconclusive (not rejected, insufficient evidence). Paper run: EXPERIMENTAL, not live-eligible

| Strategy | Test trades | Gross / net per trade | E1 | E2 | E3 | E4 | E5 | E6 | E7 |
|---|---|---|---|---|---|---|---|---|---|
| S2 gap reversal, sector/index ETFs only (2021-01 → 2026-10) | 548 | +0.126% / +0.046% | FAIL (lower bound −0.053%) | FAIL (Sharpe 0.24) | FAIL | pass | pass (p = 0.045) | FAIL (DSR 0.00) | pass |

It breaks even at a **12.6 bp** round trip, against an assumed 8 bp; at a 10 bp opening spread, net is −0.004%.
Even at zero cost its Sharpe is 0.65. Its edge is smaller than the uncertainty in its own costs.

### Rejected

| Strategy | Market | Test trades | Gross / net per trade | Break-even round trip | Failed criteria | Main reason |
|---|---|---|---|---|---|---|
| S1 market intraday momentum | Stocks | 1,445 | +0.020% / −0.060% | 2.0 bp | E1–E6 | No gross edge; worse than random entries (placebo p = 0.99) |
| S1 long/short (labelled study) | Stocks | 1,445 | +0.034% / −0.046% | 3.4 bp | E1–E6 | Same |
| S2 gap reversal, S&P 100 + sector ETFs | Stocks | 5,732 | +0.062% / −0.018% | 6.2 bp | E1–E6 | Dev edge (+0.20%, 2000–2015) vanished in validation (−0.02%, 2016–2020). Survivorship and/or decay |
| C1 liquidation-cascade reversal (maker) | Crypto | 212 | +0.027% / −1.03% | 2.7 bp | E1–E6 | Gross rebound ≈ 0 against a 1.06% round trip; holdout coins also fail (342 trades, net −1.05%) |
| C2 crypto intraday momentum | Crypto | 74 | +0.35% / −0.97% | 35 bp | E1–E7 | Gross edge far below the 1.32% round trip; fires too rarely (74 < 100) |
| Daily phase-3 candidates (breakout, mean reversion, rotation, selectors, macro overlay) | Crypto daily | see RESEARCH.md | | | | Nothing beat a fixed allocation |

### Untestable with available data

| Strategy | Why |
|---|---|
| S3 opening-range breakout ("stocks in play") | Needs years of 1–5-minute bars. Yahoo serves 60 days. The 60-day look (−0.19%/trade) is exploratory and counts for nothing. |
| Any sub-minute or order-book strategy | No historical L2 data. Live recording started 2026-10-25 and is useful only after months. |

### Benchmarks (never candidates)
Fixed allocation and buy-and-hold (daily paper accounts).

## Multiple testing (E6), combined across everything tried

| Source | Configurations |
|---|---|
| Daily phase 1 exploration | 22 |
| Daily phase 3 research | 51 |
| Stock intraday (dev + labelled variants) | 11 |
| Crypto intraday (dev) | 7 |
| **Total** | **91** |

Deflated Sharpe at N = 91 is **0.00 for every intraday test configuration**, under both the observed trial
variance and the stock worker's development variance (`research/intraday/combined.json`). The best
probabilistic Sharpe vs zero is S2-ETF's 0.73, far from 0.95. The workers had assumed 96 and 98 trials; the
true count is lower, and the conclusion is unchanged.

## Engine vs independent research (cross-check)

| Strategy | Research trades | Engine matched | Matched returns | Notes |
|---|---|---|---|---|
| S1 | 1,445 | 1,445 (100%) | correlation 0.995 | Engine exits at the last trade (bar close), research at the official close (median 1.5 bp apart) |
| S2 stocks + ETFs | 5,732 | 5,732 (100%) | correlation 1.00 | After two defect fixes (below) |
| S2 ETF-only | 548 | 548 (100%) | identical | |
| C1 | 212 | 212 (100%) | correlation 0.976; exit reason agrees 99.1% | Engine manages exits on 5m bars, research on 1m |
| C2 | 74 | 74 (100%) | identical | |

### Every S2 discrepancy before the fix (was 99.6%)

| Trades | Cause | Defect? | Net P&L effect |
|---|---|---|---|
| 5 engine-only (GEV 2024-04-04; SNDK ×4 Feb–Mar 2025) | New listings had no 20-day dollar-volume history; the engine treated NaN as liquid | **Yes**: fixed, regression test | mean net −0.52% each |
| 18 research-only (2022–2023) | The setup ranked the top 5 gaps *before* eligibility; PLTR (< $10) took a slot, was then rejected, and crowded out the 5th eligible stock | **Yes**: eligibility now precedes ranking (S1 too), regression test | mean net −0.12% each |
| 3 research-only (2025) | Crowded out by the GEV/SNDK trades above | Consequence of the first defect | mean net +0.39% each |
| **Total impact on pre-fix engine** | | | **−0.03 bp per trade**: immaterial, but the defects were real and are fixed |

Other engine defects found by the cross-checks:
- S1 traded the Thanksgiving half-day, which has no 15:30 ET bar (fixed).
- Resting limit orders filled at a better gap-open price instead of the limit, which was optimistic (fixed).

None changed a research result. All were found **after** the test results were seen, and all are logged as
such in the registry.

## Costs (summary; full table and status in COSTS.md)

| Market | Per side, base | Round trip | Verified? |
|---|---|---|---|
| Crypto, Coinbase Advanced taker | 0.66% = 0.60% fee + 0.01% half-spread + 0.05% slippage | **1.32%** | Fee tier: **no**, and sources conflict (0.60%, 0.90% or 1.20% taker). Spread measured on BTC/ETH. |
| Crypto, maker in / taker out | 0.40% / 0.66% | 1.06% | Fee: no |
| Stocks, market in / MOC out | 5 bp / 3 bp (includes SEC 0.21 bp on sells, **verified**) | 8 bp | Spread and slippage: assumed |

**"0.66%" and "1.3%" are the same assumption,** per side vs round trip. Earlier text called 1.3% "fees"; it is
fees plus spread and slippage. Phase 1's 0.45% per side was wrong (Kraken's taker fee is 0.80%) and was
corrected in AUDIT.md.

**Sensitivity** (`research/intraday/cost_sensitivity.json`):
- Every rejected strategy stays rejected at **any** plausible cost.
- Crypto break-evens (3–35 bp round trip) sit far below even the cheapest maker round trip (~80 bp).
- S1's break-even is 2 bp. S2-stocks' is 6 bp.
- Only S2-ETF's break-even (12.6 bp) sits inside the plausible stock cost range, which is why it's inconclusive rather than rejected.

## Chronological record: what was seen before each change

Full table: `research/intraday/chronology.md` (generated from the append-only registry).

| UTC (2026-10-25) | Event | Seen before it |
|---|---|---|
| 21:23 | Intraday hypotheses S1–S3, C1–C2 pre-registered (doc hash 82411ebd…) | No intraday data analysed |
| 21:25 | **Amendment 1**: S2 entry corrected from MOO (look-ahead) to a marketable order after the open print, at higher cost | No S2 result (found while writing engine fill rules) |
| 21:41 | Stock configs frozen | Dev/validation only |
| 21:43 | Stock test attempt crashed (missing file) before printing anything; logged | Nothing |
| 21:44 | Stock test results (single run) | — |
| 21:49 | Crypto configs frozen (least-negative dev configs, by a rule fixed before dev results) | Dev/validation only |
| 21:52 | Crypto test results (single run) | — |
| 22:35 | Engine changes: S1 half-day skip; eligibility before ranking; NaN liquidity rejected | Stock test results (engine-only changes; research unchanged) |
| 22:39 | C1 holdout coins | Crypto test result |
| 22:44 | Engine changes: crypto alignment; limit fill at limit price | Crypto test results (engine-only) |

Nothing was re-tuned after a test result. No test was run twice.

## What remains unproven before any separately authorised live trial

Even the best candidate fails E1–E3 and E6. If a future strategy passes, it still needs:

1. at least 3 months of prospective paper trading with ≥ 60 trades, results inside the backtest's 90% interval; *(Forward-period rule reconciled 2026-10-26: STATUS.md §Rules.)*
2. fills measured against real quotes. The current paper runners simulate fills from bars, so they **cannot**
   validate execution; a broker paper API with real quotes, or tiny live orders, can;
3. your account's actual fee tier and broker rules confirmed;
4. no risk-limit incidents;
5. your written approval of the exact configuration hash.

## Paper runs now (all labelled EXPERIMENTAL)

| Run | Strategies | Purpose |
|---|---|---|
| Stocks intraday | S2-ETF (inconclusive) | Prospective evidence only |
| Crypto intraday | C1, C2 (rejected) | Exercise the engine's live path only; not candidates |
| Daily | baseline (inconclusive), breakout (rejected, shadow), fixed allocation and buy-and-hold (benchmarks) | Prospective comparison |

## Proposed next step (one experiment, not started)

**Test the opening-range breakout (S3) on US "stocks in play", with realistic spread and slippage, out of sample.**

- **Hypothesis.** On days when a liquid US stock trades unusually high volume in the first 5 minutes (relative
  volume ≥ 3× its 14-day average for that window, price > $10, 14-day ATR > $0.50), the direction of the first
  5-minute bar persists. Entry is at the second bar's open, in that direction (long-only first; short as a
  labelled study). The stop is at the far side of the first bar; the exit is a 10R target or the close. Size is
  1% risk; at most the top 20 by relative volume. These parameters follow a **secondary summary** of
  Zarattini & Aziz (SSRN 4416622); I have not read the paper itself. They must be checked against the paper
  and then frozen in a pre-registration before any data is seen.
- **Why it's the most useful next step.**
  1. It is the only pre-registered hypothesis not yet tested.
  2. Its reported gross edge (+0.13R per trade, with R about 1–2% for these stocks, so roughly 13–26 bp) is
     the only one in our list that could plausibly exceed an 8–20 bp stock round trip.
  3. The paper charged commission but **no spread and no slippage** and had **no out-of-sample period**.
     Those are exactly the two gaps this project tests for.
  4. An independent replication on index futures found the gross result reproduced and the net result
     indistinguishable from zero, so a clear negative is the most likely outcome. That would settle whether
     intraday US stock trading is worth pursuing at all, before more engine work.
  5. It needs **no purchase**: Alpaca's free plan reportedly has stock history from 2016.
- **Data required.**
  - 1-minute (or 5-minute) bars, 2016 → 2026, for all US common stocks.
  - Daily bars for ATR and relative volume.
  - The asset list **including delisted symbols** (point-in-time universe).
  - Ideally NBBO quotes at the open, to measure spreads instead of assuming them.
- **Providers.**
  - **Alpaca, free** (official docs: history since 2016; only the latest 15 minutes restricted; 200 calls/min).
    *Unverified:* whether history is IEX-only or full SIP, whether quotes are included, and whether delisted
    symbols are covered. These must be checked with a free account before pre-registration.
  - **Massive/Polygon:** $29–199/month (third-party sources; not verified; you said no purchases).
  - IEX-only data would understate volume and miss prints, so it would only be acceptable if verified to be SIP.
- **Costs.** Stocks, per side: commission $0 (secondary source), SEC 0.21 bp on sells (**verified**), TAF
  negligible, half-spread + slippage **measured from opening quotes if available**, otherwise assumed at
  10 bp base / 25 bp stress for in-play stocks.
- **Evaluation.** Same E1–E7 with N = 91 + new trials (≤ 6). Dev 2016–2020, validation 2021–2022, untouched
  test 2023–2026; placebo; stress costs; holdout split by exchange or sector.
  - **Early stop rule:** if dev gross per trade is below 2× the base round trip, stop before validation.
- **What I need from you.** A free Alpaca account and a **paper/data-only** API key (no funding, no live
  trading permission). Or tell me not to pursue intraday stocks.
