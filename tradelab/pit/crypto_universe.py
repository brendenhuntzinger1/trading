"""Point-in-time eligible Coinbase USD spot universe.

A product is eligible for decisions taken during UTC day d when, using only daily
candles that ended before d starts:
  * it is not a stablecoin, wrapped, staked or pegged asset (explicit list below);
  * it traded on day d-1 (proxy for "listed": a candle exists; Coinbase emits no
    candle for a day without trades, and day d's own candle is not complete at d);
  * it has >= 60 daily candles before d;
  * the median daily dollar volume (close x volume) over the 30 calendar days
    before d is >= $10M, with >= 20 observed days in that window.

Product *status* (online/delisted) is only known today, so it is NOT used for
history (that would leak the future delisting). It is applied to the live date only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DAILY_DIR = ROOT / "data" / "universe"
OUT = ROOT / "data" / "pit" / "crypto_universe.csv.gz"

# Not tradable risk exposures in their own right: stablecoins, fiat/gold-pegged, wrapped and liquid-staking tokens.
EXCLUDED_BASES = frozenset({
    "USDT", "USDC", "DAI", "BUSD", "GUSD", "PAX", "PYUSD", "UST", "MUSD", "EURC", "EUROC", "GYEN", "RAI", "USDS",
    "USD1", "USDP", "TUSD", "FDUSD", "USDE", "SUSDE", "PAXG", "XAUT",
    "WBTC", "CBBTC", "LBTC", "TBTC", "WETH", "STETH", "WSTETH", "RETH", "CBETH", "LSETH", "MSOL", "JITOSOL",
    "WAXL", "WCFG", "WAMPL",
})


@dataclass(frozen=True)
class Rules:
    min_history_days: int = 60
    dv_window_days: int = 30
    min_dv_obs: int = 20
    min_median_dollar_volume: float = 10e6


def excluded(product: str) -> bool:
    return product.split("-")[0] in EXCLUDED_BASES


def load_daily(product: str, daily_dir: Path = DAILY_DIR) -> pd.DataFrame:
    df = pd.read_csv(daily_dir / f"{product}_1d.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["dollar_volume"] = df.close * df.volume
    return df


def product_eligibility(product: str, daily: pd.DataFrame, dates: pd.DatetimeIndex, rules: Rules = Rules()) -> pd.DataFrame:
    """Eligibility of one product on each date, using only candles before that date."""
    if excluded(product):
        return pd.DataFrame({"date": dates, "product": product, "eligible": False, "reason": "excluded_asset",
                             "median_dv_30d": np.nan, "history_days": 0})
    full = pd.date_range(min(daily.index.min(), dates.min()), max(daily.index.max(), dates.max()), freq="D", tz="UTC")
    has = pd.Series(1.0, index=daily.index).reindex(full, fill_value=0.0)
    dv = daily.dollar_volume.reindex(full)
    # values at date d summarise days strictly before d -> shift(1)
    history = has.cumsum().shift(1).fillna(0)
    traded_prev = has.shift(1).fillna(0) > 0
    med = dv.rolling(rules.dv_window_days, min_periods=rules.min_dv_obs).median().shift(1)
    h, tp, m = history.reindex(dates), traded_prev.reindex(dates), med.reindex(dates)
    reason = np.select(
        [~tp.to_numpy(bool), h.to_numpy() < rules.min_history_days, ~np.isfinite(m.to_numpy()),
         m.to_numpy() < rules.min_median_dollar_volume],
        ["not_trading_prev_day", "history_lt_60d", "insufficient_volume_obs", "dollar_volume_lt_10m"], default="eligible")
    return pd.DataFrame({"date": dates, "product": product, "eligible": reason == "eligible", "reason": reason,
                         "median_dv_30d": m.to_numpy(), "history_days": h.to_numpy().astype(int)})


def build(start: str = "2018-01-01", end: str | None = None, daily_dir: Path = DAILY_DIR,
          rules: Rules = Rules()) -> pd.DataFrame:
    files = sorted(p for p in daily_dir.glob("*_1d.csv"))
    dailies = {f.name.replace("_1d.csv", ""): load_daily(f.name.replace("_1d.csv", ""), daily_dir) for f in files}
    last = max(d.index.max() for d in dailies.values())
    utc = lambda x: pd.Timestamp(x).tz_localize("UTC") if pd.Timestamp(x).tzinfo is None else pd.Timestamp(x).tz_convert("UTC")
    dates = pd.date_range(utc(start), utc(end) if end else last + pd.Timedelta(days=1), freq="D")
    rows = []
    for p, d in dailies.items():
        e = product_eligibility(p, d, dates, rules)
        # keep rows only from 60 days before first candle to 1 day after last, to keep the file small
        lo, hi = d.index.min(), d.index.max() + pd.Timedelta(days=1)
        rows.append(e[(e.date >= lo) & (e.date <= hi)])
    return pd.concat(rows, ignore_index=True).sort_values(["date", "product"]).reset_index(drop=True)


def save(u: pd.DataFrame, path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    u.to_csv(path, index=False)
    return path


_CACHE: dict = {}


def load(path: Path = OUT) -> pd.DataFrame:
    if path not in _CACHE:
        u = pd.read_csv(path, parse_dates=["date"])
        u["date"] = pd.to_datetime(u.date, utc=True)
        _CACHE[path] = u
    return _CACHE[path]


def eligible_at(t, path: Path = OUT, live_status: dict | None = None) -> list[str]:
    """Products eligible for a decision taken at time t (UTC). Eligibility is fixed for
    the whole UTC day and uses only candles that ended before that day began.
    live_status (product -> 'online'/'delisted'), if given, additionally drops products
    that are not tradable now - only meaningful when t is the present."""
    u = load(path)
    d = pd.Timestamp(t).tz_convert("UTC").normalize() if pd.Timestamp(t).tzinfo else pd.Timestamp(t, tz="UTC").normalize()
    ids = u.loc[(u.date == d) & u.eligible, "product"].tolist()
    if live_status is not None:
        ids = [p for p in ids if live_status.get(p) == "online"]
    return sorted(ids)


def coinbase_status(products_json: Path | None = None) -> dict:
    """Current product status from the API (or a saved copy)."""
    if products_json is not None:
        data = json.loads(Path(products_json).read_text())
    else:
        import urllib.request
        req = urllib.request.Request("https://api.exchange.coinbase.com/products", headers={"User-Agent": "tradelab-pit"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    return {p["id"]: ("online" if p["status"] == "online" and not p["trading_disabled"] else p["status"])
            for p in data if p.get("quote_currency") == "USD"}


def summary(u: pd.DataFrame) -> pd.DataFrame:
    """Eligible counts per year and daily membership turnover."""
    e = u[u.eligible]
    per_day = e.groupby("date")["product"].apply(set)
    rows = []
    prev = None
    for d, s in per_day.items():
        if prev is not None:
            rows.append({"date": d, "n": len(s), "added": len(s - prev), "removed": len(prev - s)})
        prev = s
    t = pd.DataFrame(rows)
    t["year"] = t.date.dt.year
    return t.groupby("year").agg(mean_eligible=("n", "mean"), min_eligible=("n", "min"), max_eligible=("n", "max"),
                                 adds=("added", "sum"), removes=("removed", "sum"),
                                 distinct_products=("n", "size")).assign(
        distinct_products=e.assign(year=e.date.dt.year).groupby("year")["product"].nunique())
