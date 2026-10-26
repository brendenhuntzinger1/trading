"""F4: end-of-day reversal, liquid US stocks (research/phase2/FAMILIES.md; Baltussen, Da & Soebhag 2025).

    python research/phase2/f4_eod_reversal.py fetch 2020-01-02 2022-12-30   # 30-minute bars, dev universe only
    python research/phase2/f4_eod_reversal.py dev

Universe on session t: top 500 operating companies by 20-day dollar volume as of t-1 (F4-C1: top 200).
From SIP 30-minute bars (`all` adjustment, stamped at bar start, ET):
    prev_close  close of the 15:30 bar of t-1 (last continuous-session trade, not the auction)
    p15         close of the 14:30 bar of t (price at 15:00)
    entry       open of the 15:30 bar of t      exit  close of the 15:30 bar of t
    vol_to_15   regular-session volume 09:30-15:00 of t
Signal ROD = p15 / prev_close - 1, known at 15:00; trades 15:30 -> close. Half-days skipped.
Costs (Amendment 1): measured band-median half-spreads at 15:30 (entry) and 15:59 (exit).
"""
from __future__ import annotations

import gzip
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
from research.phase2.data import CACHE, PANELS, Phase2Data                # noqa: E402
from research.phase2.f1_reversal import load_panels                       # noqa: E402
from tradelab.stocks.timeutil import ET, bars_frame, session_bounds       # noqa: E402

FAMILY = "F4"
RESULTS = ROOT / "research" / "phase2" / "results"
DEV = ("2020-01-02", "2022-12-30")
N = 20
CONFIGS = {
    "B0": {"top_n": 500, "market_adj": False, "no_news": False, "long_short": False},
    "C1": {"top_n": 200, "market_adj": False, "no_news": False, "long_short": False},
    "C2": {"top_n": 500, "market_adj": True, "no_news": False, "long_short": False},
    "C3": {"top_n": 500, "market_adj": False, "no_news": True, "long_short": False},
    "C4": {"top_n": 500, "market_adj": False, "no_news": False, "long_short": True},
}


def universe(lo: str, hi: str, top_n: int = 500):
    a, r, comp = load_panels()
    elig, dvol = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=top_n)
    e = elig.shift(1).fillna(False).astype(bool)                 # known before session t
    e = e[(e.index >= lo) & (e.index <= hi)]
    return e, dvol.shift(1), sorted(set(e.columns[e.any()]) | {"SPY"})


def fetch(lo: str, hi: str) -> None:
    from tradelab.pit.alpaca_sip import AlpacaData
    _, _, syms = universe(lo, hi)
    d = Phase2Data(AlpacaData.from_env(), log=lambda m: print(m, flush=True))
    for y in range(int(lo[:4]), int(hi[:4]) + 1):
        d.intraday_year(syms, y, "30Min", hi)
        print("30Min", y, "symbols", len(syms), flush=True)
    print("F4 FETCH DONE", flush=True)


def session_table(lo: str, hi: str, syms: list[str]) -> pd.DataFrame:
    p = PANELS / f"f4_table_{lo}_{hi}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    rows: dict[str, list] = {}
    for f in sorted((CACHE / "intraday").glob("30Min_all_*")):
        for s, r in json.loads(gzip.decompress(f.read_bytes())).items():
            rows.setdefault(s, []).extend(r)
    out = []
    for s in syms:
        b = bars_frame(rows.get(s, []))
        if b.empty:
            continue
        b.index = b.index.tz_convert(ET)
        b["day"], b["hm"] = b.index.strftime("%Y-%m-%d"), b.index.strftime("%H:%M")
        reg = b[(b.hm >= "09:30") & (b.hm < "16:00")]
        prev = np.nan
        for day, g in reg.groupby("day", sort=True):
            bd = session_bounds(day)
            if bd is None:
                continue
            half = bd[1].tz_convert(ET).strftime("%H:%M") != "16:00"
            def bar(hm, col):
                x = g[g.hm == hm]
                return float(x[col].iloc[0]) if len(x) else np.nan
            out.append({"day": day, "symbol": s, "half": half, "prev_close": prev, "p15": bar("14:30", "close"),
                        "entry": bar("15:30", "open"), "exit": bar("15:30", "close"),
                        "vol_to_15": float(g[g.hm < "15:00"].volume.sum())})
            prev = bar("15:30", "close")
    t = pd.DataFrame(out)
    t["day"] = pd.to_datetime(t["day"])
    p.write_bytes(pickle.dumps(t))
    return t


def day_pnl(t: pd.DataFrame, elig: pd.DataFrame, cfg: dict, hs_in: pd.DataFrame, hs_out: pd.DataFrame,
            slip: float = ev.SLIP_BASE) -> tuple[pd.DataFrame, pd.DataFrame]:
    x = t[~t.half].dropna(subset=["prev_close", "p15", "entry", "exit"]).copy()
    x["rod"] = x.p15 / x.prev_close - 1
    spy = x[x.symbol == "SPY"].set_index("day").rod
    x = x[x.symbol != "SPY"]
    if cfg["market_adj"]:
        x["rod"] = x.rod - x.day.map(spy)
    if cfg["no_news"]:
        x = x.sort_values(["symbol", "day"])
        norm = x.groupby("symbol").vol_to_15.transform(lambda v: v.shift(1).rolling(20, min_periods=20).mean())
        x = x[~(x.vol_to_15 > 2 * norm)]
    e = elig.stack()
    e = set(e[e].index)
    x = x[[(d, s) in e for d, s in zip(x.day, x.symbol)]]
    x["ret"] = x.exit / x.entry - 1
    x["hs_in"] = [hs_in.at[d, s] if s in hs_in.columns and d in hs_in.index else 5e-4 for d, s in zip(x.day, x.symbol)]
    x["hs_out"] = [hs_out.at[d, s] if s in hs_out.columns and d in hs_out.index else 5e-4 for d, s in zip(x.day, x.symbol)]
    x["unit_rt"] = x.hs_in.fillna(10e-4) + x.hs_out.fillna(10e-4) + 2 * (slip + ev.FEES_PER_SIDE)
    x["rank_lo"] = x.groupby("day").rod.rank(method="first")
    x["rank_hi"] = x.groupby("day").rod.rank(method="first", ascending=False)
    longs = x[x.rank_lo <= N]
    parts = [longs.assign(side=1.0, w=1.0 / N)]
    if cfg["long_short"]:
        parts.append(x[x.rank_hi <= N].assign(side=-1.0, w=1.0 / N))
    tr = pd.concat(parts)
    tr["gross"] = tr.w * tr.side * tr.ret
    tr["cost"] = tr.w * tr.unit_rt
    g = tr.groupby("day").agg(gross=("gross", "sum"), cost=("cost", "sum"), n_pos=("w", "size"), exposure=("w", "sum"))
    g["turnover"] = 2 * g.exposure
    g["net"] = g.gross - g.cost
    # control: equal weight across every eligible name, same window and cost model
    c = x.assign(w=1.0 / x.groupby("day").symbol.transform("size"))
    ctrl = pd.DataFrame({"gross": (c.w * c.ret).groupby(c.day).sum(), "cost": (c.w * c.unit_rt).groupby(c.day).sum()})
    ctrl["net"] = ctrl.gross - ctrl.cost
    return g, ctrl


def dev() -> dict:
    out, quals, metrics = {"family": FAMILY, "window": DEV, "configs": {}}, {}, {}
    for name, cfg in CONFIGS.items():
        elig, dvol, syms = universe(*DEV, top_n=cfg["top_n"])
        t = session_table(*DEV, universe(*DEV, top_n=500)[2])
        hs_in = ev.measured_half_spread(dvol, elig, "15:30")
        hs_out = ev.measured_half_spread(dvol, elig, "15:59")
        p, ctrl = day_pnl(t, elig, cfg, hs_in, hs_out)
        ps, _ = day_pnl(t, elig, cfg, hs_in, hs_out, slip=ev.SLIP_STRESS)
        summ = ev.summarise(p, ctrl["net"], ctrl["gross"], ps["net"])
        summ["diagnosis"] = {"gross_bp_per_position": float(p.gross.sum() / p.n_pos.sum() * N * 1e4),
                             "round_trip_cost_bp": float(p.cost.sum() / p.exposure.sum() * 1e4),
                             "sessions": int(len(p))}
        q = ev.dev_qualifies(summ)
        if cfg["long_short"]:
            q = {**q, "qualified": False, "note": "labelled upper bound (borrow not modelled); not freezable"}
        out["configs"][name] = {"params": cfg, "summary": summ, "qualifiers": q}
        quals[name] = q
        metrics[name] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"],
                         "gross_vs_control_bp": summ["vs_control_gross_bp"]["mean"]}
    stages.record_dev(FAMILY, quals, metrics)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "f4_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "dev":
        r = dev()
        for k, v in r["configs"].items():
            s = v["summary"]
            print(k, f"net {s['net']['mean_bp']:.2f}bp/day sh {s['net']['sharpe']:.2f} gross {s['gross']['mean_bp']:.2f} "
                     f"rt_cost {s['diagnosis']['round_trip_cost_bp']:.2f} vs_ctrl_gross {s['vs_control_gross_bp']} "
                     f"years { {y: round(x * 1e4) for y, x in s['by_year_net'].items()} } qual {v['qualifiers']}")
