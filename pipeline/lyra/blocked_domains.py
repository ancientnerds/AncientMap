"""Shared blocked-domain list and URL safety guard for web verification sources."""

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DOMAINS_FILE = Path(__file__).parent / "blocked_domains.txt"


def _load_blocked_domains() -> frozenset[str]:
    if not _DOMAINS_FILE.exists():
        logger.error(
            "blocked_domains.txt missing at %s — web verification runs with an "
            "EMPTY blocklist; no domains will be filtered",
            _DOMAINS_FILE,
        )
        return frozenset()
    domains = set()
    for line in _DOMAINS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            domains.add(line)
    return frozenset(domains)


BLOCKED_DOMAINS = _load_blocked_domains()


def is_public_http_url(url: str) -> bool:
    """SSRF guard: True only for http(s) URLs whose host resolves to public IPs.

    Used before fetching URLs that come from untrusted input (LLM-extracted
    video-description links, federated image-connector results). Rejects
    non-HTTP schemes and hostnames resolving to private/loopback/link-local
    addresses. Performs a blocking DNS lookup — call via a worker thread
    from async code.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    return True
