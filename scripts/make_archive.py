"""Build the project archives (no credentials, no virtualenv).

  tradelab-core-<date>.tar.gz : code, tests, reports, configs, lockfile, experiment log, provenance, small outputs
  tradelab-data-<date>.tar.gz : downloaded market/event data + paper journals, with SHA256SUMS

Run: .venv/bin/python scripts/make_archive.py [--out DIR]
"""
import argparse
import hashlib
import json
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", ".git"}
SECRET_FILES = re.compile(r"(^\.env$|\.pem$|\.key$|credentials|secrets\.toml$)")
SECRET_TEXT = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\n[A-Za-z0-9+/=]{40,}")


def files(base: Path):
    for p in sorted(base.rglob("*")):
        if p.is_dir() or any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if SECRET_FILES.search(p.name):
            raise SystemExit(f"refusing to archive credential-like file: {p}")
        yield p


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    data = ROOT / "data"
    core = [p for p in files(ROOT) if data not in p.parents]
    for p in core:
        if p.suffix in {".py", ".md", ".toml", ".json", ".yml", ".txt", ".lock", ".csv", ".jsonl"} and p.stat().st_size < 5e6:
            if SECRET_TEXT.search(p.read_text(errors="ignore")):
                raise SystemExit(f"possible private key in {p}")
    data_files = list(files(data))
    sums = ROOT / "data" / "SHA256SUMS"
    sums.write_text("".join(f"{sha(p)}  {p.relative_to(ROOT)}\n" for p in data_files if p.name != "SHA256SUMS"))
    manifest = {"built_at": stamp, "core_files": len(core), "data_files": len(data_files),
                "excluded": sorted(EXCLUDE_DIRS), "credentials": "none present; paper mode only"}
    (ROOT / "ARCHIVE_MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    core.append(ROOT / "ARCHIVE_MANIFEST.json")
    for name, items in (("core", core), ("data", data_files + [sums])):
        path = out / f"tradelab-{name}-{stamp}.tar.gz"
        with tarfile.open(path, "w:gz", compresslevel=6) as t:
            for p in sorted(set(items)):
                t.add(p, arcname=f"tradelab/{p.relative_to(ROOT)}")
        print(path, f"{path.stat().st_size / 1e6:.1f} MB", sha(path))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "archives"))
    main(Path(ap.parse_args().out))
