"""F3: market intraday momentum, corrected re-test of H7/S1 (research/phase2/FAMILIES.md).

    python research/phase2/f3_intraday_momentum.py table        # build the per-session price table (cache only)
    python research/phase2/f3_intraday_momentum.py dev          # baseline + 4 configs on 2016-01-04..2022-12-30

Per session and symbol, from SIP 1-minute bars (`all` adjustment; bars stamped at their start):
    c_prev  close of the previous session's last regular bar          (15:59 bar)
    p10     close of the last bar starting before 10:00 ET            (09:59 bar)
    p12     close of the last bar starting before 12:00 ET
    p1530c  close of the last bar starting before 15:30 ET            (known at 15:30)
    entry   open of the first bar starting at or after 15:30 ET
    exit    close of the last bar starting before 16:00 ET            (15:59 bar = closing-quote proxy)
Half-days (13:00 close) are skipped and counted. A session missing any of these prices is skipped and counted.
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
from research.phase2 import stages                                       # noqa: E402
from tradelab.stocks.timeutil import ET, bars_frame, session_bounds      # noqa: E402

FAMILY = "F3"
CACHE = ROOT / "data" / "stocks" / "p2cache" / "intraday"
TABLE = ROOT / "data" / "stocks" / "p2panels" / "f3_table.pkl"
RESULTS = ROOT / "research" / "phase2" / "results"
SYMBOLS = ["SPY", "QQQ", "IWM", "DIA"]
DEV = ("2016-01-04", "2022-12-30")
HALF_SPREAD = 0.5e-4          # protocol §3 tier for SPY/QQQ/IWM/DIA (assumption; measured sample reported apart)

CONFIGS = {
    "B0": {"symbols": ["SPY"], "predictor": "pc10", "filter": None, "long_only": False},
    "C1": {"symbols": ["SPY"], "predictor": "pc10", "filter": "abs_above_60d_median", "long_only": False},
    "C2": {"symbols": ["SPY"], "predictor": "pc10_and_mid", "filter": None, "long_only": False},
    "C3": {"symbols": SYMBOLS, "predictor": "pc10", "filter": None, "long_only": False},
    "C4": {"symbols": ["SPY"], "predictor": "pc10", "filter": None, "long_only": True},
}


def load_minutes(symbol: str) -> pd.DataFrame:
    rows = []
    for p in sorted(CACHE.glob("1Min_all_*")):
        got = json.loads(gzip.decompress(p.read_bytes()))
        rows.extend(got.get(symbol, []))
    f = bars_frame(rows)
    f.index = f.index.tz_convert(ET)
    return f


def build_table() -> pd.DataFrame:
    out = []
    for sym in SYMBOLS:
        f = load_minutes(sym)
        f["day"] = f.index.strftime("%Y-%m-%d")
        f["hm"] = f.index.strftime("%H:%M")
        reg = f[(f.hm >= "09:30") & (f.hm < "16:00")]
        prev_close = None
        for day, g in reg.groupby("day", sort=True):
            b = session_bounds(day)
            if b is None:
                continue
            half = b[1].tz_convert(ET).strftime("%H:%M") != "16:00"
            row = {"day": day, "symbol": sym, "half_day": half, "c_prev": prev_close}
            def last_before(hm):
                x = g[g.hm < hm]
                return float(x.close.iloc[-1]) if len(x) else np.nan
            row["p10"], row["p12"], row["p1530c"] = last_before("10:00"), last_before("12:00"), last_before("15:30")
            e = g[g.hm >= "15:30"]
            row["entry"] = float(e.open.iloc[0]) if len(e) else np.nan
            row["exit"] = last_before("16:00")
            row["n_bars"] = len(g)
            out.append(row)
            prev_close = float(g.close.iloc[-1])
    t = pd.DataFrame(out)
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_bytes(pickle.dumps(t))
    return t


def signals(t: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Side per (day, symbol): +1 long, -1 short, 0 flat. Uses only prices known at 15:30."""
    t = t.copy()
    t["pc10"] = t.p10 / t.c_prev - 1
    t["mid"] = t.p1530c / t.p12 - 1
    side = np.sign(t["pc10"])
    if cfg["predictor"] == "pc10_and_mid":
        side = np.where(np.sign(t["pc10"]) == np.sign(t["mid"]), side, 0.0)
    if cfg["filter"] == "abs_above_60d_median":
        med = t.groupby("symbol")["pc10"].transform(lambda s: s.abs().rolling(60, min_periods=60).median().shift(1))
        side = np.where(t["pc10"].abs() > med, side, 0.0)
    if cfg["long_only"]:
        side = np.where(np.asarray(side) > 0, 1.0, 0.0)
    t["side"] = np.asarray(side, dtype=float)
    return t


def pnl(t: pd.DataFrame, cfg: dict, slip: float = ev.SLIP_BASE, force_side: float | None = None) -> pd.DataFrame:
    """Daily portfolio P&L: equal weight across the config's symbols; each trade is a same-day round trip."""
    x = t[t.symbol.isin(cfg["symbols"]) & ~t.half_day].dropna(subset=["c_prev", "p10", "p12", "p1530c", "entry", "exit"])
    side = x.side if force_side is None else pd.Series(force_side, index=x.index)
    w = 1.0 / len(cfg["symbols"])
    ret = x.exit / x.entry - 1
    unit = HALF_SPREAD + slip + ev.FEES_PER_SIDE
    d = pd.DataFrame({"day": pd.to_datetime(x.day), "gross": w * side * ret, "cost": w * side.abs() * 2 * unit,
                      "turnover": w * side.abs() * 2, "n_pos": (side != 0).astype(int), "exposure": w * side.abs()})
    g = d.groupby("day").sum()
    g["net"] = g.gross - g.cost
    return g


def window(df: pd.DataFrame, lo: str, hi: str) -> pd.DataFrame:
    return df[(df.index >= lo) & (df.index <= hi)]


def dev() -> dict:
    t = pickle.loads(TABLE.read_bytes()) if TABLE.exists() else build_table()
    t = t[(t.day >= DEV[0]) & (t.day <= DEV[1])]
    skipped = {"half_days": int(t.half_day.sum()),
               "missing_prices": int(t[~t.half_day][["c_prev", "p10", "p12", "p1530c", "entry", "exit"]].isna().any(axis=1).sum())}
    out, quals, metrics = {"family": FAMILY, "window": DEV, "skipped_sessions": skipped, "configs": {}}, {}, {}
    for name, cfg in CONFIGS.items():
        s = signals(t, cfg)
        p = pnl(s, cfg)
        always_long = pnl(s, cfg, force_side=1.0)
        stress = pnl(s, cfg, slip=ev.SLIP_STRESS)
        summ = ev.summarise(p, always_long["net"], always_long["gross"], stress["net"])
        x = s[s.symbol.isin(cfg["symbols"]) & ~s.half_day].dropna(subset=["entry", "exit", "pc10"])
        rs = (x.exit / x.entry - 1)
        summ["diagnosis"] = {
            "trades": int((x.side != 0).sum()),
            "hit_rate_gross": float(((x.side * rs) > 0)[x.side != 0].mean()),
            "corr_predictor_last30": float(np.corrcoef(x.pc10, rs)[0, 1]),
            "gross_bp_per_trade": float((x.side * rs)[x.side != 0].mean() * 1e4),
            "round_trip_cost_bp": float(2 * (HALF_SPREAD + ev.SLIP_BASE + ev.FEES_PER_SIDE) * 1e4),
            "random_sign_control": "expected gross 0; net = -round trip on traded days",
            "by_vol_tercile_gross_bp": _vol_terciles(x),
        }
        q = ev.dev_qualifies(summ, etf_family=True)
        out["configs"][name] = {"params": cfg, "summary": summ, "qualifiers": q}
        quals[name] = q
        metrics[name] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"],
                         "gross_bp_per_trade": summ["diagnosis"]["gross_bp_per_trade"]}
    stages.record_dev(FAMILY, quals, metrics)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "f3_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def _vol_terciles(x: pd.DataFrame) -> dict:
    """Gross per trade by market-volatility tercile (|pc10| as the day's volatility proxy, known at 10:00)."""
    tr = x[x.side != 0].copy()
    tr["g"] = tr.side * (tr.exit / tr.entry - 1)
    tr["terc"] = pd.qcut(tr.pc10.abs(), 3, labels=["low", "mid", "high"])
    return {str(k): float(v * 1e4) for k, v in tr.groupby("terc", observed=True).g.mean().items()}


if __name__ == "__main__":
    if sys.argv[1] == "table":
        print(build_table().groupby("symbol").size())
    elif sys.argv[1] == "dev":
        r = dev()
        for k, v in r["configs"].items():
            s = v["summary"]
            print(k, f"net {s['net']['mean_bp']:.2f}bp/day sharpe {s['net']['sharpe']:.2f} gross/trade "
                     f"{s['diagnosis']['gross_bp_per_trade']:.2f}bp trades {s['diagnosis']['trades']} "
                     f"vs_ctrl {s['vs_control_net_bp']} qual {v['qualifiers']}")
