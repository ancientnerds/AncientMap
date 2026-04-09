"""Shared blocked domain list for web verification sources."""

from pathlib import Path

_DOMAINS_FILE = Path(__file__).parent / "blocked_domains.txt"


def _load_blocked_domains() -> frozenset[str]:
    if not _DOMAINS_FILE.exists():
        return frozenset()
    domains = set()
    for line in _DOMAINS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            domains.add(line)
    return frozenset(domains)


BLOCKED_DOMAINS = _load_blocked_domains()
