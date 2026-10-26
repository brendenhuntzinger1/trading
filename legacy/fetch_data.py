"""Download historical candles from Coinbase's public API into CSVs."""
import sys, time, json, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd

DATA = Path(__file__).parent / "data"
API = "https://api.exchange.coinbase.com/products/{p}/candles?granularity={g}&start={s}&end={e}"

def fetch(product, gran, start, end):
    rows, step = [], timedelta(seconds=gran * 300)
    t = start
    while t < end:
        e = min(t + step, end)
        url = API.format(p=product, g=gran, s=t.isoformat(), e=e.isoformat())
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "backtest"})
                rows += json.load(urllib.request.urlopen(req, timeout=30))
                break
            except Exception as ex:
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"failed {url}")
        t = e
        time.sleep(0.12)
    df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"])
    df = df.drop_duplicates("ts").sort_values("ts")
    df["time"] = pd.to_datetime(df.ts, unit="s", utc=True)
    return df.set_index("time")[["open", "high", "low", "close", "volume"]]

if __name__ == "__main__":
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    jobs = [(p, 86400, datetime(2017, 1, 1, tzinfo=timezone.utc)) for p in ["BTC-USD", "ETH-USD", "SOL-USD"]]
    jobs += [(p, 3600, datetime(2020, 1, 1, tzinfo=timezone.utc)) for p in ["BTC-USD", "ETH-USD", "SOL-USD"]]
    for p, g, s in jobs:
        df = fetch(p, g, s, end)
        name = f"{p}_{'1d' if g == 86400 else '1h'}.csv"
        df.to_csv(DATA / name)
        print(name, len(df), df.index[0], df.index[-1], flush=True)
