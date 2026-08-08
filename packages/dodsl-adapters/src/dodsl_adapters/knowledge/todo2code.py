from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dodsl_contracts.development_evidence import create_development_evidence, render_development_evidence
from dodsl_contracts.errors import DoDslDependencyError
from dodsl_core.io import atomic_write_json, atomic_write_text, canonical_hash

EXECUTION_KEYS = {
    "generatedAt", "createdAt", "startedAt", "completedAt", "durationMs", "runId", "runDirectory",
    "graphPath", "diagnosticsPath", "summaryPath", "eventLogPath",
}

SEMANTIC_CONFIGURATION_KEYS = {
    "nlMode", "markdownMode", "communicationMode", "gitCommitCount", "maxFileBytes",
    "documentChunkChars", "documentMaxChunks", "documentRecordsPerChunk",
    "taskSynthesisMode", "includeCommunication", "projectDirectory",
    "documentPatterns", "documentExcludes",
}


def _semantic_projection(value: Any, workspace_root: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_projection(child, workspace_root)
            for key, child in sorted(value.items()) if key not in EXECUTION_KEYS
        }
    if isinstance(value, list):
        return [_semantic_projection(child, workspace_root) for child in value]
    if isinstance(value, str):
        root = str(workspace_root)
        return value.replace(root, "dodsl://workspace") if root in value else value
    return value


def _content_uri(role: str, value: Any) -> str:
    digest = canonical_hash(value).split(":", 1)[1]
    return f"urn:dodsl:todo2code-{role}:sha256:{digest}"


def _semantic_manifest(manifest: dict[str, Any], *, graph_fingerprint: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    configuration = manifest.get("configuration") if isinstance(manifest.get("configuration"), dict) else {}
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    stage_projection: dict[str, Any] = {}
    for name, raw in sorted(stages.items()):
        if not isinstance(raw, dict):
            continue
        reason = raw.get("reason") if isinstance(raw.get("reason"), dict) else {}
        stage_projection[name] = {
            "status": raw.get("status"), "requestedMode": raw.get("requestedMode"),
            "effectiveMode": raw.get("effectiveMode"), "degraded": bool(raw.get("degraded")),
            "recordCount": raw.get("recordCount", 0), "warningCount": raw.get("warningCount", 0),
            "reasonCode": reason.get("code"),
        }
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    llm = manifest.get("llm") if isinstance(manifest.get("llm"), dict) else {}
    return {
        "schema": "dodsl.todo2code-semantic-manifest/v1",
        "sourceSchema": manifest.get("schemaVersion"),
        "status": manifest.get("status"),
        "runtime": {"name": runtime.get("name"), "version": runtime.get("version")},
        "configuration": {key: configuration[key] for key in sorted(SEMANTIC_CONFIGURATION_KEYS) if key in configuration},
        "stages": stage_projection,
        "llmUsed": any(value is True for value in llm.values()),
        "warnings": sorted(str(item) for item in manifest.get("warnings", []) if isinstance(item, str)),
        "graphFingerprint": graph_fingerprint,
        "artifacts": artifacts,
        "authorityEffect": "none",
        "mutationEffect": "none",
    }


def _artifact_path(raw: Any, *, runtime_output: Path, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise DoDslDependencyError(f"TODO2CODE_{label}_PATH_MISSING")
    path = Path(raw).resolve()
    try:
        path.relative_to(runtime_output.resolve())
    except ValueError as exc:
        raise DoDslDependencyError(f"TODO2CODE_{label}_PATH_OUTSIDE_RUNTIME") from exc
    if not path.is_file():
        raise DoDslDependencyError(f"TODO2CODE_{label}_MISSING")
    return path


class Todo2CodeAdapter:
    """Fixed deterministic todo2code process adapter; it never accepts a command from model output."""

    def __init__(self, command: tuple[str, ...] | None = None):
        configured = os.getenv("TODO2CODE_COMMAND", "")
        self.command = command if command is not None else (tuple(shlex.split(configured)) if configured else (("t2c",) if shutil.which("t2c") else ()))

    @property
    def available(self) -> bool:
        return bool(self.command)

    def compile_repository(
        self, repository: Path, output: Path, *, workspace_root: Path, project_id: str,
    ) -> dict[str, Any]:
        if not self.command:
            return {"available": False, "status": "skipped", "code": "TODO2CODE_UNAVAILABLE"}
        runtime_output = output.parent / ("." + output.name + ".runtime")
        if runtime_output.exists():
            shutil.rmtree(runtime_output)
        runtime_output.mkdir(parents=True)
        args = [
            *self.command, "pipeline", str(repository),
            "--nl-mode", "deterministic", "--markdown-mode", "deterministic",
            "--communication-mode", "deterministic", "--no-docs-llm", "--no-summary-llm",
            "--no-communication", "--docs", "README.md,docs/**/*.md,project/**/*.md",
            "--out", str(runtime_output),
        ]
        try:
            result = subprocess.run(
                args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=900, env={**os.environ, "OPENROUTER_API_KEY": "", "T2C_NL_MODE": "deterministic",
                                  "T2C_MARKDOWN_MODE": "deterministic", "T2C_COMMUNICATION_MODE": "deterministic"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DoDslDependencyError(f"TODO2CODE_EXECUTION_FAILED:{type(exc).__name__}") from exc
        if result.returncode:
            diagnostic = result.stderr.strip().replace("\n", " ")[:1000]
            raise DoDslDependencyError(f"TODO2CODE_EXIT_{result.returncode}:{diagnostic}")
        try:
            envelope = json.loads(result.stdout)
            graph_path = _artifact_path(envelope.get("graphPath"), runtime_output=runtime_output, label="GRAPH")
            diagnostics_path = _artifact_path(envelope.get("diagnosticsPath"), runtime_output=runtime_output, label="DIAGNOSTICS")
            graph = _semantic_projection(json.loads(graph_path.read_text(encoding="utf-8")), workspace_root)
            diagnostics = _semantic_projection(json.loads(diagnostics_path.read_text(encoding="utf-8")), workspace_root)
            manifest = envelope.get("manifest")
            if not isinstance(manifest, dict):
                manifest_path = _artifact_path(str(graph_path.parent / "manifest.json"), runtime_output=runtime_output, label="MANIFEST")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_manifest = json.loads((repository.parent / "manifest.json").read_text(encoding="utf-8"))
            repository_revision = str(source_manifest["commit"])
            repository_tree = str(source_manifest["tree"])
        except (KeyError, OSError, json.JSONDecodeError, TypeError) as exc:
            raise DoDslDependencyError("TODO2CODE_RESULT_CONTRACT_INVALID") from exc

        graph_fingerprint = canonical_hash(graph)
        graph_uri = _content_uri("graph", graph)
        diagnostics_uri = _content_uri("diagnostics", diagnostics)
        proposal_artifacts: dict[str, Any] = {}
        plans_path_raw = envelope.get("codeChangePlansPath")
        if isinstance(plans_path_raw, str) and plans_path_raw:
            try:
                plans_path = _artifact_path(plans_path_raw, runtime_output=runtime_output, label="CODE_CHANGE_PLANS")
                plans = _semantic_projection(json.loads(plans_path.read_text(encoding="utf-8")), workspace_root)
            except (OSError, json.JSONDecodeError) as exc:
                raise DoDslDependencyError("TODO2CODE_CODE_CHANGE_PLANS_INVALID") from exc
            atomic_write_json(output / "code-change-plans.json", plans)
            proposal_artifacts["codeChangePlans"] = {
                "uri": _content_uri("code-change-plans", plans),
                "schema": plans.get("schemaVersion") if isinstance(plans, dict) else None,
                "execution": "not_performed", "authorityEffect": "none",
            }

        semantic_manifest = _semantic_manifest(
            manifest, graph_fingerprint=graph_fingerprint, artifacts=proposal_artifacts,
        )
        manifest_uri = _content_uri("manifest", semantic_manifest)
        counts = diagnostics.get("counts") if isinstance(diagnostics, dict) and isinstance(diagnostics.get("counts"), dict) else {}
        try:
            blocking = int(counts.get("blocking", 0))
            warnings = int(counts.get("warning", 0))
        except (TypeError, ValueError) as exc:
            raise DoDslDependencyError("TODO2CODE_DIAGNOSTIC_COUNTS_INVALID") from exc
        assessment = "incomplete" if blocking else "accepted"
        runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
        producer_version = str(runtime.get("version", "unknown"))
        repository_id = repository.parent.name
        bundle_id = f"development-{repository_id[:120]}-{graph_fingerprint[-12:]}"
        bundle = create_development_evidence(
            bundle_id=bundle_id, project_id=project_id, repository_id=repository_id,
            repository_revision=repository_revision, repository_tree=repository_tree,
            producer_version=producer_version, graph_uri=graph_uri,
            diagnostics_uri=diagnostics_uri, manifest_uri=manifest_uri,
            graph_fingerprint=graph_fingerprint, assessment=assessment,
            blocking_diagnostics=blocking, warning_diagnostics=warnings,
        )
        output.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output / "intent.graph.json", graph)
        atomic_write_json(output / "diagnostics.json", diagnostics)
        atomic_write_json(output / "manifest.semantic.json", semantic_manifest)
        atomic_write_text(output / "development-evidence.dsl", render_development_evidence(bundle) + "\n")
        execution_hash = canonical_hash(manifest)
        shutil.rmtree(runtime_output)
        return {
            "available": True, "status": "compiled", "semanticHash": bundle.semantic_hash,
            "executionHash": execution_hash, "evidenceUri": bundle.evidence_uri,
            "assessment": assessment, "blockingDiagnostics": blocking,
            "warningDiagnostics": warnings, "repositoryRevision": repository_revision,
            "repositoryTree": repository_tree, "producerVersion": producer_version,
            "graphFingerprint": graph_fingerprint, "graphUri": graph_uri,
            "diagnosticsUri": diagnostics_uri, "manifestUri": manifest_uri,
        }
