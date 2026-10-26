"""Run ONLY after the paper key is set as an environment secret (docs/CREDENTIALS_SETUP.md).
Prints entitlement facts; never prints the key. .venv/bin/python scripts/pit_verify_alpaca.py"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradelab.intraday.sessions import StockSessions  # noqa: E402
from tradelab.pit.alpaca_sip import AlpacaData, verify_entitlement, verify_paper_key  # noqa: E402

c = AlpacaData.from_env()
s = StockSessions()
d = datetime.now(timezone.utc) - timedelta(days=2)
while not s.bounds(s.day_key(d)):
    d -= timedelta(days=1)
o, cl = s.bounds(s.day_key(d))
print(json.dumps({"paper_key": verify_paper_key(c), "entitlement": verify_entitlement(c, o, cl)}, indent=1, default=str))
