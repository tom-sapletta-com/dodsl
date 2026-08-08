from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dodsl_adapters.knowledge.todo2code import Todo2CodeAdapter
from dodsl_contracts.development_evidence import parse_development_evidence


class Todo2CodeAdapterTests(unittest.TestCase):
    def test_fixed_adapter_materializes_deterministic_non_executing_evidence_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "controller"
            repository = workspace / "source/git/firmware-a1b2c3/repository"
            repository.mkdir(parents=True)
            (repository.parent / "manifest.json").write_text(json.dumps({
                "commit": "a" * 40, "tree": "b" * 40,
            }), encoding="utf-8")
            output = workspace / "source-md-dsl/development/todo2code/firmware-a1b2c3"
            invocation = 0

            def fake_run(args, **kwargs):
                nonlocal invocation
                invocation += 1
                self.assertEqual(kwargs["env"]["OPENROUTER_API_KEY"], "")
                self.assertIn("--nl-mode", args)
                self.assertIn("deterministic", args)
                self.assertIn("--no-docs-llm", args)
                runtime_output = Path(args[args.index("--out") + 1])
                run = runtime_output / "runs/run-1"
                run.mkdir(parents=True)
                graph = {
                    "schemaVersion": "t2c.intent-graph/v1", "generatedAt": f"run-{invocation}",
                    "records": [{"id": "record-1", "source": str(repository / "README.md")}],
                    "relations": [],
                }
                diagnostics = {
                    "schemaVersion": "t2c.diagnostics/v1", "generatedAt": f"run-{invocation}",
                    "diagnostics": [], "counts": {"info": 1, "warning": 2, "review_required": 0, "blocking": 0},
                }
                plans = {
                    "schemaVersion": "t2c.code-change-plan/v1", "generatedAt": f"run-{invocation}",
                    "plans": [], "generation": {"mode": "deterministic"},
                }
                manifest = {
                    "schemaVersion": "t2c.run/v1", "runId": f"run-{invocation}",
                    "createdAt": f"2026-08-08T00:00:0{invocation}Z", "status": "succeeded",
                    "runtime": {"name": "todo2code", "version": "0.5.1"},
                    "configuration": {
                        "nlMode": "deterministic", "markdownMode": "deterministic",
                        "communicationMode": "deterministic", "documentPatterns": ["README.md"],
                    },
                    "stages": {
                        "markdownExtraction": {
                            "status": "succeeded", "requestedMode": "deterministic",
                            "effectiveMode": "deterministic", "degraded": False,
                            "recordCount": 1, "warningCount": 0, "durationMs": invocation,
                        },
                    },
                    "llm": {"markdownExtraction": False}, "warnings": [],
                }
                graph_path = run / "intent.graph.json"
                diagnostics_path = run / "diagnostics.json"
                plans_path = run / "code-change-plans.json"
                graph_path.write_text(json.dumps(graph), encoding="utf-8")
                diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")
                plans_path.write_text(json.dumps(plans), encoding="utf-8")
                envelope = {
                    "graphPath": str(graph_path), "diagnosticsPath": str(diagnostics_path),
                    "codeChangePlansPath": str(plans_path), "manifest": manifest,
                }
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(envelope), stderr="")

            adapter = Todo2CodeAdapter(("t2c-fixed",))
            with patch("dodsl_adapters.knowledge.todo2code.subprocess.run", side_effect=fake_run):
                first = adapter.compile_repository(repository, output, workspace_root=workspace, project_id="controller")
                second = adapter.compile_repository(repository, output, workspace_root=workspace, project_id="controller")

            self.assertEqual(first["semanticHash"], second["semanticHash"])
            self.assertNotEqual(first["executionHash"], second["executionHash"])
            bundle = parse_development_evidence((output / "development-evidence.dsl").read_text(encoding="utf-8"))
            self.assertEqual(bundle.repository_revision, "a" * 40)
            self.assertEqual(bundle.repository_tree, "b" * 40)
            self.assertEqual(bundle.assessment, "accepted")
            self.assertEqual(bundle.blocking_diagnostics, 0)
            self.assertEqual(bundle.warning_diagnostics, 2)
            self.assertEqual(bundle.evidence_uri, second["evidenceUri"])
            self.assertNotIn(str(workspace), (output / "intent.graph.json").read_text(encoding="utf-8"))
            self.assertNotIn("generatedAt", (output / "code-change-plans.json").read_text(encoding="utf-8"))
            semantic_manifest = json.loads((output / "manifest.semantic.json").read_text(encoding="utf-8"))
            self.assertFalse(semantic_manifest["llmUsed"])
            self.assertEqual(semantic_manifest["authorityEffect"], "none")
            self.assertEqual(semantic_manifest["mutationEffect"], "none")


if __name__ == "__main__":
    unittest.main()
