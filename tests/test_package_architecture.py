from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_RULES = {
    "packages/dodsl-contracts/src": {"dodsl_core", "dodsl_planning", "dodsl_adapters", "dodsl"},
    "packages/dodsl-core/src": {"dodsl_planning", "dodsl_adapters", "dodsl"},
    "packages/dodsl-planning/src": {"dodsl_adapters", "dodsl"},
    "packages/dodsl-adapters/src": {"dodsl_planning", "dodsl"},
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_package_dependency_direction_has_no_upward_or_app_imports():
    failures: list[str] = []
    for relative, forbidden in PACKAGE_RULES.items():
        for path in sorted((ROOT / relative).rglob("*.py")):
            invalid = imported_roots(path) & forbidden
            if invalid:
                failures.append(f"{path.relative_to(ROOT)} imports {sorted(invalid)}")
    assert not failures, "\n".join(failures)


def test_workspace_members_are_real_independently_buildable_projects():
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["tool"]["uv"]["workspace"]["members"] == ["packages/*", "apps/*"]
    expected = {
        "dodsl-contracts", "dodsl-core", "dodsl-planning", "dodsl-adapters", "dodsl",
    }
    actual = set()
    for path in (*sorted((ROOT / "packages").glob("*/pyproject.toml")), *sorted((ROOT / "apps").glob("*/pyproject.toml"))):
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        actual.add(value["project"]["name"])
    assert actual == expected


def test_workspace_package_versions_are_kept_in_lockstep():
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    versions = {root["project"]["version"]}
    for path in (*sorted((ROOT / "packages").glob("*/pyproject.toml")), *sorted((ROOT / "apps").glob("*/pyproject.toml"))):
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        versions.add(value["project"]["version"])
    assert versions == {expected}

    internal_names = {
        "dodsl", "dodsl-adapters", "dodsl-contracts", "dodsl-core", "dodsl-planning",
    }
    manifests = [root, *(
        tomllib.loads(path.read_text(encoding="utf-8"))
        for path in (*sorted((ROOT / "packages").glob("*/pyproject.toml")), *sorted((ROOT / "apps").glob("*/pyproject.toml")))
    )]
    for manifest in manifests:
        for dependency in manifest["project"].get("dependencies", []):
            name = re.split(r"[<>=!~ ]", dependency, maxsplit=1)[0]
            if name in internal_names:
                assert dependency == f"{name}>=0.2,<0.3"

    for init_path in (*sorted((ROOT / "packages").glob("*/src/*/__init__.py")),
                      *sorted((ROOT / "apps").glob("*/src/*/__init__.py"))):
        assert '__version__ = "0+unknown"' in init_path.read_text(encoding="utf-8")


def test_legacy_public_imports_remain_compatible_during_package_migration():
    from dodsl.knowledge.intent_compile import compile_tree as legacy_compile_tree
    from dodsl.knowledge import KnowledgeCompiler
    from dodsl.model import ProjectRequest
    from dodsl.planning import ArtifactIntentProposal, ArtifactPlanningService
    from dodsl.sources import GitSnapshotter, UploadImporter, WebSnapshotter
    from dodsl.ssot import SsotBridge
    from dodsl.workspace import ProjectWorkspace
    from f2md.intent_compile import compile_tree

    assert all((
        KnowledgeCompiler, ProjectRequest, ArtifactIntentProposal,
        ArtifactPlanningService, GitSnapshotter, UploadImporter,
        WebSnapshotter, SsotBridge, ProjectWorkspace,
    ))
    assert legacy_compile_tree is compile_tree


def test_dodsl_uses_kernel_canonical_hash_contract_without_copying_it():
    from dodsl_contracts.hashing import canonical_hash
    from onlydsl_contracts.dsl.common import canonical_hash as kernel_canonical_hash

    assert canonical_hash is kernel_canonical_hash
    assert canonical_hash({"b": 2, "a": 1}) == kernel_canonical_hash({"a": 1, "b": 2})


def test_external_capabilities_have_one_owner_and_pinned_adapters():
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = tomllib.loads((ROOT / "packages/dodsl-contracts/pyproject.toml").read_text(encoding="utf-8"))
    adapters = tomllib.loads((ROOT / "packages/dodsl-adapters/pyproject.toml").read_text(encoding="utf-8"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    def docker_commit(name: str) -> str:
        match = re.search(rf"^ARG {name}=([0-9a-f]{{40}})$", dockerfile, re.MULTILINE)
        assert match, name
        return match.group(1)

    sources = root["tool"]["uv"]["sources"]
    assert sources["onlydsl-contracts"]["rev"] == docker_commit("ONLYDSL_PACKAGES_COMMIT")
    assert sources["f2md"]["rev"] == docker_commit("F2MD_COMMIT")
    assert len(docker_commit("TODO2CODE_COMMIT")) == 40
    assert contracts["project"]["dependencies"] == ["onlydsl-contracts>=0.0.12,<0.1"]
    assert "f2md>=0.5.31,<0.6" in adapters["project"]["dependencies"]
    assert not (ROOT / "packages/dodsl-adapters/src/dodsl_adapters/knowledge/intent_compile.py").exists()
    legacy_bridge = ROOT / "apps/dodsl-service/src/dodsl/knowledge/intent_compile.py"
    assert "from f2md.intent_compile import *" in legacy_bridge.read_text(encoding="utf-8")

    manifests = [
        tomllib.loads(path.read_text(encoding="utf-8"))["project"]["dependencies"]
        for path in (*sorted((ROOT / "packages").glob("*/pyproject.toml")), *sorted((ROOT / "apps").glob("*/pyproject.toml")))
    ]
    assert not any(dependency.lower().startswith("todo2code") for dependencies in manifests for dependency in dependencies)
    assert "/home/" not in (ROOT / "tests/test_e2e.py").read_text(encoding="utf-8")


def test_process_registry_points_to_extracted_implementations_and_new_invariant_name():
    registry = json.loads((ROOT / "process-packs/registry.v1.json").read_text(encoding="utf-8"))
    executors = {item.get("executor", "") for item in registry["operations"]}
    assert "dodsl_adapters.sources.git:GitSnapshotter" in executors
    assert "dodsl_planning.planner:ArtifactPlanningService" in executors
    assert registry["invariants"]["dodslSsotPromotion"] == "forbidden"
    assert "forgeSsotPromotion" not in registry["invariants"]
