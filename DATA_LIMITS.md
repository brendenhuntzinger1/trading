# What the available data can and cannot evaluate

**Rule:** a test can only validate decisions and execution at the resolution of its data, or coarser. Nothing
here validates execution finer than the bar size. Spreads, queue position and fills inside a bar are
**assumed** (COSTS.md), never measured from these datasets.

## Datasets and their limits

### Yahoo daily bars (stocks/ETFs, 2000 →)
- **Content:** official open, high, low and close, plus consolidated volume. Split-adjusted, not dividend-adjusted.
- **Can evaluate:** open → close returns, such as S2.
- **Cannot evaluate:**
  - Whether a marketable order sent after the opening print gets the official open price. The 5 bp entry
    cost is assumed.
  - Any stop inside the day.
  - Survivorship. The universe is today's S&P 100, and delisted companies are missing.

### Yahoo hourly bars (stocks/ETFs, 2023-11-27 → only)
- **Bar boundaries:** 09:30, 10:30 … 15:30 ET. The last bar is 15:30–16:00.
- **Content:** trade-price OHLC with no bid/ask. The bar "open" is the first trade in the hour, not a price
  anyone could be sure to get.
- **Intra-bar order is unknown,** so a stop and a target touched in the same bar can't be sequenced. The engine
  assumes the stop came first.
- **Only about 2 years of history.** S1's untouched test window is about 14 months (≈ 290 sessions), which
  only has power for large effects.
- **Data errors found:** GEV has no hourly data; the BNY ticker is a different security before 2026.
- **Can evaluate:** S1's economics if fills happen at the 15:30 first trade and the official close.
- **Cannot evaluate:** execution timing inside the 15:30 hour, or anything needing minute bars.

### Yahoo 5-minute bars (last 60 sessions only)
- Too short for any test. S3 (opening-range breakout) is **untestable** and its 60-day look is exploratory only.

### Coinbase 5-minute and 1-minute candles (crypto, 2020 →)
- **Content:** trade-based OHLC with no quotes, so spread is unobservable from candles.
- **Gaps:** missing candles mean no trades in that interval (or an outage). They are not filled with prices.
- **Fills:** the engine fills taker entries at the next bar's open trade price; the real taker price is the ask.
  For BTC/ETH the spread is under 1 bp (measured live), but alts are wider.
- **Maker fills:** only counted when a later 1-minute low trades strictly below the limit. That is
  conservative against touch fills, but it still can't model queue position or adverse selection.
- **Can evaluate:** setups whose expected move and holding period are much larger than 5 minutes, such as
  C1 and C2 with multi-hour holds.
- **Cannot evaluate:** scalping, sub-minute timing, or order-book signals.

### Coinbase hourly and daily candles
- Fine for the daily strategies (phase 1–3) and for the hourly signals inside C1.

### Live WebSocket recordings (from 2026-10-25)
- Real bid/ask, depth and trades with both exchange and receive timestamps.
- This is the only dataset that can eventually measure spread, slippage and short-horizon order-book effects.
  It will be useful only after months of prospective recording.

## Which hypotheses can genuinely be evaluated

| Strategy | Data used | Evaluable? | What remains assumed |
|---|---|---|---|
| Daily trend / fixed allocation (phase 1–3) | Coinbase daily | Yes | Taker fills near the open; fee tier |
| S1 intraday momentum | Yahoo hourly + daily | **Weakly**: short sample | Fill at the 15:30 first trade; MOC impact; spreads |
| S2 gap reversal, stocks and ETFs | Yahoo daily | Yes (survivorship-biased for stocks) | Fill at the official open after the print; spreads at the open |
| S3 opening-range breakout | Yahoo 5-minute, 60 days | **No** | Needs years of minute bars (e.g. Alpaca or Polygon) |
| C1 cascade reversal, C2 intraday momentum | Coinbase 5m (+1m for maker checks) | Yes, for signal economics | Taker at the ask; maker queue and adverse selection; fee tier |
| Anything sub-minute, order-book signals | none historical | **No** | Needs recorded L2 data (being collected) |
