import pytest
from tradelab.execution.accounting import pnl


def test_realized_and_unrealized_split():
    p = pnl([("buy", 1.0, 100.0, 1.0), ("buy", 1.0, 120.0, 1.0), ("sell", 1.0, 130.0, 1.0)], mark=140.0)
    # avg cost (100+1+120+1)/2 = 111 -> realized 130-111-1 = 18; 1 left at 111 -> unrealized 29
    assert p.realized == pytest.approx(18.0)
    assert p.unrealized == pytest.approx(29.0)
    assert p.fees == pytest.approx(3.0) and p.qty == pytest.approx(1.0)


def test_flat_position_has_no_unrealized():
    p = pnl([("buy", 2.0, 50.0, 0.5), ("sell", 2.0, 40.0, 0.5)], mark=999.0)
    assert p.unrealized == 0 and p.realized == pytest.approx(-21.0)
