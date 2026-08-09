#!/usr/bin/env python3
"""Run deterministic doDSL development gates and write a compact status report."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Stage:
    name: str
    status: str
    detail: str
    command: list[str]
    log: str | None
    required: bool


def _last_detail(output: str, returncode: int) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:300] if lines else f"exit {returncode}"


def _run(
    name: str,
    command: list[str],
    *,
    root: Path,
    output_dir: Path,
    required: bool = True,
    env: dict[str, str] | None = None,
    timeout_seconds: int = 300,
) -> Stage:
    if shutil.which(command[0]) is None:
        return Stage(name, "skipped", f"executable unavailable: {command[0]}", command, None, required)
    log_path = output_dir / f"{name}.log"
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        output = result.stdout
        status = "pass" if result.returncode == 0 else "fail"
        detail = _last_detail(output, result.returncode)
    except subprocess.TimeoutExpired as exc:
        raw_output = exc.stdout or ""
        output = raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, bytes) else raw_output
        output += f"\nTIMEOUT after {timeout_seconds}s\n"
        status = "fail"
        detail = f"timed out after {timeout_seconds}s"
    log_path.write_text(output, encoding="utf-8")
    return Stage(
        name,
        status,
        detail,
        command,
        log_path.relative_to(root).as_posix(),
        required,
    )


def _skipped(name: str, detail: str, *, required: bool = False) -> Stage:
    return Stage(name, "skipped", detail, [], None, required)


def render_markdown(report: dict[str, object]) -> str:
    stages = report["stages"]
    assert isinstance(stages, list)
    lines = [
        "# doDSL development status",
        "",
        f"Generated: {report['generatedAt']}",
        "",
        "| Stage | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for raw in stages:
        assert isinstance(raw, dict)
        detail = str(raw["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {raw['name']} | {str(raw['status']).upper()} | {detail} |")
    next_actions = report["nextActions"]
    assert isinstance(next_actions, list)
    lines.extend(["", "## Next actions", ""])
    if next_actions:
        lines.extend(f"- {action}" for action in next_actions)
    else:
        lines.append("- None; all required local gates passed.")
    return "\n".join(lines) + "\n"


def generate(root: Path, output_dir: Path, *, external: bool, docker: bool) -> dict[str, object]:
    root = root.resolve()
    output_dir = (root / output_dir).resolve() if not output_dir.is_absolute() else output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stages = [
        _run(
            "tests",
            ["uv", "run", "--all-packages", "pytest", "-q", "--ignore=tests/test_e2e.py"],
            root=root,
            output_dir=output_dir,
        ),
        _run(
            "duplicates",
            [
                "redup", "check", "packages", "--ext", ".py", "--min-lines", "8",
                "--max-groups", "0", "--max-lines", "0",
            ],
            root=root,
            output_dir=output_dir,
        ),
        _run(
            "build",
            ["uv", "build", "--all-packages", "--out-dir", str(output_dir / "dist")],
            root=root,
            output_dir=output_dir,
        ),
    ]

    if external:
        onlydsl = os.getenv("DODSL_TEST_ONLYDSL_SSOT_COMMAND", "").strip()
        todo2code = os.getenv("DODSL_TEST_TODO2CODE_COMMAND", "").strip()
        if onlydsl and todo2code:
            stages.append(
                _run(
                    "external-e2e",
                    ["uv", "run", "--all-packages", "pytest", "-q", "tests/test_e2e.py"],
                    root=root,
                    output_dir=output_dir,
                    env=os.environ.copy(),
                    timeout_seconds=900,
                )
            )
        else:
            stages.append(
                _skipped(
                    "external-e2e",
                    "DODSL_TEST_ONLYDSL_SSOT_COMMAND and DODSL_TEST_TODO2CODE_COMMAND are required",
                    required=True,
                )
            )
    else:
        stages.append(_skipped("external-e2e", "not requested; use make report-full"))

    if docker:
        stages.append(
            _run(
                "docker-build",
                ["docker", "compose", "build"],
                root=root,
                output_dir=output_dir,
                timeout_seconds=600,
            )
        )
    else:
        stages.append(_skipped("docker-build", "not requested; use make report-full"))

    next_actions: list[str] = []
    for stage in stages:
        if stage.status == "fail":
            next_actions.append(f"Inspect {stage.log or stage.name} and repair {stage.name}.")
        elif stage.status == "skipped" and stage.required:
            next_actions.append(f"Configure {stage.name}: {stage.detail}.")
    ok = not next_actions and all(stage.status != "fail" for stage in stages)
    return {
        "schema": "dodsl.status-report/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "ok": ok,
        "stages": [asdict(stage) for stage in stages],
        "nextActions": next_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path(".ci-reports"))
    parser.add_argument("--external", action="store_true")
    parser.add_argument("--docker", action="store_true")
    args = parser.parse_args()

    report = generate(args.root, args.output_dir, external=args.external, docker=args.docker)
    output_dir = args.output_dir if args.output_dir.is_absolute() else args.root / args.output_dir
    (output_dir / "status.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown = render_markdown(report)
    (output_dir / "status.md").write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
