"""Measure each stage of the live paper pipeline, end to end, on real Coinbase data:
  data arrival   exchange event time -> our receive time (WebSocket trades)
  bar ready      bar end -> REST candle available (the runner's actual data path)
  features       setup feature computation for C1/C2 on 70 days of 5-minute bars
  decision       engine.process_bar (risk checks + sizing + signal handling)
  submit / ack   order manager -> paper venue with a fresh REST order book (the paper fill path)
Run: .venv/bin/python research/intraday/latency/measure.py [seconds]"""
import asyncio
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tradelab.data.candles import fetch_coinbase
from tradelab.data.live.feeds import make_feed
from tradelab.data.live.types import Trade
from tradelab.execution.manager import OrderManager
from tradelab.execution.paper import PaperExchange
from tradelab.execution.store import Store
from tradelab.execution.venue import CoinbasePublic
from tradelab.intraday.costs import CRYPTO_TAKER
from tradelab.intraday.engine import Bar, Engine
from tradelab.intraday.limits import IntradayLimits
from tradelab.intraday.replay import Ctx
from tradelab.intraday.sessions import CryptoSessions
from tradelab.intraday.setups import C1CascadeReversal, C2IntradayMomentum


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def summary(xs):
    return {"n": len(xs), "p50_ms": round(pct(xs, 0.5), 1), "p95_ms": round(pct(xs, 0.95), 1), "max_ms": round(max(xs), 1)} if xs else {"n": 0}


async def ws_arrival(seconds):
    lat = []
    def on(rec):
        if isinstance(rec, Trade) and not getattr(rec, "from_snapshot", False):
            lat.append((rec.received_at - rec.event_time).total_seconds() * 1000)
    feed = make_feed(["BTC-USD", "ETH-USD"], "coinbase", on_record=on)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(seconds)
    feed.stop(); task.cancel()
    return lat


def bar_ready(samples=3):
    """How long after a 5-minute bar ends until Coinbase REST returns it."""
    out = []
    for _ in range(samples):
        now = datetime.now(timezone.utc)
        end = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 5)
        while True:
            df = fetch_coinbase("BTC-USD", "5m", end - timedelta(minutes=15), datetime.now(timezone.utc) + timedelta(minutes=1))
            if len(df) and (df.index[-1] + pd.Timedelta(minutes=5)) >= pd.Timestamp(end):
                out.append((datetime.now(timezone.utc) - end).total_seconds() * 1000)
                break
            time.sleep(1)
        time.sleep(2)
    return out


def compute_stages():
    now = datetime.now(timezone.utc)
    frames = {s: fetch_coinbase(s, "5m", now - timedelta(days=70), now)[["open", "high", "low", "close", "volume"]] for s in ("BTC-USD", "ETH-USD", "SOL-USD")}
    feat = []
    for _ in range(5):
        t0 = time.perf_counter(); C1CascadeReversal(frames); C2IntradayMomentum(frames); feat.append((time.perf_counter() - t0) * 1000)
    eng = Engine(IntradayLimits(market="crypto", max_weight=0.25), [C1CascadeReversal(frames), C2IntradayMomentum(frames)],
                 {"C1": CRYPTO_TAKER, "C2": CRYPTO_TAKER}, CryptoSessions(), 1000.0)
    dec = []
    idx = frames["BTC-USD"].index[-300:]
    for t in idx:
        bars = {s: Bar(*f.loc[t].to_numpy()) for s, f in frames.items() if t in f.index}
        t0 = time.perf_counter(); eng.process_bar(t.to_pydatetime(), (t + pd.Timedelta(minutes=5)).to_pydatetime(), bars, Ctx(eng.sessions))
        dec.append((time.perf_counter() - t0) * 1000)
    return feat, dec


def order_path(n=5):
    pub = CoinbasePublic()
    rules = {}
    ex = PaperExchange(lambda a: pub.book(a), lambda a: rules.setdefault(a, pub.rules(a)), cash=1000)
    om = OrderManager(Store(Path(tempfile.mkdtemp()) / "lat.db", "paper"), ex, "latency", min_request_interval_s=0)
    pub.rules("BTC-USD")
    sub, ack = [], []
    for i in range(n):
        decided = datetime.now(timezone.utc)
        o = om.submit(f"lat-{i}-{time.time()}", "BTC-USD", 10.0, 80000.0, decided_at=decided)
        sub.append((o.submitted_at - decided).total_seconds() * 1000)
        ack.append((o.acked_at - o.submitted_at).total_seconds() * 1000)
    return sub, ack


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
    ws = asyncio.run(ws_arrival(secs))
    feat, dec = compute_stages()
    sub, ack = order_path()
    br = bar_ready(2)
    res = {"measured_at": datetime.now(timezone.utc).isoformat(), "host": "cloud container behind an egress proxy (not a trading host)",
           "data_arrival_ws_trades": summary(ws), "bar_ready_after_bar_end_rest": summary(br),
           "feature_calc_C1_C2_70d_3_symbols": summary(feat), "decision_engine_process_bar": summary(dec),
           "decision_to_submit": summary(sub), "submit_to_ack_paper_incl_REST_book_fetch": summary(ack)}
    (Path(__file__).parent / "latency.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
