"""Data sources for the ORB study. The study only talks to the `DataSource` interface; tests use synthetic
fixtures, real runs use `AlpacaSource` (historical SIP via a PAPER key; read-only endpoints only).

Everything returned for a day is knowable at that day's 09:35 ET decision except the minute bars and quotes the
simulator walks forward through, which it reads strictly in time order.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from tradelab.pit.alpaca_sip import AlpacaData, is_ticker, require_old_enough
from tradelab.stocks import orb
from tradelab.stocks.spreads import HalfSpread, half_spread_at
from tradelab.stocks.timeutil import bars_frame, quotes_frame, regular_minutes, session_bounds, session_days

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "stocks" / "cache"
EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}


class DataSource(Protocol):
    quotes_available: bool

    def days(self, start: str, end: str) -> list[str]: ...

    def candidates(self, day: str) -> pd.DataFrame:
        """symbol, open, adv, atr, rv, direction, corporate_action, has_open_bar (all knowable at 09:35)."""

    def minute_bars(self, symbols: list[str], day: str) -> dict[str, pd.DataFrame]:
        """Regular-session raw 1-minute SIP bars, index = UTC bar start."""

    def half_spread(self, symbol: str, minute_start: pd.Timestamp) -> HalfSpread | None:
        """Quote in force at the end of that minute; None when quotes are not available at all."""


class _Cache:
    def __init__(self, root: Path):
        self.root = root

    def get(self, kind: str, key: str):
        p = self.root / kind / f"{key}.json.gz"
        return json.loads(gzip.decompress(p.read_bytes())) if p.exists() else None

    def put(self, kind: str, key: str, value) -> None:
        p = self.root / kind / f"{key}.json.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gzip.compress(json.dumps(value).encode()))


class AlpacaSource:
    """Historical SIP data through a paper key, cached under data/stocks/cache (gitignored).

    Universe: every us_equity asset on NYSE / Nasdaq / NYSE American / Arca / Cboe BZX in Alpaca's asset master,
    INCLUDING inactive ones (status filter omitted). Residual survivorship (securities missing from the master)
    is measured by data gate B7.3, not assumed away.
    Daily filters: raw and split-adjusted daily bars, combined point-in-time by `orb.pit_adjust`.
    RV: the 09:30 5-minute bar volume per day, fetched for every symbol passing a loose static pre-filter that
    day (traded, raw close > $2, volume > 300k shares); a symbol missing on a history day gets RV = NaN (excluded).
    """

    def __init__(self, client: AlpacaData, start: str, end: str, cache: Path = CACHE, quotes: bool = True):
        self.c, self.start, self.end = client, start, end
        self.cache = _Cache(cache)
        self.quotes_available = quotes
        self._daily_raw: dict[str, pd.DataFrame] | None = None
        self._daily_adj: dict[str, pd.DataFrame] | None = None
        self._or_cache: dict[str, dict] = {}
        self._day_syms: dict[str, set] = {}     # symbols whose minute bars were requested, per day (quote batching)

    # ----------------------------------------------------------- universe ----
    def symbols(self) -> list[str]:
        got = self.cache.get("assets", "us_equity_all")
        if got is None:
            st, rows = self.c.assets()
            if st != 200:
                raise RuntimeError(f"asset master request failed: HTTP {st}")
            got = [{"symbol": a["symbol"], "status": a.get("status"), "exchange": a.get("exchange")} for a in rows]
            self.cache.put("assets", "us_equity_all", got)
        master = {a["symbol"] for a in got if a.get("exchange") in EXCHANGES}
        # The asset master omits most delisted names (ORB Amendment 4: it held only 12-37% of the tickers that
        # disappeared through mergers each year). Add every ticker the corporate-actions feed shows leaving.
        # Bars for such tickers exist and are served for the dates they traded under that symbol.
        delisted = {x.removesuffix("_DELISTED") for x in master if x.endswith("_DELISTED")}
        return sorted(x for x in master | delisted | self.corporate_action_tickers() if is_ticker(x))

    def corporate_action_tickers(self) -> set[str]:
        got = self.cache.get("assets", f"corporate_action_tickers_{self.start}_{self.end}")
        if got is None:
            types = ["cash_merger", "stock_merger", "stock_and_cash_merger", "name_change", "worthless_removal",
                     "redemption"]
            found: set[str] = set()
            for year in range(int(self.start[:4]) - 1, int(self.end[:4]) + 2):
                st, out = self.c.corporate_actions(types, f"{year}-01-01", f"{year}-12-31")
                if st != 200:
                    raise RuntimeError(f"corporate actions failed for {year}: HTTP {st}")
                for rows in out.values():
                    for r in rows:
                        for k in ("acquiree_symbol", "old_symbol", "new_symbol", "symbol"):
                            if is_ticker(str(r.get(k, ""))):
                                found.add(r[k])
            got = sorted(found)
            self.cache.put("assets", f"corporate_action_tickers_{self.start}_{self.end}", got)
        return set(got)

    def days(self, start: str, end: str) -> list[str]:
        return session_days(start, end)

    # -------------------------------------------------------------- daily ----
    def _load_daily(self) -> None:
        if self._daily_raw is not None:
            return
        syms = self.symbols()
        lo = (pd.Timestamp(self.start) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
        raw, adj = {}, {}
        for i in range(0, len(syms), 100):
            chunk = syms[i:i + 100]
            for kind, store in (("raw", raw), ("split", adj)):
                key = f"{kind}_{lo}_{self.end}_{chunk[0]}_{len(chunk)}"
                got = self.cache.get("daily", key)
                if got is None:
                    end = pd.Timestamp(self.end, tz="UTC") + pd.Timedelta(days=1)
                    require_old_enough(end.to_pydatetime())
                    st, got = self.c.bars_multi(chunk, lo, end.strftime("%Y-%m-%dT%H:%M:%SZ"), timeframe="1Day",
                                                adjustment=kind)
                    if st != 200:
                        raise RuntimeError(f"daily bars failed: HTTP {st}")
                    self.cache.put("daily", key, got)
                for s, rows in got.items():
                    f = bars_frame(rows)
                    f.index = f.index.tz_convert("America/New_York").normalize().tz_localize(None)
                    store[s] = f
        self._daily_raw, self._daily_adj = raw, adj

    def _or_bars(self, day: str) -> dict:
        """{symbol: 09:30 5-minute bar} for the loosely pre-filtered symbols of `day`."""
        if day in self._or_cache:
            return self._or_cache[day]
        got = self.cache.get("or5", day)
        if got is None:
            d = pd.Timestamp(day)
            syms = [s for s, f in self._daily_raw.items()
                    if d in f.index and f.at[d, "close"] > 2 and f.at[d, "volume"] > 300_000]
            o, _ = session_bounds(day)
            require_old_enough((o + pd.Timedelta(minutes=5)).to_pydatetime())
            got = {}
            for i in range(0, len(syms), 200):
                st, part = self.c.bars_multi(syms[i:i + 200], o.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                             (o + pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                             timeframe="5Min")
                if st != 200:
                    raise RuntimeError(f"5-minute bars failed on {day}: HTTP {st}")
                got.update({s: r[0] for s, r in part.items() if r})
            self.cache.put("or5", day, got)
        self._or_cache[day] = got
        return got

    def candidates(self, day: str) -> pd.DataFrame:
        self._load_daily()
        o, _ = session_bounds(day)
        today = self._or_bars(day)
        hist_days = [d for d in session_days((pd.Timestamp(day) - pd.Timedelta(days=40)).strftime("%Y-%m-%d"), day)
                     if d < day][-14:]
        hist = [self._or_bars(d) for d in hist_days]
        rows, seen = [], set()
        for s, b in sorted(today.items()):
            # One company under two tickers (old and new symbol both map to it) gives identical bars: keep one.
            key = (b.get("o"), b.get("h"), b.get("l"), b.get("c"), b.get("v"))
            if key in seen:
                continue
            seen.add(key)
            raw, adj = self._daily_raw.get(s), self._daily_adj.get(s)
            if raw is None or adj is None:
                continue
            pit = orb.pit_adjust(raw, adj, day)
            hv = pd.Series([h.get(s, {}).get("v", float("nan")) for h in hist], dtype=float)
            d = pd.Timestamp(day)
            fac = raw.close / adj.close.reindex(raw.index)
            prev = fac[fac.index < d]
            ca = bool(d in fac.index and len(prev) and abs(fac.at[d] / prev.iloc[-1] - 1) > 1e-6)
            if b["t"] and pd.Timestamp(b["t"]) != o:
                continue
            rng = orb.OpeningRange(b["o"], b["h"], b["l"], b["c"], b["v"])
            rows.append({"symbol": s, "open": b["o"], "adv": orb.adv(pit, 14), "atr": orb.atr(pit, 14),
                         "rv": orb.relative_volume(b["v"], hv.dropna() if hv.notna().all() else hv.iloc[:0], 14),
                         "direction": rng.direction, "corporate_action": ca, "has_open_bar": True})
        return pd.DataFrame(rows, columns=["symbol", "open", "adv", "atr", "rv", "direction", "corporate_action",
                                           "has_open_bar"])

    # ------------------------------------------------------------- minute ----
    def minute_bars(self, symbols: list[str], day: str) -> dict[str, pd.DataFrame]:
        self._day_syms.setdefault(day, set()).update(symbols)
        o, c = session_bounds(day)
        require_old_enough(c.to_pydatetime())
        out, missing = {}, []
        for s in symbols:
            got = self.cache.get("min1", f"{day}_{s}")
            if got is None:
                missing.append(s)
            else:
                out[s] = regular_minutes(bars_frame(got), day)
        for i in range(0, len(missing), 20):
            chunk = missing[i:i + 20]
            st, part = self.c.bars_multi(chunk, o.strftime("%Y-%m-%dT%H:%M:%SZ"), c.strftime("%Y-%m-%dT%H:%M:%SZ"))
            if st != 200:
                raise RuntimeError(f"minute bars failed on {day}: HTTP {st}")
            for s in chunk:
                rows = part.get(s, [])
                self.cache.put("min1", f"{day}_{s}", rows)
                out[s] = regular_minutes(bars_frame(rows), day)
        return out

    def half_spread(self, symbol: str, minute_start: pd.Timestamp) -> HalfSpread | None:
        if not self.quotes_available:
            return None
        end = minute_start + pd.Timedelta(minutes=1)
        stamp = end.strftime('%Y%m%dT%H%M')
        got = self.cache.get("quotes", f"{symbol}_{stamp}")
        if got is None:
            require_old_enough(end.to_pydatetime())
            # Same rule as one symbol at a time (last quote in the final 2 s, else in the final 60 s), but every
            # symbol of the day still missing a quote for this minute is fetched in the same request: benchmark
            # entries share 09:35 and every exit shares 15:59.
            day = minute_start.tz_convert("America/New_York").strftime("%Y-%m-%d")
            batch = sorted({symbol} | {s for s in self._day_syms.get(day, set())
                                       if self.cache.get("quotes", f"{s}_{stamp}") is None})
            found: dict[str, list] = {}
            for back in (2, 60):              # busy names: the last 2 s suffice; quiet names: up to the staleness limit
                todo = [s for s in batch if s not in found]
                if not todo:
                    break
                for i in range(0, len(todo), 50):
                    st, part = self.c.quotes_multi(todo[i:i + 50], (end - pd.Timedelta(seconds=back)).to_pydatetime(),
                                                   end.to_pydatetime())
                    if st != 200:
                        raise RuntimeError(f"quotes failed at {end}: HTTP {st}")
                    found.update({s: rows[-1:] for s, rows in part.items() if rows})
            for s in batch:
                self.cache.put("quotes", f"{s}_{stamp}", found.get(s, []))
            got = found.get(symbol, [])
        return half_spread_at(quotes_frame(got), minute_start)
