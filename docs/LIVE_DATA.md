# Live market data

Code: `tradelab/data/live/`. Tests: `tests/test_live_*.py` (no network; fixtures are short real captures
from 2026-10-25). Smoke run against real feeds: `.venv/bin/python scripts/live_smoke.py [--venue coinbase|kraken|both] [--seconds 60] [--record]`.

## Design

| Module | Role |
|---|---|
| `types.py` | `Trade`, `TopOfBook`, `DepthSummary`, `BookSample`, `VenueNotice`, `FeedHealth`. Every record carries the exchange `event_time` **and** our `received_at`. |
| `feeds.py` | `CoinbaseFeed` (default) and `KrakenFeed` behind one interface (`BaseFeed`). `handle(raw, received_at)` is a pure message→records step; `run()` owns the socket. |
| `book.py` | Local L2 book (Decimal), snapshot + delta, truncation, crossed/locked and non-positive checks, spread, depth within N bps, Kraken CRC32. |
| `clock.py` | Measures offset to each venue's REST time endpoint (request-midpoint method) and corrects `received_at` only when skew clearly exceeds measurement error. |
| `recorder.py` | Append-only JSONL: `data/live/<venue>/<received date>/<kind>.jsonl`. |
| `bars.py` | OHLCV bars from recorded trades, **point-in-time**: a trade counts only if received by the bar's end (+ explicit grace). Late trades are counted and excluded. |
| `analytics.py` | Rolling realized volatility and pairwise correlation; windows with empty bars give NaN rather than fabricated values. |
| `derivatives.py` | **Research-only** Kraken Futures perp funding, open interest, basis. No order path exists; US persons can't trade these. |

Venues: public channels, no API keys. Coinbase Advanced Trade `wss://advanced-trade-ws.coinbase.com`
(`heartbeats`, `level2`, `market_trades`, `ticker`); Kraken `wss://ws.kraken.com/v2` (`book`, `trade`,
`ticker`, plus `status`/`heartbeat`, which it sends unprompted).

## Failure handling

| Failure | Detection | Response |
|---|---|---|
| Disconnect / protocol error | exception from socket | all books reset to invalid, `connected=False`, reconnect with capped exponential backoff (0.5 s × 2ⁿ, cap 60 s, 50–100% jitter), full resubscribe |
| Silent connection | no message for 15 s (Coinbase heartbeats arrive every ~1 s; Kraken sends heartbeats) | treated as dead → reconnect |
| Lost Coinbase messages | `sequence_num` is **per connection, across all channels** (verified live: every diff = 1) | any jump invalidates every book on the connection; level2 is unsubscribed/resubscribed for a fresh snapshot. Lower or equal numbers are replays and are ignored |
| Corrupted / missed Kraken update | CRC32 over top-10 asks then bids, computed on the exact digits received (`parse_float=Decimal`) | book invalidated, `checksum_failures += 1`, book channel resubscribed. **294/294 real messages verified** |
| Crossed/locked book, negative size, empty side | checked after every message batch | book invalidated and resynced |
| Updates before snapshot | book not valid | ignored until the snapshot arrives |
| Duplicate trades (reconnect snapshots repeat recent prints) | bounded set of `(symbol, trade_id)` | dropped and counted |
| Historical trades in subscribe snapshot | `Trade.from_snapshot=True` | excluded from latency stats; bar builder also excludes them via `received_at` |
| Stale data | `FeedHealth.stale(now, max_age_s)` from last receive time | consumer (risk engine) decides: block new orders |
| Clock skew | `FeedHealth.clock_offset_ms` | correction applied only if skew > 250 ms + RTT/2 + endpoint resolution. Kraken's endpoint has 1 s resolution, so its offset is informational only |
| Scheduled venue maintenance | Kraken `status` → `VenueNotice(status="maintenance_scheduled", starts_at, ends_at)` | available to the risk engine to pause new orders ahead of time |

Consumers must never read from a book whose `valid` is False: `top()` and `depth_summary()` return `None` in that state.

## Live smoke run (2026-10-25, 60 s per venue, through this container's proxy: WebSockets work)

| | Coinbase | Kraken |
|---|---|---|
| Raw messages | 2,417 (40/s) | 4,727 (79/s) |
| Gaps / checksum failures / reconnects | 0 / n/a / 0 | n/a / 0 / 0 |
| Spread BTC / ETH | 0.001 bps / 0.55 bps | 0.012 / 0.042 bps |
| Depth within ±10 bps (BTC) | bid $3.2M / ask $2.0M | limited by the 10-level subscription in the smoke run |
| Trade latency event→receive, p50 / p95 | 78 / 112 ms | 51 / 89 ms |
| Clock offset | +68 ms (within RTT) | −652 ms (1 s resolution endpoint; not meaningful) |

The first smoke run exposed two bugs: bars came out empty when `start` wasn't on a bar boundary, and
subscribe-snapshot trades inflated p95 latency to 48 s. Both are fixed and have regression tests.

At the account size in question ($10–$250 orders), BTC/ETH liquidity and spread are not a constraint.
They would be for small coins.

## Known limits
- **No historical order-book data.** Order-book signals can only be studied prospectively from what
  this recorder collects; licensed history (e.g. Tardis.dev) is a paid subscription and is not purchased.
- Kraken Futures funding history from the public endpoint covers about one year (9,003 hourly points from
  2025-10-15), too short to establish a funding-based effect.
- Kraken depth summaries only see the subscribed depth (`depth` rounds up to 10/25/100/500/1000).
- Recorder output is not rotated or compressed; ~40–80 messages/s of trades and tops is roughly tens of MB/day per venue.

## GitHub Actions vs an always-on host

From GitHub's documentation:
- Scheduled workflows: "The shortest interval you can run scheduled workflows is once every 5 minutes."
  "The `schedule` event can be delayed during periods of high loads … High load times include the start
  of every hour." "If the load is sufficiently high enough, some queued jobs may be dropped."
  In public repos, schedules are "automatically disabled when no repository activity has occurred in 60 days."
  ([events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule))
- "Each job in a workflow can run for up to 6 hours of execution time." The GitHub Free plan includes 2,000
  minutes/month. ([limits](https://docs.github.com/en/actions/reference/limits))

**(a) Daily baseline: GitHub Actions is adequate, with safeguards.** The audit measured that filling up to
12 h late costs ~1.4 percentage points of CAGR, so scheduling delay is tolerable. Required mitigations:
schedule several times per day at a non-zero minute (e.g. `17 0,4,8 * * *`) with an idempotent "has
today's rebalance been done?" check, so a dropped run is caught up; persist state outside the runner;
alert when no successful run in 26 h; keep the repo private so the schedule isn't disabled for inactivity.
A ~2-minute daily job uses <100 of the 2,000 free minutes.

**(b) Continuous monitoring / intraday: GitHub Actions is not suitable.** It can't hold a WebSocket
open (6 h job cap, ≥5 min schedule granularity, delays and possible drops at the top of the hour). Stale-data
and outage circuit breakers need something present all the time. That requires an always-on process: a
small VPS or an always-on home machine running `BaseFeed.run()` under a supervisor (systemd/Docker restart
policy). It is only worth paying for if an intraday component earns its cost in paper trading first.
