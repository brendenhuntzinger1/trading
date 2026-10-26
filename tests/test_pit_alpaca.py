"""Alpaca client and entitlement checks against synthetic responses (no network, no key)."""
from datetime import datetime, timedelta, timezone

import pytest

from tradelab.pit import alpaca_sip as al

OPEN = datetime(2026, 10, 22, 13, 30, tzinfo=timezone.utc)
CLOSE = datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)


def fake(sip_ok=True, quotes_ex=("Q", "N", "P", "Z", "V"), trade_ex=("Q", "N", "P", "D", "V"), paper_ok=True):
    seen = []

    def transport(url, headers):
        seen.append((url, dict(headers)))
        if url.startswith(al.PAPER_URL):
            return (200, {"status": "ACTIVE", "account_number": "PA123"}) if paper_ok else (401, {"message": "unauthorized"})
        if url.startswith(al.LIVE_URL):
            return 401, {"message": "unauthorized"}
        feed = "sip" if "feed=sip" in url else "iex"
        if feed == "sip" and not sip_ok:
            return 403, {"message": "subscription does not permit querying recent SIP data"}
        if "/bars?" in url:
            v = 1_000_000 if feed == "sip" else 25_000
            page2 = "page_token=" in url
            body = {"bars": {"SPY": [{"t": "2026-10-22T13:30:00Z", "v": v}]}, "next_page_token": None if page2 else "abc"}
            return 200, body
        if "/quotes?" in url:
            return 200, {"quotes": {"SPY": [{"bx": x, "ax": x, "bp": 1, "ap": 1.01} for x in quotes_ex]}}
        if "/trades?" in url:
            return 200, {"trades": {"SPY": [{"x": x, "z": "B"} for x in trade_ex]}}
        return 404, {}
    return transport, seen


def test_sip_verdict_and_pagination():
    t, seen = fake()
    r = al.verify_entitlement(al.AlpacaData("k", "s", t), OPEN, CLOSE)
    assert r["verdict"] == "sip" and r["sip_bars"]["n"] == 2 and r["iex_share_of_sip_volume"] == 0.025
    assert any("page_token=abc" in u for u, _ in seen)


def test_iex_only_detected():
    t, _ = fake(quotes_ex=("V",), trade_ex=("V",))
    assert al.verify_entitlement(al.AlpacaData("k", "s", t), OPEN, CLOSE)["verdict"] == "iex_only"


def test_forbidden_reported_with_message():
    t, _ = fake(sip_ok=False)
    r = al.verify_entitlement(al.AlpacaData("k", "s", t), OPEN, CLOSE)
    assert r["verdict"] == "forbidden" and "SIP" in r["sip_bars"]["message"]


def test_paper_key_check_reveals_no_secrets():
    t, _ = fake()
    r = al.verify_paper_key(al.AlpacaData("KEYID", "SECRET", t))
    assert r["is_paper_key"] and r["paper_account_status"] == "ACTIVE"
    assert "KEYID" not in str(r) and "SECRET" not in str(r) and "PA123" not in str(r)
    assert "SECRET" not in repr(al.AlpacaData("KEYID", "SECRET", t))


def test_recent_session_rejected_and_env_rules(monkeypatch):
    t, _ = fake()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        al.verify_entitlement(al.AlpacaData("k", "s", t), now - timedelta(hours=7), now - timedelta(hours=1))
    monkeypatch.delenv("TRADELAB_PAPER_APCA_API_KEY_ID", raising=False)
    with pytest.raises(RuntimeError):
        al.AlpacaData.from_env(t)
    monkeypatch.setenv("TRADELAB_PAPER_APCA_API_KEY_ID", "k")
    monkeypatch.setenv("TRADELAB_PAPER_APCA_API_SECRET_KEY", "s")
    monkeypatch.setenv("TRADELAB_LIVE_KEY_NAME", "x")
    with pytest.raises(RuntimeError, match="live"):
        al.AlpacaData.from_env(t)
