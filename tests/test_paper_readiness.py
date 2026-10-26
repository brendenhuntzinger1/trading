"""Paper-operation readiness: one equity mark per day, duplicate prevention across re-runs, persistent risk halts
through a state save/restore cycle, state recovery and failed saves of scripts/paper_state.sh."""
import json
import shutil
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

import tradelab.service.daily as daily
from tradelab.execution.store import Store
from tests.conftest import ROOT
from tests.test_service import NOW, env, run_at  # noqa: F401  (fixture reuse)


def test_save_checkpoints_wal_so_no_committed_row_is_lost(repo):
    _, clone = repo
    a = clone("w")
    (a / "data").mkdir()
    keep = sqlite3.connect(a / "data" / "journal_paper.db", isolation_level=None)   # held open, like a live process
    keep.execute("PRAGMA journal_mode=WAL"); keep.execute("PRAGMA wal_autocheckpoint=0")
    keep.execute("CREATE TABLE t (x)"); keep.execute("INSERT INTO t VALUES (42)")
    assert (a / "data" / "journal_paper.db-wal").stat().st_size > 0
    assert _state("save", a, "w").returncode == 0
    b = clone("w2")
    assert _state("restore", b).returncode == 0
    assert sqlite3.connect(b / "data" / "journal_paper.db").execute("select x from t").fetchall() == [(42,)]

SCRIPT = ROOT / "scripts" / "paper_state.sh"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def test_same_day_reruns_add_no_marks_orders_or_fills(env):
    tmp, *_ = env
    run_at(env, NOW)
    db = sqlite3.connect(tmp / "j.db")
    before = {t: db.execute(f"select count(*) from {t}").fetchone()[0] for t in ("equity", "orders", "fills")}
    run_at(env, NOW + timedelta(hours=6))                 # the 06:17 catch-up schedule
    run_at(env, NOW + timedelta(hours=6, minutes=1))      # and a manual re-run
    after = {t: db.execute(f"select count(*) from {t}").fetchone()[0] for t in ("equity", "orders", "fills")}
    assert after == before
    days = db.execute("select account, substr(at,1,10), count(*) from equity group by 1, 2").fetchall()
    assert all(n == 1 for *_, n in days)
    run_at(env, NOW + timedelta(days=1))                  # the next day gets its own mark
    assert db.execute("select count(*) from equity").fetchone()[0] == 2 * before["equity"]


def test_legacy_duplicate_marks_are_collapsed_to_the_first_of_each_day(tmp_path):
    p = tmp_path / "old.db"
    db = sqlite3.connect(p)
    db.execute("CREATE TABLE equity (at TEXT, mode TEXT, account TEXT, equity REAL, cash REAL, positions TEXT, marks TEXT, "
               "operating_cost REAL DEFAULT 0, PRIMARY KEY (at, mode, account))")
    for at, eq in (("2026-10-26T02:05:00+00:00", 100.0), ("2026-10-26T02:07:00+00:00", 101.0), ("2026-10-27T00:17:00+00:00", 102.0)):
        db.execute("INSERT INTO equity VALUES (?,?,?,?,?,?,?,?)", (at, "paper", "a", eq, 0, "{}", "{}", 0.5))
    db.commit(); db.close()
    s = Store(p, "paper")
    rows = s.db.execute("select at, equity from equity order by at").fetchall()
    assert rows == [("2026-10-26T02:05:00+00:00", 100.0), ("2026-10-27T00:17:00+00:00", 102.0)]
    assert s.mark("2026-10-27T06:17:00+00:00", "a", 999.0, 0, {}, {}) is False


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _state(cmd, cwd, *extra):
    return subprocess.run(["bash", str(SCRIPT), cmd, *extra], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    _git("init", "-q", "--bare", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-q", "-b", "main", cwd=seed)
    (seed / "README").write_text("x")
    _git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=seed)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed", cwd=seed)
    _git("push", "-q", str(remote), "main", cwd=seed)

    def clone(name):
        d = tmp_path / name
        _git("clone", "-q", "-b", "main", str(remote), str(d), cwd=tmp_path)
        return d
    return remote, clone


@needs_git
def test_state_round_trip_and_unchanged_state_is_not_resaved(repo):
    remote, clone = repo
    a = clone("a")
    assert "starting fresh" in _state("restore", a).stdout
    (a / "data" / "paper").mkdir(parents=True)
    (a / "data" / "paper" / "x.txt").write_text("one")
    r = _state("save", a, "r1"); assert r.returncode == 0, r.stderr
    # Regression: the save used to switch this checkout to paper-state, deleting scripts/config that later
    # workflow steps (alerts) still needed.
    assert (a / "README").read_text() == "x"
    assert subprocess.run(["git", "branch", "--show-current"], cwd=a, capture_output=True, text=True).stdout.strip() == "main"
    assert (a / "data" / "paper" / "x.txt").read_text() == "one"
    b = clone("b")
    assert _state("restore", b).returncode == 0
    assert (b / "data" / "paper" / "x.txt").read_text() == "one"
    assert "nothing to save" in _state("save", b, "r2").stdout


@needs_git
def test_unreachable_remote_fails_restore_and_save(repo, tmp_path):
    _, clone = repo
    c = clone("c")
    _git("remote", "set-url", "origin", str(tmp_path / "missing.git"), cwd=c)
    assert _state("restore", c).returncode != 0          # must not look like "no state yet"
    (c / "data").mkdir(exist_ok=True)
    assert _state("save", c, "x").returncode != 0


@needs_git
def test_rejected_push_fails_the_save(repo):
    remote, clone = repo
    a, b = clone("a"), clone("b")
    for d in (a, b):
        assert _state("restore", d).returncode == 0
    (a / "data").mkdir(); (a / "data" / "journal_paper.db").write_text("a")
    assert _state("save", a, "a").returncode == 0
    # b restored before a saved; its save is based on the old paper-state tip... it re-fetches, so it succeeds:
    (b / "data").mkdir(); (b / "data" / "journal_paper.db").write_text("b")
    assert _state("save", b, "b").returncode == 0
    # A real rejection (a hook refusing the push) must fail the job, never print "nothing to save".
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho rejected >&2\nexit 1\n"); hook.chmod(0o755)
    c = clone("c")
    assert _state("restore", c).returncode == 0
    (c / "data" / "journal_paper.db").write_text("c")
    r = _state("save", c, "c")
    assert r.returncode != 0 and "nothing to save" not in r.stdout


@needs_git
def test_risk_halt_survives_state_save_and_restore(repo, env, monkeypatch):
    """A latched breaker written by one Actions run is still enforced by the next run on a fresh machine."""
    remote, clone = repo
    tmp, *_ = env
    a = clone("run1")
    monkeypatch.setattr(daily, "ROOT", a)
    monkeypatch.setattr(daily, "LIVE_DATA", a / "data" / "paper")
    (a / "data").mkdir(exist_ok=True)
    j = lambda d: d / "data" / "journal_paper.db"
    daily.run(ROOT / "config" / "paper.toml", NOW, j(a))
    vp = a / "data" / "paper_venue" / "paper-fixed_allocation.json"
    bad = json.loads(vp.read_text()); bad["bal"]["USD"] -= 50; vp.write_text(json.dumps(bad))
    env[2].now = NOW + timedelta(days=1)
    s = daily.run(ROOT / "config" / "paper.toml", NOW + timedelta(days=1), j(a))
    assert "reconciliation_mismatch" in s["accounts"]["paper-fixed_allocation"]["breakers"]

    assert _state("save", a, "run1").returncode == 0

    b = clone("run2")                                      # a fresh machine
    assert _state("restore", b).returncode == 0
    monkeypatch.setattr(daily, "ROOT", b)
    monkeypatch.setattr(daily, "LIVE_DATA", b / "data" / "paper")
    env[2].now = NOW + timedelta(days=2)
    s = daily.run(ROOT / "config" / "paper.toml", NOW + timedelta(days=2), j(b))
    assert "reconciliation_mismatch" in s["accounts"]["paper-fixed_allocation"]["breakers"], "halt must survive restore"
    assert Store(j(b), "paper").active_latches("paper-fixed_allocation")
