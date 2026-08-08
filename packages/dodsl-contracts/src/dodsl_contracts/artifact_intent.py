from __future__ import annotations

import re
import math
from dataclasses import dataclass
from typing import Any

from .errors import DoDslValidationError
from .hashing import canonical_hash
from .model import ARTIFACT_TARGETS

ID_RE = re.compile(r"[a-z][a-z0-9-]{1,62}")
HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
REQUIREMENT_KINDS = {
    "component", "electrical", "geometry", "software", "manufacturing", "documentation",
}
EVIDENCE_FIELDS = {
    "manufacturer", "mpn", "lifecycle", "datasheet", "supply-range", "package", "pinout",
    "footprint", "dimensions", "symbol", "3d-model", "behavior", "source-code", "license",
    "manufacturing-profile",
}
OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "max", "min"}
PRODUCER_KINDS = {"human", "llm"}


def _strict(value: dict[str, Any], allowed: set[str], required: set[str], context: str) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        raise DoDslValidationError(
            f"{context}_KEYS_INVALID:unknown={sorted(unknown)}:missing={sorted(missing)}"
        )


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise DoDslValidationError(f"{context}_ID_INVALID")
    return value


def _text(value: Any, context: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DoDslValidationError(f"{context}_TEXT_INVALID")
    return value.strip()


def _scalar(value: Any, context: str) -> str | int | float | bool | list[str | int | float | bool]:
    if isinstance(value, float) and not math.isfinite(value):
        raise DoDslValidationError(f"{context}_VALUE_INVALID")
    if isinstance(value, (str, int, float, bool)) and not isinstance(value, type(None)):
        return value
    if isinstance(value, list) and value and len(value) <= 50 and all(
        isinstance(item, (str, int, float, bool))
        and (not isinstance(item, float) or math.isfinite(item))
        for item in value
    ):
        return value
    raise DoDslValidationError(f"{context}_VALUE_INVALID")


@dataclass(frozen=True, slots=True)
class Producer:
    kind: str
    name: str
    model: str | None = None
    response_hash: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> "Producer":
        if not isinstance(value, dict):
            raise DoDslValidationError("ARTIFACT_PRODUCER_OBJECT_REQUIRED")
        _strict(value, {"kind", "name", "model", "responseHash"}, {"kind", "name"}, "ARTIFACT_PRODUCER")
        kind = str(value["kind"])
        if kind not in PRODUCER_KINDS:
            raise DoDslValidationError("ARTIFACT_PRODUCER_KIND_INVALID")
        name = _text(value["name"], "ARTIFACT_PRODUCER", 200)
        model = value.get("model")
        response_hash = value.get("responseHash")
        if kind == "llm":
            if not isinstance(model, str) or not model.strip() or not isinstance(response_hash, str) or not HASH_RE.fullmatch(response_hash):
                raise DoDslValidationError("LLM_PRODUCER_PROVENANCE_REQUIRED")
        elif model is not None or response_hash is not None:
            raise DoDslValidationError("HUMAN_PRODUCER_MODEL_FIELDS_FORBIDDEN")
        return cls(kind, name, model, response_hash)

    def semantic_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "model": self.model, "responseHash": self.response_hash}


@dataclass(frozen=True, slots=True)
class Constraint:
    parameter: str
    operator: str
    value: str | int | float | bool | list[str | int | float | bool]
    unit: str

    @classmethod
    def from_dict(cls, value: Any) -> "Constraint":
        if not isinstance(value, dict):
            raise DoDslValidationError("ARTIFACT_CONSTRAINT_OBJECT_REQUIRED")
        _strict(value, {"parameter", "operator", "value", "unit"}, {"parameter", "operator", "value", "unit"}, "ARTIFACT_CONSTRAINT")
        parameter = _identifier(value["parameter"], "ARTIFACT_CONSTRAINT_PARAMETER")
        operator = str(value["operator"])
        if operator not in OPERATORS:
            raise DoDslValidationError("ARTIFACT_CONSTRAINT_OPERATOR_INVALID")
        unit = _text(value["unit"], "ARTIFACT_CONSTRAINT_UNIT", 32)
        return cls(parameter, operator, _scalar(value["value"], "ARTIFACT_CONSTRAINT"), unit)

    def semantic_dict(self) -> dict[str, Any]:
        return {"parameter": self.parameter, "operator": self.operator, "value": self.value, "unit": self.unit}


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    requirement_id: str
    kind: str
    subject: str
    claim: str
    quantity: int
    required_evidence: tuple[str, ...]
    constraints: tuple[Constraint, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "CapabilityRequirement":
        if not isinstance(value, dict):
            raise DoDslValidationError("ARTIFACT_REQUIREMENT_OBJECT_REQUIRED")
        allowed = {"id", "kind", "subject", "claim", "quantity", "requiredEvidence", "constraints"}
        _strict(value, allowed, {"id", "kind", "subject", "claim", "requiredEvidence"}, "ARTIFACT_REQUIREMENT")
        kind = str(value["kind"])
        if kind not in REQUIREMENT_KINDS:
            raise DoDslValidationError("ARTIFACT_REQUIREMENT_KIND_INVALID")
        evidence = value["requiredEvidence"]
        if not isinstance(evidence, list) or not evidence or len(evidence) > 32:
            raise DoDslValidationError("ARTIFACT_REQUIRED_EVIDENCE_LIST_INVALID")
        fields = tuple(dict.fromkeys(str(item) for item in evidence))
        if any(field not in EVIDENCE_FIELDS for field in fields):
            raise DoDslValidationError("ARTIFACT_REQUIRED_EVIDENCE_FIELD_INVALID")
        quantity = value.get("quantity", 1)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 10_000:
            raise DoDslValidationError("ARTIFACT_REQUIREMENT_QUANTITY_INVALID")
        raw_constraints = value.get("constraints", [])
        if not isinstance(raw_constraints, list) or len(raw_constraints) > 100:
            raise DoDslValidationError("ARTIFACT_CONSTRAINT_LIST_INVALID")
        return cls(
            _identifier(value["id"], "ARTIFACT_REQUIREMENT"),
            kind,
            _identifier(value["subject"], "ARTIFACT_REQUIREMENT_SUBJECT"),
            _text(value["claim"], "ARTIFACT_REQUIREMENT_CLAIM"),
            quantity,
            fields,
            tuple(Constraint.from_dict(item) for item in raw_constraints),
        )

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "id": self.requirement_id,
            "kind": self.kind,
            "subject": self.subject,
            "claim": self.claim,
            "quantity": self.quantity,
            "requiredEvidence": list(self.required_evidence),
            "constraints": [item.semantic_dict() for item in self.constraints],
        }


@dataclass(frozen=True, slots=True)
class ArtifactIntentProposal:
    project_id: str
    base_knowledge_hash: str
    outputs: tuple[str, ...]
    requirements: tuple[CapabilityRequirement, ...]
    producer: Producer

    @classmethod
    def from_dict(
        cls, value: Any, *, expected_project_id: str | None = None,
        expected_knowledge_hash: str | None = None,
    ) -> "ArtifactIntentProposal":
        if not isinstance(value, dict):
            raise DoDslValidationError("ARTIFACT_INTENT_OBJECT_REQUIRED")
        allowed = {"schema", "projectId", "baseKnowledgeHash", "outputs", "requirements", "producer"}
        _strict(value, allowed, allowed, "ARTIFACT_INTENT")
        if value["schema"] != "dodsl.artifact-intent-proposal/v1":
            raise DoDslValidationError("ARTIFACT_INTENT_SCHEMA_INVALID")
        project_id = _identifier(value["projectId"], "ARTIFACT_PROJECT")
        if expected_project_id is not None and project_id != expected_project_id:
            raise DoDslValidationError("ARTIFACT_PROJECT_ID_MISMATCH")
        knowledge_hash = str(value["baseKnowledgeHash"])
        if not HASH_RE.fullmatch(knowledge_hash):
            raise DoDslValidationError("ARTIFACT_BASE_KNOWLEDGE_HASH_INVALID")
        if expected_knowledge_hash is not None and knowledge_hash != expected_knowledge_hash:
            raise DoDslValidationError("ARTIFACT_BASE_KNOWLEDGE_STALE")
        outputs = value["outputs"]
        requirements = value["requirements"]
        if not isinstance(outputs, list) or not outputs or not isinstance(requirements, list) or not requirements:
            raise DoDslValidationError("ARTIFACT_OUTPUT_OR_REQUIREMENT_LIST_INVALID")
        normalized_outputs = tuple(dict.fromkeys(str(item) for item in outputs))
        if any(item not in ARTIFACT_TARGETS for item in normalized_outputs):
            raise DoDslValidationError("ARTIFACT_OUTPUT_INVALID")
        normalized_requirements = tuple(CapabilityRequirement.from_dict(item) for item in requirements)
        identifiers = [item.requirement_id for item in normalized_requirements]
        if len(identifiers) != len(set(identifiers)):
            raise DoDslValidationError("ARTIFACT_REQUIREMENT_ID_DUPLICATE")
        return cls(
            project_id, knowledge_hash, normalized_outputs, normalized_requirements,
            Producer.from_dict(value["producer"]),
        )

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "schema": "dodsl.artifact-intent-proposal/v1",
            "projectId": self.project_id,
            "baseKnowledgeHash": self.base_knowledge_hash,
            "outputs": list(self.outputs),
            "requirements": [item.semantic_dict() for item in self.requirements],
            "producer": self.producer.semantic_dict(),
        }

    @property
    def semantic_hash(self) -> str:
        return canonical_hash(self.semantic_dict())

    @property
    def candidate_id(self) -> str:
        return "artifact-" + self.semantic_hash.split(":", 1)[1][:20]
