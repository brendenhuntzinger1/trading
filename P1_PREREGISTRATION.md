# P1: cross-sectional crypto return prediction (pre-registration)

Written 2026-10-26 **before any model was fit or any label inspected**. The data volume, eligibility counts
and the data audit were seen beforehand. Run: `research/p1/study.py dev | validation | final`.
The final phase refuses to run twice; `--reproduce` re-computes a finished phase deterministically.

## Question
Can price, volume, volatility, relative-strength and breadth features, observable at the decision time,
rank liquid Coinbase coins well enough that the top-ranked ones earn more than costs over the next day
(P1a) or week (P1b)? This tests **prediction plus decision**, not a hand-written setup.

## Economic hypothesis
Crypto shows trend continuation, short-term reversal and liquidity/volatility effects. In equities these
are the strongest predictor families in Gu, Kelly & Xiu (2020); RESEARCH_PROGRAM.md covers that paper and
the weaker evidence for crypto. Coins have large cross-sectional dispersion relative to costs, so a
modest ranking skill could clear costs where intraday stock effects (a few bp) cannot.

## Universe, timing, decisions
- **Universe:** Coinbase USD spot, point-in-time eligible on the decision date
  (`tradelab.pit.crypto_universe.eligible_at`):
  - traded the previous day;
  - ≥ 60 days of history;
  - 30-day median dollar volume ≥ $10M, computed before the date;
  - no stablecoins or wrapped tokens;
  - XRP excluded during its 2021–2023 suspension.
- **P1a (primary):** decide daily at 00:00 UTC; hold 24 h; time exit.
- **P1b (secondary):** decide Mondays 00:00 UTC; hold 168 h; time exit.
- **Information:** only hourly bars that ended at or before the decision time. Entry is at the open of the
  bar starting at the decision time, and the exit is the close of the last bar in the horizon. Any outage
  or no-trade gap inside the horizon removes the sample: no fills are invented.
- **Features** (`tradelab/predict/panel.py`, 7 families): returns, candle, volume, volatility, trend/VWAP,
  relative strength (vs BTC, cross-sectional ranks), breadth.
- **Labels:** forward return over the horizon; whether a target at +1 σ is hit before a stop at −1 σ
  (σ = trailing 7-day volatility scaled to the horizon; a stop and target in the same bar count as the stop);
  worst adverse move (MAE).

## Models (P1a: 5 configurations; P1b: 3). The model trial budget is final
| Id | Model | Target | Notes |
|---|---|---|---|
| B1 | Momentum rank: score = r_7d | n/a | No fitting. The simple-rule benchmark |
| B2 | Short-term reversal: score = −r_24h | n/a | No fitting |
| M1 | Ridge (α = 100), standardised, fit in-fold | forward return | Regularised linear |
| M2 | Logistic (C = 0.05) | target before stop | Probability; calibration reported |
| M3 | Gradient-boosted trees (depth 3, ≥ 200 per leaf, 200 iterations) | forward return | |

P1b uses B1, M1 and M3. No-skill references (zero forecast, base rate, random picks) are benchmarks, not trials.

## Decision policy (identical for every model)
- At each decision time, rank the eligible coins by score and take the **top 3**, equal weight.
  The weight per position is 1/3 of the capital in the cohort.
- Return-predicting models (M1, M3) **abstain** from any coin whose predicted return ≤ the round-trip cost.
- Long-only spot, no leverage.
- Exits are not optimised in P1: fixed time exit only. Exit research is a separate, later question.

## Costs (per round trip)
- **Base 1.32%:** Coinbase taker, 0.60% fee + 0.06% spread/slippage per side. The fee is **unverified**
  (docs/FEES_VERIFIED.md).
- Reported grid: 0.50%, 0.80%, 1.06%, 1.32%, 1.92%, 2.52%. The low end is for a hypothetical cheaper venue
  or fee tier. It is labelled as such, and Alpaca crypto (verified 0.15/0.25%) runs a different venue with
  unmeasured spreads.

## Periods and overlap
| Phase | Dates | Use |
|---|---|---|
| Development | 2021-03-01 → 2024-06-30 | 5 purged expanding folds (embargo = horizon); configuration comparison; PBO |
| Validation | 2024-07-01 → 2025-06-30 | Models fit on dev, predicting validation. Confirms only; selects nothing |
| Final historical evaluation | 2025-07-01 → 2026-10-24 | Opened once, models fit on dev+val, configuration frozen beforehand |
| Prospective | from deployment | Forward paper trading: the only truly untouched test |

**Overlap, disclosed:**
- The phase-3 rotation study (RESEARCH.md) traded daily momentum across these coins over 2018–2026. B1
  resembles it, and the final window's dates and instruments were examined there at daily resolution.
- C1/C2 examined BTC/ETH/SOL 5-minute data over the same dates.
- So the final historical window is **not untouched**. A pass there is necessary but not sufficient; only
  prospective paper trading counts as unseen evidence.

## Free gate (development data only, before any model is compared)
Compute the median daily cross-sectional standard deviation σ_xs of 24h forward returns. With a top-3 pick,
the required rank skill to clear costs is roughly IC ≈ cost / (σ_xs · 1.0). If the required IC exceeds 0.15
(implausible in published work), stop P1a before modelling. Same rule for P1b at 168h.

## Selection, before the final phase
The candidate is chosen from M1–M3 by development out-of-fold net Sharpe at base cost. It must also:
- beat both B1 and B2 in development;
- have a validation net per trade ≥ 0.
If none qualifies, the final phase still runs all configurations for the record, but **no candidate can pass**.

## Pass, inconclusive, reject (final phase, candidate only, base cost)
- **PASS**, all of:
  - mean net per trade, 90% lower bound > 0 (day-block bootstrap);
  - annualised Sharpe ≥ 0.5;
  - ≥ 2 of 3 thirds positive;
  - beats matched random picks (p < 0.05);
  - beats B1 on paired daily P&L (90% CI of the difference > 0);
  - PBO ≤ 0.05 on the development trial matrix;
  - deflated Sharpe ≥ 0.95, null variance, N = 92 + 8;
  - ≥ 100 trades;
  - for M2: Brier skill > 0 and ECE ≤ 0.05.
- **REJECT (no useful effect):** 95% upper bound of the candidate's gross excess return over the
  equal-weight universe < the base round trip.
- **INCONCLUSIVE:** anything else.

A pass would authorise only: freezing the model, 3+ months of forward paper trading, and reporting.
Nothing here enables live trading.

---

# Amendment 1 (2026-10-26, before any model was fit or any P1 label was inspected)

The original text above is kept unchanged and its hash stays registered (`prereg_p1`). The sections
below **supersede** it where they conflict. They answer eight review points made before the run.
Nothing below was chosen after looking at P1 outcomes.

## A1. What P1 is, and what it is not
P1 tests one narrow component of the objective: **can a cross-sectional score choose which liquid coins
to hold for the next day or week better than holding them all, after Coinbase costs?** It is not the
day-trading objective. Its entry/hold/exit/no-trade decisions are deliberately crude: enter the top 3,
keep a coin while it stays in the top 3, otherwise exit, and abstain when the expected return does not cover
costs. A pass makes a component worth a forward paper trial. It does not make an autonomous trader.

## A2. Development stopping check (replaces "Free gate")
Large dispersion between coins says nothing about whether winners can be *predicted*. Choosing the
winners after the fact (an oracle) is only an upper bound. The check asks a narrower, falsifiable question:
**on development data, how strong would a ranking signal have to be just to break even after turnover
and costs?** If that strength is implausible, modelling at this horizon and cost is pointless.

Per decision period t (daily for P1a, weekly for P1b), with E_t the eligible coins:
- U_t = equal-weight mean forward return of E_t;
- O_t = mean forward return of the 3 coins that turned out best, minus U_t (the oracle's gross
  *selection* excess: the most any long-only top-3 selection could add over holding everything);
- S_t(ρ) = gross selection excess of a **synthetic signal** with rank correlation ρ to the outcome:
  - score = ρ·z + √(1−ρ²)·ε, where z is the normal score of the realised cross-sectional rank and ε is
    independent noise;
  - top 3 by score, averaged over 200 noise draws.

  This uses the empirical, fat-tailed distribution and makes no Gaussian assumption.
- C(τ) = cost per period = τ × round trip, where τ = Σ|Δw| / 2 is the one-way turnover per period
  (τ = 1 means every position is replaced).

The **required skill** ρ*(τ, cost) is the smallest ρ on a 0.01 grid with mean S_t(ρ) ≥ C(τ). It is
reported for three turnover cases:
- τ = 1, the full replacement a noisy signal produces;
- τ = the realised turnover of B1 momentum under the A4 policy on development data. B1 is a persistent
  rule with no fitting, so its turnover is what a slow signal would need;
- τ = 0.25, an illustrative slow signal.

All three cases are reported at every grid cost.

**Stopping rule:** stop the horizon before any model comparison if ρ*(B1 turnover, base cost) > 0.15, or if
the oracle bound is below the cost even at B1 turnover. Rank ICs above about 0.10, sustained over years
out of sample, are rare in published cross-sectional work, so 0.15 is a deliberately generous ceiling.

**What a stop would rule out:** long-only top-3 selection among Coinbase's liquid coins at this horizon and
these assumed Coinbase taker costs, by any signal of realistic strength. That conclusion depends on the
synthetic signal capturing selection excess the way a real one would. Real signals may do worse in the
tails, which makes the check lenient and a stop robust.

**What a stop would not rule out:**
- lower costs (maker orders, fee tiers);
- slower or longer-horizon policies;
- market timing (in or out of crypto altogether, which is a no-trade decision versus the universe);
- shorting;
- event-driven or intraday approaches;
- the possibility that the features carry information too small to trade here.

**A pass means only that modelling is not hopeless.** It is not evidence of predictability.

## A3. Venues and costs
- Every historical result is a **Coinbase** result: Coinbase hourly prices, the Coinbase point-in-time
  universe, Coinbase costs. Base: 1.32% round trip, made of an **assumed, unverified** 0.60% taker fee
  plus 0.06% spread and slippage per side.
- Grid: 2.52% (stress: a 1.20% taker tier plus slippage), 1.92%, 1.32% (base), 1.06%, 0.80% and 0.50%.
  The values below base are **hypothetical lower Coinbase fee levels**, for sensitivity only.
- No result is reported as Alpaca evidence. Alpaca's published fees fall near the low end of the grid,
  but executable Alpaca profitability would need Alpaca's own instrument list, prices, spreads and fills,
  none of which P1 uses.
- Costs are charged on actual weight changes: |Δw| × round trip / 2.

## A4. Decision policy (replaces "Decision policy"; the same for every score)
At each decision time t:
1. Rank the eligible coins by score; the target set is the top k = 3.
2. **Abstain** (return-predicting models M1 and M3 only): a coin not currently held enters only if its
   predicted return exceeds the round trip; a held coin stays only if its predicted return is > 0.
   Unused slots are cash, which is the no-trade decision.
3. **Hold:** a held coin that is still in the target set stays, with no trade and no cost.
   **Exit:** a held coin that left the target set, or is no longer eligible, is sold at the decision price.
   **Entry:** new target coins are bought at the decision price.
4. Each filled slot carries 1/3 of capital. Long-only, no leverage.

Prices: the decision price is the open of the bar starting at t, or the last close if that hour has no
candle. A coin's period return is the last available close at or before t + horizon − 1 h, divided by
the decision price.
- An hour with no candle on Coinbase means no trades occurred, so the price is carried forward.
- This **replaces** "a gap removes the sample". Dropping coins whose *future* window has gaps conditions
  selection on the future, which is a look-ahead.
- Barrier labels (M2's target) still require contiguous bars, and are used only for training and
  calibration.
- The number of carried-forward hours is reported.

The **time-exit** variant from the original text, where every position closes after one horizon, is
reported as a sensitivity. It is never used for selection.

## A5. Comparators, at comparable risk
Every phase reports, on the same periods and net of the same Coinbase costs:
- **No trade:** cash, return 0.
- **EW universe:** equal weight across all eligible coins, rebalanced each period, costs on actual turnover.
- **Passive BTC:** buy and hold BTC-USD, one entry cost.
- **B1 momentum top-3:** the simple-rule benchmark, under the same A4 policy.
- **Matched random top-3:**
  - a random score each period under the same A4 policy, with the same number of filled slots per
    period as the strategy it is matched to;
  - 500 draws;
  - compared on **gross** return, so it isolates selection skill from turnover.

**Risk comparison:**
- volatility, beta and alpha against EW universe returns (r = α + β·r_EW), with a block-bootstrap CI on α;
- Sharpe; maximum drawdown;
- returns scaled to EW-universe volatility.

**Does picking 3 coins add value, or only concentrate risk?** Answered by:
- the alpha against EW;
- the comparison with random 3-coin portfolios, which carry the same concentration with no skill.

## A6. Dependence
- Only one row per (decision time, coin) is used. Hourly bars are inputs, not samples.
- P1a decisions are 24 h apart with 24 h holds, and P1b decisions are 168 h apart with 168 h holds, so
  **labels do not overlap** across decisions.
- Coins on the same date share market moves. **All inference runs on per-period portfolio returns**,
  one number per day or week, or on per-period rank ICs:
  - stationary block bootstrap;
  - mean block 10 days for P1a and 4 weeks for P1b;
  - 90% intervals.
- The number of periods (the effective sample size) is reported, not the number of rows.
- Folds are purged by label end with an embargo equal to the horizon. The final fit on dev + validation
  drops rows whose labels end within one horizon of the final start.
- P1b has about 175 development weeks, so it is low-powered and labelled as such.

## A7. The final historical period is not untouched
The overlap disclosure above stands: the final window's dates and coins were examined by the rotation and
C1/C2 studies. "Final historical evaluation" means opened once for P1, never "unseen".
- **Freeze:** before any prospective evaluation, the selected configuration is written to
  `research/p1/frozen/`, refit on all data to 2026-10-24, with the model file, its SHA-256 and the commit.
- **Prospective log:** predictions are appended to `research/p1/prospective/predictions.jsonl`, with the
  decision time and the frozen model's hash, **before** the period's outcome exists. Outcomes are scored
  only after the period ends. The log is append-only, and a test checks that no prediction is written
  after its own decision time.
- If no candidate qualifies, nothing is frozen for trading. Logging B1 and the EW universe forward may
  continue as monitoring only.

## A8. Reported decision quality (every configuration, every phase)
- Net and gross return per period;
- Sharpe and maximum drawdown;
- turnover, exposure and abstention rate;
- the cost grid;
- results by year and by thirds;
- per-coin concentration, and the share of P&L from the top 1% and top 5% of position-periods;
- rank IC per period with a CI;
- calibration:
  - M2: Brier skill against the base rate, ECE, a reliability table;
  - M1 and M3: decile reliability of predicted against realised return, and the realised-on-predicted slope;
- **Abstention value** (M1, M3): the same model forced to fill all 3 slots, compared on the same periods,
  and the forced version's returns on the periods the abstaining version skipped.

## A9. Pass criteria (replaces "Pass, inconclusive, reject"; final phase, the candidate only, base Coinbase cost)
**PASS** requires all of:
1. per-period net return, 90% lower bound > 0;
2. annualised Sharpe ≥ 0.5;
3. ≥ 2 of 3 thirds positive;
4. **alpha against the EW universe**, 90% lower bound > 0;
5. gross return above the 95th percentile of matched random top-3;
6. beats B1 on paired per-period net P&L (90% CI of the difference > 0);
7. PBO ≤ 0.05 on the development trial matrix;
8. deflated Sharpe ≥ 0.95 (N = 100 trials, null per-period SR variance 1/T);
9. ≥ 100 position-entries;
10. for M2: Brier skill > 0 and ECE ≤ 0.05.

**REJECT (no useful effect):** the 95% upper bound of the candidate's gross selection excess per period
(its gross return minus the EW universe) < its own cost per period at base cost.

**INCONCLUSIVE:** anything else.

A PASS authorises only: freezing the model, at least 3 months of prospective paper logging under A7, and a
report. Nothing in P1 enables live trading.

## A10. Implementation notes (fixed before any run)
- **Selection excess** in A2 and A9 is exposure-matched: gross_t − (filled slots_t / 3) × EW gross_t.
  A strategy sitting partly in cash is compared with the same fraction of the universe, so abstention is
  neither rewarded in falling markets nor penalised in rising ones.
- **Rebalancing:** a held position is reset to 1/3 each period, and the drift trade is charged.
  Net per period = (1 − cost)(1 + gross) − 1.
- **Development comparisons** (all configurations, comparators, PBO) use only periods covered by the
  out-of-fold test blocks, so every configuration is scored on identical periods. The A2 check uses all
  development periods.
- **Folds** are built over decision periods, not rows, so a date is never split across folds.
  A training row needs label_end < first test period − one horizon.
- **Annualisation:** √365 per day for P1a, √52 per week for P1b.
- **Random seeds** are fixed (noise 11, random portfolios 13, bootstrap 3), and gradient-boosting
  random_state = 0.
