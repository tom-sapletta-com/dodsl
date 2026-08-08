from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dodsl_adapters import GitSnapshotter, KnowledgeCompiler, SsotBridge, UploadImporter, WebSnapshotter
from dodsl_contracts.model import ProjectRequest
from dodsl_core.io import atomic_write_json, utc_now
from dodsl_core.ports import (
    ArtifactPlanningPort,
    GitSnapshotPort,
    KnowledgeCompilerPort,
    SsotPort,
    UploadPort,
    WebSnapshotPort,
)
from dodsl_core.workspace import ProjectWorkspace
from dodsl_planning import ArtifactPlanningService

from . import __version__


class DoDslService:
    def __init__(
        self, projects_root: str | Path, *, git: GitSnapshotPort | None = None,
        web: WebSnapshotPort | None = None, uploads: UploadPort | None = None,
        compiler: KnowledgeCompilerPort | None = None, ssot: SsotPort | None = None,
        planning: ArtifactPlanningPort | None = None,
    ):
        self.projects_root = Path(projects_root).resolve()
        self.git = git or GitSnapshotter()
        self.web = web or WebSnapshotter()
        self.uploads = uploads or UploadImporter()
        self.compiler = compiler or KnowledgeCompiler()
        self.ssot = ssot or SsotBridge()
        self.planning = planning or ArtifactPlanningService()

    def workspace(self, project_id: str) -> ProjectWorkspace:
        return ProjectWorkspace(self.projects_root, project_id)

    def create(self, request: ProjectRequest) -> dict[str, Any]:
        workspace = self.workspace(request.project_id)
        workspace.initialize(request)
        return self.status(request.project_id)

    def ingest(self, project_id: str) -> dict[str, Any]:
        workspace = self.workspace(project_id)
        request = workspace.request()
        with workspace.writer_lock():
            git_results = [self.git.capture(workspace, item) for item in request.git_sources]
            web_results = [self.web.capture(workspace, item) for item in request.web_sources]
            receipt = {
                "schema": "dodsl-intake-receipt/v1", "projectId": project_id,
                "serviceVersion": __version__,
                "completedAt": utc_now(), "git": git_results, "web": web_results,
            }
            atomic_write_json(workspace.root / ".dodsl/runtime/latest-intake.json", receipt)
            return receipt

    def import_file(self, project_id: str, source: str | Path, *, trust_role: str = "customer") -> dict[str, Any]:
        workspace = self.workspace(project_id)
        workspace.request()
        with workspace.writer_lock():
            return self.uploads.capture(workspace, source, trust_role=trust_role)

    def compile(self, project_id: str, *, require_todo2code: bool = False) -> dict[str, Any]:
        workspace = self.workspace(project_id)
        workspace.request()
        with workspace.writer_lock():
            return self.compiler.compile(workspace, require_todo2code=require_todo2code)

    def reconcile(self, project_id: str) -> dict[str, Any]:
        workspace = self.workspace(project_id)
        workspace.request()
        with workspace.writer_lock():
            result = self.ssot.reconcile(workspace)
            recorded = {**result, "serviceVersion": __version__, "recordedAt": utc_now()}
            atomic_write_json(workspace.root / ".dodsl/runtime/latest-ssot-candidate.json", recorded)
            return recorded

    def plan_artifact(self, project_id: str, proposal: Any) -> dict[str, Any]:
        workspace = self.workspace(project_id)
        workspace.request()
        with workspace.writer_lock():
            receipt = self.planning.stage(workspace, proposal)
            atomic_write_json(workspace.root / ".dodsl/runtime/latest-artifact-plan.json", receipt)
            return receipt

    def run(self, request: ProjectRequest, *, require_todo2code: bool = False, reconcile: bool = True) -> dict[str, Any]:
        self.create(request)
        intake = self.ingest(request.project_id)
        compile_result = self.compile(request.project_id, require_todo2code=require_todo2code)
        candidate = self.reconcile(request.project_id) if reconcile else None
        return {
            "schema": "dodsl-run/v1", "projectId": request.project_id,
            "intake": intake, "compile": compile_result, "ssotCandidate": candidate,
        }

    def status(self, project_id: str) -> dict[str, Any]:
        workspace = self.workspace(project_id)
        request = workspace.request()
        source_files = sum(1 for path in (workspace.root / "source").rglob("*") if path.is_file() and ".git" not in path.parts)
        markdown_files = sum(1 for path in (workspace.root / "source-md").rglob("*.md") if path.is_file())
        dsl_files = sum(1 for path in (workspace.root / "source-md-dsl").rglob("*") if path.is_file())
        ssot_status: dict[str, Any] | None = None
        if (workspace.root / "SSOT/manifest.dsl").is_file() and self.ssot.available:
            ssot_status = self.ssot.status(workspace)
        iterations: list[dict[str, Any]] = []
        runtime = workspace.root / ".dodsl/runtime"
        for stage, filename, time_field in (
            ("sources_captured", "latest-intake.json", "completedAt"),
            ("knowledge_compiled", "latest-compile.json", "completedAt"),
            ("ssot_candidate_validated", "latest-ssot-candidate.json", "recordedAt"),
            ("artifact_intent_planned", "latest-artifact-plan.json", "recordedAt"),
        ):
            path = runtime / filename
            if not path.is_file():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            when = value.get(time_field)
            if isinstance(when, str):
                iterations.append({
                    "stage": stage,
                    "at": when,
                    "semanticHash": value.get("semanticHash"),
                    "candidateId": value.get("candidateId"),
                })
        last_iteration = max(iterations, key=lambda item: item["at"]) if iterations else None
        artifact_candidates = sum(
            1 for path in (workspace.root / ".dodsl/queue/artifact-intent").glob("artifact-*")
            if path.is_dir()
        )
        return {
            "schema": "dodsl-project-status/v1", "projectId": project_id,
            "serviceVersion": __version__, "lastIteration": last_iteration,
            "title": request.title, "workspace": str(workspace.root),
            "sources": source_files, "markdown": markdown_files, "dsl": dsl_files,
            "artifactIntentCandidates": artifact_candidates,
            "interpretation": "waiting_interpretation" if request.request_text else "not_required",
            "ssot": ssot_status,
        }
