from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dodsl_contracts.errors import DoDslConflict, DoDslDependencyError, DoDslValidationError
from dodsl_contracts.model import GitSource
from dodsl_core.io import atomic_write_json, canonical_hash, utc_now
from dodsl_core.workspace import ProjectWorkspace


def _slug(source: GitSource) -> str:
    parsed = urlsplit(source.url)
    base = Path(unquote(parsed.path)).name.removesuffix(".git") or "repository"
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-.").lower() or "repository"
    suffix = canonical_hash({"url": source.url, "ref": source.ref})[-10:]
    return f"{clean}-{suffix}"


class GitSnapshotter:
    def __init__(self, *, allow_local: bool | None = None, git_binary: str = "git"):
        self.allow_local = (os.getenv("DODSL_ALLOW_LOCAL_GIT") == "1") if allow_local is None else allow_local
        self.git_binary = git_binary

    def _validate_url(self, value: str) -> None:
        parsed = urlsplit(value)
        if parsed.scheme == "file":
            if not self.allow_local:
                raise DoDslValidationError("GIT_LOCAL_SOURCE_FORBIDDEN")
            path = Path(unquote(parsed.path)).resolve()
            if not path.is_dir():
                raise DoDslValidationError("GIT_LOCAL_SOURCE_NOT_FOUND")
            return
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"} or parsed.query:
            raise DoDslValidationError("GIT_GITHUB_HTTPS_REQUIRED")
        if not re.fullmatch(r"/[^/]+/[^/]+(?:\.git)?/?", parsed.path):
            raise DoDslValidationError("GIT_GITHUB_REPOSITORY_PATH_REQUIRED")

    def _run(self, args: list[str], *, cwd: Path | None = None) -> str:
        try:
            result = subprocess.run(
                [self.git_binary, *args], cwd=cwd, check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
                     "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
                     "GIT_LFS_SKIP_SMUDGE": "1"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DoDslDependencyError(f"GIT_EXECUTION_FAILED:{type(exc).__name__}") from exc
        if result.returncode:
            diagnostic = result.stderr.strip().replace("\n", " ")[:600]
            raise DoDslDependencyError(f"GIT_EXIT_{result.returncode}:{diagnostic}")
        return result.stdout.strip()

    def capture(self, workspace: ProjectWorkspace, source: GitSource) -> dict[str, object]:
        self._validate_url(source.url)
        slug = _slug(source)
        destination = workspace.root / "source/git" / slug
        if destination.exists():
            manifest_path = destination / "manifest.json"
            if manifest_path.is_file():
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            raise DoDslConflict(f"GIT_DESTINATION_EXISTS:{slug}")
        staging = workspace.root / "source/git" / ("." + slug + "." + uuid.uuid4().hex[:8])
        repository = staging / "repository"
        staging.mkdir(parents=True)
        try:
            self._run(["clone", "--no-tags", "--", source.url, str(repository)])
            if source.ref:
                self._run(["checkout", "--detach", source.ref], cwd=repository)
            commit = self._run(["rev-parse", "HEAD"], cwd=repository)
            tree = self._run(["rev-parse", "HEAD^{tree}"], cwd=repository)
            branch = self._run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repository)
            origin = self._run(["remote", "get-url", "origin"], cwd=repository)
            submodules = self._run(["submodule", "status", "--recursive"], cwd=repository).splitlines()
            semantic = {
                "schema": "dodsl-git-source/v1", "sourceUrl": source.url,
                "resolvedOrigin": origin, "requestedRef": source.ref, "commit": commit,
                "tree": tree, "branch": branch, "submodules": submodules,
                "trustRole": source.trust_role,
            }
            manifest = {
                **semantic, "capturedAt": utc_now(), "semanticHash": canonical_hash(semantic),
                "evidenceUri": "urn:dodsl:git:sha256:" + canonical_hash(semantic).split(":", 1)[1],
            }
            atomic_write_json(staging / "manifest.json", manifest)
            os.replace(staging, destination)
            return manifest
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
