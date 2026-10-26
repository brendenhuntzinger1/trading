# Data audit: point-in-time crypto universe, hourly bars, stock data

Written 2026-10-26. Code: `tradelab/pit/`. Data: `data/pit/` (gitignored). Reproduce:

    .venv/bin/python scripts/pit_build_universe.py      # universe  -> data/pit/crypto_universe.csv.gz
    .venv/bin/python scripts/pit_fetch_hourly.py         # bars      -> data/pit/hourly/<PRODUCT>.csv (resumable)
    .venv/bin/python scripts/pit_audit.py                # quality   -> data/pit/crypto_quality.csv, crypto_audit_summary.json
    .venv/bin/python -m pytest -q tests/test_pit_*.py

Every statement below is labelled with one of four kinds:

| Label | Meaning |
|---|---|
| **(a) decision-time** | Information a strategy could have had at the moment it decided |
| **(b) retrospective** | Information that was revised, or is only known now (looking back) |
| **(c) assumption** | A research choice we made; it can be changed and could be wrong |
| **(d) measured** | A count or fact measured from the files on 2026-10-26 |

## 1. Crypto universe (Coinbase USD spot)

File `data/pit/crypto_universe.csv.gz`: one row per (date, product) from 2018-01-01 to 2026-10-25, columns
`date, product, eligible, reason`. Built from the daily candles in `data/universe/`.

**Rule for day d** (`Rules` in `tradelab/pit/crypto_universe.py`):

| Condition | Reason when it fails | Kind |
|---|---|---|
| Product traded on day d−1 (has a daily candle) | `not_trading_prev_day` | (a) |
| ≥ 60 days with candles before d | `history_lt_60d` | (a) |
| ≥ 20 candles in the 30 days before d | `insufficient_volume_obs` | (a) |
| Median daily dollar volume (close × volume) over the 30 days before d ≥ $10 M | `dollar_volume_lt_10m` | (a) |
| Base asset not a stablecoin, pegged, wrapped or liquid-staking token | `excluded_asset` | (c) |

- (c) Thresholds (60 days, 30-day window, $10 M) are research choices, set before any strategy used them.
- (c) **Deviation from "has candles that day".** Day d's own candle is incomplete at any time during day d, so
  using it would leak the future. The listing test uses day d−1. All windows are `shift(1)`; a test
  (`test_future_independence`) changes every candle on or after d and checks that day d's eligibility does not move.
- (b) **Current status is not history.** Coinbase's `/products` reports only today's status (online / delisted).
  `eligible_at(t, live_status=...)` applies it only when t is today. Historical membership uses candles alone.
- (b) **Survivorship.** The product list comes from today's API plus the products we already had daily files for.
  A product that was listed and fully removed before our first download, with no daily file, is missing. Delisted
  products that Coinbase still returns candles for are included.
- (c) The exclusion list is written by hand from today's knowledge of what each token is (b). For example WBTC,
  CBETH, MSOL and PAXG are excluded because they track another asset.

**Eligible products per year** (d, eligible on at least one day in the year, and the daily mean):

| Year | Distinct eligible | Mean per day | Min | Max | Additions | Removals |
|---|---|---|---|---|---|---|
| 2018 | 4 | 3.0 | 1 | 4 | 7 | 8 |
| 2019 | 5 | 2.7 | 1 | 5 | 8 | 9 |
| 2020 | 13 | 4.6 | 1 | 10 | 25 | 18 |
| 2021 | 67 | 26.6 | 8 | 48 | 107 | 85 |
| 2022 | 37 | 17.2 | 7 | 31 | 37 | 59 |
| 2023 | 28 | 8.5 | 4 | 19 | 47 | 36 |
| 2024 | 48 | 19.4 | 9 | 41 | 94 | 82 |
| 2025 | 54 | 20.3 | 11 | 30 | 58 | 77 |
| 2026 (to 25 Oct) | 26 | 10.9 | 6 | 18 | 30 | 31 |

- (d) Membership turns over heavily: in 2021 there were 107 additions and 85 removals against a mean of 27 members.
  Most of it is products crossing the $10 M line and back. A strategy on this universe will trade in and out of
  names for liquidity reasons; that turnover has a cost and must be modelled.
- (d) On 2026-10-25: 11 eligible, 375 below $10 M, 7 with < 60 days of history, 2 excluded.
- (d) 113 products were eligible on at least one day since 2021-01-01 (`data/pit/ever_eligible_2021.json`).

## 2. Crypto hourly bars

Files `data/pit/hourly/<PRODUCT>.csv`, columns `time, open, high, low, close, volume, available_at, received_at`.

- (a) `time` is the bar start (UTC). `available_at = time + 1 h`: a bar can be used no earlier than its close.
  The loaders filter on `available_at <= as_of`, never on `time`.
- (b) `received_at` is when we downloaded the bar. For all history it is 2026-10-25/26, long after
  `available_at`. It records provenance, not what was knowable then. Coinbase can revise candles (trade busts,
  late prints); we cannot tell whether a historical candle equals what was published at the time.
- (a) Only complete bars are stored. The fetch ends at the last complete hour, and a resumed run starts after the
  last stored bar, so a forming bar never enters a file.
- (c) Range: from max(2021-01-01, first eligible date − 60 days) to now for online products, and to the last
  daily candle + 1 day for products that stopped trading. BTC-USD from 2021-01-01, as the reference.

### How the audit classifies a missing hour

Coinbase emits **no candle for an hour without trades**. So a missing hour is either "nobody traded" or
"the venue (or its data) was down". (c) We use BTC-USD, which trades every hour in normal operation, as the
reference: an hour missing for a product **and** for BTC is counted as an outage; an hour missing for the
product only is counted as no-trade. This misclassifies an outage that hit one market but not BTC (it is called
no-trade) and it cannot see outages that left BTC candles in place.

Other checks, which flag and never delete (thresholds are (c)):
- duplicates: repeated bar start times in the raw file;
- invalid OHLC: low above min(open, close), high below max(open, close), or a non-positive price;
- zero-volume bars, and "tiny" bars with dollar volume < $100;
- extreme returns: |hourly log return| > 0.25 between consecutive hours, and robust z > 12 (median/MAD);
- delisting: not "online" in today's product list, or no bar in the last 48 h of BTC's data;
- rebrands (`KNOWN_REBRANDS`): MATIC→POL, RNDR→RENDER, MKR→SKY. The old and new products are kept as
  **separate products with separate histories**; nothing is spliced. The overlap is reported below.

### Results (d, measured 2026-10-26; `data/pit/crypto_quality.csv`, `data/pit/crypto_audit_summary.json`)

| Measure | Value |
|---|---|
| Products fetched | 113 (every product eligible on any day since 2021-01-01, plus BTC-USD) |
| Total hourly bars | **3,892,926** |
| BTC-USD range | 2021-01-01 00:00 → 2026-10-26 00:00 UTC (last complete hour at fetch time) |
| **Venue outage hours** (BTC has no candle) | **13**, in three episodes: 2023-03-04 18:00–20:00 (3 h), 2025-10-25 16:00–20:00 (5 h), 2026-05-08 02:00–06:00 (5 h) |
| Missing product-hours, total | 54,800: 1,221 during those outages (summed over products), 53,579 no-trade |
| Duplicate bar times | 0 (see note) |
| Invalid OHLC | 0 |
| Zero-volume bars | 0 (Coinbase emits no candle instead) |
| Bars with dollar volume < $100 | 37,887 |
| Hourly \|log return\| > 0.25 (flagged) | 255 |
| Robust z > 12 (flagged) | 5,194 |
| Stopped trading (no longer online) | 16 |

Notes on the results:
- (d) **XRP-USD is 42.6% missing because Coinbase suspended it**: no candle from 2021-01-19 until
  2023-07-13 20:00 (a 905-day gap). The BTC rule counts this as 21,718 "no-trade" hours; it is a **trading
  suspension**, a third category the BTC rule cannot see. The universe drops it from 2021-01-21 (`not_trading_prev_day`, 904 days), but any loader user must not treat the gap as quiet trading.
- (d) Thin products miss many hours because nobody traded: BNT 10.9%, MASK 7.6%, REQ 6.9%, PLA 5.9%, BAND 5.1%,
  KNC 4.9%. Their returns over a missing hour are undefined, not zero; `panel()` leaves them NaN.
- (d) The extreme returns are real events or listing artifacts, kept and flagged: WLUNA −3.09 on 2022-05-13 07:00
  (the Terra collapse); SHIB −2.07 on 2021-09-10 17:00, on its first day, when opening prints near 5.7e-5 fell to
  the market price near 7.2e-6 (a listing artifact); CGLD +0.82 on 2021-08-30 13:00; IOTX +0.92 on 2026-02-28 00:00.
  (c) A strategy should skip each product's first trading day; no filter has been applied to the files.
- (d) Duplicates: 0 after `repair()`. Our own first run had two fetchers writing the same files at once, which
  duplicated rows in the first 16 files it touched (e.g. ATOM 67,793 → 33,896 rows). `repair()` removed them; `FetchLock` now prevents a
  second fetcher. The 97 files fetched afterwards needed no repair, so the API itself returned no duplicates.
- (b) The robust-z count depends on each product's typical volatility and is large for quiet periods; it is a
  screening flag, not an error count.

Stopped trading (d; last hourly bar, and today's API status):

| Product | Last bar (UTC) |
|---|---|
| ENJ-USD | 2024-06-14 18:00 |
| EOS-USD | 2025-12-10 19:00 |
| GALA-USD | 2023-05-12 16:00 |
| IOTX-USD | 2026-09-23 17:00 |
| IP-USD | 2026-10-05 15:00 |
| LRC-USD | 2026-08-07 17:00 |
| MATIC-USD | 2025-10-14 15:00 |
| MKR-USD | 2026-01-12 16:00 |
| NU-USD | 2023-02-06 17:00 |
| OMG-USD | 2023-03-29 16:00 |
| PLA-USD | 2024-02-14 01:00 |
| POLY-USD | 2023-12-05 19:00 |
| REN-USD | 2023-11-03 18:00 |
| RNDR-USD | 2025-06-26 18:00 |
| STORJ-USD | 2026-09-28 17:00 |
| WLUNA-USD | 2022-05-27 16:00 |

Rebrands (d; daily files). Old and new traded side by side; nothing is spliced:

| Old → new | Old first | New first | Old last | Overlap days |
|---|---|---|---|---|
| MATIC-USD → POL-USD | 2021-03-11 | 2024-09-04 | 2025-10-14 | 406 |
| RNDR-USD → RENDER-USD | 2022-02-03 | 2024-02-15 | 2025-06-26 | 498 |
| MKR-USD → SKY-USD | 2020-06-09 | 2025-07-10 | 2026-01-12 | 187 |

(c) A strategy holding the old product across a rebrand must model the swap or exit; the two series are not
one continuous asset in these files.

#### Per-product quality table (d)

Outage h: missing hours when BTC was also missing. No-trade h: missing hours otherwise. \|r\|: hourly log return
between consecutive hours.

| Product | First bar | Last bar | Bars | Missing % | Outage h | No-trade h | Bars < $100 | \|r\| > 0.25 | z > 12 | Max \|r\| | Status now |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AAVE-USD | 2021-01-01 | 2026-10-26 | 50,962 | 0.03 | 13 | 2 | 0 | 1 | 33 | 0.28 | online |
| ACH-USD | 2021-08-03 | 2026-10-26 | 45,776 | 0.11 | 13 | 36 | 58 | 6 | 103 | 0.38 | online |
| ADA-USD | 2021-03-18 | 2026-10-26 | 49,122 | 0.03 | 13 | 2 | 0 | 3 | 35 | 0.41 | online |
| AERGO-USD | 2025-02-21 | 2026-10-26 | 14,259 | 2.93 | 10 | 420 | 344 | 10 | 139 | 0.40 | online |
| AERO-USD | 2024-02-06 | 2026-10-26 | 23,805 | 0.05 | 10 | 1 | 0 | 1 | 26 | 0.27 | online |
| ALGO-USD | 2021-01-01 | 2026-10-26 | 50,961 | 0.03 | 13 | 3 | 0 | 0 | 25 | 0.25 | online |
| AMP-USD | 2021-06-10 | 2026-10-26 | 46,965 | 0.33 | 13 | 143 | 356 | 6 | 129 | 0.46 | online |
| ANKR-USD | 2021-03-25 | 2026-10-26 | 48,793 | 0.36 | 13 | 163 | 736 | 2 | 55 | 0.41 | online |
| APE-USD | 2022-03-17 | 2026-10-26 | 40,216 | 0.46 | 13 | 172 | 201 | 1 | 35 | 0.37 | online |
| APT-USD | 2024-01-16 | 2026-10-26 | 24,327 | 0.04 | 10 | 0 | 2 | 0 | 9 | 0.15 | online |
| ARB-USD | 2023-11-04 | 2026-10-26 | 26,079 | 0.04 | 10 | 0 | 6 | 0 | 7 | 0.23 | online |
| ATOM-USD | 2021-01-01 | 2026-10-26 | 50,963 | 0.03 | 13 | 1 | 1 | 2 | 36 | 0.36 | online |
| AVAX-USD | 2021-09-30 | 2026-10-26 | 44,416 | 0.03 | 13 | 1 | 1 | 1 | 16 | 0.29 | online |
| AVNT-USD | 2025-09-09 | 2026-10-26 | 9,852 | 0.19 | 10 | 9 | 6 | 1 | 21 | 0.26 | online |
| AXS-USD | 2021-08-12 | 2026-10-26 | 45,580 | 0.06 | 13 | 13 | 187 | 2 | 58 | 0.31 | online |
| BAND-USD | 2021-01-01 | 2026-10-25 | 48,382 | 5.09 | 13 | 2,581 | 3,173 | 1 | 48 | 0.26 | online |
| BAT-USD | 2021-09-18 | 2026-10-26 | 44,709 | 0.06 | 13 | 15 | 298 | 0 | 29 | 0.15 | online |
| BCH-USD | 2021-01-01 | 2026-10-26 | 50,963 | 0.03 | 13 | 1 | 0 | 1 | 62 | 0.30 | online |
| BNT-USD | 2021-01-01 | 2026-10-26 | 45,410 | 10.92 | 13 | 5,554 | 6,440 | 0 | 41 | 0.24 | online |
| BONK-USD | 2023-12-14 | 2026-10-26 | 25,102 | 0.04 | 10 | 0 | 0 | 0 | 16 | 0.22 | online |
| BTC-USD | 2021-01-01 | 2026-10-26 | 50,964 | 0.03 | 13 | 0 | 1 | 0 | 72 | 0.12 | online |
| CGLD-USD | 2021-01-01 | 2026-10-26 | 50,053 | 1.81 | 13 | 911 | 1,478 | 5 | 53 | 0.81 | online |
| CHZ-USD | 2021-09-13 | 2026-10-26 | 44,244 | 1.37 | 13 | 600 | 1,201 | 0 | 27 | 0.20 | online |
| COMP-USD | 2021-01-01 | 2026-10-26 | 50,956 | 0.04 | 13 | 8 | 50 | 3 | 39 | 0.31 | online |
| COTI-USD | 2021-08-26 | 2026-10-26 | 44,686 | 1.28 | 13 | 568 | 427 | 2 | 45 | 0.39 | online |
| CRO-USD | 2021-11-03 | 2026-10-26 | 43,600 | 0.04 | 13 | 4 | 5 | 0 | 91 | 0.23 | online |
| CRV-USD | 2021-03-25 | 2026-10-26 | 48,952 | 0.03 | 13 | 4 | 6 | 1 | 33 | 0.35 | online |
| CTSI-USD | 2021-09-23 | 2026-10-26 | 43,301 | 2.95 | 13 | 1,303 | 1,083 | 4 | 71 | 0.51 | online |
| DASH-USD | 2021-01-01 | 2026-10-26 | 50,955 | 0.04 | 13 | 9 | 103 | 1 | 56 | 0.32 | online |
| DOGE-USD | 2021-06-03 | 2026-10-26 | 47,274 | 0.03 | 13 | 2 | 0 | 1 | 80 | 0.25 | online |
| DOT-USD | 2021-06-16 | 2026-10-26 | 46,962 | 0.03 | 13 | 2 | 0 | 0 | 27 | 0.21 | online |
| ENA-USD | 2025-06-13 | 2026-10-26 | 11,991 | 0.08 | 10 | 0 | 0 | 0 | 2 | 0.16 | online |
| ENJ-USD | 2021-09-08 | 2024-06-14 | 24,252 | 0.03 | 3 | 4 | 60 | 0 | 22 | 0.19 | delisted |
| EOS-USD | 2021-01-01 | 2025-12-10 | 43,293 | 0.05 | 8 | 15 | 52 | 1 | 57 | 0.32 | delisted |
| ETC-USD | 2021-01-01 | 2026-10-26 | 50,956 | 0.04 | 13 | 8 | 24 | 2 | 99 | 0.33 | online |
| ETH-USD | 2021-01-01 | 2026-10-26 | 50,964 | 0.03 | 13 | 0 | 0 | 0 | 64 | 0.15 | online |
| FARTCOIN-USD | 2025-06-12 | 2026-10-26 | 11,999 | 0.08 | 10 | 0 | 0 | 1 | 5 | 0.27 | online |
| FET-USD | 2021-07-27 | 2026-10-26 | 45,977 | 0.03 | 13 | 3 | 2 | 1 | 29 | 0.30 | online |
| FIL-USD | 2021-01-01 | 2026-10-26 | 50,961 | 0.03 | 13 | 3 | 3 | 2 | 66 | 0.28 | online |
| GALA-USD | 2021-11-16 | 2023-05-12 | 13,003 | 0.04 | 3 | 2 | 0 | 2 | 21 | 0.32 | delisted |
| GRT-USD | 2021-01-01 | 2026-10-26 | 50,888 | 0.17 | 13 | 76 | 121 | 2 | 20 | 0.33 | online |
| HBAR-USD | 2024-01-05 | 2026-10-26 | 24,590 | 0.04 | 10 | 1 | 0 | 0 | 30 | 0.20 | online |
| HYPE-USD | 2026-03-26 | 2026-10-26 | 5,132 | 0.10 | 5 | 0 | 0 | 0 | 1 | 0.12 | online |
| ICP-USD | 2021-05-10 | 2026-10-26 | 47,838 | 0.05 | 13 | 13 | 0 | 0 | 46 | 0.24 | online |
| INJ-USD | 2023-10-23 | 2026-10-26 | 26,367 | 0.04 | 10 | 0 | 1 | 0 | 5 | 0.19 | online |
| IOTX-USD | 2021-09-18 | 2026-09-23 | 43,526 | 0.99 | 13 | 423 | 1,253 | 11 | 175 | 0.92 | delisted |
| IP-USD | 2025-08-04 | 2026-10-05 | 10,227 | 0.36 | 10 | 27 | 23 | 2 | 15 | 0.29 | delisted |
| JASMY-USD | 2021-10-07 | 2026-10-26 | 44,246 | 0.04 | 13 | 3 | 0 | 3 | 71 | 0.27 | online |
| JTO-USD | 2024-01-21 | 2026-10-26 | 24,205 | 0.05 | 10 | 2 | 0 | 0 | 9 | 0.24 | online |
| KNC-USD | 2021-01-01 | 2026-10-25 | 48,460 | 4.94 | 13 | 2,503 | 1,614 | 4 | 53 | 0.58 | online |
| LDO-USD | 2023-11-13 | 2026-10-26 | 25,823 | 0.19 | 10 | 40 | 21 | 0 | 6 | 0.20 | online |
| LINK-USD | 2021-01-01 | 2026-10-26 | 50,962 | 0.03 | 13 | 2 | 0 | 1 | 24 | 0.26 | online |
| LPT-USD | 2021-09-14 | 2026-10-26 | 44,170 | 1.48 | 13 | 650 | 706 | 4 | 70 | 0.34 | online |
| LRC-USD | 2021-01-01 | 2026-08-07 | 48,802 | 0.55 | 13 | 259 | 328 | 3 | 84 | 0.36 | delisted |
| LTC-USD | 2021-01-01 | 2026-10-26 | 50,962 | 0.03 | 13 | 2 | 0 | 1 | 61 | 0.30 | online |
| MANA-USD | 2021-09-11 | 2026-10-26 | 44,781 | 0.28 | 13 | 111 | 306 | 0 | 59 | 0.24 | online |
| MASK-USD | 2021-07-16 | 2026-10-25 | 42,741 | 7.63 | 13 | 3,518 | 1,264 | 5 | 49 | 0.42 | online |
| MATIC-USD | 2021-03-11 | 2025-10-14 | 40,266 | 0.01 | 3 | 2 | 1 | 1 | 46 | 0.32 | delisted |
| MKR-USD | 2021-01-01 | 2026-01-12 | 44,061 | 0.10 | 8 | 36 | 42 | 0 | 42 | 0.25 | delisted |
| MOODENG-USD | 2025-03-24 | 2026-10-26 | 13,926 | 0.14 | 10 | 9 | 22 | 1 | 24 | 0.28 | online |
| NEAR-USD | 2024-01-14 | 2026-10-26 | 24,374 | 0.05 | 10 | 1 | 0 | 0 | 5 | 0.15 | online |
| NKN-USD | 2021-04-09 | 2026-10-26 | 47,501 | 2.28 | 13 | 1,095 | 1,802 | 14 | 130 | 0.63 | online |
| NU-USD | 2021-01-01 | 2023-02-06 | 18,402 | 0.00 | 0 | 0 | 89 | 5 | 76 | 0.86 | delisted |
| OMG-USD | 2021-01-01 | 2023-03-29 | 19,619 | 0.03 | 3 | 3 | 7 | 1 | 13 | 0.33 | delisted |
| ONDO-USD | 2024-01-22 | 2026-10-26 | 24,165 | 0.04 | 10 | 0 | 0 | 0 | 12 | 0.20 | online |
| OP-USD | 2022-12-29 | 2026-10-26 | 33,422 | 0.32 | 13 | 94 | 124 | 0 | 6 | 0.16 | online |
| OXT-USD | 2021-01-01 | 2026-10-26 | 49,766 | 2.38 | 13 | 1,198 | 1,345 | 6 | 139 | 0.41 | online |
| PENGU-USD | 2025-05-20 | 2026-10-26 | 12,567 | 0.08 | 10 | 0 | 0 | 0 | 3 | 0.12 | online |
| PEPE-USD | 2024-11-13 | 2026-10-26 | 17,062 | 0.06 | 10 | 1 | 1 | 0 | 6 | 0.22 | online |
| PLA-USD | 2021-09-26 | 2024-02-14 | 19,677 | 5.88 | 3 | 1,226 | 2,607 | 6 | 49 | 0.57 | delisted |
| POLY-USD | 2021-08-03 | 2023-12-05 | 20,445 | 0.35 | 3 | 68 | 648 | 3 | 81 | 0.68 | delisted |
| POPCAT-USD | 2025-03-20 | 2026-10-26 | 13,972 | 0.49 | 10 | 59 | 63 | 0 | 3 | 0.20 | online |
| PUMP-USD | 2025-07-15 | 2026-10-26 | 11,210 | 0.09 | 10 | 0 | 0 | 0 | 4 | 0.22 | online |
| QNT-USD | 2021-07-17 | 2026-10-26 | 46,233 | 0.03 | 13 | 3 | 2 | 1 | 46 | 0.41 | online |
| RAVE-USD | 2026-02-24 | 2026-10-26 | 5,825 | 0.55 | 5 | 27 | 8 | 18 | 62 | 0.80 | online |
| REN-USD | 2021-01-01 | 2023-11-03 | 24,860 | 0.09 | 3 | 20 | 183 | 2 | 21 | 0.36 | delisted |
| RENDER-USD | 2024-09-30 | 2026-10-26 | 18,135 | 0.06 | 10 | 0 | 0 | 0 | 7 | 0.25 | online |
| REQ-USD | 2021-10-10 | 2026-10-26 | 41,139 | 6.94 | 13 | 3,057 | 2,503 | 5 | 135 | 0.48 | online |
| RNDR-USD | 2022-12-19 | 2025-06-26 | 22,095 | 0.02 | 3 | 1 | 2 | 1 | 6 | 0.25 | delisted |
| SAND-USD | 2024-10-22 | 2026-10-26 | 17,571 | 0.26 | 10 | 36 | 154 | 0 | 17 | 0.22 | online |
| SEI-USD | 2023-11-01 | 2026-10-26 | 26,151 | 0.04 | 10 | 0 | 0 | 0 | 10 | 0.17 | online |
| SHIB-USD | 2021-09-09 | 2026-10-26 | 44,922 | 0.03 | 13 | 2 | 2 | 2 | 114 | 2.07 | online |
| SKL-USD | 2021-03-11 | 2026-10-26 | 48,445 | 1.74 | 13 | 846 | 443 | 3 | 41 | 0.44 | online |
| SNX-USD | 2021-01-01 | 2026-10-26 | 50,810 | 0.33 | 13 | 154 | 326 | 3 | 31 | 0.37 | online |
| SOL-USD | 2021-06-17 | 2026-10-26 | 46,938 | 0.03 | 13 | 2 | 0 | 0 | 33 | 0.21 | online |
| SPELL-USD | 2021-12-07 | 2026-10-26 | 42,679 | 0.28 | 13 | 108 | 377 | 3 | 121 | 0.31 | online |
| STORJ-USD | 2021-03-25 | 2026-09-28 | 47,149 | 2.41 | 13 | 1,152 | 1,646 | 5 | 72 | 0.38 | delisted |
| STX-USD | 2023-01-17 | 2026-10-26 | 33,055 | 0.05 | 13 | 5 | 1 | 1 | 31 | 0.27 | online |
| SUI-USD | 2023-11-28 | 2026-10-26 | 25,503 | 0.04 | 10 | 0 | 0 | 0 | 6 | 0.18 | online |
| SUPER-USD | 2024-01-07 | 2026-10-26 | 24,487 | 0.27 | 10 | 56 | 62 | 1 | 18 | 0.39 | online |
| SUSHI-USD | 2021-03-11 | 2026-10-26 | 49,230 | 0.15 | 13 | 61 | 44 | 1 | 32 | 0.29 | online |
| SWFTC-USD | 2024-12-09 | 2026-10-26 | 16,150 | 1.91 | 10 | 305 | 656 | 2 | 79 | 0.28 | online |
| TAO-USD | 2025-03-15 | 2026-10-26 | 14,151 | 0.07 | 10 | 0 | 0 | 0 | 4 | 0.13 | online |
| TIA-USD | 2023-11-01 | 2026-10-26 | 26,133 | 0.04 | 10 | 0 | 1 | 0 | 8 | 0.20 | online |
| TOSHI-USD | 2025-08-14 | 2026-10-26 | 10,503 | 0.10 | 10 | 0 | 18 | 1 | 14 | 0.26 | online |
| TRB-USD | 2023-11-12 | 2026-10-26 | 25,810 | 0.34 | 10 | 77 | 118 | 2 | 46 | 0.61 | online |
| TRUMP-USD | 2025-01-21 | 2026-10-26 | 15,385 | 0.19 | 10 | 20 | 36 | 0 | 27 | 0.24 | online |
| UMA-USD | 2021-01-01 | 2026-10-26 | 49,487 | 2.92 | 13 | 1,477 | 1,329 | 5 | 109 | 0.49 | online |
| UNI-USD | 2021-01-01 | 2026-10-26 | 50,962 | 0.03 | 13 | 2 | 1 | 3 | 34 | 0.44 | online |
| USELESS-USD | 2025-08-25 | 2026-10-26 | 10,239 | 0.10 | 10 | 0 | 0 | 0 | 0 | 0.17 | online |
| VET-USD | 2024-10-14 | 2026-10-26 | 17,798 | 0.06 | 10 | 1 | 10 | 0 | 12 | 0.14 | online |
| VVV-USD | 2026-03-27 | 2026-10-26 | 5,108 | 0.10 | 5 | 0 | 0 | 0 | 2 | 0.16 | online |
| WIF-USD | 2024-11-22 | 2026-10-26 | 16,803 | 0.41 | 10 | 60 | 31 | 1 | 3 | 0.32 | online |
| WLUNA-USD | 2021-08-12 | 2022-05-27 | 6,910 | 0.00 | 0 | 0 | 0 | 35 | 65 | 3.09 | delisted |
| XCN-USD | 2024-12-02 | 2026-10-26 | 16,620 | 0.08 | 10 | 3 | 6 | 4 | 93 | 0.45 | online |
| XLM-USD | 2021-01-01 | 2026-10-26 | 50,962 | 0.03 | 13 | 2 | 1 | 2 | 74 | 0.36 | online |
| XRP-USD | 2021-01-01 | 2026-10-26 | 29,246 | 42.63 | 13 | 21,718 | 0 | 0 | 64 | 0.16 | online |
| XTZ-USD | 2021-01-01 | 2026-10-26 | 50,961 | 0.03 | 13 | 3 | 61 | 2 | 44 | 0.43 | online |
| XYO-USD | 2021-09-09 | 2026-10-26 | 44,612 | 0.72 | 13 | 312 | 724 | 9 | 215 | 0.52 | online |
| YFI-USD | 2021-01-01 | 2026-10-26 | 50,904 | 0.14 | 13 | 60 | 215 | 1 | 57 | 0.32 | online |
| ZEC-USD | 2021-02-22 | 2026-10-26 | 49,714 | 0.03 | 13 | 2 | 40 | 1 | 44 | 0.40 | online |
| ZORA-USD | 2025-06-06 | 2026-10-26 | 12,158 | 0.09 | 10 | 1 | 35 | 2 | 39 | 0.40 | online |
| ZRX-USD | 2021-01-01 | 2026-10-26 | 50,943 | 0.07 | 13 | 21 | 160 | 2 | 59 | 0.42 | online |


## 3. Stocks (local Yahoo data, `data/stocks/`)

Measured from the files only (`tradelab/pit/stocks_audit.py`, output `data/pit/stocks_audit.csv`).
116 symbols: S&P 100 constituents plus index and sector ETFs.

| Fact | Kind |
|---|---|
| The symbol list is **today's** S&P 100 (Wikipedia, fetched 2026-10-25). Every backtest on it has survivorship bias: past members that were removed, acquired or went bankrupt are absent, and today's members are included for years before they joined | (b) |
| Daily history: 89 symbols start 2000-01-03; 27 start later (IPO or spin-off); 6,123 bars on average. No missing NYSE session since 2006 in any symbol | (d) |
| **Daily prices are split- and dividend-adjusted retrospectively**: NFLX's close is 111.22 on 2025-11-14 and 110.29 on 2025-11-17, across its 10-for-1 split, and NFLX's first close is $0.12. The prices before any split are not the prices traded then. Levels, round-number effects and price filters on old data are wrong; returns are fine | (b) |
| The daily bar is stamped **09:30 ET** (the session open), yet holds the session's close. Using it at its timestamp would leak the whole day. It is available after 16:00 ET (13:00 on half-days) | (d) / (a) |
| Hourly bars exist only from 2023-11-27 (Yahoo's ~730-day limit; 113 of 115 symbols), ~5,083 bars each. GEV has none | (d) |
| Each symbol has ~7 zero-volume "print" bars at 16:00 or 13:00 ET (the closing print). They are not tradable hours | (d) |
| 12–16 hourly bars missing in covered sessions for a typical symbol (BNY: 138) | (d) |
| Hourly volume sums to a median **75%** of daily volume (IQR 73–81%): hourly bars omit the opening/closing auctions and some off-exchange prints. Hourly volume is not daily volume | (d) |
| **Hourly volume is not split-adjusted; hourly prices are.** Hourly/daily volume ratio: NFLX 0.08 before 2025-11-17 and 0.79 after (10:1); BKNG 0.03 before 2026-04-06 and 0.75 after (25:1). A volume or dollar-volume filter on hourly data is off by the split factor before the split | (d) / (b) |
| **Ticker reuse: BNY.** The hourly "BNY" series disagrees with the daily open by > 2% on 551 days up to 2026-02-06, and its volume is ~1% of daily until 2026-05-22. Before then the hourly series is a different security from the daily one (the symbol was reused). BNY intraday data before 2026-05-22 is unusable | (d) |
| No bid/ask, no trade-level data, no consolidated (SIP) volume; Yahoo's sources and revision policy are undocumented | (d) / (b) |
| Corporate actions, delistings and index changes are not recorded; no point-in-time constituent list exists locally | (b) |

**Consequences.** (c) Stock research on this data can use daily returns and post-2023 hourly returns of
today's large caps. It cannot measure spreads or opening auctions, cannot build a point-in-time universe, and
any result has survivorship bias of unknown size.

### What Alpaca SIP would add, and how it is checked

`tradelab/pit/alpaca_sip.py` is written and unit-tested against fixtures. **It has not been run: no key exists.**

- `AlpacaData.from_env()` reads `TRADELAB_PAPER_APCA_API_KEY_ID` / `TRADELAB_PAPER_APCA_API_SECRET_KEY` from
  the environment, and refuses if any `TRADELAB_LIVE_*` variable is set. Its repr hides both values.
- `verify_paper_key(client)` calls the paper host (`/v2/account`) and the live host. A paper key is accepted by
  the paper host and rejected by the live one. It returns status codes, account status and `is_paper_key`; it
  never returns the account number or the key.
- `verify_entitlement(client, session_open, session_close, symbol="SPY")` requires a session that closed at
  least a day ago (the free plan withholds the last 15 minutes of SIP). It compares SIP and IEX minute-bar
  volume for the session and samples one minute of SIP quotes and trades an hour before the close. Verdict
  `sip` needs SIP volume well above IEX volume **and** quotes and trades from exchanges other than IEX (code
  `V`). Other verdicts: `iex_only`, `forbidden`, `error`, `unclear`.
- Run it once the paper key is in the environment: `.venv/bin/python scripts/pit_verify_alpaca.py`.

If the verdict is `sip`, the data adds (a) consolidated minute bars from 2016, quotes and trades with exchange
codes and timestamps, which make spread and auction measurement possible. It does not fix survivorship: Alpaca
lists current symbols, and point-in-time constituents still need a separate source.

## 4. Loader API

    from tradelab.pit.crypto_universe import eligible_at
    from tradelab.pit.crypto_bars import load_hourly, panel

    eligible_at(t, path=OUT, live_status=None) -> list[str]
    load_hourly(products, start=None, end=None, as_of=None, root=HOURLY_DIR) -> dict[str, pd.DataFrame]
    panel(products, field="close", start=None, end=None, as_of=None, root=HOURLY_DIR) -> pd.DataFrame

- `eligible_at(t)` returns the products eligible on t's UTC date under the rule above. Pass `live_status`
  (from `coinbase_status()`) only for today.
- `load_hourly` returns, per product, bars indexed by `time` with `available_at` and `received_at`; `as_of`
  keeps only bars with `available_at <= as_of`.
- `panel` aligns one field on a full hourly grid. An hour without a candle is NaN; nothing is forward-filled.
