"""Re-run the ORB development period on cached data and save trade-level frames for auditing (no new API data,
no rule changes). Used to audit the direction-only benchmark, which looked strong in development.

    python research/orb/dump_dev_frames.py <chunk_index> <n_chunks>
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.orb import study                                  # noqa: E402
from research.orb.audit_mechanics import DaysSource             # noqa: E402
from research.orb.data import AlpacaSource                      # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData                  # noqa: E402

OUT = ROOT / "data" / "stocks" / "frames"


def main(i: int, n: int):
    src = AlpacaSource(AlpacaData.from_env(), *study.PERIODS["dev"])
    days = [d for d in src.days(*study.PERIODS["dev"]) if not study.excluded(d)]
    chunk = days[i * len(days) // n:(i + 1) * len(days) // n]
    out = study.run_period(DaysSource(src, chunk), "dev", ["primary"], placebo_reps=1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"dev_primary_{i}_of_{n}.pkl").write_bytes(pickle.dumps(out["configs"]["primary"]["_frames"]))
    print("saved", i, chunk[0], chunk[-1], flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
