from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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


if __name__ == "__main__":
    unittest.main()
