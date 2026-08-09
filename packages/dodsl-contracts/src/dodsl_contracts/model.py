from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .errors import DoDslValidationError
from .validation import strict_keys

PROJECT_ID_RE = re.compile(r"[a-z][a-z0-9-]{1,62}")
TRUST_ROLES = {"manager", "customer", "manufacturer", "measured", "cad", "documentation", "project", "internet"}
ARTIFACT_TARGETS = {
    "documentation", "ssot", "schematic", "pcb", "pcb-3d", "enclosure",
    "stl", "3mf", "glb", "openusd", "digital-twin", "software",
}


def _url(value: Any, context: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise DoDslValidationError(f"{context}_URL_INVALID")
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http", "file"} or not parsed.path:
        raise DoDslValidationError(f"{context}_URL_INVALID")
    if parsed.username or parsed.password or parsed.fragment:
        raise DoDslValidationError(f"{context}_URL_CREDENTIALS_OR_FRAGMENT_FORBIDDEN")
    return value


@dataclass(frozen=True, slots=True)
class GitSource:
    url: str
    ref: str | None = None
    trust_role: str = "project"

    @classmethod
    def from_dict(cls, value: Any) -> "GitSource":
        if not isinstance(value, dict):
            raise DoDslValidationError("GIT_SOURCE_OBJECT_REQUIRED")
        strict_keys(value, {"url", "ref", "trustRole"}, {"url"}, "GIT_SOURCE")
        role = str(value.get("trustRole", "project"))
        if role not in TRUST_ROLES:
            raise DoDslValidationError("GIT_SOURCE_TRUST_ROLE_INVALID")
        ref = value.get("ref")
        if ref is not None and (not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", ref) or ".." in ref):
            raise DoDslValidationError("GIT_SOURCE_REF_INVALID")
        return cls(_url(value["url"], "GIT_SOURCE"), ref, role)


@dataclass(frozen=True, slots=True)
class WebSource:
    url: str
    trust_role: str = "internet"
    method: str = "http"

    @classmethod
    def from_dict(cls, value: Any) -> "WebSource":
        if not isinstance(value, dict):
            raise DoDslValidationError("WEB_SOURCE_OBJECT_REQUIRED")
        strict_keys(value, {"url", "trustRole", "method"}, {"url"}, "WEB_SOURCE")
        role = str(value.get("trustRole", "internet"))
        method = str(value.get("method", "http"))
        if role not in TRUST_ROLES or method not in {"http", "playwright"}:
            raise DoDslValidationError("WEB_SOURCE_POLICY_INVALID")
        url = _url(value["url"], "WEB_SOURCE")
        if urlsplit(url).scheme not in {"http", "https"}:
            raise DoDslValidationError("WEB_SOURCE_HTTP_REQUIRED")
        return cls(url, role, method)


@dataclass(frozen=True, slots=True)
class ProjectRequest:
    project_id: str
    title: str
    git_sources: tuple[GitSource, ...]
    web_sources: tuple[WebSource, ...]
    artifacts: tuple[str, ...]
    request_text: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> "ProjectRequest":
        if not isinstance(value, dict):
            raise DoDslValidationError("PROJECT_REQUEST_OBJECT_REQUIRED")
        allowed = {"schema", "projectId", "title", "gitSources", "webSources", "artifacts", "requestText"}
        strict_keys(value, allowed, {"schema", "projectId", "title"}, "PROJECT_REQUEST")
        if value["schema"] != "dodsl-request/v1":
            raise DoDslValidationError("PROJECT_REQUEST_SCHEMA_INVALID")
        project_id = str(value["projectId"])
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise DoDslValidationError("PROJECT_ID_INVALID")
        title = value["title"]
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise DoDslValidationError("PROJECT_TITLE_INVALID")
        git_values = value.get("gitSources", [])
        web_values = value.get("webSources", [])
        artifacts = value.get("artifacts", ["ssot", "documentation"])
        if not isinstance(git_values, list) or not isinstance(web_values, list) or not isinstance(artifacts, list):
            raise DoDslValidationError("PROJECT_SOURCE_OR_ARTIFACT_LIST_REQUIRED")
        artifact_values = tuple(dict.fromkeys(str(item) for item in artifacts))
        if not artifact_values or any(item not in ARTIFACT_TARGETS for item in artifact_values):
            raise DoDslValidationError("PROJECT_ARTIFACT_TARGET_INVALID")
        request_text = value.get("requestText")
        if request_text is not None and (not isinstance(request_text, str) or not request_text.strip() or len(request_text) > 100_000):
            raise DoDslValidationError("PROJECT_REQUEST_TEXT_INVALID")
        return cls(
            project_id, title.strip(), tuple(GitSource.from_dict(item) for item in git_values),
            tuple(WebSource.from_dict(item) for item in web_values), artifact_values, request_text,
        )

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "schema": "dodsl-request/v1", "projectId": self.project_id, "title": self.title,
            "gitSources": [{"url": item.url, "ref": item.ref, "trustRole": item.trust_role} for item in self.git_sources],
            "webSources": [{"url": item.url, "trustRole": item.trust_role, "method": item.method} for item in self.web_sources],
            "artifacts": list(self.artifacts), "requestText": self.request_text,
        }
