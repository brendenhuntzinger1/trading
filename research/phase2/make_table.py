"""Generate the phase-2 results table from the result files (no hand-copied numbers).

    python research/phase2/make_table.py > research/phase2/results/TABLE.md
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent / "results"
NAMES = {"f3": "F3 market intraday momentum (SPY/QQQ...)", "f5": "F5 RSI(2) pullback (ETFs)",
         "f1": "F1 liquidity-provision reversal", "f6": "F6 ML ranking", "f4": "F4 end-of-day reversal",
         "f2": "F2 earnings drift"}


def fmt(x, nd=1):
    return "n/a" if x is None else f"{x:+.{nd}f}"


def main():
    print("| Family | Config | Net bp/day [90% CI] | Gross bp/day | Cost bp/day | Gross vs control bp/day [90% CI] | Net years + | Qualified |")
    print("|---|---|---|---|---|---|---|---|")
    for key, label in NAMES.items():
        p = R / f"{key}_dev.json"
        if not p.exists():
            print(f"| {label} | — | not yet run | | | | | |")
            continue
        d = json.loads(p.read_text())
        for cfg, v in d["configs"].items():
            if "superseded" in cfg:
                continue
            s = v["summary"]
            yrs = s["by_year_net"]
            ci = s["net"]["ci_bp"]
            g = s["vs_control_gross_bp"]
            print(f"| {label} | {cfg} | {fmt(s['net']['mean_bp'])} [{fmt(ci[0])}, {fmt(ci[1])}] | {fmt(s['gross']['mean_bp'])} | "
                  f"{s['cost_bp_per_day']:.1f} | {fmt(g['mean'])} [{fmt(g['ci'][0])}, {fmt(g['ci'][1])}] | "
                  f"{sum(x > 0 for x in yrs.values())}/{len(yrs)} | {'yes' if v['qualifiers'].get('qualified') else 'no'} |")
            label = ""


if __name__ == "__main__":
    main()
