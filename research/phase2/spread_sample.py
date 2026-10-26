"""Measured NBBO half-spreads at phase-2 execution minutes (PHASE2_PROTOCOL §3: measured inputs where sampled).

    python research/phase2/spread_sample.py 2020-01-02 2022-12-30

40 random development sessions; each session, 32 names drawn point-in-time from four dollar-volume rank bands
(1-100, 101-200, 201-500, 501-1000: 8 each, operating companies, eligibility as F1); minutes 09:31 (proxy for
the market-on-open fill), 15:30 (F3/F4 entry) and 15:59 (closing-quote exit). The quote in force at the end of
the minute (last quote in the final 2 s, else within 60 s), as ORB measured it. Output:
research/phase2/results/spread_sample.json with medians and 90th percentiles by band and minute.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import xs                                           # noqa: E402
from research.phase2.data import Cache, CACHE                             # noqa: E402
from research.phase2.f1_reversal import load_panels                       # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData                            # noqa: E402
from tradelab.stocks.spreads import half_spread_at                        # noqa: E402
from tradelab.stocks.timeutil import quotes_frame, session_bounds         # noqa: E402

BANDS = [(1, 100), (101, 200), (201, 500), (501, 1000)]
MINUTES = ["09:31", "15:30", "15:59"]
OUT = ROOT / "research" / "phase2" / "results" / "spread_sample.json"


def main(lo: str, hi: str, n_days: int = 40, per_band: int = 8, seed: int = 21) -> dict:
    a, r, comp = load_panels()
    elig, dvol = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=1000)
    rank = dvol.where(elig).rank(axis=1, ascending=False)
    days = [d for d in elig.index if pd.Timestamp(lo) <= d <= pd.Timestamp(hi)]
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(len(days) - 1, n_days, replace=False))
    c, cache = AlpacaData.from_env(), Cache(CACHE)
    rows = []
    for i in pick:
        t, day = days[i], days[i + 1]                      # names chosen with information at t, traded on t+1
        ds = day.strftime("%Y-%m-%d")
        b = session_bounds(ds)
        if b is None or b[1].tz_convert("America/New_York").strftime("%H:%M") != "16:00":
            continue
        names = {}
        for lo_r, hi_r in BANDS:
            pool = rank.loc[t][(rank.loc[t] >= lo_r) & (rank.loc[t] <= hi_r)].index.tolist()
            for s in rng.choice(pool, min(per_band, len(pool)), replace=False):
                names[s] = f"{lo_r}-{hi_r}"
        for hm in MINUTES:
            start = pd.Timestamp(f"{ds} {hm}", tz="America/New_York").tz_convert("UTC")
            end = start + pd.Timedelta(minutes=1)
            key = f"spread_{ds}_{hm.replace(':', '')}_{len(names)}"
            got = cache.get("quotes", key)
            if got is None:
                got = {}
                for back in (2, 60):
                    todo = [s for s in names if s not in got]
                    if not todo:
                        break
                    st, part = c.quotes_multi(todo, (end - pd.Timedelta(seconds=back)).to_pydatetime(), end.to_pydatetime())
                    if st != 200:
                        raise RuntimeError(f"quotes failed {ds} {hm}: HTTP {st}")
                    got.update({s: q[-1:] for s, q in part.items() if q})
                cache.put("quotes", key, got)
            for s, band in names.items():
                hs = half_spread_at(quotes_frame(got.get(s, [])), start)
                rows.append({"day": ds, "minute": hm, "symbol": s, "band": band, "status": hs.status,
                             "half_spread_bp": hs.value * 1e4 if hs.value is not None else None})
    df = pd.DataFrame(rows)
    ok = df[df.status == "ok"]
    summary = {f"{m}|{bd}": {"n": int(len(g)), "median_bp": float(g.half_spread_bp.median()),
                             "p90_bp": float(g.half_spread_bp.quantile(0.9))}
               for (m, bd), g in ok.groupby(["minute", "band"])}
    res = {"window": [lo, hi], "sessions": len(set(df.day)), "observations": int(len(df)),
           "valid_share": float((df.status == "ok").mean()), "by_minute_band": summary,
           "note": "measured quoted half-spread (fraction of mid) in force at the end of the minute; slippage excluded"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1))
