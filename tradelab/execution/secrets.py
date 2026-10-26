"""Credential handling: separate paper/live namespaces, least privilege,
and redaction of anything secret-looking from logs."""
from __future__ import annotations

import logging
import os
import re
import traceback
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class Credentials:
    mode: str
    key_name: str
    private_key: str

    def __repr__(self):                      # never print secrets, even by accident
        return f"Credentials(mode={self.mode!r}, key_name=<redacted>, private_key=<redacted>)"


def load(mode: str) -> Credentials | None:
    """Paper mode needs no credentials and refuses to load live ones.
    Live credentials come from the environment (populated by the host's secret
    manager or a 0600 EnvironmentFile), never from the repository."""
    if mode == "paper":
        if any(k.startswith("TRADELAB_LIVE_") and k.endswith(("KEY", "SECRET")) for k in os.environ):
            raise RuntimeError("live credentials present in a paper-mode process; refusing to start")
        return None
    if mode != "live":
        raise ValueError(mode)
    name, key = os.environ.get("TRADELAB_LIVE_KEY_NAME"), os.environ.get("TRADELAB_LIVE_PRIVATE_KEY")
    if not name or not key:
        raise RuntimeError("live credentials missing")
    return Credentials("live", name, key)


def assert_least_privilege(perms: dict) -> None:
    """perms: the venue's key-permission response (Coinbase Advanced:
    GET /api/v3/brokerage/key_permissions -> can_view, can_trade, can_transfer)."""
    if perms.get("can_transfer"):
        raise RuntimeError("API key can transfer/withdraw funds; create a view+trade key only")
    if not perms.get("can_trade") or not perms.get("can_view"):
        raise RuntimeError("API key needs view and trade permissions")


_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)(api[_-]?key|secret|private[_-]?key|passphrase|authorization|bearer)([\"'=:\s]+(?:bearer\s+)?)([^\s\"',}]+)"),
    re.compile(r"organizations/[0-9a-f-]{36}/apiKeys/[0-9a-f-]{36}"),
]


def redact(text: str) -> str:
    text = _PATTERNS[0].sub("<redacted private key>", text)
    text = _PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)
    return _PATTERNS[2].sub("<redacted key name>", text)


class RedactingFilter(logging.Filter):
    """Redacts the message and any traceback (formatted here, then dropped from the record)."""
    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + "".join(traceback.format_exception(*record.exc_info))
            record.exc_info, record.exc_text = None, None
        record.msg, record.args = redact(text), ()
        return True
