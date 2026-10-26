"""S2X single evaluation run (S2X_PREREGISTRATION.md). Refuses to run twice."""
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research/intraday/audit"))
from tradelab.intraday import yahoo
from tradelab.intraday.costs import Costs, STOCK_AT_OPEN
from tradelab.intraday.engine import Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.replay import replay_daily_open_close, trades_frame
from tradelab.intraday.sessions import StockSessions
from tradelab.intraday.setups import S2GapReversal
from tradelab.research.metrics import psr, stationary_bootstrap_idx
from tradelab.research.registry import record
from dsr_audit import sr0

OUT, DATA = Path(__file__).parent, ROOT / "data/s2x"
DONE = OUT / "test_done.json"
PRIMARY = ["EFA", "EEM", "VWO", "EWJ", "EWZ", "FXI", "EWG", "EWU", "EWC", "EWY", "EWT", "EWA", "EWH", "EWW",
           "SMH", "XBI", "IBB", "KRE", "KBE", "XOP", "OIH", "XME", "XRT", "XHB", "ITB", "GDX", "GDXJ", "IYR", "VNQ"]
SECONDARY = ["TLT", "IEF", "HYG", "LQD", "GLD", "SLV", "USO"]
START, END = "2016-01-01", "2026-10-24"
S = StockSessions()


def fetch(sym):
    p = DATA / f"{sym}.csv"
    if not p.exists():
        df = yahoo.bars(sym, "1d", "period1=1420070400&period2=1792800000")    # 2015-01-01 -> 2026-10 (warm-up for 20d volume)
        df.attrs.clear(); df.to_csv(p); time.sleep(0.3)
    d = pd.read_csv(p, index_col=0); d.index = d.index.astype(str)
    return d


def run(universe, data, cost):
    L = IntradayLimits(market="stocks", max_positions=5, max_weight=0.2, max_gross=1.0, daily_loss_limit=0.99,
                       max_entries_per_day=10, no_entries_last_minutes=0)
    eng = Engine(L, [S2GapReversal({s: data[s] for s in universe + ["SPY"]})], {"S2": cost}, S, 100_000.0)
    replay_daily_open_close(eng, {s: data[s] for s in universe + ["SPY"]}, S, start=START, end=END)
    t = trades_frame(eng)
    t["day"] = [S.day_key(x) for x in t.entry_time]
    return t


def day_series(t, col):
    pnl = (t.qty * t.entry_px / 100_000.0 * t[col]).groupby(t.day).sum()        # weight x return, flat overnight
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(START, END) if S.bounds(d.strftime("%Y-%m-%d"))]
    return pnl.reindex(days, fill_value=0.0)


def boot_mean_ci(t, col, n=2000, seed=5):
    g = t.groupby("day")[col]
    sums, cnt = g.sum().to_numpy(), g.count().to_numpy()
    rng = np.random.default_rng(seed)
    est = [sums[i].sum() / cnt[i].sum() for i in (stationary_bootstrap_idx(len(sums), 5, rng) for _ in range(n))]
    return float(np.quantile(est, 0.05)), float(np.quantile(est, 0.95)), float(np.quantile(est, 0.025)), float(np.quantile(est, 0.975))


def placebo(t, pool, data, reps=1000, seed=9):
    """Same number of trades per day, drawn at random from that day's eligible ETFs; open->close gross."""
    rng = np.random.default_rng(seed)
    per_day = t.groupby("day").size()
    oc = {s: (data[s].close / data[s].open - 1) for s in pool}
    means = []
    for _ in range(reps):
        vals = []
        for day, k in per_day.items():
            cands = [oc[s][day] for s in pool if day in oc[s].index and np.isfinite(oc[s][day])]
            if cands:
                vals += list(rng.choice(cands, size=min(k, len(cands)), replace=False))
        means.append(np.mean(vals))
    return float(np.mean(np.array(means) >= t.gross_ret.mean())), float(np.mean(means))


def evaluate(t, data, pool, label):
    net = day_series(t, "net_ret")
    sr = net.mean() / net.std()
    lo90, hi90, lo95, hi95 = boot_mean_ci(t, "gross_ret")
    nlo90, _, _, _ = boot_mean_ci(t, "net_ret")
    thirds = [float(x.sum()) for x in np.array_split(net, 3)]
    gross = t.gross_ret
    stress_net = (gross - 0.0024).mean()
    open_net = (gross - 0.0013).mean()
    p_placebo, placebo_mean = placebo(t, pool, data)
    dsr = psr(net, sr0(92, 1 / (len(net) - 1)))
    E = {"E1 net lower 5% > 0": nlo90 > 0, "E2 Sharpe >= 0.5": sr * math.sqrt(252) >= 0.5,
         "E3 stress & open-spread net > 0": stress_net > 0 and open_net > 0, "E4 >=2 of 3 thirds > 0": sum(x > 0 for x in thirds) >= 2,
         "E5 placebo p < 0.05": p_placebo < 0.05, "E6 DSR >= 0.95": dsr >= 0.95, "E7 trades >= 100": len(t) >= 100}
    verdict = "PASS" if all(E.values()) else ("REJECT (no useful effect)" if hi95 < 0.0008 else "INCONCLUSIVE")
    return {"label": label, "trades": len(t), "days_traded": int(t.day.nunique()), "symbols_traded": int(t.symbol.nunique()),
            "gross_bp": round(gross.mean() * 1e4, 1), "gross_90ci_bp": [round(lo90 * 1e4, 1), round(hi90 * 1e4, 1)],
            "gross_95_upper_bp": round(hi95 * 1e4, 1), "gross_signal_replicates (90% CI > 0)": lo90 > 0,
            "net_bp_base8": round(t.net_ret.mean() * 1e4, 1), "net_lower5_bp": round(nlo90 * 1e4, 1),
            "net_bp_open13": round(open_net * 1e4, 1), "net_bp_stress24": round(stress_net * 1e4, 1),
            "sharpe_annual_net": round(sr * math.sqrt(252), 2), "thirds": [round(x, 4) for x in thirds],
            "placebo_p": round(p_placebo, 3), "placebo_mean_gross_bp": round(placebo_mean * 1e4, 1),
            "DSR_null_var_N92": round(dsr, 3), "criteria": E, "verdict": verdict}


def reproduce():
    """Deterministic reproduction of the frozen test from archived data. Not a new evaluation: it fits
    nothing, changes nothing and is logged as a reproduction. Exits non-zero on any difference."""
    for s in PRIMARY + SECONDARY + ["SPY"]:
        if not (DATA / f"{s}.csv").exists():
            raise SystemExit(f"archived data missing for {s}; restore the data archive first (data/README.md)")
    data = {s: fetch(s) for s in PRIMARY + SECONDARY + ["SPY"]}
    recorded = json.loads((OUT / "result.json").read_text())
    diffs = []
    for label, uni in (("primary_equity", PRIMARY), ("secondary_bond_commodity", SECONDARY)):
        now = evaluate(run(uni, data, STOCK_AT_OPEN), data, uni, label)
        for k in ("trades", "gross_bp", "gross_90ci_bp", "net_bp_base8", "sharpe_annual_net", "placebo_p", "verdict"):
            if json.dumps(now[k], default=str) != json.dumps(recorded[label][k], default=str):
                diffs.append((label, k, recorded[label][k], now[k]))
    record("reproduction", "s2x_test_reproduction", {"prereg": "prereg_s2x"}, f"{START}..{END}",
           "deterministic reproduction of a frozen test (no fitting, no new evaluation)", metrics={"differences": len(diffs)})
    print("REPRODUCED IDENTICALLY" if not diffs else f"DIFFERENCES: {diffs}")
    raise SystemExit(1 if diffs else 0)


if __name__ == "__main__":
    if "--reproduce" in sys.argv:
        reproduce()
    if DONE.exists():
        raise SystemExit(f"S2X test already ran at {json.loads(DONE.read_text())['at']}; refusing to run twice")
    DONE.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "status": "started"}))
    data = {s: fetch(s) for s in PRIMARY + SECONDARY + ["SPY"]}
    res = {}
    for label, uni in (("primary_equity", PRIMARY), ("secondary_bond_commodity", SECONDARY)):
        t = run(uni, data, STOCK_AT_OPEN)
        t.to_csv(OUT / f"trades_{label}.csv", index=False)
        res[label] = evaluate(t, data, uni, label)
    # pooled reading with the already-seen S2-ETF test trades (labelled; not a pass criterion)
    old = pd.read_csv(ROOT / "research/intraday/stocks/out/test_trades_S2_etf_only_thr1_top5.csv").rename(columns={"session": "day"})
    new = pd.read_csv(OUT / "trades_primary_equity.csv")
    pooled = pd.concat([old[["day", "gross_ret", "net_ret"]], new[["day", "gross_ret", "net_ret"]]])
    lo90, hi90, _, _ = boot_mean_ci(pooled, "gross_ret"); nlo, nhi, _, _ = boot_mean_ci(pooled, "net_ret")
    res["pooled_with_seen_S2_ETF (not a pass criterion)"] = {"trades": len(pooled), "gross_bp": round(pooled.gross_ret.mean() * 1e4, 1),
        "gross_90ci_bp": [round(lo90 * 1e4, 1), round(hi90 * 1e4, 1)], "net_bp": round(pooled.net_ret.mean() * 1e4, 1),
        "net_90ci_bp": [round(nlo * 1e4, 1), round(nhi * 1e4, 1)]}
    res["data_fetched_at"] = datetime.now(timezone.utc).isoformat()
    (OUT / "result.json").write_text(json.dumps(res, indent=1, default=str))
    DONE.write_text(json.dumps({"at": res["data_fetched_at"], "status": "done"}))
    record("result", "s2x_test", {"prereg": "prereg_s2x"}, f"{START}..{END}", "out-of-universe replication (single run)",
           metrics={k: {kk: vv for kk, vv in v.items() if kk != "criteria"} if isinstance(v, dict) else v for k, v in res.items()})
    print(json.dumps(res, indent=1, default=str))
