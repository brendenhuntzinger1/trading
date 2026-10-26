# Tested inventory: what has actually been tested, on which dates, at what cost

Built 2026-10-26 from primary records only: `research/registry.jsonl` (192 lines; cited by entry name, with
the line number where names repeat), `research/consumed_data.json`, the result files under `research/`, the
phase-1 CSVs (`results_1d_*.csv`, `results_1h_*.csv`) and `research/phase2/data_inventory.json`. Documents
are cited where they add facts the registry does not hold. "Not recorded" means no file read for this
inventory states it.

## 0. Summary

| Item | Value |
|---|---|
| Distinct economic hypotheses tested | **12**, plus 3 passive benchmark configurations that the registry counts as trials |
| Configurations evaluated (registry-counted trials) | **108** = 100 (`trial_count_baseline_2026-10-26`) + 6 ORB + 2 H3 |
| Passes on the pre-registered standard | 0 promoted. `test3:gate` met its test rule (`PASS_test: true`) but was not promoted (RESEARCH.md §7) |
| Crypto (Coinbase) history read | 2018-01-01 → **2026-10-24** (daily); 2020-01-01 → 2026-10-24 (5-minute); 2021-03-01 → 2026-10-24 (hourly cross-section). No historical crypto window is unread |
| US stocks/ETFs (Yahoo) read | Daily 2000-01-03 → **2026-10-23**; hourly 2023-11-27 → 2026-10-23; 5-minute 2026-07-31 → 2026-10-23 |
| US stocks in play (Alpaca SIP minute bars + NBBO) read | **2020-01-02 → 2021-12-31 only** (ORB and H3 development) |
| Unread | Stocks-in-play intraday **2022-01-03 → 2023-12-29** (ORB/H3 validation) and **2024-01-02 → 2026-07-24** (ORB/H3 final) |

---

## 1. Distinct economic hypotheses and their configurations

Parameter variants, walk-forward versions and labelled side-variants are grouped under one hypothesis.

| # | Economic hypothesis | Study / registry names | Configs | Instruments | Bars | Data source (venue) | Holding period |
|---|---|---|---|---|---|---|---|
| H1 | **Time-series trend following on crypto** (price above SMA, SMA crossovers, momentum, Donchian/breakout, trend + volatility targeting) | Phase 1 `phase1_exploration` (17 trend configs: 11 daily, 4 hourly, 2 ensembles incl. `ensemble_vol40`); phase 3 `trial:breakout` ×9, `trial:breakout_wf` ×1 | **27** | BTC, ETH, SOL (phase 1); BTC+ETH 50/50 sleeves (phase 3) | Daily; hourly for 4 phase-1 configs | Coinbase Exchange public candles | Days to weeks; no fixed horizon (signal or 3×ATR trailing-stop exit). Mean hold not recorded |
| H2 | **Short-horizon mean reversion** (buy dips inside uptrends) | Phase 1: `rsi2_dip_trend200` daily and hourly, `bollinger_20_2.0` hourly (3); `trial:meanrev` ×12, `trial:meanrev_wf` ×1 | **16** | BTC, ETH (+SOL in phase 1) | Daily; hourly (2 phase-1 configs) | Coinbase | ≤ 5 or ≤ 10 days (`max_hold`) in phase 3; phase-1 holds not recorded |
| H3x | **Cross-sectional crypto ranking** (which coins to hold) | Phase 3 rotation: `trial:rotation` ×16, `trial:rotation_wf` ×1; P1: `prereg_p1` (P1a B1, B2, M1, M2, M3; P1b B1, M1, M3) | **25** (17 + 8) | Rotation: 473 Coinbase USD products incl. 90 delisted; P1: Coinbase USD point-in-time universe (median 16 coins) | Daily (rotation); hourly inputs (P1) | Coinbase | Rotation: rebalance every 7 or 28 days. P1a 24 h; P1b 168 h |
| H4 | **Regime / strategy selection** (switch among baseline, fixed 33 %, cash) | `trial:selector_trailing` ×2, `trial:selector_regime` ×2 | **4** | BTC, ETH | Daily | Coinbase | Yearly refit; min hold 20 or 60 days (regime) |
| H5 | **Cost-aware trade gate** (state-conditional 20-day expected return must exceed cost) | `trial:gate` ×2 | **2** | BTC, ETH | Daily | Coinbase | 20-day horizon |
| H6 | **Macro-event de-risking** (halve exposure before FOMC/CPI) | `trial:calendar` ×4 | **4** | BTC, ETH | Daily | Coinbase prices; Fed/BLS calendar | 1–2 days before each event |
| H7 | **Market intraday momentum** (prev close → 10:30 predicts last half hour), S1 | `intraday_stocks_trial:S1_*` ×5 | **5** | S&P 100 + SPY, QQQ, IWM, DIA | Hourly | Yahoo chart API | 15:30 → close (30 min) |
| H8 | **Large-cap gap-down intraday reversal**, S2 / S2-ETF / S2X | `intraday_stocks_trial:S2_*` ×4, `S2_stopvariant_hourly_window` ×1; `s2x_test` ×1 | **6** | S&P 100 + 11 sector ETFs; ETF-only (14); S2X: 29 new equity ETFs + 7 bond/commodity ETFs | Daily open/close (stop variant: hourly) | Yahoo | Open → close, one session |
| H9 | **Opening-range breakout on stocks in play** (Zarattini et al. 2024), incl. exploratory S3 | `orb_dev` (primary, long_short, dev_rv2_top20, dev_rv5_top20, dev_rv1_top10, dev_rv2_top10); `intraday_stocks_trial:S3_exploratory_orb` ×1 | **7** (6 + 1) | All US common stocks/ETFs, point-in-time (ORB Amendment 4); S3: S&P 100 + ETFs | 1-minute SIP (ORB); 5-minute Yahoo (S3) | Alpaca market data v2, `feed=sip` (ORB); Yahoo (S3) | 09:35 stop entry → 10 % ATR stop or close; median time to stop 1 min (`research/orb/results/dev.json`) |
| H10 | **First-candle continuation on stocks in play**, H3 | `prereg_h3` configs H3-L (primary), H3-LS (labelled); `h3_dev_check` | **2** | As ORB `primary` selection | 1-minute SIP (5-minute first candle) | Alpaca SIP | 09:35 → close |
| H11 | **Crypto crash rebound** (liquidation cascade), C1 | `intraday_crypto_dev:C1_*` ×4 | **4** | BTC, ETH, SOL; holdout: 31 of 51 eligible coins | 1h signal; 5m (taker) / 1m (maker) management | Coinbase | ≤ 6 h (±1.5σ bracket) |
| H12 | **Crypto intraday time-series momentum** (00–06 UTC → rest of day), C2 | `intraday_crypto_dev:C2_*` ×3 | **3** | BTC, ETH | 5-minute | Coinbase | 06:00 → 23:55 UTC (≤ ~18 h) or −2σ stop |
| — | Passive benchmarks counted as trials | Phase 1 `buy_hold` daily and hourly (2); `trial:fixed` (fixed 33 %) (1) | **3** | BTC, ETH, SOL | Daily / hourly | Coinbase | Buy and hold; 2 % rebalance band |
| | **Total** | | **108** | | | | |

Phase-1 breakdown (22 = 13 daily + 7 hourly + 2 ensembles, `phase1_exploration` params) is read from the
strategy columns of `results_1d_2018-01-01_now.csv` and `results_1h_2021-07-01_now.csv`.

**Not counted as configurations** (registry treats them as checks, not trials): holdout re-runs
(`holdout_single_assets`, `holdout_point_in_time_universe`, `intraday_crypto_holdout:C1_k4_maker`),
`audit_baseline` cost re-runs, `posthoc_holdout_exposure_matched`, `test3_addon` stresses, cost grids, all
benchmarks/placebos (P1 cash/EW/BTC/random; ORB SPY/basket/direction-only/placebo; H3 basket/opposite
side; S2X SPY/placebo), and the five `decision_quality:*` exploratory analyses (each with several dev-fitted
buckets or regime groups). Duplicate registry rows are one configuration each: lines 121/125
(`S2_stopvariant_hourly_window`), 122/126 (`S3_exploratory_orb`), 189/191 (`h3_dev_check`), 190/192 (`h3_stop_after_dev`).

---

## 2. Periods per hypothesis, and what was read

"Read" = outcomes computed and looked at. All dates inclusive unless the registry writes an exclusive end.

| Hyp. | Development | Validation | Test / final | Read? | Source |
|---|---|---|---|---|---|
| H1 phase 1 | In-sample exploration on **2018-01-01 → 2026-10-24** daily (also split 2018–2021 and 2022→); hourly **2021-07-01 →** latest | none | none (whole history in-sample) | **All read** | `phase1_exploration`; `results_*.csv` |
| H1 `ensemble_vol40` holdouts | — | — | LTC from 2017-07-20, BCH from 2018-07-08, ETC from 2019-02-24 (listing + 200 d) → 2026-10-24; universe BTC+ETH+LTC+BCH 2018-01-01 → 2026-10-24 | Read | `holdout_single_assets`, `holdout_point_in_time_universe` |
| H1, H2, H3x-rotation, H6 (phase 3) | 2018-01-01 → 2021-12-31 | 2022-01-01 → 2023-12-31 | **2024-01-01 → 2026-10-24**; holdout coins LTC/BCH/ETC 2018–2026 for single-asset families | All read | `trial:*`, `validation:*`, `prereg3:*`, `test3:*` |
| H4, H5 and the three `_wf` variants | Scored 2020-01-01 → 2021-12-31 (2018–19 used as fitting history; `research/study_strategies.py` l.274, 283) | 2022-01-01 → 2023-12-31 | 2024-01-01 → 2026-10-24 | All read | same |
| H3x P1 | 2021-03-01 → 2024-06-30 (out-of-fold scoring: P1a 2022-03-01 → 2024-06-30, 853 days; P1b 2022-02-28 → 2024-06-24, 122 weeks; stopping check on all 1,218 days / 174 weeks) | 2024-07-01 → 2025-06-30 | **2025-07-01 → 2026-10-24** (P1b weeks 2025-07-07 → 2026-10-19) | **All three read**: 2021-03 → 2026-10-24 | `p1_p1a_*`, `p1_p1b_*`; `P1_REPORT.md` |
| H7 S1 | 2023-11-27 → 2025-01-24 | 2025-01-27 → 2025-08-25 | **2025-08-26 → 2026-10-23** | All read | `intraday_stocks_trial/validation/test:S1_*` |
| H8 S2 | 2000-01-01 → 2015-12-31 | 2016-01-04 → 2020-12-31 | **2021-01-04 → 2026-10-23**; stop variant 2023-11-27 → 2026-10-23 | All read | `intraday_stocks_*:S2_*` |
| H8 S2X | — | — | **2016-01-01 → 2026-10-24** (registry `s2x_test`; prereg and data end 2026-10-23, see §8) | Read | `prereg_s2x`, `s2x_test` |
| H9 ORB | **2020-01-02 → 2021-12-31** | 2022-01-03 → 2023-12-29 | 2024-01-02 → 2026-07-24 | **Development only.** Validation and final **unread** (B16) | `orb_dev`, `orb_stop_after_dev` |
| H9 S3 exploratory | — | — | 60 sessions; trades 2026-08-20 → 2026-10-23 | Read; excluded from all ORB periods (2026-07-27 → 2026-10-23) | `intraday_stocks_explore:S3` |
| H10 H3 | Hypothesis generation / A1 check: **2020-01-02 → 2021-12-31** | 2022-01-03 → 2023-12-29 | 2024-01-02 → 2026-07-24 | **Development only.** Validation and final **unread** | `prereg_h3`, `h3_amendment1`, `h3_dev_check`, `h3_stop_after_dev` |
| H11, H12 C1/C2 | 2020-01-01 → 2022-12-31 (registry: `..2023-01-01`, exclusive) | 2023 | **2024-01-01 → 2026-10-24**; C1 holdout coins same dates | All read | `intraday_crypto_dev/validation/test:*`, `intraday_crypto_holdout:C1_k4_maker` |

ORB/H3 caveat: the 2022–26 window was never read **for these signals**, but US stocks over those dates were
read at daily/hourly resolution by S1, S2 and S2X (ORB Amendment 1, B1). H3's 2022–23 validation fetch
started 09:37:59 UTC and was stopped at 09:50 UTC before any outcome was computed (incident 20); the ledger
marks it consumed conservatively (`consumed_data.json`, scope `stocks.us.intraday.first_candle`).

---

## 3. Trial-count reconciliation

| Count | Composition | Where used |
|---|---|---|
| 73 | 22 phase 1 + 51 phase 3 | RESEARCH.md (DSR) |
| 96 | 73 + 11 stock + 12 crypto (assumed) | `intraday_stocks_test:*` `E6_n_trials` |
| 98 | 73 + 7 crypto + 18 stock (assumed) | `intraday_crypto_frozen:*`, `intraday_crypto_test:*` `n_trials` |
| 91 | 22 + 51 + 11 + 7 | INTRADAY_REPORT.md, RESEARCH_AUDIT.md; ORB original §9 |
| 92 | 91 + S2X | `s2x_test` (`DSR_null_var_N92`); RESEARCH_BUDGET.md "Spent so far (2026-10-25)" |
| 100 | 92 + P1's 8 | `trial_count_baseline_2026-10-26` (`n_trials: 100`); P1 Amendment 1 A9 |
| 106 | 100 + 6 ORB | ORB Amendment 3, B12 |
| **108** | 106 + 2 H3 (H3-L, H3-LS; both computed in `research/h3/results/dev_check.json`) | H3_PREREGISTRATION.md (E6, N = 108) |

**Current total: 108 configurations.** It includes three passive benchmarks the registry logs as trials
(phase-1 daily and hourly buy-and-hold; `trial:fixed`) and P1's two no-fit rule baselines (B1, B2). Without
the three passive benchmarks: 105. RESEARCH_BUDGET.md's "92" is the figure as of 2026-10-25, before P1,
ORB and H3; its cap "N becomes ≤ 110" was respected (108).

---

## 4. Data already inspected, and what remains unread

| Market | Scope | Date range | Seen by | Status |
|---|---|---|---|---|
| Crypto, Coinbase | BTC/ETH/SOL daily | 2018-01-01 → 2026-10-24 (2017 = warm-up) | Phase 1 (in-sample), audit, phase 3 dev/val/test | Read. Ledger lists only 2024-01-01 → 2026-10-24 (`crypto.coinbase.daily`) |
| Crypto, Coinbase | BTC/ETH/SOL hourly | 2021-07-01 → latest | Phase 1 hourly configs | Read; not in ledger |
| Crypto, Coinbase | LTC/BCH/ETC daily | listing + 200 d → 2026-10-24 | `ensemble_vol40` holdouts; phase-3 holdouts | Read; not in ledger |
| Crypto, Coinbase | 473 USD products daily | 2018 → 2026-10-24 | Rotation dev/val/test | Read; not in ledger |
| Crypto, Coinbase | Point-in-time cross-section, hourly | 2021-03-01 → 2026-10-24 | P1 dev + validation + final | Read; ledger `crypto.coinbase.cross_section` |
| Crypto, Coinbase | BTC/ETH 5m (SOL from 2021-06-17), 1m windows | 2020-01-01 → 2026-10-24 | C1/C2 dev 2020–22, val 2023, test 2024 → 2026-10-24 | Read; ledger lists test only (`crypto.coinbase.intraday`) |
| Crypto, Coinbase | 51 holdout coins, 1h from 2023-11-01 + 5m/1m windows | 2024-01-01 → 2026-10-24 | C1 holdout | Read; covered by `crypto.coinbase.intraday` note |
| Crypto | **Unread historical crypto** | — | — | **None** in any tested scope. Only prospective data (from 2026-10-25) is clean (P1_METHODS_AND_AUDIT.md §3) |
| US stocks, Yahoo | S&P 100 + 15 ETFs daily | 2000-01-03 → 2026-10-23 | S2 dev 2000–15, val 2016–20, test 2021-01-04 → 2026-10-23 | Read; ledger lists 2021-01-04 → 2026-10-23 only |
| US stocks, Yahoo | Same, hourly | 2023-11-27 → 2026-10-23 | S1 dev/val/test; S2 stop variant; DECISION_QUALITY Q3 | Read |
| US ETFs, Yahoo | 29 + 7 new ETFs daily | 2016-01-01 → 2026-10-23 | S2X | Read; ledger `stocks.us.intraday.open_close` 2016-01-01 → 2026-10-24 |
| US stocks, Yahoo | 5-minute, 60 sessions | 2026-07-31 → 2026-10-23 (ledger: from 2026-07-27) | S3 exploratory | Read; excluded from ORB/H3 |
| US stocks in play, Alpaca SIP | 1-minute bars, NBBO, daily panel | **2020-01-02 → 2021-12-31** | ORB development (6 configs + benchmarks), H3-L/H3-LS development | **Read**; not in ledger |
| US stocks in play, Alpaca SIP | NBBO quotes, 30 in-play stock-days | 2023 (dates not recorded here) | Data gate B7.4 (spread measurement only) | Quotes seen; no strategy outcome |
| US stocks in play, Alpaca SIP | Opening bars and daily bars fetched | or5 cache to 2023-01-03; daily cache 2021-11-24 → 2023-12-29 (`data_inventory.json`) | H3 validation fetch (stopped) | Fetched; **no outcome computed**. Ledger marks 2022-01-03 → 2023-12-29 consumed conservatively |
| US stocks in play, Alpaca SIP | ORB/H3 validation | **2022-01-03 → 2023-12-29** | — | **Unread** for ORB; unread for H3 (ledger-marked, see above) |
| US stocks in play, Alpaca SIP | ORB/H3 final | **2024-01-02 → 2026-07-24** | — | **Unread** |
| US stocks in play | 2016–2019 | — | — | Not usable: Alpaca asset master and corporate-actions feed cannot rebuild the universe (ORB Amendment 4, B15) |

---

## 5. Costs: assumed vs measured, per study

| Study | Assumed cost | Measured | Source |
|---|---|---|---|
| Phase 1 (22 configs) | 0.45 %/side (0.40 % "Kraken" fee + 0.05 % slippage) on Coinbase prices; CSVs also show `no_fees`, `kraken_maker`, `kraken_taker` | None | AUDIT.md; `results_*.csv` |
| `ensemble_vol40` audit/holdouts | 0.60 % taker + 1 bp half-spread + 5 bp slippage = 0.66 %/side; re-costed at 0.45 / 0.66 / 0.86 / 1.25 % and maker-with-20 %-misses | None | `holdout_*` params; `audit_baseline`; AUDIT.md |
| Phase 3 (H1–H6) | 0.66 %/side BTC/ETH, 0.80 %/side alts (rotation); stress 1.25 %/side, 20 % missed fills, +12 h delay | None in the study | `prereg3:*` note; RESEARCH.md |
| S1, S2 | 5 bp entry + 3 bp MOC = **8 bp** round trip; stress 24 bp; S2 10 bp entry sensitivity (13 bp) | None (no quote data). SEC fee 0.21 bp verified | INTRADAY_HYPOTHESES.md (+ Amendment 1); COSTS.md |
| S2X | 8 bp base, 24 bp stress, 13 bp sensitivity | None | S2X_PREREGISTRATION.md |
| S3 exploratory | 10 bp round trip (derived: gross −0.089 % vs net −0.189 %) | None | INTRADAY_STOCKS.md |
| C1 | Maker entry 0.40 % + taker exit 0.66 % = **1.06 %**; taker variants 1.32 %; stress +0.15 %/side | BTC spread 0.001 bp, ETH 0.2–0.55 bp, BTC/ETH depth $2–7M within 10 bp (live, 2026-10-25). Fee, maker fills, alt spreads not measured | COSTS.md; `intraday_crypto_test:C1_k4_maker` (`round_trip_cost_mean` 0.0106) |
| C2 | **1.32 %** (taker both sides) | as C1 | `intraday_crypto_test:C2_m1.5` (0.0132) |
| P1 | **1.32 %** base; grid 0.50 / 0.80 / 1.06 / 1.92 / 2.52 % | None | P1_PREREGISTRATION.md A3 |
| ORB | Measured SIP NBBO half-spread at trigger, stop and close minutes, plus assumed slippage 1 bp/side (5 bp stress), plus SEC/TAF; 10 bp/side (25 stress) where no quote | Per trade. Primary: gross −9.16 bp, net of spread −33.32 bp, net of all −35.38 bp, so ≈ 26 bp round trip in total (derived) | `research/orb/results/dev.json`; ORB Amendment 1 B2 |
| H3 | As ORB at 09:35 and 15:59 | H3-L mean cost 22.98 bp round trip; 99.3 % of trades had a measured spread | `research/h3/results/dev_check.json` |
| Spread gate (no strategy) | — | In-play stocks, 30 stock-days, 2023: half-spread 09:35–10:30 **median 4.0 bp, p90 10.3 bp**; 15:59 **median 1.5 bp** | docs/ALPACA_DATA_AUDIT.md (B7_4); MORNING_REPORT.md |
| Alpaca crypto paper (no strategy) | — | One $10 BTC round trip, 2026-10-26: fee 0.25 %/side, buy 4.7 bp and sell 1.1 bp from mid, **≈ 0.56 %** all-in. n = 1, simulated fills | STATUS.md; MORNING_REPORT.md |
| Coinbase fee | **0.60 % taker / 0.40 % maker assumed**; secondary sources conflict (0.90 % or 1.20 % taker) | Not verified | COSTS.md |

The gate's 4.0 bp median covers every minute 09:35–10:30. On ORB/H3 trades, which enter at or near
09:35, spread plus fees came to about 20–24 bp per round trip, roughly twice what the gate medians imply.
This is derived as gross minus net-of-spread: ORB 24.2 bp, H3-L 20.0 bp, from the two result files above.

---

## 6. Scope of each conclusion

| Hyp. | Shows | Does not show |
|---|---|---|
| H1 trend | The phase-3 breakout config lost to an exposure-matched fixed allocation on 2024-01-01 → 2026-10-24 at 0.66 %/side; `ensemble_vol40` lost to buy-and-hold Sharpe on 3 holdout coins | Anything about other trend rules, assets, venues or fee tiers. `ensemble_vol40`'s BTC/ETH record is in-sample only |
| H2 mean reversion | The tested RSI-2 dip rules on BTC/ETH were ≈ 0 or negative after 0.66 %/side | Other dip definitions, intraday versions, lower costs |
| H3x ranking | Rotation (30/90-day momentum, top 1/3) and P1's 8 configs (top-3, daily/weekly, Coinbase, 1.32 %) did not beat costs or benchmarks | Other features, models, k, weightings, horizons, shorting, cheaper execution (P1_REPORT.md "Not shown") |
| H4 selection | Both selectors underperformed both of their own components, 2022–2026 | Other candidate sets or regime definitions |
| H5 gate | Met its test rule vs fixed allocation, but not vs the ungated baseline (P(better) 0.41), uncalibrated, 0 % CAGR at 1.25 % cost | That conditioning on state is useless in general |
| H6 macro calendar | Halving exposure 2 days before FOMC/CPI hurt the baseline | Event *content* (surprises); not tested |
| H7 S1 | No gross edge (≈ 2 bp) at 15:30 → close on S&P 100 + index ETFs, 2023-11 → 2026-10, hourly bars | Other entry times (10:00 untestable on hourly bars), other universes |
| H8 S2 | Gap reversal was real 2000–2015 on a survivorship-biased universe, ≈ 6 bp gross after; S2-ETF did not replicate on 29 new ETFs (gross −2.7 bp, 95 % upper 4.8 bp) | Measured opening-spread costs; the exploratory below-50-day-average lead (DECISION_QUALITY.md Q4) |
| H9 ORB | Paper rules on SIP stocks in play, 2020–21, lost to placebo and to direction-only; sanity gate failed (−0.22R vs +0.08R) | 2022–2026 behaviour (unread); results with intra-minute stop ordering resolved (MORNING_REPORT.md §D) |
| H10 H3 | H3-L long-only lost 24 bp/trade net in 2020–21, both years negative | 2022–2026 behaviour (unread); the short side alone (never tested as a hypothesis) |
| H11 C1 | Gross rebound ≈ 0 at ±1.5σ / 6 h on BTC/ETH/SOL and 31 holdout coins, 2024–2026 | Other exit rules (the stop destroyed ≈ 0.4 %/trade, DECISION_QUALITY.md Q3), order-book signals |
| H12 C2 | +35 bp gross is far below 1.32 %; 74 trades | Lower fee tiers; a small drift is not excluded |

---

## 7. Correction

"Three strategies tested on 2020–21" was inaccurate. The three **budget** hypotheses were P1, ORB and H3.
P1 read Coinbase data from **2021-03-01 to 2026-10-24** across development, validation and final. Only ORB
and H3 used 2020–21, and that was only their development window: their 2022–2026 windows are unread.

Accurate summary: **12 distinct economic hypotheses, 108 configurations** (105 without the 3 passive
benchmarks), 0 promoted.
- **Crypto:** read through 2026-10-24: daily 2018 →, 5-minute 2020 →, hourly cross-section 2021-03 →.
- **US stocks and ETFs (Yahoo):** read through 2026-10-23: daily 2000 →, hourly 2023-11 →.
- **US stocks in play (SIP):** 2020–21 only.

---

## 8. Inconsistencies found between records

1. **S2X end date.** `prereg_s2x` and S2X_PREREGISTRATION.md say 2016-01-01 → **2026-10-23**, and the S2X data files end 2026-10-23 (`data_inventory.json`). `s2x_test`, `s2x_test_reproduction` and the ledger say **2026-10-24**.
2. **Ledger gaps** (`consumed_data.json`). Its header says dev and validation windows are "listed where they were used for selection", but these are missing:
   - ORB/H3 development 2020-01-02 → 2021-12-31;
   - phase 1's in-sample 2018 → 2026-10-24;
   - phase-3 development and validation 2018–2023, and the holdout coins;
   - S2's 2000–2020 and S1's 2023-11-27 → 2025-08-25;
   - C1/C2 2020–2023.
3. **P1_METHODS_AND_AUDIT.md §3** merges S1/S2 and S2X into one row, 2016-01-01 → 2026-10-24. The ledger keeps them as two rows; S1/S2 run 2021-01-04 → **2026-10-23**.
4. **S3 window.** The ledger and ORB exclusion start **2026-07-27**. The Yahoo 5-minute data starts **2026-07-31** (INTRADAY_STOCKS.md, `data_inventory.json`), and S3 trades start 2026-08-20 (`intraday_stocks_explore:S3`).
5. **ORB trade count and cost label.** `dev.json` has `trades: 4058`, but the per-trade net interval and concentration use **n = 4,048**. MORNING_REPORT.md calls "4,048" a typo. The config-level `cost_path` is **"cost assumed, not measured"**, because at least one trade lacks a quote. EVIDENCE_BOARD.md and STATUS.md describe the result as measured-spread.
6. **Stale cost headers.**
   - EVIDENCE_BOARD.md's header says costs "are assumed, not measured", but its ORB/H3 rows use measured spreads.
   - COSTS.md's stock section still says no quote data was available. It does not contain the measured SIP spreads (4.0 / 10.3 / 1.5 bp) or the Alpaca crypto figure; those are only in MORNING_REPORT.md, STATUS.md and docs/ALPACA_DATA_AUDIT.md.
7. **Budget limits.** RESEARCH_BUDGET.md caps each new hypothesis at ≤ 6 development configurations. P1 (budget hypothesis 1 of 3, per MORNING_REPORT.md) used **8**. The total of 16 stayed under the 18-trial cap. The budget is titled "proposed; needs your approval", and no approval is recorded in the files read.
8. **E6 trial counts.** E6 used 96 (stocks) and 98 (crypto), built on assumed counts, while the true N at that time was 91. INTRADAY_REPORT.md acknowledges this; the verdict is unchanged.
9. **`data_inventory.json` omissions.**
   - It omits P1's hourly point-in-time data (`data/pit/hourly`, `data/p1/panel_p1*.pkl`).
   - It lists the macro calendar as "not used by any tested strategy", but `trial:calendar` / `test3:calendar` used it (RESEARCH.md §5).
10. **Stale ORB status.** RESEARCH_AUDIT.md and DATA_LIMITS.md still call ORB/S3 data-blocked or "SIP unverified". SIP access passed gates B7.1–B7.5 on 2026-10-26.
11. **Label clash.** MORNING_REPORT.md §G calls the bearish-candle short idea "C1", which collides with the crypto C1 strategy (it means item C.1).
12. **Holdout-test count.** RESEARCH_BUDGET.md lists two rejected out-of-sample replications (C1 holdout coins, S2X). It omits the earlier pre-registered `ensemble_vol40` single-asset holdout, which failed on all 3 coins (`holdout_single_assets`).
