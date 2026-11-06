"""study-kit: scaffold, verify and deploy the studies in a project.

A project is a directory holding a project.json. A study is a directory directly inside it
holding a study.json. Nothing here knows where a project deploys: that lives on the machine,
in ~/.config/study-kit/deploy.toml, so a project repo can be handed to someone as-is.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from . import KIT_REPO, checks, deploy

HERE = Path(__file__).resolve().parent
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def project_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "project.json").exists():
            return d
    sys.exit(f"study-kit: {here} is not inside a project (no project.json above it)")


def studies(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob("*/study.json"))


def current_study(root: Path) -> str | None:
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if d == root:
            return None
        if (d / "study.json").exists():
            return d.name
    return None


def fill_pins(path: Path, tag: str) -> None:
    for f in path.rglob("*"):
        if f.is_file() and f.name in ("pyproject.toml", "package.json"):
            s = f.read_text()
            if "{{KIT_TAG}}" in s:
                f.write_text(s.replace("{{KIT_TAG}}", tag).replace("{{KIT_REPO}}", KIT_REPO))


def sync_claude(root: Path) -> None:
    """Copy the guide, commands and agents of this kit version into <project>/.claude/."""
    src, dest = HERE / "claude", root / ".claude"
    if not src.exists():  # running from a source checkout
        src = HERE.parents[1] / "claude"
    guide = HERE / "GUIDE.md"
    if not guide.exists():
        guide = HERE.parents[1] / "GUIDE.md"
    for sub in ("commands", "agents"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
        for f in (src / sub).glob("*.md"):
            shutil.copy2(f, dest / sub / f.name)
    shutil.copy2(guide, dest / "GUIDE.md")


def kit_tag() -> str:
    from importlib.metadata import version
    return "v" + version("study-kit")


def cmd_init(a) -> int:
    root = Path(a.dir).resolve()
    if (root / "project.json").exists():
        sys.exit(f"study-kit: {root} already has a project.json")
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(HERE / "template" / "project", root, dirs_exist_ok=True)
    meta = {"title": a.title or root.name, "description": a.description or "",
            "urlKey": secrets.token_hex(6), "kit": kit_tag()}
    (root / "project.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    sync_claude(root)
    print(f"project ready at {root}\nnext: cd {root} && git init && study-kit new <study-name>")
    return 0


def cmd_new(a) -> int:
    root = project_root()
    if not NAME_RE.match(a.name):
        sys.exit("study-kit: a study name is lowercase letters, digits and hyphens")
    dest = root / a.name
    if dest.exists():
        sys.exit(f"study-kit: {dest} already exists")
    shutil.copytree(HERE / "template" / "study", dest)
    tag = json.loads((root / "project.json").read_text()).get("kit") or kit_tag()
    fill_pins(dest, tag)
    meta = json.loads((dest / "study.json").read_text())
    meta["urlKey"] = secrets.token_hex(6)
    (dest / "study.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"created {dest}\nnext: cd {dest} && uv sync && (cd app && npm install)\n"
          "It deploys as its own site the next time anyone runs `study-kit deploy`.")
    return 0


def cmd_verify(a) -> int:
    root = project_root()
    name = a.name or current_study(root)
    if not name:
        print("usage: study-kit verify <study>\nstudies:", *[s.name for s in studies(root)], sep="\n  ")
        return 2
    if not (root / name / "study.json").exists():
        sys.exit(f"study-kit: no study named {name} in {root}")
    argv = ["bash", str(HERE / "verify.sh"), str(root), name] + (["--skip-analysis"] if a.skip_analysis else [])
    return subprocess.call(argv, env={**os.environ, "STUDY_KIT_PY": sys.executable})


def cmd_check(a) -> int:
    root = project_root()
    name = a.name or current_study(root)
    if not name:
        sys.exit("usage: study-kit check <study>")
    return checks.run(root / name)


def cmd_deploy(a) -> int:
    root = project_root()
    all_studies = studies(root)
    if a.names:
        unknown = set(a.names) - {s.name for s in all_studies}
        if unknown:
            sys.exit(f"study-kit: unknown studies: {sorted(unknown)}")
    return deploy.run(root, all_studies, set(a.names) or None)


def cmd_bump(a) -> int:
    """Point the project and all its studies at another kit version, and re-sync .claude/."""
    root = project_root()
    meta = json.loads((root / "project.json").read_text())
    meta["kit"] = a.tag
    (root / "project.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    for s in studies(root):
        for f, pat, new in [
            (s / "pyproject.toml", r'(study-kit = \{ git = "[^"]+", tag = ")[^"]+', rf"\g<1>{a.tag}"),
            (s / "app/package.json", r'("study-kit": "github:[^#]+#)[^"]+', rf"\g<1>{a.tag}"),
        ]:
            text, n = re.subn(pat, new, f.read_text())
            assert n == 1, f"{f}: expected one study-kit pin, found {n}"
            f.write_text(text)
    sync_claude(root)
    print(f"pinned {len(studies(root))} studies to {a.tag}; run `uv sync` and `npm install` in each")
    return 0


def cmd_setup(a) -> int:
    """Write the machine-local file every project's CLAUDE.md imports. Not in any repo."""
    d = Path.home() / ".config" / "study-kit"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# Machine-local context for study-kit projects. Not part of any repo.\n"]
    if a.lessons:
        lessons = Path(a.lessons).expanduser().resolve()
        if not lessons.exists():
            sys.exit(f"study-kit: no lessons file at {lessons}")
        lines.append(f"@{lessons}\n")
    (d / "context.md").write_text("".join(lines))
    print(f"wrote {d / 'context.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="study-kit", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="create a new project")
    s.add_argument("dir"); s.add_argument("--title"); s.add_argument("--description")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("new", help="create a study in this project")
    s.add_argument("name"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("verify", help="analysis, types, build, serve, screenshot, checks")
    s.add_argument("name", nargs="?"); s.add_argument("--skip-analysis", action="store_true")
    s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("check", help="only the data and metadata checks")
    s.add_argument("name", nargs="?"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("deploy", help="build and publish studies, then the project index")
    s.add_argument("names", nargs="*"); s.set_defaults(fn=cmd_deploy)
    s = sub.add_parser("bump", help="move this project to another kit version")
    s.add_argument("tag"); s.set_defaults(fn=cmd_bump)
    s = sub.add_parser("setup", help="configure this machine")
    s.add_argument("--lessons", help="path to a LESSONS.md to load in every project")
    s.set_defaults(fn=cmd_setup)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
