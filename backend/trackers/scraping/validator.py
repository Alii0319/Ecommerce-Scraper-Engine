import ipaddress
import socket
from urllib.parse import urlparse

from .exceptions import UnsafeTargetUrlError


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetUrlError(f"Unsupported URL scheme: {parsed.scheme}")

    if not parsed.hostname:
        raise UnsafeTargetUrlError("Missing hostname in target URL")

    if parsed.username or parsed.password:
        raise UnsafeTargetUrlError("Credentials in target URLs are forbidden")

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except socket.gaierror as exc:
        raise UnsafeTargetUrlError(f"Could not resolve hostname '{parsed.hostname}'") from exc

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeTargetUrlError(
                f"Target hostname '{parsed.hostname}' resolves to non-public IP address ({ip})"
            )
