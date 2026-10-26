# Data provenance

Every dataset was downloaded from a public endpoint with no credentials. Checksums of the exact files used are
in `data/SHA256SUMS`, which ships in the data archive. A re-download will **not** be byte-identical:
providers revise history, and Yahoo in particular re-adjusts prices for splits. Use the archived files to
reproduce the reported numbers exactly.

| Dataset | Path | Source / endpoint | Coverage | Fetched (UTC) | Notes |
|---|---|---|---|---|---|
| Crypto daily: BTC, ETH, SOL | `data/{SYM}_1d.csv` | Coinbase Exchange public candles `api.exchange.coinbase.com/products/{p}/candles?granularity=86400` | 2017-01-01 (SOL 2021-06-17) → 2026-10-25 | 2026-10-25 16:25 | Phase-1 fetch: no `received_at` column, so availability is reconstructed. Candle time = bar start. |
| Crypto daily: LTC, BCH, ETC (holdout) | `data/{SYM}_1d.csv` | same | 2017/2018 → 2026-10-24 | 2026-10-25 18:05 | Has `available_at` and `received_at`. BCH is missing 4 days. |
| Crypto hourly: BTC, ETH, SOL | `data/{SYM}_1h.csv` | same, granularity 3600 | 2020-01-01 (SOL 2021-06-17) → 2026-10-25 16:00 | 2026-10-25 16:26 | Real Coinbase outage gaps (BTC: 16 missing hours, longest 5h). Re-downloading gives the same gaps. |
| Coinbase USD universe, daily | `data/universe/*.csv` | same, all 473 USD products incl. 90 delisted | listing → 2026-10 | 2026-10-25 | Used for point-in-time liquidity filters. |
| Crypto intraday 5m / 1h / 1m cache | `data/crypto_intraday/` | same, granularity 300 / 3600 / 60 | 2020-01-01 → 2026-10-24 | 2026-10-25 (`fetch.log`) | Coinbase omits candles with no trades, so gaps mean no trading. See INTRADAY_CRYPTO.md. |
| Stocks daily (S&P 100 + ETFs) | `data/stocks/daily/` | Yahoo chart API (unofficial) `query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&period1=946684800&period2=1792800000` | 2000-01-03 → 2026-10-23 | 2026-10-25 21:35 (`fetched_at` column) | Split-adjusted, not dividend-adjusted. Today's constituents only (**survivorship bias**). |
| Stocks hourly | `data/stocks/hourly/` | Yahoo `interval=1h&range=730d` | 2023-11-27 → 2026-10-23 | 2026-10-25 | Bars start 09:30, 10:30 … 15:30 ET; the last bar is 30 minutes. GEV has none. The BNY ticker maps to a different security before 2026. |
| Stocks 5-minute | `data/stocks/m5/` | Yahoo `interval=5m&range=60d` | last 60 sessions only | 2026-10-25 | Exploratory only (S3). |
| Stock universe | `data/stocks/universe.csv` | Wikipedia "S&P 100" page (URL in file) + 15 ETFs | as of 2026-10-25 | 2026-10-25 21:35 | Not point-in-time. |
| Events and macro calendar | `data/events/` | Fed, BLS, BEA, SEC, CFTC, Coinbase/Kraken status pages, CoinDesk RSS (URLs per row) | 2018 → 2027 calendar; events from 2026-10-25 | 2026-10-25 | See docs/EVENTS.md. Each calendar row cites its official page. |
| Paper journals | `data/journal_paper.db`, `data/intraday/`, `data/paper_venue/` | produced by this system | 2026-10-25 → | live | Simulated trading only. |
| Live recordings | `data/live/` | Coinbase / Kraken public WebSockets | 2026-10-25 smoke tests | 2026-10-25 | Prospective order-book research. |

## Third-party terms

The Yahoo endpoint is unofficial: it has no service guarantee, and its terms restrict redistribution. The archived
Yahoo files are for this project's own research reproduction. Don't publish them, and use a licensed feed for
anything beyond research.
