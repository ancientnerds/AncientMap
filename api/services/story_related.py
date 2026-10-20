"""Which public stories a story page offers under "Related stories".

Deterministic and explainable: every pick carries the one reason it was
chosen, tried in this order until the block holds ``limit`` stories —

1. ``site``: the same matched site (``news_items.site_id``);
2. ``place``: the same place by name — the matched site's name, or the
   extractor's ``site_name_extracted`` for a story the matcher never resolved
   (2,029 of 2,869 public stories carry a place name, 1,686 a site; measured
   2026-10-20);
3. ``country``: the same country of the matched site;
4. ``topic``: shared words of headline and tags, weighted by their rarity
   across the candidates (inverse document frequency);
5. ``category``: the same ``news_category`` unless it is ``general`` — only
   to fill a block that would otherwise hold fewer than ``RELATED_MIN``.

Within a tier the stronger topic overlap comes first, then the higher
significance, then the newer story, then the higher id. A story qualifies for
``topic`` only with at least ``MIN_SHARED_TERMS`` shared words worth
``MIN_TOPIC_SCORE`` together; a block with fewer picks stays short rather
than padding with unrelated stories. Until 2026-10-20 the fallback was "same
news_category", newest first: the elongated-skull cluster (stories 7364,
6770, 5839 — 22 % of the Google clicks on stories 10.–17.10., SEO audit
2026-10-19 traffic-7) has no site and sits in ``general``/``heritage``, so its
blocks listed the newest Osireion and Egypt stories.

Measured on the 2,869 public stories of 2026-10-20 (candidates: the 2,317 of
the index set): 2,439 get five picks, 85 four, 204 three, 92 one or two and
49 none.

Pure code over plain rows: the route loads the candidates in one query
(``articles_html._related_stories``); this module never touches the DB.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

#: Picks per block — the owner's 3–5 (decision 2026-10-20).
RELATED_LIMIT = 5
RELATED_MIN = 3

#: A topic pick needs two shared words. One is too weak: 10.9 % of all story
#: pairs share at least one word, 1.8 % share two (100 sampled stories against
#: the 2,317 of the index set, 2026-10-20).
MIN_SHARED_TERMS = 2

#: ...worth this much together, each word ln(N/df) over the index set:
#: "elongated" (df 16) + "skull" (df 33) score 9.2; "temple" + "Egypt" (df 96
#: and 97) score 6.4 and do not qualify.
MIN_TOPIC_SCORE = 7.0

_TOKEN = re.compile(r"[^\W_]+")

# Function words and the news register's own vocabulary. Rarity weighting
# alone keeps them low, but "claims" or "reveals" in two headlines is no
# reason to call two stories related.
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from had has
    have he her his how in into is it its may might more most new no not of on
    or our over she so than that the their them then there these they this
    those to too under up upon was we were what when where which who why will
    with without would yet about after against all also among around before
    between both during each few many much other out own same some such through
    very while video videos claim claims claimed reveal reveals revealed show
    shows showing shown suggest suggests suggested say says said speaker
    discuss discusses discussed new evidence study studies finding findings
    found find finds year years old ancient long early first large
    """.split()
)

_TIERS = {"site": 0, "place": 1, "country": 2, "topic": 3, "category": 4}

#: Categories too broad to relate two stories: "general" holds 804 of the
#: 2,317 index stories (2026-10-20), two of the elongated-skull cluster among
#: them.
_BROAD_CATEGORIES = frozenset({"", "general"})


@dataclass(frozen=True)
class StoryRow:
    """The fields the ranking reads — one public story."""

    id: int
    headline: str
    tags: tuple[str, ...]
    site_id: str
    place: str
    country: str
    significance: int
    created_at: datetime
    news_category: str


def _stem(word: str) -> str:
    """Plural to singular, nothing more: "skulls" and "skull" are one word."""
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


# Cached per row value (a changed headline or tag list is a new key): one
# ranking over the 2,317 candidates took 55 ms cold and 10-13 ms warm
# (2026-10-20, workstation).
@lru_cache(maxsize=16384)
def terms(row: StoryRow) -> frozenset[str]:
    """The topic words of a story: headline and tags, tag underscores split."""
    text = " ".join([row.headline, *(t.replace("_", " ") for t in row.tags)])
    return frozenset(
        _stem(w)
        for w in (m.group(0).casefold() for m in _TOKEN.finditer(text))
        if len(w) >= 3 and not w.isdigit() and w not in _STOPWORDS
    )


def _place_key(place: str) -> str:
    return " ".join(place.casefold().split())


def related_stories(
    story: StoryRow, candidates: list[StoryRow], limit: int = RELATED_LIMIT
) -> list[tuple[StoryRow, str]]:
    """Up to ``limit`` (row, kind) picks for ``story``, best first.

    ``candidates`` is every public story; ``story`` itself may be among them
    and is skipped. The document frequencies count the whole set.
    """
    vocab = {row.id: terms(row) for row in candidates}
    own_terms = terms(story)
    df: Counter[str] = Counter()
    for words in vocab.values():
        df.update(words)
    n = len(candidates)
    own_place = _place_key(story.place)
    own_category = story.news_category if story.news_category not in _BROAD_CATEGORIES else ""

    picks = []
    for row in candidates:
        if row.id == story.id:
            continue
        shared = own_terms & vocab[row.id]
        score = sum(math.log(n / df[w]) for w in shared)
        if story.site_id and row.site_id == story.site_id:
            kind = "site"
        elif own_place and _place_key(row.place) == own_place:
            kind = "place"
        elif story.country and row.country == story.country:
            kind = "country"
        elif len(shared) >= MIN_SHARED_TERMS and score >= MIN_TOPIC_SCORE:
            kind = "topic"
        elif own_category and row.news_category == own_category:
            kind = "category"
        else:
            continue
        picks.append(
            (
                _TIERS[kind],
                -score,
                -row.significance,
                -row.created_at.timestamp(),
                -row.id,
                row,
                kind,
            )
        )
    picks.sort(key=lambda p: p[:5])
    chosen = [p for p in picks if p[6] != "category"][:limit]
    # The category only fills a short block up to the minimum (see RELATED_MIN).
    chosen += [p for p in picks if p[6] == "category"][: max(0, RELATED_MIN - len(chosen))]
    return [(p[5], p[6]) for p in chosen]
