"""Fetch daily candles for every Coinbase USD product (online AND delisted),
excluding stablecoins / wrapped / pegged tokens, into data/universe/.
Including delisted products limits survivorship bias in cross-asset tests."""
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradelab.data.candles import fetch_coinbase  # noqa: E402

OUT = ROOT / "data" / "universe"
EXCLUDE = {"USDT", "USDC", "DAI", "BUSD", "GUSD", "PAX", "PYUSD", "UST", "MUSD", "EURC", "GYEN", "RAI", "WBTC",
           "CBETH", "USDS", "PAXG", "TUSD", "FDUSD", "EUROC", "LSETH", "MSOL", "WAXL", "WCFG", "WAMPL"}


def main():
    req = urllib.request.Request("https://api.exchange.coinbase.com/products", headers={"User-Agent": "tradelab"})
    prods = json.load(urllib.request.urlopen(req, timeout=30))
    ids = sorted(p["id"] for p in prods if p["quote_currency"] == "USD" and p["base_currency"] not in EXCLUDE)
    status = {p["id"]: p["status"] for p in prods}
    (OUT / "_products.json").write_text(json.dumps({i: status[i] for i in ids}, indent=0))

    def one(pid):
        path = OUT / f"{pid}_1d.csv"
        if path.exists():
            return pid, "cached"
        try:
            df = fetch_coinbase(pid, "1d", datetime(2017, 1, 1, tzinfo=timezone.utc))
        except Exception as e:  # keep going; record failures
            return pid, f"error {e}"
        if len(df):
            df.to_csv(path)
        return pid, f"{len(df)} bars from {df.index[0].date() if len(df) else '-'}"

    with ThreadPoolExecutor(max_workers=3) as ex:
        for pid, msg in ex.map(one, ids):
            print(pid, msg, flush=True)


if __name__ == "__main__":
    main()
