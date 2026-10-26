"""Stage gating for phase-2 families (PHASE2_PROTOCOL.md §4).

    record_dev(family, qualifiers_by_config, metrics_by_config)   every config is a counted trial
    freeze(family, config, params, code_paths)                     only a dev-qualified config; hash = code + params
    require(family, "validation" | "final", params, code)          raises StageRefused unless allowed
    record_validation(family, qualifiers, metrics)

State lives in research/phase2/state/<family>.json (version-controlled), so a refusal survives restarts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tradelab.research.registry import record

STATE = Path(__file__).resolve().parent / "state"


class StageRefused(PermissionError):
    pass


def _path(family: str) -> Path:
    return STATE / f"{family}.json"


def _load(family: str) -> dict:
    p = _path(family)
    return json.loads(p.read_text()) if p.exists() else {}


def _save(family: str, s: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    _path(family).write_text(json.dumps(s, indent=1, default=float))


def config_hash(params: dict, code: list[Path]) -> str:
    h = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode())
    for p in sorted(code, key=str):
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


def record_dev(family: str, qualifiers: dict, metrics: dict) -> None:
    s = _load(family)
    s["dev"] = {"qualifiers": qualifiers}
    _save(family, s)
    for cfg, q in qualifiers.items():
        record("result", f"p2_{family}_dev:{cfg}", {"family": family, "config": cfg}, "development",
               f"phase-2 {family} development", metrics={"is_trial": True, "qualifiers": q, **metrics.get(cfg, {})})


def freeze(family: str, config: str, params: dict, code: list[Path]) -> str:
    s = _load(family)
    q = s.get("dev", {}).get("qualifiers", {}).get(config)
    if not q or not q.get("qualified"):
        raise StageRefused(f"{family}/{config} is not dev-qualified: nothing may be frozen")
    if s.get("frozen"):
        raise StageRefused(f"{family} already froze {s['frozen']['config']}; one config per family")
    h = config_hash(params, code)
    s["frozen"] = {"config": config, "params": params, "hash": h}
    _save(family, s)
    record("frozen_config", f"p2_{family}_frozen:{config}", {"hash": h, **params}, "validation+final",
           f"phase-2 {family} frozen before validation")
    return h


def require(family: str, stage: str, params: dict | None = None, code: list[Path] | None = None) -> dict:
    s = _load(family)
    fz = s.get("frozen")
    if not fz:
        raise StageRefused(f"{family}: no frozen dev-qualified configuration; {stage} stays unread")
    if params is not None and code is not None and config_hash(params, code) != fz["hash"]:
        raise StageRefused(f"{family}: configuration hash differs from the frozen {fz['hash']}; refused")
    if stage == "final" and not s.get("validation", {}).get("qualifiers", {}).get("qualified"):
        raise StageRefused(f"{family}: not validated; the final window stays unread")
    return fz


def record_validation(family: str, qualifiers: dict, metrics: dict) -> None:
    s = _load(family)
    s["validation"] = {"qualifiers": qualifiers}
    _save(family, s)
    record("result", f"p2_{family}_validation", {"family": family, "config": (s.get("frozen") or {}).get("config")},
           "validation", f"phase-2 {family} validation", metrics={"qualifiers": qualifiers, **metrics})


def stop(family: str, reason: str) -> None:
    s = _load(family)
    s["stopped"] = reason
    _save(family, s)
    record("result", f"p2_{family}_stopped", {"family": family}, "n/a", reason)
