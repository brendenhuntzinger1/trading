# Tradelab status (authoritative)

**As of 2026-10-26 ~10:30 UTC.** Where any other document disagrees with this file, this file wins.
- `main` is at the merge of [PR #1](https://github.com/brendenhuntzinger1/trading/pull/1), commit `14c2a32`,
  merged 03:18 UTC under the owner's conditions. All scheduled paper workflows run from it.
- Research since the merge (ORB result, H3, incident 20) is in draft
  [PR #3](https://github.com/brendenhuntzinger1/trading/pull/3). None of it changes what runs.

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

## Which dates each study covered (correction, 2026-10-26)
An earlier summary said "three strategies tested on 2020–21". That was wrong as a description of the whole
programme:
- **2020–21 was only the *development* window of ORB and H3** (US stocks in play, Alpaca SIP).
  - Their later windows (2022–23 validation, 2024-01-02 → 2026-07-24 final) were never read, because both
    failed in development.
- **Crypto ran through the most recent data.**
  - P1 read Coinbase data from 2021-03-01 to **2026-10-24** across development, validation and final.
  - The daily crypto strategies and C1/C2 were tested on 2024-01-01 → 2026-10-24.
- **US stocks on Yahoo data:**
  - S1/S2 tests ran to 2026-10-23;
  - S2X covered 2016 → 2026-10-24.
- The full reconciliation (hypotheses, configurations, periods, data read, costs) is in `TESTED_INVENTORY.md`.
- Every local dataset's first and last timestamp is in `research/phase2/data_inventory.json`
  (`scripts/data_inventory.py`).

**Data freshness (2026-10-26):**
- Coinbase crypto candles end 2026-10-25.
- Yahoo stock files end 2026-10-23.
- The Alpaca SIP caches end 2022/2023 (ORB/H3 only).
- A phase-2 SIP daily panel for 2016 → 2026-10-23 is being built.
- **Stock data access:**
  - consolidated (SIP) history is free up to 15 minutes ago;
  - real-time is IEX only (about 2–4% of volume);
  - so live intraday stock decisions on consolidated prices are not possible on the free plan.

## Research results (all failures preserved)
- **REJECTED:**
  - S1, S2, S2-ETF, S2X, C1, C2, daily breakout.
  - **P1a/P1b:** the 8 tested configurations failed (`P1_REPORT.md`, `P1_METHODS_AND_AUDIT.md`). Frozen.
  - **ORB, 2026-10-26, in development (2020–21):** 4,058 trades, gross −9.2 bp and net −35 bp per trade.
    It loses to its placebo and to direction-only, and failed the sanity gate (−0.22R against the paper's
    +0.08R). Stopped under B16, so its validation and final windows are unread.
- **INCONCLUSIVE:** the daily ensemble.
  - **H3, 2026-10-26, in development (2020–21, corrected):** 4,956 trades, gross −2.4 bp and net −24 bp
    per trade [−38, −10]; both years negative. Its motivating +60 bp was a look-ahead artifact of the harness
    (incident 20, fixed with a test). Failed Amendment 1's development gate, so validation and final are unread.
- **Research budget: spent** (P1, ORB, H3: all rejected). Per `RESEARCH_BUDGET.md`: stop intraday research,
  keep the platform and benchmarks, and recommend no trading, unless you reopen it with a new information
  source.

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
- **Close the intraday research track** (recommended; the budget is spent), or reopen it with a new
  information source (`MORNING_REPORT.md` §G).
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
