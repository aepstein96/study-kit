"""Record how each downloaded file was obtained, so raw data need not be versioned."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def record(provenance_path: str | Path, entry: dict) -> None:
    """Upsert one provenance entry (keyed by ``name``) into provenance.json."""
    provenance_path = Path(provenance_path)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if provenance_path.exists():
        entries = json.loads(provenance_path.read_text())
    # An unchanged input keeps its record: rewriting recorded_at on every re-run leaves a diff that
    # means nothing, and with several contributors those diffs collide for no reason.
    stamp = "recorded_at"
    for e in entries:
        if e.get("name") == entry.get("name") and {k: v for k, v in e.items() if k != stamp} == {
                k: v for k, v in entry.items() if k != stamp}:
            return
    entry = {**entry, stamp: datetime.now(timezone.utc).isoformat()}
    entries = [e for e in entries if e.get("name") != entry.get("name")] + [entry]
    provenance_path.write_text(json.dumps(entries, indent=2) + "\n")
