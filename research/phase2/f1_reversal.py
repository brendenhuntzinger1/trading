"""F1: liquidity-provision reversal conditioned on market stress (research/phase2/FAMILIES.md).

    python research/phase2/f1_reversal.py dev        # baseline + 4 configs on 2020-01-02..2022-12-30

Signal after the close of t (bars through t); market-on-open entry at t+1, exit at the open of t+2. A name that
does not open at t+1 is not bought (order unfilled, cash kept). A held name with no open at t+2 is valued at its
last close of t+1 (delisting/halt), so nothing is invented and nothing vanishes.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import evaluate as ev                               # noqa: E402
from research.phase2 import stages, xs                                    # noqa: E402
from research.phase2.data import Cache, CACHE, PANELS                     # noqa: E402

FAMILY = "F1"
RESULTS = ROOT / "research" / "phase2" / "results"
DEV = ("2020-01-02", "2022-12-30")
LAST = "2026-10-23"
N = 20

CONFIGS = {
    "B0": {"signal": "r1_mkt", "top_n": 1000, "no_news": False, "stress_only": False},
    "C1": {"signal": "r5_mkt", "top_n": 1000, "no_news": False, "stress_only": False},
    "C2": {"signal": "r1_mkt", "top_n": 1000, "no_news": True, "stress_only": False},
    "C3": {"signal": "r1_mkt", "top_n": 1000, "no_news": False, "stress_only": True},
    "C4": {"signal": "r1_mkt", "top_n": 200, "no_news": False, "stress_only": False},
}


def load_panels():
    a = pickle.loads((PANELS / f"daily_all_2016_{LAST}.pkl").read_bytes())
    r = pickle.loads((PANELS / f"daily_raw_2016_{LAST}.pkl").read_bytes())
    master = Cache(CACHE).get("assets", "us_equity_full")
    return a, r, xs.operating_companies(master)


def open_to_open_with_exit(a: dict) -> pd.DataFrame:
    """Return of a position entered at the open of row t and exited at the open of t+1 (row t); if there is no
    open at t+1, the last close of t is used (the position is closed at its last traded price)."""
    o, c = a["open"], a["close"]
    nxt = o.shift(-1)
    exit_px = nxt.where(nxt.notna(), c)
    return exit_px / o - 1


def features(a: dict, r: dict) -> dict:
    c = a["close"]
    ret1 = c.pct_change(fill_method=None)
    spy = ret1["SPY"]
    r5 = c.pct_change(5, fill_method=None)
    spy5 = c["SPY"].pct_change(5, fill_method=None)
    vol_ratio = r["volume"] / r["volume"].shift(1).rolling(20, min_periods=20).mean()
    spy_rv = spy.rolling(20, min_periods=20).std()
    stress = spy_rv > spy_rv.rolling(252, min_periods=126).median()
    return {"r1_mkt": ret1.sub(spy, axis=0), "r5_mkt": r5.sub(spy5, axis=0), "vol_ratio": vol_ratio, "stress": stress}


def weights(cfg: dict, f: dict, eligible: pd.DataFrame, opens: pd.DataFrame) -> pd.DataFrame:
    ok = eligible.copy()
    if cfg["no_news"]:
        ok &= f["vol_ratio"].reindex_like(ok) <= 2.0
    w = xs.select_weights(f[cfg["signal"]].reindex_like(ok), ok, N, lowest=True)
    if cfg["stress_only"]:
        w = w.mul(f["stress"].shift(1).reindex(w.index).fillna(False).astype(float), axis=0)
    return w.where(opens.reindex_like(w).notna(), 0.0)          # unfilled market-on-open orders hold cash


def run(cfg, a, r, comp, f, lo, hi, slip=ev.SLIP_BASE):
    elig, dvol = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=cfg["top_n"])
    w = weights(cfg, f, elig, a["open"][elig.columns])
    ret = open_to_open_with_exit({"open": a["open"][elig.columns], "close": a["close"][elig.columns]})
    hs = ev.tier_half_spread(dvol.shift(1))                       # tier known at the decision (row = entry day)
    keep = (w.index >= pd.Timestamp(lo)) & (w.index <= pd.Timestamp(hi))
    p = ev.backtest_weights(w[keep], ret[keep], hs[keep], slip=slip)
    cw = xs.control_weights(elig).where(a["open"][elig.columns].notna(), 0.0)
    cp = ev.backtest_weights(cw[keep], ret[keep], hs[keep], slip=slip)
    return p, cp, w[keep], ret[keep]


def dev() -> dict:
    a, r, comp = load_panels()
    f = features(a, r)
    out, quals, metrics = {"family": FAMILY, "window": DEV, "configs": {}}, {}, {}
    for name, cfg in CONFIGS.items():
        p, cp, w, ret = run(cfg, a, r, comp, f, *DEV)
        ps, _, _, _ = run(cfg, a, r, comp, f, *DEV, slip=ev.SLIP_STRESS)
        summ = ev.summarise(p, cp["net"], cp["gross"], ps["net"])
        held = (w > 0)
        trade_rets = ret.where(held).stack()
        summ["diagnosis"] = {
            "position_days": int(held.sum().sum()),
            "gross_bp_per_position_day": float(trade_rets.mean() * 1e4),
            "control_gross_bp_per_day": float(cp["gross"].mean() * 1e4),
            "stress_state_share": float(f["stress"].reindex(p.index).mean()),
            "by_stress_state_gross_bp": {str(k): float(v * 1e4) for k, v in
                                         p.gross.groupby(f["stress"].shift(1).reindex(p.index).fillna(False)).mean().items()},
            "top10_names_share_of_gross": _name_share(w, ret),
        }
        q = ev.dev_qualifies(summ)
        out["configs"][name] = {"params": cfg, "summary": summ, "qualifiers": q}
        quals[name] = q
        metrics[name] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"],
                         "gross_vs_control_bp": summ["vs_control_gross_bp"]["mean"]}
    stages.record_dev(FAMILY, quals, metrics)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "f1_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def _name_share(w: pd.DataFrame, ret: pd.DataFrame) -> float | None:
    by = (w * ret.fillna(0.0)).sum()
    tot = by.sum()
    return float(by.sort_values(ascending=False).head(10).sum() / tot) if tot > 0 else None


if __name__ == "__main__":
    r = dev()
    for k, v in r["configs"].items():
        s = v["summary"]
        print(k, f"net {s['net']['mean_bp']:.2f}bp/day sh {s['net']['sharpe']:.2f} gross {s['gross']['mean_bp']:.2f} "
                 f"cost {s['cost_bp_per_day']:.2f} vs_ctrl_gross {s['vs_control_gross_bp']} vs_ctrl_net {s['vs_control_net_bp']} "
                 f"years { {y: round(x * 1e4) for y, x in s['by_year_net'].items()} } qual {v['qualifiers']}")
