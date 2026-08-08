from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..errors import DoDslDependencyError
from ..io import atomic_write_json, canonical_hash

EXECUTION_KEYS = {
    "generatedAt", "startedAt", "completedAt", "durationMs", "runId", "runDirectory",
    "graphPath", "diagnosticsPath", "summaryPath", "eventLogPath",
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


class Todo2CodeAdapter:
    """Fixed deterministic todo2code process adapter; it never accepts a command from model output."""

    def __init__(self, command: tuple[str, ...] | None = None):
        configured = os.getenv("TODO2CODE_COMMAND", "")
        self.command = command if command is not None else (tuple(shlex.split(configured)) if configured else (("t2c",) if shutil.which("t2c") else ()))

    @property
    def available(self) -> bool:
        return bool(self.command)

    def compile_repository(self, repository: Path, output: Path, *, workspace_root: Path) -> dict[str, Any]:
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
            graph_path = Path(envelope["graphPath"])
            diagnostics_path = Path(envelope["diagnosticsPath"])
            graph = _semantic_projection(json.loads(graph_path.read_text(encoding="utf-8")), workspace_root)
            diagnostics = _semantic_projection(json.loads(diagnostics_path.read_text(encoding="utf-8")), workspace_root)
        except (KeyError, OSError, json.JSONDecodeError) as exc:
            raise DoDslDependencyError("TODO2CODE_RESULT_CONTRACT_INVALID") from exc
        output.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output / "intent.graph.json", graph)
        atomic_write_json(output / "diagnostics.json", diagnostics)
        semantic_hash = canonical_hash({"graph": graph, "diagnostics": diagnostics})
        shutil.rmtree(runtime_output)
        return {
            "available": True, "status": "compiled", "semanticHash": semantic_hash,
            "evidenceUri": "urn:dodsl:todo2code:sha256:" + semantic_hash.split(":", 1)[1],
        }
