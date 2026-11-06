"""Self-check: `python packages/research_toolkit/test_toolkit.py` (no pytest needed)."""
import http.server
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from research_toolkit import (  # noqa: E402
    BROWSER_UA, FALLBACK_UA, download, record, sha256_file, study_root, write_data_json,
)

seen_agents: list[str] = []
seen_posts: list[tuple[str, bytes]] = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        seen_posts.append((self.headers.get("Content-Type", ""), self.rfile.read(n)))
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        seen_agents.append(self.headers.get("User-Agent", ""))
        # Mimic the gov-host behaviour that forked six download helpers: 403 the stdlib UA.
        if "Python-urllib" in seen_agents[-1]:
            self.send_error(403)
            return
        # Mimic FRED: stall the browser UA rather than rejecting it, and serve anything else.
        if "stall=1" in self.path and seen_agents[-1] == BROWSER_UA:
            time.sleep(3)
            return
        body = b"payload"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/f.csv"

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prov, dest = td / "provenance.json", td / "raw" / "f.csv"

        # 1. Default UA gets through where the stdlib default would 403.
        download(url, {"a": 1}, dest, prov, name="f")
        assert dest.read_bytes() == b"payload"
        assert "Mozilla" in seen_agents[-1], seen_agents[-1]
        assert seen_agents[-1] == BROWSER_UA

        # 2. Provenance recorded with a real checksum.
        entry = next(e for e in json.loads(prov.read_text()) if e["name"] == "f")
        assert entry["sha256"] == sha256_file(dest) and entry["bytes"] == 7
        assert entry["params"] == {"a": 1} and entry["url"] == url

        # provenance.json is committed so a download is reproducible on ANOTHER machine, so the
        # recorded path must never be absolute when the file lives inside the repo. Two studies
        # had /Users/<name>/... committed before this was fixed. A temp dir is outside the repo,
        # so here the honest answer is absolute — assert the in-repo case explicitly.
        from research_toolkit.fetch import _portable
        from research_toolkit import repo_root
        inside = repo_root() / "studies" / "x" / "data" / "raw" / "f.zip"
        assert _portable(inside) == "studies/x/data/raw/f.zip", _portable(inside)
        assert not _portable(inside).startswith("/"), "in-repo path must be repo-relative"
        outside = Path("/tmp/elsewhere/f.zip")
        assert _portable(outside).startswith("/"), "out-of-repo path has no honest relative form"

        # 3. Cached: a second call must not re-fetch.
        before = len(seen_agents)
        download(url, {"a": 1}, dest, prov, name="f")
        assert len(seen_agents) == before, "cache miss — re-downloaded an existing file"

        # 4. Custom headers survive alongside the UA default.
        download(url, None, td / "raw" / "g.csv", prov, headers={"Accept": "text/csv"})

        # 5. Fatal 4xx raises instead of sitting in backoff, and leaves no stub file.
        stub = td / "raw" / "denied.csv"
        try:
            download(url, None, stub, prov, user_agent="Python-urllib/3", retries=2)
        except Exception:
            pass
        else:
            raise AssertionError("403 should have raised")
        assert not stub.exists(), "failed download left a partial file behind"

        # 6. A host that HANGS on the browser UA (fred.stlouisfed.org does) is retried
        #    without it. The tell is a timeout rather than a rejection, which reads as a bad
        #    network and costs a debugging session, so the recovery is automatic.
        hung = td / "raw" / "hung.csv"
        download(url, {"stall": 1}, hung, prov, name="hung", timeout=1, retries=3)
        assert hung.read_bytes() == b"payload"
        assert seen_agents[-2] == BROWSER_UA, "first attempt should send the browser UA"
        assert seen_agents[-1] == FALLBACK_UA, "retry after a timeout should swap the UA"

        # 7. json_body makes it a POST — the query-by-POST APIs (USAspending, NIH RePORTER)
        #    are unreachable otherwise, and that is how download helpers get forked.
        #    For those APIs the body IS the query, so provenance must carry it.
        q = {"filters": {"recipient": "ACME"}, "limit": 2}
        pdest = td / "raw" / "post.json"
        download(url, None, pdest, prov, name="p", json_body=q)
        assert json.loads(pdest.read_text()) == {"ok": True}
        ctype, raw = seen_posts[-1]
        assert ctype == "application/json", ctype
        assert json.loads(raw) == q, raw
        pentry = next(e for e in json.loads(prov.read_text()) if e["name"] == "p")
        assert pentry["json_body"] == q, "POST body must be recorded — it is the query"
        # A GET must stay a GET: no body key smuggled into an existing caller's provenance.
        assert "json_body" not in entry

        # 8. study_root walks up to the pyproject.toml dir; write_data_json is cwd-proof.
        (td / "app").mkdir()
        (td / "pyproject.toml").write_text("[project]\nname='x'\n")
        nested = td / "analysis"
        nested.mkdir()
        assert study_root(nested / "analyze.py") == td.resolve()
        out = write_data_json(td, {"k": 1})
        assert out == td / "app" / "public" / "data.json"
        assert json.loads(out.read_text()) == {"k": 1}

        # 9. project_root finds project.json and refuses to guess outside a project.
        from research_toolkit import project_root
        g = td / "proj"
        (g / "a" / "src").mkdir(parents=True)
        (g / "project.json").write_text("{}")
        assert project_root(g / "a" / "src" / "x.py") == g.resolve()
        try:
            project_root(td / "x.py")
            raise AssertionError("project_root must raise outside a project")
        except FileNotFoundError:
            pass

    srv.shutdown()
    print("research_toolkit OK")


if __name__ == "__main__":
    main()
