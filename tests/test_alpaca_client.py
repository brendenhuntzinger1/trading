"""Alpaca client guard-rails: read-only endpoints only, retries, rate limit, paper host, as-of helpers,
and the data-gate script's behaviour without credentials. Synthetic transports only (no network, no key)."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradelab.pit import alpaca_sip as al


def _client(responses, **kw):
    calls, sleeps = [], []
    it = iter(responses)

    def transport(url, headers):
        calls.append(url)
        return next(it)
    c = al.AlpacaData("k", "s", transport, sleep=sleeps.append, clock=lambda: 0.0, **kw)
    return c, calls, sleeps


@pytest.mark.parametrize("url", [f"{al.PAPER_URL}/orders", f"{al.PAPER_URL}/orders?status=all", f"{al.PAPER_URL}/positions",
                                 f"{al.PAPER_URL}/positions/AAPL", f"{al.PAPER_URL}/watchlists",
                                 f"{al.PAPER_URL}/account/configurations", f"{al.LIVE_URL}/orders",
                                 "https://example.com/v2/stocks/bars?symbols=SPY"])
def test_trading_and_unknown_endpoints_are_refused_before_any_request(url):
    c, calls, _ = _client([(200, {})])
    with pytest.raises(al.ForbiddenEndpoint):
        c._get(url)
    assert calls == []


def test_market_data_endpoints_are_allowed():
    for url in (f"{al.DATA_URL}/bars?symbols=SPY", f"{al.DATA_URL}/quotes?symbols=SPY", f"{al.PAPER_URL}/assets?asset_class=us_equity"):
        al.check_endpoint(url)


def test_retries_429_and_5xx_with_backoff_then_succeeds():
    c, calls, sleeps = _client([(429, {}), (503, {}), (200, {"ok": 1})])
    assert c._get(f"{al.DATA_URL}/bars?x=1") == (200, {"ok": 1})
    assert len(calls) == 3 and sleeps == [1.0, 2.0]


def test_rate_limit_spaces_calls():
    t = [0.0]
    sleeps = []
    c = al.AlpacaData("k", "s", lambda u, h: (200, {}), min_interval=0.31, sleep=lambda s: sleeps.append(s), clock=lambda: t[0])
    c._get(f"{al.DATA_URL}/bars?a=1")
    c._get(f"{al.DATA_URL}/bars?a=2")
    assert sleeps and sleeps[0] == pytest.approx(0.31)


def test_from_env_requires_paper_host_and_no_live_keys(monkeypatch):
    monkeypatch.setenv("TRADELAB_PAPER_APCA_API_KEY_ID", "k")
    monkeypatch.setenv("TRADELAB_PAPER_APCA_API_SECRET_KEY", "s")
    monkeypatch.setenv("TRADELAB_PAPER_APCA_BASE_URL", "https://api.alpaca.markets")
    with pytest.raises(RuntimeError, match="paper host"):
        al.AlpacaData.from_env()
    monkeypatch.setenv("TRADELAB_PAPER_APCA_BASE_URL", "https://paper-api.alpaca.markets")
    assert al.AlpacaData.from_env().min_interval > 0
    monkeypatch.setenv("TRADELAB_LIVE_APCA_API_KEY_ID", "x")
    with pytest.raises(RuntimeError, match="live"):
        al.AlpacaData.from_env()


def test_sip_requests_must_be_15_minutes_old():
    now = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        al.require_old_enough(now - timedelta(minutes=5), now)
    al.require_old_enough(now - timedelta(minutes=20), now)


def test_as_of_filters_bars_by_end_and_parses_nanoseconds():
    rows = [{"t": "2024-07-15T13:34:00Z"}, {"t": "2024-07-15T13:35:00Z"}]
    as_of = datetime(2024, 7, 15, 13, 35, tzinfo=timezone.utc)
    assert [r["t"] for r in al.available_bars(rows, as_of)] == ["2024-07-15T13:34:00Z"]
    t = al.parse_ts("2024-07-15T13:30:00.123456789Z")
    assert t == datetime(2024, 7, 15, 13, 30, 0, 123456, tzinfo=timezone.utc)


def test_bars_multi_merges_pages_and_assets_lists_inactive():
    c, calls, _ = _client([(200, {"bars": {"A": [{"t": 1}], "B": [{"t": 1}]}, "next_page_token": "p"}),
                           (200, {"bars": {"A": [{"t": 2}]}, "next_page_token": None}),
                           (200, [{"symbol": "A", "status": "active"}, {"symbol": "OLD", "status": "inactive"}])])
    st, out = c.bars_multi(["A", "B"], "2024-01-02", "2024-01-03")
    assert st == 200 and len(out["A"]) == 2 and len(out["B"]) == 1 and "page_token=p" in calls[1]
    st, assets = c.assets()
    assert {a["status"] for a in assets} == {"active", "inactive"} and "status=" not in calls[2]


def test_verify_script_without_credentials_exits_2_and_writes_nothing(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("pv", Path(__file__).resolve().parents[1] / "scripts" / "pit_verify_alpaca.py")
    pv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pv)
    doc = tmp_path / "audit.md"
    assert pv.main([], env={}, out_dir=tmp_path / "out", audit_doc=doc) == 2
    assert not (tmp_path / "out").exists() and not doc.exists()
    assert "Nothing was run" in capsys.readouterr().out


def test_bars_multi_skips_non_tickers_and_drops_symbols_alpaca_rejects():
    from tradelab.pit.alpaca_sip import AlpacaData, is_ticker
    assert is_ticker("BRK.B") and is_ticker("SPY")
    assert not is_ticker("021CVR014") and not is_ticker("TWTR_DELISTED")
    sent = []

    def transport(url, headers):
        sent.append(url)
        if "BADX" in url:
            return 400, {"message": "invalid symbol: BADX"}
        return 200, {"bars": {"SPY": [{"t": "2023-01-03T05:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]}}

    c = AlpacaData("k", "s", transport=transport)
    st, out = c.bars_multi(["SPY", "BADX", "021CVR014"], "2023-01-01", "2023-01-05", timeframe="1Day")
    assert st == 200 and list(out) == ["SPY"] and c.rejected_symbols == {"BADX"}
    assert all("021CVR014" not in u for u in sent)


def test_transport_errors_are_retried_not_fatal(monkeypatch):
    import urllib.error
    from tradelab.pit import alpaca_sip
    from tradelab.pit.alpaca_sip import AlpacaData, http_get

    def refuse(req, timeout=30):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    monkeypatch.setattr(alpaca_sip.urllib.request, "urlopen", refuse)
    st, body = http_get("https://data.alpaca.markets/v2/stocks/bars?symbols=SPY", {})
    assert st == 599 and "transport" in body["message"]

    calls = []
    def flaky(url, headers):
        calls.append(url)
        return (599, {}) if len(calls) < 3 else (200, {"bars": {}})
    c = AlpacaData("k", "s", transport=flaky, sleep=lambda s: None)
    st, _ = c._get("https://data.alpaca.markets/v2/stocks/bars?symbols=SPY")
    assert st == 200 and len(calls) == 3


def test_news_is_a_read_only_data_endpoint_and_is_paged():
    al.check_endpoint(f"{al.NEWS_URL}?symbols=AAPL&start=2024-01-01")
    pages = iter([(200, {"news": [{"id": 1, "headline": "a", "symbols": ["AAPL"], "created_at": "2024-01-02T13:00:00Z"}],
                         "next_page_token": "t"}),
                  (200, {"news": [{"id": 2, "headline": "b", "symbols": ["AAPL"], "created_at": "2024-01-03T13:00:00Z"}],
                         "next_page_token": None})])
    c, calls, _ = _client(list(pages))
    st, rows = c.news(["AAPL"], "2024-01-01", "2024-01-05")
    assert st == 200 and [r["id"] for r in rows] == [1, 2] and len(calls) == 2
    assert all(u.startswith(al.NEWS_URL) for u in calls)
