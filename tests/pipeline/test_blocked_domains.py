"""The one parent-domain walk every blocklist uses (`blocked_domains.listed_domain_of`).

Three lists share it - `blocked_domains.txt` (the phase-3 search lane's evidence filter),
`theo_sources.BLOCKED_DOMAINS` and `web_research._CORRECTION_BLOCKED_DOMAINS` - so a host is matched
by itself and its parent domains, never by substring, in all three.
"""

from __future__ import annotations

import pytest

from pipeline.lyra import theo_sources, web_research
from pipeline.lyra.blocked_domains import listed_domain_of

LIST = frozenset({"reddit.com", "x.com", "ancientnerds.com"})


@pytest.mark.parametrize(
    ("host", "listed"),
    [
        ("reddit.com", "reddit.com"),
        ("old.reddit.com", "reddit.com"),
        ("a.b.reddit.com", "reddit.com"),
        ("www.ancientnerds.com", "ancientnerds.com"),
        ("x.com", "x.com"),
        ("linux.com", None),  # a substring match on `x.com` would refuse it
        ("reddit.com.evil.org", None),
        ("com", None),  # a bare TLD is never a candidate
        ("", None),
    ],
)
def test_a_host_is_listed_by_itself_or_a_parent_domain_never_by_substring(
    host: str, listed: str | None
) -> None:
    assert listed_domain_of(host, LIST) == listed


def test_the_three_lists_share_the_walk() -> None:
    assert theo_sources._is_blocked("https://old.reddit.com/r/history")
    assert theo_sources._is_blocked("https://np.reddit.com/r/history")  # listed only as a parent
    assert not theo_sources._is_blocked("https://linux.com/x")
    assert web_research._is_blocked_correction_domain("https://m.facebook.com/page")
    assert web_research._is_blocked_correction_domain("https://user@old.reddit.com:443/r/x")
    assert not web_research._is_blocked_correction_domain("https://linux.com/x")
    assert not web_research._is_blocked_correction_domain("https://example.org/?q=reddit.com")
