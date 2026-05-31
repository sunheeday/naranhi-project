from __future__ import annotations

import ipaddress
import os
import re
import socket
import ssl
from urllib.parse import urlparse


PRIVATE_HOST_ERROR = "download_blocked_private_host"

# Korean school/gov servers (e.g. *.sen.ms.kr, *.gen.ms.kr) often present TLS
# certs with legacy signature algorithms that OpenSSL 3's default security level
# rejects mid-handshake ("WRONG_SIGNATURE_TYPE"). Mirror the crawler's host list
# so the extractor's detail/file fetches reach the same servers.
_DEFAULT_LEGACY_TLS_HOSTS = ("sen.ms.kr", "gen.ms.kr")


def tls_verify_for_url(url: str) -> bool:
    host = _host(url)
    if not host:
        return True
    insecure_hosts = _env_host_set("TLS_VERIFY_INSECURE_HOSTS")
    return host not in insecure_hosts


def uses_legacy_tls(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(_host_matches(host, pattern) for pattern in _legacy_tls_hosts())


def legacy_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        context.minimum_version = ssl.TLSVersion.TLSv1
    except (AttributeError, ValueError):
        pass
    try:
        context.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    return context


def client_verify_for_url(url: str) -> bool | ssl.SSLContext:
    """httpx ``verify`` value for fetching a school URL.

    - legacy-TLS hosts -> relaxed SSL context (fixes WRONG_SIGNATURE_TYPE)
    - TLS_VERIFY_INSECURE_HOSTS -> False
    - otherwise -> True (full verification)
    """
    if uses_legacy_tls(url):
        return legacy_ssl_context()
    return tls_verify_for_url(url)


def tls_metadata(url: str) -> dict[str, object]:
    verify = tls_verify_for_url(url) and not uses_legacy_tls(url)
    return {
        "tls_verified": verify,
        "tls_unverified": not verify,
    }


def _legacy_tls_hosts() -> tuple[str, ...]:
    raw = os.getenv("CRAWLER_TLS_LEGACY_HOSTS", ",".join(_DEFAULT_LEGACY_TLS_HOSTS))
    hosts = tuple(item.strip().lower() for item in re.split(r"[\s,;]+", raw) if item.strip())
    return hosts or _DEFAULT_LEGACY_TLS_HOSTS


def _host_matches(host: str, pattern: str) -> bool:
    normalized = pattern.strip().lower()
    return bool(normalized) and (host == normalized or host.endswith(f".{normalized}"))


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
