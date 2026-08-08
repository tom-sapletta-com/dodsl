from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from .io import canonical_hash
from .model import ProjectRequest


def render_project_dodsl(request: ProjectRequest) -> str:
    rows = [
        f"PROJECT_DODSL {request.project_id}",
        "SCHEMA dodsl.project/v1",
        "TITLE " + json.dumps(request.title, ensure_ascii=False),
        "REQUEST_HASH " + canonical_hash(request.semantic_dict()),
    ]
    rows.extend("GIT_SOURCE " + json.dumps({"url": item.url, "ref": item.ref, "trustRole": item.trust_role}, ensure_ascii=False, sort_keys=True) for item in request.git_sources)
    rows.extend("WEB_SOURCE " + json.dumps({"url": item.url, "method": item.method, "trustRole": item.trust_role}, ensure_ascii=False, sort_keys=True) for item in request.web_sources)
    rows.extend("ARTIFACT " + item for item in request.artifacts)
    rows.append("INTERPRETATION " + ("waiting_interpretation" if request.request_text else "not_required"))
    rows.append("END_PROJECT_DODSL")
    return "\n".join(rows) + "\n"


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    document_id: str
    source_uri: str
    source_path: str
    source_hash: str
    markdown_path: str
    content_hash: str
    media_type: str
    converter: str
    converter_version: str
    converted: bool

    def semantic_dict(self) -> dict[str, object]:
        return {
            "id": self.document_id, "sourceUri": self.source_uri, "sourcePath": self.source_path,
            "sourceHash": self.source_hash, "markdownPath": self.markdown_path,
            "contentHash": self.content_hash, "mediaType": self.media_type,
            "converter": self.converter, "converterVersion": self.converter_version,
            "converted": self.converted,
        }


def render_knowledge_index(project_id: str, documents: Iterable[KnowledgeDocument]) -> tuple[str, str]:
    ordered = tuple(sorted(documents, key=lambda item: item.source_path))
    semantic_hash = canonical_hash([item.semantic_dict() for item in ordered])
    rows = [f"KNOWLEDGE_INDEX {project_id}", "SCHEMA dodsl.knowledge-index/v1"]
    for item in ordered:
        rows.extend([
            f"DOCUMENT {item.document_id}",
            "  SOURCE_URI " + item.source_uri,
            "  SOURCE_PATH " + json.dumps(item.source_path, ensure_ascii=False),
            "  SOURCE_HASH " + item.source_hash,
            "  MARKDOWN_PATH " + json.dumps(item.markdown_path, ensure_ascii=False),
            "  CONTENT_HASH " + item.content_hash,
            "  MEDIA_TYPE " + json.dumps(item.media_type),
            "  CONVERTER " + json.dumps(item.converter),
            "  CONVERTER_VERSION " + json.dumps(item.converter_version),
            "  STATUS " + ("converted" if item.converted else "stub"),
            "END_DOCUMENT",
        ])
    rows.extend([f"DOCUMENTS {len(ordered)}", "SEMANTIC_HASH " + semantic_hash, "END_KNOWLEDGE_INDEX"])
    return "\n".join(rows) + "\n", semantic_hash


def render_trust_policy(request: ProjectRequest) -> str:
    roles = {item.trust_role for item in (*request.git_sources, *request.web_sources)} | {"project"}
    priorities = {"manager": 100, "measured": 95, "customer": 90, "manufacturer": 90, "cad": 80, "project": 70, "documentation": 60, "internet": 40}
    domains = {"manufacturer": ["dimensions", "pinout", "electrical", "package"], "measured": ["physical-state", "geometry"], "cad": ["design-geometry"], "project": ["code", "documentation", "intent"], "customer": ["requirements", "assets"], "manager": ["intent", "requirements"], "documentation": ["documentation"], "internet": ["research"]}
    rows = ["```trustdsl", f"TRUST_POLICY {request.project_id}"]
    for role in sorted(roles, key=lambda value: (-priorities[value], value)):
        rows.extend([f"ROLE {role}", f"  PRIORITY {priorities[role]}", "  CAN_DEFINE " + json.dumps(domains[role]), "END_ROLE"])
    rows.extend(["END_TRUST_POLICY", "```"])
    return "\n".join(rows) + "\n"
