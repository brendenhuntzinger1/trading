# Tradelab status (authoritative)

**As of 2026-10-26 ~10:00 UTC.** Where any other document disagrees with this file, this file wins.
- `main` is at the merge of [PR #1](https://github.com/brendenhuntzinger1/trading/pull/1), commit `14c2a32`,
  merged 03:18 UTC under the owner's conditions. All scheduled paper workflows run from it.
- Research since the merge (ORB result, H3) is on branch `claude/prediction-track` and is not yet on `main`.
  None of it changes what runs.

**Mode:** paper only (`mode = "paper"` in both configs).
- No strategy is live-eligible (`tradelab/governance/status.py`).
- Real orders, purchases, subscriptions, live credentials, transfers and leverage are not authorised.
- **Credentials:** one Alpaca **paper** key exists. The owner pasted it in chat on 2026-10-25. It is used
  only inside the working session, per command, and is not in the repository or in any repository secret.
  It should be rotated and stored as an environment secret (`docs/CREDENTIALS_SETUP.md`).
- No live or exchange keys exist.

**Objective:** an autonomous trader that makes informed entry, hold, exit and no-trade decisions with an edge
that survives costs. **The next proof point is one reproducible, economically meaningful signal after realistic
costs.** We do not have one.

## Verified
| Item | Evidence |
|---|---|
| Test suite | CI green on every pushed commit; the latest is in the PR's checks |
| Scheduled paper runs on `main` | `paper-crypto-intraday` runs 2–12, `paper-daily` run 6 (06:52), `paper-watchdog` runs 1–3, all green ([Actions](https://github.com/brendenhuntzinger1/trading/actions)) |
| Alert delivery | Watchdog run 1 (03:49) opened [issue #2](https://github.com/brendenhuntzinger1/trading/issues/2) (`paper-alert`, missed crypto run); run 2 (03:56) closed it automatically when the condition cleared |
| State recovery | Save → fresh clone → restore round trip (test, and on Actions every run since). State lives on branch `paper-state` |
| Duplicate prevention | Same-day re-runs add no orders, fills or marks (test, and Actions run 4: 2 → 1 mark per day, orders and fills unchanged) |
| Failed saves fail the job | Unreachable remote and a rejected push both exit non-zero (tests) |
| WAL-safe saves | Rows still in the SQLite write-ahead log are checkpointed before saving. The test fails without the fix |
| Persistent risk halts | A latched breaker survives a save and a restore on a fresh machine, and is still enforced (test) |
| Missed-run detection | Heartbeats plus watchdog, market-hours aware (tests, and live on Actions) |
| No live path | `tests/test_no_live_path.py`: configs are paper; no `secrets.` in workflows; only the paper broker module may send state-changing requests, and only to an exact (host, path) allow-list on the paper host |
| Alpaca SIP data on the paper key | Data gates B7.1–B7.5 passed (`research/stocks/verify_2026-10-26.json`): consolidated bars and NBBO quotes, timestamps across DST, delisted-name coverage, spreads, splits |
| Alpaca paper broker | One $10 BTC round trip, 2026-10-26 (`research/execution/alpaca_paper_roundtrip_20261026T030457Z.json`). Fee 0.25% per side; buy 4.7 bp and sell 1.1 bp from mid; order POST 122–161 ms; a duplicate resend returned the existing order |
| Central historical results reproduce | Audit, cross-checks, DSR, S2X, all P1 phases; ORB mechanics audited independently (31 trades, 0 mismatches) |
| P1 frozen | Config and code hash `research/p1/frozen_config.json`. A changed configuration is refused (test) |
| Consumed-data guard | `research/consumed_data.json`; selection windows overlapping consumed data raise (test) |

## Running, not yet verified
| Item | Gap |
|---|---|
| `paper-stocks-intraday` | Scheduled 13:07–21:37 UTC on weekdays. It has not yet had a market session on `main` (first: 2026-10-26) |
| GitHub's scheduler | It ran far fewer 15-minute crypto slots than scheduled (incident 18). The runner catches up on missed bars, so no data is lost, but decisions run late. Real intraday trading would need an always-on host |
| Broker paper fills in workflows | The Alpaca paper adapter is **not wired to any workflow**: there are no repository secrets. Every scheduled-run fill is simulated by tradelab |

## Active workflows on `main`
| Workflow | Schedule (UTC) | Runs | What it is |
|---|---|---|---|
| `paper-daily` | 00:17 and 06:17 | `ensemble_vol40`; `breakout_20_atr3_vol40` (shadow); `fixed_allocation`, `buy_hold` | **Diagnostic.** ensemble is INCONCLUSIVE, breakout is REJECTED, the other two are benchmarks. **No trading candidate** |
| `paper-crypto-intraday` | every 15 min | C1, C2 on BTC/ETH/SOL | **Diagnostic engine exercise.** Both REJECTED |
| `paper-stocks-intraday` | :07 and :37, 13–21 on weekdays | S2 on 15 ETFs (Yahoo prints) | **Diagnostic engine exercise.** REJECTED |
| `paper-watchdog` | :41 every 3 h | — | Monitoring; opens and closes `paper-alert` issues |
| `ci` | push / PR | tests | — |

All run with public data only, write simulated state to `paper-state`, and cannot place real orders.

## Research results (all failures preserved)
- **REJECTED:**
  - S1, S2, S2-ETF, S2X, C1, C2, daily breakout.
  - **P1a/P1b:** the 8 tested configurations failed (`P1_REPORT.md`, `P1_METHODS_AND_AUDIT.md`). Frozen.
  - **ORB, 2026-10-26, in development (2020–21):** 4,048 trades, gross −9.2 bp and net −35 bp per trade.
    It loses to its placebo and to direction-only, and failed the sanity gate (−0.22R against the paper's
    +0.08R). Stopped under B16, so its validation and final windows are unread.
- **INCONCLUSIVE:** the daily ensemble.
- **IN PROGRESS: H3, first-candle continuation** (`H3_PREREGISTRATION.md`). It is ORB's direction-only
  benchmark, which looked strong in development (+60 bp net per trade).
  - Registered before any 2022–26 data for it was read.
  - Validation 2022–23 is running now.
  - The final window (2024–26) is read only if H3-L qualifies.
- **Research budget:** H3 is the third and last hypothesis allowed by `RESEARCH_BUDGET.md`. If it fails, the
  budget rule applies: stop intraday research, keep the platform and benchmarks, and say so plainly.

## Assumed, not verified
- **Coinbase fees:** a 0.60% taker fee is assumed. Your account tier would verify it.
- **Slippage beyond the touch** (stocks): always an assumption, 1 bp base and 5 bp stress. Quoted spreads
  are measured from SIP quotes; a trade without a usable quote takes an assumed 10 bp per side.
- **Survivorship:** the stock universe adds corporate-action tickers to Alpaca's asset master (ORB
  Amendment 4). Non-merger delistings may still be missing.
- **Crypto alt spreads:** BTC/ETH spreads were measured; alts were not. Alpaca crypto costs rest on one
  round trip.
- **Real-time stock data:** the free plan delays consolidated data by 15 minutes. Any strategy that acts at
  09:35 would need a paid real-time feed. That purchase is **not authorised**.

## Decisions waiting on you
- **Rotate the Alpaca paper key** pasted in chat. If you want workflows to use broker paper fills, store the
  new key as an environment secret (`docs/CREDENTIALS_SETUP.md`). Never in chat.
- **After H3:** whether to authorise any further research budget. Under the current budget, the answer
  defaults to stop.
- Coinbase fee tier, which you read from your account. It is not a secret.

## Rules (reconciled)
- **Forward period before any live-trial proposal:**
  - 6 months for strategies that trade daily or slower;
  - otherwise the longer of 3 months and the time to reach the pre-registered trade count (≥ 60 trades
    intraday).
- **Evidence is labelled by source:**
  - historical backtest (assumed costs unless measured);
  - simulated paper fills;
  - broker paper fills (adapter verified once; not wired to workflows);
  - live (disabled).
- **Historical windows are labelled honestly.**
  - A final window already examined is "opened once", never "untouched".
  - Consumed windows may be re-run for reproduction, never used for selection.
  - If nothing qualifies at validation, the final window is not read.
- **Final order authorisation and hard risk limits are deterministic code.** No language model can change them.
