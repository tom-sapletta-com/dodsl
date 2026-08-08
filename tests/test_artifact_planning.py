from __future__ import annotations

import json

import pytest

from dodsl_contracts.errors import DoDslValidationError
from dodsl_contracts.model import ProjectRequest
from dodsl_core.io import atomic_write_json
from dodsl.service import DoDslService


KNOWLEDGE_HASH = "sha256:" + "a" * 64


def proposal(**changes):
    value = {
        "schema": "dodsl.artifact-intent-proposal/v1",
        "projectId": "device-plan",
        "baseKnowledgeHash": KNOWLEDGE_HASH,
        "outputs": ["schematic", "pcb", "enclosure", "stl"],
        "producer": {"kind": "human", "name": "owner"},
        "requirements": [
            {
                "id": "main-controller",
                "kind": "component",
                "subject": "main-controller",
                "claim": "A documented controller module",
                "requiredEvidence": ["manufacturer", "mpn", "datasheet", "pinout"],
                "constraints": [{"parameter": "quantity", "operator": "eq", "value": 1, "unit": "none"}],
            },
            {
                "id": "board-envelope",
                "kind": "geometry",
                "subject": "controller-pcb",
                "claim": "Board envelope",
                "requiredEvidence": ["dimensions"],
                "constraints": [{"parameter": "width", "operator": "max", "value": 90, "unit": "mm"}],
            },
        ],
    }
    value.update(changes)
    return value


def initialized_service(tmp_path):
    service = DoDslService(tmp_path)
    request = ProjectRequest.from_dict({
        "schema": "dodsl-request/v1",
        "projectId": "device-plan",
        "title": "Device plan",
        "gitSources": [],
        "webSources": [],
        "artifacts": ["ssot", "schematic", "pcb", "enclosure", "stl"],
    })
    service.create(request)
    workspace = service.workspace(request.project_id)
    atomic_write_json(workspace.root / "source-md-dsl/knowledge-manifest.json", {
        "schema": "dodsl-knowledge-manifest/v1",
        "projectId": request.project_id,
        "semanticHash": KNOWLEDGE_HASH,
    })
    return service, workspace


def test_artifact_intent_creates_only_non_executed_candidate(tmp_path):
    service, workspace = initialized_service(tmp_path)
    receipt = service.plan_artifact("device-plan", proposal())
    candidate = workspace.root / ".dodsl/queue/artifact-intent" / receipt["candidateId"]

    assert receipt["researchGaps"] == 5
    assert receipt["execution"] == "not_performed"
    assert receipt["ssotPromotion"] == "not_performed"
    assert not (workspace.root / "SSOT/current").exists()
    plan = (candidate / "research-plan.dsl").read_text(encoding="utf-8")
    assert "OPERATION research.component.run" in plan
    assert "EXECUTABLE_URI system-owned" in plan
    assert "dodsl://" not in plan
    status = service.status("device-plan")
    assert status["artifactIntentCandidates"] == 1
    assert status["lastIteration"]["stage"] == "artifact_intent_planned"
    assert status["lastIteration"]["candidateId"] == receipt["candidateId"]
    assert service.plan_artifact("device-plan", proposal()) == receipt


def test_artifact_intent_fails_closed_for_commands_stale_state_and_llm_without_provenance(tmp_path):
    service, _ = initialized_service(tmp_path)
    with pytest.raises(DoDslValidationError, match="KEYS_INVALID"):
        service.plan_artifact("device-plan", proposal(command="execute model output"))
    with pytest.raises(DoDslValidationError, match="BASE_KNOWLEDGE_STALE"):
        service.plan_artifact("device-plan", proposal(baseKnowledgeHash="sha256:" + "b" * 64))
    with pytest.raises(DoDslValidationError, match="LLM_PRODUCER_PROVENANCE_REQUIRED"):
        service.plan_artifact(
            "device-plan",
            proposal(producer={"kind": "llm", "name": "openrouter"}),
        )


def test_llm_proposal_is_audited_but_never_granted_authority(tmp_path):
    service, workspace = initialized_service(tmp_path)
    value = proposal(producer={
        "kind": "llm",
        "name": "openrouter",
        "model": "provider/model",
        "responseHash": "sha256:" + "c" * 64,
    })
    receipt = service.plan_artifact("device-plan", value)
    saved = json.loads((
        workspace.root / ".dodsl/queue/artifact-intent" / receipt["candidateId"] / "proposal.json"
    ).read_text(encoding="utf-8"))
    assert saved["producer"]["responseHash"] == "sha256:" + "c" * 64
    assert "authority" not in saved
    assert receipt["status"] == "proposed"
