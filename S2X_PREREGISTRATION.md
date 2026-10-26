# S2X: does the ETF gap reversal generalise to ETFs never examined? (pre-registration)

Written 2026-10-25 **before any data for these symbols was downloaded or viewed**.

## Why this experiment (from RESEARCH_AUDIT.md)
S2-ETF is the only intraday strategy with a gross effect that is positive in every period: dev 23.6 bp,
validation 14.4 bp, test 12.6 bp, with the test 90% CI [2.3, 23.0] bp excluding zero. Its bottlenecks are:
- **too few observations:** 548 test trades, net Sharpe CI [−0.41, +0.89];
- **uncertain execution cost** at the open: break-even 12.6 bp vs an assumed 8 bp round trip.

New, never-examined ETFs add independent observations without reusing any data we have already seen.

## Economic hypothesis
Opening gaps in ETFs that are large relative to the market's own gap partly reverse during the session,
because opening order imbalances (retail market-on-open flow, and ETF prices adjusting to stale foreign
or overnight information) are absorbed by intraday liquidity providers, who are paid for it.

## Universe (fixed now, by rule, not by performance)
Unleveraged, non-inverse US-listed ETFs that are well-known liquid benchmarks in their category and listed
before 2014. None of them has been downloaded or examined in this project.
- **Primary family (equity):**
  - country: EFA, EEM, VWO, EWJ, EWZ, FXI, EWG, EWU, EWC, EWY, EWT, EWA, EWH, EWW
  - industry: SMH, XBI, IBB, KRE, KBE, XOP, OIH, XME, XRT, XHB, ITB, GDX, GDXJ, IYR, VNQ
- **Secondary family (labelled; different overnight dynamics):** TLT, IEF, HYG, LQD, GLD, SLV, USO
- **Excluded:** symbols already used (SPY as the reference only, QQQ, IWM, DIA, the 11 sector SPDRs) and any
  leveraged or inverse product.
- Eligibility is applied point-in-time by the engine: previous close > $10 and 20-session median dollar
  volume > $50M (minimum 15 sessions).

## Rules: S2 exactly as frozen (`intraday_stocks_frozen:S2_etf_only_thr1_top5`), no changes
- **Signal:** gap g = (open / previous close − 1) − SPY's same gap. Eligible if g ≤ −1% and |g| < 50%.
- **Entry:** buy the 5 most negative g right after the opening print, at the official open plus the entry cost.
- **Exit:** at the official close (MOC).
- **Size:** weight 0.20 each, at most 5 positions, no stop, holding one session, gross exposure ≤ 1×, long-only.

## Data and exclusions
- Yahoo daily OHLCV, split-adjusted, 2016-01-01 → 2026-10-23.
- A symbol-day is used only if the open and close exist. No manual exclusions after viewing.

## Costs
- Entry 5 bp and exit 3 bp (8 bp round trip, base).
- Stress: 15 + 9 = 24 bp.
- Opening-spread sensitivity: 10 bp entry (13 bp round trip).
- SEC fee 0.21 bp is inside the exit cost (verified). Measured opening spreads are not available (see docs/ALPACA_DATA_AUDIT.md).

## Benchmarks
- Cash, which is the same as being flat overnight.
- SPY open→close on the same days.
- A placebo: the same count of random ETF-days drawn from the eligible pool with the same entry and exit times
  (≥ 1,000 replications).

## Evaluation period and overlap
2016-01-01 → 2026-10-23. **These symbols are untouched.** The calendar period overlaps windows already
studied with other symbols (2016–2026), so general market conditions in that period are known to us. Any
regime-level confound (e.g. 2020) is shared with the S2-ETF result and is not independent. Only the
cross-sectional evidence is new.

## Decision criteria (primary family; the secondary family is reported but cannot pass)
- **Gross signal replicates:** 90% day-bootstrap CI of gross per trade lies above 0. If it doesn't, S2-ETF's
  gross effect is not confirmed.
- **PASS (backtest evidence of an advantage):** E1–E7 from INTRADAY_HYPOTHESES.md at the 8 bp base, with:
  - E6 computed with the textbook null variance (1/T) and N = 92 (91 prior + this one);
  - E3 also requiring net > 0 at the 13 bp opening-spread sensitivity.
- **REJECT (evidence of no useful effect):** 95% upper bound of gross per trade below the 8 bp base round trip.
- **INCONCLUSIVE:** anything else.
- **Pooled reading (reported, not a pass criterion):** pooling S2-ETF test and S2X trades shows whether the
  combined evidence crosses E1/E2. It reuses already-seen S2-ETF data and is labelled as such.

## Power
Expected about 600–1,500 trades in 10 years (estimate; not yet seen). At the S2-ETF test dispersion
(trade SD ≈ 1.3%), 1,000 trades give a 90% CI half-width of about ±7 bp on gross per trade. That is enough
to separate a 13 bp effect from 0, but **not** enough to separate it from 8 bp. A net verdict of "inconclusive"
is therefore the most likely result if the effect is real, and this is stated before running.
