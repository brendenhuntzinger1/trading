# Tradelab status (authoritative)

**As of 2026-10-26, branch `claude/prediction-track`, [PR #1](https://github.com/brendenhuntzinger1/trading/pull/1)
(draft; merging not authorised).** Where any other document disagrees with this file, this file wins.

**Mode:** paper only (`mode = "paper"` in both configs). No broker or exchange credentials are configured. No
strategy is live-eligible (`tradelab/governance/status.py`). Real orders, purchases and subscriptions are not
authorised.

**Objective:** an autonomous trader that makes informed entry, hold, exit and no-trade decisions with an edge that
survives costs. **The next proof point is one reproducible, economically meaningful signal after realistic
costs.** We do not have one.

## Verified
| Item | Evidence |
|---|---|
| Test suite on the latest commit | See the "CI on the exact latest commit" line in the PR |
| Central historical results reproduce | Audit, cross-checks, DSR, S2X and all P1 phases recompute identically |
| P1 frozen | Config and code hash `research/p1/frozen_config.json`. Re-runs are reproduction-only; a changed configuration is refused (test) |
| Consumed-data guard | `research/consumed_data.json`; selection windows overlapping consumed data raise (test) |
| One equity mark per account per UTC day | Unique index plus migration (tests). Before: same-day re-runs added marks, and the dashboard summed operating cost over them |
| Duplicate prevention | Same-day re-runs add no orders, fills or marks (test). Run 3 on Actions kept 6 orders and 6 fills |
| State recovery | Save → fresh clone → restore round trip (test, and on Actions runs 2 → 3) |
| Failed saves fail the job | Unreachable remote and a rejected push both exit non-zero (tests); never reported as "nothing to save" |
| WAL-safe saves | Rows still in the SQLite write-ahead log are checkpointed before saving. The test fails without the fix |
| Persistent risk halts | A latched breaker survives a state save and a restore on a fresh machine, and is still enforced (test) |
| Missed-run detection | Heartbeats plus watchdog, market-hours aware (tests) |

## Implemented, not yet verified in operation
| Item | Gap |
|---|---|
| Scheduled runs | None has happened: GitHub schedules run only from `main`, and merging is not authorised |
| Alert delivery | **Approved by the owner on 2026-10-26:** GitHub issues labelled `paper-alert` in this repository, deduplicated per key. The repository is **public**, so alert issues are publicly visible. Delivery is tested only with a stub until the first real alert fires |
| Intraday paper workflows, watchdog | Cannot be dispatched before they exist on `main` |
| Broker paper fills | An Alpaca **paper** adapter exists (`tradelab/broker/alpaca_paper.py`). One $10 BTC round trip was verified on 2026-10-26. **No workflow uses it**, because there are no repository secrets. Every scheduled-run fill is still simulated by tradelab |

## What merging would activate (after approval)
| Workflow | Schedule | Runs | What it is |
|---|---|---|---|
| `paper-daily` | 00:17 and 06:17 UTC | `ensemble_vol40`; `breakout_20_atr3_vol40` (shadow); `fixed_allocation`, `buy_hold` | **Diagnostic.** ensemble is INCONCLUSIVE (named "champion" in `strategies.lock` only because it is the incumbent), breakout is REJECTED, the other two are benchmarks. **No trading candidate** |
| `paper-crypto-intraday` | every 15 min | C1, C2 on BTC/ETH/SOL | **Diagnostic engine exercise.** Both REJECTED |
| `paper-stocks-intraday` | every 30 min in market hours | S2 on 15 ETFs (Yahoo prints) | **Diagnostic engine exercise.** REJECTED |
| `paper-watchdog` | every 3 h | — | Monitoring |
| `ci` | push / PR | tests | Already active |

All of them run with public data only, write simulated state to `paper-state`, and cannot place real orders.

## Research results (all failures preserved)
- **REJECTED:** S1, S2, S2-ETF, S2X, C1, C2, breakout.
- **P1a/P1b:** the **8 tested configurations** failed under their data, rules and assumed Coinbase costs. That
  is not a verdict on price/volume models, top-3 portfolios or intraday crypto in general (`P1_REPORT.md`).
- **The audit** (`P1_METHODS_AND_AUDIT.md`) covers:
  - why the final window was read without a candidate (a design mistake, now banned by ORB B9);
  - the data now consumed;
  - how the break-even rank correlation was derived (a construction-specific diagnostic);
  - what PBO does and does not mean.
- **INCONCLUSIVE:** the daily ensemble.

## Assumed, not verified
- **Coinbase fees:** a 0.60% taker fee is assumed. Your account tier would verify it.
- **Stock costs:**
  - The 8 bp round trip (COSTS.md) is an **assumption** for market-on-open/MOC trading. It does not apply to ORB.
  - ORB uses measured spreads when SIP quotes are available, otherwise an assumed 10 bp per side.
  - Slippage beyond the touch is always an assumption: 1 bp base, 5 bp stress.
- **SIP data access** on the Alpaca paper account is unverified.
- **Slippage for crypto alts:** BTC/ETH spreads were measured live once; alts were not.

## Stock track (everything possible without credentials is done)
- **ORB: REJECTED in development (2026-10-26).** 4,048 trades, net −35 bp per trade; it loses to placebo and to direction-only. Stopped under B16, so validation and final are unread. Details in `MORNING_REPORT.md`.
- **ORB pre-registration, finalised:** Amendments 1–5, registered before any ORB data. It is:
  - benchmarks first (SPY, in-play basket, direction-only, placebo), then the rule;
  - measured spread kept apart from assumed slippage; with no quotes the result is labelled "cost assumed"
    and cannot PASS;
  - frozen by hash, and **only the primary configuration can be frozen**;
  - stopped after validation if nothing qualifies, leaving the final window unread;
  - E6 trial count N = 106, read from the registry.
- **Built and tested on fake API responses only. No stock data has been downloaded.**
  - A read-only Alpaca data client: GET only; order, position and account-configuration endpoints refused;
    the paper host enforced.
  - Data gates B7.1–B7.5: SIP access, timestamps across DST, coverage including 13 delisted names, spreads at
    09:35–10:30 and 15:59 ET, splits.
  - A spread module (measured only), a cost module, and the ORB simulator.
  - The study harness (gates → dev → validation → freeze → final), which calls the consumed-data guard.
- **Known unknowns until real data arrives:**
  - whether Alpaca quote timestamps are consolidated or exchange time;
  - spin-offs are not detected;
  - the delisting dates were written from memory (the gate's window tolerates a few days' error);
  - the live-data path will likely need fixes on first real contact.

## Blocked on credentials: the exact next action
1. You add an **Alpaca paper** key as environment secrets, following `docs/CREDENTIALS_SETUP.md`. Never in chat.
2. I run `scripts/pit_verify_alpaca.py --quick`, then the full gates:
   - SIP bars and quotes;
   - timestamps;
   - instrument coverage, including delisted names;
   - spreads at 09:35–10:30 and 15:59 ET;
   - corporate actions.
3. If gates 1–3 pass: ORB development replication, then development and validation.
4. The final window is read only if a configuration qualifies.

## Decisions waiting on you
- Merge authorisation, after the readiness items above.
- Coinbase fee tier, which you read from your account. It is not a secret.

## Rules (reconciled)
- **Forward period before any live-trial proposal:**
  - 6 months for strategies that trade daily or slower;
  - otherwise the longer of 3 months and the time to reach the pre-registered trade count (≥ 60 trades
    intraday).
- **Evidence is labelled by source:**
  - historical backtest (assumed costs unless measured);
  - simulated paper fills;
  - broker paper fills (not connected);
  - live (disabled).
- **Historical windows are labelled honestly.**
  - A final window already examined is "opened once", never "untouched".
  - Consumed windows may be re-run for reproduction, never used for selection.
  - If nothing qualifies at validation, the final window is not read.
- **Final order authorisation and hard risk limits are deterministic code.** No language model can change them.
