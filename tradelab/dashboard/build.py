"""Render the monitoring dashboard from the journal and research outputs.

Writes two files: ``fragment.html`` (page content for publishing as an
artifact snapshot) and ``index.html`` (the same page as a standalone document
for the always-on host). Simulated results are always labelled as such.

    .venv/bin/python -m tradelab.dashboard.build
"""
from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradelab.execution.accounting import pnl
from tradelab.risk.limits import RiskLimits

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "dashboard"
E = html.escape

CSS = """
/* Layout: a single scanning column - status strip, accounts, then evidence - like a desk blotter. */
:root {
  --paper: #f5f6f4; --panel: #ffffff; --ink: #1d2327; --muted: #5d676c; --rule: #d9dedd;
  --accent: #2c5f7c; --good: #1d7349; --warn: #9a6408; --bad: #b3261e; --sim: #8a5a00; --sim-bg: #fbf1dc;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #141a1d; --panel: #1b2226; --ink: #e3e8e9; --muted: #95a1a6; --rule: #2d373c;
  --accent: #7fb3d1; --good: #5cc28d; --warn: #e0a940; --bad: #ef7a72; --sim: #f0c26b; --sim-bg: #33290f; color-scheme: dark } }
:root[data-theme="dark"] {
  --paper: #141a1d; --panel: #1b2226; --ink: #e3e8e9; --muted: #95a1a6; --rule: #2d373c;
  --accent: #7fb3d1; --good: #5cc28d; --warn: #e0a940; --bad: #ef7a72; --sim: #f0c26b; --sim-bg: #33290f; color-scheme: dark }
body { background: var(--paper); color: var(--ink); font: 14px/1.5 var(--body); }
.wrap { max-width: 1180px; margin: 0 auto; padding-block: 20px 48px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 22px; }
header { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: baseline; justify-content: space-between; }
h1 { font: 600 26px/1.1 var(--display); letter-spacing: .01em; margin: 0; text-wrap: balance; }
h2 { font: 600 17px/1.2 var(--display); letter-spacing: .02em; margin: 0 0 8px; text-wrap: balance; }
.meta { color: var(--muted); font: 12px/1.4 var(--mono); }
.mode { display: inline-flex; gap: 8px; align-items: center; font: 600 12px/1 var(--mono); letter-spacing: .08em;
  color: var(--sim); background: var(--sim-bg); border: 1px dashed var(--sim); padding: 7px 10px; border-radius: 3px; }
.banner { background: var(--sim-bg); color: var(--ink); border-left: 3px solid var(--sim); padding: 10px 14px; font-size: 13px; }
section { display: grid; gap: 8px; min-width: 0; }
.note { color: var(--muted); font-size: 12.5px; max-width: 75ch; margin: 0; }
.strip { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; gap: 6px; align-items: center; font: 12px/1 var(--mono); padding: 6px 9px;
  border: 1px solid var(--rule); background: var(--panel); border-radius: 3px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.ok .dot { background: var(--good); } .warn .dot { background: var(--warn); } .bad .dot { background: var(--bad); }
.scroll { overflow-x: auto; border: 1px solid var(--rule); background: var(--panel); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; white-space: nowrap; }
th { font: 600 11px/1.3 var(--body); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); background: var(--paper); }
td.n, th.n { text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
td.wrap-text { white-space: normal; min-width: 220px; max-width: 420px; }
tr:last-child td { border-bottom: 0; }
.pos { color: var(--good); } .neg { color: var(--bad); }
.pill { font: 600 11px/1 var(--mono); padding: 3px 6px; border-radius: 2px; border: 1px solid currentColor; }
.pill.approved { color: var(--good); } .pill.rejected { color: var(--bad); } .pill.skipped { color: var(--muted); }
.tag { font: 11px/1 var(--mono); color: var(--muted); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 22px; }
svg text { fill: var(--muted); font: 11px var(--mono); }
.bt { border-left: 3px solid var(--muted); padding-left: 12px; }
a { color: var(--accent); }
"""


def q(db, sql, *args):
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(sql, args)]


def money(x, signed=False):
    if x is None:
        return "–"
    x = 0.0 if abs(x) < 0.005 else x
    s = f"{x:+,.2f}" if signed else f"{x:,.2f}"
    cls = "" if not signed else ("pos" if x > 0 else "neg" if x < 0 else "")
    return f'<span class="{cls}">${s}</span>' if cls else f"${s}"


def pct(x, signed=False):
    return "–" if x is None else (f"{x:+.1%}" if signed else f"{x:.1%}")


def table(headers, rows, numeric=()):
    th = "".join(f'<th class="{"n" if i in numeric else ""}">{E(h)}</th>' for i, h in enumerate(headers))
    tr = "".join("<tr>" + "".join(f'<td class="{"n" if i in numeric else ""}{" wrap-text" if isinstance(c, tuple) else ""}">'
                                  f'{c[0] if isinstance(c, tuple) else c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def equity_chart(series: dict[str, list[tuple[str, float]]], capital: float) -> str:
    pts = [v for s in series.values() for _, v in s]
    if not pts or max(len(s) for s in series.values()) < 2:
        return '<p class="note">The equity chart starts after the second daily mark.</p>'
    W, H, L, R, T, B = 640, 220, 56, 120, 12, 26
    dates = sorted({d for s in series.values() for d, _ in s})
    lo, hi = min(pts + [capital]), max(pts + [capital])
    pad = (hi - lo) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    x = lambda d: L + (W - L - R) * dates.index(d) / max(1, len(dates) - 1)
    y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    colors = ["var(--accent)", "var(--muted)", "var(--warn)", "var(--good)"]
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:760px" role="img" aria-label="Simulated equity by account">']
    for v in (lo + pad, capital, hi - pad):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--rule)"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:,.0f}</text>')
    for i, (name, s) in enumerate(series.items()):
        c = colors[i % len(colors)]
        path = " ".join(f"{'M' if j == 0 else 'L'}{x(d):.1f},{y(v):.1f}" for j, (d, v) in enumerate(s))
        out.append(f'<path d="{path}" fill="none" stroke="{c}" stroke-width="{2 if i == 0 else 1.4}"/>')
        d, v = s[-1]
        out.append(f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="3" fill="{c}"/>'
                   f'<text x="{x(d) + 6:.1f}" y="{y(v) + 4:.1f}">{E(name.replace("paper-", ""))}</text>')
    out.append(f'<text x="{L}" y="{H - 6}">{dates[0][:10]}</text><text x="{W - R}" y="{H - 6}" text-anchor="end">{dates[-1][:10]}</text></svg>')
    return "".join(out)


def events_section(now: datetime) -> str:
    try:
        from datetime import timedelta
        from tradelab.events.flags import active_flags
        from tradelab.events.store import EventStore
        store = EventStore()
        flags = active_flags(now, store)
        evs = sorted(store.events(since=now - timedelta(days=7)), key=lambda e: e.first_seen_at, reverse=True)
    except Exception as e:
        return f'<section><h2>Events and sources</h2><p class="note">Event store unavailable: {E(repr(e))}</p></section>'
    frows = [[E(f.kind), E(f.severity), E(", ".join(f.assets)), E(f.starts_at.strftime("%Y-%m-%d %H:%M") if f.starts_at else "–"),
              (E(f.reason),), " ".join(f'<a href="{E(u)}" rel="noopener" target="_blank">source</a>' for u in f.source_urls[:2])] for f in flags]
    erows = [[E(e.first_seen_at.strftime("%m-%d %H:%M")), E(e.published_at.strftime("%m-%d %H:%M")), E(e.source),
              E(getattr(e.tier, "name", str(e.tier)).lower()), E(str(getattr(e.category, "value", e.category))), E(", ".join(e.assets) or "–"),
              E(str(getattr(e.novelty, "value", e.novelty))), str(e.corroboration),
              (f'<a href="{E(e.source_url)}" rel="noopener" target="_blank">{E(e.title[:110])}</a>',)] for e in evs[:25]]
    return f"""<section><h2>Events and sources</h2>
<p class="note">Active flags are recorded with each decision. They do not block trades: that stays off until prospective
evaluation shows they help. Market-impact claims are not made for historical news, because no point-in-time news archive exists.</p>
{table(["Flag", "Severity", "Assets", "Starts (UTC)", "Reason", "Source"], frows) if frows else '<p class="note">No active flags.</p>'}
{table(["First seen", "Published", "Source", "Tier", "Category", "Assets", "Novelty", "Corroborated", "Item"], erows) if erows else '<p class="note">No events first seen in the last 7 days.</p>'}</section>"""


def build(journal: Path = ROOT / "data" / "journal_paper.db", config: Path = ROOT / "config" / "paper.toml") -> Path:
    import tomllib
    now = datetime.now(timezone.utc)
    cfg = tomllib.loads(config.read_text())
    limits, cfg_hash = RiskLimits.load(config)
    capital = cfg["capital"]
    db = sqlite3.connect(journal)
    accounts = [r["account"] for r in q(db, "SELECT DISTINCT account FROM equity ORDER BY account")]
    marks_rows = q(db, "SELECT * FROM equity ORDER BY at")
    last = {r["account"]: r for r in marks_rows}
    last_run = max((r["at"] for r in marks_rows), default=None)

    # accounts
    acc_rows, series = [], {}
    for a in accounts:
        m = last[a]
        marks = json.loads(m["marks"])
        fills = q(db, "SELECT asset, side, base, price, fee FROM fills WHERE account=? ORDER BY at", a)
        realized = unreal = fees = exit_cost = 0.0
        for asset in {f["asset"] for f in fills}:
            p = pnl([(f["side"], f["base"], f["price"], f["fee"]) for f in fills if f["asset"] == asset], marks.get(asset, 0.0))
            realized += p.realized; unreal += p.unrealized; fees += p.fees; exit_cost += p.est_exit_cost
        eq = [r for r in marks_rows if r["account"] == a]
        op_cost = sum(r["operating_cost"] for r in eq)
        peak = max([capital] + [r["equity"] for r in eq])
        net = m["equity"] - op_cost - capital
        positions = json.loads(m["positions"])
        exposure = sum(q_ * marks.get(k, 0) for k, q_ in positions.items()) / m["equity"] if m["equity"] else 0
        bench = a.endswith(("buy_hold", "fixed_allocation"))
        acc_rows.append([f'{E(a.replace("paper-", ""))} ' + ('<span class="tag">benchmark</span>' if bench else ''),
                         money(m["equity"]), money(net, True), money(realized, True), money(unreal, True), money(-fees, True),
                         money(-op_cost, True), money(-exit_cost, True), pct(m["equity"] / peak - 1), pct(exposure), len(eq)])
        series[a] = [(r["at"], r["equity"] - r["operating_cost"]) for r in eq]

    # positions and orders
    pos_rows = []
    for a in accounts:
        marks = json.loads(last[a]["marks"])
        for asset, qty in json.loads(last[a]["positions"]).items():
            pos_rows.append([E(a.replace("paper-", "")), E(asset), f"{qty:.8f}", money(marks.get(asset)), money(qty * marks.get(asset, 0))])
    open_orders = q(db, "SELECT account, data, status FROM orders WHERE status NOT IN ('filled','cancelled','rejected','not_found')")
    oo_rows = [[E(o["account"]), E(json.loads(o["data"])["asset"]), E(json.loads(o["data"])["side"]), E(o["status"])] for o in open_orders]

    # decisions
    dec = q(db, "SELECT * FROM decisions ORDER BY at DESC, account, asset LIMIT 60")
    dec_rows = [[E(d["at"][:16].replace("T", " ")), E(d["account"].replace("paper-", "")), E(d["asset"]),
                 pct(d["current_weight"]) + " → " + pct(d["target_weight"]),
                 f'<span class="pill {E(d["outcome"])}">{E(d["outcome"])}</span>', money(d["final_notional"]),
                 (E("; ".join(json.loads(d["reasons"] or "[]"))),), E(", ".join(json.loads(d["breakers"] or "[]")) or "none"),
                 f'<span class="tag">{E(d["strategy_version"] or "")} · cfg {E(d["config_hash"] or "")}</span>',
                 E((d["data_as_of"] or "–")[:10])] for d in dec]

    # risk status
    brk = q(db, "SELECT * FROM breaker_log WHERE at = (SELECT MAX(at) FROM breaker_log)") if last_run else []
    active_now = [b for b in brk if b["at"] == last_run]
    util = []
    for a in accounts:
        m = last[a]
        marks = json.loads(m["marks"])
        gross = sum(q_ * marks.get(k, 0) for k, q_ in json.loads(m["positions"]).items()) / m["equity"]
        t30 = db.execute("SELECT COALESCE(SUM(base*price),0) FROM fills WHERE account=? AND at>=datetime('now','-30 day')", (a,)).fetchone()[0] / m["equity"]
        today = db.execute("SELECT COUNT(*) FROM orders WHERE account=? AND substr(updated_at,1,10)=?", (a, last_run[:10])).fetchone()[0]
        peak = max([capital] + [r["equity"] for r in marks_rows if r["account"] == a])
        util.append([E(a.replace("paper-", "")), f"{gross:.0%} / {limits.max_gross_exposure:.0%}",
                     f"{t30:.2f}× / {limits.max_turnover_30d:.1f}×", f"{today} / {limits.max_orders_per_day}",
                     f"{1 - m['equity'] / peak:.1%} / {limits.max_drawdown_limit:.0%}"])

    # freshness
    chips = []
    if last_run:
        age_h = (now - datetime.fromisoformat(last_run)).total_seconds() / 3600
        chips.append(("ok" if age_h < 26 else "bad", f"last cycle {last_run[:16].replace('T', ' ')} UTC ({age_h:.1f}h ago)"))
    for f in sorted((ROOT / "data" / "paper").glob("*_1d.csv")):
        import pandas as pd
        d = pd.read_csv(f, usecols=["available_at"]).available_at.iloc[-1]
        age = (now - datetime.fromisoformat(d)).total_seconds() / 3600
        chips.append(("ok" if age < 26 else "bad", f"{f.stem.replace('_1d', '')} daily bar to {d[:16].replace('T', ' ')} ({age:.0f}h)"))
    sp = ROOT / "data" / "live" / "status.json"
    if sp.exists():
        st = json.loads(sp.read_text())
        age = (now - datetime.fromisoformat(st["at"])).total_seconds()
        if age > 300:
            chips.append(("bad", f"live monitor silent for {age / 60:.0f} min"))
        for sym, r in st["symbols"].items():
            good = r["connected"] and r["book_valid"] and not r["stale"]
            chips.append(("ok" if good and age <= 300 else "bad",
                          f"{st['venue']} {sym} {'live' if good else 'DOWN'} · spread {r['spread_bps'] or 0:.2f}bp · "
                          f"depth ±25bp ${(r['depth_bid'] or 0) / 1e6:.1f}M/${(r['depth_ask'] or 0) / 1e6:.1f}M"))
        if st["breakers"]:
            chips.append(("bad", "market breakers: " + ", ".join(st["breakers"])))
    else:
        chips.append(("warn", "live monitor not running"))
    chips.append(("bad" if active_now else "ok", "breakers: " + (", ".join(sorted({b['breaker'] for b in active_now})) or "none active")))
    lat = q(db, "SELECT AVG(decided_to_submit_ms) d2s, AVG(submit_to_ack_ms) s2a, AVG(slippage_bps) slip, COUNT(*) n FROM latency")[0]

    # historical simulation (audit)
    audit_html = ""
    ap = ROOT / "research" / "out" / "audit.json"
    if ap.exists():
        au = json.loads(ap.read_text())
        b = au["4_benchmarks"]
        rows = [[E(k), pct(v["CAGR"]), f'{v["sharpe"]:.2f}', pct(v["maxDD"]), pct(v["exposure"]), f'{v["orders_per_yr"]:.0f}']
                for k, v in b.items()]
        ho = au["10_holdouts"]
        hrows = [[E(k), pct(v["base_CAGR"]), pct(v["bh_CAGR"]), pct(v["base_maxDD"]), pct(v["bh_maxDD"]),
                  '<span class="pill approved">pass</span>' if v["PASS"] else '<span class="pill rejected">fail</span>'] for k, v in ho.items()]
        audit_html = f"""<section class="bt"><h2>Historical simulation: audit, BTC+ETH 2018–2026</h2>
<p class="note">Backtest, not trading results. In-sample: the strategy was designed on this data. Costs: Coinbase taker 0.66% per side.</p>
{table(["Strategy", "CAGR", "Sharpe", "Max DD", "Exposure", "Orders/yr"], rows, numeric=(1, 2, 3, 4, 5))}
<p class="note">Pre-registered holdouts (assets not used in design):</p>
{table(["Holdout", "Strategy CAGR", "Buy & hold CAGR", "Strategy max DD", "Buy & hold max DD", "Registered test"], hrows, numeric=(1, 2, 3, 4))}</section>"""

    research_html = ""
    rp = ROOT / "research" / "out" / "dashboard_research.json"
    if rp.exists():
        rr = json.loads(rp.read_text())
        research_html = f"""<section class="bt"><h2>Strategy research: untouched test period</h2>
<p class="note">{E(rr.get("note", ""))}</p>{table(rr["headers"], [[E(str(c)) for c in r] for r in rr["rows"]])}</section>"""

    events_html = events_section(now)

    body = f"""
<div class="wrap">
<header><div><h1>Tradelab Monitor</h1>
<div class="meta">venue {E(cfg["venue"])} · config {cfg_hash} · built {now:%Y-%m-%d %H:%M} UTC</div></div>
<span class="mode">PAPER · SIMULATED MONEY</span></header>
<div class="banner">Every figure in the account and order sections comes from paper trading: real prices, simulated
fills, no real money. They are not profits. Backtest sections are labelled separately. No live account is connected.</div>
<div class="strip">{"".join(f'<span class="chip {c}"><span class="dot"></span>{E(t)}</span>' for c, t in chips)}</div>

<section><h2>Paper accounts</h2>
<p class="note">${capital:,.0f} simulated starting capital each. Net is after exchange fees, simulated slippage and operating costs.
Estimated exit cost is what closing every position now would cost at the taker fee; it is not deducted from net.</p>
{table(["Account", "Equity", "Net vs start", "Realized", "Unrealized", "Fees paid", "Operating cost", "Est. exit cost", "Drawdown", "Exposure", "Marks"], acc_rows, numeric=tuple(range(1, 11)))}
{equity_chart(series, capital)}</section>

<div class="grid2">
<section><h2>Positions</h2>{table(["Account", "Asset", "Quantity", "Mark", "Value"], pos_rows, numeric=(2, 3, 4)) if pos_rows else '<p class="note">No positions.</p>'}</section>
<section><h2>Outstanding orders</h2>{table(["Account", "Asset", "Side", "Status"], oo_rows) if oo_rows else '<p class="note">No working orders.</p>'}
<h2>Execution quality</h2><p class="note">Orders measured: {lat["n"]}. Decision to submit {lat["d2s"] or 0:.0f} ms;
submit to acknowledgement {lat["s2a"] or 0:.0f} ms; average slippage vs mid {lat["slip"] or 0:.1f} bp (paper fills walk the live order book).</p></section>
</div>

<section><h2>Risk limits</h2><p class="note">Used / limit. Limits load from the config file at start-up; no strategy or model can change them.</p>
{table(["Account", "Gross exposure", "30-day turnover", "Orders today", "Drawdown"], util)}</section>

<section><h2>Decisions</h2><p class="note">Every considered trade, including rejected and skipped ones, with the reason, active breakers,
strategy version, config hash and the last candle the decision used.</p>
{table(["Time (UTC)", "Account", "Asset", "Weight now → target", "Outcome", "Notional", "Reasons", "Breakers", "Version", "Data as of"], dec_rows, numeric=(5,))}</section>
{events_html}
{research_html}
{audit_html}
</div>"""
    head = ('<title>Tradelab Monitor</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:wght@400;600&display=swap">\n'
            f"<style>{CSS}</style>\n")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fragment.html").write_text(head + body)
    (OUT / "index.html").write_text('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                                    f"{head}</head><body>{body}</body></html>")
    return OUT / "index.html"


if __name__ == "__main__":
    print(build())
