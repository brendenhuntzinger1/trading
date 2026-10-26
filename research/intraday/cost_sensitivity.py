"""Recompute each test-period trade list's result across round-trip costs, from gross returns.
Daily P&L = sum over the day's trades of weight x net return (positions are flat overnight)."""
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STOCK = ROOT / "research/intraday/stocks/out"
CRYPTO = ROOT / "research/intraday/crypto/out"


def evaluate(path: Path, roundtrips_bp, day_col, year_days):
    t = pd.read_csv(path)
    w = t.size_weight if "size_weight" in t else pd.Series(1.0, index=t.index)
    day = t[day_col].astype(str).str[:10]
    n_days = None
    rows = []
    for rt in roundtrips_bp:
        net = t.gross_ret - rt / 1e4
        pnl = (w * net).groupby(day).sum()
        span = pd.date_range(day.min(), day.max(), freq="D" if year_days == 365 else "B")
        pnl = pnl.reindex(span.strftime("%Y-%m-%d"), fill_value=0.0)
        sr = pnl.mean() / pnl.std() * math.sqrt(year_days) if pnl.std() > 0 else 0.0
        rows.append({"roundtrip_bp": rt, "mean_net_per_trade_pct": round(net.mean() * 100, 4),
                     "hit_rate": round((net > 0).mean(), 3), "daily_sharpe": round(sr, 2),
                     "total_return_pct": round(((1 + pnl).prod() - 1) * 100, 1)})
    return {"file": path.name, "trades": len(t), "gross_mean_pct": round(t.gross_ret.mean() * 100, 4),
            "breakeven_roundtrip_bp": round(t.gross_ret.mean() * 1e4, 1), "grid": rows}


if __name__ == "__main__":
    out = {}
    stock_grid = [0, 4, 8, 12, 16, 24, 30]                 # bp round trip
    for f in sorted(STOCK.glob("test_trades_*.csv")):
        out[f.name] = evaluate(f, stock_grid, "session", 252)
    crypto_grid = [36, 80, 106, 132, 150, 180, 240]        # bp round trip (see COSTS.md for what each represents)
    for f in sorted(CRYPTO.glob("test_trades_*.csv")) if CRYPTO.exists() else []:
        out[f.name] = evaluate(f, crypto_grid, "entry_time_utc", 365)
    (ROOT / "research/intraday/cost_sensitivity.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(f"\n{k}: trades {v['trades']}, gross {v['gross_mean_pct']}%/trade, break-even round trip {v['breakeven_roundtrip_bp']} bp")
        print(pd.DataFrame(v["grid"]).to_string(index=False))
