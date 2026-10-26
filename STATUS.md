# Tradelab status (authoritative)

**As of 2026-10-26, branch `claude/prediction-track`.** Code and results verified at commit `96924c0`. This file
was added in the commit after it, along with P1_REPORT.md. Where any other document disagrees with this file,
this file wins. Older documents carry a pointer here where they were stale.

**Mode:** paper only. `config/paper.toml` and `config/intraday_paper.toml` set `mode = "paper"`. No exchange or
broker credentials are configured anywhere. No strategy is live-eligible (`tradelab/governance/status.py`). Real
orders, purchases and subscriptions are not authorised.

## Objective, and where we are against it
The objective is an autonomous system that finds opportunities and makes informed entry, hold, exit and no-trade
decisions, intraday, in US stocks and crypto, with performance that survives costs.

**Not achieved.** No tested signal or model has a net edge after realistic costs on data it was not tuned on.
The research and paper infrastructure needed to find one, and to recognise a false one, exists and is tested.

## 1. Implemented and verified
| Component | Evidence |
|---|---|
| Test suite | **237 passed**: locally, and from a clean install of `requirements.lock` on 2026-10-26 |
| Deterministic risk engine, order state machine, paper venue, journal | Unit and regression tests; decision path never imports an LLM or the network (`tests/test_decision_path_isolation.py`) |
| Reproduction of central historical results | Audit, stock/crypto engine cross-checks, combined DSR, period tables and the S2X final test were recomputed from archived data and match exactly (`research/reproduce/`) |
| Point-in-time Coinbase universe and hourly bars | 113 products, 3.89 M bars, 2021-01 → 2026-10; audit in `docs/DATA_AUDIT.md` |
| Prediction research tools | Causal panel; purged walk-forward; PBO; calibration; block bootstrap (`tradelab/predict`, `tradelab/research/validation.py`) |
| P1 study and verdict | `P1_REPORT.md`; every phase reproduces identically |
| Paper state persistence script | Tested against a local remote: save → restore → save round trips, no-change skip, and failure when the remote is unreachable |
| **Two manual daily paper cycles on GitHub Actions (restore verified)** | Run 40257231608 succeeded and saved `paper-state@6ce7e32`: 8 decisions, 6 simulated fills, 4 equity marks. Run 40257385219 restored that state and saved `f007904`: still 6 orders and 6 fills (the same UTC day traded nothing twice), 16 decisions, 8 equity marks. Run 40256991578 failed (scikit-learn/scipy missing from the lock file; now fixed) |

## 2. Implemented but not verified
| Component | What is missing |
|---|---|
| **Scheduled** paper workflows (daily; crypto intraday every 15 min; stocks intraday every 30 min in market hours) | They exist only on this branch. GitHub runs schedules only from the default branch, so **no scheduled run has happened**. The intraday workflows cannot even be triggered manually until merged. **Continuous paper trading is not running and must not be claimed until scheduled runs are observed** |
| Same-day re-runs | They append duplicate decision and equity-mark rows. Harmless to positions, but they double-count marks on the dashboard. To fix before relying on equity curves |
| Alerts | **None configured.** By default GitHub emails failed scheduled-run notifications to whoever last edited the schedule; that has not been tested |
| Intraday paper runners (`live_crypto`, `live_stocks`) | Unit-tested and run by hand before; never run on Actions. The stocks runner uses Yahoo prints, not consolidated quotes |
| Dashboard "evidence by source" section | Built locally and on Actions; nobody has reviewed it |
| Simulated vs broker fills | All fills are **simulated by tradelab**. Broker paper fills are not connected (no Alpaca paper key) |

## 3. Research only (results, no deployable strategy)
| Study | Status |
|---|---|
| S1, S2, S2-ETF, S2X (intraday stocks) | REJECTED. S2-ETF, once "inconclusive", failed its out-of-universe replication |
| C1, C2 (intraday crypto) | REJECTED at retail costs |
| Daily trend ensemble | INCONCLUSIVE; benchmark challenger only |
| **P1a / P1b (crypto daily/weekly ranking, 2026-10-26)** | **REJECTED: no qualifying candidate.** Rank ICs −0.04…+0.06 against ~0.10 needed. Every configuration lost money net in development. PBO 0.43 / 0.54 |

## 4. Planned but absent
- **Prediction ledger:** append-only, timestamped forecasts recorded before outcomes. Designed (P1 Amendment
  A7) but not built, because nothing qualified.
- Exit research on fixed entries (time vs target vs volatility stop vs model-informed).
- The required-skill check for **stocks** at ~8 bp costs; needs consolidated quotes.
- The ORB study (pre-registered).
- Equity event coverage (earnings, halts, filings) as a prospective dataset.
- Drift monitors wired into the scheduled loop.
- Real alerts.

## 5. Blocked
| Blocker | Unblocks | Needs from you |
|---|---|---|
| No consolidated (SIP) stock quotes | Stock cost measurement, the stock required-skill check, ORB | An **Alpaca paper** key, set up as in `docs/CREDENTIALS_SETUP.md` (repository secrets; never pasted in chat). There is no read-only key type; a paper key cannot move money |
| Coinbase fee unverified | Every crypto cost assumption | Your fee tier from the Coinbase fee page. It is not a secret |
| Lower-cost crypto execution | Any intraday crypto work | A measured maker-fill or fee-tier cost; P1 shows retail taker cost is the binding constraint |
| Scheduled paper runs | Prospective evidence | **Merge this PR** (or approve the merge) |

## Rules (reconciled)
- **Forward period before any live-trial proposal:**
  - 6 months for strategies that trade daily or slower;
  - otherwise the longer of 3 months and the time needed to reach the pre-registered trade count (≥ 60
    trades for intraday).

  This replaces the conflicting "3 months" in INTRADAY_* / RESEARCH_BUDGET and "6 months" in ARCHITECTURE /
  RESEARCH.
- **Evidence sources are always labelled separately:**
  - historical backtest (Coinbase or Yahoo data, assumed costs);
  - simulated paper fills (tradelab);
  - broker paper fills (not connected);
  - live (disabled).
- **The final historical window of any study is "opened once", never "untouched"**, when earlier studies
  examined the same dates.
- **Final order authorisation and hard risk limits are deterministic code.** No language model can change them.
