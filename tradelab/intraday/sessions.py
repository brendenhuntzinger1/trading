"""Trading sessions: NYSE regular hours (holidays and half-days from exchange_calendars)
and crypto's 24/7 UTC day."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pandas as pd


class StockSessions:
    market = "stocks"

    def __init__(self):
        import exchange_calendars as xc
        self.cal = xc.get_calendar("XNYS", start="1999-01-01")      # default covers only the last 20 years

    @lru_cache(maxsize=4096)
    def bounds(self, day: str) -> tuple[datetime, datetime] | None:
        """(open, close) in UTC for a session date 'YYYY-MM-DD', or None if closed."""
        if not self.cal.is_session(day):
            return None
        o, c = self.cal.session_open(day), self.cal.session_close(day)
        return o.to_pydatetime(), c.to_pydatetime()

    def session_of(self, t: datetime) -> tuple[datetime, datetime] | None:
        day = pd.Timestamp(t).tz_convert("America/New_York").strftime("%Y-%m-%d")
        b = self.bounds(day)
        return b if b and b[0] <= t <= b[1] else None

    def day_key(self, t: datetime) -> str:
        return pd.Timestamp(t).tz_convert("America/New_York").strftime("%Y-%m-%d")


class CryptoSessions:
    market = "crypto"

    def session_of(self, t: datetime):
        d = t.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return d, d + timedelta(days=1)

    def day_key(self, t: datetime) -> str:
        return t.astimezone(timezone.utc).strftime("%Y-%m-%d")
