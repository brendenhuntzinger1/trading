"""Audit of the ORB development benchmark that looked strong: "direction-only" (stocks in play, enter at 09:35 in
the first 5-minute candle's direction, hold to the close, no stop). It is a BENCHMARK from the development window,
not a candidate (ORB B10). This audit decides only whether it is worth a separately registered test on unread data.

Reads data/stocks/frames/dev_primary_*_of_*.pkl (research/orb/dump_dev_frames.py) and writes
research/orb/audits/direction_lead_dev.json.

Incident 20: the first version of this audit (direction_lead_dev_LOOKAHEAD.json) ran on frames whose direction-only
benchmark had been recorded only when the breakout later triggered. The frames are now regenerated without that
conditioning, and the decomposition is reported against the corrected benchmark.
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
from research.orb import evaluate as ev                          # noqa: E402

FRAMES = ROOT / "data" / "stocks" / "frames"
CACHE = ROOT / "data" / "stocks" / "cache"


def load(name: str) -> pd.DataFrame:
    parts = [pickle.loads(p.read_bytes())[name] for p in sorted(FRAMES.glob("dev_primary_*_of_*.pkl"))]
    return pd.concat([p for p in parts if len(p)], ignore_index=True)


def summary(f: pd.DataFrame, days: list[str]) -> dict:
    bp = lambda x: float(np.nanmean(x) * 1e4)
    daily = ev.daily(f, days, "net_all")
    w_pnl = f.weight * f.net_all
    s = w_pnl.sort_values(ascending=False)
    k1, k5 = max(1, len(s) // 100), max(1, len(s) // 20)
    by_sym = w_pnl.groupby(f.symbol).sum().sort_values(ascending=False)
    by_day = (f.weight * f.net_all).groupby(f.day).sum().sort_values(ascending=False)
    return {
        "trades": int(len(f)), "days_with_trades": int(f.day.nunique()),
        "gross_bp": bp(f.gross), "cost_bp": bp(f.cost_total), "net_bp": bp(f.net_all),
        "median_net_bp": float(np.nanmedian(f.net_all) * 1e4), "hit_rate_net": float((f.net_all > 0).mean()),
        "measured_spread_share": float(f.spread_cost.notna().mean()),
        "portfolio_net": ev.series_stats(daily),
        "share_of_pnl_top1pct_trades": float(s.iloc[:k1].sum() / s.sum()) if s.sum() else None,
        "share_of_pnl_top5pct_trades": float(s.iloc[:k5].sum() / s.sum()) if s.sum() else None,
        "net_bp_without_top1pct_trades": bp(f.loc[~f.index.isin(s.index[:k1]), "net_all"]),
        "net_bp_without_top5pct_trades": bp(f.loc[~f.index.isin(s.index[:k5]), "net_all"]),
        "top10_symbols_share": float(by_sym.head(10).sum() / by_sym.sum()) if by_sym.sum() else None,
        "top10_symbols": {k: round(float(v), 4) for k, v in by_sym.head(10).items()},
        "top10_days_share": float(by_day.head(10).sum() / by_day.sum()) if by_day.sum() else None,
        "by_year_net_bp": {str(y): bp(g.net_all) for y, g in f.groupby(f.day.str[:4])},
        "by_half_net_bp": {h: bp(g.net_all) for h, g in f.groupby(f.day.str[:4] + "H" + np.where(f.day.str[5:7] <= "06", "1", "2"))},
        "meme_names_trades": int(f.symbol.isin(["GME", "AMC", "BB", "NOK", "KOSS", "EXPR", "BBBY"]).sum()),
        "net_bp_excluding_meme_names": bp(f.loc[~f.symbol.isin(["GME", "AMC", "BB", "NOK", "KOSS", "EXPR", "BBBY"]), "net_all"]),
    }


def main():
    rule, direction, basket = load("rule"), load("direction"), load("basket")
    days = sorted(set(basket.day))
    master = {a["symbol"] for a in json.loads(gzip.decompress((CACHE / "assets" / "us_equity_all.json.gz").read_bytes()))}
    out = {
        "what": "ORB development 2020-01-02..2021-12-31 (inside the paper's 2016-2023 sample); primary filters "
                "(RV>=1, top 20, 1x cap). Benchmarks are not candidates (B10). Direction-only corrected for incident "
                "20: entered at 09:35 on every non-doji long-eligible stock-day, whether or not the breakout came.",
        "direction_only": summary(direction, days),
        "basket_long_all_selected": summary(basket, days),
        "rule_primary": summary(rule, days),
        "direction_trades_in_names_absent_from_asset_master": int((~direction.symbol.isin(master)).sum()),
        "paired_daily_net": {
            "rule_minus_direction": ev.paired_ci(ev.daily(rule, days, "net_all"), ev.daily(direction, days, "net_all")),
            "rule_nostop_minus_direction (entry-trigger value)": ev.paired_ci(
                ev.daily(load("rule_nostop"), days, "net_all"), ev.daily(direction, days, "net_all")),
            "direction_minus_basket": ev.paired_ci(ev.daily(direction, days, "net_all"),
                                                   ev.daily(basket, days, "net_all"))},
    }
    p = ROOT / "research" / "orb" / "audits" / "direction_lead_dev.json"
    p.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
