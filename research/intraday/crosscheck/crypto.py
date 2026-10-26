"""Replay the crypto test period (2024-01-01 -> 2026-10-24) through the live engine and compare with
the research trade lists. Research manages exits on 1-minute bars (C1); the engine on 5-minute bars."""
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tradelab.intraday.costs import CRYPTO_MAKER_IN, CRYPTO_TAKER
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.replay import replay_bars, trades_frame
from tradelab.intraday.sessions import CryptoSessions
from tradelab.intraday.setups import C1CascadeReversal, C2IntradayMomentum

OUT = ROOT / "research/intraday/crypto/out"


def bars(sym):
    df = pd.read_csv(ROOT / "data/crypto_intraday" / f"{sym}_5m.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["open", "high", "low", "close", "volume"]]


def run(name, setup_cls, syms, costs, research_file):
    frames = {s: bars(s) for s in syms}
    L = IntradayLimits(market="crypto", max_positions=len(syms), max_weight=0.25, max_gross=1.0,
                       daily_loss_limit=0.99, max_entries_per_day=50)
    eng = Engine(L, [setup_cls(frames)], {name: costs}, CryptoSessions(), 100_000.0)
    replay_bars(eng, frames, timedelta(minutes=5), CryptoSessions(), start="2024-01-01", end="2026-10-25")
    e = trades_frame(eng)
    r = pd.read_csv(OUT / research_file)
    # key: symbol + the signal hour (research entry may be on a later minute than the engine's 5m bar)
    e["key"] = e.symbol + "|" + pd.to_datetime(e.entry_time, utc=True).dt.floor("h").astype(str)
    r["key"] = r.symbol + "|" + pd.to_datetime(r.entry_time_utc, utc=True).dt.floor("h").astype(str)
    m = e.merge(r, on="key", suffixes=("_eng", "_res"))
    res = {"label": name, "engine_trades": len(e), "research_trades": len(r), "matched": len(m),
           "match_rate_vs_research": round(len(m) / max(1, len(r)), 4),
           "engine_mean_net_pct": round(e.net_ret.mean() * 100, 4), "research_mean_net_pct": round(r.net_ret.mean() * 100, 4),
           "matched_mean_net_eng_pct": round(m.net_ret_eng.mean() * 100, 4), "matched_mean_net_res_pct": round(m.net_ret_res.mean() * 100, 4),
           "matched_net_corr": round(float(np.corrcoef(m.net_ret_eng, m.net_ret_res)[0, 1]), 4) if len(m) > 2 else None,
           "matched_same_exit_reason": round(float((m.exit_reason_eng == m.exit_reason_res).mean()), 4) if len(m) else None,
           "engine_only": e[~e.key.isin(r.key)].key.tolist()[:20], "research_only": r[~r.key.isin(e.key)].key.tolist()[:20],
           "n_engine_only": int((~e.key.isin(r.key)).sum()), "n_research_only": int((~r.key.isin(e.key)).sum())}
    return res


if __name__ == "__main__":
    results = [run("C1", C1CascadeReversal, ["BTC-USD", "ETH-USD", "SOL-USD"], CRYPTO_MAKER_IN, "test_trades_C1_C1_k4_maker.csv"),
               run("C2", C2IntradayMomentum, ["BTC-USD", "ETH-USD"], CRYPTO_TAKER, "test_trades_C2_C2_m1.5.csv")]
    (ROOT / "research/intraday/crosscheck/crypto.json").write_text(json.dumps(results, indent=1, default=str))
    for r in results:
        print(json.dumps(r, default=str))
