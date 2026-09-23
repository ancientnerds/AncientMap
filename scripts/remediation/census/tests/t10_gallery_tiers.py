"""T10 - every `wiki_images` row of a curated site gets a triage tier.

The plan's Phase 1 item 10 is "Compute gallery signals S/A/B/D/E/P/F -> tier assignment per
image", and §6.5 spends that triage in Phase 2: tier D is audited by **zero** VLM calls,
tier A (heroes) and tier B (the CORE signal `S|A|B|D|E`) by **one each**, tier C is
sampled at 3 images per site. A tier is therefore an economic decision, not a claim about
the world: getting it wrong spends or saves VLM money, and the one thing that must never
happen is an image landing in tier D because a signal could not be computed. "Could not
check" must not become "checked and clean", so every signal that is unknown keeps its row
out of D.

Signal by signal - what this module can stand behind, and why
-------------------------------------------------------------
**S - same Commons file attached to a differently named site. FAITHFUL, no network.**
Computed from the snapshot alone: group the rows by the Commons file they reference
(`commons_file_name`, the same URL parsing T09 uses - one spelling of "which Commons file
is this row"), and collect the *normalised* site names of the sites that use it. A file
whose set of names has more than one member is S. Names are compared after NFKD
de-accenting, casefolding and dropping non-alphanumerics, so "merida" and "mérida" are
one name and only a genuinely different name flags. Two curated rows
carrying the identical name are *not* "differently named" and are therefore not S.

**F - own site name absent from title + filename + Commons name. FAITHFUL, no network.**
Computed from the row. The site's own `name` is searched as a *phrase* in the normalised
`title` + `filename` + Commons file name, with alphanumeric boundaries. Phrase, not token:
"Nazca Lines" is present in "Nazca Lines from the air" and absent from "Nasca lines" - an
approximation of "the name", but the only one that can be stated exactly.

**P - the file is NOT in the site's P373 category. FAITHFUL, and it must be fetched.**
P373 is the Wikidata property holding the Commons category name. The project reads it
exactly that way - `pipeline/wiki_image_downloader.py:392` (`get_string_value`) and `:402`
(`result["commons_category"] = get_string_value("P373")`) - and then lists that category
with `generator=categorymembers` + `gcmtitle=Category:<name>` + `gcmtype=file`
(`pipeline/wiki_image_downloader.py:492-502`), one subcategory level deep
(`_fetch_subcategory_names`, `:537`; `fetch_commons_category_images`, `:577-598`: "Crawls
1 level deep"). Two API facts decided the shape used here:

* `prop=categories` answers for a `File:` title just as well as for a `Category:` title
  (verified live 2026-09-21 against `commons.wikimedia.org/w/api.php`), and the question is
  "is this file in that category" - the file side. Asking per file costs ~1,000 batched
  requests for the 46,070 referenced files, instead of one request per category *and* one
  per subcategory on the category side (~15,000+, and again per run).
* "One subcategory level" means a file reachable from the site's category is one *hop down*
  from it: the file sits in a category whose parent is the site's category. The collector
  therefore fetches each file's own categories **and** their parents, and membership is
  `site_category in file_categories or site_category in parents(file_categories)`. Without
  that hop, a file the project's own downloader would have fetched from the site's category
  would be reported as "not in the category" - a contradiction inside the project.
  The downloader's other limit - `max_per_category=20` at `:859`, passed through to
  `fetch_commons_category_images(category, limit=...)` at `:908` - is an *acquisition*
  budget (how many images to download), not a membership rule, so it is deliberately **not**
  applied here. The strict reading (direct membership only) is counted in the run log, so
  what this choice costs is measured rather than assumed.

**D - place token of a curated site more than 50 km away. RECONSTRUCTED from the snapshot.**
The plan's 4,396-token dictionary is not in this repository (grep for place_token /
museum_city / non_photo finds nothing in the tree or in the git history), so this is **not**
the plan's list. The plan states its own source - "place token of a curated site" - and the
5,004 curated sites with their coordinates are in the snapshot, so the dictionary is derived
here instead of invented: the tokens of **length >= 4** from the normalised site names
(5,825 of them), each mapped to the coordinates of the sites whose name contains it. For an
image, a token of `title`/`filename`/Commons name hits when the **nearest** site carrying
that token is more than 50 km from the image's site.

The distance rule alone is not enough, and that is measured rather than argued: 4,900 of the
tokens belong to exactly one curated name, but the rest are ordinary words that some site
name happens to contain ("temple" in 156 names, "roman" in 205, "from" in 2), and they made D
fire on **18,670 of 49,691 rows (37.6 %)** - against the plan's D at 1.7 % of its labelled
sample. What separates a place from a type word is rarity in the corpus being matched, so the
dictionary is cut to the plan's own size (4,396 tokens) by document frequency in the image
corpus, ties broken by fewer carriers and then alphabetically. That drops "from" (df 1,425),
"roman" (1,346), "temple" (1,204), "museum" (872), "stone" (756), "ancient" (752), "hill"
(706), "site" (663) and 1,421 others, and D falls to 2,089 rows (4.2 %) - the plan's order of
magnitude, reached by a rule stated up front and not by tuning towards the plan's numbers.

**E - non-photo word. PARTIAL RECONSTRUCTION - six of 67 terms.**
The plan prints six of its 67 terms - "map, plan, drawing, painting, diagram, engraving,
..." (§6.4) - and nothing in the repository carries the list. Those six are used verbatim
(token, or token + "s"); **no other term is guessed**, because a guessed term would be
presented as the plan's signal. Consequence, stated rather than hidden: E is **under-flagged
here by an unknown factor**, and every image the missing 61 terms would have caught is not
flagged by this census.

**A - museum word in the title, filename or Commons category. NARROW RECONSTRUCTION.**
The plan's list is gone too; the principle it states is "museum word". Reconstructed as the
one lexeme *museum* in the spellings that occur in Commons titles and categories
(EN/DE/FR/ES/PT/IT plus the Scandinavian and Slavic forms spelled with the same letters).
Matching sees the file's Commons categories as well, which the P fetch delivers anyway. This
is narrower than the plan's A, which fired on 62 of 652 labelled images (9.5 %).

**B - museum city more than 150 km away. UNAVAILABLE, and deliberately not fabricated.**
The 41-city list with coordinates is neither in the repository nor in its history, and no
principle in the plan determines *which* 41 cities. Inventing a list would put a plausible
number behind a signal nobody can reproduce, so B is reported as unavailable (recorded as
`null` in every finding's signal vector) and CORE is computed as `S|A|D|E`.

What that means for CORE, and for tier D
----------------------------------------
CORE here is a **subset** of the plan's CORE (B is missing, A and E are narrower), so the
suspect tier is under-flagged by an unknown amount and the plan's stage-1 precision/recall
figures (33.1 % / 76.9 %) do not transfer. The reverse error - something dirty landing in
tier D - is guarded mechanically: D is assigned only when P is *proven* false (the site's
category is known **and** the file's categories are known **and** the category matches),
the own name is in the filename, and no word or cross-site signal fired.

Precedence, chosen and documented (the plan does not resolve the overlaps)
--------------------------------------------------------------------------
1. **A hero (tier A) wins over every other tier.** The plan names heroes as tier A and
   audits *all* of them whatever their signals say, because they are the maximally visible
   image on the page (`ORDER BY is_hero DESC` in `api/routes/sites_html.py:331`).
2. **Suspect (tier B) wins over clear (tier D).** An image can satisfy both: the plan's safe
   class asks only for "in the P373 category and no *word* signal", and S is not a word
   signal. S is one of the strongest contamination signals the plan measured (precision
   38.5 % on 78 flagged images), so letting D win would send an image that the plan's own
   stage 1 VLM-audits straight into the zero-call stage. The overlap is counted and logged.
3. Otherwise **D (clear)** when proven in-category + no word signal + own name in the
   filename, and **C (grey)** for everything else - including every row whose P could not be
   established, which is the "could not check is not clean" rule in one line.

Nothing here is auto-applicable and nothing writes to the database: a tier is a work order
for Phase 2, so every finding carries `Proposal.NONE` and `Confidence` says how much of the
vector was measured (`AUTHORITATIVE` when P was proven, `WEAK` when it was not but a CORE
signal fired, `UNVERIFIABLE` when P is unknown and only snapshot signals spoke).

The module does **not** pick the 3 sampled images per site for tier C. §6.5 leaves that
sample to the audit stage ("one hit escalates that site's entire gallery"); freezing a
selection rule here would decide something the plan does not, and the C rows are the pool.

One deliberate deviation from the census's request convention
------------------------------------------------------------
`scripts/remediation/census/fetch.py` sends `maxlag=5` on API calls, "so a lagging replica
yields 503 instead of load". The collector respects that - until the server itself reports
maxlag. Measured 2026-09-21 between 22:10 and 22:30, Wikidata answered
`maxlag: Waiting for wdqs1013: 446 seconds lagged` to 66 of its 93 `wbgetentities` batches
for the whole half hour (the lag grew from 148 s to 446 s while retrying), naming the
*query service* rather than the API's own replicas. `maxlag` is a politeness throttle, not
a check on the data, and no retry budget clears a 446 s window, so on a maxlag answer the
request is repeated without the parameter - counted, logged, and recorded in the index as
`stats.wikidata_maxlag_retries` so the artifact states how often that was needed.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from census.fetch import FetchError
from census.model import Confidence, Evidence, Finding, Proposal, Severity
from census.tests.t09_commons_dimensions import _commons_file_name as commons_file_name

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T10"
NAME = "gallery triage: per-image tier from the measured signals"
DIMENSION = "images / gallery triage"

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

#: 50 is the anonymous limit for both `wbgetentities` ids and `titles` per request.
WD_BATCH = 50
TITLE_BATCH = 50

#: `cllimit=max` is 500 categories per response, so a 50-title batch needs a continuation
#: once its pages carry more than 500 categories between them.
MAX_CONTINUATIONS = 20

CACHE_NS_WD = "t10_wikidata"
CACHE_NS_CAT = "t10_commons"

INDEX_NAME = "gallery_signals.json"
#: Version of the *file* and *parent* part files. Schema 2 stores the raw Commons category
#: titles next to the normalised names, because only the raw title can be asked for: the
#: normalised form ("cc by sa 3 0") is not a page title ("CC-BY-SA-3.0"). Schema 1 part
#: files are therefore not reused - re-running the sweep costs cache reads, not requests.
PART_SCHEMA = 2
PART_FILES = "gallery_signals.files.json"
PART_PARENTS = "gallery_signals.parents.json"
PART_P373 = "gallery_signals.p373.json"

#: §6.4, verbatim: the plan prints six of its 67 non-photo terms. The other 61 are not in
#: this repository and are not guessed - see the module docstring.
NON_PHOTO_TERMS: tuple[str, ...] = ("map", "plan", "drawing", "painting", "diagram", "engraving")

#: Reconstruction of §6.4's "museum word" (see the docstring), normalised on import.
MUSEUM_WORDS_RAW: tuple[str, ...] = (
    "museum",
    "museums",
    "museen",
    "musee",
    "musees",
    "museo",
    "museos",
    "museu",
    "museus",
    "museet",
    "muzeum",
    "müze",
)

#: D's dictionary is derived from the curated site names; tokens shorter than this are
#: articles and prepositions ("el", "abu", "of", "the") and identify nothing.
PLACE_TOKEN_MIN_LEN = 4
#: §6.4 "place token of a curated site > 50 km away".
PLACE_TOKEN_MIN_KM = 50.0
#: Size of the reconstructed place dictionary - the plan's own figure for its lost one
#: ("dictionary of 4,396 tokens", §6.4). Used as the *size*, never as a target for what D
#: then does; see `distinctive_place_tokens` for the selection rule and its measurement.
PLACE_TOKEN_BUDGET = 4396

#: Why signal B is not computed. Recorded as `null` in every finding's signal vector and
#: printed once per run, so no run can look like it checked all seven.
B_MUSEUM_CITY = "unavailable: the plan's 41-city list with coordinates is not in this repository"

HERO, SUSPECT, GREY, CLEAR = "A", "B", "C", "D"
TIER_LABEL = {HERO: "hero", SUSPECT: "suspect", GREY: "grey", CLEAR: "clear"}

log = logging.getLogger("census.t10")

_NON_ALNUM = re.compile(r"[^0-9a-zA-Z]+")
_WS = re.compile(r"\s+")
_CATEGORY_PREFIX = re.compile(r"^\s*category\s*:\s*", re.I)


def normalize_text(value: Any) -> str:
    """Casefolded, de-accented, alphanumeric-only text - the one normal form used here.

    NFKD plus combining-mark removal turns "Merida" with an accent into "merida";
    casefolding before the non-alphanumeric sweep keeps "ss" for a German sharp s instead
    of dropping it.
    """
    s = unicodedata.normalize("NFKD", str(value if value is not None else ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    return _WS.sub(" ", _NON_ALNUM.sub(" ", s)).strip()


def words(value: Any) -> list[str]:
    return normalize_text(value).split()


def normalize_category(value: Any) -> str:
    """A Commons category name in the one form both sides of the comparison use."""
    return normalize_text(_CATEGORY_PREFIX.sub("", str(value if value is not None else "")))


NON_PHOTO_TERMS_NORM: tuple[str, ...] = tuple(normalize_text(t) for t in NON_PHOTO_TERMS)
MUSEUM_WORDS: tuple[str, ...] = tuple(sorted({normalize_text(w) for w in MUSEUM_WORDS_RAW}))


def matches_term(word: str, terms: tuple[str, ...]) -> bool:
    """A term or its plural - the whole token, never a substring.

    "plan" must not match "plant" and "map" must not match "mapping".
    """
    if word in terms:
        return True
    return word.endswith("s") and word[:-1] in terms


def matched_terms(text_words: list[str], terms: tuple[str, ...]) -> list[str]:
    return sorted({w for w in text_words if matches_term(w, terms)})


def name_in_text(name_norm: str, haystack_norm: str) -> bool:
    """Is the normalised site name present in the normalised text as a phrase?

    Alphanumeric boundaries only: "dara" is in "dara fortress", not in "darax".
    """
    if not name_norm:
        return False
    return re.search(rf"(?<![0-9a-z]){re.escape(name_norm)}(?![0-9a-z])", haystack_norm) is not None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------- site context
@dataclass
class SiteContext:
    """Everything the signal vectors need from `unified_sites`, built once per run."""

    names: dict[str, str] = field(default_factory=dict)
    norm_names: dict[str, str] = field(default_factory=dict)
    coords: dict[str, tuple[float, float]] = field(default_factory=dict)
    #: place token -> the sites carrying it, with coordinates (D's dictionary)
    place_tokens: dict[str, list[tuple[str, float, float]]] = field(default_factory=dict)

    def nearest_place(self, token: str, site_id: str) -> tuple[str, float] | None:
        """The nearest site carrying `token` and its distance, or None if unplaced.

        The image's own site is part of the comparison on purpose: a token of the site's
        own name is 0 km away and therefore never a D hit.
        """
        here = self.coords.get(site_id)
        sites = self.place_tokens.get(token)
        if here is None or not sites:
            return None
        best: tuple[str, float] | None = None
        for other_id, lat, lon in sites:
            km = 0.0 if other_id == site_id else haversine_km(here[0], here[1], lat, lon)
            if best is None or km < best[1]:
                best = (other_id, km)
        return best


def build_site_context(sites: list[dict[str, Any]]) -> SiteContext:
    """Index the curated sites: names, coordinates, and D's token dictionary."""
    sc = SiteContext()
    for site in sites:
        sid = str(site["id"])
        sc.names[sid] = str(site.get("name") or "")
        sc.norm_names[sid] = normalize_text(sc.names[sid])
    for site in sites:
        lat, lon = site.get("lat"), site.get("lon")
        if lat is None or lon is None:
            continue
        sc.coords[str(site["id"])] = (float(lat), float(lon))
    for sid, norm in sc.norm_names.items():
        here = sc.coords.get(sid)
        if here is None:
            continue
        for token in {w for w in norm.split() if len(w) >= PLACE_TOKEN_MIN_LEN}:
            sc.place_tokens.setdefault(token, []).append((sid, here[0], here[1]))
    return sc


def distinctive_place_tokens(
    sc: SiteContext, rows: Iterable[dict[str, Any]], budget: int = PLACE_TOKEN_BUDGET
) -> list[str]:
    """Drop the tokens that are *not* place names, and return the dropped ones for the log.

    A dictionary read off 5,004 site names mixes two kinds of token: the names of places
    ("ishtar", "cueva", "peri") and the words that merely occur in a site name somewhere
    ("temple" in 156 of them, "roman" in 205, "from" in 2). The distance rule does not
    separate them - the nearest site carrying "temple" is usually far away, so the first
    version of this signal fired on 18,670 of 49,691 rows (37.6 %), against the plan's D at
    1.7 % of its labelled sample. What separates them is rarity in the corpus being matched:
    a place name is rare in file names and titles, a type word is not.

    The cut only bites when there are more candidates than the budget - production has 5,825
    against 4,396 - so `run` logs both counts rather than assuming it did.

    So the 4,396 tokens (the plan's dictionary size, §6.4) with the lowest document frequency
    in the image corpus are kept, ties broken by fewer curated sites carrying the token and
    then alphabetically. Measured 2026-09-21 over the whole snapshot: 855 of 5,825 candidates
    never occur in any image text at all, the cut drops "from" (df 1,425), "roman" (1,346),
    "temple" (1,204), "museum" (872), "stone" (756), "ancient" (752), "hill" (706), "site"
    (663), "tomb" (590), "fort" (521), "castle" (509) - and D falls from 18,670 rows to
    2,089 (4.2 %), the plan's order of magnitude. The cut's margin is arbitrary - the tokens
    at it fire on one or two images - and harmless: a missed D hit leaves the row in tier C,
    which §6.5 samples, rather than putting anything into the zero-call tier.
    """
    frequency: Counter[str] = Counter()
    for row in rows:
        for token in {w for w in image_haystack(row).split() if len(w) >= PLACE_TOKEN_MIN_LEN}:
            if token in sc.place_tokens:
                frequency[token] += 1
    ranked = sorted(
        sc.place_tokens, key=lambda tok: (frequency[tok], len(sc.place_tokens[tok]), tok)
    )
    kept = set(ranked[:budget])
    # returned most-generic-first, which is what a log wants to name; the tokens at the
    # margin all fire on one or two images, so which side of the cut they land on is
    # arbitrary - and cheap either way (a missed D hit only keeps the row out of tier D).
    dropped = [tok for tok in ranked if tok not in kept]
    sc.place_tokens = {tok: sites for tok, sites in sc.place_tokens.items() if tok in kept}
    return list(reversed(dropped))


def cross_site_shares(ctx: Context, sc: SiteContext) -> dict[str, set[str]]:
    """Commons file -> the distinct normalised site names using it (only when > 1).

    The `S` signal: a file whose sites do not all carry the same name is attached to a
    differently named site. Rows without a Commons file reference cannot be grouped and are
    simply absent - S is unknown for them, never False.
    """
    out: dict[str, set[str]] = defaultdict(set)
    for row in ctx.snap.rows("wiki_images"):
        name = commons_file_name(row)
        sid = str(row["site_id"])
        if name and sid in sc.norm_names:
            out[name].add(sc.norm_names[sid])
    return {name: names for name, names in out.items() if len(names) > 1}


# --------------------------------------------------------------------- API access / fetch
def _api_json(
    ctx: Context,
    api: str,
    params: dict[str, Any],
    ns: str,
    stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    """One API answer, or a raised error - never an empty result.

    Wikimedia reports `maxlag` and other transient trouble as HTTP 200 with an `error`
    object, and the Fetcher caches whatever came back. A naive read would store that as
    "this entity has no P373" for up to 50 sites, so the error is detected, refetched past
    the cache, and raised if it persists.

    `maxlag` alone gets a second answer, and it is a deliberate deviation from the census's
    `maxlag=5` convention (`fetch.py`): measured 2026-09-21 22:10-22:30, Wikidata answered
    `maxlag: Waiting for wdqs1013: 446 seconds lagged` to 66 of 93 `wbgetentities` batches,
    naming the *query service* rather than the API's own replicas, and the window lasted
    longer than any retry budget. `maxlag` is a politeness throttle, not a check on the
    data, and this is a read-only sweep of 93 batches - so after the server itself reports
    maxlag the request is repeated without the parameter, and every occurrence is counted
    into `stats` so the artifact states how often that was necessary.
    """
    net = ctx.net()
    last = ""
    for attempt in range(4):
        payload = net.get_json(api, params, ns=ns, force=attempt > 0)
        body = payload.get("json") or {}
        err = body.get("error")
        if not err:
            if "query" not in body and "entities" not in body:
                raise RuntimeError(
                    f"{api}: response without 'query'/'entities' for "
                    f"{params.get('titles') or params.get('ids')!r}"
                )
            return body
        last = f"{err.get('code')}: {err.get('info')}"
        if err.get("code") == "maxlag" and "maxlag" in params:
            params = {k: v for k, v in params.items() if k != "maxlag"}
            if stats is not None:
                stats["maxlag"] = stats.get("maxlag", 0) + 1
            log.warning("%s answered maxlag, repeating without the parameter: %s", api, last)
        else:
            log.warning("%s error (attempt %d/4): %s", api, attempt + 1, last)
    raise RuntimeError(f"{api} refused a batch: {last}")


def _page_records(
    ctx: Context, titles: list[str], ns: str
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """`({canonical title: {"missing": bool, "categories": [...]}}, title mapping)`.

    `cllimit=max` caps a response at 500 categories *across* the batch, so a batch of 50
    files with many categories each answers in several pieces; a continuation response
    carries only the pages it advances, which is why the pieces are merged per title rather
    than read as complete answers. The `normalized`/`redirects` entries are collected too,
    so a requested title can be resolved to the page the API actually answered.
    """
    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "categories",
        "cllimit": "max",
        "titles": "|".join(titles),
        "redirects": 1,
        "maxlag": 5,
    }
    pages: dict[str, dict[str, Any]] = {}
    mapping: dict[str, str] = {}
    for _ in range(MAX_CONTINUATIONS):
        body = _api_json(ctx, COMMONS_API, params, ns)
        query = body.get("query") or {}
        for page in query.get("pages") or []:
            title = page.get("title")
            if not title:
                continue
            rec = pages.setdefault(title, {"missing": False, "categories": []})
            rec["missing"] = rec["missing"] or bool(page.get("missing"))
            rec["categories"].extend(
                cat["title"] for cat in page.get("categories") or [] if cat.get("title")
            )
        for entry in (query.get("normalized") or []) + (query.get("redirects") or []):
            mapping[entry["from"]] = entry["to"]
        cont = body.get("continue")
        if not cont:
            return pages, mapping
        params.update(cont)
    raise RuntimeError(
        f"commons: a {len(titles)}-title categories query still had a continuation after "
        f"{MAX_CONTINUATIONS} responses (first title {titles[0]!r}) - refusing to record a "
        "truncated category list"
    )


def _entries_for_titles(
    ctx: Context, titles: list[str], ns: str, splits: list[int]
) -> dict[str, dict[str, Any]]:
    """The category list of every requested title, splitting a batch Commons refuses.

    A batch of 50 long non-Latin titles can exceed the request-URI limit (HTTP 414 - T09
    hit exactly that). That is the one refusal a smaller request fixes.
    """
    from pipeline.utils.mediawiki import dereference

    try:
        pages, mapping = _page_records(ctx, titles, ns)
    except FetchError as exc:
        if "414" not in str(exc) or len(titles) == 1:
            raise
        splits.append(len(titles))
        mid = len(titles) // 2
        log.warning("T10: HTTP 414 on a %d-title batch, asking in two halves", len(titles))
        merged = _entries_for_titles(ctx, titles[:mid], ns, splits)
        merged.update(_entries_for_titles(ctx, titles[mid:], ns, splits))
        return merged

    out: dict[str, dict[str, Any]] = {}
    for title in titles:
        page = pages.get(dereference(title, mapping)) or pages.get(title)
        if page is None:
            # The API may have answered under a different capitalisation of the first
            # letter; that is the same page on Commons, so it is not "unresolved".
            page = next(
                (p for t, p in pages.items() if t.casefold() == title.casefold()), None
            )
        if page is None:
            out[title] = {"status": "unresolved", "title": None, "categories": []}
        elif page["missing"]:
            out[title] = {"status": "missing", "title": title, "categories": []}
        else:
            out[title] = {"status": "ok", "title": title, "categories": sorted(set(page["categories"]))}
    return out


# ------------------------------------------------------------------------------- collect
def _map_batches(
    ctx: Context,
    batches: list[Any],
    fn: Callable[[Any], Any],
    desc: str,
    rounds: int = 3,
    backoff: float = 10.0,
    workers: int | None = None,
) -> list[Any]:
    """Run `fn` over every batch, retrying the ones that failed, order-preserving.

    Wikimedia's `maxlag` is a *window*, not a per-request verdict: measured 2026-09-21,
    Wikidata answered `maxlag: Waiting for wdqs1018: 148 seconds lagged` to 66 of 93
    batches, and the same request answered normally 20 minutes later. Retrying immediately
    therefore burns the whole sweep inside the window, so the rounds are spaced out - and a
    batch that still fails in every round is left as an error for the caller to raise on,
    never dropped.
    """
    out: list[Any] = [None] * len(batches)
    pending = list(range(len(batches)))
    for round_no in range(rounds):
        if not pending:
            break
        got = ctx.net().map(
            fn,
            [batches[i] for i in pending],
            workers=workers,
            desc=f"{desc} (round {round_no + 1})",
        )
        still: list[int] = []
        for index, result in zip(pending, got, strict=True):
            out[index] = result
            if isinstance(result, BaseException):
                still.append(index)
        if still and round_no + 1 < rounds:
            wait = backoff * (round_no + 1)
            log.warning(
                "%s: %d/%d batches failed, retrying in %.0fs", desc, len(still), len(batches), wait
            )
            time.sleep(wait)
        pending = still
    return out


def _part_path(ctx: Context, name: str) -> Path:
    return Path(ctx.cache) / name


def _read_part(ctx: Context, name: str) -> dict[str, Any] | None:
    path = _part_path(ctx, name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("T10: unreadable collection part, re-collecting: %s", path)
        return None
    if not isinstance(payload, dict) or payload.get("snapshot_exported_at") != ctx.snap.exported_at():
        return None
    return payload


def _write_part(ctx: Context, name: str, payload: dict[str, Any]) -> None:
    path = _part_path(ctx, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic: a killed run leaves no half part


def _qids(ctx: Context) -> dict[str, str]:
    """site_id -> Wikidata QID, from the existing anchors (4,618 of 5,004 sites have one)."""
    return ctx.snap.ids_of_kind("wikidata_qid")


def _first_string_claim(claims: dict[str, Any], prop: str) -> str | None:
    """The first *value* of a string property - the same read as the project's connector.

    `pipeline/wiki_image_downloader.py:392-395` takes `claims[prop][0]`; snaks of type
    novalue/somevalue carry no string and are skipped rather than stringified.
    """
    for claim in claims.get(prop) or []:
        snak = claim.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        value = (snak.get("datavalue") or {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sweep_p373(
    ctx: Context, *, rounds: int = 5, backoff: float = 30.0, workers: int = 4
) -> dict[str, dict[str, Any]]:
    """P373 for every site that has a QID. Resumable through a part file and the cache.

    Wikidata is the flaky half of this collector (see `_map_batches`), which is why its
    patience is configurable: the tests exercise the failure path without the waiting.
    """
    qids = _qids(ctx)
    part = _read_part(ctx, PART_P373)
    if part is not None and set(part.get("entries", {})) == set(qids):
        log.info(
            "T10: reusing %d P373 records from %s (%d maxlag retries were needed)",
            len(qids),
            _part_path(ctx, PART_P373),
            part.get("maxlag", 0),
        )
        return part["entries"]

    items = sorted(qids.items())
    batches = [items[i : i + WD_BATCH] for i in range(0, len(items), WD_BATCH)]
    log.info("T10: %d QIDs in %d wbgetentities batches", len(items), len(batches))

    def one(batch: list[tuple[str, str]]) -> dict[str, Any]:
        stats: dict[str, int] = {}
        body = _api_json(
            ctx,
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(q for _, q in batch),
                "props": "claims",
                "format": "json",
                "formatversion": 2,
                "maxlag": 5,
            },
            CACHE_NS_WD,
            stats=stats,
        )
        entities = body.get("entities") or {}
        out: dict[str, dict[str, Any]] = {}
        for sid, qid in batch:
            ent = entities.get(qid)
            if ent is None:
                ent = next((e for e in entities.values() if e.get("id") == qid), None)
            if not ent or "claims" not in ent:
                # not found / redirected away: "we could not find out", never "no category"
                out[sid] = {"qid": qid, "status": "missing", "category": None}
                continue
            category = _first_string_claim(ent.get("claims") or {}, "P373")
            out[sid] = {"qid": qid, "status": "ok" if category else "absent", "category": category}
        return {"entries": out, "maxlag": stats.get("maxlag", 0)}

    results = _map_batches(
        ctx, batches, one, "T10 wikidata P373", rounds=rounds, backoff=backoff, workers=workers
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    if failures:
        raise RuntimeError(
            f"T10: {len(failures)}/{len(batches)} wbgetentities batches failed; first: "
            f"{failures[0]!r}. No P373 part was written - re-run to resume from the cache."
        )
    entries: dict[str, dict[str, Any]] = {}
    maxlag = 0
    for got in results:
        entries.update(got["entries"])
        maxlag += got["maxlag"]
    _write_part(
        ctx,
        PART_P373,
        {
            "api": WIKIDATA_API,
            "batch": WD_BATCH,
            "snapshot_exported_at": ctx.snap.exported_at(),
            "summary": dict(Counter(r["status"] for r in entries.values())),
            "maxlag": maxlag,
            "entries": entries,
        },
    )
    log.info(
        "T10: P373 for %d sites (%s, %d maxlag retr(y|ies) without the parameter)",
        len(entries),
        dict(Counter(r["status"] for r in entries.values())),
        maxlag,
    )
    return entries


def _all_files(ctx: Context) -> list[str]:
    names = {n for row in ctx.snap.rows("wiki_images") if (n := commons_file_name(row))}
    return sorted(names)


def _sweep_files(ctx: Context) -> dict[str, dict[str, Any]]:
    """The Commons categories of every referenced file. Resumable (part file + cache)."""
    names = _all_files(ctx)
    part = _read_part(ctx, PART_FILES)
    if (
        part is not None
        and part.get("schema") == PART_SCHEMA
        and set(part.get("entries", {})) == set(names)
    ):
        log.info("T10: reusing category lists for %d files from %s", len(names), _part_path(ctx, PART_FILES))
        return part["entries"]

    batches = [names[i : i + TITLE_BATCH] for i in range(0, len(names), TITLE_BATCH)]
    log.info("T10: %d distinct Commons files in %d category batches", len(names), len(batches))
    splits: list[int] = []
    results = _map_batches(
        ctx,
        batches,
        lambda b: _entries_for_titles(ctx, [f"File:{n}" for n in b], CACHE_NS_CAT, splits),
        "T10 commons file categories",
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    if failures:
        raise RuntimeError(
            f"T10: {len(failures)}/{len(batches)} category batches failed; first: "
            f"{failures[0]!r}. No file part was written - re-run to resume from the cache."
        )
    entries: dict[str, dict[str, Any]] = {}
    for batch, got in zip(batches, results, strict=True):
        for name in batch:
            rec = got.pop(f"File:{name}", None) or {"status": "unresolved", "categories": []}
            entries[name] = {
                "status": rec["status"],
                "categories": sorted({normalize_category(c) for c in rec["categories"]}),
                "raw_categories": sorted(set(rec["categories"])),
            }
    _write_part(
        ctx,
        PART_FILES,
        {
            "api": COMMONS_API,
            "schema": PART_SCHEMA,
            "batch": TITLE_BATCH,
            "split_batches": len(splits),
            "snapshot_exported_at": ctx.snap.exported_at(),
            "summary": dict(Counter(r["status"] for r in entries.values())),
            "entries": entries,
        },
    )
    log.info(
        "T10: category lists for %d files (%s)",
        len(entries),
        dict(Counter(r["status"] for r in entries.values())),
    )
    return entries


def _sweep_parents(ctx: Context, files: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The parents of every category the files carry - the "one subcategory level" hop.

    Asked by the **raw** Commons title, keyed by the normalised name. The normalised form is
    for comparison, not for the API: measured 2026-09-21, `Category:dara fortress` does not
    exist for "Category:Dara (Fortress)" - 26 of 26 raw titles resolved against 5 of 26
    normalised ones, and the first version of this sweep asked the normalised names and
    found parents for only 6,703 of 47,636 categories. A normalised name can stand for
    several raw titles (hyphen, parenthesis, diacritic), so all of them are asked and their
    parents merged.
    """
    by_norm: dict[str, set[str]] = {}
    for rec in files.values():
        if rec["status"] != "ok":
            continue
        for raw in rec.get("raw_categories") or []:
            by_norm.setdefault(normalize_category(raw), set()).add(raw)
    cats = sorted(by_norm)
    part = _read_part(ctx, PART_PARENTS)
    if (
        part is not None
        and part.get("schema") == PART_SCHEMA
        and set(part.get("entries", {})) == set(cats)
    ):
        log.info("T10: reusing parent lists for %d categories from %s", len(cats), _part_path(ctx, PART_PARENTS))
        return part["entries"]

    titles = sorted({raw for raws in by_norm.values() for raw in raws})
    batches = [titles[i : i + TITLE_BATCH] for i in range(0, len(titles), TITLE_BATCH)]
    log.info(
        "T10: %d category names (%d Commons titles) in %d parent batches",
        len(cats),
        len(titles),
        len(batches),
    )
    splits: list[int] = []
    results = _map_batches(
        ctx,
        batches,
        # `raw_categories` holds whole Commons page titles ("Category:Dara (Fortress)"),
        # exactly as the API returned them - they are asked verbatim, never re-prefixed.
        lambda b: _entries_for_titles(ctx, list(b), CACHE_NS_CAT, splits),
        "T10 commons category parents",
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    if failures:
        raise RuntimeError(
            f"T10: {len(failures)}/{len(batches)} parent batches failed; first: "
            f"{failures[0]!r}. No parent part was written - re-run to resume from the cache."
        )
    answered: dict[str, dict[str, Any]] = {}
    for batch, got in zip(batches, results, strict=True):
        for title in batch:
            answered[title] = got.pop(title, None) or {
                "status": "unresolved",
                "categories": [],
            }
    entries: dict[str, dict[str, Any]] = {}
    for norm in cats:
        raws = sorted(by_norm[norm])
        recs = [answered[raw] for raw in raws]
        found = [r for r in recs if r["status"] == "ok"]
        status = (
            "ok"
            if found
            else ("missing" if all(r["status"] == "missing" for r in recs) else "unresolved")
        )
        entries[norm] = {
            "status": status,
            "parents": sorted({normalize_category(p) for r in recs for p in r["categories"]}),
            "titles": raws,
        }
    _write_part(
        ctx,
        PART_PARENTS,
        {
            "api": COMMONS_API,
            "schema": PART_SCHEMA,
            "batch": TITLE_BATCH,
            "split_batches": len(splits),
            "snapshot_exported_at": ctx.snap.exported_at(),
            "summary": dict(Counter(r["status"] for r in entries.values())),
            "entries": entries,
        },
    )
    log.info(
        "T10: parent lists for %d categories (%s)",
        len(entries),
        dict(Counter(r["status"] for r in entries.values())),
    )
    return entries


def collect(ctx: Context) -> None:
    """Fetch P373 and the Commons category graph, then fold them into one index.

    Three sweeps, each writing its own part file when it finishes, so a run that is cut off
    (the T07 lane before this one died at its timeout) keeps the finished sweeps and
    continues from the Fetcher's per-request cache. The index is written last and
    atomically, and `_read_index` refuses an index that does not cover every referenced
    file, every category of those files and every QID - a partial sweep can therefore never
    pass for a complete one.
    """
    p373 = _sweep_p373(ctx)
    files = _sweep_files(ctx)
    parents = _sweep_parents(ctx, files)
    p373_part = _read_part(ctx, PART_P373) or {}
    index = {
        "wikidata_api": WIKIDATA_API,
        "commons_api": COMMONS_API,
        "batch": TITLE_BATCH,
        "snapshot_exported_at": ctx.snap.exported_at(),
        "stats": {"wikidata_maxlag_retries": p373_part.get("maxlag", 0)},
        "counts": {"sites_with_qid": len(p373), "files": len(files), "categories": len(parents)},
        "p373": p373,
        "files": files,
        "parents": parents,
    }
    path = _index_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    log.info(
        "T10: index with %d P373 records, %d file category lists, %d parent lists -> %s",
        len(p373),
        len(files),
        len(parents),
        path,
    )


# --------------------------------------------------------------------------- index access
@dataclass
class SignalIndex:
    """The fetched half: P373 per site, categories per file, parents per category."""

    p373: dict[str, dict[str, Any]]
    files: dict[str, dict[str, Any]]
    parents: dict[str, dict[str, Any]]
    stats: dict[str, Any] = field(default_factory=dict)
    _cats: dict[str, tuple[frozenset[str], frozenset[str]]] = field(default_factory=dict)

    def categories(self, file_name: str) -> tuple[frozenset[str], frozenset[str]] | None:
        """`(direct categories, categories one subcategory level down)` of a Commons file.

        None when the file's own category list is unknown - the caller must then treat P as
        unproven instead of as "not in the category".
        """
        rec = self.files.get(file_name)
        if rec is None or rec["status"] != "ok":
            return None
        cached = self._cats.get(file_name)
        if cached is not None:
            return cached
        direct = frozenset(rec["categories"])
        reach = set(direct)
        for cat in direct:
            reach.update(self.parents.get(cat, {}).get("parents") or [])
        out = (direct, frozenset(reach))
        self._cats[file_name] = out
        return out


def _index_path(ctx: Context) -> Path:
    return Path(ctx.cache) / INDEX_NAME


def _read_index(ctx: Context) -> SignalIndex:
    """The fetched signals, or a clear failure - never a silently empty result.

    Coverage is asserted on all three halves. A file with no category list would read as
    "not in the category" for every one of its images, and a category with no parent list
    would make the one-subcategory-level hop silently miss - both turn "could not check"
    into a tier, which is the inversion this census exists to prevent.
    """
    path = _index_path(ctx)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing - run the collector first "
            "(`run.py --tests T10 --collect-only`), then the census against the same cache"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    exported = ctx.snap.exported_at()
    if payload.get("snapshot_exported_at") != exported:
        raise RuntimeError(
            f"{path} was collected from snapshot {payload.get('snapshot_exported_at')!r} but "
            f"the snapshot in use is {exported!r} - re-collect before trusting the tiers"
        )
    p373: dict[str, dict[str, Any]] = payload["p373"]
    files: dict[str, dict[str, Any]] = payload["files"]
    parents: dict[str, dict[str, Any]] = payload["parents"]

    expected_qids = set(_qids(ctx))
    if set(p373) != expected_qids:
        absent = sorted(expected_qids - set(p373))
        extra = sorted(set(p373) - expected_qids)
        raise RuntimeError(
            f"{path} does not match this snapshot: {len(absent)} QID anchor(s) without a P373 "
            f"record (first: {absent[:3]}), {len(extra)} record(s) for sites without one"
        )
    expected_files = set(_all_files(ctx))
    if set(files) != expected_files:
        absent = sorted(expected_files - set(files))
        extra = sorted(set(files) - expected_files)
        raise RuntimeError(
            f"{path} does not match this snapshot: {len(absent)} referenced file(s) without a "
            f"category list (first: {absent[:3]}), {len(extra)} list(s) no longer referenced"
        )
    expected_cats = {c for rec in files.values() for c in rec["categories"]}
    missing_cats = sorted(expected_cats - set(parents))
    if missing_cats:
        raise RuntimeError(
            f"{path}: {len(missing_cats)} categor(y|ies) of referenced files have no parent "
            f"record (first: {missing_cats[:3]}) - the one-subcategory-level hop would be "
            "incomplete; re-collect"
        )
    return SignalIndex(
        p373=p373, files=files, parents=parents, stats=payload.get("stats") or {}
    )


# --------------------------------------------------------------------------------- signals
@dataclass(frozen=True)
class Signals:
    """One image's signal vector. `None` is "not computed", and never equals "clean"."""

    same_file_other_site: bool | None  # S
    no_own_name: bool | None  # F
    name_in_filename: bool  # the filename half of D's own-name condition
    in_category: bool | None  # not P, one subcategory level included
    in_category_direct: bool | None  # not P, direct membership only (sensitivity only)
    museum_word: bool  # A
    other_place_token: bool  # D
    non_photo_word: bool  # E
    place_hits: tuple[tuple[str, str, float], ...] = ()  # (token, nearest site, km)
    medium_hits: tuple[str, ...] = ()  # the E terms that matched
    museum_hits: tuple[str, ...] = ()  # the A words that matched
    category: str | None = None  # the site's P373 category, when known
    share_partners: tuple[str, ...] = ()  # the other site names sharing the file

    @property
    def core(self) -> bool:
        """§6.4 CORE = S|A|B|D|E, minus B which is unavailable (see the module docstring)."""
        return (
            bool(self.same_file_other_site)
            or self.museum_word
            or self.other_place_token
            or self.non_photo_word
        )

    def to_json(self) -> dict[str, Any]:
        """The vector as recorded: `None` marks the signals that could not be computed."""
        return {
            "S": self.same_file_other_site,
            "A": self.museum_word,
            "B": None,  # unavailable - the 41-city list is gone
            "D": self.other_place_token,
            "E": self.non_photo_word,
            "P": None if self.in_category is None else not self.in_category,
            "F": self.no_own_name,
        }

    def fired(self) -> list[str]:
        return [
            name
            for name, value in (
                ("S", self.same_file_other_site),
                ("A", self.museum_word),
                ("D", self.other_place_token),
                ("E", self.non_photo_word),
            )
            if value
        ]


def image_haystack(img: dict[str, Any]) -> str:
    """The normalised text the word signals are matched against.

    §6.4 anchors A in "title or Commons category" and B in "the title"; D and E state no
    channel. All of them see `title` + `filename` + the Commons file name - a wider channel
    than any single reading, which errs towards a VLM call rather than towards the zero-call
    tier. A additionally sees the file's Commons categories, which the P fetch delivers.
    """
    parts = [
        str(img.get("title") or ""),
        str(img.get("filename") or ""),
        commons_file_name(img) or "",
    ]
    return normalize_text(" ".join(parts))


def signals_for(
    img: dict[str, Any],
    site_id: str,
    sc: SiteContext,
    index: SignalIndex,
    shares: dict[str, set[str]],
) -> Signals:
    """Compute the signal vector of one `wiki_images` row, purely from snapshot + index."""
    haystack = image_haystack(img)
    tokens = haystack.split()
    name = sc.norm_names.get(site_id, "")

    file_name = commons_file_name(img)
    if file_name is None:
        shared: bool | None = None
        cats: tuple[frozenset[str], frozenset[str]] | None = None
    else:
        partners = shares.get(file_name)
        shared = bool(partners) if partners is not None else False
        cats = index.categories(file_name)

    site_rec = index.p373.get(site_id)
    site_cat = (
        normalize_category(site_rec["category"])
        if site_rec and site_rec.get("category")
        else None
    )
    in_category = in_category_direct = None
    if cats is not None and site_cat is not None:
        in_category = site_cat in cats[1]
        in_category_direct = site_cat in cats[0]

    place_hits: list[tuple[str, str, float]] = []
    for token in sorted(set(tokens)):
        nearest = sc.nearest_place(token, site_id)
        if nearest is not None and nearest[1] > PLACE_TOKEN_MIN_KM:
            place_hits.append((token, sc.names.get(nearest[0], ""), round(nearest[1], 1)))

    medium = matched_terms(tokens, NON_PHOTO_TERMS_NORM)
    museum = matched_terms(tokens, MUSEUM_WORDS)
    if file_name is not None:
        cat_tokens = [
            w for cat in (index.files.get(file_name) or {}).get("categories", []) for w in cat.split()
        ]
        museum = sorted(set(museum) | set(matched_terms(cat_tokens, MUSEUM_WORDS)))

    return Signals(
        same_file_other_site=shared,
        no_own_name=None if not name else not name_in_text(name, haystack),
        name_in_filename=bool(name) and name_in_text(name, normalize_text(img.get("filename"))),
        in_category=in_category,
        in_category_direct=in_category_direct,
        museum_word=bool(museum),
        other_place_token=bool(place_hits),
        non_photo_word=bool(medium),
        place_hits=tuple(place_hits[:3]),
        medium_hits=tuple(medium),
        museum_hits=tuple(museum),
        category=site_cat,
        share_partners=tuple(sorted(shares.get(file_name, set()) - {name})) if file_name else (),
    )


def tier_for(signals: Signals) -> tuple[str, str]:
    """The tier and the reason, with the precedence documented in the module docstring."""
    if signals.core:
        return SUSPECT, "core"
    if signals.in_category is None:
        return GREY, "p-unproven"
    if signals.in_category is False:
        return GREY, "not-in-category"
    if not signals.name_in_filename:
        return GREY, "name-not-in-filename"
    return CLEAR, "in-category-clear"


# ------------------------------------------------------------------------------- findings
def _row_evidence(img: dict[str, Any]) -> Evidence:
    return Evidence(
        source="snapshot:wiki_images",
        quote=(
            f"id={img['id']} site_id={img['site_id']} filename={img['filename']!r} "
            f"title={img['title']!r} is_hero={img['is_hero']} is_excluded={img['is_excluded']} "
            f"original_url={img['original_url']!r}"
        ),
    )


def _evidence(signals: Signals, file_name: str | None) -> list[Evidence]:
    """The evidence the tier rests on - quoted, so a reviewer can re-derive the tier."""
    out: list[Evidence] = []
    if signals.share_partners:
        out.append(
            Evidence(
                source="snapshot:wiki_images (cross-site share)",
                quote=(
                    f"File:{file_name} is also attached to a site named "
                    f"{signals.share_partners[0]!r} - a differently named site"
                ),
            )
        )
    if signals.place_hits:
        token, other, km = signals.place_hits[0]
        out.append(
            Evidence(
                source="snapshot:unified_sites (place token)",
                quote=(
                    f"token {token!r} occurs in {other!r}, the nearest curated site carrying "
                    f"it, {km} km away (> {PLACE_TOKEN_MIN_KM:g} km)"
                ),
            )
        )
    if signals.medium_hits:
        out.append(
            Evidence(
                source="census:t10 NON_PHOTO_TERMS (6 of the plan's 67)",
                quote=f"non-photo term(s) in title/filename: {list(signals.medium_hits)}",
            )
        )
    if signals.museum_hits:
        out.append(
            Evidence(
                source="census:t10 MUSEUM_WORDS (reconstruction)",
                quote=(
                    "museum word(s) in title/filename/Commons category: "
                    f"{list(signals.museum_hits)}"
                ),
            )
        )
    if signals.in_category is not None:
        out.append(
            Evidence(
                source="commons:categories + wikidata:P373",
                quote=(
                    f"the site's P373 category {signals.category!r} is "
                    f"{'in' if signals.in_category else 'not in'} the file's categories "
                    "(direct or one subcategory level)"
                ),
            )
        )
    return out[:3]


def _confidence(signals: Signals) -> Confidence:
    if signals.core:
        return Confidence.WEAK if signals.in_category is None else Confidence.AUTHORITATIVE
    if signals.in_category is None:
        return Confidence.UNVERIFIABLE
    return Confidence.AUTHORITATIVE


def _note(tier: str, reason: str, signals: Signals) -> str:
    if tier is HERO:
        return (
            "hero: is_hero - the most visible image of the site, so §6.5 stage 2 audits every "
            "one of these whatever its signals say"
        )
    if tier is SUSPECT:
        return (
            f"CORE signal {signals.fired()} - §6.5 stage 1 audits every one of these; signal B "
            f"is unavailable ({B_MUSEUM_CITY}), so CORE here is a subset of the plan's CORE"
        )
    if tier is CLEAR:
        return (
            f"clear: in the site's P373 category ({signals.category!r}), no word signal, own "
            "name in the filename - §6.5 stage 0 spends no VLM call here"
        )
    if reason == "p-unproven":
        return (
            "grey: no word signal, but membership in the site's P373 category is unproven, so "
            "this row must not enter the zero-call tier; §6.5 stage 3 samples it"
        )
    if reason == "not-in-category":
        return (
            "grey: not in the site's P373 category and not covered by a word or cross-site "
            "signal; §6.5 stage 3 samples it"
        )
    return (
        "grey: no CORE signal and the own name is not in the filename, so the clear conditions "
        "do not hold; §6.5 stage 3 samples it"
    )


def applies_to(site: dict[str, Any], ctx: Context) -> bool:
    """Only sites with at least one `wiki_images` row are triaged (4,010 of 5,004)."""
    return bool(ctx.snap.images(str(site["id"])))


def run(ctx: Context) -> list[Finding]:
    """Assign exactly one tier to every image row of every curated site. No socket."""
    index = _read_index(ctx)
    sc = build_site_context(ctx.sites)
    dropped = distinctive_place_tokens(sc, ctx.snap.rows("wiki_images"))
    shares = cross_site_shares(ctx, sc)

    log.warning(
        "T10 place dictionary: %d tokens kept of %d (the plan's %d-token figure, filtered "
        "by document frequency in the image corpus); dropped %s and %d other generic token(s)",
        len(sc.place_tokens),
        len(sc.place_tokens) + len(dropped),
        PLACE_TOKEN_BUDGET,
        ", ".join(repr(tok) for tok in dropped[:5]),
        len(dropped) - min(len(dropped), 5),
    )
    log.warning(
        "T10 signal fidelity: S faithful, F faithful, P faithful (fetched), D reconstructed "
        "from the 5,004 curated site names and cut to the plan's 4,396-token size by corpus "
        "frequency, E partial (6 of the plan's 67 non-photo terms), "
        "A narrow reconstruction, B %s",
        B_MUSEUM_CITY,
    )

    findings: list[Finding] = []
    tiers: Counter[str] = Counter()
    tiers_served: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    p_coverage: Counter[str] = Counter()
    hero_core_overlap = 0
    hop_only_clear = 0
    share_over_clear = 0
    clear_rows = 0

    for site in ctx.sites:
        sid = str(site["id"])
        rec = index.p373.get(sid)
        p_coverage[rec["status"] if rec else "no-qid-anchor"] += 1
        for img in ctx.snap.images(sid):
            signals = signals_for(img, sid, sc, index, shares)
            word_signal = signals.museum_word or signals.other_place_token or signals.non_photo_word
            clear_conditions = (
                signals.in_category is True and not word_signal and signals.name_in_filename
            )
            if img.get("is_hero"):
                tier, reason = HERO, "hero"
                if signals.core:
                    hero_core_overlap += 1
            else:
                tier, reason = tier_for(signals)
            if tier is CLEAR:
                clear_rows += 1
                if signals.in_category_direct is False:
                    hop_only_clear += 1
            if clear_conditions and signals.same_file_other_site:
                share_over_clear += 1
            tiers[tier] += 1
            if not img.get("is_excluded"):
                tiers_served[tier] += 1
            reasons[f"{tier}:{reason}"] += 1
            file_name = commons_file_name(img)
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/tier-{tier}",
                    field=f"wiki_images:{img['id']}",
                    severity=Severity.MODERATE if tier in (HERO, SUSPECT) else Severity.COSMETIC,
                    dimension=DIMENSION,
                    current_value={
                        "image_id": img["id"],
                        "filename": img["filename"],
                        "is_hero": bool(img.get("is_hero")),
                        "is_excluded": bool(img.get("is_excluded")),
                        "tier": tier,
                        "tier_label": TIER_LABEL[tier],
                        "reason": reason,
                        "signals": signals.to_json(),
                        "commons_file": file_name,
                    },
                    proposal=Proposal.NONE,
                    confidence=_confidence(signals),
                    note=_note(tier, reason, signals),
                    evidence=[_row_evidence(img), *_evidence(signals, file_name)],
                )
            )

    log.info(
        "T10 tiers: %s (all rows) / %s (not excluded)",
        {TIER_LABEL[t]: tiers[t] for t in (HERO, SUSPECT, GREY, CLEAR)},
        {TIER_LABEL[t]: tiers_served[t] for t in (HERO, SUSPECT, GREY, CLEAR)},
    )
    log.info("T10 tier reasons: %s", dict(reasons.most_common()))
    log.info("T10 P373 coverage over %d sites: %s", len(ctx.sites), dict(p_coverage.most_common()))
    log.info("T10 collection stats: %s", index.stats)
    log.info(
        "T10 overlaps and sensitivity: %d hero/heroes also carry a CORE signal (hero wins); "
        "%d row(s) would satisfy the clear conditions without the cross-site S signal (suspect "
        "wins); %d of %d clear row(s) rest on the one-subcategory-level hop and would be grey "
        "under direct membership only",
        hero_core_overlap,
        share_over_clear,
        hop_only_clear,
        clear_rows,
    )
    return findings
