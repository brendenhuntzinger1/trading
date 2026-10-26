# P1: evaluation audit, consumed data, and the statistics behind the claims

Companion to `P1_REPORT.md`. P1 stays **REJECTED**. Nothing here re-opens it, and no number from the final
period is used to choose anything.

## 1. Scope of the conclusion
Eight configurations failed their pre-registered standard:
- P1a: B1, B2, M1, M2, M3;
- P1b: B1, M1, M3.

This holds under:
- the Coinbase USD point-in-time universe;
- hourly bars, 2021-03-01 → 2026-10-24;
- daily or weekly decisions;
- equal-weight top-3, long-only;
- abstention only for M1 and M3;
- an **assumed, unverified** 1.32% round trip.

It is not a statement about price/volume models, top-3 portfolios or intraday crypto trading in general
(P1_REPORT.md, "What P1 does and does not show").

## 2. Why the final period was read without a qualifying candidate, and what that cost

**What happened:**
- The original pre-registration said: "If none qualifies, the final phase still runs all configurations for
  the record, but no candidate can pass."
- At validation, the daily candidate (M1) failed its qualifier, and there was never a weekly candidate.
- The final phase then ran, as written.

**Why it was written that way:** to fix the protocol in advance, so the final window would not be read only
when validation looked good (a form of optional stopping), and to leave a complete record.

**Why that was the wrong rule:**
- Once validation had produced no candidate, the final result could not change the verdict.
- Reading it bought no decision. It **consumed** 16 months of data in the same scope.
- It also produced attractive-looking but unselected numbers (M2's final IC, M3's final Sharpe). These invite
  revival by hindsight. They are reported and must not be acted on.

**Rule from now on** (added to ORB as Amendment 2, B9): if no configuration qualifies after validation, the
study stops there and the final window stays unread. That window remains available to a later, separately
registered study.

## 3. What data is now consumed (`research/consumed_data.json`)
| Scope | Window | Consumed by |
|---|---|---|
| `crypto.coinbase.cross_section` | 2021-03-01 → 2026-10-24 | P1 development, validation and final |
| `crypto.coinbase.daily` | 2024-01-01 → 2026-10-24 | Phase-3 daily strategies (test3:*) |
| `crypto.coinbase.intraday` | 2024-01-01 → 2026-10-24 | C1/C2 test (BTC/ETH/SOL 5-minute; holdout coins over the same dates) |
| `stocks.us.intraday.open_close` | 2016-01-01 → 2026-10-24 | S1/S2 tests, S2X |
| `stocks.us.intraday.momentum_5m` | 2026-07-27 → 2026-10-23 | S3 exploratory (excluded from ORB) |

**Consequences:**
- For **choosing** models, rules or parameters for cross-sectional crypto selection, no historical Coinbase
  data from 2021-03-01 to 2026-10-24 is clean. Earlier years were seen at daily resolution by the rotation study.
- The **only** clean evidence in this scope is prospective, from 2026-10-25 onward.
- `tradelab/research/consumed.py::check_selection_window` raises on any selection window that overlaps a
  consumed entry in a related scope.
- It is a guard for honest use, not a sandbox. It only works if new studies call it, which their harnesses do
  (ORB does).

**Reproduction is allowed; re-selection is not.**
- `research/p1/frozen_config.json` holds a hash of every specification, period, cost, policy rule and the
  evaluation code.
- Any P1 phase may be re-run any number of times. With results present, a run is a deterministic
  **reproduction**: it compares with the stored result, never overwrites it, and records a reproduction entry.
- A run whose configuration or code differs from the frozen hash is **refused**, and the refusal is
  recorded. A test changes M1's ridge α and checks the refusal.
- A pure refactor can be accepted with `refreeze`, but only if it reproduces every stored P1 result exactly.
- The earlier "refuse a second final run" rule did not protect against overfitting. Re-running unchanged
  code is harmless. Changing the model after seeing the results is the harm, and that is what the hash blocks.

## 4. The break-even rank-correlation diagnostic (`gate()` in `research/p1/study.py`)

**What it computes**, on development periods only. For each decision period t, with the eligible coins' realised
forward returns y₁…y_N (N ≥ 4):
1. **Universe mean:** U_t = mean(y).
2. **Oracle selection excess:** O_t = mean of the 3 largest y − U_t. This is an upper bound for a long-only,
   equal-weight top-3 pick.
3. **Synthetic signal of strength ρ:**
   - z_i = Φ⁻¹((rank(y_i) − 0.5)/N), the normal score of the realised rank;
   - s_i = ρ·z_i + √(1−ρ²)·ε_i, with ε_i independent N(0,1);
   - pick the top 3 by s;
   - average over 200 draws of ε.

   S_t(ρ) = mean y of the picks − U_t.
4. **Break-even:** S(ρ) = mean over t of S_t(ρ) is compared with C(τ) = τ × round trip, where
   τ = Σ|Δw| / 2 is the one-way turnover per period. ρ* is the smallest ρ on a 0.01 grid with S(ρ) ≥ C(τ).

**Interpreting ρ:**
- ρ is the correlation between the latent score and the normal scores of returns.
- For Gaussian scores the implied Spearman rank IC is (6/π)·arcsin(ρ/2), slightly below ρ (0.096 at ρ = 0.10).
- Finite-N normal scores have variance a little below 1.

So ρ* slightly overstates the required Spearman IC.

**Assumptions. Each one makes ρ* specific to P1, not a universal minimum:**
- **Portfolio construction:** equal weight, k = 3, long-only, fully invested, no abstention, no drift
  rebalancing. A different k, weighting, hold buffer or abstention rule changes both S(ρ) and τ.
- **Dispersion:** the realised cross-section of the development period (median 16 coins, fat tails, including
  the LUNA collapse). A calmer or wider universe changes O_t and S(ρ).
- **Constant skill:** ρ is the same in every period. A signal whose skill concentrates in high-dispersion
  periods or in the tails can break even with a lower average IC; one that fails in the tails needs more.
- **Turnover is exogenous.** The synthetic signal's own noise is independent each period, so by itself it
  would turn over almost completely (τ ≈ 1). The τ = B1 and τ = 0.25 rows ask what a signal with this
  skill **and** that persistence would need. They do not show that such a signal exists.
- **Costs:** a fixed round trip × turnover, compared with the selection excess only. That is break-even
  against holding the universe, before the universe's own (small) rebalancing cost.
- **Monte Carlo error** at 200 draws × 1,218 periods is small next to the 0.01 grid step.

**Use:** a construction-specific diagnostic that says whether modelling under a given construction and cost is
plausible at all. It is not a lower bound on the skill any strategy needs.

## 5. PBO: what was computed, and what it does not mean (`cscv_pbo` in `tradelab/research/validation.py`)

**Inputs:**
- The matrix of per-period net returns at base cost for each configuration, over the out-of-fold development
  periods. Rows are periods, columns are configurations; every configuration uses the same periods.
- P1a: 853 days × 5 configurations.
- P1b: 122 weeks × 3 configurations.

**Procedure** (Bailey, Borwein, López de Prado & Zhu, 2017, CSCV):
1. Split the rows, in time order, into S = 16 contiguous blocks: about 53 days each for P1a, 7–8 weeks for P1b.
2. For each of the C(16, 8) = 12,870 ways to pick 8 blocks as in-sample, the other 8 are out-of-sample.
3. Find the configuration with the best in-sample Sharpe (mean / std of per-period returns).
4. Compute its out-of-sample relative rank w among the N configurations, with ties counted half, clipped to
   (0.5/N, 1 − 0.5/N), and the logit λ = ln(w / (1 − w)).
5. **PBO** = the share of the 12,870 splits with λ ≤ 0: the in-sample best ranks at or below the
   out-of-sample median.

**Results:** P1a 0.43; P1b 0.54.

**Dependence and other assumptions:**
- **Exchangeable blocks.** Contiguous blocks keep serial dependence *within* a block, but the method treats
  blocks as exchangeable. In-sample blocks can come from after out-of-sample ones, so time order and regimes
  are ignored.
- **The splits are not independent samples.** All 12,870 reuse the same 16 blocks, so PBO is a descriptive
  frequency over re-splittings of one history. It is not an estimate with a known standard error.
- **A coarse statistic with few configurations.**
  - With N = 5, w takes only the values 0.1, 0.3, 0.5, 0.7 and 0.9. λ ≤ 0 means the in-sample best ranked
    3rd or worse of 5 out of sample.
  - With N = 3 the middle rank counts as "overfit", so PBO is close to P(the in-sample best is not the
    out-of-sample best).
- **The selection rule differs slightly.** The study chose among M1–M3 after requiring them to beat B1 and B2.
  CSCV takes the argmax over all configurations, baselines included.
- **The weekly blocks hold 7–8 observations,** so the in-sample Sharpe ranks are very noisy.

**What PBO does mean here:** for these configurations, picking the one with the best development Sharpe would
have landed in the bottom half out of sample in about 43% (daily) or 54% (weekly) of re-splittings. The
ranking among them was not a reliable basis for selection.

**What it does not mean:**
- not the probability that a strategy's results were luck;
- not the probability that it loses money;
- not a property of any single configuration.

Those questions are answered by the bootstrap intervals and the deflated Sharpe ratio, per configuration.
