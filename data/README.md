# Data (not in this repository)

This repository is public. Raw market data is **not** committed:
- Yahoo's unofficial endpoint has terms that restrict redistribution.
- The full set is about 176 MB compressed.
- Paper-trading journals are runtime state.

Stock trade lists containing Yahoo-derived prices are excluded for the same reason. Their summaries (JSON) and
all crypto trade lists are included.

To reproduce exactly, use the data archive (`tradelab-data-*.tar.gz`) produced by `scripts/make_archive.py`
and verify it against `data/SHA256SUMS`, which lists every file used. Without it, re-download from the
sources in `PROVENANCE.md`. Providers revise history, so a re-download will not be byte-identical.

Tests that need this data are **skipped**, not failed, when it is absent (`tests/conftest.py`).
