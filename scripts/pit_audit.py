"""Reproduce the crypto hourly-bar quality audit (docs/DATA_AUDIT.md).

    .venv/bin/python scripts/pit_audit.py

Reads data/pit/hourly/*.csv and data/pit/ever_eligible_2021.json; writes data/pit/crypto_quality.csv
and data/pit/crypto_audit_summary.json. Nothing in the bar files is changed.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.pit import crypto_bars as cb  # noqa: E402
from tradelab.pit import crypto_universe as cu  # noqa: E402

PIT = Path(__file__).resolve().parents[1] / "data" / "pit"


def main():
    ever = json.loads((PIT / "ever_eligible_2021.json").read_text())
    products = sorted(set(ever) | {"BTC-USD"})
    try:
        status = cu.coinbase_status()
    except Exception as e:  # network optional; status is only a label here
        print(f"status unavailable: {e}")
        status = {}
    q = cb.audit_all(products, status=status)
    q.to_csv(PIT / "crypto_quality.csv")

    btc = cb.load("BTC-USD")
    btc_grid = pd.date_range(btc.index.min(), btc.index.max(), freq="h")
    btc_missing = btc_grid.difference(btc.index)
    have = q[q.bars > 0]
    # Stopped trading: not "online" now, or no bar in the last 48 h of the BTC reference.
    stale = pd.to_datetime(have.last_bar, utc=True) < btc.index.max() - pd.Timedelta(hours=48)
    delisted = have[stale | (have.status_now.fillna("absent") != "online")]
    summary = {
        "products": len(products), "products_with_bars": int(len(have)),
        "total_bars": int(have.bars.sum()),
        "btc_first": str(btc.index.min()), "btc_last": str(btc.index.max()),
        "venue_outage_hours_btc_missing": int(len(btc_missing)),
        "venue_outage_hours_list": [str(t) for t in btc_missing[:200]],
        "missing_hours_total": int(have.missing_hours.sum()),
        "missing_outage_hours_total": int(have.missing_outage_hours.sum()),
        "missing_no_trade_hours_total": int(have.missing_no_trade_hours.sum()),
        "duplicates_total": int(have.duplicates_in_file.sum()),
        "invalid_ohlc_total": int(have.invalid_ohlc.sum()),
        "zero_volume_bars_total": int(have.zero_volume_bars.sum()),
        "tiny_dollar_volume_bars_total": int(have.tiny_dollar_volume_bars.sum()),
        "extreme_abs_logret_bars_total": int(have.extreme_abs_logret_bars.sum()),
        "robust_z_outliers_total": int(have.robust_z_outliers.sum()),
        "delisted": {p: {"last_bar": str(r.last_bar), "status_now": r.status_now if isinstance(r.status_now, str) else "absent"}
                     for p, r in delisted.iterrows()},
        "rebrands": [{k: str(v) for k, v in cb.rebrand_overlap(o, n).items()} for o, n in cb.KNOWN_REBRANDS.items()],
    }
    (PIT / "crypto_audit_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "venue_outage_hours_list"}, indent=2))


if __name__ == "__main__":
    main()
