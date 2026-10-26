"""Data gates B7.1-B7.5 of ORB_PREREGISTRATION.md (Amendment 1), run against Alpaca with a PAPER key.

Every number in the report comes from an API response; nothing is filled in by assumption. A gate that could not
be evaluated is reported as pass=False with the reason. Read-only market-data endpoints only."""
from __future__ import annotations

import random
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tradelab.pit.alpaca_sip import AlpacaData, verify_entitlement, verify_paper_key
from tradelab.stocks import orb
from tradelab.stocks.spreads import half_spread_at, measure_day, summarize
from tradelab.stocks.timeutil import ET, bars_frame, quotes_frame, session_bounds, session_days, to_et

# Known delisted / acquired names: (symbol, last regular trading day as best known, confidence).
# The check uses sessions ending 30 days BEFORE that date, so a date that is off by a few days does not matter.
DELISTED = [
    ("TWTR", "2022-10-27", "high: acquisition closed 2022-10-27"),
    ("XLNX", "2022-02-11", "high: acquired by AMD 2022-02-14"),
    ("ATVI", "2023-10-12", "high: acquired by Microsoft 2023-10-13"),
    ("VMW", "2023-11-21", "high: acquired by Broadcom 2023-11-22"),
    ("SIVB", "2023-03-09", "medium: halted 2023-03-10, later delisted"),
    ("FRC", "2023-04-28", "medium: bank seized 2023-05-01"),
    ("BBBY", "2023-05-02", "low: Nasdaq delisting around early May 2023"),
    ("CTXS", "2022-09-29", "medium: taken private 2022-09-30"),
    ("CERN", "2022-06-07", "medium: acquired by Oracle 2022-06-08"),
    ("SGEN", "2023-12-13", "medium: acquired by Pfizer 2023-12-14"),
    ("HZNP", "2023-10-05", "medium: acquired by Amgen 2023-10-06"),
    ("SPLK", "2024-03-15", "medium: acquired by Cisco 2024-03-18"),
    ("DISCA", "2022-04-08", "low: merged into WBD April 2022"),
]
SPLITS = [("NVDA", "2024-06-10", 10.0), ("AAPL", "2020-08-31", 4.0), ("TSLA", "2022-08-25", 3.0)]
EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}


def _z(t: pd.Timestamp) -> str:
    return t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _first_session(month: str) -> str:
    return session_days(f"{month}-01", f"{month}-28")[0]


def recent_session(now: datetime | None = None) -> str:
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    days = session_days((now - pd.Timedelta(days=14)).strftime("%Y-%m-%d"), (now - pd.Timedelta(days=2)).strftime("%Y-%m-%d"))
    return days[-1]


# ------------------------------------------------------------------- gates ----
def gate_sip_access(c: AlpacaData, now: datetime | None = None) -> dict:
    days = [_first_session("2016-03"), _first_session("2020-03"), _first_session("2024-06"), recent_session(now)]
    rows = {}
    for d in days:
        o, cl = session_bounds(d)
        sb, bars, _ = c.bars("SPY", _z(o), _z(cl), feed="sip")
        m = o + pd.Timedelta(hours=5, minutes=30)
        sq, q, qb = c.quotes("SPY", _z(m), _z(m + pd.Timedelta(minutes=1)), feed="sip")
        rows[d] = {"bars_status": sb, "bars": len(bars), "quotes_status": sq, "quotes": len(q),
                   "message": qb.get("message") if sq != 200 else None}
    o, cl = session_bounds(days[-1])
    ent = verify_entitlement(c, o.to_pydatetime(), cl.to_pydatetime())
    ok = all(r["bars_status"] == 200 and r["bars"] > 300 and r["quotes_status"] == 200 and r["quotes"] > 0
             for r in rows.values()) and ent["verdict"] == "sip"
    return {"pass": ok, "sessions": rows, "entitlement": ent,
            "note": "free plan: SIP history must end >= 15 minutes ago (source E); every request here is older"}


def gate_timestamps(c: AlpacaData) -> dict:
    out, ok = {}, True
    for d in ("2024-07-15", "2024-01-16"):                 # daylight saving / standard time
        day0 = pd.Timestamp(d, tz=ET)
        sb, rows, _ = c.bars("SPY", _z(day0 + pd.Timedelta(hours=4)), _z(day0 + pd.Timedelta(hours=20)), feed="sip")
        f = bars_frame(rows)
        o, cl = session_bounds(d)
        et = f.index.tz_convert(ET)
        outside = int(((et.hour * 60 + et.minute) < 4 * 60).sum() + ((et.hour * 60 + et.minute) >= 20 * 60).sum())
        has_open = o in f.index
        m = o + pd.Timedelta(hours=2)
        sq, q, _ = c.quotes("SPY", _z(m), _z(m + pd.Timedelta(seconds=10)), feed="sip")
        qf = quotes_frame(q)
        mono = bool(qf.index.is_monotonic_increasing) if len(qf) else False
        within = bool(len(qf) and qf.index.min() >= m and qf.index.max() <= m + pd.Timedelta(seconds=10))
        ns = any(len(r["t"].split(".")[-1].rstrip("Z")) > 6 for r in q if "." in r.get("t", ""))
        fields = sorted(set().union(*[set(r) for r in q[:50]])) if q else []
        good = sb == 200 and has_open and to_et(o).strftime("%H:%M") == "09:30" and outside == 0 and mono and within
        ok &= good
        out[d] = {"pass": good, "open_bar_present": has_open, "open_bar_et": to_et(o).strftime("%H:%M"),
                  "bars_outside_0400_2000_et": outside, "quotes": len(qf), "quotes_monotonic": mono,
                  "quotes_within_window": within, "nanosecond_timestamps": ns, "quote_fields": fields}
    return {"pass": bool(ok), "days": out,
            "note": "quote field 't' is the only timestamp returned; whether it is the SIP or participant time is "
                    "not documented (record fields above)"}


def _daily(c: AlpacaData, symbols: list[str], start: str, end: str, adjustment="raw") -> dict:
    out = {}
    for i in range(0, len(symbols), 100):
        q = dict(timeframe="1Day", adjustment=adjustment)
        st, part = c.bars_multi(symbols[i:i + 100], start, end, **q)
        if st != 200:
            raise RuntimeError(f"daily bars HTTP {st}")
        out.update({s: bars_frame(r) for s, r in part.items()})
    return out


def gate_coverage(c: AlpacaData, sample: int = 200, sessions_per_stock: int = 5, seed: int = 7, year: str = "2023") -> dict:
    st, assets = c.assets()
    if st != 200:
        return {"pass": False, "reason": f"asset master HTTP {st}"}
    eq = [a for a in assets if a.get("exchange") in EXCHANGES]
    inactive = sum(a.get("status") == "inactive" for a in eq)
    rng = random.Random(seed)
    pool = sorted(a["symbol"] for a in eq)
    rng.shuffle(pool)
    chosen, checked = {}, 0
    for i in range(0, min(len(pool), 3000), 100):
        d = _daily(c, pool[i:i + 100], f"{year}-01-01", f"{year}-12-31")
        checked += 100
        for s, f in d.items():
            if len(f) > 100 and f.close.median() > 5 and f.volume.median() >= 1_000_000:
                chosen[s] = f
            if len(chosen) >= sample:
                break
        if len(chosen) >= sample:
            break
    pairs = {}
    for s, f in chosen.items():
        days = [x.strftime("%Y-%m-%d") for x in f.index.tz_convert(ET)]
        for d in rng.sample(days, min(sessions_per_stock, len(days))):
            pairs.setdefault(d, []).append(s)
    have = total = 0
    for d, syms in sorted(pairs.items()):
        o, cl = session_bounds(d)
        for i in range(0, len(syms), 20):
            stt, part = c.bars_multi(syms[i:i + 20], _z(o), _z(cl))
            for s in syms[i:i + 20]:
                total += 1
                have += int(stt == 200 and len(part.get(s, [])) > 0)
    coverage = have / total if total else 0.0
    delisted = {}
    for sym, last, conf in DELISTED:
        end = pd.Timestamp(last) - pd.Timedelta(days=30)
        stt, rows, _ = c.bars(sym, (end - pd.Timedelta(days=30)).strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
                              timeframe="1Day", asof="-")
        delisted[sym] = {"last_trading_day": last, "confidence": conf, "status": stt, "daily_bars": len(rows)}
    n_delisted = sum(v["daily_bars"] > 0 for v in delisted.values())
    ok = coverage >= 0.95 and inactive > 0 and n_delisted >= 10 and len(chosen) >= sample
    return {"pass": ok, "assets": len(eq), "inactive_assets": inactive, "sample_stocks": len(chosen),
            "sample_symbols": sorted(chosen),
            "symbols_screened": checked, "stock_sessions": total, "coverage": coverage,
            "delisted_with_bars": n_delisted, "delisted": delisted}


def gate_spreads(c: AlpacaData, candidates: list[str], n_days: int = 30, seed: int = 11, year: str = "2023") -> dict:
    """Quoted half-spreads at 09:35-10:30 ET and 15:59 ET on in-play stock-days (RV >= 1) of a sample.
    A MEASUREMENT; the slippage assumption is not part of it."""
    rng = random.Random(seed)
    days = session_days(f"{year}-02-01", f"{year}-12-15")
    found, tried = [], 0
    syms = list(candidates)
    rng.shuffle(syms)
    for s in syms:
        if len(found) >= n_days or tried >= 4 * n_days:
            break
        d = rng.choice(days)
        tried += 1
        hist = [x for x in session_days((pd.Timestamp(d) - pd.Timedelta(days=30)).strftime("%Y-%m-%d"), d)][-15:]
        o0, _ = session_bounds(hist[0])
        _, cl = session_bounds(d)
        st, rows, _ = c.bars(s, _z(o0), _z(cl), timeframe="5Min")
        f = bars_frame(rows)
        opens = {h: session_bounds(h)[0] for h in hist}
        vol = pd.Series({h: float(f.volume.get(opens[h], np.nan)) for h in hist})
        rv = orb.relative_volume(vol.iloc[-1], vol.iloc[:-1].dropna(), 14)
        if np.isfinite(rv) and rv >= 1.0:
            found.append((s, d, rv))
    entry, close = [], []
    for s, d, _ in found:
        mins = []
        for key, lst in measure_minutes(d).items():
            for m in lst:
                end = m + pd.Timedelta(minutes=1)
                q = []
                for back in (2, 60):
                    st, q, _ = c.quotes(s, _z(end - pd.Timedelta(seconds=back)), _z(end))
                    if q:
                        break
                (entry if key == "entry_window" else close).append(half_spread_at(quotes_frame(q[-1:]), m))
    se, sc = summarize(entry), summarize(close)
    ok = len(found) >= 20 and se.get("share_unusable", 1) is not None and se["share_unusable"] < 0.2
    return {"pass": bool(ok), "in_play_stock_days": len(found), "candidates_tried": tried,
            "stock_days": [{"symbol": s, "day": d, "rv": rv} for s, d, rv in found],
            "entry_window_0935_1030": se, "close_1559": sc,
            "note": "measured quoted half-spreads only; slippage beyond the touch stays an assumption (costs.py)"}


def measure_minutes(day: str) -> dict:
    from tradelab.stocks.spreads import close_minute, minutes_et
    return {"entry_window": minutes_et(day, "09:35", "10:30"), "close": [close_minute(day)]}


def gate_corporate_actions(c: AlpacaData) -> dict:
    out, ok = {}, True
    for sym, eff, ratio in SPLITS:
        d = pd.Timestamp(eff)
        lo, hi = (d - pd.Timedelta(days=10)).strftime("%Y-%m-%d"), (d + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        raw = _daily(c, [sym], lo, hi, "raw").get(sym)
        adj = _daily(c, [sym], lo, hi, "split").get(sym)
        if raw is None or adj is None or raw.empty:
            out[sym] = {"pass": False, "reason": "no daily bars"}
            ok = False
            continue
        idx = raw.index.tz_convert(ET).normalize().tz_localize(None)
        fac = pd.Series(raw.close.to_numpy() / adj.close.reindex(raw.index).to_numpy(), index=idx)
        before, after = fac[fac.index < d], fac[fac.index >= d]
        measured = float(before.iloc[-1] / after.iloc[0]) if len(before) and len(after) else float("nan")
        prev = before.index[-1].strftime("%Y-%m-%d") if len(before) else None
        o, cl = session_bounds(prev)
        st, rows, _ = c.bars(sym, _z(o), _z(cl))
        last_min = bars_frame(rows).close.iloc[-1] if rows else float("nan")
        daily_close = float(raw.close.iloc[len(before) - 1])
        good = abs(measured / ratio - 1) < 0.01 and abs(last_min / daily_close - 1) < 0.005
        ok &= bool(good)
        out[sym] = {"pass": bool(good), "split_effective": eff, "expected_ratio": ratio, "raw_over_adjusted_jump": measured,
                    "intraday_raw_last_close": float(last_min), "daily_raw_close": daily_close}
    return {"pass": bool(ok), "splits": out,
            "note": "intraday bars are requested with adjustment=raw (the paper's unadjusted convention); daily filters "
                    "use point-in-time split adjustment (tradelab/stocks/orb.py pit_adjust)"}


def run_all(c: AlpacaData, now: datetime | None = None) -> dict:
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "paper_key": verify_paper_key(c),
              "gates": {}}
    if not report["paper_key"]["is_paper_key"]:
        report["gates"]["B7_1_sip_access"] = {"pass": False, "reason": "key is not confirmed as a PAPER key; stopped"}
        return report
    g = report["gates"]
    g["B7_1_sip_access"] = gate_sip_access(c, now)
    g["B7_2_timestamps"] = gate_timestamps(c)
    g["B7_3_coverage"] = gate_coverage(c)
    sample = g["B7_3_coverage"].get("sample_symbols", [])
    g["B7_4_spreads"] = gate_spreads(c, sample) if sample else {"pass": False, "reason": "no coverage sample to draw from"}
    g["B7_5_corporate_actions"] = gate_corporate_actions(c)
    report["api_calls"] = c.calls
    return report


def markdown(report: dict) -> str:
    lines = [f"\n## Data-gate run {report['generated_at']} (paper key; scripts/pit_verify_alpaca.py)\n",
             "| Gate | Pass | Key facts |", "|---|---|---|"]
    g = report["gates"]
    def fact(k, v):
        if k == "B7_1_sip_access":
            return f"entitlement verdict {v.get('entitlement', {}).get('verdict')}"
        if k == "B7_2_timestamps":
            return "; ".join(f"{d}: open {x['open_bar_et']}, outside-hours bars {x['bars_outside_0400_2000_et']}"
                             for d, x in v.get("days", {}).items())
        if k == "B7_3_coverage":
            return (f"coverage {v.get('coverage', 0):.1%} of {v.get('stock_sessions')} stock-sessions; inactive assets "
                    f"{v.get('inactive_assets')}; delisted with bars {v.get('delisted_with_bars')}/{len(DELISTED)}")
        if k == "B7_4_spreads":
            e, cl = v.get("entry_window_0935_1030", {}), v.get("close_1559", {})
            return (f"MEASURED half-spread 09:35-10:30 median {e.get('median_bp')} bp, p90 {e.get('p90_bp')} bp; "
                    f"15:59 median {cl.get('median_bp')} bp ({v.get('in_play_stock_days')} in-play stock-days)")
        if k == "B7_5_corporate_actions":
            return "; ".join(f"{s}: jump {x.get('raw_over_adjusted_jump')}" for s, x in v.get("splits", {}).items())
        return v.get("reason", "")
    for k, v in g.items():
        lines.append(f"| {k} | {'yes' if v.get('pass') else 'NO'} | {fact(k, v)} |")
    return "\n".join(lines) + "\n"
