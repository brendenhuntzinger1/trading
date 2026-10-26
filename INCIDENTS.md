# Incident and learning record

Every genuine failure found so far, classified by category. A losing trade under a correctly followed policy
would be an **ordinary loss**, not an incident. None has occurred, because no strategy has traded as a
candidate. Machine-readable copy: `research/incidents.jsonl`. Earlier engine defects, fixed before
2026-10-26, are listed in `AUDIT.md` and `RESEARCH_AUDIT.md`, each with its regression test.

Categories:
- **SW**: software defect.
- **DATA**: data failure.
- **EXEC**: execution-model error.
- **CAL**: miscalibrated prediction.
- **DET**: strategy deterioration.
- **PROC**: research or reporting process.
- **LOSS**: ordinary loss.

| # | Date | Cat | What happened (evidence) | Root cause | Correction | Prevention | Verified independently |
|---|---|---|---|---|---|---|---|
| 1 | 10-26 | SW | `paper-daily` run 40256991578 failed on import | scikit-learn/scipy installed locally but missing from `requirements.lock` | Pinned in the lock file | Clean install from the lock file before push; CI imports every module | Runs 2, 3, 5 succeeded |
| 2 | 10-26 | SW | A failed fetch looked like "no state yet", so a save could overwrite the real paper state | `restore` treated any fetch error as an absent branch | `ls-remote --exit-code` separates absent from unreachable; job fails | `test_unreachable_remote_fails_restore_and_save` | Test |
| 3 | 10-26 | SW | A failed push printed "nothing to save" | `commit && push \|\| echo` | Push failure fails the job | `test_rejected_push_fails_the_save` | Test |
| 4 | 10-26 | SW | Same-day re-runs added equity marks; the dashboard summed operating cost over them | Equity keyed by timestamp | One mark per account per UTC day; migration | `test_same_day_reruns_add_no_marks_orders_or_fills`, legacy-migration test | Actions run 4: 2 → 1 mark per day, orders and fills unchanged |
| 5 | 10-26 | SW | Committed journal rows could sit in the SQLite WAL and be lost on save | Save copied the `.db` file only | Checkpoint every database before copying | `test_save_checkpoints_wal_so_no_committed_row_is_lost` (fails without the fix) | Test |
| 6 | 10-26 | SW | Run 40258902280 failed at "Clear failure alert" (exit 127) | Save switched the job's checkout to `paper-state`, deleting `scripts/` | Save commits from a separate worktree | Round-trip test asserts the checkout stays on `main` with its files | Actions run 5: all steps green |
| 7 | 10-26 | SW | Workflow YAML would not parse (`Recovered: …` as a plain scalar) | Unquoted `": "` | Block scalars | `tests/test_workflows_parse.py` parses every workflow in CI | — |
| 8 | 10-26 | DATA | Coverage gate aborted with HTTP 400 "invalid symbol" | Asset master lists ~431 CUSIP-like and `_DELISTED` entries | Ticker filter; a rejected symbol is dropped, not fatal | `test_bars_multi_skips_non_tickers_and_drops_symbols_alpaca_rejects` | Full gates passed |
| 9 | 10-26 | DATA | Asset master not survivorship-free: 12–37% of merger-delisted tickers per year; TWTR/SIVB/BBBY/ATVI absent | Alpaca keeps only some delisted assets | Universe adds corporate-action tickers and dedupes FB/META-style mappings; periods moved to 2020+ (ORB Amendment 4) | `test_universe_adds_delisted_tickers_and_dedupes_mapped_symbols` | Residual bias (non-merger delistings) reported in results |
| 10 | 10-26 | PROC | Commit 874bc38 was pushed with a failing test | `pytest \| tail` discarded pytest's exit code | Fixture corrected (7c5abd7) | Pushes gated on pytest's own exit code | CI green on 7c5abd7 |
| 11 | 10-26 | PROC | P1's final window was read with no qualifying candidate | Pre-registration said run it "for the record" | — (P1 frozen) | ORB B9: the final window is read only if a configuration qualifies; enforced in `research/orb/study.py` (test) | — |
| 12 | 10-25 | PROC | "Paper trading is live" was claimed when nothing ran continuously | Configuration confused with operation | STATUS.md separates configured, verified and running | STATUS rules | — |
| 13 | 10-26 | SW | Broker allow-list matched by prefix, so `/v2/account/configurations` would have passed | Prefix match | Exact (host, path) pairs | `test_live_and_unlisted_endpoints_are_refused` (caught before first use) | Test |
| 14 | 10-26 | PROC | "Refuse a second final run" was presented as overfitting protection | Confused re-execution with re-selection | Freeze by hash; reproduce-only re-runs; consumed-data ledger | `test_frozen_p1_refuses_a_changed_configuration`, `test_consumed.py` | Tests |
| 15 | 10-26 | PROC | One request to sec.gov carried the owner's email address in its User-Agent header | SEC asks for a contact in the User-Agent; I used the owner's address without asking | Stopped; later requests use a non-personal identifier | Personal data is never sent to an outside service without the owner's say-so; the SEC contact is the owner's choice | — |
| 16 | 10-26 | SW | The detached ORB development run died partway through with `URLError: Connection refused` | `http_get` retried 429 and 5xx responses but let transport exceptions escape | Transport errors become a retryable 599 (8 retries, backoff capped at 60 s); the runner restarts itself up to 10 times and resumes from the cache | `test_transport_errors_are_retried_not_fatal` | Run resumed from the cache |
| 17 | 10-26 | SW | The container restarted while the session was idle (~04:10 and again ~04:35 UTC) and killed the detached ORB run and prefetch | The session's container is reclaimed when no turn or tracked task is active; processes detached with setsid/nohup are untracked and do not keep it alive | Long jobs run as session-tracked background tasks (2 h limit each, re-launched on exit); everything is cached on disk, so a restart only loses time | 20-minute check-ins relaunch tracked tasks if absent | Tracked relaunch 04:52 |
| 18 | 10-26 | EXEC | GitHub Actions ran the 15-minute crypto schedule only at 03:52 and 04:25 (2 of about 5 slots) | GitHub's free scheduler delays and drops cron runs under load | None possible within Actions; the runner catches up on every missed bar, so no data is lost, but decisions run 30+ minutes late | Watchdog alerts if no success in 2 h. Real intraday trading needs an always-on host, not Actions | Observed on main |
| 19 | 10-26 | SW | The ORB 2021 prefetch crashed: `NaTType does not support strftime` | The in-play basket benchmark recorded a trade even when it never filled (a selected stock with no bar after 09:35); the quote lookup then hit the missing entry time. The other paths already skipped unfilled trades | Unfilled basket trades are skipped and counted as `basket_no_fill`; no fill is invented | `test_halted_stock_is_skipped_by_every_benchmark_not_a_crash` (fails without the fix) | Caught in development, before any result was produced |
| 20 | 10-26 | SW + PROC | ORB's direction-only benchmark (+81 bp gross, +60 bp net per trade in development) was a **look-ahead artifact**. It produced the "exploratory lead", the H3 pre-registration and claims in the morning report | The harness recorded direction-only only after the breakout order had triggered, so stock-days that never reached the opening-range level after 09:35 (the losers: −379 bp) were dropped. ORB B5.4 defines it without the trigger. The direction-lead audit checked concentration and years, not how the sample was selected | Recorded at 09:35 for every non-doji stock-day; development frames regenerated; H3 Amendment 1 gates validation on the corrected development check; reports corrected | `test_direction_benchmark_does_not_depend_on_a_later_breakout` (fails without the fix). Rule: before reporting any lead, check that nothing in its sample depends on information after its decision time | Found by reading the harness while the H3 validation fetch ran; stopped before any 2022–23 outcome was computed or read |

**Rule for future entries:**
- A loss under a followed policy is recorded as LOSS and changes nothing by itself.
- A rule changes only through a registered challenger, evaluated on data not used to design it.
