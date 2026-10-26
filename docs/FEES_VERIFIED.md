# Fee schedules: what was verified from official sources

Checked 2026-10-26 unless a row says otherwise. Only official pages count: the venue's own site, docs, or
disclosure PDFs, and sec.gov / finra.org for regulatory fees. Third-party figures appear only to show why a
row is still unverified.

- **VERIFIED**: read on the official page on the date shown.
- **UNVERIFIED**: the official page could not be read. The figure in use is an assumption.

## Summary

| Venue / item | Product | Small account (lowest tier) maker / taker | Larger tiers (examples) | Status | Source |
|---|---|---|---|---|---|
| **Coinbase Advanced** | Spot crypto | **Unknown.** COSTS.md assumes 0.40% / 0.60% | Unknown | **UNVERIFIED** | Every official fee page returned HTTP 403 to automated access (2026-10-25 and 2026-10-26). See the Coinbase section |
| Kraken Pro | Spot crypto | **0.40% / 0.80%** ($0+) | $10K+: 0.22/0.38; $100K+: 0.12/0.25; $1M+: 0.06/0.18; $10M+: 0.00/0.10 | **VERIFIED** | https://www.kraken.com/features/fee-schedule |
| Kraken Pro | Stablecoin / FX pairs | 0.20% / 0.20% | $100K+: 0.12/0.12; $1M+: 0.02/0.02 | **VERIFIED** | same |
| Alpaca Crypto | Spot crypto | **0.15% / 0.25%** (0–$100K) | $1M–10M: 0.08/0.18; $100M+: 0.00/0.10 | **VERIFIED** (docs page) | https://docs.alpaca.markets/docs/crypto-fees (page "last updated 2025-09-24") |
| Alpaca Securities | US stocks/ETFs, commission | **$0** for retail self-directed | Elite Smart Router: $0.0025→$0.0015/share cost-plus, or $0.0040 all-in | **VERIFIED** | Brokerage Fee Schedule PDF, "Revised on October 12, 2026": https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf |
| SEC Section 31 fee | Stock sells only | **$20.60 per $1M** (0.206 bp) | n/a | **VERIFIED** (checked 2026-10-25) | https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2 . Alpaca's schedule shows the same rate: "$0.0000206 * Trade Value, When sells only" |
| FINRA TAF as Alpaca charges it | Stock sells only | **$0 per share** | n/a | **VERIFIED** (Alpaca schedule) | Alpaca Brokerage Fee Schedule (above) |
| FINRA TAF as FINRA bills its members | Covered equity sales | $0.000166/share, max $8.30/trade | n/a | **UNVERIFIED as current.** The footnote was read, but the page did not say which effective-date version it belongs to | https://www.finra.org/rules-guidance/rulebooks/corporate-organization/section-1-member-regulatory-fees |
| FINRA CAT fee (via Alpaca) | Stock buys and sells | $0.000003 per executed equivalent share | n/a | **VERIFIED** (Alpaca schedule) | Alpaca Brokerage Fee Schedule |
| Alpaca short borrow | Stocks | Easy-to-borrow: free. Hard-to-borrow: locate fee and daily borrow rate vary by security | n/a | **VERIFIED** (Alpaca schedule) | Alpaca Brokerage Fee Schedule |

## Coinbase Advanced (the venue our crypto research assumes)

**Status: UNVERIFIED.** Automated requests to all of these returned HTTP 403:
- https://www.coinbase.com/advanced-fees
- https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees
- https://help.coinbase.com/en/coinbase/trading-and-funding/pricing-and-fees/fees

Third-party reports conflict: 0.60/0.40, 0.90/0.50 and 1.20/0.60 taker/maker for small accounts. They are listed
in COSTS.md and are **not** treated as facts here.

**Your own account's fee tier is the only authoritative number.** Coinbase's tier is not purely a public table.
The official API schema (below) includes tiers qualified by **assets on platform** (`aop_from` / `aop_to`) and
promotional rates (`fee_tier_without_promotion`). Two accounts can therefore see different rates.

### What the official API documentation says (VERIFIED, 2026-10-26)

Source: https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/fees/get-transaction-summary
and the scope table at https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-scopes

- `GET https://api.coinbase.com/api/v3/brokerage/transaction_summary`: "Get a summary of transactions with fee tiers, total volume, and fees."
- Optional query `product_type`: `SPOT`, `FUTURE`, and others. The default returns all product types.
- Required API-key scope: **`view`**, the read-only scope. It does not need `trade` or `transfer`.
- The response's `fee_tier` object contains `pricing_tier` (e.g. "<$10k"), `maker_fee_rate`, `taker_fee_rate`
  (decimal strings, e.g. "0.0020"), `aop_from` and `aop_to`. The response also has `total_volume`, `total_fees`,
  `has_cost_plus_commission` and `fee_tier_without_promotion`.
- The official Python SDK (`coinbase-advanced-py`) wraps this as `RESTClient.get_transaction_summary()`. It reads
  `COINBASE_API_KEY` and `COINBASE_API_SECRET` from the environment (SDK README on github.com/coinbase).

### How to read your tier without sharing any secret

**Option A (recommended: no key at all).** Sign in at coinbase.com in your own browser and open your Advanced
trading fee page or fee-tier display. Tell me only three numbers: the tier name, the maker rate and the taker
rate. These are not secrets. I could not verify where the display sits in the signed-in interface, because those
pages were blocked to me.

**Option B (API, view-only).**
1. In the Coinbase Developer Platform, create an API key with **View** permission only. Leave Trade and Transfer
   unticked. Coinbase Advanced has no paper environment, so this key belongs to your real account. View-only
   scope means it can read balances and history, but it cannot place orders or move funds.
2. Do not paste the key or secret into chat, a file or a commit. Add them in the cloud environment settings as
   environment secrets named `COINBASE_API_KEY` and `COINBASE_API_SECRET`. Start a new session afterwards.
3. In that session, run this command. It prints only the tier and rates, never the key:

        .venv/bin/pip install coinbase-advanced-py
        .venv/bin/python -c "from coinbase.rest import RESTClient; r=RESTClient().get_transaction_summary(product_type='SPOT'); d=r.to_dict() if hasattr(r,'to_dict') else r; t=d['fee_tier']; print(t['pricing_tier'], 'maker', t['maker_fee_rate'], 'taker', t['taker_fee_rate'])"

4. Delete the key in the Coinbase Developer Platform once the numbers are recorded, unless it is needed again.

Once the numbers are known, update COSTS.md and re-state the crypto cost basis (currently 0.66% per taker
side, 1.32% round trip). Every crypto result in EVIDENCE_BOARD.md depends on it.

## Notes and caveats

- **Kraken's fee page today** matches the 2026-10-25 check (0.40% / 0.80% at the lowest tier).
- **Alpaca Crypto PDF.** https://files.alpaca.markets/disclosures/library/AlpacaCryptoLLCFeeDisclosure.pdf
  ("Revised on Jul 17, 2026") says Alpaca Crypto uses "a maker/taker volume-tiered Fee schedule", but its table is
  an image that could not be extracted. The figures above come from the docs page, which is dated 2025-09-24. If
  the two disagree, the PDF is the later document. The PDF also lists a withdrawal fee of 0.02% plus network fees.
- **Alpaca crypto fees** are "charged on the credited crypto asset/fiat (what you receive)" and are "calculated
  and posted end of day" (docs page).
- **Alpaca regulatory-fee page** https://docs.alpaca.markets/docs/regulatory-fees (updated 2025-10-03) lists only
  TAF and CAT for equities and defers rates to the fee schedule. The October 2026 schedule PDF is the later
  document and adds the SEC fee.
- **Alpaca commission exceptions.** Commissions apply to index options, the Elite Smart Router, and order flow
  "determined to be non-retail in nature". Alpaca "reserves the right to charge additional fees if it is
  determined that the orders' flow is non-retail in nature."
- **Spreads and slippage are not fees.** Nothing here measures them. Stock spreads remain an assumption until
  consolidated quotes (Alpaca SIP) are verified (docs/ALPACA_DATA_AUDIT.md).
