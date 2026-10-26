# Phase 2: candidate families, selection and specifications

Written 2026-10-26 ~13:00 UTC, **before any phase-2 outcome was computed**, under `PHASE2_PROTOCOL.md`. The
literature evidence (citations, effect sizes, decay, verification tags) is in `LITERATURE.md`. The duplicate
check is `python research/ledger.py dedup …`.

## 1. Screening: 17 families, 6 selected

| # | Family | Evidence (LITERATURE.md) | Decision | Reason |
|---|---|---|---|---|
| 1 | Short-term reversal as liquidity provision, conditioned on market stress | Nagel 2012; Da, Liu & Schaumburg 2014; Medhat & Schmeling 2022 | **Selected: F1** | Clearest economic story (paid for providing liquidity). Measurable state dependence. Free daily data |
| 2 | Earnings-announcement drift (price reaction + headline surprise) | Brandt et al. 2008; Chan, Jegadeesh & Lakonishok 1996; Martineau 2022 (decay) | **Selected: F2** | A genuine out-of-sample question for 2020–2026. Event data free (Alpaca/Benzinga headlines). Low turnover |
| 3 | Market intraday momentum (first half hour → last half hour), SPY/QQQ | Gao, Han, Li & Zhou 2018 | **Selected: F3 (corrected re-test of H7/S1)** | S1 was rejected on hourly Yahoo bars against an assumed 8 bp round trip. SPY's quoted spread is about 0.2 bp per side, so that cost assumption was the binding constraint. A re-test on SIP minute data with measured costs answers a question S1 could not. Overlap disclosed |
| 4 | End-of-day reversal (previous close → 15:00 losers rebound 15:30 → close), large caps | Baltussen, Da & Soebhag 2025; Bogousslavsky 2021 | **Selected: F4** | Recent, large t-statistic, mechanism stated. Untested after 2019. Costs decide it, which is exactly what we can measure |
| 5 | Trend pullback, RSI(2) inside a 200-day uptrend, index ETFs | Connors-style practitioner tests; daily index autocorrelation negative since 2000 | **Selected: F5** | The most common retail day/swing rule. Cheap to test honestly against buy-and-hold. Overlaps H2 (crypto only), disclosed |
| 6 | Machine-learning ranking of next-day returns, liquid stocks | Gu, Kelly & Xiu 2020; daily S&P 500 ML studies; decay after 2010 | **Selected: F6** | The owner asked for ML with a defined job. It ranks the same opportunities as F1 using separate feature families, compared with F1's simple rule |
| 7 | Overnight vs intraday "tug of war" | Lou, Polk & Skouras 2019; Berkman et al. 2012 | Rejected before testing | Same economic content as H8 (gap reversal, rejected). The open/close scope 2016–2026 is already consumed by S2/S2X. Kept as an execution-timing consideration |
| 8 | Intraday periodicity (same half hour, next day) | Heston, Korajczyk & Sadka 2010: about 3 bp per half hour | Rejected before testing | Gross about one round-trip spread even for large caps. The test cannot show net profitability. Kept as a timing input |
| 9 | Failed breakouts / liquidity sweeps of the prior-day high or low ("smart money concepts") | Osler 2003/2005 (FX stop cascades); no equity effect size; Sullivan, Timmermann & White 1999 | **Screen only:** descriptive event study on SPY/QQQ, development window only, no trading rule | No rigorous equity evidence to justify a strategy test. The event study measures whether reversal after a breach exceeds random-time drift. It can motivate a registered test later |
| 10 | Industry momentum / slow diffusion | Moskowitz & Grinblatt 1999; Hou 2007 | Deferred | Monthly or weekly holding, not trading skill at day horizon. No free point-in-time industry map (SEC's ticker map refused this client's anonymous User-Agent) |
| 11 | Pairs trading | Gatev et al. 2006; Do & Faff 2010 | Rejected | Profits decayed to near zero after 2002. Needs shorting with unknown borrow |
| 12 | Time-series momentum on ETFs | Moskowitz, Ooi & Pedersen 2012 | Rejected for this phase | Months-long holding; weak recent single-asset evidence; crypto trend (H1) already rejected |
| 13 | Order-flow imbalance (quotes and trades) | Cont, Kukanov & Stoikov 2014; Boehmer et al. | Rejected (live), deferred (research) | Effect decays in seconds to minutes; a retail account cannot capture it net of spread. The weekly retail-imbalance signal needs trade-condition decoding not yet verified |
| 14 | Crypto weekly momentum / seasonality / funding | Liu, Tsyvinski & Wu 2022 | Prospective only | Every historical Coinbase window is consumed. Funding and basis need derivatives (not authorised) |
| 15 | Closing-auction print deviation | Bogousslavsky & Muravyev 2023 | Rejected | Needs auction-imbalance data (not free). The overnight reversion is captured only by liquidity providers at the auction |
| 16 | Calendar effects (turn of month, pre-holiday) | Widely documented; decayed | Rejected | Low information value; not day-horizon skill |
| 17 | ORB / first-candle continuation | Zarattini 2024 | Already tested | H9, H10 rejected |

## 2. Common rules for the selected families
- **Universes, liquid stocks (F1, F4, F6):**
  - operating companies only (funds, ETFs and trusts excluded by asset-master name);
  - raw close ≥ $5;
  - 20-session mean dollar volume ≥ $20M;
  - ≥ 60 sessions of history;
  - point-in-time, top 1,000 by dollar volume at *t* (F4 and F1-C4: top 500 / top 200).
- **ETFs (F3, F5):**
  - F3: SPY and QQQ (F3-C3 adds IWM and DIA);
  - F5: SPY, QQQ, IWM, DIA and the nine SPDR sector ETFs that existed throughout 2016.
- **Costs:** PHASE2_PROTOCOL §3 tiers.
  - SPY/QQQ/IWM/DIA: 0.5 bp per side, plus 1 bp slippage (base) and 5 bp (stress), plus fees.
  - A **measured-spread sample** (SIP quotes at the actual entry and exit minutes, ≥ 200 trades per family in
    development) is reported next to the tier assumption.
- **Trial accounting:** every configuration listed below (baselines included) is one trial.
  - Six families × at most five configurations, so at most 30 trials.
  - N for E3 = 108 + phase-2 trials evaluated by then.

---

## F1. Liquidity-provision reversal, conditioned on market stress (daily, liquid US stocks)
**Market behaviour.**
- Stocks that fell sharply relative to the market over the last 1–5 sessions, *without* a news-sized volume
  spike, tend to recover part of the move.
- The fall was partly price pressure from investors demanding immediacy, and the rebound pays whoever absorbed
  it.

**Why it might persist.**
- Liquidity provision bears inventory risk, which is highest exactly when the market is stressed and capital is
  scarce (Nagel 2012). The premium is compensation for that risk, not a free lunch.
- Competition from market makers compresses it in calm markets.

**Observable information:**
- the 1-day or 5-day return relative to the market (beta-adjusted);
- volume relative to its 20-day average (high volume flags news, where continuation is more likely);
- market stress: SPY 20-day realised volatility relative to its trailing 252-day median.

**Who provides it:** liquidity demanders (forced sellers, fund flows, retail capitulation) who trade
regardless of price.

**Holding period:** one session, open to open. The signal is computed after the close of *t*, entered at the
open of *t*+1 and exited at the open of *t*+2.

**Data:** SIP daily bars (`all` adjustment for returns, `raw` for filters). SPY for market return, beta and
volatility.

**Execution:** market-on-open orders, 20 names, long only; turnover about 100% per day, so costs are central.

**Invalidated by:**
- no gross advantage over the equal-weight eligible universe;
- gross advantage below the round-trip cost;
- profit only in 2020 (the COVID crash);
- dependence on the 10 best days.

**Simplest benchmark:** the matched control, equal weight across every eligible stock over the same
open-to-open windows (it removes market drift).

| Config | Definition |
|---|---|
| **F1-B0 (baseline)** | 20 lowest 1-day market-adjusted returns (stock return − SPY return, close to close at *t*) among the top-1,000 liquid names |
| F1-C1 | 20 lowest 5-day market-adjusted returns (weekly reversal) |
| F1-C2 | B0, excluding names whose day-*t* volume is > 2× their 20-day mean (no-news reversal) |
| F1-C3 | B0, traded only when SPY 20-day realised volatility > its trailing 252-session median; otherwise cash (Nagel stress state) |
| F1-C4 | B0 restricted to the top 200 by dollar volume (lowest-cost names) |

---

## F2. Earnings-announcement drift: price reaction plus headline surprise (event-driven, liquid US stocks)
**Market behaviour.** After an earnings release, prices move in the direction of the surprise but under-react:
part of the adjustment continues over the following days, because attention is limited and some investors
anchor on prior estimates.

**Why it might persist.**
- Attention constraints and arbitrage limits in mid-caps.
- **Strong decay evidence:** Martineau 2022 finds analyst-based drift gone for large caps since 2006.
- The question is whether a price-reaction signal still carries information in 2020–2026.

**Observable information:**
- the first Benzinga headline of the form "… EPS … Beats/Misses … Estimate" (timestamped);
- the announcement return, the open-to-close return of the first regular session after the headline (EAR);
- volume confirmation.

**Who provides it:** under-reacting investors and those who trade against the move, such as contrarian
retail and stale-estimate holders.

**Holding period:** 5 sessions; C2 uses 20.

**Data:**
- Alpaca news (Benzinga, read-only), SIP daily bars.
- **Stage A must show headline coverage ≥ 70% of the expected quarterly announcements** for the eligible
  universe in each development year. Otherwise the family stops as untestable.

**Execution:** market-on-open entry the session after the reaction session; exit at the open after 5 (or 20)
sessions. Long only.

**Invalidated by:**
- no excess return over the control in development;
- an excess smaller than costs;
- coverage gaps that bias the sample.

**Simplest benchmark:** the equal-weight eligible universe over identical holding windows.

| Config | Definition |
|---|---|
| **F2-B0 (baseline)** | Long every eligible stock whose headline says EPS **Beats** and whose EAR > 0. Equal weight across concurrent positions (max 20; cap 5% each; first by headline time). Hold 5 sessions |
| F2-C1 | B0 but select by EAR alone: EAR in the top quintile of that day's eligible announcers, regardless of the headline |
| F2-C2 | B0, hold 20 sessions |
| F2-C3 | B0 restricted to beats on **both** EPS and sales |
| F2-C4 | B0 restricted to mid-caps (dollar-volume rank 201–1,000), where limited attention should matter most |

---

## F3. Market intraday momentum, corrected re-test (SPY, QQQ; intraday)
**Market behaviour.** The return from the previous close to 10:00 ET (overnight + first half hour) predicts
the return of the last half hour (15:30 → 16:00) in the same direction.

**Why it might persist.**
- Infrequent rebalancers and option-hedging flows execute late in the day, in the direction of the day's move
  (Gao et al. 2018; Baltussen et al. 2021 on gamma hedging).
- The flow is mandated, not discretionary.

**Observable information:** the sign and size of the previous-close → 10:00 return. The 12:00 → 15:30 return is
an alternative predictor.

**Who provides it:** hedgers and rebalancers who must trade near the close.

**Holding period:** 30 minutes, 15:30 → 16:00.

**Data:**
- SIP 1-minute bars, 2016 → 2026-10-23;
- measured cost: SIP quotes at 15:30 and 15:59 on a sample.

**Execution:**
- Enter at the 15:30 bar's open. Exit at the 15:59 bar's close, which marks the closing quote (not the
  auction print).
- Live use needs a decision at 15:30. The consolidated feed is 15 minutes delayed, so forward tests use IEX
  prices for SPY/QQQ. That is reasonable for these two ETFs, and labelled.

**Invalidated by:**
- a gross effect below about 2 bp per trade;
- dependence on 2020;
- the sign flipping across years.

**Simplest benchmark:** being long every day 15:30 → 16:00 (drift control), plus random-sign entries.

**Overlap:** H7/S1 (Yahoo hourly; test 2025-08-26 → 2026-10-23, assumed 8 bp). The ETF minute data for
2016–2026 was inspected by S1/S2/S2X for other rules. **The final window is labelled "previously inspected
market data".**

| Config | Definition |
|---|---|
| **F3-B0 (baseline)** | SPY: sign of previous close → 10:00 return; trade 15:30 → close in that direction (long or short; short ETF borrow is routine, still labelled) |
| F3-C1 | B0, but only when \|previous close → 10:00\| exceeds its trailing 60-day median absolute value |
| F3-C2 | Predictor = previous close → 10:00 **plus** 12:00 → 15:30 return sign agreement (both must agree) |
| F3-C3 | B0 on SPY, QQQ, IWM and DIA, equal weight |
| F3-C4 | B0 **long only**, traded only when the predictor is positive |

---

## F4. End-of-day reversal (liquid US stocks, intraday)
**Market behaviour.** Stocks that fell most from the previous close to 15:00 rebound between 15:30 and the
close.

**Why it might persist.** Attention-driven buying of the day's losers and short-covering into the close (both
stated by Baltussen, Da & Soebhag 2025) create predictable late price pressure. The edge is about one spread
for large caps, so only cheap execution can capture it.

**Observable information:** the previous close → 15:00 return, ranked across the eligible universe.

**Who provides it:** short-sellers covering and retail dip-buyers who trade near the close.

**Holding period:** 30 minutes, 15:30 → close.

**Data:**
- SIP 30-minute bars for the point-in-time top-500 liquid names, 2020 → 2026-10-23;
- measured spreads at 15:30 and 15:59 on a sample.

**Execution:**
- Limit or marketable orders at 15:30; exit at the 15:59 quote (MOC deviation is avoided by design).
- Live needs a real-time cross-section at 15:30, which the free plan has only on IEX (labelled).

**Invalidated by:**
- a gross excess below the round-trip cost in large caps;
- a sign flip after 2019.

**Simplest benchmark:** equal-weight eligible universe 15:30 → close.

| Config | Definition |
|---|---|
| **F4-B0 (baseline)** | Long the 20 lowest previous-close → 15:00 returns in the top-500 universe, 15:30 → close |
| F4-C1 | Top-200 universe only (lowest cost) |
| F4-C2 | B0 using market-adjusted returns (stock − SPY over the same span) |
| F4-C3 | B0, excluding names with day volume to 15:00 > 2× normal (news days) |
| F4-C4 | Long-short (20 losers long, 20 winners short), labelled upper bound because borrow is not modelled; not freezable |

---

## F5. Trend pullback, RSI(2) in an uptrend (index and sector ETFs, daily swing)
**Market behaviour.** In an established uptrend, a sharp 1–3-day dip is bought back by trend-following and
dip-buying flows.

**Why it might persist.** Retail and systematic dip-buying, and volatility-control funds re-leveraging after
volatility falls. **Evidence is weak:** practitioner tests show decay since 2008, and the rule trails
buy-and-hold since 2009.

**Observable information:**
- 2-period RSI (Wilder) on daily closes;
- close above its 200-day simple moving average.

**Who provides it:** short-term sellers in a long-term uptrend (stop-outs, de-risking).

**Holding period:** 1–10 sessions.

**Data:** SIP daily bars plus 1-minute bars at 15:45 for SPY/QQQ/IWM/DIA. Sector ETFs use the daily close
(assumption, labelled).

**Execution:**
- The decision uses the 15:45 price (RSI computed with that price as today's close); market-on-close entry;
  exit on close when the exit condition holds.
- Long only, at most 1/n of equity per ETF.

**Invalidated by:** failing to beat **buy-and-hold at matched exposure** (time in market × benchmark return),
not merely being positive.

**Simplest benchmark:** buy-and-hold of the same ETF, scaled to the rule's average exposure; plus random
entries with the same holding-time distribution.

**Overlap:** H2 (crypto RSI2, rejected). ETFs 2016–2026 inspected by S2X for other rules: **"previously
inspected market data"**.

| Config | Definition |
|---|---|
| **F5-B0 (baseline)** | SPY, QQQ, IWM, DIA: buy when RSI2 < 10 and close > SMA200; sell when close > the previous day's high or after 10 sessions |
| F5-C1 | Exit when RSI2 > 70 instead |
| F5-C2 | Entry threshold RSI2 < 5 |
| F5-C3 | B0 on the nine sector SPDRs (XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY) |
| F5-C4 | B0 without the trend filter (tests whether the filter adds anything) |

ETF development window: 2016-01-04 → 2022-12-30 (protocol §2). D2 requires at least 5 of 7 years positive.

---

## F6. Machine-learning ranking of next-day returns (daily, liquid US stocks)
**Job:** rank F1's opportunity set (the top-1,000 liquid names, open-to-open next day) better than F1's
one-feature rule. No order is placed by a model; the deterministic risk engine stays in control.

**Why it might work:** non-linear interactions between short-horizon reversal, volume, volatility and trend,
for example "reversal only without volume", which a single sort cannot express.

**Features** (point-in-time, cross-sectionally ranked each day; no ticker or calendar fields), in families:
- reversal: 1-day, 5-day, overnight gap, intraday (close/open) at *t*;
- momentum: 20-day, 60-day, 120-day returns, distance to 52-week high;
- volatility: 20-day realised volatility, high-low range;
- liquidity: volume ratio, dollar-volume rank;
- market-relative: beta-adjusted 1-day and 5-day returns, 60-day beta.

**Target:** next open-to-open return, cross-sectionally demeaned and rank-transformed.

**Training:**
- walk-forward with expanding windows from 2016, refit each January;
- predictions for 2020, 2021 and 2022 use models trained only on earlier years;
- 2016–2019 is survivorship-affected and used **for training only** (protocol §2).

**Portfolio:** long the 20 highest-predicted names, open to open, same costs as F1.

**Invalidated by:**
- not beating F1-B0 (paired, development);
- calibration with no monotone decile spread;
- importance concentrated in features that proxy calendar or market drift.

**Benchmarks:** F1-B0 (simple rule) and the equal-weight control.

| Config | Definition |
|---|---|
| **F6-B0 (baseline)** | Ridge regression on the reversal family only (a linear version of F1) |
| F6-C1 | Ridge on all feature families |
| F6-C2 | Gradient-boosted trees (sklearn HistGradientBoosting, fixed hyperparameters: depth 3, 200 iterations, learning rate 0.05, min leaf 200) on all families |
| F6-C3 | The same trees on the single best family. Chosen by mean rank correlation in the walk-forward folds of 2017–2019 (training years only), before development returns are read |
| F6-C4 | C2 with a no-trade filter: hold only names whose predicted demeaned return exceeds the modelled round-trip cost; otherwise cash |

Feature-family diagnostics (per-family rank correlation and decile spreads) are reported for all five
families. They are diagnostics, not extra trials.

---

## Round 2 (owner, 2026-10-26 ~14:00 UTC: "do a better job"; treated as approval to continue past the 6-family limit)
The phase-1 criteria (D1–D4, V1–V4, E1–E5), chronology and Amendment 1 cost rules are unchanged. Every new
configuration is a counted trial.

## F7. Machine-learning ranking executed at the close (liquid US stocks)
**Motivation (post-result, disclosed).**
- F6 found a small but consistent ranking signal (daily rank correlation 0.010–0.027 every development year).
- That signal was 5–10× too small for open-to-open execution, which pays the measured 09:31 spread (5–26 bp).
- The measured 15:59 spread is 1.4–2.5 bp.
- F7 tests whether the **same model family** survives when traded at the cheapest point of the day.
- This is a new registered hypothesis about execution timing. It does not rescue F6: F6's results stay
  rejected, and F7 reads only data that F6 did not use for its decision.
  - The development window is the same 2020–22, already seen by F6 for open-to-open returns.
  - **Disclosed:** F7's development read is therefore not independent of F6.
  - Only F7's validation (2023-01 → 2024-06) and final windows count as unseen evidence.

**Rule.**
- **Universe:** the F4 universe, the point-in-time top 500 by dollar volume as of *t*−1. Its 14:30–16:00 bars
  are cached.
- **Decision at 15:30 ET** on session *t*:
  - features are F6's families computed from daily bars through *t*−1, plus *p* = the 15:30 price of *t*
    (open of the 15:30 bar), all known at 15:30:
    - r1 = *p* / close(*t*−1) − 1; r5 = *p* / close(*t*−5) − 1;
    - gap = open(*t*) / close(*t*−1) − 1; intraday = *p* / open(*t*) − 1;
    - r20, r60, r120 = *p* / close(*t*−k) − 1; dist52 = *p* / max close over the prior 252 sessions − 1;
    - vol20 and range from daily bars through *t*−1;
    - vol_ratio and log_dvol from daily volume through *t*−1;
    - r1_mkt, r5_mkt and beta60 use SPY's 15:30 price the same way.
  - Every feature uses only data available at 15:30. No other changes.
- **Execution:**
  - buy at the close of *t* (15:59 closing-quote proxy = close of the 15:30 bar) and sell at the close of
    *t*+1;
  - costs: Amendment 1 measured band-median half-spreads at 15:59 on both sides.
- **Label for training:** close *t* → close *t*+1 return, cross-sectionally demeaned and ranked.
- **Training:** walk-forward as in F6, annual refits.
  - The intraday 15:30 price exists only from 2019-12, where F4's windows begin.
  - So training on 2016–2019 uses the *t* close as a stand-in for the 15:30 price (labelled). Development
    predictions for 2020–22 use the true 15:30 price.
- **Control:** equal weight across the eligible universe, close *t* → close *t*+1, same costs.

| Config | Definition |
|---|---|
| **F7-B0 (baseline)** | Ridge on the reversal family (1-day return to 15:30, 5-day, gap, intraday to 15:30) |
| F7-C1 | Gradient-boosted trees on all families (F6-C2 hyperparameters) |
| F7-C2 | C1 with the cost filter: hold only names whose calibrated expected demeaned return exceeds their own measured 15:59 round trip |
| F7-C3 | C1, top 10 instead of top 20 (higher conviction, same total exposure) |
| F7-C4 | C1 held 2 sessions (half the book rebalanced each day) |
