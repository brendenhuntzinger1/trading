# Morning report, 2026-10-26 (overnight run)

> Final, 2026-10-26 ~10:30 UTC. Supersedes the 04:00 draft and the 09:40 version, which reported a lead that
> turned out to be a look-ahead artifact (incident 20).

Written for the owner; it supersedes nothing in `STATUS.md`, which stays authoritative for status. Every
claim below links to a commit, a run, a file or a test. Paper only throughout: no live orders, purchases,
subscriptions or relaxed limits.

## A. Verdict
**No demonstrated advantage.** Nothing is an exploratory lead worth a test under the current budget. Nothing is
historically qualified, nothing has forward support, and nothing is live-eligible.
- **ORB (stocks in play, opening-range breakout): REJECTED in development** (2020–21, 4,058 trades).
  - Net −35 bp per trade after measured spreads and assumed slippage; worse than its placebo.
  - Stopped under B16, so the 2022–26 data was never read for ORB.
- **H3 (first-candle continuation): REJECTED in development.**
  - Its motivating number was a **look-ahead artifact of my harness** (incident 20): +81 bp gross and
    +60 bp net per trade. The direction-only benchmark had been recorded only on stock-days where the
    breakout later triggered, which silently dropped the losers.
  - Corrected over 2020–21: 4,956 trades, gross −2.4 bp and net −24.4 bp per trade (90% CI −38 to −10).
    Both years are negative.
  - Under H3 Amendment 1 (the same principle as ORB B16), its 2022–23 validation and 2024–26 final windows
    stay **unread**. The fetch was stopped before any 2022–23 outcome was computed.
- **P1 (crypto ranking): stays REJECTED and frozen.**
- **The research budget (`RESEARCH_BUDGET.md`) is spent: three hypotheses, three rejections.** Its rule now
  applies: stop intraday research, keep the platform and paper benchmarks, and recommend no trading.

## B. Completed research (all outcomes, including failures)

| Study | Hypothesis | Configurations | Data | Result after costs | Status |
|---|---|---|---|---|---|
| P1a / P1b | Price/volume features rank liquid Coinbase coins well enough that the top 3 beat costs over a day or a week | 8 (B1 momentum, B2 reversal, ridge, logistic, GBT; weekly B1, ridge, GBT) | Coinbase point-in-time universe, 2021-03 → 2026-10 | Every configuration negative net in development. Rank IC −0.04…+0.06 against ~0.10 break-even for that construction. The daily candidate lost 0.21%/day in validation | **REJECTED** (`P1_REPORT.md`, `P1_METHODS_AND_AUDIT.md`); frozen by hash |
| ORB (stocks in play) | A large opening imbalance (relative volume ≥ 1) persists through the session; buying the 5-minute breakout in the first candle's direction captures part of it | 6 (primary long-only; long/short; RV ≥ 2 or 5 with top 20; RV ≥ 1 or 2 with top 10). Benchmarks: SPY, in-play basket, direction-only, placebo (1,000 replications) | Alpaca SIP minute bars and NBBO quotes; universe = asset master + corporate-action tickers; development 2020–2021 | **Primary:** 4,058 trades over 505 sessions. Gross −9.2 bp, net −35.4 bp per trade (90% CI −41 to −29 bp); hit rate 10.7%. Loses to the placebo (+17.6 bp gross); does not beat direction-only (corrected). Sanity gate failed: −0.22R [−0.29, −0.15] against the paper's +0.08R. All five variants fail too | **REJECTED** in development. Stopped under B16; the validation (2022–23) and final (2024–26) windows are **unread** |
| H3 (first-candle continuation) | On an in-play day, the first 5-minute candle's direction persists to the close | 1 primary (long bullish candles, 09:35 → close, 1/20 equal weight); H3-LS labelled | Same as ORB, development 2020–21 (the hypothesis-generation window) | **H3-L:** 4,956 trades, gross −2.4 bp, net −24.4 bp [−38, −10]; 2020 −13 bp, 2021 −36 bp; −98 bp without the best 5%. Beats the in-play basket by +7 bp a day at matched exposure, but loses money. **H3-LS** (with bearish-candle shorts, borrow not modelled): net −7 bp [−17, +2] | **REJECTED** in development (Amendment 1). Validation and final windows **unread** (`research/h3/results/dev_check.json`) |
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
Only two are honest candidates. A third would be manufactured. **Neither justifies spending money or
relaxing a limit.**

1. **Short in-play stocks whose first 5-minute candle is bearish (09:35 → close).** This is the short half of
   H3-LS: a registered variant, reported, never tested on its own.
   - *Observed, development 2020–21 only:*
     - 5,051 trades; gross +36 bp, net +10 bp per trade (90% CI −6 to +27), **before borrow fees**;
     - 2020: −21 bp; 2021: +42 bp;
     - −64 bp without the best 5% of trades.
   - *Why it could exist:* attention-driven buying of in-play names at the open fades during the day. The
     whole in-play basket also drifted down (−19 bp gross); see the "tug of war" between overnight and
     intraday returns in the academic literature.
   - *Why it may not survive:*
     - borrow availability and fees, and the short-sale circuit breaker (Rule 201), are not modelled;
     - one year carries it all;
     - the hypothesis comes from the same data that produced it;
     - live use needs real-time consolidated data at 09:35, which is a purchase.
   - *Invalidated by:*
     - net ≤ 0 after a borrow-cost model on fresh data (2022–23 is still unread);
     - or a loss in either year;
     - or dependence on the best 5% of trades.
   - **Not authorised:** the budget is spent. Testing it needs your decision, and RESEARCH_BUDGET.md says to
     change direction only with a new information source. Borrow data would be one.
2. **Cheaper crypto execution as a precondition, not a strategy.**
   - P1's break-even diagnostic needed a rank IC near 0.10 at Coinbase's assumed 1.32% round trip. At about
     0.5% the bar falls to roughly 0.04, which P1's reversal baseline (IC +0.035) nearly reached.
   - One Alpaca paper round trip measured about 0.56% all-in. That is a single simulated sample.
   - Every historical Coinbase window is consumed, so the only clean test is **prospective**: months of
     forward data on the cheaper venue, at no cost.
   - *Invalidated by:* measured all-in cost above about 0.8%, or forward IC below 0.03.

**Not recommended:** resolving ORB's stop order with trade-by-trade data. That fixes a real simulator bias
(D), but ORB also loses to its placebo, and even without a stop its breakout entry adds nothing over entering at 09:35.

## D. Decision-quality findings
ORB's registered decompositions separate the decisions. Numbers are from development (2020–2021) only, per
trade, with 90% intervals from day-block bootstrap. **They describe the 2020–21 sample, not a capability.**

| Decision | Comparison on the same opportunities | Result |
|---|---|---|
| **Selection** (which stocks) | In-play basket, long, every selected stock, against SPY | Basket gross −19 bp per trade, net Sharpe −3.3: being in play alone was not worth buying |
| **Direction** (which side) | First-candle direction against the basket | Corrected (incident 20): bullish first candle, long, gross −2.4 bp against the basket's −19 bp. Bearish first candle, short, gross +36 bp. Some relative information (+7 bp a day against the basket at matched exposure), but not enough to pay costs on the long side. The +81 bp reported earlier was a look-ahead artifact |
| **Entry timing** | Breakout stop entry against entering at 09:35, both without a stop (daily P&L, paired) | Corrected: +3 bp a day [−37, +46], **no measurable value**. The earlier −98 bp compared against the look-ahead benchmark |
| **Exit / stop** | 10%-ATR stop against holding to the close, same entries | Stop changed results by −29 bp [−68, +9]. Not significant, and **biased against the stop** (next paragraph) |
| **Abstention** | Stocks armed but never triggered | Their forward return in the signal direction was **−379 bp**. The breakout filter does separate winners from losers, but only after the move has happened, so entering on it pays away the gain |
| **Risk** | Portfolio at the 1× cap | Rule: −73% (2020) and −76% (2021). Beta to SPY 0.03 |

**The execution-model finding behind the sanity-gate failure.**
- The pre-registered fill rule says that if the entry minute's bar also touches the stop, the stop is
  assumed hit first.
- For a breakout, that bar's low usually comes *before* the price crosses the entry level. So the rule
  stops out trades that in reality survived that minute.
- That produced the 10.7% hit rate (the paper had 48%) and a 1-minute median time to the stop.
- Resolving the order within the minute needs trade-by-trade timestamps, which the SIP trade feed has. Doing
  so is the obvious simulator improvement.
- **It does not change this verdict:** without any stop, the breakout entry's gross is +10 bp per trade,
  under the ~26 bp cost. It is no better than entering at 09:35.

## E. Learning record
20 incidents are in `INCIDENTS.md` / `research/incidents.jsonl`, each categorised, with its root cause,
correction and prevention.

**The most important one is incident 20 (software + process).**
- My harness recorded the "direction-only" benchmark only on stock-days where the breakout later triggered.
  That is look-ahead.
- My concentration audit checked years, top days and meme names, but not *how the sample was selected*. So
  the artifact became an "exploratory lead", a pre-registration and a headline in the 09:40 report.
- I found it by re-reading the harness while H3's validation download was running. I stopped the download
  before any 2022–23 outcome existed, fixed the code with a regression test that fails without the fix, and
  regenerated the development frames. The lead disappeared.
- **New rule:** before any number is called a lead, check that every trade's inclusion is decided only with
  information available at its decision time.
- **What went right:** the pre-registration and consumed-data discipline meant the mistake cost no unread
  data.

**Tonight's other incidents:**
- **Software defects:**
  - missing dependency pins;
  - an unsafe state restore;
  - silent push failures;
  - duplicate equity marks;
  - SQLite WAL loss on save;
  - a save that deleted later steps' files;
  - a broker allow-list prefix hole;
  - transport errors killing a download;
  - the container reclaimed while idle;
  - an unfilled benchmark trade crashing a run.
- **Data failures:** the asset master's invalid symbols; the survivorship gap.
- **Execution:** GitHub's scheduler skipping most 15-minute slots.
- **Process errors:**
  - a commit pushed with a failing test;
  - P1's final window read without a candidate;
  - a "refuse second run" rule mistaken for overfitting protection;
  - the owner's email sent once to sec.gov;
  - ORB's trade count mistyped as 4,048 in four documents (it is 4,058; corrected).

Each software defect has a regression test. **No ordinary trading losses were recorded, because nothing traded
as a candidate.**

## F. Operational evidence (unattended, on GitHub Actions)
**Merged:** [PR #1](https://github.com/brendenhuntzinger1/trading/pull/1) merged into `main` at 03:18 UTC
(`14c2a32`), after CI passed on the exact head and the no-live-path gate passed. Research since then is in
draft [PR #3](https://github.com/brendenhuntzinger1/trading/pull/3). It changes no workflow or execution path.

**Scheduled runs on `main`:** all successful, no failures.
| Workflow | Runs observed | Notes |
|---|---|---|
| `paper-crypto-intraday` | Scheduled runs 2–14, 03:52 → 10:02 UTC ([latest](https://github.com/brendenhuntzinger1/trading/actions/runs/40304266813)), plus 1 manual run | Scheduled every 15 min, but GitHub ran it every 25–50 min (incident 18). C1/C2 are REJECTED; this is an engine exercise |
| `paper-daily` | Scheduled run 6 at 06:52 ([run](https://github.com/brendenhuntzinger1/trading/actions/runs/40282418534)), the 06:17 slot about 35 min late; manual runs 2, 3, 5 earlier | Diagnostic strategies and benchmarks, not candidates |
| `paper-watchdog` | Manual run 03:48; scheduled runs 03:56 ([run](https://github.com/brendenhuntzinger1/trading/actions/runs/40266488692)), 07:12, 09:56 | Opened issue #2 (missed run) and closed it once the crypto job succeeded: alert delivery verified end to end |
| `paper-stocks-intraday` | None yet: it runs only in market hours (first slot 13:07 UTC today) | Diagnostic S2 on ETFs |

**State and safety:**
- **Persisted state:** the `paper-state` branch holds the journal, the intraday journal and engine state,
  and heartbeats for each workflow.
- **Recovery and duplicate prevention:** verified on Actions earlier (manual run 3 restored run 2's state, 6
  orders stayed 6). Duplicate equity marks were collapsed on the real journal (2 → 1 per day).
- **Risk halts** survive a save and a restore (test).
- **No live path:** every config is in paper mode; no workflow reads secrets; the only order-sending code is
  the Alpaca *paper* adapter, which no workflow uses (`tests/test_no_live_path.py`).

**Research compute (this cloud session, not Actions):**
- The ORB and H3 downloads and computations ran in this session's container. **It was not unattended in the durable
  sense.** The container was reclaimed twice while the session sat idle (incident 17).
- Session-tracked tasks keep it alive but stop after 2 hours, and the harness asks that they not be
  restarted. The run was finished by staying in an active session.
- Every API result is cached on disk, so each interruption cost only time.

**Unresolved:**
- GitHub's scheduler runs the 15-minute job far less often than scheduled.
- Real-time stock execution would need paid real-time consolidated data.
- The paper broker adapter is not wired to any workflow: there are no repository secrets.

## G. Next action
**Your decision: accept the budget outcome and close the intraday research track.** I recommend it.
- Under `RESEARCH_BUDGET.md`, three hypotheses have been tested and rejected, so the rule is to stop, keep
  the platform and the paper benchmarks running, and recommend no trading. I see no evidence that argues
  otherwise.
- The only remaining idea (C1, bearish-candle shorts) rests on one favourable year of development data, with
  borrow costs unmodelled.
- If you'd rather reopen research, the budget's own rule asks for a new information source first. Borrow-fee
  data, or months of forward crypto data at a cheaper venue (C2), would qualify. Tell me which, and I will
  pre-register it before touching any data.

Housekeeping, whatever you decide: **rotate the Alpaca paper key** you pasted in chat. If you want workflows
to use broker paper fills, store the new key as an environment secret, following `docs/CREDENTIALS_SETUP.md`.

## Capability audit: what the system can and cannot do today

| Capability | Implemented | How tested | Evidence of skill | Missing |
|---|---|---|---|---|
| Recognise price, candle, volume and context patterns | Point-in-time feature panel (returns, candles, volume, volatility, trend/VWAP, relative strength, breadth) for crypto; first-candle direction and relative volume for stocks (ORB) | Causality tests (a feature never sees later bars); P1 and ORB studies | **None yet that clears costs.** P1: rank IC ≤ 0.06 against ~0.10 needed. ORB: see A | Order book and quote features; event features; individual tests of each feature family's incremental value (planned, not done) |
| Separate signal from noise | Matched random entries, placebo, block-bootstrap intervals, PBO, deflated Sharpe | Every study | Short-term reversal had a statistically real but small rank IC (+0.035) in P1 development and validation, swamped by costs. No signal has beaten its placebo after costs | — |
| Rank opportunities by expected benefit after costs | Return models with a cost threshold (P1 M1/M3) | P1 | Not demonstrated: abstaining models beat forced trading only by staying in cash | A calibrated expected-return model with skill |
| Recognise changing conditions | Drift monitors and a regime filter (exploratory) | Unit tests; DECISION_QUALITY Q4 (exploratory) | Not demonstrated | Validated regime or out-of-distribution detection |
| Entry, hold, exit, no-trade | P1 policy (enter top 3, hold while ranked, exit, abstain); ORB stop entry / stop / close exit with decompositions | P1; ORB benchmarks 1–6; H3 | P1: no-trade was the best decision. C1: its stop destroyed ~0.4%/trade. ORB and H3: see D | An exit model with skill; position sizing beyond fixed caps |
| Estimate uncertainty and unfamiliar conditions | Calibration (Brier, ECE, reliability) and bootstrap intervals | P1 M2: ECE 0.02–0.03, Brier skill +0.5–1.4% | Mild calibration with little skill | Out-of-distribution flags; prediction intervals for returns |
| Avoid repeating mistakes | Incident record, regression tests, frozen hashes, consumed-data ledger, no-live-path merge gate | 324 tests; CI on every commit | 20 incidents, each with prevention. Incident 20 shows the checks can still miss a selection bias | Automatic incident capture from production runs |

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
