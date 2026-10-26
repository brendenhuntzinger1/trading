"""Download (or resume) the phase-2 daily panels: python research/phase2/fetch_daily.py 2016 2026-10-23 [all,raw]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.phase2.data import Phase2Data                      # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData                   # noqa: E402

first, last = int(sys.argv[1]), sys.argv[2]
d = Phase2Data(AlpacaData.from_env(), log=lambda m: print(m, flush=True))
print("universe", len(d.universe()), flush=True)
for adj in (sys.argv[3].split(",") if len(sys.argv) > 3 else ("all", "raw")):
    p = d.build_panel(first, last, adj)
    print("panel", adj, {k: v.shape for k, v in p.items()}, flush=True)
print("PANELS DONE", flush=True)
