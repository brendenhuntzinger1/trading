from tradelab.data.live.derivatives import funding_history, perp_snapshots


def test_perp_snapshot_parsing_and_research_flag():
    fake = {"tickers": [{"symbol": "PF_XBTUSD", "markPrice": 101.0, "indexPrice": 100.0, "relativeFundingRate": 1e-5,
                         "openInterest": 5.0, "lastTime": "2026-10-25T18:13:03.843017267Z", "suspended": False}]}
    (p,) = perp_snapshots(("BTC-USD",), fetch=lambda u: fake)
    assert p.research_only and round(p.basis, 6) == 0.01 and round(p.funding_rate_annualized, 4) == 0.0876


def test_suspended_contract_skipped():
    fake = {"tickers": [{"symbol": "PF_XBTUSD", "markPrice": 1, "indexPrice": 1, "suspended": True}]}
    assert perp_snapshots(("BTC-USD",), fetch=lambda u: fake) == []


def test_funding_history_parse():
    fake = {"rates": [{"timestamp": "2025-10-15T08:00:00Z", "relativeFundingRate": 6.8e-06}]}
    (t, r), = funding_history("BTC-USD", fetch=lambda u: fake)
    assert t.hour == 8 and r == 6.8e-06
