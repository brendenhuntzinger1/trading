# Tradelab: architecture, costs and the path to real money

Status 2026-10-25: **paper trading only.** No exchange credentials exist, no live order code exists,
and nothing here can move real money.

## What the evidence says (read this first)

| Question | Answer | Source |
|---|---|---|
| Is the phase-1 "22% a year" real? | Arithmetically yes, under phase-1 assumptions. With correct fees it is 19.8%. It is in-sample, and on 3 unseen coins the strategy lost to holding a fixed ~20%. | `AUDIT.md` |
| Did any new strategy beat a fixed allocation on untouched 2024–2026 data? | No. 73 configurations tried; every deflated Sharpe ≤ 0.05. | `RESEARCH.md` |
| Does news / macro data help? | The scheduled-macro overlay (FOMC/CPI, point-in-time) **hurt** (5.6% vs 11.9% CAGR). Headline news can only be judged going forward; no historical claim is made. | `RESEARCH.md`, `docs/EVENTS.md` |
| Does regime detection help? | No. Both selectors did worse than either strategy they choose between. | `RESEARCH.md` |
| Day trading / order-book signals? | Hourly setups went to ~$0 after fees in phase 1. No historical order-book data exists, so order-book signals are recorded for future study only. | phase 1, `docs/LIVE_DATA.md` |
| Expected result on $1,000? | Median tens of dollars a year, 90% range includes losses of $100+. An always-on server or paid AI classification would consume the median. | `RESEARCH.md` |

The strongest system we can substantiate is small: a daily decision, a fixed allocation as the default,
the trend baseline as its challenger, strict risk limits, and honest measurement. Everything else is
built and running in paper mode so it can earn its place with forward evidence, or be dropped.

## Components and why each exists

```
 Coinbase REST/WS ──► data layer ──────────────► strategies (daily, locked versions)
   (public)           point-in-time candles,        │ target weights
                      live books/trades,             ▼
                      quality checks ──────────► RISK ENGINE (hard limits, breakers; no overrides)
 official sources ──► event pipeline ── flags ──►   │ approved intents only
   Fed/BLS/BEA/SEC/   (source, published,           ▼
   CFTC/status pages   first-seen, novelty)     order manager ──► paper venue (real book, simulated fills)
                                                    │ journal-first, idempotent, reconcile-before-retry
                                                    ▼
                                    SQLite journal ──► dashboard / governance monitors
```

| Component | Code | Why it is necessary | State |
|---|---|---|---|
| Point-in-time candles | `tradelab/data/candles.py` | Every bar records when it became knowable and when we received it. This prevents look-ahead and the phase-1 "drop the last row blindly" bug. | Done, tested |
| Backtest engine | `tradelab/research/engine.py` | Tracks units and cash, so weights drift and every rebalance is charged. Next-bar fills, minimum orders, rebalance band. Phase 1 gave free rebalancing. | Done, tested; 2 bugs found and fixed |
| Statistics | `tradelab/research/metrics.py` | CAGR vs arithmetic mean, block bootstrap that respects time dependence, deflated Sharpe for multiple testing. | Done |
| Experiment registry | `research/registry.jsonl` | Every configuration tried and every pre-registration, written before results. Without it, "best of N" passes for skill. | 73+ trials logged |
| Walk-forward and gate | `tradelab/research/walkforward.py`, `gate.py` | Required evidence for any adaptive rule. The gate failed calibration, so it logs only. | Done, not used for decisions |
| Live market data | `tradelab/data/live/` | Trades, L2 books with sequence and checksum integrity, reconnects, clock offset, stale detection, recorder, derivatives (research only). | Done; 60 s live smoke run clean on both venues |
| Always-on monitor | `tradelab/service/monitor.py` | Watches freshness, book integrity and abnormal moves between daily decisions; records books for future order-book research. | Done; needs a host to run continuously |
| Event pipeline | `tradelab/events/` | Source-backed records with published / first-seen times, reliability tier, corroboration, novelty (new/duplicate/correction/resurfaced). The optional LLM only labels, with injection defenses and quote verification. | Done; 11/13 sources live |
| Risk engine | `tradelab/risk/` | Hard limits loaded from a file and frozen; breakers with separate halt / cancel / reduce actions; no liquidation on outage; latched breakers need a named human reset. No override parameter exists. | Done, tested |
| Order manager and paper venue | `tradelab/execution/` | Deterministic client order ids (one order per decision, whatever the direction), journal before send, any unclear venue error treated as unknown and reconciled before retry, partial fills, venue minimums, holds for resting orders, fills that walk the real book, a touch is not a fill, latency and slippage measured. | Done, tested |
| Secrets | `tradelab/execution/secrets.py` | Paper processes refuse to start if live keys are present; keys with transfer permission are rejected; logs are redacted. | Done; no live keys exist |
| Daily runner | `tradelab/service/daily.py` | One idempotent cycle per UTC day; refuses unlocked strategy code; never values positions at $0 on missing prices. | Running in paper |
| Governance | `tradelab/governance/`, `config/strategies.lock` | Drift monitors (performance, inputs, execution). Fixed promotion thresholds; promotion and rollback are git commits by a human, never by the bot. | Done |
| Dashboard | `tradelab/dashboard/build.py` | Realized vs unrealized P&L, net of fees and operating cost, benchmarks, positions, orders, freshness, risk utilisation, every decision with reason, version and sources. Paper and backtest are labelled; nothing is called profit. | Done |

## Independent review

A separate reviewer read the risk, execution and runner code without my conclusions and reported 11 defects,
each reproduced with a script. Before the fixes, each of these had at least one failing regression test,
which fails again if the fix is removed. All 155 tests pass now.

| Finding | Severity | Fix |
|---|---|---|
| A real-client HTTP error mid-run aborted every later account and left an order stuck as `new` forever, latching a reconciliation halt | High | Each account isolated with venue state always saved; any unclear error becomes `unknown`; orders never sent resolve to `not_found` after the grace period |
| A same-day re-run whose target flipped could trade a second time and overwrote the first decision record | High | Order id no longer includes the side; one decision per asset per UTC day; decisions are append-only; the bar that closed at today's 00:00 UTC must exist |
| Latched breakers (drawdown, reconciliation, rejections) cleared themselves on the next run | High | Latches persist in the journal; clearing needs `scripts/reset_breaker.py` with an operator name and a note |
| The correlated-exposure cap (80%) was exceeded because each asset saw the same pre-trade state | High | Account state is updated after each approved order |
| The repeated-rejections breaker could never trip | Medium | Counted from the journal |
| Bearer tokens and tracebacks could reach logs unredacted | Medium | Both redacted |
| A configured REDUCE policy was silently ignored | Medium | Applied by the runner |
| Paper venue could sell coins already held for resting orders; resting buys looked like reconciliation gaps | Medium-low | Holds for resting orders; balances report totals |
| Sells were limited by ask-side rather than bid-side depth | Low | Side-specific depth |
| Stale-book check measured age at run start, so it could never trip | Low | Age measured at each decision |
| Tests passing for the wrong reason (fake errors, fixed timestamps, challengers unchecked) | Low | Tests rewritten; two more false passes were found and fixed while doing so |

Not changed: the lock file's latest entries are marked "PENDING OWNER REVIEW" and paper trading still uses
them. A live mode must refuse any pending entry.

## Paper accounts now running ($1,000 simulated each)

| Account | Role |
|---|---|
| `fixed_allocation` (33% of each sleeve) | Primary candidate and benchmark |
| `ensemble_vol40` | Preserved phase-1 baseline (challenger; in-sample evidence only) |
| `buy_hold` | Market benchmark (capped at 80% gross by the correlated-exposure limit, like every account) |
| `breakout_20_atr3_vol40` | Shadow only; failed its pre-registered test |

## Hosting

| Need | Choice | Why |
|---|---|---|
| Daily decision + tests + dashboard | **GitHub Actions** scheduled workflow (`.github/workflows/paper-daily.yml`), state kept on a `paper-state` branch | The audit measured a 12 h fill delay at ~1.4%/yr cost, so GitHub's scheduling delays are tolerable; the runner is idempotent per day; tests must pass before each cycle. |
| CI | GitHub Actions (`ci.yml`) | Every push runs the full test suite. |
| Continuous monitoring, event polling every 10 min, book recording | An always-on host (`deploy/systemd/`) | GitHub jobs cap at 6 h, schedule no more often than every 5 min, and can be delayed or dropped. **Not needed** for the daily strategies on paper. Worth it only once real money is at stake, or to collect order-book data. |

## Cost estimate (for the selected services)

| Item | Monthly | Notes |
|---|---|---|
| GitHub Actions | $0 | Free plan: 2,000 Linux min/month on private repos (third-party sources; confirm on GitHub billing). Daily cycle ~3 min plus CI ≈ 150 min/month. Public repos are unlimited. |
| Market data (Coinbase public REST/WS) | $0 | No key needed for market data. |
| Official event sources, FRED key | $0 | FRED API key is free but not yet created. |
| Always-on host (optional) | ~$4–8 | DigitalOcean's smallest droplet is reported at $4 (512 MB); Hetzner's small CX/CPX plans ~€4–8 after their April 2026 price change, and some CX plans are reported unavailable. Third-party figures; confirm before buying. |
| LLM event labelling (optional, off) | $0 (off) / ~$1.30 Haiku / ~$50 Opus | Estimates at ~150 items/day; defaults to Haiku. Only worth turning on if prospective evaluation shows the labels help. |
| Licensed consensus forecasts | not priced | Needed to measure macro "surprise". Without it the pipeline stores actuals only. |
| Historical order-book data | not priced | Needed to backtest order-book signals; omitted on purpose because fees rule out the intraday trading it would support. |
| Exchange fees (paper-simulated now) | ~$0.40 (fixed 33%) to ~$7 (baseline) | Coinbase lowest tier 0.60% taker; baseline turns over ~12× capital a year. |

**Recommended now: $0/month.** At $1,000, every paid item above takes a large share of a median edge
measured in tens of dollars a year.

## Missing data, credentials and decisions

**Needs you:**
1. **A permanent home.** Everything lives in a temporary scratch folder that is deleted when this
   session's container is recycled. Create an empty private GitHub repo (e.g. `tradelab`). I'll push the
   code there and enable the daily paper workflow.
2. **Venue.** Default is Coinbase Advanced (lower small-account taker fee than Kraken, 0.60% vs 0.80%, and the
   same venue as the historical data). Confirm, and confirm your US state: Kraken does not serve every state.
3. **Review the strategy lock** (`config/strategies.lock`, history entry marked "PENDING OWNER REVIEW").

**Optional, free:**
- FRED API key (point-in-time US macro vintages).

**Not needed until a live trial is approved:**
- A Coinbase Advanced API key with **view + trade only, transfers disabled**, held in the host's
  secret store and never in the repo. The live venue adapter is intentionally not written yet.

**Not available, so these questions can't be answered from history:**
- Point-in-time news archive (news effects must be measured going forward).
- Licensed consensus expectations (macro surprise).
- Historical L2 order books (order-book signals).
- Tax treatment of frequent rebalancing (every sale is a taxable event in the US; ask a tax professional).

## Evidence required before any real-money trial

All of these, measured on paper trading after today (the only untouched data left):

1. **Duration:** at least 6 months, and at least 90 days for the promotion check in `strategies.lock`.
2. **Performance:** the candidate beats `fixed_allocation` at matched exposure after fees, with
   P(Sharpe better) ≥ 0.90 on the paired block bootstrap. Otherwise, run `fixed_allocation` itself,
   which needs no timing skill.
3. **Execution:** average realised slippage within the modelled 6 bp. Note the paper venue simulates fills
   against real books, so this check only completes with tiny live orders.
4. **Operations:** zero latched breaker incidents, reconciliation always within tolerance, no missed
   daily cycles without a recorded reason.
5. **Business case:** positive expected net after all operating costs at the actual account size.
6. **Your written approval** naming the exact config hash. The live adapter checks
   `TRADELAB_LIVE_APPROVED_CONFIG`, and the first trial should be a small fraction of the planned capital
   with unchanged risk limits.

If after six months nothing beats a fixed allocation, the evidence-backed answer is a fixed allocation,
or not trading at all. That would be a correct result, not a failure of the system.
