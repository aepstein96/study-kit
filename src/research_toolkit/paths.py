"""Resolve where things live, portably (works locally or on the box)."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Walk up to the repo root (marked by CLAUDE.md or .git). The toolkit is installed inside a
    study's .venv, so this finds the repo that contains that study."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "CLAUDE.md").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def study_root(caller_file: str | os.PathLike) -> Path:
    """The study directory containing ``caller_file``, found by walking up to the
    dir holding ``pyproject.toml`` — i.e. the study's folder.

    Pass ``__file__``. Every path in an analysis/connector script should hang off
    this, never off the process cwd: the session shell's cwd resets between
    commands, and relative paths have silently turned real verification runs into
    sheets of false FAILs.
    """
    here = Path(caller_file).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parent


def project_root(caller_file: str | os.PathLike) -> Path:
    """The project containing ``caller_file``: the nearest ancestor holding a ``project.json``.
    Reach a sibling study through this, so the path survives the project being cloned anywhere.
    Raises when the caller is not inside a project, rather than guessing a directory.
    """
    here = Path(caller_file).resolve()
    for parent in here.parents:
        if (parent / "project.json").exists():
            return parent
    raise FileNotFoundError(f"{caller_file} is not inside a project (no project.json above it)")


def write_data_json(study_dir: str | os.PathLike, payload: dict) -> Path:
    """Write the app's ``app/public/data.json`` and report it. The one output path
    every study shares — resolved absolutely, so it lands correctly from any cwd.

    ``allow_nan=False``: Python would happily emit a bare ``NaN``, which is invalid
    JSON — the browser's ``response.json()`` then rejects and the whole app sticks on
    its loading screen (one unfilled pandas value did exactly that). Fail here, loudly,
    at write time instead.

    A payload that differs only in ``meta.generated`` is not written: the file is one long
    line, so a timestamp-only rewrite makes every re-run a merge conflict between contributors.
    """
    import json

    def without_stamp(p: dict) -> dict:
        return {**p, "meta": {k: v for k, v in p["meta"].items() if k != "generated"}} \
            if isinstance(p.get("meta"), dict) else p

    dest = Path(study_dir) / "app" / "public" / "data.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, allow_nan=False)
    if dest.exists():
        try:
            if without_stamp(json.loads(dest.read_text())) == without_stamp(json.loads(text)):
                print(f"unchanged {dest}")
                return dest
        except json.JSONDecodeError:
            pass  # a corrupt file gets replaced below
    dest.write_text(text)
    print(f"wrote {dest} ({dest.stat().st_size} bytes)")
    return dest


def data_root(study_dir: str | os.PathLike | None = None) -> Path:
    """Data location for a study.

    Default: ``<study_dir>/data``. Override globally with ``RESEARCH_DATA_DIR``
    (e.g. point at a bigger disk on the box) without changing any code.
    """
    override = os.environ.get("RESEARCH_DATA_DIR")
    if override:
        return Path(override)
    if study_dir is not None:
        return Path(study_dir) / "data"
    return repo_root() / "data"
