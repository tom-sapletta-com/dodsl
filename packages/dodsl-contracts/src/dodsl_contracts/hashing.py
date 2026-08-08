from __future__ import annotations

import hashlib
import json
from typing import Any

from onlydsl_contracts.dsl.common import canonical_hash


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
