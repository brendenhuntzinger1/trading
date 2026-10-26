# Morning report, 2026-10-26 (overnight run)

> **DRAFT (04:00 UTC).** Sections A, C, D, F and G are filled in when the ORB development run finishes.

Written for the owner; it supersedes nothing in `STATUS.md`, which stays authoritative for status. Every
claim below links to a commit, a run, a file or a test. Paper only throughout: no live orders, purchases,
subscriptions or relaxed limits.

## A. Verdict
**ORB_VERDICT_PLACEHOLDER**

## B. Completed research (all outcomes, including failures)

| Study | Hypothesis | Configurations | Data | Result after costs | Status |
|---|---|---|---|---|---|
| P1a / P1b | Price/volume features rank liquid Coinbase coins well enough that the top 3 beat costs over a day or a week | 8 (B1 momentum, B2 reversal, ridge, logistic, GBT; weekly B1, ridge, GBT) | Coinbase point-in-time universe, 2021-03 → 2026-10 | Every configuration negative net in development. Rank IC −0.04…+0.06 against ~0.10 break-even for that construction. The daily candidate lost 0.21%/day in validation | **REJECTED** (`P1_REPORT.md`, `P1_METHODS_AND_AUDIT.md`); frozen by hash |
| ORB (stocks in play) | A large opening imbalance (relative volume ≥ 1) persists through the session; buying the 5-minute breakout in the first candle's direction captures part of it | ORB_CONFIGS_PLACEHOLDER | Alpaca SIP minute bars and NBBO quotes; universe = asset master + corporate-action tickers; development 2020–2021 | ORB_RESULT_PLACEHOLDER | ORB_STATUS_PLACEHOLDER |
| Earlier (S1, S2, S2-ETF, S2X, C1, C2, daily breakout) | Intraday momentum, gap reversal, crash rebound, time-of-day momentum, daily breakout | 92 in total | Yahoo stocks, Coinbase crypto | None cleared costs on untouched data | REJECTED (`EVIDENCE_BOARD.md`) |

**Data facts established tonight** (measured, not assumed):
- Consolidated (SIP) history works on the paper key: minute bars, NBBO quotes from 15 exchanges, trades.
  IEX alone carried 3.7% of SPY's SIP volume.
- **Measured quoted half-spread on in-play stocks** (30 stock-days, 2023): 09:35–10:30 median 4.0 bp
  (90th percentile 10.3 bp); 15:59 median 1.5 bp. Slippage beyond the touch is still an assumption.
- **The asset master is not survivorship-free.** It holds 12–37% of merger-delisted tickers per year.
  Corrected with corporate-action tickers from 2020 (ORB Amendment 4).
- **Alpaca crypto paper round trip** ($10 BTC, n = 1): fee 0.25% per side, buy 4.7 bp and sell 1.1 bp from
  mid. A rough all-in round trip of ~0.56%, against the 1.32% assumed for Coinbase retail. One sample of
  Alpaca's *simulated* fills, so indicative only.

## C. Best remaining opportunities (ranked; none is a profitable strategy)
OPPORTUNITIES_PLACEHOLDER

## D. Decision-quality findings
DECISION_PLACEHOLDER

## E. Learning record
16 incidents are in `INCIDENTS.md` / `research/incidents.jsonl`, each categorised, with its root cause,
correction and prevention.
- **Tonight's software defects:**
  - missing dependency pins;
  - an unsafe state restore;
  - silent push failures;
  - duplicate equity marks that double-counted operating cost;
  - SQLite WAL loss on save;
  - a save that deleted later steps' files (it failed an Actions run);
  - a broker allow-list prefix hole;
  - transport errors killing a long download.
- **Tonight's data failures:**
  - the asset master's invalid symbols;
  - the survivorship gap.
- **Tonight's process errors:**
  - a commit pushed with a failing test;
  - P1's final window read without a candidate;
  - a "refuse second run" rule mistaken for overfitting protection;
  - the owner's email sent once to sec.gov.

Each software defect has a regression test, and three of them were confirmed on real Actions runs.
**No ordinary trading losses were recorded, because nothing traded as a candidate.**

## F. Operational evidence (unattended, on GitHub Actions)
OPS_PLACEHOLDER

## G. Next action
NEXT_PLACEHOLDER

## Capability audit: what the system can and cannot do today

| Capability | Implemented | How tested | Evidence of skill | Missing |
|---|---|---|---|---|
| Recognise price, candle, volume and context patterns | Point-in-time feature panel (returns, candles, volume, volatility, trend/VWAP, relative strength, breadth) for crypto; first-candle direction and relative volume for stocks (ORB) | Causality tests (a feature never sees later bars); P1 and ORB studies | **None yet that clears costs.** P1: rank IC ≤ 0.06 against ~0.10 needed. ORB: see A | Order book and quote features; event features; individual tests of each feature family's incremental value (planned, not done) |
| Separate signal from noise | Matched random entries, placebo, block-bootstrap intervals, PBO, deflated Sharpe | Every study | Short-term reversal had a statistically real but small rank IC (+0.035) in P1 development and validation, swamped by costs. No signal has beaten its placebo after costs | — |
| Rank opportunities by expected benefit after costs | Return models with a cost threshold (P1 M1/M3) | P1 | Not demonstrated: abstaining models beat forced trading only by staying in cash | A calibrated expected-return model with skill |
| Recognise changing conditions | Drift monitors and a regime filter (exploratory) | Unit tests; DECISION_QUALITY Q4 (exploratory) | Not demonstrated | Validated regime or out-of-distribution detection |
| Entry, hold, exit, no-trade | P1 policy (enter top 3, hold while ranked, exit, abstain); ORB stop entry / stop / close exit with decompositions | P1; ORB benchmarks 1–6 | P1: no-trade was the best decision. C1: its stop destroyed ~0.4%/trade. ORB: see D | An exit model with skill; position sizing beyond fixed caps |
| Estimate uncertainty and unfamiliar conditions | Calibration (Brier, ECE, reliability) and bootstrap intervals | P1 M2: ECE 0.02–0.03, Brier skill +0.5–1.4% | Mild calibration with little skill | Out-of-distribution flags; prediction intervals for returns |
| Avoid repeating mistakes | Incident record, regression tests, frozen hashes, consumed-data ledger, no-live-path merge gate | 316 tests; CI on every commit | 16 incidents, each with prevention | Automatic incident capture from production runs |

**Rule execution is not predictive skill.** The engine executes rules reliably and safely (deterministic risk
checks under 0.1 ms; no AI model on the order path). Whether any rule has an edge is the open question above.

## Timing path (measured)
| Stage | Measured | Note |
|---|---|---|
| Market data → receipt | Coinbase WebSocket 69 ms median. **US stocks on the free plan: SIP is 15 minutes delayed** (IEX real-time only) | The dominant delay for stocks |
| Features | 16 ms (3 coins, 70 days) | — |
| Decision and risk checks | < 0.1 ms | Deterministic |
| Order POST → acknowledgement (Alpaca paper) | 122–161 ms; fill stamped ~2 ms after acceptance | From this container, behind a proxy |
| Opportunity decay | Flat for every tested strategy (LATENCY.md) | Faster infrastructure buys nothing until an edge with measurable decay exists |
