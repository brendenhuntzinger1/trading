# Audit of the research conclusions and the actual bottleneck

Date: 2026-10-25. Reproduce:
- `research/intraday/audit/dsr_audit.py`: the statistic
- `research/intraday/audit/periods.py`: effects with confidence intervals by period
- `research/intraday/s2x/run.py`: the replication; it refuses to re-run

## 1. What "DSR 0.00 vs 0.95" measured

**The statistic.** The deflated Sharpe ratio (Bailey & López de Prado, 2014) is the probability that a
strategy's true Sharpe ratio exceeds the Sharpe that the *best of N strategies with no skill* would show by
luck. It is the probabilistic Sharpe ratio (PSR) evaluated against a raised benchmark SR₀:

- PSR(SR₀) = Φ( (SR − SR₀) · √(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) )
- SR₀ = √V · [ (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ], with γ ≈ 0.5772

**Inputs as implemented** (`tradelab/research/metrics.py`):
- SR: the per-day Sharpe ratio of the strategy's **net** daily P&L, with no-trade days counted as zero.
- T: the number of days.
- γ₃, γ₄: skewness and kurtosis of the daily P&L.
- N: the number of configurations tried. The **91** = 22 (daily phase 1) + 51 (daily phase 3) + 11 (stock
  intraday) + 7 (crypto intraday). N enters **only** through SR₀, which grows roughly like √(2 ln N).
- V: the variance of per-day Sharpe ratios across trials. Two values were used: 0.0066 (across the six
  intraday test configs) and 0.0278 (the stock worker's development trials).
- 0.95 is a pre-registered threshold, not a property of the method.

**Assumptions:**
- the N trials are independent, unskilled draws;
- V reflects luck only;
- returns are stationary;
- the skewness and kurtosis correction is adequate.

**What the audit found:**

1. **The reported 0.00 does not come from the 91 trials.** Five of the six strategies have *negative* net
   Sharpe, so they fail at N = 1. S2-ETF fails at N = 1 too: PSR vs 0 is 0.73. The multiple-testing
   adjustment was never the deciding factor.
2. **SR₀ was over-stated.** With V = 0.0066 or 0.0278, the "best lucky trial" benchmark is an annual Sharpe
   of 3.2–6.6. That is implausibly high, because the dispersion across trials mostly reflects different
   **costs** (deterministic), not luck, and it mixed daily-crypto with intraday-stock Sharpe ratios. With the
   textbook null variance V = 1/T, SR₀ at N = 91 is 1.0–2.3 annually. The verdict is unchanged.
3. **N = 91 over-counts.** Those configurations span different markets, frequencies and families, and many are
   correlated, so the effective number of independent trials is smaller. This makes the adjustment
   conservative. It is irrelevant here (see 1).
4. **The tails are extreme:** S2-ETF has kurtosis 176 and skew 5. The normal-based PSR is fragile under such
   tails, so block-bootstrap intervals (below) are the more reliable uncertainty measure.

| Strategy (test) | Days | Net Sharpe (90% CI) | PSR vs 0 (N=1) | DSR, null var, N=6 | DSR, null var, N=91 | Sharpe needed for 0.95 at N=91 |
|---|---|---|---|---|---|---|
| S1 | 304 | −2.57 (−4.13, −1.01) | 0.003 | 0.000 | 0.000 | 3.8 |
| S2 stocks+ETFs | 1,515 | −0.14 (−0.82, 0.53) | 0.36 | 0.05 | 0.002 | 1.7 |
| S2 ETF-only | 1,512 | +0.24 (−0.41, 0.89) | 0.73 | 0.23 | 0.024 | 1.7 |
| C1 | 1,010 | −4.14 (−4.63, −3.65) | 0.000 | 0.000 | 0.000 | 3.0 |
| C2 | 1,016 | −1.17 (−2.33, −0.01) | 0.05 | 0.003 | 0.000 | 2.4 |

### Insufficient evidence vs evidence of no useful effect

This is judged on the **gross** effect per trade against the base round-trip cost. CIs come from a
stationary bootstrap over trading days.

| Strategy | Period | Trades | Gross bp (90% CI) | Reading |
|---|---|---|---|---|
| S1 | dev / val / test | 1,427 / 724 / 1,445 | 0.8 (−2.3, 3.8) / −1.8 (−5.9, 2.3) / 2.0 (−2.3, 6.1) | **No useful effect**: upper bound < 8 bp in every period |
| S2 stocks | dev / val / test | 10,940 / 3,488 / 5,732 | 27.7 (21.8, 33.8) / 6.3 (−2.1, 14.7) / 6.2 (−2.0, 14.2) | Real in 2000–2015; after that **insufficient evidence** (CI straddles 8 bp) |
| S2 ETF-only | dev / val / test | 512 / 227 / 548 | 23.6 (−1.5, 49.0) / 14.4 (−8.5, 37.6) / 12.6 (2.3, 23.0) | Gross > 0 in the test; insufficient evidence vs cost |
| **S2X: 29 new ETFs** (pre-registered, untouched) | 2016–2026 | 4,692 | **−2.7 (−8.9, 3.9)**; 95% upper 4.8 | **No useful effect.** S2-ETF did not generalise |
| C1 | dev / val / test | 221 / 70 / 212 | 1.5 (−14, 16) / 22.7 (−1, 43) / 2.7 (−13, 19) | **No useful effect** vs a 106 bp round trip |
| C2 | dev / val / test | 88 / 32 / 74 | 46.7 (−34, 128) / 60.6 (−6, 131) / 35.3 (−31, 99) | **No useful effect at retail cost** (upper < 132 bp). A small positive drift is not excluded |

**Correction to my earlier statement.** I wrote that a clean negative ORB result "would settle whether intraday
US stock trading is worth pursuing at all." That was wrong. One rejected hypothesis says nothing about
untested ones. These results reject **specific rules at specific costs with specific data**. They do not show
that intraday trading cannot work.

## 2. The actual bottleneck, per strategy

✔ = the primary cause; ◐ = contributes; — = not the issue.

| Strategy | No predictive signal | Signal < costs | Too few observations | Inadequate data | Unrealistic execution | Worked only in one period |
|---|---|---|---|---|---|---|
| S1 intraday momentum | ✔ gross ≈ 0 in all 3 periods | — | — | ◐ hourly bars force 10:30, not 10:00 | ◐ fill at the 15:30 first trade is assumed | — |
| S2 gap reversal, stocks | ◐ now ≈ 6 bp | ✔ 6 bp < 8 bp | — | ◐ survivorship inflates 2000–2015 | ◐ opening spread assumed | ✔ 28 bp → 6 bp after 2015 |
| S2-ETF | ✔ did not replicate on 29 new ETFs | ◐ | ◐ (548 trades) | — | ◐ opening spread assumed | ◐ |
| S3 / ORB | unknown | likely: the paper's own +0.08R ≈ 2–5 bp vs 20 bp | — | ✔ needs consolidated (SIP) minute data, unverified | ✔ the paper charged no spread or slippage | unknown (paper sample only) |
| C1 cascade reversal | ✔ gross ≈ 0 | — | — | ◐ no order-book or liquidation data | ◐ maker queue unmodelled | — |
| C2 crypto momentum | ◐ (+35–61 bp, CIs include 0) | ✔ ≤ 61 bp vs 132 bp | ✔ (74 test trades) | — | — | — |
| Daily trend/rotation (phase 3) | ✔ vs fixed allocation | ◐ | — | — | — | ◐ |

**The bottleneck across the board is the absence of a signal whose gross effect clearly exceeds realistic
retail costs.** Execution speed, extra AI models, more features and more infrastructure address none of the
rows above. The second-order bottleneck is **data**: everything testable so far uses daily, hourly or
5-minute bars without quotes, so execution cost is assumed, never measured.

**What is worth investigating next, and why:**
- **Highest value: measuring real execution cost** (spreads and slippage at the moments we'd trade) for one
  candidate. Every borderline result (S2 stocks, S2-ETF, ORB, C2 at maker fees) turns on a cost
  number we have assumed. A cost measurement changes the verdict on several hypotheses at once, while a new
  signal changes only one.
- **Most informative new signal: ORB on stocks in play**, run only after SIP access is verified. It is
  pre-registered, with power to reach a clear verdict. Expectations should be low: the paper's average edge
  is roughly at our cost level.
- **Not worth more effort at this account size:** crypto intraday at retail fees. Break-even needs ≤ ~0.2% per
  side, below any Coinbase retail tier.
