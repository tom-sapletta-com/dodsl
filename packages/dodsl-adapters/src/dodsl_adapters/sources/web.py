from __future__ import annotations

import json
import os
import shutil
import ssl
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from dodsl_contracts.errors import DoDslConflict, DoDslDependencyError, DoDslValidationError
from dodsl_contracts.model import WebSource
from dodsl_core.io import atomic_write_bytes, atomic_write_json, canonical_hash, sha256_bytes, utc_now
from dodsl_core.workspace import ProjectWorkspace
from .guards import assert_public_http_url, normalized_host


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class WebSnapshotter:
    def __init__(self, *, allow_private: bool | None = None, max_bytes: int = 5 * 1024 * 1024, timeout: int = 30):
        self.allow_private = (os.getenv("DODSL_ALLOW_PRIVATE_WEB") == "1") if allow_private is None else allow_private
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def _fetch(self, value: str, allowed_hosts: set[str]) -> tuple[str, int, dict[str, str], bytes]:
        current = value
        for _ in range(6):
            assert_public_http_url(current, allow_private=self.allow_private)
            if normalized_host(current) not in allowed_hosts:
                raise DoDslValidationError(f"WEB_REDIRECT_HOST_FORBIDDEN:{normalized_host(current)}")
            request = Request(current, headers={
                "User-Agent": "doDSL/0.1 (+https://github.com/tom-sapletta-com/dodsl)",
                "Accept": "text/html,application/xhtml+xml;q=0.9", "Accept-Encoding": "identity",
            })
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
                    current = urljoin(current, exc.headers["Location"])
                    continue
                raise DoDslDependencyError(f"WEB_HTTP_{exc.code}:{current}") from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise DoDslDependencyError(f"WEB_FETCH_FAILED:{type(exc).__name__}:{current}") from exc
            with response:
                content_type = response.headers.get_content_type().lower()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise DoDslValidationError(f"WEB_HTML_REQUIRED:{content_type}")
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > self.max_bytes:
                    raise DoDslValidationError("WEB_RESPONSE_TOO_LARGE")
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise DoDslValidationError("WEB_RESPONSE_TOO_LARGE")
                headers = {key.lower(): value for key, value in response.headers.items()}
                return response.geturl(), response.status, headers, body
        raise DoDslValidationError("WEB_REDIRECT_LIMIT_EXCEEDED")

    def capture(self, workspace: ProjectWorkspace, source: WebSource) -> dict[str, object]:
        if source.method != "http":
            raise DoDslDependencyError("PLAYWRIGHT_ADAPTER_NOT_CONFIGURED")
        allowed_hosts = {normalized_host(source.url)}
        resolved_url, status, headers, body = self._fetch(source.url, allowed_hosts)
        content_hash = sha256_bytes(body)
        key = canonical_hash({"url": source.url, "contentHash": content_hash})[-16:]
        destination = workspace.root / "source/web" / normalized_host(source.url) / key
        if destination.exists():
            manifest_path = destination / "manifest.json"
            if manifest_path.is_file():
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            raise DoDslConflict(f"WEB_DESTINATION_EXISTS:{key}")
        staging = destination.parent / ("." + key + "." + uuid.uuid4().hex[:8])
        try:
            staging.mkdir(parents=True)
            atomic_write_bytes(staging / "page.html", body)
            atomic_write_json(staging / "response-headers.json", headers)
            semantic = {
                "schema": "dodsl-web-source/v1", "sourceUrl": source.url,
                "resolvedUrl": resolved_url, "contentHash": content_hash,
                "mimeType": headers.get("content-type", "text/html").split(";", 1)[0],
                "status": status, "method": "http", "trustRole": source.trust_role,
            }
            semantic_hash = canonical_hash(semantic)
            manifest = {
                **semantic, "fetchedAt": utc_now(), "semanticHash": semantic_hash,
                "evidenceUri": "urn:dodsl:web:sha256:" + semantic_hash.split(":", 1)[1],
            }
            atomic_write_json(staging / "manifest.json", manifest)
            os.replace(staging, destination)
            return manifest
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
