# Strategy research — phase 3

Date: 2026-10-25. All results are after costs (Coinbase Advanced lowest-tier taker: 0.60% fee + 1 bp
half-spread + 5 bp slippage = 0.66% per side; 0.80% for altcoins in the rotation study). Long-only spot,
no leverage. Every configuration evaluated is in `research/registry.jsonl`.

Reproduce (the test phase refuses to run twice):

    .venv/bin/python research/study_fetch_universe.py        # all Coinbase USD products incl. delisted
    .venv/bin/python research/study_strategies.py dev        # (dev_finish completed an interrupted run)
    .venv/bin/python research/study_strategies.py validate
    .venv/bin/python research/study_strategies.py preregister
    .venv/bin/python research/study_strategies.py test       # one run only
    .venv/bin/python research/study_test_addon.py            # stress for gate/selectors, gate vs baseline
    .venv/bin/python research/study_business.py [LLM $/yr]
    .venv/bin/python -m pytest -q tests/test_research_*.py tests/test_strategies.py

## Bottom line

**No new strategy earned promotion.** One strategy (the trade gate) technically met its pre-registered
test criterion, but it did not beat the ungated baseline it filters. Its probability estimates were not
calibrated, and its return fell to 0% under stressed costs. Nothing survives the multiple-testing
adjustment: across 73 logged trials, every deflated Sharpe ratio is below 0.05.
**Paper-trade the fixed allocation and the existing baseline only.** The breakout strategy can run as a
shadow to gather evidence, not as a candidate for money. For a $1,000 account, the median expected
result is tens of dollars a year with a wide range that includes losses. An always-on server or paid AI
classification would consume most or all of it.

## Method

| Period | Use |
|---|---|
| 2018-01-01 → 2021-12-31 | Development: parameter search (every configuration logged) |
| 2022-01-01 → 2023-12-31 | Validation: chosen configurations only; no re-selection |
| 2024-01-01 → 2026-10-24 | Untouched test: configurations and pass criteria frozen in the registry first (`prereg3:*`, 18:30:45 UTC), run once |
| LTC, BCH, ETC (2018 → 2026) | Holdout coins for single-asset strategies (unseen by all new strategies) |

**Pass rule (pre-registered).** In the test period the strategy must beat a fixed allocation holding the
*same average exposure* on both Sharpe and CAGR. Its max drawdown may be at most 10 points worse, and
its CAGR must be above zero. To be promoted it must also have passed validation.
**Holdout rule.** Beat the exposure-matched fixed allocation on Sharpe and CAGR on at least 2 of 3 coins.

**Universe.** Rotation uses all 473 Coinbase USD products, including 90 delisted ones, so survivorship
bias is limited. A coin is eligible on day t only if all three hold:
- it has at least 365 days of history;
- its 30-day median dollar volume is at least $2M;
- it has a candle on day t.

Eligible coins per year: 3 in 2018, 4 in 2019–20, 11 in 2021, 31 in 2022, 19 in 2023, 47 in 2024,
64 in 2025 and 29 in 2026.

**Caveat on the baseline.** `ensemble_vol40` was designed in phase 1 using data through 2026, so its
test-period numbers below are **in-sample** and serve only as a reference.

## Test-period results (2024-01-01 → 2026-10-24, 2.8 years)

| Strategy (frozen config) | CAGR | Sharpe | Max DD | Exposure | Orders/yr | Fixed alloc. at same exposure: CAGR / Sharpe / DD | P(ΔSharpe>0) | Validation | **Test** | DSR |
|---|---|---|---|---|---|---|---|---|---|---|
| `fixed_33` (benchmark) | 7.3% | 0.48 | −24% | 33% | 46 | — | — | n/a | n/a | 0.04 |
| `breakout_20_atr3_vol40` | 8.2% | 0.42 | −33% | 46% | 31 | 9.4% / 0.48 / −33% | 0.43 | PASS | **FAIL** | 0.03 |
| `meanrev_t100_rsi2_5_h10` | 0.1% | 0.04 | −5% | 3% | 15 | 0.7% / 0.50 / −2% | 0.23 | FAIL | **FAIL** | 0.01 |
| `rotation_l30_k1_r7_nomf` | **−89.7%** | −1.02 | −99.9% | 98% | 62 | 14.8% / 0.52 / −58% | 0.02 | FAIL | **FAIL** | 0.00 |
| Selector: trailing Sharpe | −0.9% | 0.05 | −36% | 35% | — | 7.7% / 0.48 / −26% | 0.08 | FAIL | **FAIL** | 0.01 |
| Selector: regime map | 0.7% | 0.15 | −37% | 45% | — | 9.3% / 0.48 / −32% | 0.15 | FAIL | **FAIL** | 0.01 |
| Gate on baseline (h=20d, z=1.0) | 10.0% | 0.55 | −25% | 32% | 75 | 7.2% / 0.48 / −24% | 0.53 | PASS | **PASS** | 0.05 |
| Breakout, walk-forward params | = breakout (it picked the same config every year from 2022 on) | | | | | | | PASS | **FAIL** | 0.03 |
| Rotation, walk-forward params | −64.4% | −0.43 | −97% | 88% | 155 | 13.9% / 0.51 / −54% | 0.05 | FAIL | **FAIL** | 0.00 |
| Macro overlay (FOMC+CPI, 2d, ×0.5) | 5.6% | 0.36 | −31% | 37% | 154 | 8.0% / 0.48 / −27% | 0.33 | FAIL | **FAIL** | 0.02 |
| *Baseline `ensemble_vol40` (in-sample)* | *11.9%* | *0.60* | *−30%* | *40%* | *113* | | | | | |
| *Buy & hold BTC/ETH* | *15.0%* | *0.53* | *−58%* | *100%* | *0* | | | | | |

(The mean-reversion walk-forward variant gave the same result as mean reversion.)

**Stress tests** (test-period CAGR). The cost stress is 1.25% per side; the delay stress fills 12h after
the daily close; 20% of orders unfilled is the missed-fill stress.

| | Base case | 1.25% cost | 20% missed | +12h delay |
|---|---|---|---|---|
| fixed_33 | 7.3% | 6.9% | 7.3% | 7.7% |
| breakout | 8.2% | 3.1% | 9.7% | **4.7%** |
| meanrev | 0.1% | −3.5% | 0.0% | −0.3% |
| rotation | −89.7% | −89.5% | −89.9% | n/a (no hourly alt data) |
| macro overlay | 5.6% | **−5.8%** | 5.9% | 3.1% |
| gate | 10.0% | **0.0%** | 8.4% | — |
| selector trailing / regime | −0.9% / 0.7% | 3.6% / −6.1% | — | — |
| *baseline* | *11.9%* | *3.2%* | *10.9%* | — |

Gate and selector stress come from `study_test_addon.py`, run after the test on frozen configurations.
Only fixed allocation is insensitive to costs and timing.

**Multiple testing.** 73 configurations were tried in total: 22 in phase 1 and 51 here, all logged.
The variance of per-day Sharpe across trials is 0.0011. **Deflated Sharpe ratio** of every test
result: ≤ 0.05, against 0.95 needed for confidence. With 2.8 years of test data and 73 trials, none of
these results can be distinguished from luck.

## Per strategy

### 1. Fixed allocation — `tradelab.strategies.fixed.fixed(0.33)`
Hypothesis: assume no timing skill. Hold a constant allocation at a chosen risk level and rebalance on
2% drift. The 33% weight was chosen *a priori* to match the baseline's exposure, not searched.
It is the benchmark every other strategy must beat. Test: 7.3% CAGR, −24% max DD, robust to every
stress. On holdouts it is trivially equal to itself. **Verdict: paper-trade (benchmark and candidate).**

### 2. Breakout — `tradelab.strategies.breakout.breakout(20, 3.0)`
Hypothesis: new 20-day highs start persistent moves. One entry per breakout, sized to 40%
volatility at entry, exited by a 3×ATR trailing stop.
- Dev: neighbours were stable (entry 20: Sharpe 1.37–1.55; entry 50: 1.19–1.32).
- Validation: +7.2% against −1.4% for the fixed benchmark (PASS).
- Test: 8.2% against 9.4% (FAIL).
- Holdout: 2 of 3 coins (LTC and ETC beat the fixed benchmark on Sharpe and CAGR, but with much deeper
  drawdowns, e.g. LTC −75% against −44%).
- Most sensitive to execution delay (12h delay: 8.2% → 4.7%).

**Verdict: not promoted. Optional paper shadow for evidence only.**

### 3. Daily mean reversion — `tradelab.strategies.meanrev.meanrev(100, 2, 5.0, 10)`
Hypothesis: liquidity-driven dips inside uptrends partly reverse. All 12 dev configurations were near
zero or negative after costs. It failed validation and test. The holdout "PASS" is uninformative: the
strategy is ~3% invested, so its exposure-matched benchmark is essentially cash. The intraday version
was not revisited, because phase 1 showed no gross edge even before fees. **Verdict: reject.**

### 4. Cross-asset rotation — `tradelab.strategies.relative.rotation(30, 1, 7, False)`
Hypothesis: coins with the strongest recent risk-adjusted momentum keep outperforming.
- Dev: highly parameter-sensitive (Sharpe −0.13 to 1.12), with drawdowns of −68% to −95% everywhere.
- Validation and test were catastrophic: −89.7% a year in the test period.
- Diagnosis: not a data artefact. Before costs, the held coins compounded to −69% (2024), −94% (2025)
  and −49% (2026). The strategy bought recent pumps (ZEC, VVV, PUMP, ...) just before they reversed,
  then paid $261 in fees chasing them. The walk-forward version, which changed parameters yearly, was
  also catastrophic (−64% a year).

**Verdict: reject.**

### 5. Scheduled macro-event overlay — `tradelab.strategies.calendar.event_overlay`
Uses the official calendar built by the events pipeline (`data/events/macro_calendar.csv`): 327
BLS/Federal Reserve events, of which only those with `known_in_advance` = True are used. Hypothesis:
cutting exposure into scheduled FOMC/CPI releases lowers risk more than return. Mechanics: it halves
exposure for 2 days before each release, which adds ~40 round trips a year and doubles the order count.
- Validation and test: FAIL.
- Holdout: 0 of 3 coins.
- Under 1.25% costs: −5.8%.
- Ablation: the overlay applied to the baseline returns 5.6%, against 11.9% for the baseline without
  it, so it **hurts**.

This tests the *calendar* only. Release content (the surprise versus expectations) was not tested,
because no licensed point-in-time consensus data exists here. **Verdict: reject.**

### 6. Regime detection / strategy selection — `tradelab.strategies.regime`
Two selectors chose among the baseline, fixed 33% and cash, both walk-forward with yearly refits,
switching costs and minimum holding times:
- **trailing Sharpe**: pick the candidate with the best trailing 1-year Sharpe;
- **regime map**: map BTC trend × volatility regimes to the best candidate per regime, holding each choice at least 20 days.

Both failed validation and test. Each was worse than *either* of its own components (fixed: 7.3%;
baseline: 11.9%; selectors: −0.9% / 0.7%). Selection added switching costs and chased stale winners.
**Verdict: reject. A fixed approach is better.**

### 7. Evidence-based trade gate — `tradelab.research.gate`
For each state (trend vote × volatility tercile), the gate estimates from past data only:
- the expected 20-day return from the next open;
- its standard error, using the effective number of non-overlapping observations;
- the probability of a gain and the average loss.

The training data ends 22 days before each test year (an embargo). A state is approved only if
mean − z·se exceeds the 1.32% round-trip cost.

| Result | |
|---|---|
| Test vs fixed at same exposure | 10.0% vs 7.2% CAGR, Sharpe 0.55 vs 0.48 → pre-registered **PASS** (P(ΔSharpe>0) = 0.53, a coin flip) |
| Test vs the ungated baseline (ablation) | Median ΔSharpe −0.04, ΔCAGR −1.6%; P(gate better) 0.41 |
| 1.25% cost stress | 0.0% CAGR |

**Calibration (2022+, out of sample, overlapping 20-day labels):**

| Predicted P(gain) bin | Days | Predicted P(gain) | Realized P(gain) | Predicted mean | Realized mean |
|---|---|---|---|---|---|
| ≤0.45 | 612 | 0.40 | 0.51 | −2.4% | +2.7% |
| 0.45–0.50 | 461 | 0.48 | 0.41 | −0.5% | −2.4% |
| 0.50–0.55 | 459 | 0.52 | 0.63 | +6.5% | +3.4% |
| 0.55–0.60 | 611 | 0.56 | 0.45 | +6.7% | −0.5% |
| 0.60–0.65 | 1236 | 0.63 | 0.49 | +10.5% | +1.9% |
| >0.65 | 95 | 0.71 | 0.40 | +17.2% | +1.8% |

Predicted probabilities do not rank outcomes, and predicted returns overstate realized returns 3–10×.
**Verdict: do not use it to approve trades.** The mechanism (cost-aware approval with an uncertainty
penalty) is sound and tested. The inputs simply carry no reliable information. Keep logging its
predictions in paper trading to re-check calibration prospectively.

## Business-level results ($1,000 account, test period, bootstrapped, before taxes)

| | Gross $/yr: 5th pct / median / 95th pct | P(gross > 0) | Net median, daily GitHub Actions job ($0) | Net median, $6/mo VPS | Net median, VPS + $60/yr LLM |
|---|---|---|---|---|---|
| fixed_33 | −$117 / $67 / $277 | 0.72 | $67 | −$5 | −$65 |
| baseline (in-sample) | −$138 / $97 / $476 | 0.72 | $97 | $25 | −$35 |
| breakout | −$185 / $67 / $459 | 0.65 | $67 | −$5 | −$65 |
| gate | −$129 / $83 / $424 | 0.70 | $83 | $11 | −$49 |
| buy & hold | −$332 / $136 / $874 | 0.65 | $136 | $64 | $4 |
| rotation | −$970 / −$899 / −$605 | 0.00 | −$899 | −$971 | −$1,031 |

At $1,000, a $72-a-year server equals the whole median edge of every daily strategy. The daily
strategies don't need one: the audit showed that a 12h fill delay costs only ~1.4% a year for the
baseline. **Run the daily decision as a scheduled job ($0). Add no paid LLM inference until a news
feature shows evidence in prospective paper trading.** Taxes on each rebalance are not modelled.

## Recommendation for paper trading (ranked)

1. **`fixed_33`**: `from tradelab.strategies.fixed import fixed; fixed(0.33)`. Primary candidate and benchmark.
2. **`ensemble_vol40`**: `from tradelab.strategies.trend import BASELINE`. The preserved baseline to
   beat. Its only evidence is in-sample, and out of sample it lost to fixed allocation on holdout coins.
3. *(optional shadow, not a money candidate)* **`breakout_20_atr3_vol40`**:
   `from tradelab.strategies.breakout import breakout; breakout(20, 3.0)`. Fewer orders (31/yr);
   passed validation and holdout, failed the pre-registered test.
4. Log only, never trade on: gate predictions (`tradelab.research.gate.walk_forward_gate`, horizon 20,
   z 1.0), for prospective calibration.

Settings: BTC-USD and ETH-USD as 50/50 independent sleeves, decision on the 00:00 UTC daily close,
long-only spot, 2% rebalance band. **Rejected:** mean reversion, rotation (both variants), both
selectors, the macro-calendar overlay.

**Evidence a strategy needs before real money** (suggested): at least 6 months of paper trading
in which it beats `fixed_33` at the same exposure after fees, with realized slippage within the
modelled 6 bp, and no risk-limit breach.

## Known issues
- **Engine bug (FIXED 2026-10-25, regression test `test_missing_close_carries_last_price_not_zero`; audit re-run, only change universe buy-and-hold Sharpe 0.5025 → 0.5014):** `tradelab/research/engine.py` `simulate()`
  valued a held asset at **0** on any bar where its close is NaN (`mark = np.where(np.isnan(c[i]), 0.0, c[i])`).
  It should carry the last price. Every study here forward-fills gaps before calling the engine. Measured
  on the audit's universe test (BCH has 4 missing days in Nov 2018), the impact is negligible
  (buy-and-hold Sharpe 0.502 vs 0.501; PASS unchanged; `research/study_engine_nan_check.py`).
  A single-asset series reindexed to a calendar with gaps shows a fake −100% drawdown.
- The dev run was interrupted at its last step: the macro calendar appeared mid-run with a different
  schema. The 47 trials already logged were reused, not re-run (`dev_finish`), so the trial count is not inflated.
- Rotation slippage for altcoins (0.80% per side) is an assumption. Thin books could make it worse.
- The test period is 2.8 years, one market cycle at most. Bootstrap intervals are wide.
