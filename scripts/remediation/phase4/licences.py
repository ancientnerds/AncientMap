"""Which licence a source carries, which hosts are never a source, and when a page is a mirror.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, section
source_store ("DENY LIST (phase4/licences.py, versioned)") and section licensing_and_ai_act. Work
item WB-A2.

Three questions, three functions, and nothing here fetches anything:

* `licence_of(url)` - the licence of a page by its host: every Wikipedia language edition is
  CC BY-SA 4.0, Wikidata is CC0 (a witness only, never published), and every other page is
  `restricted`: its facts may be restated, its wording is never published.
* `deny_family(url)` - the family a host is refused as, or `None`. Four families: the AI-generated
  aggregators the design names (`grokipedia.com` also sits in the `api/main.py` seed), the
  Wikipedia mirrors (counted as the wikimedia family, never as a separate source - their text is
  reachable at its source, with its revision), `pipeline/lyra/blocked_domains.BLOCKED_DOMAINS`, and
  this project's own site. The last one is not in the design's list; it is added because a page of
  ancientnerds.com would make a description cite our own (possibly wrong) value - the same reason
  the phase-3 search lane excludes it (`phase3/search_evidence.OWN_DOMAINS`).
* `is_mirror(page_text, wiki_text)` - a page that shares a run of `MIRROR_RUN_WORDS` or more words
  with the site's Wikipedia text is classed as wikimedia whatever its host.

Hosts are matched label by label (`blocked_domains.listed_domain_of`), never by substring: a
substring match on `x.com` would refuse `linux.com`. A mirror named without its TLD (`wikiwand`,
`dbpedia`) is matched as one whole label of the host (`www.wikiwand.com`), so a mirror that moves
to another TLD stays refused.

The list is versioned (`LICENCES_VERSION`): a stored R page records which list it passed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urlsplit

from phase3.search_evidence import OWN_DOMAINS

from phase4 import model4 as M
from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS, listed_domain_of

#: Bumped whenever a list below changes. A stored lane-R page carries the version it passed.
LICENCES_VERSION = "2026-09-23.1"

#: Every Wikipedia language edition: `en.wikipedia.org`, `fr.wikipedia.org`, `en.m.wikipedia.org`.
WIKIPEDIA_DOMAIN = "wikipedia.org"
#: Wikidata: `www.wikidata.org` (the API) and `query.wikidata.org` (WDQS).
WIKIDATA_DOMAIN = "wikidata.org"

#: The AI-generated aggregators the design names (source_store, DENY LIST).
AI_AGGREGATORS: tuple[str, ...] = (
    "grokipedia.com",
    "aroundus.com",
    "mindtrip.ai",
    "evendo.com",
    "wanderlog.com",
)
#: The Wikipedia mirrors the design names, each as one host label (`kiddle` covers `kiddle.co`).
MIRROR_NAMES: tuple[str, ...] = (
    "kiddle",
    "wikiwand",
    "dbpedia",
    "alchetron",
    "wiki2",
    "everybodywiki",
    "infogalactic",
    "wikishire",
)

FAMILY_AI_AGGREGATOR = "ai-aggregator"
#: A Wikipedia mirror, and any page the mirror detector matches: counted as wikimedia.
FAMILY_WIKIMEDIA = "wikimedia"
FAMILY_BLOCKED = "blocked-domain"
FAMILY_OWN_SITE = "own-site"

#: A shared run of this many words makes a page a mirror of the Wikipedia text (design).
MIRROR_RUN_WORDS = 25

_WORD = re.compile(r"\w+")


def host_of(url: str) -> str:
    """The lowercased host of an http(s) URL. Anything else raises: a licence needs a host."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host:
        raise ValueError(f"{url!r} is not an http(s) URL with a host")
    return host


def _under(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def is_wikipedia_host(host: str) -> bool:
    """`*.wikipedia.org`: every language edition, mobile hosts included."""
    return _under(host, WIKIPEDIA_DOMAIN)


def is_wiki_host(host: str) -> bool:
    """The hosts the design gives the 1 MiB cap: `*.wikipedia.org` and `wikidata.org`."""
    return is_wikipedia_host(host) or _under(host, WIKIDATA_DOMAIN)


def licence_of(url: str) -> M.Licence:
    """The licence of the page at `url`, by its host (the registry of the module docstring)."""
    host = host_of(url)
    if is_wikipedia_host(host):
        return M.Licence.CC_BY_SA_4
    if _under(host, WIKIDATA_DOMAIN):
        return M.Licence.CC0
    return M.Licence.RESTRICTED


def deny_family(url: str) -> str | None:
    """The family `url`'s host is refused as, or `None` when it may be a source."""
    host = host_of(url)
    if listed_domain_of(host, OWN_DOMAINS) is not None:
        return FAMILY_OWN_SITE
    if listed_domain_of(host, AI_AGGREGATORS) is not None:
        return FAMILY_AI_AGGREGATOR
    if any(label in MIRROR_NAMES for label in host.split(".")):
        return FAMILY_WIKIMEDIA
    if listed_domain_of(host, BLOCKED_DOMAINS) is not None:
        return FAMILY_BLOCKED
    return None


def _runs(words: list[str]) -> Iterator[tuple[str, ...]]:
    for start in range(len(words) - MIRROR_RUN_WORDS + 1):
        yield tuple(words[start : start + MIRROR_RUN_WORDS])


def is_mirror(page_text: str, wiki_text: str) -> bool:
    """Whether the page shares a run of `MIRROR_RUN_WORDS` or more words with the Wikipedia text.

    Words are `\\w+` runs, compared casefolded, so markup, punctuation and line breaks between them
    do not hide a copy. A run of 25 words shared is a run of every length up to 25 shared, so one
    window size decides it.
    """
    wiki_runs = set(_runs(_WORD.findall(wiki_text.casefold())))
    if not wiki_runs:
        return False
    return any(run in wiki_runs for run in _runs(_WORD.findall(page_text.casefold())))
