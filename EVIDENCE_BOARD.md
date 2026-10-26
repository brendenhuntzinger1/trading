# Evidence board

Updated 2026-10-26 (P1 rows added). Operational status, including whether paper jobs actually ran: `STATUS.md`. Gross and net are per trade on the untouched test period unless noted; intervals are
90% day-block bootstrap. Costs come from COSTS.md and are assumed, not measured.

Four separate gates:
- **Software works:** the engine reproduces the research and passes its tests.
- **Historical effect:** a positive net effect on untouched data under the E1–E7 standard.
- **Forward support:** prospective paper results consistent with the backtest.
- **Live-trial eligible:** all three of the above plus your written approval (`tradelab/governance/status.py`).

| Strategy: hypothesis | Data suitability | Gross (90% CI) | Est. net | Uncertainty / evidence | Software works | Historical effect | Forward support | Live-trial eligible | Next decision |
|---|---|---|---|---|---|---|---|---|---|
| S1: prev close→10:30 move persists into the last half hour | Weak: hourly bars, ~1 year test | +2.0 bp (−2.3, 6.1) | −6 bp | No useful effect: upper bound < 8 bp in all periods | Yes (1,445/1,445) | **No** | n/a | No | Closed |
| S2 stocks: large-cap gap-downs reverse intraday | Fair: daily open/close; survivorship-biased | +6.2 bp (−2.0, 14.2) | −1.8 bp | Real 2000–2015 (+28 bp); decayed after | Yes (5,732/5,732) | **No** | n/a | No | Closed. Market-trend filter is an exploratory lead only (DECISION_QUALITY.md) |
| S2-ETF: same rule on 14 index/sector ETFs | Fair | +12.6 bp (2.3, 23.0) | +4.6 bp | Own test inconclusive; **failed out-of-universe replication** | Yes (548/548) | **No** | Paper run is engine exercise only | No | Closed |
| S2X: frozen S2-ETF on 29 untouched ETFs | Fair | −2.7 bp (−8.9, 3.9) | −10.7 bp | Pre-registered; no useful effect (95% upper 4.8 < 8) | Yes | **No** | n/a | No | Closed |
| S3 / ORB: stocks in play continue the first 5-minute direction | **Untestable now**: needs SIP minute bars and quotes (unverified) | Paper (in-sample): +0.08R ≈ 2–5 bp | Likely < 0 at 20 bp | Pre-registered with power for a clear verdict | Not built | Unknown | n/a | No | Run after the paper key verifies SIP access; measure spreads |
| C1: crypto crash rebound | Good for the signal; maker queue not modelled | +2.7 bp (−13, 19) | −103 bp | No useful effect; holdout coins also fail | Yes (212/212) | **No** | Paper run is engine exercise only | No | Closed |
| C2: crypto 00–06 UTC momentum | Good for the signal | +35 bp (−31, 99) | −97 bp | Small drift not excluded; far below 132 bp cost; 74 trades | Yes (74/74) | **No** | Paper run is engine exercise only | No | Closed at retail fees |
| Daily trend `ensemble_vol40` | Good | n/a (daily) | in-sample only | Lost to fixed allocation on holdout coins | Yes | **No** (inconclusive) | Not continuously paper-traded yet (STATUS.md) | No | Keep as benchmark challenger |
| P1a: daily top-3 Coinbase coin ranking (B1, B2, ridge, logistic, GBT) | Good: point-in-time universe, hourly bars | Best rank IC −0.04…+0.06 vs ~0.10 needed | All configs < 0 net in development | Pre-registered + Amendment 1; PBO 0.43 | Yes (P1 tests) | **No**: no qualifying candidate | n/a | No | Closed at Coinbase retail costs |
| P1b: weekly top-3 coin ranking (B1, ridge, GBT) | Good, but 122 dev weeks (low power) | ICs not distinguishable from 0 | Mostly < 0 | No model beat momentum in development; PBO 0.54 | Yes | **No**: no candidate | n/a | No | Closed |
| Fixed allocation / buy & hold | Good | benchmark | benchmark | | Yes | n/a | Not continuously paper-traded yet | Not a strategy | Benchmarks |

**Decision quality (exploratory, DECISION_QUALITY.md).** The system cannot yet:
- separate setups from noise out of development data;
- rank trades by expected value;
- improve exits with its stops: C1's stop **destroys** about +0.4% per trade of rebound;
- show a reliable ability to abstain.

**Verdict.** No strategy qualifies for a live trial; the system stays in paper mode. The reason is specific:
no tested signal has a gross effect that clearly exceeds realistic retail costs on untouched data, and the
one consistent lead did not replicate. The binding next step is to **measure real execution costs with
consolidated quotes** (paper Alpaca key; credentials guide), then run the pre-registered ORB test within the
budget in RESEARCH_BUDGET.md.
