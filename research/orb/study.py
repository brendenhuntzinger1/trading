"""ORB on US Stocks in Play: study harness for ORB_PREREGISTRATION.md (+ Amendments 1 and 2).

    python research/orb/study.py gates                 # read the latest data-gate report (scripts/pit_verify_alpaca.py)
    python research/orb/study.py dev                   # benchmarks first, then the rule and the <= 4 dev variants
    python research/orb/study.py validation
    python research/orb/study.py freeze --config primary
    python research/orb/study.py final                 # only with a QUALIFIED frozen candidate (B9); re-runnable

Rules of the harness (B5, B9):
- dev and validation are selection windows: they refuse to run on data recorded as consumed for this scope.
- freeze stores a hash of every rule, parameter, cost model, period and the source code of the code path.
- final refuses (and records a violation) if the current hash differs from the frozen one. It may be re-run any
  number of times; the result must reproduce. If no configuration qualified, final does not read any data.
- the final window is recorded as consumed (research/consumed_data.json) before it is first read.
Paper research only; the data client cannot place orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.orb import evaluate as ev                                                    # noqa: E402
from tradelab.research import consumed                                                    # noqa: E402
from tradelab.research.registry import record                                             # noqa: E402
from tradelab.stocks import orb                                                           # noqa: E402
from tradelab.stocks.costs import BASE, STRESS, CostModel, trade_costs                    # noqa: E402
from tradelab.stocks.spreads import close_minute                                          # noqa: E402
from tradelab.stocks.timeutil import session_bounds                                       # noqa: E402

RESULTS = ROOT / "research" / "orb" / "results"
FROZEN = ROOT / "research" / "orb" / "frozen.json"
VERIFY_DIR = ROOT / "data" / "stocks"
SCOPE = "stocks.us.intraday.orb"
CONSUMED_LEDGER = consumed.LEDGER
PERIODS = {"dev": ("2016-01-04", "2019-12-31"), "validation": ("2020-01-02", "2023-12-29"),
           "final": ("2024-01-02", "2026-07-24")}
EXCLUDED = ("2026-07-27", "2026-10-23")              # exploratory S3 window (pre-registration §5, B1)
PAPER_R = 0.08                                       # paper: +0.08R per trade at RV > 100%, net of commission
PAPER_COMMISSION = 0.0035                            # $/share, for the §8 sanity gate only
PLACEBO_REPS = 1000
EQUITY = 25_000.0                                    # paper's starting capital; only affects per-share fee caps
SPARE = 10                                           # extra ranked names fetched to replace excluded stock-days
CODE_FILES = ["tradelab/stocks/orb.py", "tradelab/stocks/costs.py", "tradelab/stocks/spreads.py",
              "tradelab/stocks/timeutil.py", "research/orb/study.py", "research/orb/evaluate.py", "research/orb/data.py"]


# ------------------------------------------------------------------ hashing ----
def config_hash(root: Path = ROOT) -> str:
    spec = {"configs": {k: v.as_dict() for k, v in orb.CONFIGS.items()},
            "costs": [BASE.as_dict(), STRESS.as_dict()], "periods": PERIODS, "excluded": EXCLUDED,
            "paper_r": PAPER_R, "placebo_reps": PLACEBO_REPS, "spare": SPARE, "equity": EQUITY,
            "code": {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in CODE_FILES}}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def excluded(day: str) -> bool:
    return EXCLUDED[0] <= day <= EXCLUDED[1]


# --------------------------------------------------------------- one period ----
def _quote_minute(trade: orb.Trade, entry: bool, kind: str, close_min: pd.Timestamp) -> pd.Timestamp:
    """Minute whose END carries the quote used for a fill. Stop triggers: end of the trigger minute; fills at a
    bar open (market entry, gap-through stop): end of the previous minute; close exit: end of 15:59 (12:59)."""
    one = pd.Timedelta(minutes=1)
    if entry:
        return trade.entry_time if kind == "stop" else trade.entry_time - one
    if trade.exit_reason == "close":
        return close_min
    return trade.exit_time - one if trade.exit_reason == "stop_gap" else trade.exit_time


def _row(source, day, sym, tr: orb.Trade, kind: str, atr: float, rv: float, close_min) -> dict:
    hs_in = source.half_spread(sym, _quote_minute(tr, True, kind, close_min))
    hs_out = source.half_spread(sym, _quote_minute(tr, False, kind, close_min))
    v_in = hs_in.value if hs_in is not None and hs_in.status == "ok" else None
    v_out = hs_out.value if hs_out is not None and hs_out.status == "ok" else None
    return {"day": day, "symbol": sym, "side": tr.side, "entry_time": tr.entry_time, "exit_time": tr.exit_time,
            "entry_px": tr.entry_px, "exit_px": tr.exit_px, "exit_reason": tr.exit_reason, "gross": tr.gross,
            "r": tr.r, "mae": tr.mae, "mfe": tr.mfe, "halted": tr.halted, "atr": atr, "rv": rv,
            "hs_in": v_in, "hs_out": v_out, "quotes_api": hs_in is not None}


def _costs(rows: pd.DataFrame, model: CostModel) -> pd.DataFrame:
    if rows.empty:
        return rows.assign(weight=[], net_spread=[], net_all=[], cost_label=[])
    out = rows.copy()
    tot, spr, lab = [], [], []
    for r in out.itertuples():
        shares = max(r.weight, 1e-9) * EQUITY / r.entry_px
        c = trade_costs(r.side, r.entry_px, r.exit_px, shares, date.fromisoformat(r.day), r.hs_in, r.hs_out, model)
        tot.append(c["total"]); spr.append(c["spread_measured"]); lab.append(c["label"])
    out["cost_total"] = tot
    out["spread_cost"] = spr
    out["cost_label"] = lab
    out["net_all"] = out.gross - out.cost_total
    out["net_spread"] = [g - s if s is not None else np.nan for g, s in zip(out.gross, spr)]
    return out


def _weights(rows: pd.DataFrame, cfg: orb.ORBConfig, equal: bool = False) -> pd.Series:
    if rows.empty:
        return pd.Series(dtype=float)
    if equal:
        n = rows.groupby("day").symbol.transform("size")
        return (cfg.max_gross / n).astype(float)
    return pd.concat([orb.allocate(g, cfg) for _, g in rows.groupby("day")]).reindex(rows.index)


def run_period(source, phase: str, configs: list[str], placebo_reps: int = PLACEBO_REPS) -> dict:
    days = [d for d in source.days(*PERIODS[phase]) if not excluded(d)]
    cfgs = {k: orb.CONFIGS[k] for k in configs}
    acc = {k: {"rule": [], "rule_nostop": [], "direction": [], "basket": [],
               "abst": {"doji": 0, "short_signal_long_only": 0, "armed_not_triggered": 0, "days_nothing_selected": 0,
                        "excluded_no_open_bar": 0},
               "not_traded_fwd": []} for k in cfgs}
    spy_rows = []
    for day in days:
        o, c = session_bounds(day)
        cm = close_minute(day)
        cands = source.candidates(day)
        ranked = {k: cands[_passes(cands, cfg)].sort_values(["rv", "symbol"], ascending=[False, True])
                  for k, cfg in cfgs.items()}
        want = sorted(set().union(*[set(r.symbol.head(cfg.top_n + SPARE)) for (k, r), cfg in
                                    zip(ranked.items(), cfgs.values())]) | {"SPY"})
        bars = source.minute_bars(want, day)
        spy = bars.get("SPY")
        if spy is not None and not spy.empty:
            tr = orb.simulate(spy, o, c, orb.LONG, 1.0, entry="market", use_stop=False)
            if tr.triggered:
                spy_rows.append(_row(source, day, "SPY", tr, "market", float("nan"), float("nan"), cm))
        for k, cfg in cfgs.items():
            a = acc[k]
            chosen = []
            for r in ranked[k].itertuples():
                if len(chosen) == cfg.top_n:
                    break
                b = bars.get(r.symbol)
                if b is None:
                    b = source.minute_bars([r.symbol], day).get(r.symbol)
                    bars[r.symbol] = b
                rng = orb.opening_range(b, o, cfg.or_minutes) if b is not None else None
                if rng is None:
                    a["abst"]["excluded_no_open_bar"] += 1
                    continue
                chosen.append((r, rng, b))
            if not chosen:
                a["abst"]["days_nothing_selected"] += 1
            for r, rng, b in chosen:
                a["basket"].append(_row(source, day, r.symbol, orb.simulate(b, o, c, orb.LONG, r.atr, "market",
                                                                             use_stop=False), "market", r.atr, r.rv, cm))
                d = rng.direction
                if d == 0:
                    a["abst"]["doji"] += 1
                    continue
                if d < 0 and cfg.long_only:
                    a["abst"]["short_signal_long_only"] += 1
                    fwd = orb.simulate(b, o, c, orb.SHORT, r.atr, "market", use_stop=False)
                    if fwd.triggered:
                        a["not_traded_fwd"].append({"reason": "short_signal_long_only", "gross": fwd.gross})
                    continue
                level = rng.high if d > 0 else rng.low
                rule = orb.simulate(b, o, c, d, r.atr, "stop", level=level, stop_frac=cfg.stop_atr_frac)
                if not rule.triggered:
                    a["abst"]["armed_not_triggered"] += 1
                    fwd = orb.simulate(b, o, c, d, r.atr, "market", use_stop=False)
                    if fwd.triggered:
                        a["not_traded_fwd"].append({"reason": "armed_not_triggered", "gross": fwd.gross})
                    continue
                a["rule"].append(_row(source, day, r.symbol, rule, "stop", r.atr, r.rv, cm))
                ns = orb.simulate(b, o, c, d, r.atr, "stop", level=level, use_stop=False)
                a["rule_nostop"].append(_row(source, day, r.symbol, ns, "stop", r.atr, r.rv, cm))
                dr = orb.simulate(b, o, c, d, r.atr, "market", use_stop=False)
                if dr.triggered:
                    a["direction"].append(_row(source, day, r.symbol, dr, "market", r.atr, r.rv, cm))
    spy_df = pd.DataFrame(spy_rows)
    if not spy_df.empty:
        spy_df["weight"] = 1.0
    spy_df = _costs(spy_df, BASE)
    spy_daily = ev.daily(spy_df, days, "net_all") if not spy_df.empty else pd.Series(0.0, index=days)
    out = {"phase": phase, "sessions": len(days), "range": [days[0], days[-1]] if days else None,
           "quotes_available": bool(getattr(source, "quotes_available", False)), "configs": {},
           "benchmark_spy": ev.series_stats(spy_daily)}
    for k, cfg in cfgs.items():
        a = acc[k]
        frames = {}
        for name in ("rule", "rule_nostop", "direction", "basket"):
            f = pd.DataFrame(a[name])
            if not f.empty:
                f["weight"] = _weights(f, cfg, equal=(name == "basket")).to_numpy()
            frames[name] = _costs(f, BASE)
        stress = _costs(pd.DataFrame(a["rule"]).assign(weight=frames["rule"].weight.to_numpy()) if a["rule"] else
                        pd.DataFrame(), STRESS)
        plc_means, plc_daily = _placebo(source, frames["rule"], cfg, days, placebo_reps)
        out["configs"][k] = _summarize(frames, stress, a, days, spy_daily, plc_means, plc_daily, cfg)
        out["configs"][k]["_frames"] = frames
        out["configs"][k]["_stress"] = stress
        out["configs"][k]["_placebo_means"] = plc_means
    return out


def _passes(c: pd.DataFrame, cfg: orb.ORBConfig) -> pd.Series:
    return ((c.open > cfg.min_open) & (c.adv >= cfg.min_adv) & (c.atr > cfg.min_atr) & (c.rv >= cfg.min_rv)
            & ~c.corporate_action.astype(bool) & c.has_open_bar.astype(bool))


def _placebo(source, rule: pd.DataFrame, cfg: orb.ORBConfig, days: list[str], reps: int, seed: int = 17):
    """B3.5: for each realised rule trade, the same stock-day with a random side (long only in the long-only
    study) and an entry minute drawn from the realised entry-time distribution; same stop and close exit.
    Approximation (stated): each placebo trade carries its rule trade's own cost and weight; quotes at random
    minutes are not fetched."""
    if rule.empty or reps <= 0:
        return np.array([]), np.zeros((max(reps, 0), len(days)))
    rng = np.random.default_rng(seed)
    offs = []
    for r in rule.itertuples():
        o, _ = session_bounds(r.day)
        offs.append(int((r.entry_time - o) / pd.Timedelta(minutes=1)))
    offs = np.array(offs)
    day_ix = {d: i for i, d in enumerate(days)}
    gross_sum = np.zeros(reps)
    daily_pnl = np.zeros((reps, len(days)))
    for day, g in rule.groupby("day"):
        o, c = session_bounds(day)
        bars = source.minute_bars(sorted(g.symbol.unique()), day)
        for r in g.itertuples():
            b = bars.get(r.symbol)
            k = rng.choice(offs, size=reps)
            side = np.full(reps, orb.LONG) if cfg.long_only else rng.choice([orb.LONG, orb.SHORT], size=reps)
            cost = r.cost_total
            res = {}
            for kk, ss in set(zip(k.tolist(), side.tolist())):
                t = orb.simulate(b, o, c, ss, r.atr, "market", entry_minute=o + pd.Timedelta(minutes=kk),
                                 stop_frac=cfg.stop_atr_frac)
                res[(kk, ss)] = t.gross if t.triggered else 0.0
            gvec = np.array([res[(kk, ss)] for kk, ss in zip(k.tolist(), side.tolist())])
            gross_sum += gvec
            daily_pnl[:, day_ix[day]] += r.weight * (gvec - cost)
    return gross_sum / len(rule), daily_pnl


def _summarize(frames, stress, a, days, spy_daily, plc_means, plc_daily, cfg) -> dict:
    rule = frames["rule"]
    measured = bool(len(rule)) and rule.spread_cost.notna().all()
    col = "net_spread" if measured else "net_all"         # assumed-cost path: no measured spread exists
    s = {"long_only": cfg.long_only, "cost_path": "measured spread" if measured else "cost assumed, not measured",
         "rule": ev.decision_metrics(rule, days, spy_daily, a["abst"]),
         "not_traded_forward_gross_bp": {r: float(np.mean([x["gross"] for x in a["not_traded_fwd"] if x["reason"] == r]) * 1e4)
                                         for r in {x["reason"] for x in a["not_traded_fwd"]}},
         "benchmarks": {}}
    for name in ("basket", "direction", "rule_nostop"):
        f = frames[name]
        s["benchmarks"][name] = {"trades": int(len(f)), **(ev.series_stats(ev.daily(f, days, "net_all")) if len(f) else {}),
                                 "gross_bp": float(f.gross.mean() * 1e4) if len(f) else None}
    rule_d = ev.daily(rule, days, col) if len(rule) else pd.Series(0.0, index=days)
    dir_d = ev.daily(frames["direction"], days, col) if len(frames["direction"]) else pd.Series(0.0, index=days)
    nostop_d = ev.daily(frames["rule_nostop"], days, col) if len(frames["rule_nostop"]) else pd.Series(0.0, index=days)
    plc_d = ev.placebo_daily(plc_daily, days) if len(plc_daily) else pd.Series(0.0, index=days)
    s["decomposition"] = {"entry_trigger_value": ev.paired_ci(nostop_d, dir_d), "stop_value": ev.paired_ci(rule_d, nostop_d)}
    s["placebo"] = {"reps": int(len(plc_means)), "mean_gross_bp": float(np.mean(plc_means) * 1e4) if len(plc_means) else None,
                    "p_value": float((plc_means >= rule.gross.mean()).mean()) if len(plc_means) and len(rule) else None}
    s["vs_direction"] = ev.paired_ci(rule_d, dir_d)
    s["vs_placebo"] = ev.paired_ci(rule_d, plc_d)
    s["net_all_per_trade"] = ev.trade_mean_ci(rule, "net_all", days) if len(rule) else {"mean": None}
    s["stress_net_all_bp"] = float(stress.net_all.mean() * 1e4) if len(stress) else None
    return s


def sanity_gate(dev: dict) -> dict:
    """§8: paper rules (long/short, RV >= 1, top 20) gross R per trade net of $0.0035/share commission must
    have a 95% interval that contains the paper's +0.08R."""
    t = dev["configs"]["long_short"]["_frames"]["rule"]
    if t.empty:
        return {"pass": False, "reason": "no trades"}
    t = t.assign(r_comm=t.r - 2 * PAPER_COMMISSION / (0.10 * t.atr))
    ci = ev.trade_mean_ci(t, "r_comm", list(t.day.unique()), level=0.95)
    return {"pass": ci["ci"][0] <= PAPER_R <= ci["ci"][1], "paper_R": PAPER_R, **ci}


def dev_qualifiers(dev: dict, gate: dict) -> dict:
    """B9 development qualifier per configuration."""
    q = {}
    for k, s in dev["configs"].items():
        q[k] = {"sanity_gate": gate["pass"], "beats_direction": s["vs_direction"]["ci"][0] is not None
                and s["vs_direction"]["ci"][0] > 0, "beats_placebo": s["vs_placebo"]["ci"][0] is not None
                and s["vs_placebo"]["ci"][0] > 0}
        q[k]["qualified"] = all(q[k].values())
    return q


def validation_qualifiers(val: dict) -> dict:
    return {k: {"net_all_mean_ge_0": s["net_all_per_trade"]["mean"] is not None and s["net_all_per_trade"]["mean"] >= 0}
            for k, s in val["configs"].items()}


# -------------------------------------------------------------- persistence ----
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 10)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def _write(name: str, out: dict) -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    js = _jsonable(out)
    (RESULTS / f"{name}.json").write_text(json.dumps(js, indent=1, sort_keys=True))
    return js


def _read(name: str) -> dict:
    p = RESULTS / f"{name}.json"
    if not p.exists():
        sys.exit(f"run '{name}' first")
    return json.loads(p.read_text())


def phase_gates(verify_dir: Path = VERIFY_DIR) -> dict:
    reports = sorted(verify_dir.glob("verify_*.json"))
    if not reports:
        sys.exit("no data-gate report: run scripts/pit_verify_alpaca.py with the paper key first (docs/CREDENTIALS_SETUP.md)")
    r = json.loads(reports[-1].read_text())
    g = r.get("gates", {})
    ok = all(g.get(k, {}).get("pass") for k in ("B7_1_sip_access", "B7_2_timestamps", "B7_3_coverage"))
    return _write("gates", {"report": reports[-1].name, "pass": ok, "quotes_available": bool(g.get("B7_4_spreads", {}).get("pass")),
                            "gates": {k: v.get("pass") for k, v in g.items()}})


def phase_selection(source, phase: str, placebo_reps: int = PLACEBO_REPS) -> dict:
    if not _read("gates")["pass"]:
        sys.exit("data gates failed: the study does not run (B7)")
    consumed.check_selection_window(SCOPE, *PERIODS[phase], path=CONSUMED_LEDGER)
    out = run_period(source, phase, list(orb.CONFIGS), placebo_reps)
    if phase == "dev":
        gate = sanity_gate(out)
        out["sanity_gate"] = gate
        out["qualifiers"] = dev_qualifiers(out, gate)
    else:
        out["qualifiers"] = validation_qualifiers(out)
    js = _write(phase, out)
    record("result", f"orb_{phase}", {"prereg": "prereg_orb", "amendments": ["prereg_orb_amendment1", "prereg_orb_amendment2"]},
           "..".join(PERIODS[phase]), f"ORB {phase}", metrics={"qualifiers": js["qualifiers"]})
    return js


def phase_freeze(config: str) -> dict:
    dev, val = _read("dev"), _read("validation")
    qd, qv = dev["qualifiers"].get(config, {}), val["qualifiers"].get(config, {})
    qualified = bool(qd.get("qualified")) and bool(qv.get("net_all_mean_ge_0"))
    if not qualified:
        record("result", "orb_stop_after_validation", {"config": config, "dev": qd, "validation": qv}, "..".join(PERIODS["final"]),
               "B9: no qualified configuration; final window stays unread")
        sys.exit(f"B9: '{config}' did not qualify (dev {qd}, validation {qv}); the study stops and the final window stays UNREAD")
    for k in orb.CONFIGS:
        record("trial", f"orb_{k}", orb.CONFIGS[k].as_dict(), "..".join(PERIODS["dev"]), "ORB configuration tried")
    frozen = {"config": config, "hash": config_hash(), "qualified": True, "n_trials": ev.trial_count(),
              "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    FROZEN.write_text(json.dumps(frozen, indent=1))
    record("frozen_config", "orb_frozen", frozen, "..".join(PERIODS["final"]), "ORB frozen before the final window")
    return frozen


def phase_final(source, placebo_reps: int = PLACEBO_REPS) -> dict:
    if not FROZEN.exists() or not json.loads(FROZEN.read_text()).get("qualified"):
        sys.exit("B9: no qualified frozen candidate; the final window is NOT read")
    frozen = json.loads(FROZEN.read_text())
    h = config_hash()
    if h != frozen["hash"]:
        record("violation", "orb_final_refused", {"frozen": frozen["hash"], "current": h}, "..".join(PERIODS["final"]),
               "final evaluation refused: configuration or code changed after the freeze")
        sys.exit("REFUSED: rules, parameters, costs or code changed after the freeze (recorded as a violation)")
    consumed.mark_consumed(SCOPE, *PERIODS["final"], "ORB", note="final window read for the frozen configuration",
                           path=CONSUMED_LEDGER)
    out = run_period(source, "final", sorted({frozen["config"], "long_short"}), placebo_reps)
    s = out["configs"][frozen["config"]]
    days = [d for d in source.days(*PERIODS["final"]) if not excluded(d)]
    out["verdict"] = ev.e_criteria(s["_frames"]["rule"], s["_stress"], days, s["_placebo_means"], frozen["n_trials"],
                                   cost_measured=s["cost_path"] == "measured spread")
    out["frozen"] = frozen
    js = _jsonable(out)
    p = RESULTS / "final.json"
    if p.exists():
        same = json.loads(p.read_text()) == js
        record("reproduction", "orb_final_reproduction", {"hash": h}, "..".join(PERIODS["final"]), "deterministic re-run",
               metrics={"identical": same})
        print("REPRODUCED IDENTICALLY" if same else "DIFFERS FROM THE STORED FINAL RESULT")
        return js
    _write("final", out)
    record("result", "orb_final", {"hash": h, "config": frozen["config"]}, "..".join(PERIODS["final"]), "ORB final",
           metrics={"verdict": js["verdict"]["verdict"]})
    return js


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["gates", "dev", "validation", "freeze", "final"])
    ap.add_argument("--config", default="primary", choices=list(orb.CONFIGS))
    a = ap.parse_args(argv)
    if a.phase == "gates":
        print(json.dumps(phase_gates(), indent=1)); return
    if a.phase == "freeze":
        print(json.dumps(phase_freeze(a.config), indent=1)); return
    if a.phase == "final" and (not FROZEN.exists() or not json.loads(FROZEN.read_text()).get("qualified")):
        sys.exit("B9: no qualified frozen candidate; the final window is NOT read")
    from research.orb.data import AlpacaSource
    from tradelab.pit.alpaca_sip import AlpacaData
    quotes = _read("gates")["quotes_available"]
    lo = PERIODS["dev"][0] if a.phase == "dev" else PERIODS[a.phase][0]
    src = AlpacaSource(AlpacaData.from_env(), lo, PERIODS[a.phase][1], quotes=quotes)
    js = phase_selection(src, a.phase) if a.phase in ("dev", "validation") else phase_final(src)
    print(json.dumps({k: js.get(k) for k in ("qualifiers", "sanity_gate", "verdict") if k in js}, indent=1, default=str))


if __name__ == "__main__":
    main()
