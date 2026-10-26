"""Phase-2 market data layer: one cached, resumable daily panel for the whole US-listed universe, plus intraday
bars for chosen symbols. Alpaca market data v2, feed=sip (consolidated), read-only paper key.

Universe (point-in-time as far as free data allows, ORB Amendment 4):
    asset master (exchange-listed: NYSE, NASDAQ, AMEX, ARCA, BATS; any status) + `_DELISTED` names stripped
    + every ticker the corporate-actions feed shows leaving through a merger, name change, worthless removal or
    redemption (2020 onwards; the feed has nothing earlier, so 2016-2019 remain survivorship-affected).
Bars for a ticker are served for the dates it traded under that symbol, so the panel holds delisted names on
the days they existed.

Daily bars are cached per (adjustment, calendar year, chunk of 100 symbols): adding a newer year later reuses
every earlier request. Adjustments: `all` (splits and dividends; for returns) and `raw` (as traded; for price,
dollar-volume and tick-size filters).
"""
from __future__ import annotations

import gzip
import json
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from tradelab.pit.alpaca_sip import AlpacaData, is_ticker, require_old_enough

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "stocks" / "p2cache"
PANELS = ROOT / "data" / "stocks" / "p2panels"
EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
FIELDS = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap", "n": "trades"}


class Cache:
    def __init__(self, root: Path = CACHE):
        self.root = root

    def _p(self, kind: str, key: str) -> Path:
        return self.root / kind / f"{key}.json.gz"

    def get(self, kind: str, key: str):
        p = self._p(kind, key)
        return json.loads(gzip.decompress(p.read_bytes())) if p.exists() else None

    def put(self, kind: str, key: str, value) -> None:
        p = self._p(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(gzip.compress(json.dumps(value).encode()))
        tmp.replace(p)


class Phase2Data:
    def __init__(self, client: AlpacaData | None, cache: Path = CACHE, log=print):
        self.c, self.cache, self.log = client, Cache(cache), log

    # ------------------------------------------------------------ universe ----
    def asset_master(self) -> list[dict]:
        got = self.cache.get("assets", "us_equity_full")
        if got is None:
            st, rows = self.c.assets()
            if st != 200:
                raise RuntimeError(f"asset master failed: HTTP {st}")
            keep = ("symbol", "name", "status", "exchange", "tradable", "shortable", "easy_to_borrow",
                    "fractionable", "attributes")
            got = [{k: a.get(k) for k in keep} for a in rows]
            self.cache.put("assets", "us_equity_full", got)
        return got

    def corporate_action_tickers(self, first_year: int = 2020, last_year: int = 2026) -> set[str]:
        key = f"corporate_action_tickers_{first_year}_{last_year}"
        got = self.cache.get("assets", key)
        if got is None:
            types = ["cash_merger", "stock_merger", "stock_and_cash_merger", "name_change", "worthless_removal",
                     "redemption"]
            found: set[str] = set()
            for year in range(first_year, last_year + 1):
                st, out = self.c.corporate_actions(types, f"{year}-01-01", f"{year}-12-31")
                if st != 200:
                    raise RuntimeError(f"corporate actions failed for {year}: HTTP {st}")
                for rows in out.values():
                    for r in rows:
                        for k in ("acquiree_symbol", "old_symbol", "new_symbol", "symbol"):
                            if is_ticker(str(r.get(k, ""))):
                                found.add(r[k])
            got = sorted(found)
            self.cache.put("assets", key, got)
        return set(got)

    def universe(self) -> list[str]:
        master = {a["symbol"] for a in self.asset_master() if a.get("exchange") in EXCHANGES}
        delisted = {x.removesuffix("_DELISTED") for x in master if x.endswith("_DELISTED")}
        return sorted(x for x in master | delisted | self.corporate_action_tickers() if is_ticker(x))

    # --------------------------------------------------------------- daily ----
    def daily_year(self, symbols: list[str], year: int, adjustment: str, last_day: str) -> None:
        """Download (into the cache only) all daily bars of `year` (through `last_day` for the current year)."""
        for key, chunk, start, end_day in self._daily_keys(symbols, year, adjustment, last_day):
            if self.cache._p("daily", key).exists():
                continue
            end = pd.Timestamp(end_day, tz="UTC") + pd.Timedelta(days=1)
            require_old_enough(end.to_pydatetime())
            st, got = self.c.bars_multi(chunk, start, end.strftime("%Y-%m-%dT%H:%M:%SZ"), timeframe="1Day",
                                        adjustment=adjustment)
            if st != 200:
                raise RuntimeError(f"daily bars failed {year} {chunk[0]}: HTTP {st}")
            self.cache.put("daily", key, got)

    @staticmethod
    def _daily_keys(symbols, year, adjustment, last_day):
        start = f"{year}-01-01"
        end_day = min(f"{year}-12-31", last_day)
        for i in range(0, len(symbols), 100):
            chunk = symbols[i:i + 100]
            yield f"{adjustment}_{start}_{end_day}_{chunk[0]}_{len(chunk)}", chunk, start, end_day

    def build_panel(self, first_year: int, last_day: str, adjustment: str,
                    fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")) -> dict[str, pd.DataFrame]:
        """Wide float32 frames (date x symbol) per field, assembled year by year from the cache (download first
        with daily_year). Saved to data/stocks/p2panels/daily_<adj>_<first>_<last>.pkl."""
        p = PANELS / f"daily_{adjustment}_{first_year}_{last_day}.pkl"
        if p.exists():
            return pickle.loads(p.read_bytes())
        syms = self.universe()
        inv = {v: k for k, v in FIELDS.items()}
        parts: dict[str, list[pd.DataFrame]] = {f: [] for f in fields}
        for year in range(first_year, int(last_day[:4]) + 1):
            self.daily_year(syms, year, adjustment, last_day)
            cols: dict[str, list] = {"date": [], "symbol": [], **{f: [] for f in fields}}
            for key, *_ in self._daily_keys(syms, year, adjustment, last_day):
                for s, rows in (self.cache.get("daily", key) or {}).items():
                    for r in rows:
                        cols["date"].append(r["t"][:10]); cols["symbol"].append(s)
                        for f in fields:
                            cols[f].append(r.get(inv[f]))
            df = pd.DataFrame({k: (np.asarray(v, dtype="float32") if k in fields else v) for k, v in cols.items()})
            df["date"] = pd.to_datetime(df["date"])
            for f in fields:
                parts[f].append(df.pivot_table(index="date", columns="symbol", values=f, aggfunc="last").astype("float32"))
            self.log(f"panel {adjustment} {year}: {df.symbol.nunique()} symbols, {len(df)} bars")
            del df, cols
        panel = {f: pd.concat(v, axis=0).sort_index() for f, v in parts.items()}
        PANELS.mkdir(parents=True, exist_ok=True)
        p.write_bytes(pickle.dumps(panel))
        return panel

    # ------------------------------------------------------------ intraday ----
    def intraday_year(self, symbols: list[str], year: int, timeframe: str, last_day: str,
                      adjustment: str = "all") -> dict[str, list]:
        """Intraday bars (e.g. 1Min, 5Min, 30Min) for a few symbols over one calendar year, cached per month."""
        out: dict[str, list] = {}
        for m in range(1, 13):
            start = pd.Timestamp(year=year, month=m, day=1)
            if start.strftime("%Y-%m-%d") > last_day:
                break
            stop = min(start + pd.offsets.MonthEnd(0), pd.Timestamp(last_day))
            for i in range(0, len(symbols), 20):
                chunk = symbols[i:i + 20]
                key = f"{timeframe}_{adjustment}_{start:%Y-%m}_{stop:%d}_{'-'.join(chunk)[:80]}_{len(chunk)}"
                got = self.cache.get("intraday", key)
                if got is None:
                    end = (stop + pd.Timedelta(days=1)).tz_localize("UTC")
                    require_old_enough(end.to_pydatetime())
                    st, got = self.c.bars_multi(chunk, start.strftime("%Y-%m-%d"),
                                                end.strftime("%Y-%m-%dT%H:%M:%SZ"), timeframe=timeframe,
                                                adjustment=adjustment)
                    if st != 200:
                        raise RuntimeError(f"intraday bars failed {start:%Y-%m} {chunk[0]}: HTTP {st}")
                    self.cache.put("intraday", key, got)
                for s, rows in got.items():
                    out.setdefault(s, []).extend(rows)
        return out
