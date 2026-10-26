# Reproducing every reported result

Requirements: Linux or macOS and Python 3.13 (see `PYTHON_VERSION`).

    tar xzf tradelab-core-*.tar.gz && tar xzf tradelab-data-*.tar.gz   # both unpack into tradelab/
    cd tradelab
    python3.13 -m venv .venv && .venv/bin/pip install -r requirements.lock
    sha256sum -c data/SHA256SUMS --quiet || echo "data differs from the archived run"
    .venv/bin/python -m pytest -q                                  # engine and research tests

| Result | Command | Output |
|---|---|---|
| Phase-1 audit (AUDIT.md) | `.venv/bin/python research/audit.py` | `research/out/audit.json` |
| Daily strategy research (RESEARCH.md) | see the command list at the top of RESEARCH.md; the test phase refuses to run twice | `research/out/` |
| Stock intraday S1–S3 (INTRADAY_STOCKS.md) | `.venv/bin/python research/intraday/stocks/study.py` (see INTRADAY_STOCKS.md for phases) | `research/intraday/stocks/out/` |
| Crypto intraday C1–C2 (INTRADAY_CRYPTO.md) | see INTRADAY_CRYPTO.md | `research/intraday/crypto/out/` |
| Engine vs research cross-checks | `.venv/bin/python research/intraday/crosscheck/stocks.py`, `.../crypto.py` | `research/intraday/crosscheck/*.json` |
| Combined multiple-testing analysis | `.venv/bin/python research/intraday/combined.py` | `research/intraday/combined.json` |

Every experiment, including failed and crashed runs and pre-registrations written before results, is in
`research/registry.jsonl`, in chronological order. `INTRADAY_REPORT.md` lists what was seen before each
subsequent change.

Paper trading only. No component places real orders: no live venue adapter exists, and the paper processes refuse
to start if live credentials are present in the environment.
