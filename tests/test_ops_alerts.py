"""Missed-run detection and alert delivery gating (nothing is delivered without an approved destination)."""
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tomllib

from tradelab.ops import watchdog
from tests.conftest import ROOT

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)          # a Tuesday, NYSE open
CFG = tomllib.loads((ROOT / "config" / "alerts.toml").read_text())


def test_repository_alert_destination_is_not_approved_by_default():
    assert CFG["destination"]["approved"] is False


def test_missed_and_fresh_runs(tmp_path):
    watchdog.beat("paper-daily", now=NOW - timedelta(hours=30), root=tmp_path)
    watchdog.beat("paper-crypto-intraday", now=NOW - timedelta(minutes=20), root=tmp_path)
    rows = {r["workflow"]: r for r in watchdog.check(tmp_path, NOW, CFG, market_open=lambda t: True)}
    assert rows["paper-daily"]["status"] == "missed"
    assert rows["paper-crypto-intraday"]["status"] == "ok"
    assert rows["paper-stocks-intraday"]["status"] == "missed"           # never ran, market open
    closed = {r["workflow"]: r for r in watchdog.check(tmp_path, NOW, CFG, market_open=lambda t: False)}
    assert closed["paper-stocks-intraday"]["status"] == "ok"              # not judged while the market is closed


def test_market_hours_from_the_exchange_calendar():
    assert watchdog._market_open(NOW) is True
    assert watchdog._market_open(datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)) is False   # Sunday


def _run_alert(tmp_path, approved: bool, *args):
    cfg = tmp_path / "alerts.toml"
    cfg.write_text(f'[destination]\ntype = "github_issue"\napproved = {"true" if approved else "false"}\n')
    log = tmp_path / "gh.log"
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "gh").write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit 0\n')
    (fake / "gh").chmod(0o755)
    env = {**os.environ, "ALERTS_CONFIG": str(cfg), "PATH": f"{fake}:{os.environ['PATH']}", "GITHUB_STEP_SUMMARY": str(tmp_path / "sum.md")}
    r = subprocess.run(["bash", str(ROOT / "scripts" / "paper_alert.sh"), *args], env=env, capture_output=True, text=True)
    return r, (log.read_text() if log.exists() else "")


def test_unapproved_destination_delivers_nothing(tmp_path):
    r, calls = _run_alert(tmp_path, False, "open", "failed:paper-daily", "paper-daily failed", "url")
    assert r.returncode == 0 and calls == ""
    assert "NOT DELIVERED" in r.stdout
    assert "not delivered" in (tmp_path / "sum.md").read_text()


def test_approved_destination_opens_one_issue(tmp_path):
    r, calls = _run_alert(tmp_path, True, "open", "failed:paper-daily", "paper-daily failed", "url")
    assert r.returncode == 0, r.stderr
    assert "issue create --label paper-alert --title [paper-alert] failed:paper-daily" in calls
