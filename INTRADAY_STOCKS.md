# Stock intraday research: S1, S2, S3

Date: 2026-10-25. Binding plan: `INTRADAY_HYPOTHESES.md` (doc hash 82411ebd4b5b4d78, including Amendment 1 for S2).
Reproduce:

    .venv/bin/python -m tradelab.intraday.research.stocks_data      # fetch universe + daily/hourly/5m bars
    .venv/bin/python research/intraday/stocks/data_check.py
    .venv/bin/python research/intraday/stocks/study.py dev|val|freeze|test|explore    # test refuses a second run
    .venv/bin/python -m pytest -q tests/test_intraday_stocks_*.py

## Verdict

**No stock hypothesis meets the evidence standard. S1 and S2 are rejected; S3 is untestable with the
available data.** The only positive test-period result was S2's ETF-only variant, at +0.05% per trade after base
costs. It fails the bootstrap lower bound (E1), Sharpe (E2), stress costs (E3) and the multiple-testing
adjustment (E6), and it turns negative when the opening spread is assumed to be 10 bp.

## Data used

| Item | Detail |
|---|---|
| Source | Yahoo chart API (unofficial, no key); fetched 2026-10-25, fetch time stored in every file |
| Universe | 101 current S&P 100 members (Wikipedia, `data/stocks/universe.csv` with URL and fetch date), SPY QQQ IWM DIA, 11 SPDR sector ETFs |
| Daily | 2000-01-03 → 2026-10-23, split-adjusted. 9 rows blanked (open outside the day's range, zero volume) |
| Hourly | 2023-11-27 → 2026-10-23. Bars start 09:30, 10:30 … 15:30 ET. GEV has no hourly file: Yahoo refused the 730-day range |
| 5-minute | 2026-07-31 → 2026-10-23 (60 days); S3 exploratory only |
| Alignment | Hourly 15:30-bar close vs official daily close: median gap 1.5 bp |
| Validity filter (S1) | A session is dropped when the hourly 09:30 open differs from the official daily open by more than 2%. This uses only information available at the open, so it isn't look-ahead. It removed 577 symbol-sessions, 548 of them BNY: its hourly series is a different ~$10 security (a reused ticker) until 2026, while its daily series is BNY Mellon throughout |
| Corporate actions | Spin-offs (MO 2008, MDLZ 2012) and mergers (TMUS 2013) show artificial overnight "gaps" in the S2 signal. Trade P&L uses the same day's open and close, so it isn't distorted |

**Survivorship bias (S2, and S1 to a lesser degree).** The stock universe is *today's* S&P 100. Firms that were
large caps and later failed, were acquired or were delisted are missing. That inflates a buy-the-losers rule,
most of all in 2000–2015. The ETF-only variant has no survivorship issue, and the 2021+ test window is
much less affected. Earnings dates are not available historically, so earnings gaps could not be excluded.

## Trials (all logged in `research/registry.jsonl`)

| Trial | Period | Trades | Gross / trade | Net / trade | Win rate | Daily Sharpe |
|---|---|---|---|---|---|---|
| S1 default (thr 0.25%, top 5, all) | dev 2023-11-27 → 2025-01-24 | 1,427 | +0.000% | −0.080% | 42% | −4.08 |
| S1 thr 0.50% | dev | 1,426 | −0.000% | −0.080% | 42% | −4.11 |
| S1 index ETFs only | dev | 441 | −0.009% | −0.089% | 29% | −5.26 |
| S1 SPY only | dev | 101 | −0.006% | −0.086% | 26% | −4.27 |
| S1 long/short | dev | 1,440 | −0.001% | −0.081% | 42% | −4.47 |
| S2 default (gap ≤ −1%, top 5, stocks+sector) | dev 2000–2015 | 10,940 | +0.277% | +0.197% | 53% | +1.14 |
| S2 gap ≤ −2% | dev | 4,107 | +0.345% | +0.265% | 51% | +0.75 |
| S2 top 3 | dev | 8,206 | +0.281% | +0.201% | 53% | +1.20 |
| S2 ETF-only | dev | 512 | +0.236% | +0.156% | 54% | +0.19 |
| S2 −3% stop (hourly window only) | 2023-11-27 → 2026-10-23 | 3,006 | | −0.232% | | −1.49 |
| S3 ORB exploratory | 60 days | 451 | −0.089% | −0.189% | 30% | (unreliable) |

11 stock configurations. **E6 uses n_trials = 73 prior + 11 stock + 12 crypto (assumed) = 96.** The variance of
per-day Sharpe across stock dev trials is 0.0278, stored in `research/intraday/stocks/out/test.json` (`E6_trial_sr_var`).

**Validation (2016–2020 for S2; 2025-01-27 → 2025-08-25 for S1). Confirm only, nothing selected:**

| Config | Trades | Gross | Net | Daily Sharpe |
|---|---|---|---|---|
| S1 default | 724 | −0.024% | −0.104% | −4.45 |
| S1 long/short | 725 | −0.022% | −0.102% | −3.49 |
| S2 default | 3,488 | +0.063% | −0.017% | −0.14 |
| S2 ETF-only | 227 | +0.144% | +0.064% | +0.14 |

S2's large development-period edge had mostly disappeared by 2016–2020. That fits survivorship inflating the early
period, the effect decaying, or both.

**Frozen for the test:** the pre-registered defaults (S1 default, S2 default) and the required or labelled
variants (S1 long/short, S2 ETF-only). They were logged as `intraday_stocks_frozen:*` before the test. No test
configuration was chosen from development results. The first test invocation crashed (missing GEV hourly file in the secondary stop
variant) before any metric was printed, saved or recorded. That is logged as `intraday_stocks_test_attempt_crashed`,
and the identical frozen run was then executed once.

## Test results (untouched; S2 2021-01-04 → 2026-10-23, S1 2025-08-26 → 2026-10-23)

| | S1 default | S1 long/short (labelled) | S2 default | S2 ETF-only |
|---|---|---|---|---|
| Trades | 1,445 | 1,445 | 5,732 | 548 |
| Gross / trade | +0.020% | +0.034% | +0.062% | +0.126% |
| Net / trade (base) | −0.060% | −0.046% | −0.018% | +0.046% |
| Win rate | 43% | 45% | 50% | 51% |
| **E1** bootstrap 5% lower bound > 0 | −0.107% FAIL | −0.095% FAIL | −0.102% FAIL | −0.053% FAIL |
| **E2** daily Sharpe ≥ 0.5 | −2.62 FAIL | −1.65 FAIL | −0.15 FAIL | +0.24 FAIL |
| **E3** stress mean > 0 | −0.220% FAIL | −0.206% FAIL | −0.178% FAIL | −0.114% FAIL |
| **E4** ≥ 2 of 3 thirds positive | −14.6% / +0.3% / −3.2% FAIL | −7.0% / −7.4% / +1.1% FAIL | −12.8% / +2.3% / −10.0% FAIL | +4.6% / +0.6% / −0.1% PASS |
| **E5** placebo p < 0.05 | 0.994 FAIL | 0.929 FAIL | 0.265 FAIL | 0.045 PASS |
| **E6** DSR ≥ 0.95 (96 trials) | 0.00 FAIL | 0.00 FAIL | 0.00 FAIL | 0.00 FAIL |
| **E7** ≥ 100 trades | PASS | PASS | PASS | PASS |
| Entry cost 10 bp (sensitivity) | | | −0.068%, Sharpe −0.56 | −0.004%, Sharpe −0.02 |
| **All E1–E7** | **FAIL** | **FAIL** | **FAIL** | **FAIL** |

E4 thirds are sums of daily P&L (fraction of equity) per third. E5 placebo: 1,000 replications.
- S1: random test days and symbols, same trades per day, same side, 15:30 → close.
- S2: same sessions and position counts, symbols drawn at random from the liquidity-eligible pool, open → close.

## Verdicts

- **S1, market intraday momentum: rejected.** Its gross edge is about +0.02% per trade against about 0.08% round-trip cost,
  and it does worse than random 15:30 entries (placebo p 0.99). The long/short variant is also rejected. The hourly
  sample is short (about 290 test days), but the point estimate is negative, not merely uncertain.
- **S2, overnight gap reversal: rejected** on the stock universe: net −0.018% per trade, no criterion besides E7
  passes. The ETF-only variant's sign is positive, so the doc's extra rejection condition doesn't trigger. But it
  fails E1/E2/E3/E6 and turns negative with a 10 bp opening spread. **Not rejected outright, but with insufficient
  evidence.** It can be monitored prospectively, not traded.
- **S3, opening-range breakout: untestable** (needs multi-year 5-minute data, e.g. an Alpaca data key).
  The 60-day exploratory look is negative (−0.19% per trade net, 30% win rate) and carries no evidential weight either way.

## Rules the engine must implement to reproduce the test trades

Times are America/New_York. Trade lists are in `research/intraday/stocks/out/test_trades_*.csv`, with columns
session, symbol, side, signal, entry_time_utc, entry_px, exit_time_utc, exit_px, gross_ret, cost, net_ret, size_weight.

**S1 default** (`test_trades_S1_default_thr0.25_top5_all.csv`)
- Universe: the S&P 100 list plus SPY/QQQ/IWM/DIA. Skip any session where the hourly 09:30 open differs from the
  official open by more than 2%, or where there is no 15:30 bar (half days).
- Signal: r = close of the 09:30–10:30 hourly bar / previous session's official close − 1.
- Selection at 15:30: long if r ≥ 0.0025. Rank by r descending and take the first 5.
- Entry: open of the 15:30 bar, intraday market order. Cost 5 bp base, 15 bp stress.
- Exit: official close, MOC order. Cost 3 bp base, 9 bp stress.
- Size: weight 0.20 each, so at most 100% gross. Maximum holding 30 minutes. No stop.

**S1 long/short** (`..._S1_longshort_thr0.25_top5_all.csv`)
- Same as S1 default, except: trade the sign of r when |r| ≥ 0.0025, and rank by |r|.
- Short net = entry·(1−c_in) / (exit·(1+c_out)) − 1. Borrow cost is ignored.

**S2 default** (`..._S2_default_thr1_top5_stocks+sector.csv`)
- Universe: S&P 100 stocks plus the 11 sector ETFs. SPY is the market reference.
- Eligibility at session t:
  - previous close > $10;
  - median(close × volume) over the 20 sessions ending t−1 (at least 15 present) > $50M;
  - relative gap g = (open_t / close_{t−1} − 1) − (SPY open_t / SPY close_{t−1} − 1) satisfies g ≤ −0.01 and |g| < 0.5.
- Selection: the 5 most negative g.
- Entry: marketable order immediately after the opening print, filled at the official open. Cost 5 bp base,
  15 bp stress, 10 bp sensitivity.
- Exit: MOC at the official close. Cost 3 bp base, 9 bp stress.
- Size: weight 0.20 each. Maximum holding is one session. No stop.

**S2 ETF-only** (`..._S2_etf_only_thr1_top5.csv`)
- Same as S2 default, but the universe is the 11 sector ETFs plus QQQ, IWM and DIA.

## Limitations

- Yahoo is unofficial. Data can be revised or withdrawn, and the rate limit depends on the client's user-agent string.
- Survivorship bias as described above. There are no point-in-time index constituents and no delisted prices.
- Daily data can't time stops inside the session. The stop variant fills at the close of the hourly bar where the stop
  is breached, within the hourly window only.
- Short sample for S1, about 290 test days.
- The cost model assumes liquid large caps. Real opening-auction spreads for some names can exceed 10 bp.
- The E6 trial count assumes 12 crypto trials; recompute with the crypto worker's actual count using the stored
  per-day Sharpe statistics (`daily_mean`, `daily_std`, `daily_skew`, `daily_kurt` in `test.json`).
