# Alpaca market data: what is actually available (audit 2026-10-25)

Sources are official Alpaca pages only, fetched 2026-10-25. "Unverified" means the official pages do not say,
and the point must be tested with a key before anything depends on it. Nothing below was filled in from memory.

| # | Source |
|---|---|
| A | https://docs.alpaca.markets/docs/about-market-data-api |
| B | https://docs.alpaca.markets/docs/historical-stock-data-1 |
| C | https://docs.alpaca.markets/reference/stockbars |
| D | https://docs.alpaca.markets/reference/stockquotes-1 |
| E | https://docs.alpaca.markets/docs/market-data-faq |
| F | https://docs.alpaca.markets/reference/get-v2-assets-1 |
| G | https://docs.alpaca.markets/docs/paper-trading |
| H | https://docs.alpaca.markets/docs/using-oauth2-and-trading-api |
| I | https://docs.alpaca.markets/docs/historical-crypto-data-1 |
| J | https://docs.alpaca.markets/docs/crypto-pricing-data |

The stock-quotes URL `reference/stockquotes` and the assets URL `reference/get-v2-assets` returned 404. Their
`-1` variants (D, F) were used instead.

## US stock feeds

| Feed | What it is (official wording) | Share of market volume |
|---|---|---|
| `sip` | "Consolidates quotes and trades from US exchanges via UTP and CTA" (B); "all US exchanges" (C) | "100% of the market volume" (B) |
| `iex` | Investors Exchange, a single exchange; "the only feed that can be used without a subscription" (B) | "approximately 2.5%" (B). FAQ example: AAPL 2023-09-29, IEX 1.8% of volume and 2.4% of trades (E) |
| `boats` | Blue Ocean ATS overnight trading (B, C) | not stated |
| `overnight` | Derived from BOATS, cheaper, trades 15 minutes delayed (B) | not stated |
| `otc` | Over-the-counter (C) | not stated |
| `delayed_sip` | **Not documented** in the pages read | n/a |

**IEX is not the market.** IEX-only bars contain roughly 2–3% of volume and only IEX's own quotes. Relative
volume, opening-range high and low, and spreads computed from IEX would describe IEX, not the stock.

## Plans: US stocks (A, E)

| | Basic (free) | Algo Trader Plus ($99/month) |
|---|---|---|
| Real-time | "IEX exchange" only | "All US Stock Exchanges" |
| Historical since | "Since 2016" | "Since 2016" |
| Historical restriction | "latest 15 minutes". FAQ: "the `end` parameter must be at least 15 minutes old to query SIP data without a subscription" | none |
| Historical calls | 200 / minute | 10,000 / minute |
| WebSocket | 30 symbols | unlimited |

Two statements conflict:
- The FAQ (E) says historical **SIP** data older than 15 minutes is queryable "without a subscription".
- The paper-trading page (G) says a **Paper Only** account "is only entitled to receive and make use of IEX
  market data".

Whether a free, paper-only account may use historical SIP is therefore **unverified**. It must be settled in
writing or by testing before any SIP-dependent research runs.

## Endpoints and data semantics

- **Bars (C):**
  - timeframes from `1Min` up to month;
  - `feed` default `sip`;
  - `adjustment` = `raw` (default) | `split` | `dividend` | `spin-off` | `all`, combinable;
  - `asof` (YYYY-MM-DD, default today) maps renamed symbols, and `-` disables mapping;
  - `limit` up to 10,000 data points per request, total across symbols.
- **Bar construction (E):**
  - built from trades, where trade conditions decide which fields a trade updates;
  - "the bar is only emitted if none of its fields (open, high, low, close, volume) are 0", so minutes
    without qualifying trades are absent;
  - timestamps are the **start** of the interval, truncated "in New York", returned in UTC RFC-3339 with
    nanosecond precision (C).
- **Quotes (D):** "the best bid and ask information for a given security", with bid/ask price, size and
  exchange; `feed` default `sip`; nanosecond timestamps. **Whether `sip` quotes are the consolidated NBBO is
  not stated (unverified).** IEX quotes are, by construction, IEX's own book only.
- **Trades, snapshots, auctions:** not documented in the pages read (unverified).
- **History start per feed:** only "since 2016" at plan level (A). Per-endpoint and per-feed start dates are
  unverified.

## Universe, delisted securities, survivorship

- **Asset list (F):** `/v2/assets` returns all statuses by default (`status` filter optional), so inactive
  assets are listed; some are data-only (`tradable=false`). The page doesn't define "inactive" or "delisted".
- **Bars for delisted symbols:** **unverified.** Not stated.
- **Point-in-time index membership:** not offered in any page read.
  - Workaround: define the universe each day from data available that day (listed status, price, volume,
    ATR), as the ORB paper does, instead of using an index.
  - Residual bias: securities missing from Alpaca's asset master or bar history would be silently absent.
    Measure it by checking known delisted names (the paper cites Twitter, delisted 2022-10-27) once a key exists.

## Crypto

- **Venue:** "Our crypto market data reflects trades and quotes from our own Alpaca exchange" (E). v1beta3
  endpoints "no longer distribute data from other providers" (I).
- This is **not Coinbase,** whose data all of our crypto research used. Results do not transfer between venues
  without re-testing, and Alpaca's crypto fees were not checked.
- **Bars with no trades** have volume 0 and prices "based on quote midpoints" (E). Those prices aren't trades.
- **Endpoints (J):** REST latest order books `/v1beta3/crypto/us/latest/orderbooks`; WebSocket trades, quotes
  and order books at `wss://stream.data.alpaca.markets/v1beta3/crypto/us`. History start is not stated.

## Credentials and read-only access (G, H)

- Paper and live keys are separate: "Your paper trading account will have a different API key from your live
  account." Paper base URL: `https://paper-api.alpaca.markets`.
- A Paper Only account trades no real money: orders are simulated, not routed.
- **Read-only personal API keys are not documented.** No page read offers a read-only or data-only scope for
  ordinary API keys. A paper key can place **paper** orders.
- OAuth apps differ: "Read-only endpoint access is assumed by default". Scopes are `account:write`, `trading`
  and `data`, with `env` = `live` or `paper`. That suits third-party apps; it is not a personal data-only key.
- **Conclusion:** the safest credential is a key for a **Paper Only account**. It cannot move real money, but
  it is not read-only (it can place simulated orders) and may be limited to IEX data (see the conflict above).
  No live-account key should ever be created for this project.

## Practical download estimates (Basic: 200 calls/min, ≤10,000 points per call)

| Job | Volume | Minimum calls | Time at 200/min | Storage |
|---|---|---|---|---|
| 1-minute SIP bars, all ~7,000 US stocks, 2016–2026 | ≤ 7,000 × 2,600 days × 390 ≈ 7.1B bars (fewer, as empty minutes are omitted) | ≥ 710,000 | ≥ 59 hours | ~200–300 GB raw. **Too large for this container; not proposed** |
| 5-minute SIP bars, same universe | ≈ 1.4B bars | ≥ 142,000 | ≥ 12 hours | ~50 GB raw; keep only the 09:30 bar and daily aggregates → < 1 GB |
| 1-minute bars for the top-20 selected stocks per day only | 52,000 stock-days × 390 ≈ 20M bars | ~2,000 (if batched by symbol) to 52,000 (per stock-day) | 10 min – 4.3 hours | ~1 GB |
| SIP quotes around each entry (e.g. ±2 min), top 20/day | 52,000 windows | ~52,000 | ~4.3 hours | a few GB |

All are lower bounds: they assume no retries and full 10,000-point pages.

## Suitability

| Use | `sip` (historical, if entitled) | `iex` only | Alpaca crypto |
|---|---|---|---|
| ORB opening range (09:30–09:35 high/low/direction) | Suitable | **Unsuitable**: IEX prints are a 2–3% sample; the range and direction differ from the market's | n/a |
| Relative volume (first 5 minutes vs 14-day average) | Suitable | **Unsuitable**: measures IEX volume only | n/a |
| 14-day ATR, average daily volume, price filter | Suitable (daily bars, split-adjusted) | Unsuitable (volume) / partial (price) | n/a |
| Stop-entry and stop-loss triggers on 1-minute bars | Partially: no intra-minute order | Unsuitable | n/a |
| Spread and slippage at entry | Suitable **if** sip quotes are NBBO (unverified) | Unsuitable: IEX book only | n/a |
| Closing auction (MOC) price | Partially: auction prints are not documented as a separate field | Unsuitable | n/a |
| Order-book or order-flow signals | Unsuitable: no depth history | Unsuitable | Partially: latest order book only, own exchange |
| Crypto intraday, re-testing C1/C2 | n/a | n/a | Partially: different venue from Coinbase; requires a fresh test |

**Bottom line:** the ORB experiment needs **historical SIP** bars and, for costs, SIP quotes. If a free
paper-only account is limited to IEX (G), the experiment cannot be run on Alpaca's free tier. The choice would
then be the $99/month SIP plan or another provider, and that purchase needs your approval.

## Data gates for the ORB study (ORB_PREREGISTRATION.md Amendment 1, B7). **Not run yet: no key**

`scripts/pit_verify_alpaca.py` (logic in `tradelab/stocks/verify.py`) checks each gate against API responses,
and appends a dated results table below. Until that table exists, every "unverified" item above stays unverified.

| Gate | What is checked | Pass rule |
|---|---|---|
| B7.1 SIP access | **Paper key:** confirmed first. **Data:** SPY 1-minute SIP bars and one minute of SIP quotes on the first session of 2016-03, 2020-03 and 2024-06, and the latest session ≥ 2 days old. **Entitlement:** `verify_entitlement` exchange-code / volume test | All requests 200 with data; entitlement verdict `sip` |
| B7.2 Timestamps | SPY on 2024-07-15 (DST) and 2024-01-16 (standard): bar at the session open exists and is 09:30 ET; no bars outside 04:00–20:00 ET. Quotes: inside the requested window, monotonic. Records whether timestamps carry nanoseconds and which quote fields exist | Both days pass |
| B7.3 Coverage | **Asset master:** listed with inactive assets. **Stock sample:** 200 random stocks with median 2023 close > $5 and volume ≥ 1M, 5 random sessions each, need ≥ 1 regular-session minute bar. **Delisted:** 13 names with daily bars in the 30 days ending one month before their last trading day | Coverage ≥ 95%, inactive assets > 0, ≥ 10 delisted names with bars |
| B7.4 Spreads (measured) | In-play stock-days (RV ≥ 1) drawn from the coverage sample. Quoted half-spread of the NBBO quote in force at the end of each minute 09:35–10:30 ET and at 15:59 ET. Median, p90 and the share of minutes with no usable quote | ≥ 20 in-play stock-days, < 20% unusable minutes. **A measurement, never mixed with the slippage assumption** |
| B7.5 Corporate actions | NVDA 2024-06-10 (10:1), AAPL 2020-08-31 (4:1), TSLA 2022-08-25 (3:1): the raw/split-adjusted ratio jumps by the split ratio; the raw intraday last close matches the raw daily close | All three within 1% / 0.5% |

**Delisting dates are from memory.** The confidence of each is listed in `tradelab/stocks/verify.py`. The check
uses a window ending 30 days before each date, so an error of a few days does not affect it.

**Costs in the ORB study:**
- The measured half-spreads at the trigger, stop and close minutes are recorded per trade.
- Slippage beyond the touch is a separate assumption: 1 bp base, 5 bp stress.
- Without historical quotes, the per-side cost falls back to the assumed 10 bp (25 bp stress), and results
  are labelled **"cost assumed, not measured"**. They cannot PASS.
