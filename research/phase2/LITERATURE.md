# Phase 2 literature review: short-horizon equity, ETF and crypto strategy families

Compiled 2026-10-26. This is a reading list for choosing up to six families to test. No experiments were run.

## How to read this file

Each claim carries a verification tag:

- **[V]**: read in the primary text (published PDF or the author's working paper). Page-level numbers were checked.
- **[A]**: taken from the paper's abstract or a publisher/repository record. The full text was not read.
- **[S]**: taken from a secondary summary (CXO Advisory, Alpha Architect, Quantpedia, a replication thesis or a blog). Treat it as a lead, not a fact.
- **[U]**: not verified. Either it comes from my prior knowledge or no accessible source confirmed it. Check it before relying on it.

"bp" means basis points. "L/S" means long-short. "EW" and "VW" mean equal-weighted and value-weighted. All effects are **gross of costs** unless the text says otherwise.

**Cross-cutting decay evidence.** The two results below apply to every family:

- McLean & Pontiff (2016), *Journal of Finance* 71(1). Across 97 predictors, returns are 26% lower out of sample and 58% lower after publication [A]. https://doi.org/10.1111/jofi.12365 (working-paper PDF: https://ivey.uwo.ca/media/3775549/pontiff.pdf)
- Chen & Velikov (2023), *JFQA* 58(3), 968–1004. Across 204 anomalies, after effective-spread costs, post-publication decay and the post-2005 trading-technology era, the average anomaly nets about **4 bp/month**. The best anomalies net at most about 10 bp, and combinations about 20 bp [A/S]. The paper uses effective spreads, so its cost estimate is a lower bound for anyone paying the spread. https://www.federalreserve.gov/econres/feds/zeroing-in-on-the-expected-returns-of-anomalies.htm

**Data constraints applied in the "Data needed" lines:** Alpaca SIP history (bars, NBBO, trades) starts in 2016; real-time data is IEX-only and consolidated data is 15 minutes delayed; corporate actions start in 2020; there is no options, futures or paid fundamentals/IBES data. Verified free point-in-time sources are in Section 4 and the Appendix.

---

## 1. Short-term cross-sectional reversal as liquidity provision, conditioned on VIX

**Definition.**

- Nagel (2012), *RFS* 25(7), 2005–2039 [V]:
  - Daily strategy: the average of five sub-strategies.
  - Sub-strategy k weights each stock in proportion to minus its market-adjusted return on day t−k (k = 1…5): `w_it ∝ −(R_i,t−k − R_m,t−k)`.
  - Weights are scaled to $1 long and $1 short. The book is rebalanced daily at the close and held for one day.
  - Universe: CRSP share codes 10/11 on NYSE/AMEX/Nasdaq. Sample January 1998 to December 2010.
  - Returns are computed both from closing transaction prices and from closing bid/ask midpoints (Nasdaq only).
- Avramov, Chordia & Goyal (2006), *JF* 61(5), 2365–2394 [A/V]: weekly and monthly reversal, conditioned on Amihud illiquidity and turnover.
- Da, Liu & Schaumburg (2014), *Management Science* 60(3), 658–674 [A]:
  - Decompose reversal into four parts: across-industry momentum, within-industry differences in expected return, under-reaction to within-industry cash-flow news (analyst revisions), and a residual.
  - Their "enhanced" reversal, built on the residual, has a risk-adjusted return about four times the standard one.
- Hameed & Mian (2015), *JFQA* 50(1–2), 89–117 [V]:
  - Monthly within-industry reversal: buy last month's industry-adjusted losers, sell winners, hold one month. Sample 1968–2010.

**Reported effect and sample.**

- Nagel, Table 1 [V]:
  - Individual-stock reversal: **0.30%/day** with transaction prices; **0.18%/day** with quote midpoints (annualised Sharpe 8.4 and 4.5).
  - Industry-portfolio reversal: 0.02%/day, Sharpe 0.56.
  - Returns were near 1%/day in late 1998, 2000–01 and 2008. They fell to under 0.2%/day before 2007.
- Nagel on large caps [V]: among large, liquid, low-volatility stocks, reversal profits are "very close to zero when VIX is low" and about **0.1%/day** when VIX is high, for both transaction-price and midquote returns.
- Hameed & Mian [V]:
  - Within-industry monthly reversal: 0.97%/month risk-adjusted, against 0.63% for the plain reversal.
  - After skipping one day, the within-industry version still earns 0.57%/month. The plain reversal drops to 0.27%, which is insignificant.
- Blitz et al. "short-term residual reversal" (2013, *JFM*) [S]: reported profitable net of costs among post-1990 large caps.
- de Groot, Huij & Zhou (2012, *JBF*) [S]: about 30–50 bp/week net of costs in large caps, using low-turnover construction.

**Decay evidence.**

- Nagel [V]: a steady decline from 1998 to 2007 that tracks the fall in VIX and decimalisation. He adds a pre-decimalisation dummy.
- Avramov, Chordia & Goyal [A]: "contrarian trading strategy profits are smaller than the likely transactions costs." Profits sit in high-turnover, illiquid losers.
- Medhat & Schmeling (2022) [V] show the reversal flips to *momentum* among high-turnover stocks (see Section 15). An unconditional reversal mixes two opposite effects.

**Mechanism (who pays).** Liquidity demanders pay for immediacy: uninformed sellers under pressure, and fund flows. Market makers and risk-constrained intermediaries are paid, and they demand more when their capital is scarce, which is when VIX is high. The trade is a short put on market turmoil: its worst-quarter loss coincides with liquidity crises.

**Costs.** About half of the transaction-price return is bid-ask bounce (0.30% versus 0.18%/day midquote) [V], so any backtest must use NBBO midquotes or next-trade fills, never closing prints. Daily turnover is roughly 100%+ of book; at 2–5 bp per side in large caps, the low-VIX state is unprofitable.

**Data needed.** SIP daily bars plus NBBO quotes near the close (available); VIX from CBOE's free download or SPY realised volatility as a proxy; SIC industries from the SEC submissions JSON (`sic` field, verified). Survivorship-free universe membership (delisted names) is a risk.

**Citations.**

- Nagel 2012: https://www.nber.org/papers/w17653
- Avramov, Chordia & Goyal 2006: https://ideas.repec.org/a/bla/jfinan/v61y2006i5p2365-2394.html (working paper: https://users.nber.org/~confer/2004/mmsu04/goyal.pdf)
- Da, Liu & Schaumburg 2014: https://doi.org/10.1287/mnsc.2013.1766 (NY Fed staff report 513: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr513.html)
- Hameed & Mian 2015: https://web2-bschool.nus.edu.sg/wp-content/uploads/media_rp/publications/BwXb81392625636.pdf
- de Groot, Huij & Zhou 2012: https://www.sciencedirect.com/science/article/abs/pii/S0378426611002263
- Blitz et al. 2013: https://www.sciencedirect.com/science/article/abs/pii/S1386418112000468

---

## 2. Industry momentum, within-industry reversal and slow industry information diffusion

**Definition.**

- Moskowitz & Grinblatt (1999), *JF* 54(4), 1249–1290 [A]:
  - 20 industries from 2-digit SIC. Value-weighted industry returns over the past L months (L = 1, 6, 12).
  - Long the top 3 industries, short the bottom 3. Hold H months (1–12).
  - The paper reports that industry momentum captures most of individual-stock momentum (except 12-month) and that the effect is strongest at the 1-month horizon [A/S].
- Hou (2007), *RFS* 20(4), 1113–1138 [A]:
  - Within each industry, lagged weekly returns of big firms predict weekly returns of small firms. The lead-lag effect is mostly intra-industry.
  - It is driven by slow response to *negative* news, and is stronger in small, less competitive, neglected industries.
- The within-industry reversal leg is covered in Section 1 (Hameed & Mian; Da, Liu & Schaumburg).

**Reported effect and sample.**

- Moskowitz & Grinblatt: 1963–1995. The 6-month/6-month strategy is often quoted at about 0.4%/month, and the 1-month/1-month strategy at about 1%/month **[U: exact table values not verified]**.
- Hameed & Mian [V] confirm significant inter-industry *momentum* in monthly returns, 1968–2010.
- Lou, Polk & Skouras (2019) [V]: industry momentum, like price momentum, earns its premium entirely overnight.
- Hou: weekly coefficient sizes not verified [U].

**Decay evidence.**

- No dedicated post-2010 decay study for 1-month industry momentum was found.
- Blitz et al. (2023, FAJ; Section 15) treat 1-month industry momentum as one of several short-term signals that are gross-profitable but erased by naive trading costs [S].

**Mechanism.** Investors under-react to industry-level news; Hou attributes this to limited attention and slow diffusion from bellwethers to small firms. The counterparties are slow-updating holders of laggard firms.

**Costs.** With 20–49 industries traded through sector ETFs, costs are low: SPDR sector ETFs cost about 1 bp per side. Industry momentum can therefore be implemented almost cost-free at a monthly or weekly rebalance. The within-industry stock-level reversal leg is expensive.

**Data needed.** SIP daily bars, and SIC codes (EDGAR) or the 11 SPDR sector ETFs plus industry ETFs. This is feasible. The Hou lead-lag test needs a size-sorted universe with small caps, so survivorship matters.

**Citations.**

- Moskowitz & Grinblatt 1999: https://doi.org/10.1111/0022-1082.00146 (AQR summary: https://www.aqr.com/Insights/Research/Journal-Article/Do-Industries-Explain-Momentum)
- Hou 2007: https://doi.org/10.1093/revfin/hhm003 (record: https://ideas.repec.org/a/oup/rfinst/v20y2007i4p1113-1138.html)

---

## 3. Overnight versus intraday "tug of war"

**Definition.**

- Lou, Polk & Skouras (2019), *JFE* 134(1), 192–213 [V]:
  - Overnight return = previous close → open. Intraday return = open → close.
  - "Open" = VWAP from 9:30 to 10:00 in TAQ. Observations with fewer than 1,000 shares are dropped.
  - Each month, sort into deciles on the lagged 1-month overnight (or intraday) return. Value-weighted. Hold one month.
  - Excludes stocks priced under $5 and the bottom NYSE size quintile. Sample 1993–2013.
- Berkman, Koch, Tuttle & Zhang (2012), *JFQA* 47(4), 715–741 [A/S]:
  - High-attention stocks (large absolute prior-day return or high retail attention) open high and reverse intraday.
  - Universe: the 3,000 largest US stocks, 1996–2008.

**Reported effect and sample.**

- Lou, Polk & Skouras [V]:
  - Overnight-winner minus overnight-loser decile: 3-factor overnight alpha **+3.47%/month** (t = 16.8), intraday alpha **−3.02%/month**. Intraday-sorted: intraday +2.41%, overnight −1.77%/month. Persists with signals lagged up to 60 months.
  - Momentum (12-2) overnight CAPM alpha 0.98%/month versus intraday −0.02% (overnight Sharpe 0.77 against 0.31 close-to-close). Short-term reversal: overnight +0.93%/month, intraday −1.05%.
  - Value, profitability, investment, beta and idiosyncratic volatility earn their premia intraday with opposite-signed overnight returns. The authors state that transaction costs make these patterns "much less attractive" [V].
- Berkman et al. [S]: all stocks average +0.10% overnight and −0.07% intraday per day. In hard-to-value or high-short-interest stocks: +0.4–0.6% overnight, −0.4–0.7% intraday.
- Della Corte, Kosowski & Wang (2016 working paper) [S]: an overnight-return reversal strategy earns about 5× the conventional short-term reversal in US stocks, 1993–2014, with 100% daily turnover. **Not peer-reviewed; numbers unverified.**

**Decay evidence.**

- Berkman et al. [S]: the effect "weakened after decimalisation in 2001 and the expansion of algorithmic trading in 2005."
- Boyarchenko, Larsen & Whelan (2023), *RFS* 36(9) [A/S]: the index-level "overnight drift" (2:00–3:00 ET in E-mini futures, about 3.7%/year over 1998–2020) has averaged **about zero since 2021**, per the authors' own 2026 New York Fed post. That window is not tradable in SPY.

**Mechanism.** Retail and attention-driven buyers trade at the open; institutions trade intraday and at the close (LPS show large TAQ trades cluster near the close). Persistent clientele demand creates price pressure that reverses in the other session. Buyers at the open pay an implicit cost larger than the effective half-spread.

**Costs.** A pure overnight/intraday split strategy trades twice a day, through the opening auction and MOC. Open-auction slippage is unknown with Alpaca data, and the 9:30–10:00 VWAP used by LPS is not a fill price. The practical use is **execution timing** (avoid buying attention stocks at the open; prefer later in the day), not a stand-alone strategy.

**Data needed.** SIP minute bars and trades for opening VWAP (from 2016), and the opening and closing auction prints (SIP trade conditions). Feasible. Note that 2016–2026 lies entirely in the post-decay regime.

**Citations.**

- Lou, Polk & Skouras 2019: https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- Berkman et al. 2012: https://doi.org/10.1017/S0022109012000270 (summary: https://www.cxoadvisory.com/?p=6907)
- Boyarchenko, Larsen & Whelan 2023: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf (decay post: https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/)
- Della Corte, Kosowski & Wang: https://www.cicfconf.org/sites/default/files/paper_357.pdf

---

## 4. Post-earnings-announcement drift with a price-based surprise (EAR)

**Definition.**

- Brandt, Kishore, Santa-Clara & Venkatachalam, "Earnings Announcements are Full of Surprises" (SSRN 909563, working paper; not found in a journal) [V, June 2007 version]:
  - EAR = 3-day buy-and-hold return over days [t−1, t+1] around the announcement, minus the matching size/book-to-market (2×3) Fama-French benchmark portfolio.
  - Quintile breakpoints come from the *previous* quarter's EAR distribution, so a stock can be placed on its own announcement day without look-ahead.
  - Long the top quintile, short the bottom. Returns accumulate from t+2 to t+n (up to about 4 quarters).
  - Universe: Compustat quarterly, 1987–2004.
- Chan, Jegadeesh & Lakonishok (1996), *JF* 51(5), 1681–1713 [A]:
  - Measure surprise three ways: SUE, the abnormal return around the announcement, and analyst revisions. Rank and hold up to 12 months.
  - NYSE/AMEX/Nasdaq, 1977–1993. Each signal predicts drift controlling for the others.
- Martineau (2022), *Critical Finance Review* 11(3–4), 613–646 [V]: SUE from the IBES analyst consensus (and seasonal random walk). Drift over 60 days. Sample 1984–2019.

**Reported effect and sample.**

- Brandt et al. [V]:
  - EAR L/S **6.3%/year** abnormal, against 5.6% for SUE.
  - The two signals are largely independent; combined about 11–11.5%/year.
  - EAR profits concentrate at the *next* earnings announcements: about **3.3%** spread in 3-day abnormal return around the next announcement.
  - The SSRN January 2008 version reports 7.55%/year [S].
  - Subperiods: the next-quarter EAR announcement-window spread rose from 2.67% (1987–95) to 3.14% (1996–2004).
  - A top-1000-firm table exists; values not extracted.

**Decay evidence.**

- Martineau [V]: "For large stocks, PEAD have been non-existent since 2006"; for microcaps, since 2016. Announcement-day price responses to surprises are 6× (non-microcap) and 3× (microcap) larger in 2016–19 than in 1984–90.
- Martineau tests *analyst/accounting* SUE, **not EAR**. EAR post-2005 is untested in what I found [U].
- Two 2025 papers claim PEAD persists [S]: Dickerson, Julliard & Mueller (*JFE*, "co-pricing factor zoo"), whose factor is built on announcement returns, and Hirshleifer, Peng & Wang (*RFS* 38(3), 2025).
- Subrahmanyam (SSRN 5930255, 2025) [S]: on 2001–2024, PEAD t = 2.18 for all stocks but **1.43 excluding microcaps**. The disagreement is microcaps and design choices.

**Mechanism.** Under-reaction from limited attention and anchoring, and analysts revising slowly (Chan et al.). The other side is investors who did not update on the announcement, and arbitrage limited by costs and idiosyncratic risk in small firms.

**Costs.** Quarterly signal with low turnover: about 4 rebalances a year per name, plus optional trades around the next announcement. Cost is not binding in large caps; the binding problem is that the large-cap effect may be zero after 2006.

**Data needed.**

- Earnings timestamps from SEC EDGAR [V]. `https://data.sec.gov/submissions/CIK##########.json` returns, per filing, `form`, `items` (for example `"2.02,9.01"`) and `acceptanceDateTime` in UTC. Checked on Apple: 8-K Items 2.02 accepted 2026-07-30T20:30:28Z, which is 16:30 ET, after the close. The `recent` block holds about 1,000 filings; older ones are in `files`.
  - Use acceptance time to classify before-open, intraday and after-close announcements, so the [t−1, t+1] window anchors to the first tradable session.
  - Caveats: the press release often crosses the wire minutes before the 8-K is accepted, and a few firms file 2.02 late. Send a `User-Agent` header and respect SEC rate limits.
- SIP daily bars for EAR, and SPY or a size/sector-matched benchmark in place of Fama-French benchmarks.
- SUE needs EPS: XBRL companyfacts (free) is feasible but not point-in-time-perfect [U].

**Citations.**

- Brandt et al.: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=909563 (PDF: https://www.anderson.ucla.edu/documents/areas/fac/finance/ear.pdf)
- Chan, Jegadeesh & Lakonishok 1996: https://www.nber.org/papers/w5375
- Martineau 2022: https://cfr.ivo-welch.org/published/papers/martineau2021rest.pdf
- Subrahmanyam and the 2025 debate: https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again

---

## 5. Pairs trading and relative value

**Definition.**

- Gatev, Goetzmann & Rouwenhorst (2006), *RFS* 19(3), 797–827 [V, 2006 working paper]:
  - Formation: 12 months. Normalise cumulative total-return indices. Pair each stock with the partner that minimises the sum of squared deviations (SSD). Keep the top 5 or 20 pairs.
  - Trading: the next 6 months. Open when the spread diverges by more than **2 standard deviations** (estimated in formation). Close at the next crossing or at period end.
  - Universe: CRSP liquid stocks (no missing days), 1962–2002.
- Do & Faff (2010), *FAJ* 66(4) and Do & Faff (2012), *Journal of Financial Research* 35(2), 261–287 [A/S]: the same rule applied through 2009, plus 29 refinements (same industry, number of zero crossings), with commissions, impact and short fees.

**Reported effect and sample.**

- Gatev et al. [V]: top-20 pairs **1.44%/month** excess on fully invested capital (t = 11.6), 0.81% on committed capital. Waiting one day to trade cuts this to **0.90%/month** (bounce/spread). Raw excess fell from 118 bp/month pre-1989 to about 38 bp afterwards; risk-adjusted from 67 to 42 bp.
- Do & Faff 2012 [A]: net of all costs, about 30 bp/month for refined intra-industry pairs and about 24 bp/month in the largest 30% of stocks. **"largely unprofitable after 2002."**
- CXO summary of the 2010 working paper [S]: gross 0.70–1.15%/month, net −0.07 to +0.35%/month. Most 1989–2009 profit came in the 2000–02 bear market.

**Decay evidence.** Strong and monotone: the post-1988 decline was documented by the original authors, and post-2002 profits are about zero net (Do & Faff).

**Mechanism.** Liquidity provision to idiosyncratic flows and convergence of temporary mispricing. The pair is short a fundamental divergence (merger, restructuring); non-convergence risk rose over time.

**Costs.** Two legs, a short leg, and roughly 2 round trips per trade. Short-borrow fees and recalls (Gatev et al. test recalls: −4 to −13 bp/month). Costs are binding.

**Data needed.** SIP daily bars (available). Shorting is simulated in paper trading; a borrow-fee assumption is needed. Feasible but unattractive. ETF-pair variants (for example sector versus sector) are not covered by these papers [U].

**Citations.**

- Gatev, Goetzmann & Rouwenhorst 2006: https://www.nber.org/papers/w7032 (2006 working paper: https://c.mql5.com/forextsd/forum/208/Pairs%20Trading%20-%20Performance%20of%20a%20Relative%20Value%20Arbitrage%20Rule.pdf)
- Do & Faff 2012: https://strathprints.strath.ac.uk/41722/ (summary: https://www.cxoadvisory.com/technical-trading/pairs-trading-net-profitability/)
- Do & Faff 2010: https://strathprints.strath.ac.uk/41067/

---

## 6. Intraday return periodicity (Heston, Korajczyk & Sadka)

**Definition.**

- Heston, Korajczyk & Sadka (2010), *JF* 65(4), 1369–1407 [V]:
  - Split each day into **13 half-hour intervals**.
  - Each interval, sort stocks into deciles by their return k half-hours ago. Long the winner decile, short the loser decile, equal-weighted, hold one half-hour.
  - Main universe: NYSE common stocks (share codes 10/11), January 2001 to December 2005, TAQ (1,715 firms).

**Reported effect and sample.**

- Lag 13 (same half-hour yesterday): winner-minus-loser **3.01 bp per half-hour** [V]. Above 1 bp at daily lags out to 5 days (t > 8.7); significant for at least 40 days. Non-daily lags reverse (−1.5 bp).
- Strongest at the open (Day-1 spread over 11 bp in the opening half-hour) and the close (about 8 bp) [V]. Robustness: 1.93 bp with filters; 2.45 bp for stocks with at least 10 trades per interval.

**Decay evidence.**

- Significance was *highest* after decimalisation, within 1993–2005 [V].
- Later international replications (UK, Brazil yes; China weaker) [S].
- No post-2010 US replication found [U].

**Mechanism.** Institutional order-splitting and fund flows trade at the same time of day across days. Persistent, predictable order imbalance causes repeated temporary price pressure.

**Costs.** The authors' own framing [V]: 3 bp is about the round-trip quoted half-spread twice over (S&P 500 half-spread about 1.7 bp in 2008), so the effect is "of the same order of magnitude" as costs. It is mainly an **execution-timing** tool ("timing trades can reduce execution costs by the equivalent of the effective spread").

**Data needed.** SIP minute bars for the universe from 2016 (heavy but available). Feasible as research. As a live strategy it needs real-time consolidated data, which is not available live (IEX only).

**Citations.**

- Heston, Korajczyk & Sadka 2010: https://www.bauer.uh.edu/departments/finance/documents/Heston_Korajczyk_Sadka_paper_UH.pdf (arXiv: https://ar5iv.arxiv.org/html/1005.3535)

---

## 7. Market intraday momentum (first half-hour predicts last half-hour)

**Definition.**

- Gao, Han, Li & Zhou (2018), *JFE* 129(2), 394–414 [V]:
  - r1 = SPY return from the *previous day's close* to 10:00 ET. r12 = 15:00–15:30. r13 = 15:30–16:00.
  - Timing strategy: at 15:30, go long SPY if r1 > 0 and short if r1 < 0 (a variant also uses r12). Exit at the 16:00 close.
  - SPY, TAQ, February 1993 to December 2013. Also tested on 10 other ETFs.
- Baltussen, Da, Lammers & Martens (2021), *JFE* 142(1), 377–403 [V]:
  - Predictor rROD = previous close to 15:30. Predicted variable rLH = last 30 minutes.
  - More than 60 futures (equities, bonds, commodities, FX), 1974–2020.

**Reported effect and sample.**

- Gao et al. [V]:
  - In-sample R² = 1.6% (r1 alone), 2.6% with r12. Out-of-sample R² = 1.2–1.4%.
  - The timing strategy earns **6.67%/year** with volatility 6.19% (Sharpe 1.08), trading about 30 minutes a day. That is about **2.6 bp per trade**.
  - Predictability is stronger on high-volatility and high-volume days, in recessions, and on macro-news days.
- Baltussen et al. [V]:
  - Present everywhere; equity-index rROD coefficient significant in both 1974–99 and 2000–2020.
  - Linked to **dealer short-gamma hedging** (options and leveraged ETFs): momentum appears only when market makers are net short gamma.
  - The effect reverses over the following days.

**Decay evidence.**

- No peer-reviewed post-2013 SPY replication found [U].
- Baltussen et al.'s sample to 2020 shows persistence in futures, and stronger effects in February–May 2020 [V].
- Dim, Eraker & Vilkov (2024 working paper) [A] find 0DTE gamma does *not* propagate volatility, which cuts against the "more gamma means more momentum" story after 2022.
- Practitioner: Zarattini, Aziz & Barbon (2024, SFI working paper 24-97) [A] report a "noise-area" breakout version on SPY earning 19.6%/year net with Sharpe 1.33 over 2007–2024. **It is an author-affiliated practitioner paper with a trailing-stop design, so treat it as a hypothesis and verify it yourself.**

**Mechanism.** Gamma hedging by short-gamma dealers and leveraged-ETF rebalancing near the close (both trade with the day's move). Infrequent rebalancing (Bogousslavsky 2016) and late-informed traders are alternative explanations. The other side is the hedgers themselves, who are price-insensitive.

**Costs.** Baltussen et al. [V]: "we do not consider transaction costs"; S&P futures stay net-positive at a cost of one tick. SPY's spread is about 1 cent (about 0.15–0.2 bp per side at current prices), so 2.6 bp gross is meaningfully above spread, and last-half-hour impact is small at retail size.

**Data needed.** SIP minute bars for SPY, QQQ and IWM, 2016–present (available). Live: r1 is fixed at 10:00 and delayed SIP has it by 10:15, so an r1-only 15:30 entry works. A ROD signal (close to 15:30) needs IEX real-time, because the delayed SIP only reaches 15:15 at 15:30; SPY on IEX is adequate as a price signal. Feasible.

**Citations.**

- Gao, Han, Li & Zhou 2018: https://doi.org/10.1016/j.jfineco.2018.05.009 (working paper: https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf)
- Baltussen, Da, Lammers & Martens 2021: https://www3.nd.edu/~zda/intramom.pdf
- Zarattini, Aziz & Barbon 2024: https://www.sfi.ch/de/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy
- Li, Sakkas & Urquhart (global intraday time-series momentum, 12 of 16 markets significant) [A]: https://centaur.reading.ac.uk/95566/1/Accepted-Version.pdf

---

## 8. Short-term pullback in a long-term uptrend: RSI(2) and Connors-style mean reversion on index ETFs

**Definition (canonical Connors).** Hold SPY long when:

- RSI(2) (Wilder) is below 10, **and**
- the close is above its 200-day SMA.

Enter at the close. Exit at the close when the close rises above the 5-day SMA. No stop. Long-only. Variants use RSI below 5, exit on RSI above 70, and so on.

**Academic evidence.** No peer-reviewed evaluation of RSI(2) itself was found. The closest rigorous evidence concerns the *ingredient*, short-horizon index mean reversion:

- Hu, Jin & Wang (SSRN 5314371, about 2025) [A]: daily US market return autocorrelation, 1897–2024, was "close to zero prior to 1929, ... peaks in the 1970s, and turns persistently negative after 2000." Reversals are more likely after *negative* returns. That is exactly the regime RSI(2) exploits.
- Anderson et al. (Berkeley working paper) [A]: SPY autocorrelation is mostly positive 1993–2000 and negative 2001–2008.

**Practitioner evaluation (the most rigorous found)** [S, single blog author, not peer-reviewed]:

- Setup: SPY 1993 to September 2026, dividend-adjusted, close fills, 2 bp per side.
- Full sample: 265 trades, 77% winners, average trade 0.63%, CAGR 5.0% at about 11% time in market, Sharpe 0.81 versus 0.65 for buy-and-hold, max drawdown 14.8%.
- Before 2009: Sharpe 0.97, average trade 0.79%. **2009 onward: Sharpe 0.68, average trade 0.51%, versus buy-and-hold Sharpe 0.87.**
- Robustness: all 15 pre-declared parameter variants positive (Sharpe 0.13–0.92); other ETFs Sharpe 0.38–0.53; 5.3%/year at zero cost, 3.7% at 10 bp.

**Decay evidence.** Average trade return fell by about 35% after the 2008 book. It still beats cash but **does not beat buy-and-hold on Sharpe after 2009** [S]. The negative index autocorrelation regime is ongoing [A].

**Mechanism.** Liquidity provision at the index level (Section 1's mechanism applied to ETFs). Discretionary and forced sellers after short drawdowns pay dealers. The uptrend filter avoids buying into crash regimes where reversal fails.

**Costs.** Low: about 12–20 round trips a year in SPY. The main implementation issue is the signal computed at the close: either estimate RSI at 15:55 or enter at the next open, which costs 0.2–0.5% per trade per one source [S].

**Data needed.** Daily bars for SPY and the sector ETFs. Trivially feasible, and back to 2000 with the existing Yahoo data.

**Citations.**

- Practitioner test: https://empiricalab.substack.com/p/connors-rsi2-spy
- Rules reference: https://www.quantifiedstrategies.com/rsi-2-strategy/
- Hu, Jin & Wang: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5314371
- Anderson et al.: https://eml.berkeley.edu/~anderson/Sources-042212.pdf

---

## 9. Failed breakouts, stop-loss cascades and liquidity sweeps ("smart money concepts")

**Rigorous evidence (all FX or order-book microstructure, not a tested equity strategy).**

- Osler (2003), *JF* 58(5), 1791–1819 [A]:
  - Data: a large FX dealer's order book (stop-loss and take-profit orders).
  - Take-profit orders cluster *at* round numbers, so trends tend to reverse there (support/resistance).
  - Stop-loss buy orders cluster *just above* round numbers and stop-loss sell orders *just below*, so trends accelerate once a level is crossed.
- Osler (2005), *JIMF* 24(2), 219–241 (NY Fed staff report 150) [V, working paper]:
  - Order data: August 1999 to April 2000, 9,655 orders, over $55 billion; stop-losses are 43% of orders by volume.
  - Order clustering, for example: 14.3% of executed stop-loss buys sit at rates ending 01–10, against 6.9% at 90–99.
  - Exchange-rate tests use Reuters minute quotes, January 1996 to April 1998.
  - Findings: trends are "unusually rapid" after rates reach stop-loss clusters (**cascades**). Stop-loss responses are larger and longer than take-profit responses. Most results are significant "for hours, although not for days."
- Kavajecz & Odders-White (2004), *RFS* 17(4), 1043–1071 [A]: support/resistance levels coincide with **peaks in limit-order-book depth**. Technical levels mark where liquidity already sits, which supports the "liquidity pool" intuition.
- Bhattacharya, Holden & Jacobsen (2012), *Management Science* 58(2), 413–431 [A]: in US stocks, buy-sell imbalances shift at round-dollar prices, and 24-hour returns differ across price points. Liquidity demanders lose nearly $1 billion a year.
- Brock, Lakonishok & LeBaron (1992), trading-range break [U], then Sullivan, Timmermann & White (1999), *JF* 54(5) [A/S]: after a data-snooping-adjusted bootstrap, the best rule on DJIA 1987–1996 earns an *insignificant* 8.63%/year before costs. Classic breakout rules died out of sample.
- Chung & Bellotti (arXiv 2101.07410) [A]: algorithmically identified support/resistance levels produce statistically significant bounces. Bounce probability rises with prior touches and decays over time. Asset coverage was not verified.
- Equity next-day evidence: Dow stocks with large high-to-close drops have higher next-day returns, a partial end-of-day overreaction (*Economics Letters*, 2012) [A].
- **No peer-reviewed study was found that tests "reversal after breaching the prior-day high or low" in US stocks or ETFs.**

**Reported effect and decay.** Osler's FX results are significant for hours, expressed as hit-rate and trend-speed differences, not tradable P&L [V]. No equity effect size exists. Decay is unknown; breakout rules have a long record of out-of-sample failure (Sullivan, Timmermann & White).

**Mechanism (who pays).** Stop-loss holders pay through price impact when clustered stops trigger together. Liquidity providers who absorb the cascade earn the reversal *if* the cascade was not informed. The "sweep then reverse" pattern is liquidity provision to forced stop flow, which is the same economics as Sections 1 and 15 at a known price level.

**Costs.** Intraday, with fills at the worst moment (during a cascade). Simulation needs quote data, not bars.

**Data needed.** SIP minute bars plus NBBO and trades for event studies around prior-day high/low breaches in SPY, QQQ and large caps. Feasible as a **descriptive event study**. There is no prior effect size to anchor power calculations.

**Citations.**

- Osler 2003: https://doi.org/10.1111/1540-6261.00588 (staff report 125: https://econpapers.repec.org/RePEc:fip:fednsr:125)
- Osler 2005: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf
- Kavajecz & Odders-White 2004: https://ideas.repec.org/a/oup/rfinst/v17y2004i4p1043-1071.html
- Bhattacharya, Holden & Jacobsen 2012: https://host.kelley.iu.edu/cholden/Bhattacharya%20Holden%20and%20Jacobsen%20(2012).pdf
- Sullivan, Timmermann & White 1999: https://www.fmg.ac.uk/sites/default/files/2020-11/dp303.pdf
- Chung & Bellotti: https://arxiv.org/abs/2101.07410
- End-of-day overreaction (Dow stocks): https://www.sciencedirect.com/science/article/abs/pii/S0165176512005666

---

## 10. Time-series momentum and trend at a daily rebalance on ETFs

This is not day trading: the holding period is weeks to months.

**Definition.**

- Moskowitz, Ooi & Pedersen (2012), *JFE* 104(2), 228–250 [A/U]:
  - For each of 58 futures and forwards (equity indexes, bonds, FX, commodities), take the sign of the past 12-month excess return.
  - Position scaled by inverse ex-ante volatility (target 40% per instrument, per my recollection) [U]. Held 1 month.
  - Sample 1985–2009.
  - Persistence over 1–12 months, partly reversing over longer horizons [A].

**Reported effect.** The diversified portfolio has "substantial abnormal returns with little exposure to standard asset pricing factors" and performs best in extreme markets [A]. The headline Sharpe is above 1 gross [U].

**Decay and critique.**

- Huang, Li, Wang & Zhou (2020), *JFE* 135(3), 774–794 [A]: asset-by-asset regressions show "little evidence of TSM, both in- and out-of-sample." The pooled t-statistic is unreliable under bootstrap. TSMOM profits are "virtually the same" as a strategy based on the historical sample mean.
- Trend-following CTA returns were weak in about 2011–2018, a widely reported pattern [U].

**Mechanism.** Initial under-reaction followed by delayed over-reaction, hedging demand, and the volatility-scaling channel. Partly a long-volatility, crisis-alpha profile.

**Costs.** Low with monthly rebalancing in liquid ETFs (SPY, TLT, GLD, DBC-type, UUP). Daily rebalancing adds turnover with little evidence of benefit.

**Data needed.** Daily ETF bars, available since 2016 (Alpaca) and 2000 (Yahoo). Feasible. A long-only, unlevered ETF version is not the futures strategy the paper tested: no shorting of bond futures and no leverage to reach equal risk.

**Citations.**

- Moskowitz, Ooi & Pedersen 2012: https://papers.ssrn.com/abstract=2089463 (AQR: https://www.aqr.com/library/journal-articles/time-series-momentum)
- Huang, Li, Wang & Zhou 2020: https://ideas.repec.org/a/eee/jfinec/v135y2020i3p774-794.html

---

## 11. Order-flow imbalance (OFI) predicting short-horizon returns

**Definition.**

- Chordia & Subrahmanyam (2004), *JFE* 72(3), 485–518 [A]:
  - Daily order imbalance per stock (buyer- minus seller-initiated trades, Lee-Ready signing), NYSE.
  - Lagged imbalance predicts next-day returns *positively*, but the sign **flips negative** once the same day's imbalance is controlled for.
  - A secondary source says a trading strategy is feasible but costs mitigate it [S].
- Cont, Kukanov & Stoikov (2014), *Journal of Financial Econometrics* 12(1), 47–88 [A]:
  - OFI = net change in best-bid size minus net change in best-ask size, from NBBO events over an interval.
  - Price changes are **contemporaneously** linear in OFI, with slope proportional to 1/depth. TAQ, 50 stocks.
  - This is a contemporaneous fit, not a forecast.
- Cont, Cucuringu & Zhang (2023), *Quantitative Finance* 23(10), 1373–1393 [A]: lagged cross-asset OFI improves forecasts, but "mainly ... at short-term horizons and decays rapidly". Horizons are seconds to minutes.
- Boehmer, Jones, Zhang & Zhang (2021), *JF* 76(5), 2249–2305 [A]:
  - Retail marketable orders are identified by sub-penny price improvement on off-exchange (TRF) prints.
  - Stocks with net retail buying beat those with net retail selling by about **10 bp over the next week**.
- Barber, Huang, Jorion, Odean & Schwarz (2024), *JF* 79(4), 2403–2427 [A]:
  - Placed 85,000 real retail trades. The BJZZ algorithm identifies only about 35% of them as retail and mis-signs about 28% of those it identifies.
  - Signing against the quote midpoint fixes most of the error.

**Decay and costs.**

- OFI is a high-frequency signal. The predictive part decays within seconds to minutes, so a non-HFT trader paying the spread with a 15-minute-delayed consolidated feed cannot capture it.
- The weekly retail-imbalance signal (about 10 bp/week, long-short across many names) is closer to accessible, but is about one round-trip of large-cap spread plus impact.
- No net-of-spread profit for non-HFT is documented [U].

**Mechanism.** Contemporaneous: inventory and adverse selection. Predictive (BJZZ): retail order flow carries some firm-level information, or persistent flow creates price pressure.

**Data needed.** SIP trades (with exchange code and sub-penny prices) and NBBO quotes from 2016. **Feasible for research.** The BJZZ/Barber-corrected retail imbalance can be built from Alpaca trades if TRF prints and conditions are present [U: verify exchange code "D" and the condition fields]. Live intraday OFI is infeasible: IEX-only real-time data.

**Citations.**

- Chordia & Subrahmanyam 2004: https://doi.org/10.1016/S0304-405X(03)00175-2
- Cont, Kukanov & Stoikov 2014: https://arxiv.org/abs/1011.6402
- Cont, Cucuringu & Zhang 2023: https://arxiv.org/abs/2112.13213
- Boehmer, Jones, Zhang & Zhang 2021: https://www.interactivebrokers.com/campus/ibkr-quant-news/how-to-track-retail-investor-activity-in-taq/
- Barber et al. 2024: https://papers.ssrn.com/abstract=4202874

---

## 12. Machine-learning cross-sectional prediction from short-horizon price and volume features

**Definitions and effects.**

- Gu, Kelly & Xiu (2020), *RFS* 33(5), 2223–2273 [V]:
  - About 30,000 US stocks, March 1957 to December 2016; 94 characteristics × 8 macro variables plus industry dummies; monthly horizon. Train 1957–74, validate 1975–86, test 1987–2016 with refits.
  - NN3 out-of-sample monthly R² **0.40%**; long-short decile Sharpe **1.35 (VW) and 2.45 (EW)**. The most important features are **short-term reversal (mom1m), momentum and liquidity**: price-based, short-horizon features.
- Jiang, Kelly & Xiu (2023), *JF* 78(6), 3193–3249 [V]:
  - CNN on OHLC-plus-volume chart images of 5, 20 or 60 days. Labels: positive 5-, 20- or 60-day future return.
  - Trained once on 1993–2000, tested 2001–2019 (NYSE/AMEX/Nasdaq).
  - Weekly-rebalanced decile H-L for I20/R5: **EW 0.84%/week (Sharpe 6.75); VW 0.22%/week (Sharpe 1.74)**. Monthly turnover about 670–730%.
  - Benchmarks: weekly short-term reversal is EW Sharpe 2.8 and VW 0.8.
  - The authors say the weekly version is "mostly accessible to investors who behave as market makers"; lower-frequency versions survive standard cost adjustments.
- Chinco, Clark-Joseph & Ye (2019), *JF* 74(1), 449–492 [A]:
  - LASSO on the whole cross-section of lagged **1-minute** returns (past 3 minutes) to forecast each stock's next-minute return.
  - Raises out-of-sample fit and forecast-implied Sharpe. The selected predictors are "unexpected, short-lived, and sparse" and often stocks with fundamental news.
  - Sample and magnitudes not verified [U].
- Krauss, Do & Huck (2017), *EJOR* 259(2) [A]: S&P 500 constituents, daily, 1992–2015. DNN/GBT/random-forest ensemble, top-10/flop-10: **above 0.45%/day before costs**, "declining in recent years". A secondary source says returns were negative in 2010–15 [S].
- Fischer & Krauss (2018), *EJOR* [A/S]: LSTM, 0.46%/day before costs, Sharpe 5.8. The published abstract says profits since 2010 seem "arbitraged away" and fluctuate around zero after costs. LSTM profits load on short-term reversal and high volatility.

**Decay and costs.**

- Avramov, Cheng & Metzker (2023), *Management Science* 69(5), 2587–2619 [A/S]: excluding microcaps cuts ML portfolio payoff by about 62%. Excluding distressed firms also reduces it. Realistic trading costs degrade it further. Some long-side signal remains.

**Mechanism.** Mostly a better-weighted combination of known liquidity-provision signals (reversal, illiquidity, volatility) plus some genuine non-linear interactions. The other side is the same as in Section 1.

**Data needed.** SIP daily bars and minute bars (2016+); point-in-time fundamentals are absent. Only the price/volume subset is feasible, which is the subset that matters most in these papers. The ten-year sample is short for training deep models; walk-forward needs care.

**Citations.**

- Gu, Kelly & Xiu 2020: https://dachxiu.chicagobooth.edu/download/ML.pdf
- Jiang, Kelly & Xiu 2023: https://doi.org/10.1111/jofi.13268 (SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3756587)
- Chinco, Clark-Joseph & Ye 2019: https://www.nber.org/papers/w23933
- Krauss, Do & Huck 2017: https://ideas.repec.org/a/eee/ejores/v259y2017i2p689-702.html
- Fischer & Krauss 2018: https://hdl.handle.net/10419/157808
- Avramov, Cheng & Metzker 2023: https://papers.ssrn.com/abstract=3450322

---

## 13. Crypto: intraday seasonality, weekends, funding rates and daily cross-sectional momentum/reversal

**Cross-sectional momentum and size.**

- Liu, Tsyvinski & Wu (2022), *JF* 77(2), 1133–1177 [V, NBER 2019 version]:
  - Coins above $1M market cap, CoinMarketCap, 2014–2018 in the working paper (the published sample may be extended [U]). Weekly quintile sorts, long the top quintile, short the bottom.
  - 1- to 4-week momentum earns **2.5–4.1% per week** excess, concentrated in **above-median-size coins** (4.2%/week, significant) versus below-median (0.6%, insignificant). A 3-factor model (market, size, momentum) prices the cross-section. **No trading costs** (the authors note this).

**Daily reversal.**

- Zaremba et al. (2021), *International Review of Financial Analysis* ("Up or down?") [A/S]:
  - More than 3,600 coins, 2015–2021.
  - Strong *daily* cross-sectional reversal, driven by illiquid coins.
  - **The largest, most tradable coins show daily momentum, not reversal.**

**Intraday and seasonality.**

- Shen, Urquhart & Wang (2022), *Financial Review* 57(2), 319–344 [A]: bitcoin's "first half-hour" (defined using volume-based sessions) predicts the last half-hour. Stronger in high-volume and high-volatility sessions. Mechanism attributed to liquidity provision.
- Padyšák & Vojtko (2022, SSRN, Quantpedia authors) [S]: BTC hourly returns 2015–2022 concentrate in **21:00–23:00 UTC**. Single research group, practitioner source. **Unverified.**
- Weekend effect: mixed. One study using BTC 2014–2024 daily data finds no weekend/weekday mean difference, only lower weekend volatility and volume [S]. Another hourly study puts the day-of-week effects entirely in Sunday 23:00–00:00 UTC [S]. **Treat as weak.**

**Funding rates.** He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures" (arXiv 2212.06888) [A]: perp prices deviate from no-arbitrage far more than FX forwards, with deviations that co-move across coins and shrink over time. Their high-Sharpe strategy **trades the perp**, so it is infeasible here. No reviewed evidence was found that funding predicts *spot* returns [U].

**Decay.** The crypto anomaly literature is short (samples end 2018–2022). Market efficiency in large coins has risen.

**Costs.** Coinbase taker fees for retail are tens of bp per side, far higher than equities. Daily cross-sectional strategies across small coins are cost-dominated, and small-coin liquidity on Coinbase is thin.

**Data needed.** Existing: BTC/ETH/SOL at 5-minute, 1-hour and 1-day resolution; a 473-product Coinbase daily universe including delisted products. Feasible for weekly momentum on the top 20–30 coins and for BTC intraday seasonality. Funding data is publicly downloadable from exchanges but is only usable as a signal.

**Citations.**

- Liu, Tsyvinski & Wu 2022: https://www.nber.org/papers/w25882.pdf
- Zaremba et al. 2021: https://www.sciencedirect.com/science/article/pii/S1057521921002349
- Shen, Urquhart & Wang 2022: https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/
- Padyšák & Vojtko (Quantpedia summary): https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin
- He, Manela, Ross & von Wachter: https://arxiv.org/abs/2212.06888

---

## 14. Closing auction, end-of-day effects and pre-close liquidity

**Papers.**

- Bogousslavsky (2021), *JFE* 141(1), 172–194 [A/V, 2016 working paper]:
  - Arbitrageurs unwind before the close because of overnight margin and lending costs.
  - A mispricing factor earns positive returns through the day but **performs poorly at the end of the day**, more so in the second half of the sample.
  - Working paper: size and illiquidity premia are realised in the **last 30 minutes**. Profitability and idiosyncratic-volatility effects accrue through the day and lose overnight.
- Bogousslavsky & Muravyev (2023), *Journal of Financial Markets* 66, 100852 [A]:
  - The closing auction was **7.5% of daily volume in 2018**, up from 3.1% in 2010, driven by indexing and ETFs.
  - Closing prints often **deviate from the closing quote midpoint**. Half the deviation reverts shortly after the close and all of it overnight.
  - Little price discovery happens at the auction. As volume migrates to the close, liquidity at the open worsens.
- Baltussen, Da & Soebhag, "End-of-Day Reversal" (working paper, April 2025; Quantpedia award 2025) [V]:
  - Signal ROD3 = return from the previous close to 15:00 (skipping 15:00–15:30).
  - Each day, sort stocks into quintiles or deciles on ROD3. Long the losers, short the winners, from 15:30 to the 16:00 close. CRSP/TAQ, January 1993 to December 2019.
  - Quintile L/S: **3.78 bp/day VW (about 9.5%/year), 6.86 bp/day EW (17.3%/year)**, t above 10.
  - Largest 20% of firms: 6-factor alpha **3.41 bp/day** (t = 10.6). Smallest 20%: 14.7 bp/day.
  - Driven by positive price pressure on intraday *losers*: attention-driven retail buying and short-sellers covering before the close. The authors say it is not liquidity- or gamma-driven and is distinct from market intraday momentum.

**Decay.** Bogousslavsky: the end-of-day mispricing effect is stronger in the later half of the sample. End-of-day reversal: rolling 3-year coefficients are "largely persistent" through 2019 [V]. Post-2019 is untested.

**Costs.** End-of-day reversal trades twice daily. The authors [V]: "might not be exploitable by many investors after accounting for transaction costs"; it suits market makers or the timing of planned trades. For large caps at 1–3 bp per side, a 3.4 bp/day gross edge is roughly break-even. Exiting via MOC is subject to the auction-price deviation Bogousslavsky & Muravyev document.

**Data needed.** SIP minute bars plus closing auction prints (trade condition codes) and NBBO at 15:59:59 (available from 2016). Feasible for research. Live execution at 15:30 with a cross-sectional signal across hundreds of names needs consolidated real-time data, which is not available (IEX-only). An IEX-based approximation for large caps is possible [U]. **Backtest hygiene for every family:** use the 15:59 midpoint, not the closing print, as the "close" mark.

**Citations.**

- Bogousslavsky 2021: https://ideas.repec.org/a/eee/jfinec/v141y2021i1p172-194.html (2016 working paper: https://finance.unibocconi.eu/sites/default/files/files/media/attachments/The%2520Cross-Section%2520of%2520Intraday%2520and%2520Overnight%2520Returns_21Dec1620170112151545.pdf)
- Bogousslavsky & Muravyev 2023: https://ideas.repec.org/a/eee/finmar/v66y2023ics1386418123000502.html
- Baltussen, Da & Soebhag 2025: https://www3.nd.edu/~zda/EOD.pdf

---

## 15. Other recent (2022–2026) short-horizon results, read skeptically

- **Short-term momentum.** Medhat & Schmeling (2022), *RFS* 35(3), 1480–1526 [V, accepted version]:
  - Monthly conditional double decile sort (NYSE breakpoints) on last month's return, then last month's share turnover. Value-weighted, rebalanced monthly.
  - In the **highest-turnover decile**, winners minus losers earns **+16.4%/year**; skipping the last days of the month, 22.0%.
  - In the lowest-turnover decile, the reversal is −16.9%/year.
  - Sample July 1963 to December 2018. Strongest in the **largest, most liquid** stocks. Survives Novy-Marx/Velikov cost estimates.
  - Horizon is monthly, not 1–5 days, but it is the most cost-robust short-horizon price result in this review. It also implies that a reversal trade should *exclude* high-turnover names.
- **Short-term signal composites.** Blitz, Hanauer, Honarvar, Huisman & Vidojevic (2023), *FAJ* 79(4), 96–117 [A/S]:
  - Signals: short-term reversal, industry momentum, analyst revisions and similar.
  - Single signals: gross alpha above 6%/year, **net below −2% at 25 bp per one-way trade**.
  - The composite plus buffered trading (buy top 10%, hold until it leaves the top 50%) leaves positive net alpha; post-publication and international results hold.
  - Robeco-authored, but in a peer-reviewed journal.
- **Covered elsewhere:** end-of-day reversal (Section 14; the most promising *new* intraday cross-sectional result, but its gross edge is about one spread in large caps), retail-flow imbalance (Section 11), the overnight drift (Section 3, **already decayed** since 2021) and daily-horizon ML (Section 12, near zero post-2010 in large caps).
- **The cost reality check** (Chen & Velikov 2023, above): the default prior for any published cross-sectional anomaly, net, post-2005, is a few bp per month.

**Weak or unverified evidence flagged.** Zarattini, Aziz & Barbon (SPY noise-area momentum, author-affiliated with trading firms); Padyšák & Vojtko (BTC 21–23 UTC); the RSI(2) blog test; Della Corte et al. (overnight reversal working paper). None has independent peer-reviewed replication.

---

## Appendix: free point-in-time sources (verified on 2026-10-26)

- **SEC EDGAR submissions JSON** (`data.sec.gov/submissions/CIK{10-digit}.json`):
  - Per filing: `form`, `items`, `acceptanceDateTime` (UTC), `filingDate`.
  - Company level: `sic`, `sicDescription`, `tickers`.
  - Requires a descriptive `User-Agent`.
  - Use it for 8-K Item 2.02 earnings timestamps (Section 4) and SIC industries (Sections 1 and 2).
- **VIX history**: CBOE's free daily CSV [U: URL not re-checked]. Alternatively, a realised-volatility proxy from SPY minute bars.
- **Closing-auction and opening-auction prints**: in SIP trades, identified by sale-condition codes [U: verify Alpaca's condition-code mapping].
