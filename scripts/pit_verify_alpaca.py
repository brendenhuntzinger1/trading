"""Data gates B7.1-B7.5 for the ORB study (ORB_PREREGISTRATION.md, Amendment 1). Run ONLY after the PAPER key is
configured as a secret (docs/CREDENTIALS_SETUP.md). Never prints the key.

    .venv/bin/python scripts/pit_verify_alpaca.py            # full gates -> data/stocks/verify_<date>.json + audit doc
    .venv/bin/python scripts/pit_verify_alpaca.py --quick    # paper-key and SIP entitlement check only

Exit codes: 0 all gates pass, 1 a gate failed, 2 no credentials (nothing was run, nothing written)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tradelab.pit.alpaca_sip import AlpacaData, http_get, verify_entitlement, verify_paper_key  # noqa: E402

OUT_DIR = ROOT / "data" / "stocks"
AUDIT_DOC = ROOT / "docs" / "ALPACA_DATA_AUDIT.md"


def main(argv=None, transport=http_get, env=None, out_dir: Path = OUT_DIR, audit_doc: Path = AUDIT_DOC) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    env = os.environ if env is None else env
    if not env.get("TRADELAB_PAPER_APCA_API_KEY_ID") or not env.get("TRADELAB_PAPER_APCA_API_SECRET_KEY"):
        print("No Alpaca paper credentials in the environment (TRADELAB_PAPER_APCA_API_KEY_ID / _SECRET_KEY). "
              "Nothing was run. Set them as secrets per docs/CREDENTIALS_SETUP.md; never paste them into chat.")
        return 2
    saved = dict(os.environ)
    try:
        os.environ.update({k: v for k, v in env.items() if k.startswith("TRADELAB_")})
        client = AlpacaData.from_env(transport)
    finally:
        os.environ.clear(); os.environ.update(saved)
    if a.quick:
        from tradelab.stocks.verify import recent_session
        from tradelab.stocks.timeutil import session_bounds
        o, c = session_bounds(recent_session())
        print(json.dumps({"paper_key": verify_paper_key(client),
                          "entitlement": verify_entitlement(client, o.to_pydatetime(), c.to_pydatetime())}, indent=1, default=str))
        return 0
    from tradelab.stocks.verify import markdown, run_all
    report = run_all(client)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"verify_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps(report, indent=1, default=str))
    with audit_doc.open("a") as fh:
        fh.write(markdown(report))
    ok = all(g.get("pass") for g in report["gates"].values())
    print(f"report: {path}\n" + markdown(report))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
