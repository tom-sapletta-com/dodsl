from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from dodsl_contracts.model import GitSource, WebSource

from .workspace import ProjectWorkspace


class GitSnapshotPort(Protocol):
    def capture(self, workspace: ProjectWorkspace, source: GitSource) -> dict[str, object]: ...


class WebSnapshotPort(Protocol):
    def capture(self, workspace: ProjectWorkspace, source: WebSource) -> dict[str, object]: ...


class UploadPort(Protocol):
    def capture(self, workspace: ProjectWorkspace, source: str | Path, *, trust_role: str) -> dict[str, Any]: ...


class KnowledgeCompilerPort(Protocol):
    def compile(self, workspace: ProjectWorkspace, *, require_todo2code: bool = False) -> dict[str, Any]: ...


class SsotPort(Protocol):
    @property
    def available(self) -> bool: ...

    def reconcile(self, workspace: ProjectWorkspace) -> dict[str, Any]: ...

    def status(self, workspace: ProjectWorkspace) -> dict[str, Any]: ...


class ArtifactPlanningPort(Protocol):
    def stage(self, workspace: ProjectWorkspace, value: Any) -> dict[str, Any]: ...
