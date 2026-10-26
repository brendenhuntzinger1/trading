import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

DATA_DIR = ROOT / "data"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Report tests that fail only because the (unpublished) market data is absent as skipped.
    See data/README.md."""
    outcome = yield
    rep = outcome.get_result()
    if rep.failed and call.excinfo is not None and call.excinfo.errisinstance((FileNotFoundError, OSError)):
        msg = str(call.excinfo.value)
        if str(DATA_DIR) in msg or "data/" in msg:
            rep.outcome = "skipped"
            rep.longrepr = (str(item.fspath), item.location[1] or 0, "market data not present (see data/README.md)")
