from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dodsl.io import atomic_write_json
from dodsl.server import DoDslHandler
from dodsl.service import DoDslService


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DoDslHandler)
        self.server.dodsl = DoDslService(self.temporary.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temporary.cleanup()

    def test_health_declares_non_executing_boundary(self):
        with urlopen(self.base + "/health") as response:
            value = json.load(response)
        self.assertTrue(value["ok"])
        self.assertEqual(value["modelCommands"], "forbidden")
        self.assertEqual(value["ssotPromotion"], "forbidden")

    def test_create_project_accepts_explicit_contract_and_rejects_extra_command(self):
        value = {
            "schema": "dodsl-request/v1", "projectId": "api-demo", "title": "API Demo",
            "gitSources": [], "webSources": [], "artifacts": ["ssot"],
        }
        request = Request(self.base + "/v1/projects", method="POST", data=json.dumps(value).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            created = json.load(response)
        self.assertEqual(created["projectId"], "api-demo")
        value["command"] = "echo model-output"
        invalid = Request(self.base + "/v1/projects", method="POST", data=json.dumps(value).encode(), headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(invalid)
        self.assertEqual(caught.exception.code, 422)

    def test_artifact_intent_endpoint_only_stages_typed_candidate(self):
        request_value = {
            "schema": "dodsl-request/v1", "projectId": "api-plan", "title": "API Plan",
            "gitSources": [], "webSources": [], "artifacts": ["ssot", "pcb"],
        }
        create = Request(
            self.base + "/v1/projects", method="POST", data=json.dumps(request_value).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(create):
            pass
        knowledge_hash = "sha256:" + "d" * 64
        workspace = self.server.dodsl.workspace("api-plan")
        atomic_write_json(workspace.root / "source-md-dsl/knowledge-manifest.json", {
            "schema": "dodsl-knowledge-manifest/v1", "projectId": "api-plan",
            "semanticHash": knowledge_hash,
        })
        proposal = {
            "schema": "dodsl.artifact-intent-proposal/v1", "projectId": "api-plan",
            "baseKnowledgeHash": knowledge_hash, "outputs": ["pcb"],
            "producer": {"kind": "human", "name": "owner"},
            "requirements": [{
                "id": "controller", "kind": "component", "subject": "controller",
                "claim": "Documented controller", "requiredEvidence": ["datasheet", "pinout"],
            }],
        }
        stage = Request(
            self.base + "/v1/projects/api-plan/artifact-intents", method="POST",
            data=json.dumps(proposal).encode(), headers={"Content-Type": "application/json"},
        )
        with urlopen(stage) as response:
            receipt = json.load(response)
        self.assertEqual(response.status, 201)
        self.assertEqual(receipt["execution"], "not_performed")
        self.assertEqual(receipt["researchGaps"], 2)
        status = self.server.dodsl.status("api-plan")
        self.assertEqual(status["lastIteration"]["stage"], "artifact_intent_planned")


if __name__ == "__main__":
    unittest.main()
