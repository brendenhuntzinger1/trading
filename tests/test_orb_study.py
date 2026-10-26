"""ORB harness on a synthetic data source: benchmarks and decomposition, measured vs assumed cost paths,
B9 (no qualified candidate -> final window unread), freeze-by-hash refusal, consumed-data marking and
deterministic re-runs. No network and no real market data."""
import hashlib
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from research.orb import study
from tradelab.research.consumed import ConsumedDataError
from tradelab.stocks.spreads import HalfSpread
from tradelab.stocks.timeutil import session_bounds, session_days


class Fixture:
    """Deterministic random-walk minute bars; candidates A (up), B (down), C (doji), D (up, quiet)."""
    def __init__(self, quotes=True, n_days=6):
        self.quotes_available = quotes
        self.n_days = n_days

    def days(self, start, end):
        return session_days(start, end)[: self.n_days]

    def candidates(self, day):
        return pd.DataFrame({"symbol": list("ABCD"), "open": [50.0] * 4, "adv": [3e6] * 4, "atr": [1.5] * 4,
                             "rv": [6.0, 4.0, 3.0, 1.5], "direction": [1, -1, 0, 1], "corporate_action": [False] * 4,
                             "has_open_bar": [True] * 4})

    def minute_bars(self, symbols, day):
        out = {}
        o, c = session_bounds(day)
        idx = pd.date_range(o, c - pd.Timedelta(minutes=1), freq="min")
        for s in symbols:
            seed = int(hashlib.sha256(f"{s}{day}".encode()).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            drift = {"A": 0.0004, "B": -0.0004, "C": 0.0, "D": 0.0, "SPY": 0.0001}.get(s, 0.0)
            px = 50 * np.exp(np.cumsum(rng.normal(drift, 0.001, len(idx))))
            op = np.r_[50.0, px[:-1]]
            if s == "C":                                   # doji opening range: close of 09:34 == open of 09:30
                px[4] = op[0]
            if s in ("A", "D"):                            # bullish opening range
                px[4] = max(px[4], op[0] * 1.001)
            if s == "B":
                px[4] = min(px[4], op[0] * 0.999)
            hi = np.maximum(op, px) * 1.0005
            lo = np.minimum(op, px) * 0.9995
            out[s] = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": px, "volume": 1000.0}, index=idx)
        return out

    def half_spread(self, symbol, minute):
        return HalfSpread(0.0002, minute, "ok") if self.quotes_available else None


class Untouchable:
    quotes_available = True

    def __getattr__(self, name):
        raise AssertionError(f"data source touched: {name}")


@pytest.fixture
def iso(tmp_path, monkeypatch):
    recs = []
    monkeypatch.setattr(study, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(study, "FROZEN", tmp_path / "frozen.json")
    monkeypatch.setattr(study, "CONSUMED_LEDGER", tmp_path / "consumed.json")
    monkeypatch.setattr(study, "record", lambda *a, **k: recs.append((a, k)))
    return tmp_path, recs


def test_benchmarks_decomposition_and_abstentions():
    out = study.run_period(Fixture(), "dev", ["primary", "long_short"], placebo_reps=20)
    p = out["configs"]["primary"]
    assert p["cost_path"] == "measured spread"
    assert set(p["benchmarks"]) == {"basket", "direction", "rule_nostop"}
    assert set(p["decomposition"]) == {"entry_trigger_value", "stop_value"}
    ab = p["rule"]["abstention"]
    assert ab["doji"] == 6 and ab["short_signal_long_only"] == 6
    assert (p["_frames"]["rule"].side > 0).all()
    assert (out["configs"]["long_short"]["_frames"]["rule"].side < 0).any()
    assert p["placebo"]["reps"] == 20 and out["benchmark_spy"]["sharpe"] is not None


def test_cost_assumed_path_is_labelled():
    p = study.run_period(Fixture(quotes=False), "dev", ["primary"], placebo_reps=0)["configs"]["primary"]
    assert p["cost_path"] == "cost assumed, not measured"
    assert p["rule"]["cost_label"] == ["cost assumed, not measured"]


def test_final_without_a_qualified_freeze_reads_nothing(iso):
    with pytest.raises(SystemExit, match="B9"):
        study.phase_final(Untouchable())
    study.FROZEN.write_text(json.dumps({"config": "primary", "hash": study.config_hash(), "qualified": False}))
    with pytest.raises(SystemExit, match="B9"):
        study.phase_final(Untouchable())
    assert not study.CONSUMED_LEDGER.exists()


def test_freeze_refuses_an_unqualified_configuration(iso):
    study.RESULTS.mkdir(parents=True)
    (study.RESULTS / "dev.json").write_text(json.dumps({"qualifiers": {"primary": {"qualified": False}}}))
    (study.RESULTS / "validation.json").write_text(json.dumps({"qualifiers": {"primary": {"net_all_mean_ge_0": True}}}))
    with pytest.raises(SystemExit, match="stays UNREAD"):
        study.phase_freeze("primary")
    assert not study.FROZEN.exists()


def test_final_refuses_a_changed_configuration_and_records_a_violation(iso):
    _, recs = iso
    study.FROZEN.write_text(json.dumps({"config": "primary", "hash": "0" * 64, "qualified": True, "n_trials": 100}))
    with pytest.raises(SystemExit, match="REFUSED"):
        study.phase_final(Untouchable())
    assert recs[-1][0][0] == "violation" and not study.CONSUMED_LEDGER.exists()


def test_final_marks_consumed_and_reruns_reproduce(iso):
    _, recs = iso
    study.FROZEN.write_text(json.dumps({"config": "primary", "hash": study.config_hash(), "qualified": True, "n_trials": 100}))
    a = study.phase_final(Fixture(), placebo_reps=10)
    led = json.loads(study.CONSUMED_LEDGER.read_text())["entries"]
    assert led[0]["scope"] == study.SCOPE and (led[0]["start"], led[0]["end"]) == study.PERIODS["final"]
    assert a["verdict"]["verdict"] in ("PASS", "INCONCLUSIVE", "REJECT (no useful effect)")
    b = study.phase_final(Fixture(), placebo_reps=10)
    assert a == b and recs[-1][1]["metrics"] == {"identical": True}


def test_selection_windows_refuse_consumed_data(iso):
    study.RESULTS.mkdir(parents=True)
    (study.RESULTS / "gates.json").write_text(json.dumps({"pass": True, "quotes_available": True}))
    study.CONSUMED_LEDGER.write_text(json.dumps({"entries": [
        {"scope": "stocks.us.intraday", "start": "2021-01-01", "end": "2021-06-30", "study": "X"}]}))
    with pytest.raises(ConsumedDataError):
        study.phase_selection(Untouchable(), "dev")


def test_hash_covers_parameters_and_code(tmp_path, monkeypatch):
    h0 = study.config_hash()
    for f in study.CODE_FILES:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(study.ROOT / f, tmp_path / f)
    assert study.config_hash(tmp_path) == h0
    (tmp_path / "tradelab/stocks/orb.py").write_text((tmp_path / "tradelab/stocks/orb.py").read_text() + "\n# edit\n")
    assert study.config_hash(tmp_path) != h0
    import dataclasses
    from tradelab.stocks import orb
    monkeypatch.setitem(orb.CONFIGS, "primary", dataclasses.replace(orb.CONFIGS["primary"], stop_atr_frac=0.2))
    assert study.config_hash() != h0


def test_dev_qualifiers_require_sanity_gate_and_both_benchmarks():
    dev = {"configs": {"primary": {"vs_direction": {"ci": [0.001, 0.01]}, "vs_placebo": {"ci": [0.0005, 0.01]}},
                       "x": {"vs_direction": {"ci": [-0.001, 0.01]}, "vs_placebo": {"ci": [0.001, 0.01]}}}}
    q = study.dev_qualifiers(dev, {"pass": True})
    assert q["primary"]["qualified"] and not q["x"]["qualified"]
    assert not study.dev_qualifiers(dev, {"pass": False})["primary"]["qualified"]


def test_only_primary_can_be_frozen():
    """Amendment 3, B10: dev variants and long/short are sensitivity only, never frozen or promoted."""
    for cfg in ("long_short", "dev_rv2_top20", "dev_rv5_top20", "dev_rv1_top10", "dev_rv2_top10"):
        with pytest.raises(SystemExit, match="B10"):
            study.phase_freeze(cfg)


def test_trial_count_baseline_is_recorded():
    from research.orb import evaluate as ev
    assert ev.trial_count() >= 100


def test_universe_adds_delisted_tickers_and_dedupes_mapped_symbols(tmp_path):
    """ORB Amendment 4: the asset master omits most delisted names; corporate actions add them back, and one
    company reachable through two tickers (FB/META) is counted once."""
    from research.orb.data import AlpacaSource

    class FakeClient:
        def assets(self):
            return 200, [{"symbol": "META", "exchange": "NASDAQ", "status": "active"},
                         {"symbol": "FB", "exchange": "BATS", "status": "active"},
                         {"symbol": "TWTR_DELISTED", "exchange": "NYSE", "status": "inactive"},
                         {"symbol": "021CVR014", "exchange": "NASDAQ", "status": "inactive"}]

        def corporate_actions(self, types, start, end):
            if start.startswith("2022"):
                return 200, {"cash_mergers": [{"acquiree_symbol": "ATVI"}, {"acquiree_symbol": "007CVR020"}],
                             "name_changes": [{"old_symbol": "FB", "new_symbol": "META"}]}
            return 200, {}

    src = AlpacaSource(FakeClient(), "2022-01-03", "2022-12-30", cache=tmp_path)
    assert src.symbols() == ["ATVI", "FB", "META", "TWTR"]

    idx = pd.date_range("2022-05-01", "2022-06-10", freq="B")
    daily = pd.DataFrame({"open": 200.0, "high": 205.0, "low": 195.0, "close": 200.0, "volume": 3e6}, index=idx)
    src._daily_raw = {"FB": daily, "META": daily}
    src._daily_adj = {"FB": daily, "META": daily}
    bar = {"t": "2022-06-01T13:30:00Z", "o": 200.0, "h": 202.0, "l": 199.0, "c": 201.5, "v": 900000}
    src._or_bars = lambda day: {"FB": bar, "META": bar}
    c = src.candidates("2022-06-01")
    assert list(c.symbol) == ["FB"]


def test_quote_batching_matches_single_symbol_rule(tmp_path):
    """One request per minute for every symbol of the day, with the same 2 s / 60 s rule per symbol."""
    from research.orb.data import AlpacaSource
    calls = []

    class FakeClient:
        def quotes_multi(self, symbols, start, end):
            calls.append((tuple(symbols), (end - start).total_seconds()))
            if (end - start).total_seconds() == 2:
                return 200, {"AAA": [{"t": "2022-06-01T19:59:59.5Z", "bp": 10.0, "ap": 10.02, "bs": 1, "as": 1}]}
            return 200, {"BBB": [{"t": "2022-06-01T19:59:30Z", "bp": 20.0, "ap": 20.1, "bs": 1, "as": 1}]}

    src = AlpacaSource(FakeClient(), "2022-01-03", "2022-12-30", cache=tmp_path)
    src._day_syms["2022-06-01"] = {"AAA", "BBB", "CCC"}
    m = pd.Timestamp("2022-06-01T19:59:00Z")
    a = src.half_spread("AAA", m)
    assert calls == [(("AAA", "BBB", "CCC"), 2.0), (("BBB", "CCC"), 60.0)]
    b, c = src.half_spread("BBB", m), src.half_spread("CCC", m)
    assert len(calls) == 2                                   # BBB and CCC came from the cache
    assert src.cache.get("quotes", "BBB_20220601T2000")[0]["bp"] == 20.0
    assert src.cache.get("quotes", "CCC_20220601T2000") == []
    assert a is not None


def test_validation_stays_unread_if_primary_fails_development(iso):
    """Amendment 5, B16: no validation data is touched unless primary qualified in development."""
    study.RESULTS.mkdir(parents=True)
    (study.RESULTS / "gates.json").write_text(json.dumps({"pass": True, "quotes_available": True}))
    (study.RESULTS / "dev.json").write_text(json.dumps({"qualifiers": {
        "primary": {"sanity_gate": True, "beats_direction": False, "beats_placebo": True, "qualified": False},
        "dev_rv5_top20": {"qualified": True}}}))
    with pytest.raises(SystemExit, match="B16"):
        study.phase_selection(Untouchable(), "validation")


def test_halted_stock_is_skipped_by_every_benchmark_not_a_crash():
    """Incident 19: a selected stock with no bar after 09:35 (halted all day) made the basket benchmark record an
    unfilled trade and crash on its missing entry time. It must count as 'basket_no_fill' and invent nothing."""
    class Halted(Fixture):
        def minute_bars(self, symbols, day):
            out = super().minute_bars(symbols, day)
            if "D" in out:
                o, _ = session_bounds(day)
                out["D"] = out["D"][out["D"].index < o + pd.Timedelta(minutes=5)]    # opening range only
            return out
    out = study.run_period(Halted(), "dev", ["primary"], placebo_reps=5)
    ab = out["configs"]["primary"]["rule"]["abstention"]
    assert ab["basket_no_fill"] >= 1
