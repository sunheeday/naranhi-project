from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import urlparse


PRIVATE_HOST_ERROR = "download_blocked_private_host"


def tls_verify_for_url(url: str) -> bool:
    host = _host(url)
    if not host:
        return True
    insecure_hosts = _env_host_set("TLS_VERIFY_INSECURE_HOSTS")
    return host not in insecure_hosts


def tls_metadata(url: str) -> dict[str, object]:
    verify = tls_verify_for_url(url)
    return {
        "tls_verified": verify,
        "tls_unverified": not verify,
    }


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise RuntimeError(f"{PRIVATE_HOST_ERROR}: missing host")
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"{PRIVATE_HOST_ERROR}: unsupported scheme {parsed.scheme}")
    if _is_private_host(host):
        raise RuntimeError(f"{PRIVATE_HOST_ERROR}: {host}")


def sanitize_error(exc: BaseException | str) -> str:
    text = str(exc)
    for key in _sensitive_values():
        if key:
            text = text.replace(key, "[REDACTED]")
    text = re.sub(r"(x-goog-api-key=)[^&\s]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(key=)[^&\s]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    return text


def _is_private_host(host: str) -> bool:
    lowered = host.lower().strip("[]")
    if lowered in {"localhost", "metadata.google.internal"}:
        return True
    try:
        ip = ipaddress.ip_address(lowered)
        return _is_blocked_ip(ip)
    except ValueError:
        pass

    # DNS resolution is intentionally best-effort. If it fails, the normal HTTP
    # request will fail later; if it resolves private, block before fetching.
    try:
        infos = socket.getaddrinfo(lowered, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = info[4][0]
        try:
            if _is_blocked_ip(ipaddress.ip_address(address)):
                return True
        except ValueError:
            continue
    return False


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _env_host_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {item.strip().lower() for item in re.split(r"[\s,;]+", raw) if item.strip()}


def _sensitive_values() -> list[str]:
    values: list[str] = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEYS", "SUPABASE_SERVICE_ROLE_KEY"):
        raw = os.getenv(name, "")
        values.extend(item.strip() for item in re.split(r"[\s,;]+", raw) if item.strip())
    return values
