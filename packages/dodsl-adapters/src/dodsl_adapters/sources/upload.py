from __future__ import annotations

import mimetypes
import os
import re
import shutil
import uuid
from pathlib import Path

from dodsl_contracts.errors import DoDslConflict, DoDslValidationError
from dodsl_core.io import atomic_write_json, canonical_hash, sha256_bytes, utc_now
from dodsl_core.workspace import ProjectWorkspace


class UploadImporter:
    def __init__(self, *, max_bytes: int = 50 * 1024 * 1024):
        self.max_bytes = max_bytes

    def capture(self, workspace: ProjectWorkspace, source_path: str | Path, *, trust_role: str = "customer") -> dict[str, object]:
        source = Path(source_path).resolve()
        if source.is_symlink() or not source.is_file():
            raise DoDslValidationError("UPLOAD_REGULAR_FILE_REQUIRED")
        if source.stat().st_size > self.max_bytes:
            raise DoDslValidationError("UPLOAD_TOO_LARGE")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip("-.") or "upload.bin"
        body = source.read_bytes()
        content_hash = sha256_bytes(body)
        destination = workspace.root / "source/uploads" / content_hash.split(":", 1)[1][:16]
        if destination.exists():
            raise DoDslConflict(f"UPLOAD_ALREADY_EXISTS:{content_hash}")
        staging = destination.parent / ("." + destination.name + "." + uuid.uuid4().hex[:8])
        staging.mkdir(parents=True)
        try:
            target = staging / safe_name
            target.write_bytes(body)
            semantic = {
                "schema": "dodsl-upload-source/v1", "contentHash": content_hash,
                "fileName": safe_name, "size": len(body),
                "mimeType": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
                "trustRole": trust_role,
            }
            semantic_hash = canonical_hash(semantic)
            manifest = {
                **semantic, "importedAt": utc_now(), "semanticHash": semantic_hash,
                "evidenceUri": "urn:dodsl:upload:sha256:" + semantic_hash.split(":", 1)[1],
            }
            atomic_write_json(staging / "manifest.json", manifest)
            os.replace(staging, destination)
            return manifest
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
