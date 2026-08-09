from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from dodsl_contracts.dsl import KnowledgeDocument, render_knowledge_index, render_project_dodsl, render_trust_policy
from dodsl_contracts.errors import DoDslDependencyError, DoDslValidationError
from dodsl_core.io import atomic_write_json, atomic_write_text, canonical_hash, sha256_bytes, utc_now
from dodsl_core.workspace import ProjectWorkspace

from .. import __version__
from .todo2code import Todo2CodeAdapter

SKIP_DIRS = {".git", ".svn", "node_modules", "__pycache__", ".venv", "venv"}


def _walk_primary(root: Path):
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS and not name.startswith("."))
        for name in sorted(filenames):
            if not name.startswith("."):
                yield Path(directory) / name


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    marker = text.find("\n---\n", 4)
    if marker < 0:
        return {}, text
    fields: dict[str, str] = {}
    for line in text[4:marker].splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9]*):\s*(.*)$", line)
        if not match:
            continue
        raw = match.group(2).strip()
        if raw.startswith('"') and raw.endswith('"'):
            try:
                raw = str(json.loads(raw))
            except json.JSONDecodeError:
                pass
        fields[match.group(1)] = raw
    return fields, text[marker + 5:]


def _replace_directory(staging: Path, target: Path) -> None:
    backup = target.parent / ("." + target.name + ".backup." + uuid.uuid4().hex[:8])
    if target.exists():
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _canonicalize_intents(intent_root: Path, markdown_root: Path, project_id: str, content_hashes: dict[str, str]) -> None:
    packs: list[dict[str, Any]] = []
    for path in sorted(intent_root.rglob("*.intent.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        source_path = Path(str(value.get("source", "")))
        try:
            relative = source_path.resolve().relative_to(markdown_root.resolve()).as_posix()
        except (ValueError, OSError):
            relative = path.relative_to(intent_root).as_posix().removesuffix(".intent.json")
        logical = f"dodsl://project/{project_id}/source-md/{relative}"
        content_hash = content_hashes.get(relative, str(value.get("sourceHash", "")))
        value["source"] = logical
        value["sourceHash"] = content_hash.removeprefix("sha256:")
        for record in value.get("records", []):
            if isinstance(record, dict) and isinstance(record.get("source"), dict):
                record["source"]["artifactUri"] = logical
                record["source"]["revisionHash"] = content_hash.removeprefix("sha256:")
                record["source"]["fragment"] = relative
        atomic_write_json(path, value)
        packs.append(value)
    atomic_write_json(intent_root / "intent-packs.json", {
        "schema": "dodsl-intent-packs/v1", "projectId": project_id, "packs": packs,
    })
    report = intent_root / "compile-report.json"
    if report.is_file():
        value = json.loads(report.read_text(encoding="utf-8"))
        value["source"] = f"dodsl://project/{project_id}/source-md"
        value["output"] = f"dodsl://project/{project_id}/source-md-dsl/development/f2md"
        atomic_write_json(report, value)


class KnowledgeCompiler:
    def __init__(self, todo2code: Todo2CodeAdapter | None = None):
        self.todo2code = todo2code or Todo2CodeAdapter()

    def compile(self, workspace: ProjectWorkspace, *, require_todo2code: bool = False) -> dict[str, Any]:
        try:
            from f2md.tree import convert_tree
        except ImportError as exc:
            raise DoDslDependencyError("F2MD_UNAVAILABLE") from exc
        try:
            from f2md.intent_compile import compile_tree, refresh_output_identity
            intent_compiler = "f2md.intent-compiler/v1"
        except ImportError as exc:
            raise DoDslDependencyError("F2MD_INTENT_COMPILER_UNAVAILABLE") from exc
        source = workspace.root / "source"
        if not any(_walk_primary(source)):
            raise DoDslValidationError("SOURCE_TREE_EMPTY")
        run_id = uuid.uuid4().hex
        md_stage = workspace.root / ".dodsl/runtime" / f"source-md-{run_id}"
        dsl_stage = workspace.root / ".dodsl/runtime" / f"source-md-dsl-{run_id}"
        md_stage.mkdir(parents=True)
        dsl_stage.mkdir(parents=True)
        try:
            conversion = convert_tree(str(source), str(md_stage))
            documents: list[KnowledgeDocument] = []
            content_hashes: dict[str, str] = {}
            evidence_uris: list[str] = []
            for raw_path in _walk_primary(source):
                relative = raw_path.relative_to(source).as_posix()
                markdown_relative = relative + ".md"
                markdown_path = md_stage / markdown_relative
                if not markdown_path.is_file():
                    raise DoDslValidationError(f"F2MD_PROJECTION_MISSING:{relative}")
                raw = raw_path.read_bytes()
                source_hash = sha256_bytes(raw)
                fields, body = _frontmatter(markdown_path.read_text(encoding="utf-8"))
                normalized_body = body.replace("\r\n", "\n").rstrip() + "\n"
                content_hash = sha256_bytes(normalized_body.encode("utf-8"))
                content_hashes[markdown_relative] = content_hash
                if raw_path.name == "manifest.json":
                    try:
                        source_manifest = json.loads(raw.decode("utf-8"))
                        if str(source_manifest.get("evidenceUri", "")).startswith("urn:"):
                            evidence_uris.append(str(source_manifest["evidenceUri"]))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        pass
                documents.append(KnowledgeDocument(
                    "doc-" + canonical_hash(relative)[-16:],
                    "urn:dodsl:source:sha256:" + source_hash.split(":", 1)[1],
                    relative, source_hash, markdown_relative, content_hash,
                    fields.get("mediaType", "application/octet-stream"), fields.get("converter", "unknown"),
                    fields.get("converterVersion", "unknown"), fields.get("converted", "false") == "true",
                ))
            index, knowledge_hash = render_knowledge_index(workspace.project_id, documents)
            atomic_write_text(dsl_stage / "knowledge-index.dsl", index)
            request = workspace.request()
            atomic_write_text(dsl_stage / "intent/project-dodsl.dsl", render_project_dodsl(request))
            atomic_write_text(dsl_stage / "contracts/trust.dsl", render_trust_policy(request))
            f2md_intents = dsl_stage / "development/f2md"
            summary = compile_tree(md_stage, f2md_intents, only_english=False)
            summary["compiler"] = intent_compiler
            atomic_write_json(f2md_intents / "compile-report.json", summary)
            if summary["failures"]:
                raise DoDslValidationError("F2MD_INTENT_COMPILE_FAILED")
            _canonicalize_intents(f2md_intents, md_stage, workspace.project_id, content_hashes)
            refresh_output_identity(f2md_intents)

            todo_results: dict[str, Any] = {}
            for repository in sorted((source / "git").glob("*/repository")):
                result = self.todo2code.compile_repository(
                    repository, dsl_stage / "development/todo2code" / repository.parent.name,
                    workspace_root=workspace.root, project_id=workspace.project_id,
                )
                todo_results[repository.parent.name] = result
                if result.get("evidenceUri"):
                    evidence_uris.append(str(result["evidenceUri"]))
            if require_todo2code and (not todo_results or any(not item.get("available") for item in todo_results.values())):
                raise DoDslDependencyError("TODO2CODE_REQUIRED_BUT_UNAVAILABLE")

            semantic_files: dict[str, str] = {}
            for path in sorted(dsl_stage.rglob("*")):
                if path.is_file():
                    semantic_files[path.relative_to(dsl_stage).as_posix()] = sha256_bytes(path.read_bytes())
            semantic_hash = canonical_hash(semantic_files)
            evidence_uris.extend([
                "urn:dodsl:knowledge:sha256:" + knowledge_hash.split(":", 1)[1],
                "urn:dodsl:compile:sha256:" + semantic_hash.split(":", 1)[1],
            ])
            semantic_todo_results = {
                repository: {key: value for key, value in result.items() if key != "executionHash"}
                for repository, result in todo_results.items()
            }
            manifest = {
                "schema": "dodsl-knowledge-manifest/v1", "projectId": workspace.project_id,
                "knowledgeHash": knowledge_hash, "semanticHash": semantic_hash,
                "files": semantic_files, "evidenceUris": sorted(set(evidence_uris)),
                "todo2code": semantic_todo_results,
            }
            atomic_write_json(dsl_stage / "knowledge-manifest.json", manifest)
            receipt = {
                "schema": "dodsl-compile-receipt/v1", "projectId": workspace.project_id,
                "serviceVersion": __version__,
                "completedAt": utc_now(), "semanticHash": semantic_hash,
                "f2md": conversion.to_dict(), "todo2code": todo_results,
            }
            _replace_directory(md_stage, workspace.root / "source-md")
            _replace_directory(dsl_stage, workspace.root / "source-md-dsl")
            atomic_write_json(workspace.root / ".dodsl/runtime/latest-compile.json", receipt)
            return {**receipt, "evidenceUris": sorted(set(evidence_uris)), "documents": len(documents)}
        except Exception:
            for path in (md_stage, dsl_stage):
                if path.exists():
                    shutil.rmtree(path)
            raise
