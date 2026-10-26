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
