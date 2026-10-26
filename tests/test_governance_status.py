from tradelab.governance.status import REGISTRY, Entry, Status, live_eligible


def test_nothing_is_live_eligible_today():
    assert [n for n in REGISTRY if live_eligible(n)] == []


def test_inconclusive_or_pending_never_eligible_even_with_approval():
    for st in (Status.INCONCLUSIVE, Status.PENDING, Status.REJECTED, Status.UNTESTABLE, Status.BENCHMARK):
        REGISTRY["_t"] = Entry(st, "experimental", "x", prospective_paper_accepted=True, owner_approval="yes")
        assert not live_eligible("_t")
    REGISTRY["_t"] = Entry(Status.PASSED, "experimental", "x", prospective_paper_accepted=False, owner_approval="yes")
    assert not live_eligible("_t")
    del REGISTRY["_t"]


def test_every_paper_strategy_has_a_status():
    import tomllib
    from tests.conftest import ROOT
    daily = tomllib.loads((ROOT / "config/paper.toml").read_text())["strategies"]
    intraday = tomllib.loads((ROOT / "config/intraday_paper.toml").read_text())
    names = daily + intraday["crypto"]["setups"] + ["S2_etf" if s == "S2" else s for s in intraday["stocks"]["setups"]]
    assert all(n in REGISTRY for n in names), [n for n in names if n not in REGISTRY]
    assert all(REGISTRY[n].status is not Status.REJECTED or REGISTRY[n].paper_run != "none" for n in names)
