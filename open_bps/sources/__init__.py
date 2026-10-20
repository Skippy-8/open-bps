"""Download public benchmarking data and keep a dated raw snapshot with a manifest.

Every snapshot records the source URL, retrieval time and SHA-256 of each file, so a scored dataset can
always be traced to the exact upstream bytes it was computed from (and rebuilt if a portal changes).
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "open-bps (https://github.com/Skippy-8/open-bps)"


def get(url: str, params: dict | None = None, retries: int = 3, timeout: int = 120) -> bytes:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def snapshot_dir(root: Path, jurisdiction: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d = Path(root) / "raw" / jurisdiction / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_manifest(folder: Path, files: dict[str, str]) -> Path:
    """files: name -> source url. Adds size, sha256 and the retrieval time."""
    entries = []
    for name, url in files.items():
        data = (folder / name).read_bytes()
        entries.append({"file": name, "url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": entries}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1))
    return path


def latest_snapshot(root: Path, jurisdiction: str) -> Path:
    base = Path(root) / "raw" / jurisdiction
    snaps = sorted(p for p in base.glob("*") if (p / "manifest.json").exists()) if base.exists() else []
    if not snaps:
        raise FileNotFoundError(f"no {jurisdiction} snapshot under {base}; run `open-bps fetch {jurisdiction}`")
    return snaps[-1]
