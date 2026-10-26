# Intraday hypotheses: pre-registration

Written 2026-10-25, **before any intraday data was analysed**. Rules, splits, costs and rejection criteria
below are frozen; the registry (`research/registry.jsonl`, `prereg_intraday:*`) carries the same text.
Stocks and crypto are researched separately. Nothing is assumed to transfer between them.

## Two questions that are kept apart

1. **Does the engine work?** Does it scan, decide, size, enter, manage and exit trades correctly in paper mode,
   within its risk limits? Software tests and paper replays answer this.
2. **Does a strategy have an advantage?** Only the evidence standard below answers this. A working engine,
   a high win rate, in-sample results, or passing tests are not evidence of an advantage.

## Evidence standard (all must hold on the untouched test period, after base costs)

| # | Criterion |
|---|---|
| E1 | Mean net return per trade > 0, with the one-sided 95% block-bootstrap lower bound > 0 |
| E2 | Annualised Sharpe of daily net P&L ≥ 0.5, accounting for the days with no trade |
| E3 | Net mean > 0 under stress costs (stocks 3×, crypto taker + 0.15% slippage per side) |
| E4 | Positive net result in at least 2 of 3 equal sub-periods of the test window |
| E5 | Beats a placebo: random entries with the same count, side, time of day and holding time (p < 0.05) |
| E6 | Deflated Sharpe ratio ≥ 0.95, counting every configuration tried in **both** markets |
| E7 | At least 100 test-period trades |

Passing all seven means "backtest evidence of an advantage", **not** "profitable". A live trial would
additionally need prospective paper results (see the end of this file).

## Cost models (per side)

| Market | Base | Stress |
|---|---|---|
| US stocks at the open/close auction (MOO/MOC) | 3 bp (impact + regulatory sell fees; $0 commission) | 9 bp |
| US stocks, intraday market order | 5 bp (half-spread + slippage, liquid large caps) | 15 bp |
| Crypto, Coinbase taker | 0.66% (0.60% fee + 1 bp half-spread + 5 bp slippage) | 0.81% |
| Crypto, Coinbase maker (limit) | 0.40%, with fills only when price trades through | n/a |

## Data splits

| Data | Development | Validation | Untouched test |
|---|---|---|---|
| Stocks, daily open/close (Yahoo, 2000→) | 2000-01-01 → 2015-12-31 | 2016-01-01 → 2020-12-31 | 2021-01-01 → 2026-10-23 |
| Stocks, hourly (Yahoo, 2023-11-27→) | first 40% of days | next 20% | last 40% |
| Crypto, 1-minute/5-minute (Coinbase, 2020→) | 2020-01-01 → 2022-12-31 | 2023-01-01 → 2023-12-31 | 2024-01-01 → 2026-10-24 |

Parameter searches are allowed only in development: at most 6 configurations per hypothesis, all logged.
Validation chooses nothing; it only confirms. The test is run once.

---

## Stocks

### S1. Market intraday momentum (index ETFs and liquid large caps)

- **Claim.** The return from the previous close to 10:30 ET predicts the 15:30–16:00 ET return, in the same direction.
- **Why it could work.** Documented for SPY (Gao, Han, Li & Zhou, *JFE* 2018). The proposed mechanisms are
  late-informed traders, end-of-day rebalancing, and option dealers' hedging flows near the close.
- **Rule.**
  - Signal: at 15:30 ET, compute r = (price at 10:30) / (previous close) − 1. If |r| ≥ 0.25%, trade in the sign of r.
  - Long-only (the default): trade only when r > 0. Long/short is studied separately, because shorting needs a margin account.
  - Execution: enter at the 15:30 bar's open with a market order; exit at the close with an MOC order.
  - Size: equal weight, at most 5 positions, each at most 20% of equity. Maximum holding: 30 minutes.
- **Data.** 1-hour bars (Yahoo, about 2 years) for SPY, QQQ, IWM, DIA and the current S&P 100.
- **Rejected if** E1–E7 fail. **Known weakness:** about 200 test days, so only a large effect can pass.
  The published effect is a few bp per day against 8 bp of round-trip cost. Failure is the expected outcome.

### S2. Overnight gap reversal in large caps

- **Claim.** Stocks that gap down at the open relative to the market earn a positive open-to-close return the same day.
- **Why it could work.** Overnight and intraday returns are negatively related across stocks (Lou, Polk &
  Skouras, *JFE* 2019). Opening sell pressure from retail and overnight traders is absorbed by intraday
  liquidity providers, who are paid for it.
- **Rule.**
  - Signal: at the open, gap_i = open / previous close − 1, minus SPY's gap. Candidates have gap_i ≤ −1.0%,
    price > $10 and 20-day median dollar volume > $50M.
  - Execution: buy the 5 most negative at the open auction (MOO); sell at the close auction (MOC). No stop by default.
    A −3% stop variant is tested, filled at the next hourly bar, because daily data cannot time a stop inside the day.
  - Size: equal weight, at most 20% of equity each. Maximum holding: one session.
- **Data.** Daily OHLC 2000→ (Yahoo, split-adjusted). Universe: current S&P 100 plus sector ETFs.
- **Survivorship warning.** The universe is today's large caps. Companies that failed are missing, which biases
  a buy-the-losers rule **upward**. Mitigations: an ETF-only variant (no survivorship), and reporting
  2021→ separately. Ex-dividend gaps are included as noise. Earnings dates are not available historically,
  so earnings gaps cannot be excluded.
- **Rejected if** E1–E7 fail on the stock universe, **or** the sign is not positive on the ETF-only variant.

### S3. Opening-range breakout in "stocks in play" (data-blocked)

- **Claim.** Liquid stocks with unusually high opening volume continue in the direction of the first 5-minute
  bar (Zarattini & Aziz 2023).
- **Status.** Not testable: Yahoo serves only 60 days of 5-minute data. It needs a broker data key
  (e.g. Alpaca) for 2016→ history. Any 60-day look is labelled exploratory and cannot pass.

## Crypto (Coinbase spot, 24/7)

### C1. Liquidation-cascade reversal

- **Claim.** After an extreme 1-hour drop, BTC/ETH/SOL partly rebound over the next 1–6 hours.
- **Why it could work.** Forced liquidations and stop cascades push the price below fair value for a short time;
  the buyers who absorb that pressure earn the rebound. The fee hurdle is high (about 1.3% round trip), so it can only
  pay on extreme events.
- **Rule.**
  - Signal: on a completed 1-hour bar, r_1h ≤ −k·σ, where σ is the trailing 30-day standard deviation of
    1-hour returns. k ∈ {3, 4} in development; 4 is the pre-specified default.
  - Entry: buy at the next 5-minute bar's open (taker), or a maker variant with a limit order 0.3% below,
    valid 15 minutes, filled only if price trades through.
  - Exit: whichever comes first — +1.5σ_1h target, −1.5σ_1h stop (stop assumed hit first if both fall in one bar),
    or 6 hours.
  - Size: risk 1% of equity at the stop, at most 25% of equity per trade, one position per coin.
- **Data.** Coinbase 1-minute candles 2020→ for BTC/ETH/SOL. Holdout coins: other Coinbase USD products
  that pass a point-in-time liquidity filter of 30-day median daily volume > $20M.
- **Rejected if** E1–E7 fail, or the gross rebound is smaller than round-trip cost.

### C2. Crypto intraday time-series momentum

- **Claim.** BTC/ETH's return over the first 6 hours of the UTC day predicts the rest of that day, in the same direction.
- **Why it could work.** Intraday momentum has been reported for Bitcoin, for example the first half-hour predicting
  the last. Half-hour moves can't clear 1.3% fees, so the window is stretched to 6h → 18h.
- **Rule.** Long-only. At 06:00 UTC, if r(00:00→06:00) ≥ +1.0·σ_6h, buy (taker). Exit at 23:55 UTC or on a
  −2·σ_6h stop. Size: 1% risk at the stop, at most 25% of equity.
- **Data.** Coinbase 5-minute candles 2020→.
- **Rejected if** E1–E7 fail.

## Trial accounting

Phase-1 to phase-3 daily research used 73 configurations. These hypotheses add at most 6 each
(≤ 30 in total). E6 uses the combined count.

## Before any live trial (separately authorised)

Even a strategy that passes E1–E7 also needs all of the following:

- at least 3 months of prospective paper trading, with *(Forward-period rule reconciled 2026-10-26: STATUS.md §Rules.)*
  - at least 60 trades,
  - net results consistent with the backtest's 90% interval,
  - realised fills and slippage within the cost model;
- no risk-limit incidents;
- the broker's actual fees and rules confirmed;
- your written approval of the exact configuration.

## Amendment 1 (2026-10-25, before any S2 test-period result existed)

**S2 entry was look-ahead.** A market-on-open (MOO) order must be submitted before the opening auction,
but S2's signal is the gap measured *at* the official open. The order cannot be conditioned on the price it
receives. Corrected rule:

- Entry is a marketable order sent after the opening print, filled at the official open price plus the
  **intraday market-order cost: 5 bp base, 15 bp stress**, instead of the MOO cost (3 / 9 bp).
- The opening minutes have wider spreads, so a sensitivity at 10 bp base is also reported.
- The exit stays an MOC order, which is legitimate because it is a time exit not conditioned on the closing price.

S1 is unaffected: its signal uses the 10:30 price, and it enters at 15:30.
