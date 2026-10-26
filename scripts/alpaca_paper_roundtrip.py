"""Verify the paper order path end to end with one tiny round trip (default: $10 of BTC/USD on Alpaca PAPER).

Measures: decision -> submit -> acknowledgement -> fill latency, fill price against the quote mid at decision,
position quantity after fees, idempotency (a resend of the same client id must not create a second order).
Writes research/execution/alpaca_paper_roundtrip_<UTC>.json. Simulated money only; fills are Alpaca's simulation.

    TRADELAB_PAPER_BROKER_ENABLED=1 .venv/bin/python scripts/alpaca_paper_roundtrip.py [--symbol BTC/USD] [--usd 10]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradelab.broker.alpaca_paper import AlpacaPaperBroker  # noqa: E402


def mid(q: dict) -> float | None:
    bp, ap = float(q.get("bp", 0) or 0), float(q.get("ap", 0) or 0)
    return (bp + ap) / 2 if bp > 0 and ap > 0 else None


def leg(b: AlpacaPaperBroker, cid: str, symbol: str, side: str, **size) -> dict:
    q = b.latest_quote(symbol)
    t_decide = time.time()
    o = b.submit(cid, symbol, side, **size)
    t_ack = time.time()
    f = b.wait_terminal(cid, timeout_s=60)
    t_done = time.time()
    m = mid(q)
    px = float(f.get("filled_avg_price") or 0) or None
    sgn = 1 if side == "buy" else -1
    return {"client_order_id": cid, "side": side, "status": f.get("status"), "quote": {k: q.get(k) for k in ("bp", "ap", "t")},
            "quoted_half_spread_bps": ((float(q["ap"]) - float(q["bp"])) / 2 / m * 1e4) if m else None,
            "filled_qty": f.get("filled_qty"), "filled_avg_price": px,
            "slippage_vs_mid_bps": (sgn * (px - m) / m * 1e4) if (px and m) else None,
            "submit_to_ack_ms": (t_ack - t_decide) * 1000, "decide_to_terminal_ms": (t_done - t_decide) * 1000,
            "submitted_at": f.get("submitted_at"), "filled_at": f.get("filled_at"), "broker_order_id": o.get("id")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTC/USD")
    ap.add_argument("--usd", type=float, default=10.0)
    a = ap.parse_args()
    b = AlpacaPaperBroker.from_env()
    acct = b.account()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {"what": "Alpaca PAPER round trip (simulated money, Alpaca-simulated fills)", "symbol": a.symbol, "usd": a.usd,
           "account_status": acct.get("status"), "at": stamp}
    buy = leg(b, f"rt-{stamp}-buy", a.symbol, "buy", notional=a.usd)
    dup = b.submit(f"rt-{stamp}-buy", a.symbol, "buy", notional=a.usd)
    out["buy"], out["duplicate_resend_returned_existing"] = buy, bool(dup.get("_duplicate")) and dup.get("id") == buy["broker_order_id"]
    held = float(b.positions().get(a.symbol.replace("/", ""), {}).get("qty", 0))
    out["position_qty_after_buy"] = held
    out["fee_or_rounding_qty"] = (float(buy["filled_qty"] or 0) - held) if buy["filled_qty"] else None
    if held > 0:
        out["sell"] = leg(b, f"rt-{stamp}-sell", a.symbol, "sell", qty=held)
    out["position_qty_after_sell"] = float(b.positions().get(a.symbol.replace("/", ""), {}).get("qty", 0))
    out["requests"] = [{k: r[k] for k in ("method", "path", "status")} | {"ms": round((r["received"] - r["sent"]) * 1000, 1)}
                       for r in b.log]
    p = ROOT / "research" / "execution" / f"alpaca_paper_roundtrip_{stamp}.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "requests"}, indent=1))
    print(p)


if __name__ == "__main__":
    main()
