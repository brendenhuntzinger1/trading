"""F2: earnings-announcement drift with headline surprise (research/phase2/FAMILIES.md).

    python research/phase2/f2_earnings_drift.py dev

Events: the first earnings-like Benzinga headline per symbol within 10 calendar days (cache from f2_news_fetch.py).
    EPS verdict: Beat / Miss / In-line, parsed from the headline; sales verdict where present.
Reaction session R: the first regular session that STARTS after the headline time (a headline at 08:00 ET -> that
    day; at 16:05 ET -> next session; during a session -> next session).
EAR: open-to-close return of R (`all` adjustment). Eligibility: top-1,000 liquid operating company at the close of R.
Entry: market-on-open the session after R; hold H sessions (5; C2: 20); exit at the open after the last held day.
Sizing: 5% per position (max 20 concurrent; later events skipped while full, first by headline time).
Control: the same daily gross exposure spread equally over every eligible name (same open-to-open windows).
Costs (Amendment 1): measured 09:31 band-median half-spreads + slippage + fees, on entry and exit.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import evaluate as ev                               # noqa: E402
from research.phase2 import stages, xs                                    # noqa: E402
from research.phase2.data import CACHE                                    # noqa: E402
from research.phase2.f1_reversal import load_panels, open_to_open_with_exit   # noqa: E402
from tradelab.stocks.timeutil import ET, session_bounds                   # noqa: E402

FAMILY = "F2"
RESULTS = ROOT / "research" / "phase2" / "results"
DEV = ("2020-01-02", "2022-12-30")
SLOT = 0.05
MAXPOS = 20
CONFIGS = {
    "B0": {"select": "beat_ear_pos", "hold": 5, "band": None},
    "C1": {"select": "ear_top_quintile", "hold": 5, "band": None},
    "C2": {"select": "beat_ear_pos", "hold": 20, "band": None},
    "C3": {"select": "beat_both_ear_pos", "hold": 5, "band": None},
    "C4": {"select": "beat_ear_pos", "hold": 5, "band": (201, 1000)},
}
EPS_RX = re.compile(r"\bEPS\b[^,]*?\b(Beats?|Miss(?:es)?|In-?Line|Inline)\b", re.I)
SALES_RX = re.compile(r"\b(Sales|Revenue)\b[^,]*?\b(Beats?|Miss(?:es)?|In-?Line|Inline)\b", re.I)


def verdict(word: str | None) -> str | None:
    if not word:
        return None
    w = word.lower()
    return "beat" if w.startswith("beat") else ("miss" if w.startswith("miss") else "inline")


def load_events(lo: str, hi: str) -> pd.DataFrame:
    rows = []
    for p in (CACHE / "news").glob("earn_*"):
        for h in json.loads(gzip.decompress(p.read_bytes())):
            m, s = EPS_RX.search(h["headline"]), SALES_RX.search(h["headline"])
            for sym in h["symbols"]:
                rows.append({"symbol": sym, "time": pd.Timestamp(h["created_at"]), "eps": verdict(m.group(1) if m else None),
                             "sales": verdict(s.group(2) if s else None), "headline": h["headline"]})
    e = pd.DataFrame(rows).drop_duplicates(["symbol", "time", "headline"]).sort_values(["symbol", "time"])
    e = e[e.eps.notna()]
    keep, last = [], {}
    for r in e.itertuples():
        if r.symbol in last and r.time - last[r.symbol] < pd.Timedelta(days=10):
            continue
        last[r.symbol] = r.time
        keep.append(r.Index)
    e = e.loc[keep]
    return e[(e.time >= pd.Timestamp(lo, tz="UTC")) & (e.time <= pd.Timestamp(hi, tz="UTC") + pd.Timedelta(days=1))]


def reaction_session(t: pd.Timestamp, sessions: pd.DatetimeIndex) -> pd.Timestamp | None:
    """First session whose regular open is after t."""
    for d in sessions[sessions >= t.tz_convert(ET).normalize().tz_localize(None)][:5]:
        b = session_bounds(d.strftime("%Y-%m-%d"))
        if b is not None and b[0] > t:
            return d
    return None


def dev() -> dict:
    a, r, comp = load_panels()
    elig, dvol = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=1000)
    rank = dvol.where(elig).rank(axis=1, ascending=False)
    sessions = elig.index
    ev_all = load_events(DEV[0], DEV[1])
    ear_all = a["close"] / a["open"] - 1
    recs = []
    for e in ev_all.itertuples():
        if e.symbol not in elig.columns:
            continue
        R = reaction_session(e.time, sessions)
        if R is None or not elig.at[R, e.symbol]:
            continue
        i = sessions.get_loc(R)
        if i + 1 >= len(sessions):
            continue
        recs.append({"symbol": e.symbol, "time": e.time, "R": R, "entry": sessions[i + 1], "eps": e.eps, "sales": e.sales,
                     "ear": float(ear_all.at[R, e.symbol]), "rank": float(rank.at[R, e.symbol])})
    E = pd.DataFrame(recs)
    E["ear_q"] = E.groupby("R").ear.rank(pct=True)
    ret = open_to_open_with_exit({"open": a["open"][elig.columns], "close": a["close"][elig.columns]})
    hs = ev.measured_half_spread(dvol, elig, "09:31").shift(1)
    keep = (sessions >= pd.Timestamp(DEV[0])) & (sessions <= pd.Timestamp(DEV[1]))
    out = {"family": FAMILY, "window": DEV, "events_parsed": int(len(ev_all)), "events_eligible": int(len(E)),
           "eps_verdicts": E.eps.value_counts().to_dict(), "configs": {}}
    quals, metrics = {}, {}
    for name, cfg in CONFIGS.items():
        sel = E.copy()
        if cfg["select"] == "beat_ear_pos":
            sel = sel[(sel.eps == "beat") & (sel.ear > 0)]
        elif cfg["select"] == "beat_both_ear_pos":
            sel = sel[(sel.eps == "beat") & (sel.sales == "beat") & (sel.ear > 0)]
        elif cfg["select"] == "ear_top_quintile":
            sel = sel[sel.ear_q > 0.8]
        if cfg["band"]:
            sel = sel[(sel["rank"] >= cfg["band"][0]) & (sel["rank"] <= cfg["band"][1])]
        w = pd.DataFrame(0.0, index=sessions, columns=elig.columns)
        held = pd.Series(0, index=sessions)
        taken = skipped = 0
        for e in sel.sort_values("time").itertuples():
            i = sessions.get_loc(e.entry)
            span = sessions[i:i + cfg["hold"]]
            if (held.loc[span] >= MAXPOS).any():
                skipped += 1
                continue
            if pd.isna(a["open"].at[e.entry, e.symbol]):
                skipped += 1
                continue
            w.loc[span, e.symbol] += SLOT
            held.loc[span] += 1
            taken += 1
        p = ev.backtest_weights(w[keep], ret[keep], hs[keep])
        ps = ev.backtest_weights(w[keep], ret[keep], hs[keep], slip=ev.SLIP_STRESS)
        expo = w[keep].sum(axis=1)
        e_ = elig[keep].astype(float)
        cw = e_.div(e_.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0).mul(expo, axis=0)
        cw = cw.where(a["open"][elig.columns][keep].notna(), 0.0)
        cp = ev.backtest_weights(cw, ret[keep], hs[keep])
        summ = ev.summarise(p, cp["net"], cp["gross"], ps["net"])
        pos_ret = (w[keep] * ret[keep].fillna(0)).sum(axis=1)
        summ["diagnosis"] = {"events_selected": int(len(sel)), "positions_taken": taken, "skipped_full_or_no_open": skipped,
                             "avg_concurrent": float(held[keep].mean()),
                             "gross_bp_per_position_day": float(pos_ret.sum() / max(1e-9, expo.sum()) * 1e4),
                             "control_gross_bp_per_exposure_day": float(cp.gross.sum() / max(1e-9, expo.sum()) * 1e4)}
        q = ev.dev_qualifies(summ)
        out["configs"][name] = {"params": cfg, "summary": summ, "qualifiers": q}
        quals[name] = q
        metrics[name] = {"net_mean_bp": summ["net"]["mean_bp"], "net_sharpe": summ["net"]["sharpe"],
                         "gross_vs_control_bp": summ["vs_control_gross_bp"]["mean"], "positions": taken}
    stages.record_dev(FAMILY, quals, metrics)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "f2_dev.json").write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    r = dev()
    print({k: r[k] for k in ("events_parsed", "events_eligible", "eps_verdicts")})
    for k, v in r["configs"].items():
        s = v["summary"]
        print(k, f"net {s['net']['mean_bp']:.2f}bp/day gross {s['gross']['mean_bp']:.2f} vs_ctrl_gross {s['vs_control_gross_bp']} "
                 f"vs_ctrl_net {s['vs_control_net_bp']} diag {s['diagnosis']} years "
                 f"{ {y: round(x * 1e4) for y, x in s['by_year_net'].items()} } qual {v['qualifiers']}")
