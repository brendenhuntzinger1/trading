"""Download (or resume) intraday bars: python research/phase2/fetch_intraday.py 1Min 2016 2026-10-23 SPY,QQQ,IWM,DIA"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.phase2.data import Phase2Data                      # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData                   # noqa: E402

tf, first, last, syms = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4].split(",")
d = Phase2Data(AlpacaData.from_env(), log=lambda m: print(m, flush=True))
for y in range(first, int(last[:4]) + 1):
    got = d.intraday_year(syms, y, tf, last)
    print(tf, y, {s: len(v) for s, v in got.items()}, flush=True)
print("INTRADAY DONE", flush=True)
