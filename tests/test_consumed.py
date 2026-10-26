import json

import pytest

from tradelab.research import consumed


def test_overlap_raises_for_related_scopes_and_marking_is_idempotent(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"entries": []}))
    consumed.mark_consumed("crypto.coinbase.cross_section", "2021-03-01", "2026-10-24", "P1", path=p)
    consumed.mark_consumed("crypto.coinbase.cross_section", "2021-03-01", "2026-10-24", "P1", path=p)
    assert len(consumed.load(p)) == 1
    with pytest.raises(consumed.ConsumedDataError):
        consumed.check_selection_window("crypto.coinbase", "2024-01-01", "2024-06-30", path=p)        # parent scope
    with pytest.raises(consumed.ConsumedDataError):
        consumed.check_selection_window("crypto.coinbase.cross_section.weekly", "2026-10-01", "2026-12-31", path=p)
    consumed.check_selection_window("crypto.coinbase.cross_section", "2026-10-25", "2027-06-30", path=p)  # prospective: fine
    consumed.check_selection_window("stocks.us.intraday.orb", "2016-01-04", "2019-12-31", path=p)        # other scope: fine


def test_repository_ledger_marks_p1_as_consumed():
    with pytest.raises(consumed.ConsumedDataError):
        consumed.check_selection_window("crypto.coinbase.cross_section", "2025-07-01", "2026-10-24")
