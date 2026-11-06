"""Provenance-tracked, cached downloads (stdlib only — no heavy deps)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .paths import repo_root
from .provenance import record, sha256_file


def _portable(dest: Path) -> str:
    """The path to store in provenance.json: relative to the repo root when it is inside it.

    provenance.json is committed precisely so a download is reproducible on another machine, so
    an absolute path defeats the file's whole purpose — and two studies had `/Users/<name>/...`
    committed in theirs before this was fixed. Studies that hand-rolled their own downloader all
    stored a relative path, which is how the bug stayed invisible: the forks were right and the
    shared helper was wrong.

    Data can legitimately live outside the repo (`RESEARCH_DATA_DIR` points at a bigger disk on
    the box), and there is no honest relative form for that, so those stay absolute. That branch
    is a real distinction, not backward-compatibility cruft.
    """
    try:
        return str(dest.resolve().relative_to(repo_root().resolve()))
    except ValueError:
        return str(dest.resolve())

# Government/statistical hosts (fda.gov, cdc.gov, seer.cancer.gov …) 403 the default
# urllib agent. Sending a normal browser UA is what every study ended up doing by hand.
#
# It is not universal, and the counter-example does not announce itself: fred.stlouisfed.org
# HANGS on this UA (read timeout, every time) and serves the same CSV in 0.1 s to a
# descriptive UA, to Python-urllib, or to no UA at all. A hang looks like a network problem
# rather than a rejected request, so pass `user_agent="<yourtool>/1.0 (contact)"` when a host
# stalls — the same override that data.sec.gov requires outright.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# What the timeout path below falls back to. Deliberately not "no UA at all": urllib then
# supplies `Python-urllib/3.x`, which is the exact string the gov hosts BROWSER_UA exists for
# reject outright, so the fallback would trade one failure for another.
FALLBACK_UA = "research-toolkit/1.0"


def download(
    url: str,
    params: dict | None,
    dest: str | Path,
    provenance_path: str | Path,
    name: str | None = None,
    user_agent: str | None = BROWSER_UA,
    headers: dict | None = None,
    retries: int = 3,
    timeout: int = 120,
    json_body: dict | None = None,
) -> Path:
    """Download ``url?params`` to ``dest`` (cached: skipped if it already exists),
    and record provenance. Returns the local path.

    ``user_agent`` defaults to a browser UA because several public data hosts reject
    the stdlib default; pass ``user_agent=None`` to send no UA header at all.
    Retries with exponential backoff on transient HTTP 5xx / URLError.

    ``json_body`` turns the request into a POST of that dict as JSON. Several public
    data APIs are query-by-POST only (USAspending's ``/api/v2/search/…``, NIH
    RePORTER's ``/v2/projects/search``) and are otherwise unreachable through this
    helper — which is exactly how download wrappers get forked. The body is recorded
    in provenance next to ``params``, because for a POST API the body *is* the query
    and provenance without it would not identify what was fetched.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    body = json.dumps(json_body, sort_keys=True).encode() if json_body is not None else None

    if not dest.exists():
        hdrs = dict(headers or {})
        if user_agent:
            hdrs.setdefault("User-Agent", user_agent)
        if body is not None:
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(full, data=body, headers=hdrs)
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
                    while chunk := r.read(1 << 16):
                        f.write(chunk)
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                # 4xx (other than 429) won't fix themselves — fail fast rather than sit in backoff.
                status = getattr(e, "code", None)
                fatal = status is not None and 400 <= status < 500 and status != 429
                dest.unlink(missing_ok=True)
                if fatal or attempt == retries - 1:
                    raise
                # A timeout while sending the browser UA is not necessarily a slow network:
                # some hosts stall that UA specifically and answer instantly to anything else
                # (fred.stlouisfed.org does, reproducibly). The failure mode is a hang rather
                # than a rejection, so it reads as a network problem and costs a debugging
                # session. Swap in FALLBACK_UA for the remaining attempts and let retry decide.
                if isinstance(e, TimeoutError) and hdrs.get("User-Agent") == BROWSER_UA:
                    hdrs["User-Agent"] = FALLBACK_UA
                    req = urllib.request.Request(full, data=body, headers=hdrs)
                time.sleep(2**attempt)

    record(
        provenance_path,
        {
            "name": name or dest.name,
            "url": url,
            "params": params or {},
            **({"json_body": json_body} if json_body is not None else {}),
            "file": _portable(dest),
            "bytes": dest.stat().st_size,
            "sha256": sha256_file(dest),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return dest
