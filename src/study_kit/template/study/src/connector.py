"""Fetch this study's data. Every download goes through research_toolkit so
provenance (URL, params, timestamp, SHA-256) is recorded automatically.

`download()` already handles the things studies keep re-inventing: it caches (skips a
file that exists), sends a browser User-Agent (several public data hosts 403 the stdlib
default), and retries transient 5xx. Pass `headers=`/`user_agent=` if a host needs
something specific — don't fork a curl wrapper.
"""
from pathlib import Path

from research_toolkit import data_root, download, study_root

STUDY = study_root(__file__)
DATA = data_root(STUDY)  # <study>/data by default; RESEARCH_DATA_DIR overrides


def fetch() -> Path:
    return download(
        url="https://example.com/api",
        params={"q": "value"},
        dest=DATA / "raw" / "example.json",
        provenance_path=DATA / "provenance.json",
        name="example",
    )
