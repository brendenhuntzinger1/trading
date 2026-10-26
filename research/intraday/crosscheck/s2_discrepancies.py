"""Every S2 trade that differs between the engine replay and the research trade list."""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
from stocks import S, U, OUT, daily, Engine, IntradayLimits, S2GapReversal, STOCK_AT_OPEN, replay_daily_open_close, trades_frame

stocks = U[U.kind == "stock"].yahoo.tolist()
sector = [s for s in ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"] if (ROOT / "data/stocks/daily" / f"{s}.csv").exists()]
data = {s: daily(s) for s in stocks + sector + ["SPY"]}
L = IntradayLimits(market="stocks", max_positions=5, max_weight=0.2, max_gross=1.0, daily_loss_limit=0.99,
                   max_entries_per_day=10, no_entries_last_minutes=0)
setup = S2GapReversal(data)
eng = Engine(L, [setup], {"S2": STOCK_AT_OPEN}, S, 100_000.0)
replay_daily_open_close(eng, data, S, start="2021-01-04", end="2026-10-24")
e = trades_frame(eng); e["session"] = [S.day_key(t) for t in e.entry_time]
r = pd.read_csv(OUT / "test_trades_S2_default_thr1_top5_stocks+sector.csv")
k = ["session", "symbol"]
eo = e.merge(r[k], on=k, how="left", indicator=True).query("_merge=='left_only'")
ro = r.merge(e[k], on=k, how="left", indicator=True).query("_merge=='left_only'")
dec = pd.DataFrame([d.__dict__ for d in eng.decisions]); dec["session"] = [S.day_key(t) for t in dec["at"]]
rows = []
for _, x in ro.iterrows():
    d = dec[(dec.session == x.session) & (dec.symbol == x.symbol)]
    rows.append(("research_only", x.session, x.symbol, round(x.signal, 5), round(x.net_ret, 5),
                 "; ".join(" | ".join(v) for v in d.reasons) if len(d) else "engine never received the signal"))
for _, x in eo.iterrows():
    rr = r[r.session == x.session]
    rows.append(("engine_only", x.session, x.symbol, None, round(x.net_ret, 5),
                 f"research traded {len(rr)} that day: {sorted(rr.symbol)}"))
out = pd.DataFrame(rows, columns=["side", "session", "symbol", "research_signal", "net_ret", "engine_reason"])
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
print(out.to_string(index=False))
out.to_csv(Path(__file__).parent / "s2_discrepancies.csv", index=False)
