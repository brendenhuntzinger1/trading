# Pre-registration: 5-minute opening-range breakout on US "Stocks in Play" (ORB-SIP)

Written 2026-10-25, before any ORB evaluation. **Not run.** The registry entry `prereg_orb` carries this file's
SHA-256 prefix. Any later change is a dated amendment that states what had been seen first.

## Source and what was read

- **Rules source, read in full:** Zarattini, Barbon & Aziz, *A Profitable Day Trading Strategy For The U.S.
  Equity Market*, SSRN 4729284 / Swiss Finance Institute RP 24-98, dated 2024-02-16. Full text from
  https://alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content
  (abstract page: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284).
- **Correction to my earlier report:** the earlier paper, Zarattini & Aziz, SSRN 4416622, is the authors' QQQ/TQQQ
  5-minute ORB study (reference [23] in the 2024 paper). It is **not** the source of the Stocks-in-Play rules.
  Its full text was not read: SSRN returned 403.

### The paper's rules (quoted or exact)

| Item | Paper |
|---|---|
| Data | All NYSE and Nasdaq equities, 2016-01-01 → 2023-12-31, ~7,000 stocks, "free from survivorship bias" (CRSP); intraday from IQFeed, **unadjusted** for splits and dividends |
| Filters | "opening price had to be above $5"; "average trading volume over the previous 14 days … at least 1,000,000 shares per day"; "ATR over the previous 14 days had to be more than $0.50" |
| Relative volume | RV(t,j) = OR volume in the first 5 minutes on day t ÷ mean of the first-5-minute volume over the previous 14 days |
| Stocks in Play | RV ≥ 100%; trade only the **top 20** by RV |
| Direction | First 5-minute candle (09:30–09:35 ET): bullish → long only; bearish → short only; doji (open = close) → no order |
| Entry | A **stop order** at the opening-range high (long) or low (short), placed after 09:35 ET |
| Stop loss | "10% ATR distance from the executed entry price" |
| Target / exit | None; unwind "at the end of the trading session (i.e., 4:00 pm ET)" |
| Sizing | Lose 1% of capital if stopped; **maximum leverage 4×** (so some trades risk less than 1%) |
| Costs | Commission **$0.0035 per share** (IB Pro tiered). **The paper never mentions spreads, slippage, borrow fees, short-sale availability or partial fills** (full-text search, 2026-10-25) |
| Capital | $25,000 start |
| Results (net of commission only) | Base 5-minute ORB (no RV filter): Sharpe 0.48, IRR 3.2%, hit 41.4%. **ORB + RV (top 20): total 1,637%, IRR 41.6%, vol 14.8%, Sharpe 2.81, hit 48.4%, MDD 12%, alpha 35.8%/yr, beta 0.00.** Avg PnL per trade: −0.02R at RV < 100%, **+0.08R at RV > 100%**, +0.38R at RV > 30× |
| Out-of-sample | **None.** The authors say the parameters "were minimal and based on economic rationale rather than retrospective optimization" |

### What +0.08R means in price terms (why costs decide this test)

- One unit of risk R is 10% of the 14-day ATR. For stocks in play with ATR/price ≈ 3–6%, R ≈ **30–60 bp of price**.
- The paper's +0.08R per trade is therefore about **2–5 bp**. Its +0.38R (RV > 30×) is about 11–23 bp.
- A round trip at our base stock cost (10 bp per side, below) is **20 bp**, or 0.3–0.7R.
- **Under our assumed costs, the paper's average trade is negative.** Only a measured spread far below 10 bp
  per side, or a strong concentration of edge in extreme RV, could change that. This is stated before any data.

## 1. Economic hypothesis

A large, abnormal opening imbalance on a news day (relative volume ≥ 1) persists through the session, because
institutions re-position over hours rather than minutes. The breakout of the 5-minute range in the direction of
the first candle captures part of that persistence. Prediction: on Stocks-in-Play days, gross returns from the
breakout are positive and increase with relative volume. On low-RV days they are near zero.

## 2. Universe and selection (computed each day from data available at 09:35 ET)

- All US common stocks and ETFs listed on NYSE/Nasdaq/NYSE American/Arca that day, from the Alpaca asset
  master, **including inactive symbols**. Use `asof` symbol mapping. Survivorship check before dev: confirm
  bars exist for at least 10 known delisted names (e.g. TWTR before 2022-10-27).
- **Filters exactly as the paper:**
  - the day's opening price > $5;
  - 14-day average daily volume ≥ 1,000,000 shares;
  - 14-day ATR > $0.50 (split-adjusted daily bars, previous 14 sessions);
  - RV ≥ 1.0;
  - top 20 by RV;
  - doji excluded.
- **Data source must be SIP** (consolidated). If only IEX is permitted, the study does not run (see
  docs/ALPACA_DATA_AUDIT.md).

## 3. Signal timing (America/New_York; daylight saving from `exchange_calendars` XNYS)

- Opening range: 1-minute SIP bars starting 09:30–09:34, aggregated. Decision at 09:35:00 ET.
- On half-days the rules are unchanged; the exit is the 13:00 close.
- Orders are active from the 09:35 bar onward.

## 4. Entry, exit, sizing

- **Entry:** a buy-stop at the OR high (long) or sell-stop at the OR low (short), triggered by the first
  1-minute bar after 09:35 whose high (low) exceeds the level.
  - Fill = max(stop, bar open) for longs, min(stop, bar open) for shorts, plus slippage.
  - A stop gapped through fills at the bar's open, not at the stop price.
  - An order never triggered before the close means no trade.
- **Stop loss:** 0.10 × ATR14 from the executed price, checked on 1-minute bars. Fill at the stop, or at the bar
  open if gapped through, plus slippage. If entry and stop occur in the same minute, the stop is assumed hit.
- **Exit:** the official close. MOC cost applies; on bars, the 15:59 bar close is used where no official close exists.
- **Sizing, with our constraint overriding the paper:**
  - Risk 1% at the stop.
  - **Total gross exposure ≤ 1× equity.** The paper allows 4×.
  - With 20 candidates and R ≈ 0.3–0.6% of price, the 1% risk rule asks for 2–3× equity *per position*, so the
    1× cap binds on essentially every day. Effective sizing becomes about equal weight, roughly 5% of equity per
    triggered position.
  - **Consequence:** per-trade results in R and in bp are unaffected. Portfolio returns and volatility are about
    ¼ of the paper's 4× version, and its Sharpe ratio is comparable. Results are reported in R, in bp per trade,
    and as a 1× portfolio.
- **Primary study: long-only** (no shorting). **Labelled secondary study: long/short as in the paper.** Borrow
  availability and fees are not modelled, so short results are an upper bound.

## 5. Data exclusions (decided now)

- No 09:30 SIP bar, or the first trade after 09:35 (late open or halt): excluded that day.
- Trading halt during the position (a gap of 5+ consecutive missing minutes for a stock with RV ≥ 1): the
  position is marked at the first bar after the halt and the trade flagged.
- Corporate-action days (split or spin-off effective that day): excluded.
- **Our prior exposure:** I looked at Yahoo 5-minute data for the 60 sessions ending 2026-10-23 for an
  exploratory S3 test (−0.19%/trade net; INTRADAY_STOCKS.md). That window (2026-07-27 → 2026-10-23) is
  excluded from every period below.

## 6. Costs and fills (per side)

| Component | Base | Stress | Status |
|---|---|---|---|
| Commission | $0 (Alpaca, secondary) — also report the paper's $0.0035/share | $0.0035/share | S |
| SEC fee (sells) | 0.21 bp from 2026-04-04; $0 before | same | **V** |
| Half-spread + slippage at stop entry/exit | **measured** from SIP quotes (half the NBBO spread at trigger + 1 bp), if NBBO is confirmed; else **10 bp** | 25 bp | A |
| MOC exit | 3 bp | 9 bp | A |

## 7. Benchmarks

- Cash (0).
- SPY buy-and-hold over the same days (beta and correlation reported).
- **Placebo:** the same selected stock-days, a random side, entry at a random 1-minute time drawn from the
  realised entry-time distribution, same stop and exit rules. 1,000 replications. This isolates the directional
  information.
- The paper's figures: +0.08R per trade; Sharpe 2.81 at 4× net of commission only.

## 8. Periods: honest about overlap

| Period | Dates | Status |
|---|---|---|
| Development (replication) | 2016-01-04 → 2019-12-31 | Inside the authors' sample. Their result is known, so this can only replicate. |
| Validation | 2020-01-02 → 2023-12-29 | Also inside the authors' sample. **Not independent.** Used only to confirm the implementation matches the paper. |
| **Untouched test** | **2024-01-02 → 2026-07-24** (~645 sessions) | After the authors' sample ended. Never examined by me with any data source. The authors published on 2024-02-16; January 2024 is inside the window. |

**Implementation sanity gate (dev):** if gross R per trade at RV ≥ 1 in dev differs from the paper's +0.08R
(net of commission) by more than its 95% interval, the data or implementation is suspect. Stop and investigate
before validation.

## 9. Trials

- At most 6 configurations: the paper rules long-only (primary), long/short (labelled), and up to 4 dev-only
  variants (RV threshold 1 / 2 / 5; top-N 10 / 20).
- The frozen config is logged before the test. Cost variants are sensitivity, not trials.
- E6 uses N = 91 + the number of configurations actually tried.

## 10. Decision criteria (test period, daily P&L series, base costs)

- **PASS** (backtest evidence only, never live-eligible by itself): E1–E7 from INTRADAY_HYPOTHESES.md all hold.
- **REJECT: evidence of no useful effect.** The one-sided 95% **upper** bound of the gross mean per trade is
  below the base round-trip cost. Or the long-only gross mean is ≤ 0 and its upper bound is below the
  minimum detectable effect (MDE) below.
- **INCONCLUSIVE:** neither of the above. The report must then state the effect size that *could* still exist
  given the interval.

## 11. Power: what the test can detect

- **Expected trades:** with the top 20 armed per day and an unknown trigger rate (assume 50–100%), the test has
  about 6,500–13,000 trades over about 645 days.
- **Per-trade spread:** stops near −1R and a fat right tail. Assume a standard deviation of about 3R.
- **Day clustering:** inference uses a daily block bootstrap; the effective n is lower than the trade count.
- **MDE** (one-sided α = 0.05, power 0.8): 2.49 × 3R / √n = **≈ 0.07–0.09R**, about **2–5 bp per trade**. That
  is smaller than the base round trip (20 bp), so a clear rejection is achievable. The paper's own +0.08R sits
  right at the MDE, so an honest "inconclusive" for the gross edge is also a plausible outcome. The assumed
  3R spread is replaced by the dev-period estimate before the test, and the revision is logged.

## 12. Requirements before running

1. A paper-only Alpaca key in environment secrets (docs/CREDENTIALS_SETUP.md).
2. Confirmed historical **SIP** access for that account. If only IEX is available, stop.
3. A delisted-coverage check.
4. Disk for the reduced dataset (< 5 GB per the download plan in docs/ALPACA_DATA_AUDIT.md).
