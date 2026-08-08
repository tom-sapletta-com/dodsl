from __future__ import annotations

import hmac
import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import __version__
from dodsl_contracts.errors import DoDslConflict, DoDslDependencyError, DoDslError, DoDslValidationError
from dodsl_contracts.model import ProjectRequest

from .service import DoDslService

PROJECT_PATH_RE = re.compile(r"^/v1/projects/([a-z][a-z0-9-]{1,62})(?:/(ingest|compile|reconcile))?$")
ARTIFACT_INTENT_PATH_RE = re.compile(r"^/v1/projects/([a-z][a-z0-9-]{1,62})/artifact-intents$")


class DoDslHandler(BaseHTTPRequestHandler):
    server_version = "doDSL/" + __version__

    @property
    def dodsl(self) -> DoDslService:
        return self.server.dodsl  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        token = os.getenv("DODSL_API_TOKEN", "")
        if not token:
            return True
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        return hmac.compare_digest(supplied, token)

    def _json_body(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise DoDslValidationError("CONTENT_LENGTH_INVALID") from exc
        if length <= 0 or length > 1024 * 1024:
            raise DoDslValidationError("JSON_BODY_SIZE_INVALID")
        return json.loads(self.rfile.read(length))

    def _send(self, status: int, value: Any) -> None:
        body = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self) -> None:
        if not self._authorized():
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "UNAUTHORIZED"})
            return
        if self.command == "GET" and self.path == "/health":
            self._send(HTTPStatus.OK, {
                "ok": True, "version": __version__, "service": "dodsl",
                "boundary": "source-to-candidate-ssot", "modelCommands": "forbidden",
                "ssotPromotion": "forbidden",
            })
            return
        if self.command == "POST" and self.path == "/v1/projects":
            request = ProjectRequest.from_dict(self._json_body())
            self._send(HTTPStatus.CREATED, self.dodsl.create(request))
            return
        artifact_match = ARTIFACT_INTENT_PATH_RE.fullmatch(self.path)
        if self.command == "POST" and artifact_match:
            self._send(
                HTTPStatus.CREATED,
                self.dodsl.plan_artifact(artifact_match.group(1), self._json_body()),
            )
            return
        match = PROJECT_PATH_RE.fullmatch(self.path)
        if not match:
            self._send(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
            return
        project_id, operation = match.groups()
        if self.command == "GET" and not operation:
            self._send(HTTPStatus.OK, self.dodsl.status(project_id))
        elif self.command == "POST" and operation == "ingest":
            self._send(HTTPStatus.OK, self.dodsl.ingest(project_id))
        elif self.command == "POST" and operation == "compile":
            body = self._json_body()
            if not isinstance(body, dict) or set(body) - {"requireTodo2code"}:
                raise DoDslValidationError("COMPILE_BODY_INVALID")
            self._send(HTTPStatus.OK, self.dodsl.compile(project_id, require_todo2code=bool(body.get("requireTodo2code"))))
        elif self.command == "POST" and operation == "reconcile":
            self._send(HTTPStatus.OK, self.dodsl.reconcile(project_id))
        else:
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "METHOD_NOT_ALLOWED"})

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._dispatch()
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._dispatch()
        except Exception as exc:
            self._error(exc)

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, json.JSONDecodeError):
            status = HTTPStatus.BAD_REQUEST
        elif isinstance(exc, DoDslConflict):
            status = HTTPStatus.CONFLICT
        elif isinstance(exc, (DoDslValidationError, DoDslDependencyError)):
            status = HTTPStatus.UNPROCESSABLE_ENTITY
        elif isinstance(exc, DoDslError):
            status = HTTPStatus.BAD_REQUEST
        else:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        message = "INTERNAL_SERVER_ERROR" if status == HTTPStatus.INTERNAL_SERVER_ERROR else str(exc)
        self._send(status, {"error": type(exc).__name__, "message": message})

    def log_message(self, format: str, *args: object) -> None:
        if os.getenv("DODSL_HTTP_LOG", "1") == "1":
            super().log_message(format, *args)


def serve(projects_root: str, host: str = "127.0.0.1", port: int = 8788) -> None:
    server = ThreadingHTTPServer((host, port), DoDslHandler)
    server.dodsl = DoDslService(projects_root)  # type: ignore[attr-defined]
    server.serve_forever()
