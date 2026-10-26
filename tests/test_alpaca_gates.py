"""Data gates against synthetic API responses: a non-paper key stops everything; the timestamp gate checks the
09:30 ET open bar on DST and standard-time days; the corporate-action gate checks raw vs split-adjusted bars."""
import urllib.parse

import pandas as pd

from tradelab.pit import alpaca_sip as al
from tradelab.stocks import verify
from tradelab.stocks.timeutil import session_bounds


def _q(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def test_non_paper_key_stops_before_any_gate():
    def t(url, h):
        return (401, {}) if url.startswith(al.PAPER_URL) else (200, {})
    r = verify.run_all(al.AlpacaData("k", "s", t))
    assert not r["paper_key"]["is_paper_key"] and list(r["gates"]) == ["B7_1_sip_access"]
    assert not r["gates"]["B7_1_sip_access"]["pass"]


def _minute_rows(day):
    o, c = session_bounds(day)
    idx = pd.date_range(o - pd.Timedelta(hours=5, minutes=30), c + pd.Timedelta(hours=4) - pd.Timedelta(minutes=1), freq="min")
    return [{"t": x.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for x in idx]


def test_timestamp_gate_passes_on_correct_utc_bar_starts():
    def t(url, h):
        q = _q(url)
        if "/bars?" in url:
            day = pd.Timestamp(q["start"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
            return 200, {"bars": {"SPY": _minute_rows(day)}}
        start = pd.Timestamp(q["start"])
        rows = [{"t": (start + pd.Timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S.123456789Z"), "bp": 1, "ap": 1.01}
                for s in range(5)]
        return 200, {"quotes": {"SPY": rows}}
    g = verify.gate_timestamps(al.AlpacaData("k", "s", t))
    assert g["pass"] and all(d["open_bar_et"] == "09:30" and d["nanosecond_timestamps"] for d in g["days"].values())


def test_timestamp_gate_fails_if_bars_are_shifted_an_hour():
    def t(url, h):
        q = _q(url)
        if "/bars?" in url:
            day = pd.Timestamp(q["start"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
            rows = _minute_rows(day)
            for r in rows:
                r["t"] = (pd.Timestamp(r["t"]) + pd.Timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return 200, {"bars": {"SPY": rows}}
        return 200, {"quotes": {"SPY": []}}
    assert not verify.gate_timestamps(al.AlpacaData("k", "s", t))["pass"]


def test_corporate_action_gate_detects_split_jump():
    def t(url, h):
        q = _q(url)
        sym = q["symbols"]
        eff = {s: (pd.Timestamp(d), r) for s, d, r in verify.SPLITS}[sym]
        if q["timeframe"] == "1Day":
            days = pd.bdate_range(pd.Timestamp(q["start"]), pd.Timestamp(q["end"]))
            rows = []
            for d in days:
                raw = 1000.0 if d < eff[0] else 1000.0 / eff[1]
                px = raw if q["adjustment"] == "raw" else 1000.0 / eff[1]
                ts = pd.Timestamp(d, tz="America/New_York").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
                rows.append({"t": ts, "o": px, "h": px, "l": px, "c": px, "v": 1})
            return 200, {"bars": {sym: rows}}
        return 200, {"bars": {sym: [{"t": q["start"], "o": 1000, "h": 1000, "l": 1000, "c": 1000.0, "v": 1}]}}
    g = verify.gate_corporate_actions(al.AlpacaData("k", "s", t))
    assert g["pass"], g
