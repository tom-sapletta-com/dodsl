from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dodsl_contracts.dsl import render_project_dodsl, render_trust_policy
from dodsl_contracts.errors import DoDslConflict, DoDslValidationError
from dodsl_contracts.model import PROJECT_ID_RE, ProjectRequest

from .io import atomic_write_json, atomic_write_text, canonical_hash, utc_now


class ProjectWorkspace:
    def __init__(self, projects_root: str | Path, project_id: str):
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise DoDslValidationError("PROJECT_ID_INVALID")
        self.projects_root = Path(projects_root).resolve()
        self.root = (self.projects_root / project_id).resolve()
        if self.root.parent != self.projects_root:
            raise DoDslValidationError("PROJECT_PATH_ESCAPE")
        self.project_id = project_id

    @property
    def request_path(self) -> Path:
        return self.root / ".dodsl/request.json"

    def initialize(self, request: ProjectRequest) -> None:
        if request.project_id != self.project_id:
            raise DoDslValidationError("PROJECT_REQUEST_ID_MISMATCH")
        self.projects_root.mkdir(parents=True, exist_ok=True)
        if self.request_path.exists():
            existing = json.loads(self.request_path.read_text(encoding="utf-8"))
            if canonical_hash(existing["request"]) != canonical_hash(request.semantic_dict()):
                raise DoDslConflict("PROJECT_ALREADY_EXISTS_WITH_DIFFERENT_REQUEST")
            return
        for relative in (
            "source/git", "source/web", "source/uploads", "source-md", "source-md-dsl/code",
            "source-md-dsl/documentation", "source-md-dsl/geometry", "source-md-dsl/electronics",
            "source-md-dsl/intent", "source-md-dsl/contracts", "artifact/pcb", "artifact/cad", "artifact/print",
            "artifact/digital-twin", "artifact/docs", ".dodsl/locks", ".dodsl/runtime",
            ".dodsl/queue/artifact-intent",
            ".onlydsl/authority/grants", ".onlydsl/cache", ".onlydsl/queue", ".onlydsl/runtime",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.request_path, {
            "schema": "dodsl-request-envelope/v1", "createdAt": utc_now(),
            "requestHash": canonical_hash(request.semantic_dict()), "request": request.semantic_dict(),
        })
        atomic_write_text(self.root / "project.projectdsl", render_project_dodsl(request))
        atomic_write_text(self.root / "source-md-dsl/intent/project-dodsl.dsl", render_project_dodsl(request))
        atomic_write_text(self.root / "source-md-dsl/contracts/trust.dsl", render_trust_policy(request))
        if request.request_text:
            atomic_write_text(self.root / "source/uploads/request.md", request.request_text.rstrip() + "\n")
        atomic_write_text(
            self.root / ".gitignore",
            ".dodsl/runtime/\n.dodsl/queue/\n.onlydsl/cache/\n.onlydsl/queue/\n.onlydsl/runtime/\n",
        )

    def request(self) -> ProjectRequest:
        if not self.request_path.is_file():
            raise DoDslValidationError("PROJECT_NOT_INITIALIZED")
        return ProjectRequest.from_dict(json.loads(self.request_path.read_text(encoding="utf-8"))["request"])

    @contextmanager
    def writer_lock(self) -> Iterator[None]:
        lock = self.root / ".dodsl/locks/workspace.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DoDslConflict("DODSL_PROJECT_WRITER_ALREADY_ACTIVE") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
