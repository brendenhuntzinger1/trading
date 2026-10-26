# Phase 2 research protocol (pre-registered before any phase-2 result)

Written 2026-10-26 ~12:00 UTC, under the owner's authorisation of an expanded, bounded research phase (paper only,
free data, no purchases). **Every criterion below is fixed before any phase-2 outcome is computed.** A change
needs a dated amendment in this file, a `change` entry in `research/registry.jsonl`, and a reason that does not
depend on results. Criteria are never loosened after results are seen.

## 1. Scope and budget
- **Screen 10–15 economically distinct families** (`research/phase2/FAMILIES.md`). Reject unsuitable ones
  before any code is written, with the reason recorded.
- **Implement at most 6 families.** Each gets one simple baseline and **at most 4 development configurations**,
  so at most 30 phase-2 trials.
- No expansion beyond that without a new owner review.
- **Trial accounting:**
  - every configuration evaluated on outcome data (baselines included) is recorded in the registry as a
    `result` with `metrics.is_trial = true`;
  - the selection-bias N for deflated Sharpe is 108 (all earlier trials) plus every phase-2 trial
    (`python research/ledger.py trials`).
- Before a family is coded, `python research/ledger.py dedup "<description>"` is run. Overlaps with earlier
  hypotheses are stated in the family's specification.

## 2. Data, chronology and honesty labels
Data:
- **US stocks and ETFs:** Alpaca market data v2, `feed=sip` (consolidated). Daily bars with `all` adjustment for
  returns and `raw` for price and dollar-volume filters. Intraday bars and NBBO quotes where needed.
- **Universe:** asset master + delisted + corporate-action tickers (`research/phase2/data.py`). Corporate actions
  exist only from 2020, so **2016–2019 is survivorship-affected**.

| Window | Stocks (cross-section) | ETFs (single-instrument families) | Use |
|---|---|---|---|
| Training / stress | 2016-01-04 → 2019-12-31 | (part of development) | Model fitting and stress tests only; never used to qualify (survivorship) |
| **Development** | 2020-01-02 → 2022-12-30 | 2016-01-04 → 2022-12-30 | Baseline + ≤ 4 configurations; diagnosis |
| **Validation** | 2023-01-03 → 2024-06-28 | same | Frozen candidate only |
| **Final** | 2024-07-01 → 2026-10-23 | same | Read only for a validated candidate |
| Recent subsets of the final window | last 12 months 2025-10-24 → 2026-10-23; last 90 days 2026-07-26 → 2026-10-23 | same | Reported separately with sample sizes and intervals; **never used for selection** |
| Prospective | from registration of a frozen candidate | same | Forward paper trading with fresh data |

**Honesty labels:**
- Every result states which of its windows were already inspected by earlier studies (`TESTED_INVENTORY.md`,
  `research/consumed_data.json`). For example, SPY and other ETFs 2016–2026 open/close data was examined by
  S1, S2, S2-ETF and S2X.
- A final window inspected for an *other* hypothesis is labelled **"previously inspected market data"**. A pass
  there can at most be **"historically qualified, prospective evidence required"**.
- Crypto history is fully consumed for cross-sectional and daily/intraday scopes, so crypto families are
  **prospective-only**.

**Point-in-time rules:**
- A decision at time *t* uses only bars that ended before *t*.
- Daily decisions at the close use data through the prior close, unless the rule explicitly trades the closing
  auction with information available by 15:50 ET.
- Universe filters use raw prices and trailing volumes known at *t*.
- Corporate-action-adjusted returns never feed a filter.

## 3. Costs (assumed vs measured, always labelled)
- **Spreads:**
  - measured NBBO half-spreads where a family's trades are sampled (SIP quotes at the decision minute);
  - otherwise the measured liquidity tiers below, which are **assumptions**:
    - ETFs SPY/QQQ/IWM/DIA: 0.5 bp per side;
    - other ETFs and large caps (dollar volume ≥ $100M per day): 2 bp;
    - $20–100M: 5 bp;
    - below $20M: excluded.
- **Slippage beyond the touch:** 1 bp per side base, 5 bp stress (assumption).
- **Fees:** SEC fee and FINRA TAF on sales; commission $0 (Alpaca).
- **Short positions** (where a family needs them):
  - borrow is not modelled, so short legs are labelled **upper bound**;
  - primary configurations are long-only unless the hypothesis is inherently long/short;
  - a long/short configuration then reports its long leg separately.
- **Market-on-open / market-on-close auctions:** half-spread of the last pre-auction quote, plus 1 bp (assumption).

## 4. Staged screening
**Stage A, feasibility** (before any outcome). A family proceeds only if:
- data coverage ≥ 95% of the needed symbol-days;
- point-in-time availability is demonstrated;
- the expected development sample is ≥ 300 trades **and** ≥ 150 distinct trading days;
- a cost model exists whose share of measured inputs is stated;
- the execution is possible for a retail paper account (order types, hours, no borrow assumption for long-only).

Otherwise it is stopped as **untestable here**, with the reason.

**Stage B, development:**
- The baseline and ≤ 4 configurations are evaluated.
- The **matched control** is family-specific and stated in its specification: the equal-weight eligible
  universe over the same holding window, random entries with the same timing distribution, or the instrument's
  buy-and-hold over the same hours.
- A configuration is **dev-qualified** only if **all** hold:
  - D1: net mean P&L per trading day > 0, and the 90% day-block bootstrap interval of the **difference from the
    matched control** is above 0;
  - D2: net P&L is positive in at least 2 of the 3 development years (ETF families: in at least 5 of 7);
  - D3: the 10 best days provide less than 50% of total net P&L;
  - D4: net mean > 0 under stress costs (5 bp slippage per side).
- **Selection:** at most one configuration per family is frozen: the dev-qualified one with the highest net
  daily Sharpe. It is **frozen by hash** (code + parameters) before validation is read.
- If none qualifies, the family stops, and validation and final stay unread for it.

**Stage C, validation** (frozen candidate only). **Validated** only if all hold:
- V1: net mean daily P&L > 0 with a 90% day-block bootstrap lower bound > 0;
- V2: the difference from the matched control has a 90% lower bound > 0;
- V3: net mean > 0 under stress costs;
- V4: neither half of the validation window has net P&L below −50% of the other half's gain (no single-regime
  dependence).

**Stage D, final** (validated candidate only). **PASS** requires all of:
- E1: net mean daily P&L > 0 with a 95% day-block bootstrap lower bound > 0;
- E2: beats the matched control (95% one-sided);
- E3: deflated Sharpe probability ≥ 0.95, with N = the cumulative trial count at that time;
- E4: net ≥ 0 in the last 12 months (reported with its interval);
- E5: positive under stress costs.

If the final window was previously inspected market data, the best label is **historically qualified,
prospective evidence required**. A PASS authorises only freezing plus prospective paper trading:
- daily-or-slower strategies: ≥ 6 months;
- intraday: the longer of 3 months and 60 trades.

It never authorises live trading.

## 5. Diagnosis of every failure (mandatory)
Each stopped family reports:
- (a) **Gross signal:** is gross P&L minus control above 0?
- (b) **Costs:** break-even cost per trade against the modelled cost.
- (c) **Timing:** sensitivity to a one-bar entry delay.
- (d) **Concentration:** top-day and top-name shares.
- (e) **Implementation:** an independent recomputation of a sample of trades.
- (f) **Calibration** (models): reliability of predicted versus realised returns.
- (g) **Regime:** results by year and by market-volatility tercile.
- (h) **Sizing and exits:** equal weight versus volatility scaling, and hold-to-horizon versus fixed exits, where
  the family has them.

Post-result discoveries are **exploratory**. They may motivate a separately registered hypothesis within the
budget. They never rescue the failed test, and a losing rule is never simply reversed.

## 6. Machine learning (where a family uses it)
- **Job:** rank or filter opportunities by predicted next-period return, or decide an exit. Never place orders.
- **Training:** walk-forward with expanding windows, refit annually, inside the development window only. The
  frozen model is refit on development data before validation.
- **Features:** point-in-time and cross-sectionally ranked. No ticker identity, no calendar fields.
- **Target:** cross-sectionally demeaned, so market drift cannot be learned.
- **Feature families** (reversal, momentum, volatility, volume/liquidity, market-relative) are evaluated
  separately first. A combined model is kept only if it beats the best single family **and** the simple
  baseline on development folds.
- **Calibration:** reported in deciles.

## 7. Forward evidence
- A frozen candidate's predictions are written to an append-only log **before** the outcome window opens:
  timestamp, inputs digest, signal, intended orders.
- Outcomes are filled in later from fresh data.
- A decision is **blocked** (recorded as `stale_data`) if its input data is older than the family's staleness
  limit or incomplete.
- Live intraday stock decisions on consolidated prices are impossible on the free plan (15-minute SIP delay).
  Such families are forward-tested only at decision times the delayed feed supports, or with IEX real-time
  prices, labelled as such.

## 8. Stopping
- Stop a family early when data quality or execution assumptions make further testing uninformative.
- If no candidate qualifies: deliver the findings and the ranked remaining opportunities. Do not force a winner.
