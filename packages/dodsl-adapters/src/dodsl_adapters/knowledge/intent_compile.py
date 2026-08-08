"""Deterministic Markdown evidence projection used when f2md lacks intent_compile.

This module indexes headings and prose as source-anchored evidence.  It does not
interpret a user's natural-language request, create authority, or promote SSOT.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from dodsl_core.io import atomic_write_json


COMPILER_ID = "dodsl.markdown-evidence-compiler/v1"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return {}
    block = text[4:text.find("\n---", 4)]
    result: dict[str, str] = {}
    for line in block.splitlines():
        match = re.match(r'^([A-Za-z][A-Za-z0-9_]*):\s*"?(.*?)"?$', line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def _validate(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise ValueError("T2C_INTENT_ARRAY_REQUIRED")
    allowed_types = {"request", "plan", "decision", "message", "report", "result", "claim"}
    allowed_keys = {"schema", "id", "type", "text", "actor", "targetUris", "ticket", "source"}
    required = {"schema", "id", "type", "text", "actor", "targetUris"}
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) - allowed_keys or not required.issubset(record):
            raise ValueError(f"INVALID_INTENT_KEYS:{index}")
        if record["schema"] != "t2c.intent/v1" or record["type"] not in allowed_types:
            raise ValueError(f"INVALID_INTENT:{index}")
        if not isinstance(record["id"], str) or record["id"] in seen or not record["text"]:
            raise ValueError(f"INVALID_INTENT_ID_OR_TEXT:{index}")
        targets = record["targetUris"]
        if not isinstance(targets, list) or not targets or not all(isinstance(item, str) for item in targets):
            raise ValueError(f"INVALID_INTENT_TARGETS:{index}")
        seen.add(record["id"])
    return records


def compile_markdown(path: str | Path, root: str | Path) -> list[dict[str, Any]]:
    source = Path(path).resolve()
    base = Path(root).resolve()
    text = source.read_text(encoding="utf-8")
    frontmatter = _frontmatter(text)
    body = text.split("\n---\n", 1)[-1]
    relative = source.relative_to(base).as_posix()
    source_uri = f"subactor://markdown/{relative}"
    anchor = {
        "artifactUri": source_uri,
        "revisionHash": _hash(text),
        "fragment": relative,
        "converter": frontmatter.get("converter", "unknown"),
        "converterVersion": frontmatter.get("converterVersion", "unknown"),
    }
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", body))
    records: list[dict[str, Any]] = []
    for index, match in enumerate(headings):
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        section = re.sub(r"\s+", " ", body[start:end]).strip()
        section = re.sub(r"[`*_]", "", section)[:1200] or match.group(2).strip()
        records.append({
            "schema": "t2c.intent/v1",
            "id": _hash(f"{relative}:{index}")[:16],
            "type": "claim",
            "text": f"{match.group(2).strip()}: {section}",
            "actor": "source:markdown",
            "targetUris": [source_uri],
            "source": anchor,
        })
    if not records:
        prose = re.sub(r"\s+", " ", body).strip()[:1200]
        records.append({
            "schema": "t2c.intent/v1",
            "id": _hash(relative)[:16],
            "type": "claim",
            "text": prose or f"Evidence exists in {relative}",
            "actor": "source:markdown",
            "targetUris": [source_uri],
            "source": anchor,
        })
    return _validate(records)


def compile_tree(source: str | Path, output: str | Path, only_english: bool = True) -> dict[str, Any]:
    root, destination = Path(source).resolve(), Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema": "subactor.intent-compile-report/v1",
        "compiler": COMPILER_ID,
        "source": str(root),
        "output": str(destination),
        "files": 0,
        "records": 0,
        "failures": [],
    }
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts or ".living-runtime" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        language = _frontmatter(text).get("language")
        if only_english and language not in ("", "en", "unknown", None):
            continue
        try:
            records = compile_markdown(path, root)
            relative = path.relative_to(root)
            target = destination / relative.parent / f"{relative.name}.intent.json"
            atomic_write_json(target, {
                "schema": "t2c.intent-pack/v1",
                "source": str(path),
                "sourceHash": _hash(text),
                "records": records,
            })
            summary["files"] += 1
            summary["records"] += len(records)
        except (OSError, ValueError) as error:
            summary["failures"].append({"path": str(path), "error": str(error)})
    atomic_write_json(destination / "compile-report.json", summary)
    return summary
