"""F2 data: earnings headlines from Alpaca news (Benzinga), staged by window (PHASE2_PROTOCOL §4: later windows
are fetched only if development qualifies).

    python research/phase2/f2_news_fetch.py 2020-01-01 2022-12-31    # development window

Universe: every operating company that was in the point-in-time top-1,000 by dollar volume on any session in
the window. All headlines are paged through per batch of 25 symbols per calendar quarter; only earnings-like
headlines are kept: "... EPS ... Beats/Misses/In-Line ... Estimate", or "... EPS $x" plus "Sales" with "Beat/Miss".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.phase2 import xs                                           # noqa: E402
from research.phase2.data import Cache, CACHE                             # noqa: E402
from research.phase2.f1_reversal import load_panels                       # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData                            # noqa: E402

EARN = re.compile(r"\bEPS\b.*\b(Beats?|Miss(es)?|In-?Line|Inline)\b", re.I)


def universe(lo: str, hi: str) -> list[str]:
    a, r, comp = load_panels()
    elig, _ = xs.eligibility(r["close"], r["volume"], allowed=comp, top_n=1000)
    e = elig[(elig.index >= lo) & (elig.index <= hi)]
    return sorted(e.columns[e.any()])


def main(lo: str, hi: str) -> None:
    cache = Cache(CACHE)
    c = AlpacaData.from_env()
    syms = universe(lo, hi)
    print("universe", len(syms), flush=True)
    quarters = pd.period_range(lo, hi, freq="Q")
    for q in quarters:
        s, e = q.start_time.strftime("%Y-%m-%dT00:00:00Z"), (q.end_time.floor("s")).strftime("%Y-%m-%dT%H:%M:%SZ")
        kept = 0
        for i in range(0, len(syms), 25):
            chunk = syms[i:i + 25]
            key = f"earn_{q}_{chunk[0]}_{len(chunk)}"
            got = cache.get("news", key)
            if got is None:
                st, rows = c.news(chunk, s, e)
                if st != 200:
                    raise RuntimeError(f"news failed {q} {chunk[0]}: HTTP {st}")
                got = [{"id": r["id"], "created_at": r["created_at"], "headline": r["headline"],
                        "symbols": r.get("symbols", [])} for r in rows if EARN.search(r.get("headline", ""))]
                cache.put("news", key, got)
            kept += len(got)
        print(q, "earnings-like headlines", kept, flush=True)
    print("NEWS DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
