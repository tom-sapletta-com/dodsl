from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from dodsl_contracts.errors import DoDslDependencyError, DoDslValidationError
from dodsl_core.workspace import ProjectWorkspace


class SsotBridge:
    """System-owned bridge to onlyDSL SSOT; it can stage candidates but never promotes them."""

    def __init__(self, command: tuple[str, ...] | None = None):
        configured = os.getenv("ONLYDSL_SSOT_COMMAND", "")
        self.command = command or (tuple(shlex.split(configured)) if configured else (("onlydsl", "ssot") if shutil.which("onlydsl") else ()))

    @property
    def available(self) -> bool:
        return bool(self.command)

    def _run(self, arguments: list[str], *, timeout: int = 300) -> str:
        if not self.command:
            raise DoDslDependencyError("ONLYDSL_SSOT_UNAVAILABLE")
        try:
            result = subprocess.run(
                [*self.command, *arguments], check=False, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DoDslDependencyError(f"ONLYDSL_SSOT_EXECUTION_FAILED:{type(exc).__name__}") from exc
        if result.returncode:
            diagnostic = (result.stdout + " " + result.stderr).strip().replace("\n", " ")[:1200]
            raise DoDslDependencyError(f"ONLYDSL_SSOT_EXIT_{result.returncode}:{diagnostic}")
        return result.stdout

    def initialize(self, workspace: ProjectWorkspace) -> dict[str, Any]:
        if not (workspace.root / "SSOT/manifest.dsl").is_file():
            self._run(["init", str(workspace.root), "--project-id", workspace.project_id,
                       "--project-dsl", str(workspace.root / "project.projectdsl")])
        return self.status(workspace)

    def status(self, workspace: ProjectWorkspace) -> dict[str, Any]:
        return json.loads(self._run(["status", str(workspace.root)]))

    def reconcile(self, workspace: ProjectWorkspace) -> dict[str, Any]:
        self.initialize(workspace)
        root = workspace.root / "source-md-dsl"
        manifest_path = root / "knowledge-manifest.json"
        if not manifest_path.is_file():
            raise DoDslValidationError("KNOWLEDGE_MANIFEST_REQUIRED")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        selected: dict[str, Path] = {
            "sources/knowledge-index.dsl": root / "knowledge-index.dsl",
            "sources/knowledge-manifest.json": manifest_path,
            "intent/project-dodsl.dsl": root / "intent/project-dodsl.dsl",
            "contracts/trust.dsl": root / "contracts/trust.dsl",
            "development/f2md/intent-packs.json": root / "development/f2md/intent-packs.json",
            "development/f2md/compile-report.json": root / "development/f2md/compile-report.json",
        }
        todo_root = root / "development/todo2code"
        for path in sorted(todo_root.glob("*/*")):
            if path.is_file() and path.suffix.lower() in {".json", ".dsl"}:
                selected["development/todo2code/" + path.relative_to(todo_root).as_posix()] = path
        missing = [name for name, path in selected.items() if not path.is_file()]
        if missing:
            raise DoDslValidationError("SSOT_SECTION_MISSING:" + ",".join(missing))
        semantic_hash = str(manifest["semanticHash"])
        candidate_id = "dodsl-" + semantic_hash.split(":", 1)[1][:16] + "-" + uuid.uuid4().hex[:8]
        arguments = ["reconcile", str(workspace.root), "--id", candidate_id]
        for target, source in selected.items():
            arguments.extend(["--section", f"{target}={source}"])
        evidence_uris = tuple(dict.fromkeys(str(item) for item in manifest.get("evidenceUris", [])))
        if not evidence_uris:
            raise DoDslValidationError("SSOT_EVIDENCE_REQUIRED")
        for uri in evidence_uris:
            arguments.extend(["--evidence", uri])
        diff = self._run(arguments)
        return {
            "schema": "dodsl-ssot-candidate/v1", "candidateId": candidate_id,
            "semanticHash": semantic_hash, "evidenceUris": list(evidence_uris), "diff": diff,
            "promotion": "not_performed",
        }
