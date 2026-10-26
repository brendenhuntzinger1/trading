# Latency: measured, and what is actually required

Measured 2026-10-25 from this cloud container, which sits behind an egress proxy and is not a trading host
(`research/intraday/latency/latency.json`).

| Stage | Median | p95 | Notes |
|---|---|---|---|
| Data arrival (Coinbase WebSocket trade: exchange time → our receipt) | 69 ms | 108 ms | 348 trades |
| Bar availability (5-minute bar end → REST candle returned) | ~116 s | | **The dominant delay** in the current crypto runner. A WebSocket bar builder (`tradelab/data/live/bars.py`) would cut it to about 0.1 s if ever needed |
| Feature calculation (C1+C2, 70 days, 3 coins) | 16 ms | 19 ms | |
| Decision (engine: risk checks, sizing, signals) | < 0.1 ms | 0.1 ms | Deterministic; never calls an AI model or the network (enforced by `tests/test_decision_path_isolation.py`) |
| Decision → order submission | 113 ms | 212 ms | Includes a fetch of the product rules |
| Submission → acknowledgement (paper venue, fresh REST order book) | 304 ms | 621 ms | Simulated venue; real broker acknowledgement is unmeasured |

## Requirement, set from opportunity decay (DECISION_QUALITY.md)

Gross return per trade does not measurably change with entry delay:
- C1: 0 → 60 minutes, flat within about ±0.5%;
- C2: flat at 0.56–0.66% across delays;
- S2: open vs 10:30, −0.007% [−0.11, +0.10].

None of the strategies has an edge whose decay could be measured, so **a 1–5 minute decision cycle is
sufficient**. Sub-second infrastructure would buy nothing for any strategy tested.

A faster requirement will be set only when a strategy with a demonstrated edge shows measurable decay. The
requirement is then the delay at which the expected loss of edge equals 10% of the net edge.
