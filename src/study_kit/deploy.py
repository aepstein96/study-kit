"""Publish each study as its own Cloudflare Pages site, then the project's index site.

Where things go is machine config, never project code. ~/.config/study-kit/deploy.toml:

    prefix = "ab"                  # starts every site name; pages.dev names are global
    feedback_kv_id = "<namespace>" # optional: where FeedbackBox comments land

Site names are <prefix>-<study>-<urlKey>. The urlKey is random and lives in study.json, so a study
nobody has been given the link to can't be guessed. Sites are created the first time they deploy.
"""
from __future__ import annotations

import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_DIR = Path(os.environ.get("STUDY_KIT_CONFIG_DIR", Path.home() / ".config" / "study-kit"))
COMPAT_DATE = "2026-07-01"
MAX_SITE_NAME = 58  # Cloudflare's limit on a pages.dev subdomain label
PROPAGATION_TIMEOUT = 120

NOT_FOUND = """<!doctype html><meta charset="utf-8"><title>Not found</title>
<style>body{font:16px/1.5 system-ui;display:grid;place-items:center;min-height:100vh;margin:0}</style>
<p>404: nothing here.</p>
"""


def load_config() -> dict:
    path = CONFIG_DIR / "deploy.toml"
    if not path.exists():
        sys.exit(f"study-kit: no deploy config at {path}.\n"
                 'Create it with at least: prefix = "<short-unique-prefix>"')
    cfg = tomllib.loads(path.read_text())
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", cfg.get("prefix", "")):
        sys.exit(f"study-kit: {path} needs a lowercase prefix")
    return cfg


def wrangler(*args: str, cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["wrangler", *args], cwd=cwd, text=True, capture_output=capture)


def ensure_key(meta_path: Path) -> dict:
    meta = json.loads(meta_path.read_text())
    if not meta.get("urlKey"):
        meta["urlKey"] = secrets.token_hex(6)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return meta


def site_name(prefix: str, name: str, key: str) -> str:
    room = MAX_SITE_NAME - len(prefix) - len(key) - 2
    return f"{prefix}-{name[:room].rstrip('-')}-{key}"


def toml_str(s: str) -> str:
    return json.dumps(s)


def stage(site_dir: Path, staging: Path, site: str, cfg: dict, study: str | None, extra_functions: Path | None) -> None:
    """Lay out what wrangler publishes: the site, its Functions, and a generated wrangler.toml."""
    shutil.copytree(site_dir, staging / "site")
    with open(staging / "site" / "_headers", "a") as f:
        f.write("/*\n  X-Robots-Tag: noindex\n")
    # Without a 404.html, Pages serves index.html for every unmatched path.
    if not (staging / "site" / "404.html").exists():
        (staging / "site" / "404.html").write_text(NOT_FOUND)
    toml = [f"name = {toml_str(site)}", 'pages_build_output_dir = "site"',
            f"compatibility_date = {toml_str(COMPAT_DATE)}"]
    if study:
        toml += ["", "[vars]", f"STUDY_NAME = {toml_str(study)}"]
        if cfg.get("feedback_kv_id"):
            shutil.copytree(HERE / "functions", staging / "functions")
            toml += ["", "[[kv_namespaces]]", 'binding = "FEEDBACK"', f"id = {toml_str(cfg['feedback_kv_id'])}"]
    if extra_functions and extra_functions.is_dir():
        shutil.copytree(extra_functions, staging / "functions", dirs_exist_ok=True)
    (staging / "wrangler.toml").write_text("\n".join(toml) + "\n")


def publish(site_dir: Path, site: str, cfg: dict, existing: set[str], study: str | None = None,
            extra_functions: Path | None = None) -> bool:
    if site not in existing:
        print(f">> creating site {site}")
        if wrangler("pages", "project", "create", site, "--production-branch", "main").returncode:
            return False
        existing.add(site)
    with tempfile.TemporaryDirectory(prefix="study-kit-") as t:
        staging = Path(t)
        stage(site_dir, staging, site, cfg, study, extra_functions)
        # --branch pinned: otherwise wrangler infers it from ambient git state, and a wrong guess
        # "succeeds" as a preview deployment.
        return wrangler("pages", "deploy", "--project-name", site, "--branch", "main",
                        "--commit-dirty=true", cwd=staging).returncode == 0


def fetch(url: str) -> str:
    # A named agent: Cloudflare answers Python's default User-Agent with 403.
    req = urllib.request.Request(f"{url}?nocache={time.time_ns()}", headers={"User-Agent": "study-kit"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def wait_for_live(built: dict[str, Path]) -> list[str]:
    """"Deployment complete" is not "propagated": the live URL can serve the previous bundle for a
    minute. Each index.html names its content-hashed bundle, so compare that with what was built.
    """
    want = {}
    for url, index in built.items():
        m = re.search(r"assets/[\w.-]+\.js", index.read_text(errors="replace"))
        want[url] = m.group(0) if m else index.read_text(errors="replace")[:200]
    pending, deadline = dict(want), time.time() + PROPAGATION_TIMEOUT
    while pending and time.time() < deadline:
        for url, marker in list(pending.items()):
            try:
                if marker in fetch(url):
                    del pending[url]
            except (urllib.error.URLError, OSError):
                pass
        if pending:
            time.sleep(5)
    return sorted(pending)


def index_html(project: dict, cards: list[dict]) -> str:
    e = html.escape
    items = "\n".join(
        f'<a class="card" href="{e(c["url"])}/"><figure><img src="{e(c["url"])}/cover.svg" alt="" loading="lazy"></figure>'
        f'<div class="body"><h2>{e(c["title"])}</h2><p>{e(c["description"])}</p>'
        f'<span class="go">Open study &rarr;</span></div></a>' for c in cards)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(project.get("title", ""))}</title>
<style>
:root {{ --bg:#f7f5f0; --fg:#22211d; --muted:#716c60; --card:#fffdf8; --line:#e4e0d5; --accent:#3574d4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14161c; --fg:#e8eaf0; --muted:#9aa3b2; --card:#1e2129; --line:#2a2e38; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
.wrap {{ max-width:940px; margin:0 auto; padding:48px 24px 72px; }}
h1,h2 {{ font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; font-weight:500; }}
h1 {{ font-size:clamp(1.9rem,4.5vw,2.7rem); line-height:1.15; margin:0 0 10px; }}
.lede {{ color:var(--muted); max-width:64ch; margin:0 0 40px; }}
.grid {{ display:grid; grid-template-columns:1fr; gap:28px; }}
@media (min-width:700px) {{ .grid {{ grid-template-columns:1fr 1fr; }} }}
.card {{ display:flex; flex-direction:column; background:var(--card); border:1px solid var(--line); border-radius:12px;
  overflow:hidden; color:inherit; text-decoration:none; }}
.card:hover {{ border-color:var(--accent); }}
.card:focus-visible {{ outline:2px solid var(--accent); outline-offset:3px; }}
.card figure {{ margin:0; padding:22px 22px 8px; }}
.card img {{ display:block; width:100%; height:auto; }}
.body {{ padding:4px 22px 20px; display:flex; flex-direction:column; flex:1; }}
.card h2 {{ font-size:1.35rem; margin:8px 0; }}
.card p {{ color:var(--muted); font-size:.92rem; margin:0 0 18px; }}
.go {{ margin-top:auto; color:var(--accent); font-size:.85rem; }}
</style></head>
<body><main class="wrap">
<h1>{e(project.get("title", ""))}</h1>
<p class="lede">{e(project.get("description", ""))}</p>
<div class="grid">
{items}
</div>
</main></body></html>
"""


def record_sites(project_slug: str, entry: dict) -> None:
    """Remember what this machine has published. A hub can list every project from this file,
    which is why it lives here and not in any project repo."""
    path = CONFIG_DIR / "sites.json"
    sites = json.loads(path.read_text()) if path.exists() else {}
    sites[project_slug] = entry
    path.write_text(json.dumps(sites, indent=2, ensure_ascii=False) + "\n")


def is_committed(study: Path) -> bool:
    r = subprocess.run(["git", "ls-files", "--", "study.json"], cwd=study, capture_output=True, text=True)
    return bool(r.stdout.strip())


def is_dirty(study: Path) -> bool:
    r = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=study, capture_output=True, text=True)
    return bool(r.stdout.strip())


def run(root: Path, studies: list[Path], only: set[str] | None) -> int:
    cfg = load_config()
    if shutil.which("wrangler") is None:
        sys.exit("study-kit: wrangler not found (npm i -g wrangler)")
    # A browser login cannot complete in a background run. Fail here rather than hang there.
    who = wrangler("whoami", capture=True)
    if "not authenticated" in (who.stdout + who.stderr).lower():
        sys.exit("study-kit: not logged in to Cloudflare. Run `wrangler login`, or set CLOUDFLARE_API_TOKEN.")
    listing = wrangler("pages", "project", "list", capture=True).stdout
    existing = set(re.findall(r"([a-z0-9][a-z0-9-]*)\.pages\.dev", listing))

    project = ensure_key(root / "project.json")
    prefix = cfg["prefix"]
    cards, built, failed, skipped, dirty = [], {}, [], [], []
    for study in studies:
        name = study.name
        # An uncommitted study is someone's work in flight: never publish it for them.
        if not is_committed(study):
            skipped.append(name)
            continue
        meta = ensure_key(study / "study.json")
        site = site_name(prefix, name, meta["urlKey"])
        url = f"https://{site}.pages.dev"
        cards.append({"name": name, "url": url, "title": meta.get("title", name),
                      "description": meta.get("description", "")})
        if only is not None and name not in only:
            continue
        if is_dirty(study):
            dirty.append(name)
        print(f">> building {name}")
        app = study / "app"
        ok = subprocess.run("npm ci || npm install", shell=True, cwd=app).returncode == 0 \
            and subprocess.run(["npm", "run", "build"], cwd=app).returncode == 0
        if ok and publish(app / "dist", site, cfg, existing, study=name, extra_functions=study / "functions"):
            built[url] = app / "dist" / "index.html"
        else:
            failed.append(name)

    index_site = site_name(prefix, root.name, project["urlKey"])
    index_url = f"https://{index_site}.pages.dev"
    with tempfile.TemporaryDirectory(prefix="study-kit-index-") as t:
        (Path(t) / "index.html").write_text(index_html(project, cards))
        if publish(Path(t), index_site, cfg, existing):
            live_marker = Path(t) / "index.html"
            stale = wait_for_live({**built, index_url: live_marker})
        else:
            failed.append("(project index)")
            stale = wait_for_live(built)

    record_sites(root.name, {"title": project.get("title", root.name), "description": project.get("description", ""),
                             "url": index_url, "studies": cards})
    print(f"\n>> {project.get('title', root.name)}: {index_url}/")
    for c in cards:
        state = "STILL STALE" if c["url"] in stale else "live" if c["url"] in built else "unchanged"
        print(f"   {state:<12} {c['name']:<36} {c['url']}/")
    if skipped:
        print(f">> NOT published (uncommitted): {', '.join(skipped)}")
    if dirty:
        print(f">> WARNING: built from uncommitted changes: {', '.join(dirty)}")
    if failed:
        print(f">> FAILED: {', '.join(failed)}")
    if index_url in stale:
        print(">> STILL STALE: the project index")
    return 1 if failed or stale else 0
