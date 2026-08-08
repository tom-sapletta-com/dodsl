from __future__ import annotations

import json
import os
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


ROOT = Path(__file__).resolve().parents[1]
ONLYDSL = ROOT.parent / "onlyDSL"
TODO2CODE = Path("/home/tom/github/semcod/todo2code")


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
            todo_command: tuple[str, ...] = ()
            todo_cli = TODO2CODE / "dist/src/cli.js"
            if todo_cli.is_file():
                todo_command = ("node", str(todo_cli))
            dodsl = DoDslService(
                projects_td, git=GitSnapshotter(allow_local=True), web=WebSnapshotter(allow_private=True),
                compiler=KnowledgeCompiler(Todo2CodeAdapter(todo_command)),
                ssot=SsotBridge((str(onlydsl_python), str(onlydsl_server), "ssot")),
            )
            dodsl.create(request)
            dodsl.ingest(request.project_id)
            compiled = dodsl.compile(request.project_id, require_todo2code=bool(todo_command))
            self.assertGreaterEqual(compiled["documents"], 3)
            compiled_again = dodsl.compile(request.project_id, require_todo2code=bool(todo_command))
            self.assertEqual(compiled_again["semanticHash"], compiled["semanticHash"])
            workspace = Path(projects_td) / request.project_id
            index = (workspace / "source-md-dsl/knowledge-index.dsl").read_text(encoding="utf-8")
            self.assertIn("KNOWLEDGE_INDEX e2e-device", index)
            self.assertNotIn(str(workspace), index)
            self.assertTrue((workspace / "source-md-dsl/development/f2md/intent-packs.json").is_file())
            if todo_command:
                self.assertTrue(next((workspace / "source-md-dsl/development/todo2code").rglob("intent.graph.json")).is_file())
            candidate = dodsl.reconcile(request.project_id)
            self.assertEqual(candidate["promotion"], "not_performed")
            candidate_tree = workspace / "SSOT/candidate" / candidate["candidateId"] / "tree"
            self.assertTrue((candidate_tree / "sources/knowledge-index.dsl").is_file())
            self.assertFalse((workspace / "SSOT/current/sources/knowledge-index.dsl").exists())
            status = dodsl.status(request.project_id)
            self.assertTrue(status["ssot"]["verified"])
            self.assertEqual(status["serviceVersion"], "0.1.0")
            self.assertEqual(status["lastIteration"]["stage"], "ssot_candidate_validated")
            self.assertEqual(status["lastIteration"]["candidateId"], candidate["candidateId"])


if __name__ == "__main__":
    unittest.main()
