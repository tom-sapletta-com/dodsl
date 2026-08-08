from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dodsl.dsl import KnowledgeDocument, render_knowledge_index, render_project_dodsl, render_trust_policy
from dodsl.errors import DoDslValidationError
from dodsl.model import ProjectRequest
from dodsl.workspace import ProjectWorkspace


def request_value(**updates):
    value = {
        "schema": "dodsl-request/v1", "projectId": "device-demo", "title": "Device demo",
        "gitSources": [{"url": "https://github.com/example/device.git", "trustRole": "project"}],
        "webSources": [{"url": "https://example.com/device", "trustRole": "manufacturer"}],
        "artifacts": ["ssot", "documentation", "pcb", "stl"],
        "requestText": "Build the described device.",
    }
    value.update(updates)
    return value


class ContractTests(unittest.TestCase):
    def test_request_is_strict_and_free_text_remains_uninterpreted(self):
        request = ProjectRequest.from_dict(request_value())
        dsl = render_project_dodsl(request)
        self.assertIn("INTERPRETATION waiting_interpretation", dsl)
        self.assertNotIn("ESP32", dsl)
        with self.assertRaisesRegex(DoDslValidationError, "KEYS_INVALID"):
            ProjectRequest.from_dict(request_value(command="rm -rf /"))

    def test_git_credentials_and_unknown_artifacts_are_rejected(self):
        with self.assertRaisesRegex(DoDslValidationError, "CREDENTIALS"):
            ProjectRequest.from_dict(request_value(gitSources=[{"url": "https://user:secret@github.com/org/repo"}]))
        with self.assertRaisesRegex(DoDslValidationError, "ARTIFACT_TARGET"):
            ProjectRequest.from_dict(request_value(artifacts=["execute-shell"]))

    def test_workspace_separates_source_projection_ssot_and_authority(self):
        with tempfile.TemporaryDirectory() as td:
            request = ProjectRequest.from_dict(request_value())
            workspace = ProjectWorkspace(td, request.project_id)
            workspace.initialize(request)
            self.assertTrue((workspace.root / "source/git").is_dir())
            self.assertTrue((workspace.root / "source-md").is_dir())
            self.assertTrue((workspace.root / "source-md-dsl/contracts/trust.dsl").is_file())
            self.assertTrue((workspace.root / ".onlydsl/authority").is_dir())
            self.assertFalse((workspace.root / "SSOT/current").exists())
            self.assertEqual(workspace.request(), request)

    def test_knowledge_index_excludes_execution_time_and_absolute_paths(self):
        document = KnowledgeDocument(
            "doc-1", "urn:dodsl:source:sha256:" + "a" * 64, "web/page.html",
            "sha256:" + "a" * 64, "web/page.html.md", "sha256:" + "b" * 64,
            "text/html", "markitdown", "1.0", True,
        )
        first, first_hash = render_knowledge_index("device-demo", [document])
        second, second_hash = render_knowledge_index("device-demo", [document])
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(first, second)
        self.assertNotIn("GENERATED_AT", first)
        self.assertNotIn("/tmp/", first)

    def test_trust_policy_exposes_domains_without_resolving_conflict(self):
        policy = render_trust_policy(ProjectRequest.from_dict(request_value()))
        self.assertIn("ROLE manufacturer", policy)
        self.assertIn('CAN_DEFINE ["dimensions", "pinout", "electrical", "package"]', policy)
        self.assertNotIn("RESOLVE", policy)


if __name__ == "__main__":
    unittest.main()
