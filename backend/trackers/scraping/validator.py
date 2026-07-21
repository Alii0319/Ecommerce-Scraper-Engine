from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from .exceptions import UnsafeTargetUrlError

METADATA_HOSTNAMES = {
    "metadata.google.internal",
    "169.254.169.254",
    "100.100.100.200",
}


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    hostname: str
    addresses: tuple[str, ...]


def _is_forbidden_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)

    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


def resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    if hostname.lower() in METADATA_HOSTNAMES:
        raise UnsafeTargetUrlError("Access to metadata services is strictly forbidden")

    try:
        results = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeTargetUrlError(f"Target hostname '{hostname}' could not be resolved.") from exc

    addresses = sorted({row[4][0] for row in results})

    if not addresses:
        raise UnsafeTargetUrlError(f"Target hostname '{hostname}' resolved to no IP addresses.")

    for address in addresses:
        if _is_forbidden_ip(address):
            raise UnsafeTargetUrlError(
                f"Target hostname '{hostname}' resolves to a forbidden network address ({address})."
            )

    return tuple(addresses)


def validate_public_url(url: str) -> ValidatedTarget:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetUrlError(f"Only HTTP and HTTPS targets are supported. Got '{parsed.scheme}'")

    if not parsed.hostname:
        raise UnsafeTargetUrlError("Target hostname is required.")

    if parsed.username or parsed.password:
        raise UnsafeTargetUrlError("Credentials embedded in target URLs are forbidden.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = resolve_public_addresses(parsed.hostname, port)

    return ValidatedTarget(
        url=url,
        hostname=parsed.hostname,
        addresses=addresses,
    )
