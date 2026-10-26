"""Sanity checks on the committed calendar built from official pages."""
from collections import Counter
from datetime import datetime

import pytest

from tradelab.events import calendar as cal

pytestmark = pytest.mark.skipif(not cal.CAL_PATH.exists(), reason="calendar not built")


def test_every_row_cites_an_official_page():
    for r in cal.load():
        assert (r.source_url or r.index_url).startswith(("https://www.federalreserve.gov", "https://www.bls.gov"))


def test_coverage_and_release_times():
    rows = cal.load()
    fomc = Counter(r.release_utc[:4] for r in rows if r.kind == "fomc_decision")
    assert all(fomc[str(y)] == 8 for y in range(2018, 2027) if y != 2020) and fomc["2020"] == 7
    for r in rows:
        if r.kind in ("cpi_release", "nfp_release") and r.release_utc:
            assert datetime.fromisoformat(r.release_utc).strftime("%H:%M") in ("12:30", "13:30")   # 8:30 ET
        if r.kind == "fomc_decision" and r.release_utc and "assumed" not in r.release_local:
            assert r.release_local.startswith("2:00 p.m.")
    assert not any(r.known_in_advance for r in rows if r.kind == "fomc_unscheduled")
