from __future__ import annotations

import json
import os
import shutil
import uuid
from typing import Any

from dodsl_contracts.artifact_intent import ArtifactIntentProposal
from dodsl_contracts.errors import DoDslConflict, DoDslValidationError
from dodsl_core.io import atomic_write_json, atomic_write_text, utc_now
from dodsl_core.workspace import ProjectWorkspace

from . import __version__


def _render_intent(proposal: ArtifactIntentProposal) -> str:
    rows = [
        f"ARTIFACT_INTENT {proposal.candidate_id}",
        "SCHEMA dodsl.artifact-intent/v1",
        "STATUS proposed",
        f"PROJECT {proposal.project_id}",
        f"BASE_KNOWLEDGE_HASH {proposal.base_knowledge_hash}",
        f"PRODUCER_KIND {proposal.producer.kind}",
        "PRODUCER_NAME " + json.dumps(proposal.producer.name, ensure_ascii=False),
    ]
    if proposal.producer.model:
        rows.extend([
            "PRODUCER_MODEL " + json.dumps(proposal.producer.model),
            f"PRODUCER_RESPONSE_HASH {proposal.producer.response_hash}",
        ])
    rows.extend(f"OUTPUT {item}" for item in proposal.outputs)
    for requirement in proposal.requirements:
        rows.extend([
            f"REQUIREMENT {requirement.requirement_id}",
            f"  KIND {requirement.kind}",
            f"  SUBJECT {requirement.subject}",
            "  CLAIM " + json.dumps(requirement.claim, ensure_ascii=False),
            f"  QUANTITY {requirement.quantity}",
        ])
        rows.extend(f"  REQUIRED_EVIDENCE {field}" for field in requirement.required_evidence)
        for constraint in requirement.constraints:
            rows.append("  CONSTRAINT " + json.dumps(constraint.semantic_dict(), ensure_ascii=False, sort_keys=True))
        rows.append("END_REQUIREMENT")
    rows.extend([f"SEMANTIC_HASH {proposal.semantic_hash}", "END_ARTIFACT_INTENT"])
    return "\n".join(rows) + "\n"


def _render_gaps(proposal: ArtifactIntentProposal) -> tuple[str, list[dict[str, str]]]:
    gaps: list[dict[str, str]] = []
    rows = [f"RESEARCH_GAPS {proposal.candidate_id}", "SCHEMA dodsl.research-gaps/v1"]
    for requirement in proposal.requirements:
        for field in requirement.required_evidence:
            gap_id = f"gap-{requirement.requirement_id}-{field}"
            gaps.append({
                "id": gap_id,
                "requirementId": requirement.requirement_id,
                "subject": requirement.subject,
                "field": field,
                "operation": "research.component.run",
            })
            rows.extend([
                f"RESEARCH_GAP {gap_id}",
                f"  REQUIREMENT {requirement.requirement_id}",
                f"  SUBJECT {requirement.subject}",
                f"  FIELD {field}",
                "  OPERATION research.component.run",
                "  STATUS open",
                "END_RESEARCH_GAP",
            ])
    rows.extend([f"GAPS {len(gaps)}", "END_RESEARCH_GAPS"])
    return "\n".join(rows) + "\n", gaps


def _render_plan(proposal: ArtifactIntentProposal, gaps: list[dict[str, str]]) -> str:
    rows = [
        f"RESEARCH_PLAN {proposal.candidate_id}",
        "SCHEMA dodsl.research-plan/v1",
        f"FROM_ARTIFACT_INTENT {proposal.semantic_hash}",
        "STATUS proposed",
    ]
    for index, gap in enumerate(gaps, 1):
        rows.extend([
            f"STEP research-{index:04d}",
            f"  GAP {gap['id']}",
            f"  OPERATION {gap['operation']}",
            "  EXECUTABLE_URI system-owned",
            "  ACCEPTANCE immutable-evidence-required",
            "END_STEP",
        ])
    rows.extend([f"STEPS {len(gaps)}", "END_RESEARCH_PLAN"])
    return "\n".join(rows) + "\n"


class ArtifactPlanningService:
    def stage(self, workspace: ProjectWorkspace, value: Any) -> dict[str, Any]:
        manifest_path = workspace.root / "source-md-dsl/knowledge-manifest.json"
        if not manifest_path.is_file():
            raise DoDslValidationError("KNOWLEDGE_MANIFEST_REQUIRED_BEFORE_ARTIFACT_INTENT")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        knowledge_hash = manifest.get("semanticHash")
        if not isinstance(knowledge_hash, str):
            raise DoDslValidationError("KNOWLEDGE_SEMANTIC_HASH_REQUIRED")
        proposal = ArtifactIntentProposal.from_dict(
            value, expected_project_id=workspace.project_id, expected_knowledge_hash=knowledge_hash,
        )
        destination = workspace.root / ".dodsl/queue/artifact-intent" / proposal.candidate_id
        if destination.exists():
            existing = json.loads((destination / "proposal.json").read_text(encoding="utf-8"))
            if existing != proposal.semantic_dict():
                raise DoDslConflict("ARTIFACT_CANDIDATE_ID_COLLISION")
            return json.loads((destination / "receipt.json").read_text(encoding="utf-8"))
        staging = destination.parent / ("." + proposal.candidate_id + "." + uuid.uuid4().hex[:8])
        try:
            staging.mkdir(parents=True)
            gaps_dsl, gaps = _render_gaps(proposal)
            atomic_write_json(staging / "proposal.json", proposal.semantic_dict())
            atomic_write_text(staging / "artifact-intent.dsl", _render_intent(proposal))
            atomic_write_text(staging / "research-gaps.dsl", gaps_dsl)
            atomic_write_text(staging / "research-plan.dsl", _render_plan(proposal, gaps))
            receipt = {
                "schema": "dodsl.artifact-planning-receipt/v1",
                "serviceVersion": __version__,
                "projectId": workspace.project_id,
                "candidateId": proposal.candidate_id,
                "semanticHash": proposal.semantic_hash,
                "baseKnowledgeHash": proposal.base_knowledge_hash,
                "requirements": len(proposal.requirements),
                "researchGaps": len(gaps),
                "status": "proposed",
                "execution": "not_performed",
                "ssotPromotion": "not_performed",
                "recordedAt": utc_now(),
            }
            atomic_write_json(staging / "receipt.json", receipt)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, destination)
            return receipt
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
