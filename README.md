# Tradelab

A trading research and paper-trading system for crypto (Coinbase) and US stocks/ETFs. Long-only by default, no leverage.
**Paper mode only. No real orders can be placed. No strategy has demonstrated an advantage, and none is
live-eligible (`tradelab/governance/status.py`).**

Start here:
- `EVIDENCE_BOARD.md`: one-table status of every strategy (software / historical / forward / live-eligible)
- `RESEARCH_AUDIT.md`, `DECISION_QUALITY.md`, `LATENCY.md`, `INTELLIGENCE_POLICY.md`, `RESEARCH_BUDGET.md`
- `ORB_PREREGISTRATION.md`, `S2X_PREREGISTRATION.md`, `docs/ALPACA_DATA_AUDIT.md`, `docs/CREDENTIALS_SETUP.md`
- `INTRADAY_REPORT.md`: combined intraday results (passed / rejected / inconclusive / untestable), cross-checks, chronology, next step
- `COSTS.md`, `DATA_LIMITS.md`, `docs/S1_TIMING.md`: cost reconciliation, data limits, S1 timing
- `PROVENANCE.md`, `REPRODUCE.md`: where every dataset came from; how to reproduce every result
- `AUDIT.md`: what the phase-1 bot's results actually show
- `RESEARCH.md`: every strategy tested, with pre-registered results
- `ARCHITECTURE.md`: components, hosting, costs, what's missing, and the evidence needed before real money
- `docs/LIVE_DATA.md`, `docs/EVENTS.md`: market-data and news/event pipelines

## Run

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m pytest -q                         # full suite
    .venv/bin/python -m tradelab.service.daily            # one daily paper cycle (idempotent per UTC day)
    .venv/bin/python -m tradelab.dashboard.build          # data/dashboard/index.html
    .venv/bin/python -m tradelab.service.monitor          # always-on live monitor (Ctrl-C to stop)
    .venv/bin/python scripts/events_ingest.py --fill-outcomes
    .venv/bin/python research/audit.py                    # reproduce the audit

## Layout

| Path | Contents |
|---|---|
| `legacy/` | Phase-1 bot, frozen (hashes in `legacy/SHA256SUMS`) |
| `tradelab/data` | Point-in-time candles, live WebSocket feeds, recorder |
| `tradelab/strategies` | Strategy specs with written hypotheses |
| `tradelab/research` | Engine, statistics, registry, walk-forward, gate |
| `tradelab/risk` | Hard limits and circuit breakers |
| `tradelab/execution` | Orders, journal, paper venue, accounting, secrets |
| `tradelab/events` | News, economic and geopolitical event pipeline |
| `tradelab/governance` | Drift monitors and promotion checks |
| `tradelab/service` | Daily runner, live monitor, strategy registry |
| `config/` | `paper.toml` (risk limits) and `strategies.lock` (approved strategy versions) |
| `research/` | Studies, `registry.jsonl` (every experiment) and outputs |
| `deploy/systemd`, `.github/workflows` | Always-on host units; CI and daily paper workflow |
