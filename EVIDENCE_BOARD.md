# Evidence board

Updated 2026-10-26 (P1, ORB and H3 rows; incident 20 corrections). Operational status, including whether paper jobs actually ran: `STATUS.md`. Gross and net are per trade on the untouched test period unless noted; intervals are
90% day-block bootstrap. Costs come from COSTS.md and are assumed, except the ORB and H3 rows, which use measured SIP spreads for 99% of trades plus assumed slippage.

Four separate gates:
- **Software works:** the engine reproduces the research and passes its tests.
- **Historical effect:** a positive net effect on untouched data under the E1–E7 standard.
- **Forward support:** prospective paper results consistent with the backtest.
- **Live-trial eligible:** all three of the above plus your written approval (`tradelab/governance/status.py`).

| Strategy: hypothesis | Data suitability | Gross (90% CI) | Est. net | Uncertainty / evidence | Software works | Historical effect | Forward support | Live-trial eligible | Next decision |
|---|---|---|---|---|---|---|---|---|---|
| S1: prev close→10:30 move persists into the last half hour | Weak: hourly bars, ~1 year test | +2.0 bp (−2.3, 6.1) | −6 bp | No useful effect: upper bound < 8 bp (assumed cost) in all periods | Yes (1,445/1,445) | **No** | n/a | No | Closed |
| S2 stocks: large-cap gap-downs reverse intraday | Fair: daily open/close; survivorship-biased | +6.2 bp (−2.0, 14.2) | −1.8 bp | Real 2000–2015 (+28 bp); decayed after | Yes (5,732/5,732) | **No** | n/a | No | Closed. Market-trend filter is an exploratory lead only (DECISION_QUALITY.md) |
| S2-ETF: same rule on 14 index/sector ETFs | Fair | +12.6 bp (2.3, 23.0) | +4.6 bp | Own test inconclusive; **failed out-of-universe replication** | Yes (548/548) | **No** | Paper run is engine exercise only | No | Closed |
| S2X: frozen S2-ETF on 29 untouched ETFs | Fair | −2.7 bp (−8.9, 3.9) | −10.7 bp | Pre-registered; no useful effect (95% upper 4.8 < 8) | Yes | **No** | n/a | No | Closed |
| ORB: stocks in play continue a 5-minute opening-range breakout (Zarattini et al. 2024) | Good: SIP minute bars and NBBO quotes; universe partly survivorship-affected (non-merger delistings) | Development 2020–21: −9.2 bp per trade gross | −35.4 bp net (measured spread + assumed slippage) | 4,058 trades; loses to placebo; does not beat direction-only (corrected, incident 20); sanity gate failed (−0.22R vs paper +0.08R) | Yes (mechanics audited, 31/31) | **No**: rejected in development | n/a | No | Closed. Validation and final windows unread (B16) |
| H3: stocks in play continue the first 5-minute candle's direction, 09:35 → close (replaces S3) | Good: as ORB | Development 2020–21 (corrected): −2.4 bp per trade gross | −24.4 bp net [−38, −10] | 4,956 trades; both years negative; −98 bp without the best 5%. Its motivating +81 bp was a look-ahead artifact (incident 20) | Yes (regression test) | **No**: rejected in development (Amendment 1) | n/a | No | Closed. Validation and final windows unread |
| C1: crypto crash rebound | Good for the signal; maker queue not modelled | +2.7 bp (−13, 19) | −103 bp | No useful effect; holdout coins also fail | Yes (212/212) | **No** | Paper run is engine exercise only | No | Closed |
| C2: crypto 00–06 UTC momentum | Good for the signal | +35 bp (−31, 99) | −97 bp | Small drift not excluded; far below 132 bp cost; 74 trades | Yes (74/74) | **No** | Paper run is engine exercise only | No | Closed at retail fees |
| Daily trend `ensemble_vol40` | Good | n/a (daily) | in-sample only | Lost to fixed allocation on holdout coins | Yes | **No** (inconclusive) | Not continuously paper-traded yet (STATUS.md) | No | Keep as benchmark challenger |
| P1a: daily top-3 Coinbase coin ranking (B1, B2, ridge, logistic, GBT) | Good: point-in-time universe, hourly bars | Rank IC −0.04…+0.06 vs ~0.10 break-even for this construction (diagnostic) | All configs < 0 net in development | Pre-registered + Amendment 1; PBO 0.43 | Yes (P1 tests) | **No**: none of the 5 tested configs qualified | n/a | No | Closed for these configs, data and assumed costs |
| P1b: weekly top-3 coin ranking (B1, ridge, GBT) | Good, but 122 dev weeks (low power) | ICs not distinguishable from 0 | Mostly < 0 | No model beat momentum in development; PBO 0.54 | Yes | **No**: none of the 3 tested configs qualified | n/a | No | Closed for these configs |
| Fixed allocation / buy & hold | Good | benchmark | benchmark | | Yes | n/a | Not continuously paper-traded yet | Not a strategy | Benchmarks |

**Decision quality (exploratory, DECISION_QUALITY.md).** The system cannot yet:
- separate setups from noise out of development data;
- rank trades by expected value;
- improve exits with its stops: C1's stop **destroys** about +0.4% per trade of rebound;
- show a reliable ability to abstain.

**Verdict.** No strategy qualifies for a live trial; the system stays in paper mode.
- The reason is specific: no tested signal has a gross effect that clearly exceeds realistic retail costs on
  data not used to design it.
- Consolidated quotes are now measured, and in-play spreads are not the binding problem. The gross effects are.
- The research budget in RESEARCH_BUDGET.md is spent (P1, ORB, H3: all rejected). Its rule applies: stop
  intraday research, keep the platform and benchmarks, and recommend no trading.
