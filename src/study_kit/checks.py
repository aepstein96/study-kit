"""Checks on one study. Each returns a list of problems; empty means healthy."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SUSPECT_EXT = (".csv", ".tsv", ".md")
ALLOW_NAMES = {"readme.md", "notes.md"}  # conventionally notes ABOUT a download
COMMITTED_TIERS = ("tables", "curated")
DERIVED_TIERS = ("interim", "processed")
PLACEHOLDERS = {
    "app/index.html": "<title>REPLACE",
    "study.json": "<Study title",
    "README.md": "# <study title>",
}


def _records(data: Path) -> list[dict]:
    out: list[dict] = []
    for f in data.glob("provenance*.json"):
        try:
            recs = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out += [r for r in (recs if isinstance(recs, list) else recs.values()) if isinstance(r, dict)]
    return out


def curated_data_is_committed(study: Path) -> list[str]:
    """A gitignored table that no provenance record explains is hand-made: nothing can regenerate
    it, so it belongs in the committed data/tables/. An agent's hand-cited CSV written to data/raw/
    is otherwise dropped silently at commit, and the study ships with no evidence.
    """
    data = study / "data"
    if not data.is_dir():
        return []
    known = {os.path.basename(str(r[k])) for r in _records(data) for k in ("file", "path", "dest") if r.get(k)}
    promoted: set[str] = set()
    for tier in COMMITTED_TIERS:
        for _, _, files in os.walk(data / tier):
            promoted.update(files)
    # data/REGENERABLE: "raw/cms/  src/connector_cms.py" declares what a named script fetches again.
    declared = data / "REGENERABLE"
    regenerable = tuple(l.split()[0] for l in declared.read_text().splitlines()
                        if l.strip() and not l.startswith("#")) if declared.exists() else ()
    candidates = []
    for d, _, files in os.walk(data):
        rel = os.path.relpath(d, data)
        if rel.split(os.sep)[0] in COMMITTED_TIERS + DERIVED_TIERS:
            continue
        if regenerable and (rel + "/").startswith(regenerable):
            continue
        for fn in files:
            if not fn.lower().endswith(SUSPECT_EXT) or fn.lower() in ALLOW_NAMES:
                continue
            if fn in known or fn in promoted or any(t.endswith("__" + fn) for t in promoted):
                continue
            candidates.append(os.path.join(d, fn))
    if not candidates:
        return []
    res = subprocess.run(["git", "check-ignore", "--stdin"], cwd=study,
                         input="\n".join(candidates), capture_output=True, text=True)
    return [f"{os.path.relpath(p, study)}: gitignored and no provenance record explains it; "
            "move it to data/tables/, or declare it in data/REGENERABLE"
            for p in res.stdout.splitlines() if p.strip()]


def provenance_paths_are_portable(study: Path) -> list[str]:
    """provenance.json is committed so a download can be reproduced elsewhere; an absolute path
    baked into it defeats that."""
    return [f"data provenance: {k}={str(r[k])[:70]} is absolute"
            for r in _records(study / "data") for k in ("file", "path", "dest")
            if isinstance(r.get(k), str) and os.path.isabs(r[k])]


def no_template_placeholders(study: Path) -> list[str]:
    """A placeholder <title> survives every other check: the page body is fine, and the title only
    shows in browser tabs and link previews."""
    return [f"{rel} still has the template placeholder: {needle}"
            for rel, needle in PLACEHOLDERS.items()
            if (study / rel).exists() and needle in (study / rel).read_text(errors="replace")]


CHECKS = (curated_data_is_committed, provenance_paths_are_portable, no_template_placeholders)


def run(study: Path) -> int:
    failed = 0
    for check in CHECKS:
        problems = check(study)
        print(f"  {'FAIL' if problems else 'PASS'}  {check.__name__}")
        for p in problems[:30]:
            print(f"        {p}")
        if len(problems) > 30:
            print(f"        ... and {len(problems) - 30} more")
        failed += bool(problems)
    return 1 if failed else 0
