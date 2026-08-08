from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from dodsl_contracts.errors import DoDslValidationError


def assert_public_http_url(value: str, *, allow_private: bool = False) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise DoDslValidationError("WEB_URL_INVALID")
    if allow_private:
        return
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DoDslValidationError(f"WEB_DNS_FAILED:{parsed.hostname}") from exc
    if not addresses:
        raise DoDslValidationError(f"WEB_DNS_EMPTY:{parsed.hostname}")
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise DoDslValidationError(f"WEB_PRIVATE_ADDRESS_FORBIDDEN:{parsed.hostname}:{address}")


def normalized_host(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname:
        raise DoDslValidationError("URL_HOST_REQUIRED")
    return parsed.hostname.encode("idna").decode("ascii").lower()
