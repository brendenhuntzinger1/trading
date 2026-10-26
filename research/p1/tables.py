"""Markdown tables for P1_REPORT.md, generated from research/p1/results/*.json (no numbers typed by hand)."""
import json
from pathlib import Path

R = Path(__file__).resolve().parent / "results"


def pct(x, d=2):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def ci(c, d=2):
    return f"[{c[0] * 100:+.{d}f}, {c[1] * 100:+.{d}f}]"


def main():
    out = []
    for hz, per in (("p1a", "day"), ("p1b", "week")):
        g = json.loads((R / f"{hz}_gate.json").read_text())
        out.append(f"### {hz.upper()} development stopping check ({g['periods_used']} {per}s, median {g['coins_per_period']['median']:.0f} coins)\n")
        out.append(f"Oracle top-3 selection excess {pct(g['oracle_selection_excess_mean'])} per {per}; B1 turnover {g['b1_turnover_per_period']:.2f} per {per}.\n")
        out.append("| Round trip | Label | ρ* at full replacement | ρ* at B1 turnover | ρ* at τ = 0.25 |\n|---|---|---|---|---|")
        for k, v in g["required_rho"].items():
            out.append(f"| {float(k) * 100:.2f}% | {v['label']} | {v['rho_star_tau1']} | {v['rho_star_tau_b1']} | {v['rho_star_tau025']} |")
        out.append(f"\nDecision: **{g['decision']}**.\n")
        for ph in ("dev", "validation", "final"):
            d = json.loads((R / f"{hz}_{ph}.json").read_text())
            n = d.get("oof_periods", d.get("periods"))
            rng = d.get("oof_range", d.get("range"))
            out.append(f"### {hz.upper()} {ph} ({n} {per}s, {rng[0][:10]} → {rng[1][:10]}; base Coinbase cost 1.32%)\n")
            out.append(f"| Config | Rank IC [90% CI] | Net per {per} [90% CI] | Sharpe | Max DD | Exposure | Turnover/{per} | Cost/{per} | "
                       f"Selection excess (gross) [90% CI] | α vs EW [90% CI] | β | Thirds > 0 |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
            for name, c in d["configs"].items():
                b = c["base"]
                out.append(f"| {name} | {c['rank_ic']['mean']:+.3f} [{c['rank_ic']['ci90'][0]:+.3f}, {c['rank_ic']['ci90'][1]:+.3f}] | "
                           f"{pct(b['mean'])} {ci(b['net_per_period']['ci90'])} | {b['sharpe']:.2f} | {b['max_drawdown'] * 100:.0f}% | "
                           f"{b['exposure'] * 100:.0f}% | {b['turnover_per_period']:.2f} | {pct(b['cost_per_period'])} | "
                           f"{pct(b['selection_excess_gross']['mean'])} {ci(b['selection_excess_gross']['ci90'])} | "
                           f"{pct(b['alpha_vs_ew']['alpha'])} {ci(b['alpha_vs_ew']['alpha_ci90'])} | {b['alpha_vs_ew']['beta']:.2f} | {b['thirds_positive']}/3 |")
            cp = d["comparators"]
            out.append(f"\nComparators: no trade 0; EW universe {pct(cp['ew_universe']['mean'])}/{per}, Sharpe {cp['ew_universe']['sharpe']:.2f}, "
                       f"total {cp['ew_universe']['total_return'] * 100:+.0f}%, max DD {cp['ew_universe']['max_drawdown'] * 100:.0f}%; "
                       f"BTC buy-and-hold Sharpe {cp['btc_buy_hold']['sharpe']:.2f}, total {cp['btc_buy_hold']['total_return'] * 100:+.0f}%, "
                       f"max DD {cp['btc_buy_hold']['max_drawdown'] * 100:.0f}%.")
            if "pbo" in d:
                out.append(f"PBO across the {len(d['configs'])} configurations: **{d['pbo']['pbo']:.2f}**. "
                           f"Selected candidate: **{d['selection']['candidate']}**.")
            abst = {k: c["abstention_value"] for k, c in d["configs"].items() if "abstention_value" in c}
            if abst:
                out.append("Abstention value (abstaining minus forced-to-fill, net per period): " + "; ".join(
                    f"{k} {pct(v['abstaining_minus_forced_net']['mean'])} {ci(v['abstaining_minus_forced_net']['ci90'])}" for k, v in abst.items()))
            if "M2" in d["configs"]:
                cal = d["configs"]["M2"]["calibration"]
                out.append(f"M2 calibration: base rate {cal['base_rate']:.3f}, Brier skill {cal['brier_skill_vs_base_rate']:+.4f}, ECE {cal['ece']:.3f}.")
            grid = {k: {kk: vv["sharpe"] for kk, vv in c["cost_grid"].items()} for k, c in d["configs"].items()}
            out.append("Sharpe across the Coinbase cost grid (0.50 / 0.80 / 1.06 / 1.32 / 1.92 / 2.52%): " + "; ".join(
                f"{k} " + " / ".join(f"{v:.2f}" for v in g_.values()) for k, g_ in grid.items()))
            if "verdict" in d:
                out.append(f"\n**Verdict: {d['verdict']['verdict']}**. No-useful-effect test per config: " + ", ".join(
                    f"{k} {'REJECT' if v['reject_no_useful_effect'] else 'not rejected'}" for k, v in d['verdict']['per_config_reject_test'].items()))
            out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
