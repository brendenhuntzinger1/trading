# Trading costs: one reconciled table

Status key: **V** = verified from the provider's own page or a primary regulator source (date checked);
**S** = secondary sources only; **A** = assumption with no source. Every A and S figure is a reason to verify
before a live trial.

## Crypto: Coinbase Advanced (retail spot product; the same order book as the public Coinbase Exchange feed)

| Component | Per side | Status | Note |
|---|---|---|---|
| Taker fee, lowest tier | **0.60%** (used) | **S, conflicting** | Third-party reports: 0.60% taker / 0.40% maker ($0–10k, most common); 0.90% / 0.50% (one Oct-2026 source says US repricing Sep 2026); 1.20% / 0.60% (< $1k "intro" tier). Coinbase's fee page blocked automated access twice (2026-10-25). Check the fee page in your own account. |
| Maker fee, lowest tier | 0.40% (used) | S, conflicting | As above. |
| Half-spread (taker crosses it) | 0.01% (1 bp) | A, consistent with measurements | Measured live on 2026-10-25: BTC-USD 0.001 bp, ETH-USD 0.2–0.55 bp. Alts are wider; this was not measured for them. |
| Slippage / impact ($10–$250 orders) | 0.05% (5 bp) | A | Depth within 10 bp was $2–7M on BTC/ETH (measured), so impact at this size should be far below 5 bp. 5 bp is a conservative pad. |
| **Taker, all-in per side** | **0.66%** = 0.60 + 0.01 + 0.05 | derived | The "0.66%" used in AUDIT/RESEARCH/INTRADAY docs. |
| **Taker round trip** | **1.32%** = 2 × 0.66% | derived | The "about 1.3%" in INTRADAY docs. Earlier text called this "fees". It is fees **plus** spread and slippage. |
| Maker entry + taker exit round trip | 1.06% = 0.40 + 0.66 | derived | Used for C1's maker variant. Maker fills also carry adverse selection and missed fills, which only a live order book can measure. |

**The 0.66% figure and the 1.3% figure are the same assumption.** 0.66% is the cost of one side (buy or
sell); 1.32% is the cost of buying and then selling. Nothing changed between them.

**Figures that were wrong and are corrected:** phase 1 used 0.45% per side (0.40% + 0.05% slippage, labelled
Kraken). Kraken Pro's published lowest tier is 0.40% maker / **0.80% taker** (**V**, kraken.com fee page,
checked 2026-10-25), so phase 1 understated taker costs. AUDIT.md shows the corrected figures (Kraken taker
all-in 0.86%).

### Plausible crypto round-trip range used for sensitivity

| Scenario | Round trip |
|---|---|
| Maker both sides at 0.40% (optimistic; assumes every limit order fills) | ~0.80% |
| Maker in / taker out at the 0.60/0.40 tier | 1.06% |
| Taker both sides at 0.60% (base) | 1.32% |
| Taker 0.60% + 0.15% extra slippage per side (pre-registered stress) | 1.62% |
| Taker both sides at 0.90% (reported Sep-2026 repricing) | ~1.92% |
| Taker both sides at 1.20% (< $1k tier report) | ~2.52% |

## US stocks and ETFs (broker assumed: a commission-free API broker such as Alpaca; not selected or opened)

| Component | Per side | Status | Note |
|---|---|---|---|
| Commission | $0 | S | Alpaca's site says commission-free for self-directed accounts; the fee schedule was not retrieved. |
| SEC Section 31 fee (sells only) | 0.21 bp ($20.60 per $1M) since 2026-04-04; $0 before | **V** | SEC Fee Rate Advisory 2026-2 and Release 34-104909. Included inside the exit cost below. |
| FINRA TAF (sells only) | ≈ $0.000166/share, capped | S (rate not re-checked) | Negligible at these sizes (< 0.01 bp on a $50+ stock). |
| Half-spread + slippage, intraday market order (entry) | **5 bp** base / 15 stress / 10 sensitivity (S2) | A | Large caps and major ETFs typically quote 1–2 bp spreads, but opening minutes are wider. No quote data was available to measure it. |
| Closing auction (MOC) exit | **3 bp** base / 9 stress | A | The auction itself has no spread; 3 bp covers auction price impact plus regulatory fees. |
| **Round trip, base** | **8 bp** (5 + 3) | derived | S1 and S2 after Amendment 1. Before the amendment S2 was 6 bp (3 + 3), but no S2 test result used that. |
| Round trip, stress | 24 bp (15 + 9) | derived | |

## Sensitivity of every intraday test result to cost

`research/intraday/cost_sensitivity.json` recomputes each test-period trade list from its **gross** returns
across round-trip costs (stocks 0–30 bp; crypto 36–240 bp). The combined report (INTRADAY_REPORT.md) quotes
the break-even round trip for each strategy. A strategy whose break-even sits inside the plausible cost range
is not robust to cost uncertainty.

## Not modelled anywhere

- Taxes. In the US every sale is a taxable event; short-term gains are taxed as income. This is not tax advice.
- Funding and transfer costs, such as bank deposits, crypto network fees and card fees.
- Operating costs, which ARCHITECTURE.md handles separately (hosting, data, LLM).
