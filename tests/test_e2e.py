from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

from dodsl_adapters.knowledge import KnowledgeCompiler
from dodsl_adapters.knowledge.todo2code import Todo2CodeAdapter
from dodsl_adapters.sources import GitSnapshotter, WebSnapshotter
from dodsl_adapters.ssot import SsotBridge
from dodsl_contracts.model import ProjectRequest
from dodsl.service import DoDslService
from dodsl import __version__ as service_version


ROOT = Path(__file__).resolve().parents[1]
ONLYDSL = ROOT.parent / "onlyDSL"


def _git(command: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *command], cwd=cwd, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()


class EndToEndTests(unittest.TestCase):
    def test_git_to_markdown_to_dsl_to_ssot_candidate(self):
        onlydsl_python = ONLYDSL / ".venv/bin/python"
        onlydsl_server = ONLYDSL / "server.py"
        if not onlydsl_python.is_file() or not onlydsl_server.is_file():
            self.skipTest("local onlyDSL checkout unavailable")
        with tempfile.TemporaryDirectory() as repo_td, tempfile.TemporaryDirectory() as projects_td:
            repository = Path(repo_td)
            _git(["init", "-q"], repository)
            _git(["config", "user.email", "test@example.invalid"], repository)
            _git(["config", "user.name", "doDSL Test"], repository)
            (repository / "README.md").write_text("# Controller\n\nThe board width is 42 mm.\n", encoding="utf-8")
            (repository / "TODO.md").write_text("- [ ] Add sensor support\n", encoding="utf-8")
            _git(["add", "README.md", "TODO.md"], repository)
            _git(["commit", "-qm", "initial"], repository)
            request = ProjectRequest.from_dict({
                "schema": "dodsl-request/v1", "projectId": "e2e-device", "title": "E2E Device",
                "gitSources": [{"url": repository.as_uri(), "trustRole": "project"}],
                "webSources": [], "artifacts": ["ssot", "documentation"],
                "requestText": "Create a device from these sources.",
            })
            # Never let a developer's ambient PATH select an arbitrary t2c build.
            # The real todo2code integration is opt-in and pins the complete command.
            configured_todo2code = os.getenv("DODSL_TEST_TODO2CODE_COMMAND", "")
            todo_command = tuple(shlex.split(configured_todo2code)) if configured_todo2code else ()
            todo_adapter = Todo2CodeAdapter(todo_command)
            dodsl = DoDslService(
                projects_td, git=GitSnapshotter(allow_local=True), web=WebSnapshotter(allow_private=True),
                compiler=KnowledgeCompiler(todo_adapter),
                ssot=SsotBridge((str(onlydsl_python), str(onlydsl_server), "ssot")),
            )
            dodsl.create(request)
            dodsl.ingest(request.project_id)
            compiled = dodsl.compile(request.project_id, require_todo2code=todo_adapter.available)
            self.assertGreaterEqual(compiled["documents"], 3)
            compiled_again = dodsl.compile(request.project_id, require_todo2code=todo_adapter.available)
            self.assertEqual(compiled_again["semanticHash"], compiled["semanticHash"])
            workspace = Path(projects_td) / request.project_id
            index = (workspace / "source-md-dsl/knowledge-index.dsl").read_text(encoding="utf-8")
            self.assertIn("KNOWLEDGE_INDEX e2e-device", index)
            self.assertNotIn(str(workspace), index)
            self.assertTrue((workspace / "source-md-dsl/development/f2md/intent-packs.json").is_file())
            if todo_adapter.available:
                self.assertTrue(next((workspace / "source-md-dsl/development/todo2code").rglob("intent.graph.json")).is_file())
                self.assertTrue(next((workspace / "source-md-dsl/development/todo2code").rglob("development-evidence.dsl")).is_file())
            else:
                self.assertTrue(compiled["todo2code"])
                self.assertTrue(all(
                    item["status"] == "skipped" and item["code"] == "TODO2CODE_UNAVAILABLE"
                    for item in compiled["todo2code"].values()
                ))
            candidate = dodsl.reconcile(request.project_id)
            self.assertEqual(candidate["promotion"], "not_performed")
            candidate_tree = workspace / "SSOT/candidate" / candidate["candidateId"] / "tree"
            self.assertTrue((candidate_tree / "sources/knowledge-index.dsl").is_file())
            if todo_adapter.available:
                self.assertTrue(next((candidate_tree / "development/todo2code").rglob("development-evidence.dsl")).is_file())
            self.assertFalse((workspace / "SSOT/current/sources/knowledge-index.dsl").exists())
            status = dodsl.status(request.project_id)
            self.assertTrue(status["ssot"]["verified"])
            self.assertEqual(status["serviceVersion"], service_version)
            self.assertEqual(status["lastIteration"]["stage"], "ssot_candidate_validated")
            self.assertEqual(status["lastIteration"]["candidateId"], candidate["candidateId"])
            if todo_adapter.available:
                self.assertEqual(status["developmentEvidence"]["bundles"], 1)
                evidence = status["developmentEvidence"]["items"][0]
                self.assertEqual(evidence["assessment"], "accepted")
                self.assertEqual(evidence["blockingDiagnostics"], 0)
                self.assertTrue(evidence["evidenceUri"].startswith("urn:onlydsl:development-evidence:sha256:"))


if __name__ == "__main__":
    unittest.main()
