# Research program: what the literature supports, and the next three experiments

Written 2026-10-26. **Nothing here has been run. No result is claimed.** Every fact below comes from a primary
source I read on this date or on 2026-10-25, cited by URL. Where only an abstract or a working-paper version
was available, the entry says so. Nothing is filled in from memory. Fees are in docs/FEES_VERIFIED.md. The
trial budget and its stopping rules are in RESEARCH_BUDGET.md, and this program stays inside them.

## 0. What could not be read

| Item | What happened | What was used instead |
|---|---|---|
| Gao, Han, Li & Zhou, published JFE 129(2):394–414 (2018) | Publisher PDF not found | Authors' working paper, "Current Version: December, 2015", from a forum mirror (c.mql5.com). Numbers may differ from the published version |
| Cont, Kukanov & Stoikov, J. Financial Econometrics 12(1):47–88 (2014) | Full text not read | arXiv abstract only, https://arxiv.org/abs/1011.6402 |
| Shen, Urquhart & Wang, Financial Review 57(2):319–344 (2022) | Accepted-version host (University of Reading) refused by the egress proxy | Abstract excerpts from https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/ |
| Chague, De-Losso & Giovannetti (Brazil day traders) | USP PDF: connection reset. FGV repository: blocked | RePEc abstract, https://ideas.repec.org/p/spa/wpaper/2019wpecon47.html |
| Chinco, Clark-Joseph & Ye, JF 74(1):449–492 (2019) | Publisher version not read | NBER WP 23933 full text |
| Zarattini & Aziz, SSRN 4416622 (QQQ ORB) | SSRN 403 | Not used. ORB rules come from the 2024 Stocks-in-Play paper (ORB_PREREGISTRATION.md) |
| Bailey et al., PBO paper | Read in full, but the text does not name its journal | Cited as the Feb-2015 revision PDF |
| Crypto candidates not read: "Quarter-Hour Effect" (arXiv 2607.09426, a 2026 preprint); Guo et al. on cross-crypto predictability; Aleti, Bollerslev & Siggaard (Management Science 2025, equities) | Seen only in search snippets | **Not cited as evidence** |
| Coinbase fee pages | HTTP 403 | See docs/FEES_VERIFIED.md |

## 1. Gu, Kelly & Xiu, "Empirical Asset Pricing via Machine Learning", RFS 33(5):2223–2274 (2020)

Read in full: https://dachxiu.chicagobooth.edu/download/ML.pdf

- **Data:** about 30,000 US stocks, 1957–2016. Predictors: 94 firm characteristics interacted with 8 macro
  variables, plus 74 industry dummies (over 900 signals). Characteristics are lagged by at least 1, 4 or 6
  months, depending on reporting delay.
- **Horizon:** monthly (annual results are also shown).
- **Out-of-sample design:** training 1957–1974, validation 1975–1986, test 1987–2016. Models are refit every
  year, with an expanding training window and a rolling 12-year validation window. This is a genuine
  out-of-sample test.
- **Monthly OOS R²:** elastic net 0.11%, PCR 0.26%, PLS 0.27%, trees and neural networks 0.33–0.40% (NN3
  peaks at 0.40%).
- **Portfolios:** the NN4 value-weighted long-short decile portfolio has a Sharpe ratio of 1.35 (2.45
  equal-weighted), against 0.51 for the S&P 500.
- **Dominant predictors:** price trend (momentum, industry momentum, short-term reversal), then liquidity, then
  volatility.
- **Costs:** none are deducted. The paper reports turnover of about 110–130% per month and says value-weighted
  portfolios "are less sensitive to trading cost considerations".
- **What carries over to us:** the gains come from a broad cross-section at a monthly horizon, and from features
  built mostly from **price and volume**. Nonlinear models beat linear ones modestly in absolute R² (0.40 vs 0.11).
  The paper itself is **not attainable** for stocks with our data. It needs point-in-time fundamentals and a
  survivorship-free universe, and Yahoo daily data provides neither. The feature families can be computed from
  candles alone, so a crypto cross-section is the only attainable analogue. **That transfer is our hypothesis,
  not the paper's finding.**

## 2. Probability of Backtest Overfitting (Bailey, Borwein, López de Prado & Zhu)

Read in full: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf (Feb-2015 revision; the journal is not
named in the text).

### CSCV exactly as the paper defines it
1. Build **M**, a T×N matrix: T periods of returns (same dates for every column), one column for each of the N
   trial configurations.
2. Split the rows into **S** contiguous, equal-sized blocks. S must be even.
3. For each of the C(S, S/2) ways to choose S/2 blocks:
   - The chosen blocks form the training set J. The remaining blocks form the test set J̄.
   - Compute each column's performance statistic (Sharpe) on J and pick the best column, n\*.
   - Find n\*'s relative rank ω̄ among the N columns on J̄, scaled to (0, 1).
   - Compute the logit λ = ln(ω̄ / (1 − ω̄)).
4. **PBO = φ = the fraction of combinations with λ ≤ 0.** That is the fraction where the in-sample winner falls at
   or below the median out of sample.
5. The paper also reports:
   - performance degradation: a regression of OOS performance on IS performance across combinations;
   - probability of loss: the share of combinations where n\* loses out of sample;
   - stochastic dominance of the selected strategy over the median.

### Parameters and limits the paper states
- S = 16 is "a reasonable value to use in most cases". With 4 years of daily data it gives quarterly blocks
  and keeps serial correlation intact.
- The paper prints "12, 780" combinations for S = 16. That is a misprint: C(16, 8) = 12,870.
- N must be large enough that ω̄ takes many values. With a small N, the ranks are coarse.
- "A customary approach would be to reject models for which PBO is estimated to be greater than 0.05."
- Limitations the paper names: serial dependence, the file-drawer problem, guided searches that use final
  outcomes, structural breaks. CSCV checks only the selection process. It does not check costs or look-ahead.

### How to apply it to our trial matrix
- **One PBO per hypothesis family.** Never pool unrelated strategies, because their columns cover different
  dates, and CSCV requires a common T. For each family, build M from the **daily net P&L** of every configuration
  actually tried in development, over identical sessions. Use zero on days a configuration is flat, not a
  missing value.
- With ≤ 6 registered configurations per hypothesis (RESEARCH_BUDGET.md), ω̄ takes only 6 values. **Widen N
  honestly:** add every hyperparameter grid point the fitting procedure evaluated as its own column. Report N.
- Use S = 16 by default. Use S = 24 if the development window exceeds about 6 years.
- **Decision use:** PBO > 0.05 vetoes freezing a configuration even if E1–E7 pass. PBO ≤ 0.05 is necessary but
  not sufficient. Report degradation and probability of loss alongside it.
- An implementation is not in the repo yet. It belongs in `tradelab/research/` with a unit test checking that
  the combination count is 12,870 for S = 16, and that M with one dominant column gives PBO ≈ 0.

## 3. Zarattini, Barbon & Aziz (2024), ORB on Stocks in Play

Summarised from ORB_PREREGISTRATION.md, which records the full-text read.
- **Data and rules:** all NYSE/Nasdaq stocks, 2016–2023, survivorship-free. Trade the top 20 by relative opening
  volume, breaking out in the direction of the first 5-minute candle. Stop at 10% of ATR; exit at the close.
- **Reported results:** Sharpe 2.81 with the relative-volume filter, net of $0.0035/share commission **only**.
  The paper never mentions spreads, slippage, borrow or partial fills.
- **No out-of-sample test.** The average trade is +0.08R, about 2–5 bp of price, which is below our assumed
  20 bp round trip.
- It is already pre-registered, with power for a clear verdict. It is blocked until Alpaca SIP access is verified.

## 4. Intraday papers

| | Information used | Why it could predict | Market / timeframe / period | Genuinely OOS? | Costs included? | Attainable for us? |
|---|---|---|---|---|---|---|
| **Chinco, Clark-Joseph & Ye (JF 2019)**: NBER w23933, https://www.nber.org/system/files/working_papers/w23933/w23933.pdf | 3 lagged 1-minute returns of ~2,000 NYSE stocks, selected by LASSO | Sparse, short-lived cross-stock signals tied to news about fundamentals | NYSE; 1-minute-ahead forecasts; 30-minute rolling estimation; 250 random stocks a day; 2005–2012; stocks < $5 excluded | **Yes**: rolling, strictly prior data | **Spread only.** Trades only when the forecast exceeds the prior day's average spread. Sharpe 1.79 vs S&P 0.12. The AR(3) benchmark strategy loses after the spread. No fees, impact or latency | **No.** Needs consolidated 1-minute data for the whole cross-section and minute-level execution |
| **Heston, Korajczyk & Sadka (JF 2010)**: https://www.bauer.uh.edu/departments/finance/documents/Heston_Korajczyk_Sadka_paper_UH.pdf (May-2010 version) | A stock's return in the same half-hour on previous days | Periodic institutional trading and fund flows. Volume, order imbalance and spreads show the same periodicity but do not explain it | NYSE; 1,715 firms; 13 half-hours per day; 2001–2005 (TAQ) | **No**: full-sample cross-sectional regressions | **No.** The top-minus-bottom decile earns **3.01 bp** at the same half-hour the next day. The authors compare this to execution costs (the effective spread) and frame it as trade **timing** that can save about one effective spread | Only as an execution-timing input. Needs SIP half-hour bars; too small to trade alone |
| **Gao, Han, Li & Zhou (JFE 2018)**: Dec-2015 working paper, https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf | SPY first half-hour return (and the 12th half-hour) predicting the last half-hour | Informed trading clustered at the high-volume open and close; late-informed traders | SPY, 1993–2013, plus 10 ETFs | **Partly**: recursive OOS from 1998. OOS R² 1.2% (1.8% with the 12th half-hour) | **Yes, spread only.** Uses 15:30 bid/ask; the 16:00 exit is at the closing price. After 2005: 6.52%/yr net vs 7.96% gross; spread ≈ 1.2 bp. Derived: **≈ 2.6 bp per trading day net, ≈ 3.2 bp gross** | Testable on minute bars. Our S1 (a close variant) measured **+2.0 bp gross (−2.3, 6.1)**, consistent with the paper and **below our 8 bp round trip**. Closed |
| **Baltussen, Da, Lammers & Martens (JFE 2021)**, "Hedging demand and market intraday momentum": published PDF https://www3.nd.edu/~zda/intramom.pdf | Return from the previous close to 30 minutes before the close, predicting the last 30 minutes | Gamma hedging by options market makers and leveraged ETFs, which trade in the direction of the move | 60+ futures (equity, bond, commodity, currency), 1974–2020 | **Partly**: expanding-window OOS R² up to **2.88%** in the paper's Table 2 Panel A specification | **No.** "We do not consider transaction costs." The authors state that S&P 500 futures stay positive at a one-tick cost (asserted in the text; the table was not read) | Futures are not in scope (no account). The ETF version is S1's family, which is closed |
| **Cont, Kukanov & Stoikov (JFEc 2014)**: abstract only, https://arxiv.org/abs/1011.6402 | Order-flow imbalance at the best bid and ask | Price changes are linear in OFI, with slope ∝ 1/depth | NYSE TAQ, 50 stocks | Not applicable: the relation is **contemporaneous**. The abstract makes no predictive claim | Not applicable | For **cost and impact modelling**, not signals. Crypto L1 quotes can be recorded **forward** from Coinbase WebSocket for free; there is no history |
| **Akyildirim, Goncu & Sensoy (Ann. Oper. Res. 297:3–36, 2021)**: https://repository.bilkent.edu.tr/bitstream/11693/77044/1/Prediction_of_cryptocurrency_returns_using_machine_learning.pdf | 40 features from past prices and technical indicators; SVM, logistic, ANN, random forest classifiers | Weak-form inefficiency in crypto | 12 coins on Bitfinex; 15/30/60-minute and daily bars; intraday sample 10 Aug 2017 – 23 Jun 2018 | **Weak**: a single 80/20 (or 90/10) chronological holdout, not walk-forward. Random forest's OOS accuracy is "drastically lower" than in-sample | **No.** "Trading strategies are not considered in detail." Accuracy only: **55–65%** | Data attainable (Coinbase 5m/1m). The paper says nothing about tradability, and accuracy alone does not imply that a move exceeds cost |
| **Shen, Urquhart & Wang (Fin. Review 2022)**: abstract only | First half-hour of a volume-defined session predicting the last half-hour | Liquidity provision (by analogy with FX) | Bitcoin | Unknown (abstract only) | Unknown | Our C2 (00–06 UTC momentum) belongs to this family and was rejected at retail fees: +35 bp gross vs 132 bp cost |

### Why these are worth testing, compared with a simpler alternative
- **Gao and Baltussen:** already answered for us by S1. The effect is real and about 2–3 bp, which is not enough at
  retail stock costs. The simpler alternative, not trading, wins.
- **Heston et al.:** too small to trade. Use it to time entries and exits of a strategy that has an edge.
- **Chinco et al.:** the most rigorous intraday ML evidence, and its cost gate (trade only when the forecast
  exceeds the spread) is the design rule worth copying. The data and execution are out of reach.
- **Akyildirim et al.:** the only crypto ML study read in full. Its value is a warning: in-sample fit is far above
  out-of-sample, and accuracy without a cost model proves nothing about tradability.

## 5. Synthesis by horizon

| Horizon | Best evidence | Gross effect per trade | Against our costs |
|---|---|---|---|
| **Monthly cross-section** | GKX: genuine OOS, decades of data | Large in Sharpe terms; R² ≈ 0.4% a month | The ML evidence is strongest here, but stock fundamentals are unattainable. Turnover of 110–130% a month is untested against costs |
| **Daily / half-hour, market level** | Gao, Baltussen: partly OOS | ≈ 2–3 bp (SPY) | Below the 8 bp stock round trip. S1 confirmed this |
| **Half-hour, cross-section** | Heston et al.: in-sample | ≈ 3 bp | Execution timing only |
| **1-minute cross-section** | Chinco et al.: OOS, spread-gated | Positive after spread | Unattainable data and latency |
| **Crypto intraday** | Akyildirim et al.: weak OOS, no costs | Unknown | Our C1/C2 lost to a 1.32% round trip |

**Conclusion.** Every credible intraday effect read here is a few basis points. Our verified and assumed
round-trip costs are 8–20 bp for stocks and about 132 bp for crypto at the assumed Coinbase taker fee.
- The literature does **not** support an intraday edge for an account with these costs.
- The ML evidence that is genuinely out of sample is at a **monthly** horizon, with price-trend, liquidity and
  volatility features.
- The one attainable direction with a plausible gross effect above cost is therefore **low-turnover,
  multi-day, cross-sectional crypto**, plus the already pre-registered ORB test.

## 6. The bounded program: at most three experiments

These are the three slots RESEARCH_BUDGET.md allows: at most 6 development configurations each, 8 weeks, $0.
Each experiment needs a dated pre-registration file before its data is viewed. Pass or fail uses the repo's
E1–E7 standard on untouched data, **plus** PBO ≤ 0.05 (Section 2). Benchmarks: zero, the equal-weight universe,
and the fixed-allocation / buy-and-hold paper benchmarks.

### Stocks track: blocked until Alpaca SIP access is verified

**X1. ORB on Stocks in Play.** Exactly as in ORB_PREREGISTRATION.md.
- **Hypothesis:** opening imbalances on high relative-volume days persist into the close.
- **Data:** SIP 1-minute bars and NBBO quotes. The opening spreads it measures replace the 10 bp assumption.
- **Model progression:**
  - Baseline: the paper's rule.
  - The 6 trial slots are already allocated to rule variants (RV threshold, top-N, long/short).
  - A logistic or GBT trade filter (features: RV, gap, opening-range/ATR, measured spread) would need **either**
    a dated amendment that swaps out dev-only variants before dev data is seen, **or** your approval of extra
    trials. **Recommendation: replicate the rule first.** Add a model only if the gross effect is positive but
    under cost. That would be a follow-up, counted against the budget.
- **Evaluation:**
  - development 2016–2019 (replication);
  - untouched test 2024-01-02 → 2026-07-24;
  - PBO over the dev configurations.
- **Unblocking step:** the paper-key SIP check in docs/CREDENTIALS_SETUP.md. Note: that guide names
  `TRADELAB_PAPER_APCA_KEY_ID` / `_SECRET_KEY`, but `tradelab/pit/alpaca_sip.py` reads
  `TRADELAB_PAPER_APCA_API_KEY_ID` / `_API_SECRET_KEY`. Reconcile them before the user creates the secrets.
  That is a code or doc fix, outside this file.

### Crypto track: unblocked now (free Coinbase candles; point-in-time universe from scripts/pit_build_universe.py)

**X2. Weekly cross-sectional crypto ranking (GKX feature families transplanted).**
- **Hypothesis:** among Coinbase USD spot products eligible as of each date, these features predict next-week
  relative returns:
  - price trend (1–4 week return);
  - short-term reversal (1-day return);
  - liquidity (dollar volume; Amihud from candles);
  - volatility.
- **Portfolio:** long-only top-k against the equal-weight eligible universe. No shorting, no leverage.
- **Horizon:** 7 days, rebalanced weekly, with a no-trade band to cap turnover.
- **Data:** daily and hourly candles 2021→ for every product ever eligible, including delisted ones (the
  point-in-time dataset already being built).
- **Feasibility gate, run before any model and costing no trials:** in the development window, the median
  weekly cross-sectional inter-quartile return range must exceed **2 × the round-trip cost** (2 × 1.32% at the
  assumed fee). Otherwise X2 stops without modelling. This checks dispersion only, not any signal.
- **Model progression, 6 configurations:**
  - B1, single-feature rank (4-week momentum): the simple alternative to beat;
  - M1a, ridge on rank-normalised features;
  - M1b, logistic (top tercile vs rest);
  - M2a and M2b, gradient-boosted trees at two depths;
  - E, an average of M1a and M2a.
  - Hyperparameters are tuned only inside each training window (GKX-style validation). Every grid point
    becomes a PBO column.
- **Evaluation:**
  - expanding-window walk-forward, refit monthly;
  - 7-day embargo between training labels and test;
  - untouched final 12 months, opened once.
  - Primary metric: weekly net excess return over the equal-weight universe at 1.32% round trip on the turnover
    actually traded (stress: 1.92%), with a block-bootstrap CI.
  - Also report OOS R², turnover and PBO.
- **Pass:** E1–E7 net, PBO ≤ 0.05, **and** beating B1 net. Matching the single momentum rank does not justify a
  model.

**X3. Cost-gated intraday cross-coin lead-lag (Chinco design, transplanted). Conditional: run only if a
verified venue cost is ≤ ~0.6% round trip all-in.**
- **Why conditional:** at 1.32% a 1-hour forecast almost never clears cost, and C1/C2 already showed this.
  docs/FEES_VERIFIED.md shows **Alpaca Crypto's verified lowest tier at 0.15% maker / 0.25% taker**, against
  0.40/0.60 assumed for Coinbase and a verified 0.40/0.80 at Kraken. That is the "cost structure the account
  doesn't have today" which RESEARCH_BUDGET.md allows as a reason to change direction. Alpaca crypto **spreads
  and depth are unmeasured**. Measure them from quotes for 2 weeks before deciding; this costs no trials.
- **Hypothesis:** lagged 5-minute returns of other coins (BTC/ETH leading alts) predict the next-hour return.
  Trade only when |forecast| > round-trip cost.
- **Data:** Coinbase 5-minute candles 2020→, used as the signal source for the cross-coin test.
- **Model progression, ≤ 6 configurations:**
  - B0, own AR(3) (Chinco's benchmark);
  - M1, LASSO on all coins' lags (rolling window);
  - M1b, logistic-LASSO;
  - M2, GBT;
  - two cost-gate thresholds (1.0× and 1.5× round trip).
- **Evaluation:**
  - rolling walk-forward; untouched final 6 months; PBO.
  - Report how often the gate opens. If it opens fewer than 100 times in the test period, the result is
    "predictable but not tradable" and X3 closes (E7).
- **Expectation, stated now:** rejection is the most likely outcome. Akyildirim et al.'s 55–65% accuracy says
  nothing about move size.

If the Alpaca crypto cost condition fails, the X3 slot stays **unspent**. It is not used for another
parameter search.

### Order and stopping
1. X2 now, starting with the feasibility gate.
2. In parallel: verify the Coinbase fee tier (docs/FEES_VERIFIED.md, Option A) and Alpaca SIP access. Both are
   free and need user action.
3. X1 once SIP is verified.
4. X3 only if its cost condition holds.

If all budgeted slots end without a pass, RESEARCH_BUDGET.md's rule applies: stop the search, keep the
benchmarks, and say so plainly.

## 7. Benchmarks for "better than human day traders"

| Study | Read | Finding |
|---|---|---|
| Barber, Lee, Liu, Odean & Zhang, "Learning, Fast or Slow" (Oct-2017 version): https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf | Full text | Complete Taiwan Stock Exchange data, 1992–2006. Day traders' aggregate performance net of fees was **negative in every one of the 15 years**. More than 75% quit within two years. Fewer than 1% are predictably profitable (citing Barber, Lee, Liu & Odean 2010) |
| Chague, De-Losso & Giovannetti, USP WP 2019_47: https://ideas.repec.org/p/spa/wpaper/2019wpecon47.html | Abstract only | Individuals who began day trading Brazilian equity futures in 2013–2015 and persisted for 300 or more days: **97% lost money**. Only 0.4% earned more than a bank teller's starting salary (US$54 a day). The top individual earned US$310 a day (SD US$2,560). No evidence of learning. Other figures seen secondhand (sample size; a 2020 revision) are **unverified** and not used |

**What this means for any claim:**
- Doing better than the typical human day trader is a very low bar. **Not trading beats 97%** of the persistent
  Brazilian day traders.
- So "better than human day traders" is **not** an acceptable success criterion. The bar is:
  - a positive net return whose one-sided lower bound is above zero;
  - higher than the passive benchmarks (fixed allocation, buy-and-hold) after **verified** costs;
  - on untouched data, followed by 3 months of forward paper trading.
- No statement of superiority over human traders will be made from a backtest alone.
