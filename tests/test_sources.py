from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dodsl_adapters.sources import GitSnapshotter, WebSnapshotter
from dodsl_contracts.errors import DoDslValidationError
from dodsl_contracts.model import GitSource, ProjectRequest, WebSource
from dodsl_core.workspace import ProjectWorkspace


class _Page(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/device")
            self.end_headers()
            return
        body = b"<!doctype html><html><head><title>Device</title></head><body><h1>Dimensions</h1><p>Width 42 mm</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def _git(command: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *command], cwd=cwd, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()


def _request(project_id: str = "source-demo") -> ProjectRequest:
    return ProjectRequest.from_dict({
        "schema": "dodsl-request/v1", "projectId": project_id, "title": "Source demo",
        "gitSources": [], "webSources": [], "artifacts": ["ssot"],
    })


class SourceTests(unittest.TestCase):
    def test_git_capture_is_real_clone_with_exact_revision(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as projects:
            repository = Path(td)
            _git(["init", "-q"], repository)
            _git(["config", "user.email", "test@example.invalid"], repository)
            _git(["config", "user.name", "doDSL Test"], repository)
            (repository / "README.md").write_text("# Device\n", encoding="utf-8")
            _git(["add", "README.md"], repository)
            _git(["commit", "-qm", "initial"], repository)
            expected_commit = _git(["rev-parse", "HEAD"], repository)
            workspace = ProjectWorkspace(projects, "source-demo")
            workspace.initialize(_request())
            result = GitSnapshotter(allow_local=True).capture(
                workspace, GitSource(repository.as_uri(), trust_role="project"),
            )
            self.assertEqual(result["commit"], expected_commit)
            self.assertRegex(str(result["evidenceUri"]), r"^urn:dodsl:git:sha256:[0-9a-f]{64}$")
            clone = next((workspace.root / "source/git").glob("*/repository"))
            self.assertEqual((clone / "README.md").read_text(encoding="utf-8"), "# Device\n")

    def test_local_git_is_forbidden_by_default(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as projects:
            workspace = ProjectWorkspace(projects, "source-demo")
            workspace.initialize(_request())
            with self.assertRaisesRegex(DoDslValidationError, "LOCAL_SOURCE_FORBIDDEN"):
                GitSnapshotter(allow_local=False).capture(workspace, GitSource(Path(td).as_uri()))

    def test_web_capture_preserves_raw_html_and_redirect_provenance(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as projects:
                workspace = ProjectWorkspace(projects, "source-demo")
                workspace.initialize(_request())
                url = f"http://127.0.0.1:{server.server_port}/redirect"
                result = WebSnapshotter(allow_private=True).capture(workspace, WebSource(url, "manufacturer"))
                html = next((workspace.root / "source/web").rglob("page.html")).read_bytes()
                self.assertTrue(html.startswith(b"<!doctype html>"))
                self.assertTrue(str(result["resolvedUrl"]).endswith("/device"))
                self.assertEqual(result["method"], "http")
                self.assertRegex(str(result["evidenceUri"]), r"^urn:dodsl:web:sha256:[0-9a-f]{64}$")
        finally:
            server.shutdown()
            server.server_close()

    def test_private_web_is_forbidden_by_default(self):
        with self.assertRaisesRegex(DoDslValidationError, "PRIVATE_ADDRESS"):
            WebSnapshotter(allow_private=False)._fetch("http://127.0.0.1/device", {"127.0.0.1"})


if __name__ == "__main__":
    unittest.main()
