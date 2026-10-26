# When an "intelligent" component may be added

**Precondition for every row:** a base strategy that has at least reached *inconclusive*, with positive gross
evidence. Today none qualifies: S2-ETF was rejected by S2X. So **no addition below is scheduled**. Adding
filters to a strategy with no edge only creates new ways to overfit.

**Method, identical for each candidate:**
- add exactly **one** component to a frozen base;
- register the comparison in advance;
- evaluate the base and base + component on the same untouched period, with a paired day-block bootstrap of
  the difference;
- one component per experiment: no stacking, and no interaction claims.

| Candidate | Information it contributes | Why it might help | Data and running cost | Test of incremental value | Removed if |
|---|---|---|---|---|---|
| News and event flags (built, off) | Scheduled macro releases; venue incidents; official regulatory actions | Avoid entries when a known catalyst dominates (e.g. CPI at 08:30 ET before a 09:30 entry) | $0 for official feeds. A paid model to label headlines: ~$1.30/mo (Haiku est.) – $50/mo (Opus est.) | Base vs base-with-abstention on flagged days: net/trade and Sharpe difference with a 90% CI; ≥ 3 months forward (no historical news archive) | Difference CI includes 0 after its pre-registered sample, or it removes more than 30% of trades without improving net/trade. The scheduled-calendar version already **hurt** the daily strategy (RESEARCH.md) |
| Order-flow / order-book features (recorder built) | Imbalance, depth and spread at the decision time | Distinguish fills that will be immediately adverse; skip entries when depth is thin | $0 to record; needs an always-on host (~$4–8/mo) and months of recording before any test | Only on recorded data after the recording starts; walk-forward; must improve net/trade, not hit rate | No net improvement on ≥ 1,000 recorded opportunities, or latency or ops cost exceeds the gain |
| Market-state (regime) detection | Volatility and trend state from prior data | Abstain in states where the setup historically fails | $0 | Regime cut-offs fit on dev only; tested on validation and test (DECISION_QUALITY.md) | Abstaining doesn't improve the untouched period's net with a CI excluding 0. Both regime selectors already failed in phase 3 |
| Machine-learning signal or entry model | Nonlinear combinations of features | Rank setups by expected net return | $0 compute at this scale; a high **overfitting** cost | Nested walk-forward; the model must beat the simple frozen rule out of sample, with the trial count added to N | Doesn't beat the simple rule out of sample, or calibration (predicted vs realised by decile) is poor |
| LLM in the trading path | n/a | **Not permitted.** Language-model calls are slow, non-deterministic and injectable. They may only label events off the decision path. Risk checks and execution never wait on them | | | |
