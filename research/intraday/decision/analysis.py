"""Exploratory decision-quality study. Everything fitted on development data only; validation and
test periods were already examined by earlier work, so no result here can promote a strategy."""
import json
from datetime import timedelta

import numpy as np
import pandas as pd

from common import OUT, ROOT, RT, boot_mean, boot_spearman, fmt, period_of, prior_regimes
from functools import lru_cache

from stocks import U, daily as _daily, hourly as _hourly
from crypto import bars as _bars

daily, hourly, bars = lru_cache(None)(_daily), lru_cache(None)(_hourly), lru_cache(None)(_bars)   # load each file once

SECTOR = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]
STOCKS = U[U.kind == "stock"].yahoo.tolist()
UNIV = {"S2": STOCKS + SECTOR, "S2_etf": SECTOR + ["QQQ", "IWM", "DIA"]}
R = {}


def load(k):
    t = pd.read_csv(OUT / f"trades_{k}.csv")
    for c in ("entry_time", "exit_time", "signal_time"):
        if c in t:
            t[c] = pd.to_datetime(t[c], utc=True)
    return t


def periods(t, k):
    if k == "S1":
        days = sorted(t.day.unique())
        hd = sorted(set(pd.read_csv(ROOT / "data/stocks/hourly/SPY.csv", index_col=0).index.str[:10]))
        a, b = hd[int(len(hd) * 0.4)], hd[int(len(hd) * 0.6)]
        return np.where(t.day < a, "dev", np.where(t.day < b, "validation", "test"))
    return [period_of(d, "S2" if k.startswith("S2") else "C") for d in t.day]


TR = {k: load(k) for k in ["S2", "S2_etf", "S1", "C1", "C2"]}
for k, t in TR.items():
    t["period"] = periods(t, k)
    t["net"] = t.gross_ret - RT[k]
    t["strength"] = -t.feature if k in ("S2", "S2_etf", "C1") else t.feature   # larger = stronger signal

# ---------------------------------------------------------------- Q1: setup vs noise
def s2_noise(k):
    syms = UNIV[k]
    d = {s: daily(s) for s in syms}
    O = pd.DataFrame({s: x.open for s, x in d.items()}); C = pd.DataFrame({s: x.close for s, x in d.items()})
    V = pd.DataFrame({s: x.volume for s, x in d.items()})
    oc = C / O - 1
    dv = (C * V).rolling(20, min_periods=15).median().shift(1)
    elig = (C.shift(1) > 10) & (dv > 50e6)
    return oc.where(elig)


def s1_noise():
    rows = {}
    for s in STOCKS + ["SPY", "QQQ", "IWM", "DIA"]:
        h = hourly(s)
        if h is None:
            continue
        et = h.index.tz_convert("America/New_York")
        last = h[et.strftime("%H:%M") == "15:30"]
        rows[s] = pd.Series((last.close / last.open - 1).values, index=last.index.tz_convert("America/New_York").strftime("%Y-%m-%d"))
    return pd.DataFrame(rows)


def crypto_noise(t, k, n=40, seed=5):
    rng = np.random.default_rng(seed)
    out = []
    cache = {}
    for _, x in t.iterrows():
        b = cache.setdefault(x.symbol, bars(x.symbol))
        hold = x.exit_time - x.entry_time
        per = [p for p in (("dev", "2020-01-01", "2023-01-01"), ("validation", "2023-01-01", "2024-01-01"), ("test", "2024-01-01", "2026-10-25")) if p[0] == x.period][0]
        days = pd.date_range(per[1], per[2], freq="D", tz="UTC", inclusive="left")
        draws = []
        for d in rng.choice(days, size=n):
            st = pd.Timestamp(d) + (x.entry_time - x.entry_time.normalize())
            en = st + hold
            if st in b.index:
                j = b.index.searchsorted(en, side="right") - 1
                if j >= 0 and b.index[j] >= st:
                    draws.append(b.close.iloc[j] / b.open.loc[st] - 1)
        out.append(np.mean(draws) if draws else np.nan)
    return np.array(out)


q1 = {}
for k in ["S2", "S2_etf"]:
    oc = s2_noise(k)
    t = TR[k]
    base = []
    for s, d in zip(t.symbol, t.day):
        row = oc.loc[d].drop(index=s, errors="ignore") if d in oc.index else pd.Series(dtype=float)
        base.append(row.mean())
    t["noise"] = base
s1n = s1_noise()
TR["S1"]["noise"] = [s1n.loc[d].drop(index=s, errors="ignore").mean() if d in s1n.index else np.nan for s, d in zip(TR["S1"].symbol, TR["S1"].day)]
for k in ["C1", "C2"]:
    TR[k]["noise"] = crypto_noise(TR[k], k)
for k, t in TR.items():
    t["excess"] = t.gross_ret - t.noise
    q1[k] = {p: {"n": int((t.period == p).sum()), "gross": fmt(boot_mean(t.gross_ret[t.period == p], t.day[t.period == p])),
                 "matched_random": fmt(boot_mean(t.noise[t.period == p], t.day[t.period == p])),
                 "excess": fmt(boot_mean(t.excess[t.period == p], t.day[t.period == p]))}
             for p in ("dev", "validation", "test")}
R["Q1_setup_vs_noise_pct"] = q1

# ---------------------------------------------------------------- Q2: strength -> gross, cost-aware gate
q2 = {}
for k, t in TR.items():
    dev = t[t.period == "dev"]
    cuts = np.quantile(dev.strength.dropna(), [1 / 3, 2 / 3])
    t["bucket"] = np.digitize(t.strength, cuts)              # 0 weak .. 2 strong, cut-offs from dev only
    pred = dev.assign(bucket=np.digitize(dev.strength, cuts)).groupby("bucket").gross_ret.mean()
    t["pred"] = t.bucket.map(pred)
    t["gate"] = t.pred > RT[k]
    res = {"dev_cutoffs": cuts.tolist(), "dev_predicted_gross_pct_by_bucket": (pred * 100).round(4).to_dict(), "round_trip_pct": RT[k] * 100}
    for p in ("validation", "test"):
        s = t[t.period == p]
        res[p] = {"spearman_strength_vs_gross": [round(v, 3) for v in boot_spearman(s.strength, s.gross_ret, s.day)],
                  "calibration": {int(b): {"predicted": round(pred.get(b, np.nan) * 100, 3), "n": int((s.bucket == b).sum()),
                                           "realized": fmt(boot_mean(s.gross_ret[s.bucket == b], s.day[s.bucket == b]))} for b in range(3)},
                  "gate_keeps": f"{int(s.gate.sum())}/{len(s)}",
                  "net_all": fmt(boot_mean(s.net, s.day)),
                  "net_gated": fmt(boot_mean(s.net[s.gate], s.day[s.gate])) if s.gate.sum() > 2 else "n/a (gate keeps <3 trades)"}
        w = s.size_weight if "size_weight" in s else pd.Series(0.2, index=s.index)
    q2[k] = res
R["Q2_strength_and_cost_gate"] = q2

# ---------------------------------------------------------------- Q3: hold vs premise failed
def crypto_counterfactual(t, k):
    rows = []
    cache = {}
    for _, x in t.iterrows():
        b = cache.setdefault(x.symbol, bars(x.symbol))
        deadline = (x.signal_time + timedelta(hours=6)) if k == "C1" else (x.signal_time.normalize() + timedelta(hours=23, minutes=55))
        path = b[(b.index >= x.entry_time) & (b.index < deadline)]
        if path.empty:
            rows.append((np.nan, np.nan)); continue
        hold = path.close.iloc[-1] / x.entry_px - 1
        if k == "C1":
            tgt = x.entry_px * (1 + 1.5 * x.sigma)
            hit = path[path.high > tgt]
            nostop = (max(hit.open.iloc[0], tgt) / x.entry_px - 1) if len(hit) else hold
        else:
            nostop = hold                                 # C2 has no target: no-stop == hold to deadline
        rows.append((hold, nostop))
    return np.array(rows)


q3 = {}
for k in ["C1", "C2"]:
    t = TR[k]
    cf = crypto_counterfactual(t, k)
    t["cf_hold"], t["cf_nostop"] = cf[:, 0], cf[:, 1]
    q3[k] = {"exit_reasons": t.exit_reason.value_counts().to_dict()}
    for p in ("dev", "validation", "test"):
        s = t[t.period == p]
        q3[k][p] = {"n": len(s), "actual_gross": fmt(boot_mean(s.gross_ret, s.day)),
                    "hold_to_deadline_minus_actual": fmt(boot_mean(s.cf_hold - s.gross_ret, s.day)),
                    "no_stop_minus_actual": fmt(boot_mean(s.cf_nostop - s.gross_ret, s.day))}
# S2 abandon rule on hourly window
t = TR["S2"]
rows = []
for _, x in t[t.day >= "2023-11-27"].iterrows():
    h = hourly(x.symbol)
    if h is None:
        continue
    o = pd.Timestamp(x.entry_time)
    if o not in h.index:
        continue
    first_close = h.loc[o, "close"]
    abandon = first_close < x.entry_px                       # the first hour extended the gap down
    alt = (first_close / x.entry_px - 1 - 0.0002) if abandon else x.gross_ret   # market exit costs 2 bp more than MOC
    rows.append((x.day, x.gross_ret, alt, abandon))
ab = pd.DataFrame(rows, columns=["day", "actual", "alt", "abandon"])
q3["S2_abandon_at_1030"] = {"n": len(ab), "abandoned": int(ab.abandon.sum()), "window": "2023-11-27 -> 2026-10-23 (inside the already-seen test period)",
                           "rule_minus_hold": fmt(boot_mean(ab.alt - ab.actual, ab.day)),
                           "actual_gross_abandoned_trades": fmt(boot_mean(ab.actual[ab.abandon], ab.day[ab.abandon]))}
R["Q3_holding_vs_abandon_pct"] = q3

# ---------------------------------------------------------------- Q4: regimes / abstention
spy = daily("SPY").close
btc5 = bars("BTC-USD")
btc = btc5.close.resample("1D").last().dropna()
btc.index = btc.index.strftime("%Y-%m-%d")
REG = {"stocks": prior_regimes(spy), "crypto": prior_regimes(btc)}
q4 = {}
for k, t in TR.items():
    reg = REG["crypto" if k.startswith("C") else "stocks"]
    t["vol20"] = t.day.map(reg.vol20)
    t["trend_up"] = t.day.map(reg.trend_up)
    dev = t[t.period == "dev"]
    vc = np.nanquantile(dev.vol20, [1 / 3, 2 / 3])
    t["vol_t"] = np.digitize(t.vol20, vc)
    groups = {f"vol_tercile_{i}": t.vol_t == i for i in range(3)}
    groups.update({"trend_up": t.trend_up == True, "trend_down": t.trend_up == False})  # noqa: E712
    devmeans = {g: t.gross_ret[m & (t.period == "dev")].mean() for g, m in groups.items()}
    worst = min(devmeans, key=devmeans.get)
    res = {"dev_vol_cutoffs": vc.tolist(), "worst_dev_group": worst, "candidate_groups": len(groups)}
    for p in ("dev", "validation", "test"):
        inp = t.period == p
        res[p] = {g: f"n={int((m & inp).sum())} " + fmt(boot_mean(t.gross_ret[m & inp], t.day[m & inp])) for g, m in groups.items()}
        keep = inp & ~groups[worst]
        res[p]["abstain_worst_net"] = fmt(boot_mean(t.net[keep], t.day[keep]))
        res[p]["all_net"] = fmt(boot_mean(t.net[inp], t.day[inp]))
    q4[k] = res
R["Q4_regime_abstention_pct"] = q4

# ---------------------------------------------------------------- Decay
dec = {}
for k, delays in (("C1", [0, 1, 2, 5, 10, 15, 30, 60]), ("C2", [0, 5, 10, 15, 30, 60])):
    t = TR[k]
    res = {}
    for dmin in delays:
        vals, days = [], []
        for _, x in t.iterrows():
            b = bars(x.symbol) if f"b_{x.symbol}" not in dec else None
            b = dec.setdefault(f"b_{x.symbol}", b if b is not None else bars(x.symbol))
            st = x.signal_time + timedelta(minutes=dmin)
            end = (x.signal_time + timedelta(hours=6)) if k == "C1" else (x.signal_time.normalize() + timedelta(hours=23, minutes=55))
            if dmin % 5:                                           # 1-minute entries: only where the 1m cache exists
                f = ROOT / "data/crypto_intraday/m1_cache" / f"{x.symbol}_{(x.signal_time - timedelta(hours=1)).strftime('%Y%m%dT%H%M')}.csv"
                if not f.exists():
                    continue
                m1 = pd.read_csv(f, index_col=0); m1.index = pd.to_datetime(m1.index, utc=True)
                if st not in m1.index:
                    continue
                px = m1.loc[st, "open"]
            else:
                if st not in b.index:
                    continue
                px = b.loc[st, "open"]
            path = b[(b.index >= st) & (b.index < end)]
            if path.empty:
                continue
            vals.append(path.close.iloc[-1] / px - 1); days.append(x.day)
        res[f"+{dmin}m"] = f"n={len(vals)} " + fmt(boot_mean(vals, days))
    dec[k] = res
t = TR["S2"]
rows = []
for _, x in t[t.day >= "2023-11-27"].iterrows():
    h = hourly(x.symbol)
    o = pd.Timestamp(x.entry_time)
    if h is None or o + timedelta(hours=1) not in h.index:
        continue
    rows.append((x.day, x.gross_ret, x.exit_px / h.loc[o + timedelta(hours=1), "open"] - 1))
sd = pd.DataFrame(rows, columns=["day", "open", "plus60"])
dec["S2"] = {"+0m (open)": f"n={len(sd)} " + fmt(boot_mean(sd.open, sd.day)), "+60m (10:30)": fmt(boot_mean(sd.plus60, sd.day)),
             "difference": fmt(boot_mean(sd.plus60 - sd.open, sd.day))}
dec["S1"] = "not measurable: hourly bars only, and the 15:30 bar is the last of the session"
R["decay_gross_pct"] = {k: v for k, v in dec.items() if not k.startswith("b_")}

(OUT / "decision_quality.json").write_text(json.dumps(R, indent=1, default=str))
for k, t in TR.items():
    t.to_csv(OUT / f"annotated_{k}.csv", index=False)
print(json.dumps(R, indent=1, default=str))
