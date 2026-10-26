# Research stopping budget (proposed; needs your approval)

The budget exists so the search ends on evidence, not on fatigue or on finding something that looks good by
chance. Leverage, turnover and risk are never raised to reach an income target.

## Spent so far (2026-10-25)
- 92 registered configurations (91 + S2X), 0 passes, $0 spent on data or services.
- Two pre-registered out-of-sample replications. Both rejected: holdout coins for C1; S2X for S2-ETF.

## Budget for the next phase

| Resource | Limit |
|---|---|
| Calendar time | 8 weeks from approval |
| Money | $0 by default. Up to **$99 for one month** of consolidated data (Alpaca Algo Trader Plus) only if the free SIP history is verified unavailable **and** you approve the purchase. Optional ~$6/mo host only once a candidate needs forward order-book data |
| New hypotheses | At most **3**, each pre-registered, each with ≤ 6 development configurations (≤ 18 trials; N becomes ≤ 110) |
| Forward paper period for any candidate | 3 months minimum before a live-trial proposal (rule: STATUS.md §Rules) |

## Order of work
1. Verify paper-key SIP entitlement and quotes (credentials guide). Free.
2. ORB (pre-registered), including measured opening spreads.
3. At most two further hypotheses. They must be chosen for a plausible gross effect **above** measured costs,
   stated before data is viewed.

## Decision rules

| Outcome | Action |
|---|---|
| A hypothesis **passes** E1–E7 on untouched data with measured costs | Freeze it. 3 months of forward paper trading with real quotes. Then a live-trial proposal to you, with fixed capital at risk and the kill-switch rules. **Stop searching** for new hypotheses meanwhile |
| **Inconclusive**, with a positive gross effect and measured costs within 2× of break-even | One pre-registered follow-up on fresh data (new universe or a later period). If that is not a pass, it counts as rejected |
| **Rejected** | Record it; move to the next budgeted hypothesis |
| Budget exhausted with **no pass** | **Stop intraday research.** Keep the platform and paper benchmarks. Recommend the fixed-allocation benchmark or no trading, and say so plainly |
| Any result requiring leverage, higher turnover, or relaxed limits to look acceptable | Rejected by definition |

## Changing direction instead of stopping
Only with a **new information source** (e.g. months of recorded order-book data, or a cost structure the
account doesn't have today such as lower fee tiers). Never by re-testing the same data with new parameters.
