# H3: first-candle continuation on US stocks in play (pre-registration)

Written 2026-10-26 ~09:40 UTC, **before any 2022–2026 data for this signal was read.** This is hypothesis 3 of
3 in RESEARCH_BUDGET.md: the last one. Once it is evaluated, the budget is spent.

## Where the idea came from (disclosed)
H3 is ORB's **direction-only benchmark**, which looked strong in ORB's development window (2020–2021, inside
the Zarattini et al. 2016–2023 sample):
- 4,058 trades; gross +81 bp, net +60 bp per trade, using measured spreads;
- median +25 bp; hit rate 54%;
- positive in every half-year;
- +34 bp net per trade with the best 5% of trades removed.

The **portfolio** P&L, under ORB's stop-distance sizing, was concentrated: 10 symbols gave 74% and 10 days
gave 71% (`research/orb/audits/direction_lead_dev.json`). The result was **found by looking** at development
data. It is a lead, not evidence. Everything below is decided before the 2022–2026 data is read.

## Economic hypothesis
On a news or imbalance day (relative volume ≥ 1), the first five minutes reveal the direction of informed
or forced order flow. That flow keeps executing through the session, because large participants spread their
orders over hours. So the first candle's direction persists to the close.

A follower can profit only if the persistence after 09:35 exceeds the costs of entering at 09:35 and exiting
at the close. The 2020–2021 sample may owe this to retail-driven momentum. If so, H3 should fail on 2022–2023.

## Rule (one primary configuration; one labelled secondary)
- **Universe and selection:** exactly ORB `primary`. Point-in-time universe (ORB Amendment 4); open > $5;
  ADV14 ≥ 1M; ATR14 > $0.50; RV ≥ 1; top 20 by RV; doji days skipped.
- **Primary (H3-L): long-only.** If the 09:30–09:34 candle is bullish, buy at the open of the 09:35 bar and
  sell at the close of the last regular-session bar. No stop, no target.
- **Secondary (H3-LS, labelled):** also short a bearish first candle. Borrow availability and fees are not
  modelled, so this is an upper bound. It can never be frozen.
- **Sizing:** equal weight, 1/20 of equity per position, so gross exposure is at most 1×. (ORB's
  stop-distance weights do not apply: H3 has no stop.)
- **Costs:**
  - measured SIP NBBO half-spread at entry (09:35) and at exit (15:59);
  - plus assumed slippage, 1 bp per side base and 5 bp stress;
  - plus SEC/TAF fees.
  - Reported gross, net of measured spread, and net of everything. A trade without a usable quote takes the
    assumed 10 bp per side.

## Periods
| Phase | Dates | Status |
|---|---|---|
| Hypothesis generation | 2020-01-02 → 2021-12-31 | **Seen** (ORB development) |
| **Validation** | 2022-01-03 → 2023-12-29 | Unread for this signal: ORB stopped before reading it (B16) |
| **Final** | 2024-01-02 → 2026-07-24 | Unread. **Read only if H3-L qualifies in validation** |
| Prospective | from deployment | Needs real-time consolidated data (not on the free plan) |

The ORB excluded window (2026-07-27 → 2026-10-23) stays excluded. Both 2022–2023 and 2024–2026 lie
**after** the hypothesis-generation window.

## Benchmarks (same stock-days, same costs, same 1× cap)
1. Cash (0).
2. **In-play basket, long:** every selected stock, bought at 09:35 and held to the close, equal weight. This
   tests whether the *direction* adds information beyond being in play.
3. SPY, 09:35 → close.
4. **Opposite-direction control:** the same bullish stock-days traded short. With 2, this gives a
   random-direction reference.

## Validation qualifiers (all must hold for H3-L to proceed to the final window)
1. Net per trade (all costs), 90% day-block bootstrap lower bound > 0.
2. Daily net P&L beats the in-play basket on paired days, at matched exposure (90% CI of the difference > 0).
3. Positive net in both 2022 and 2023.
4. Net per trade without the best 5% of trades > 0.

If any fails: **H3 is rejected, the final window stays unread, and the research budget is spent.**

## Final (only if qualified)
- **Freeze:** H3-L is frozen by hash before the final window is read.
- **PASS** requires E1–E7 (INTRADAY_HYPOTHESES.md), with:
  - E5 = beats the opposite-direction control and the basket (p < 0.05);
  - E6 = deflated Sharpe with N = 106 + 2 = 108;
  - plus concentration reporting (top 1% and 5% of trades, top 10 symbols and days).
- **REJECT** if the 95% upper bound of the gross per-trade mean is below the base round-trip cost.
- Otherwise **INCONCLUSIVE**.

A PASS authorises only: freezing, a prospective paper period of at least 3 months and 60 trades, and a
report. Real-time execution would additionally need real-time consolidated data. That is a purchase, and it
is **not authorised**.

## Consumed data and reproduction
- **Consumed scope:** `stocks.us.intraday.first_candle`.
  - 2022–2023 is marked consumed when validation is first read.
  - 2024–2026-07-24 is marked consumed only if the final window is read.
- **Reproduction:** results may be re-run deterministically. Any configuration change after a window is read
  is refused, as for P1 and ORB.

## Amendment 1 (2026-10-26 ~10:00 UTC): development gate, after a harness defect

Written after the validation fetch was stopped at 09:50 UTC. At that point no 2022–2023 outcome had been
computed to completion, saved or read: no frame file existed.

**The defect (incident 20).** ORB registered direction-only as "entered at 09:35 at market, held to close …
without the breakout trigger" (ORB B5.4). The harness recorded it **only on stock-days where the breakout later
triggered**. That conditions on the future. Stock-days whose price never reached the opening-range high after
09:35 were dropped, and those are the losers. Every development figure quoted under "Where the idea came from"
(+81 bp gross, +60 bp net, …) comes from that defective benchmark. **H3's motivating evidence is therefore
invalid.** The rule itself is unchanged, and the harness is now fixed with a regression test.

**Disclosure.** Before writing this amendment I estimated the corrected development gross from ORB's stored
aggregates:
- 4,058 triggered stock-days at +81 bp;
- 898 never-triggered stock-days at −379 bp;
- combined, about −2 bp gross per trade, so roughly −25 bp after costs.

That estimate is why this gate exists. It can only **stop** H3. It cannot select, tune or revive anything.

**A1 (development gate, the same principle as ORB B16).**
- H3's validation (2022–2023) is read only if H3-L, computed with the corrected harness on the
  hypothesis-generation window (2020-01-02 → 2021-12-31), meets **all four validation qualifiers** there:
  - 1/20 equal weights;
  - measured costs;
  - the same code as validation.
- If it does not:
  - H3 is **rejected in development**;
  - the validation and final windows stay unread;
  - the research budget is spent.
- `research/h3/study.py` enforces this: `fetch` and `validation` refuse unless `dev_check` passed.

**Consumed data.** The ledger entry for 2022–2023 (`stocks.us.intraday.first_candle`) was written when the fetch
started. It stays, conservatively, with its note corrected: marked at fetch start; stopped before any outcome
was computed or read.
