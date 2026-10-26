"""H3: first-candle continuation on US stocks in play. Pre-registration: H3_PREREGISTRATION.md.

    python research/h3/study.py fetch 2022        # one validation year per process (warms the cache, saves frames)
    python research/h3/study.py fetch 2023
    python research/h3/study.py validation        # qualifiers from the saved frames
    python research/h3/study.py final             # refuses unless H3-L qualified and is frozen

Reuses ORB's simulator and data source (same universe, filters, fills and cost model); only the decision rule
(enter at 09:35 in the first candle's direction, hold to the close) and the equal-weight sizing are H3's own.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.orb import evaluate as ev                          # noqa: E402
from research.orb import study as orb_study                      # noqa: E402
from tradelab.research import consumed                           # noqa: E402
from tradelab.research.registry import record                    # noqa: E402

SCOPE = "stocks.us.intraday.first_candle"
PERIODS = {"validation": ("2022-01-03", "2023-12-29"), "final": ("2024-01-02", "2026-07-24")}
SLOT_WEIGHT = 1 / 20                         # equal weight, top 20 slots, gross <= 1x
FRAMES = ROOT / "data" / "stocks" / "h3_frames"
RESULTS = ROOT / "research" / "h3" / "results"
CONSUMED_LEDGER = consumed.LEDGER


def fetch(year: str, source=None) -> Path:
    """Run ORB's period loop on one validation year with the primary and long/short configs; save frames."""
    start, end = PERIODS["validation"]
    lo, hi = max(start, f"{year}-01-01"), min(end, f"{year}-12-31")
    consumed.mark_consumed(SCOPE, *PERIODS["validation"], "H3 validation", "marked before the first read",
                           path=CONSUMED_LEDGER)
    if source is None:
        from research.orb.audit_mechanics import DaysSource
        from research.orb.data import AlpacaSource
        from tradelab.pit.alpaca_sip import AlpacaData
        inner = AlpacaSource(AlpacaData.from_env(), start, end)
        source = DaysSource(inner, [d for d in inner.days(lo, hi) if not orb_study.excluded(d)])
    out = orb_study.run_period(source, "validation", ["primary", "long_short"], placebo_reps=1)
    FRAMES.mkdir(parents=True, exist_ok=True)
    p = FRAMES / f"validation_{year}.pkl"
    p.write_bytes(pickle.dumps({k: out["configs"][k]["_frames"] for k in ("primary", "long_short")}))
    return p


def _load(config: str, name: str) -> pd.DataFrame:
    parts = [pickle.loads(p.read_bytes())[config][name] for p in sorted(FRAMES.glob("validation_*.pkl"))]
    f = pd.concat([x for x in parts if len(x)], ignore_index=True) if parts else pd.DataFrame()
    return f.assign(weight=SLOT_WEIGHT) if len(f) else f


def stats(f: pd.DataFrame, days: list[str]) -> dict:
    bp = lambda x: float(np.nanmean(x) * 1e4)
    s = (f.weight * f.net_all).sort_values(ascending=False)
    k5 = max(1, len(s) // 20)
    by_sym = (f.weight * f.net_all).groupby(f.symbol).sum().sort_values(ascending=False)
    by_day = (f.weight * f.net_all).groupby(f.day).sum().sort_values(ascending=False)
    return {"trades": int(len(f)), "gross_bp": bp(f.gross), "cost_bp": bp(f.cost_total), "net_bp": bp(f.net_all),
            "net_spread_bp": bp(f.net_spread), "median_net_bp": float(np.nanmedian(f.net_all) * 1e4),
            "hit_rate": float((f.net_all > 0).mean()), "measured_spread_share": float(f.spread_cost.notna().mean()),
            "net_per_trade_ci90": ev.trade_mean_ci(f, "net_all", days),
            "net_bp_without_top5pct": bp(f.loc[~f.index.isin(s.index[:k5]), "net_all"]),
            "by_year_net_bp": {y: bp(g.net_all) for y, g in f.groupby(f.day.str[:4])},
            "top10_symbols_share": float(by_sym.head(10).sum() / by_sym.sum()) if by_sym.sum() else None,
            "top10_days_share": float(by_day.head(10).sum() / by_day.sum()) if by_day.sum() else None,
            "portfolio_net": ev.series_stats(ev.daily(f, days, "net_all"))}


def validation() -> dict:
    h3 = _load("primary", "direction")
    basket = _load("primary", "basket")
    ls = _load("long_short", "direction")
    if h3.empty:
        sys.exit("no validation frames: run `fetch 2022` and `fetch 2023` first")
    days = sorted(set(basket.day))
    d_h3, d_bk = ev.daily(h3, days, "net_all"), ev.daily(basket, days, "net_all")
    # matched exposure: scale the basket to H3's daily gross exposure
    exp_h3 = h3.groupby("day").weight.sum().reindex(days, fill_value=0.0)
    exp_bk = basket.groupby("day").weight.sum().reindex(days, fill_value=0.0)
    d_bk_matched = d_bk * (exp_h3 / exp_bk.replace(0, np.nan)).fillna(0.0)
    vs_basket = ev.paired_ci(d_h3, d_bk_matched)
    out = {"H3-L": stats(h3, days), "H3-LS (labelled)": stats(ls, days) if len(ls) else None,
           "basket": stats(basket, days), "vs_basket_matched_daily": vs_basket, "sessions": len(days)}
    s = out["H3-L"]
    trade_ci = s["net_per_trade_ci90"]["ci"]
    q = {"net_lower_bound_gt_0": trade_ci[0] is not None and trade_ci[0] > 0,
         "beats_basket_matched": vs_basket["ci"][0] is not None and vs_basket["ci"][0] > 0,
         "both_years_positive": all(v > 0 for v in s["by_year_net_bp"].values()) and len(s["by_year_net_bp"]) == 2,
         "positive_without_top5pct": s["net_bp_without_top5pct"] > 0}
    q["qualified"] = all(q.values())
    out["qualifiers"] = q
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "validation.json").write_text(json.dumps(out, indent=1, default=float))
    record("result", "h3_validation", {"prereg": "prereg_h3"}, "..".join(PERIODS["validation"]), "H3 validation",
           metrics={"qualifiers": q, "net_bp": s["net_bp"], "trades": s["trades"]})
    return out


def final() -> None:
    p = RESULTS / "validation.json"
    if not p.exists() or not json.loads(p.read_text())["qualifiers"]["qualified"]:
        record("result", "h3_stop_after_validation", {}, "..".join(PERIODS["final"]),
               "H3-L did not qualify; final window stays unread; research budget spent")
        sys.exit("H3-L did not qualify in validation: the final window stays UNREAD (H3_PREREGISTRATION.md)")
    sys.exit("H3-L qualified: freeze by hash, then implement the final phase per the pre-registration")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["fetch", "validation", "final"])
    ap.add_argument("year", nargs="?")
    a = ap.parse_args(argv)
    if a.phase == "fetch":
        print(fetch(a.year))
    elif a.phase == "validation":
        print(json.dumps(validation()["qualifiers"], indent=1))
    else:
        final()


if __name__ == "__main__":
    main()
