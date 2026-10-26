# ORB mechanics audit, 2026-10-26 (development days 2020-01-02, 2020-01-03, 2020-01-06)

`research/orb/audit_mechanics.py` recomputed every primary-rule trade from the raw 1-minute SIP bars with
separate code.
- **Trades checked:** 31.
- **Real mismatches:** 0.
- **Label-only differences:** 15. The harness labels stops `stop_same_minute` and `stop_gap`; the audit
  says `stop`. The script now normalises them.

**What agreed on every trade:**
- the first-candle direction;
- the entry price, including gap-through fills at the bar open;
- the exit price;
- the stop logic, assuming the stop was hit first when entry and stop fall in the same minute;
- no entry before 09:35;
- the filters as known at 09:35: open > $5, ADV14 ≥ 1M, ATR14 > $0.50, RV ≥ 1.

**Abstentions on these three days (primary, long-only):**
- 26 bearish first candles skipped (long-only);
- 2 armed but never triggered;
- 1 doji;
- 1 symbol without an opening bar.

**Limit:** the audit shares the harness's data source, so it checks the code path, not the data. The data
itself was checked by gates B7.1–B7.5.
