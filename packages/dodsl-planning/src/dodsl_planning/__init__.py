"""Typed artifact intent and research planning contracts."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dodsl-planning")
except PackageNotFoundError:
    __version__ = "0.2.0"

from dodsl_contracts.artifact_intent import ArtifactIntentProposal
from .planner import ArtifactPlanningService

__all__ = ["ArtifactIntentProposal", "ArtifactPlanningService", "__version__"]
