"""Build the sitelink lane's plan: the fields the mass finder called UNVERIFIABLE, asked again with the
site's own other-language Wikipedia articles as new evidence. Zero MiniMax; the finder and reviewer are
the mass run's (`opencode-go/deepseek-v4.1-flash`, the frozen round-5 prompts).

**Why.** The mass run's finder answered `UNVERIFIABLE` on 7,761 fields, 4,342 of them writable
(`period_start` 3,028, `site_type` 887, `country` 427, counted with `discover_stage.parse_answer`).
Each of those answers already had the English article by name and, where the site has one, its
Wikidata item as evidence: asking again on the same evidence buys the same answer. What the run never
read is the item's articles in other languages - the Spanish article of a Peruvian site, the Greek one
of a Greek site. This lane adds up to `fetch_stage.MAX_WIKI_SITELINKS` of them per site through the
fetch stage's sitelink route (`wiki_sitelinks` on the record; `fetch_stage` states the route, the pin
and the refusals) and asks only the fields it was built for (`rerun_fields`; the writer refuses every
other field, `write_stage.RULE_NOT_RERUN`). A **rerun** plan in `mass_run.py`'s terms: `rerun_fields`
and no `search_fields`, run through `prepare,fetch,judge`; batch ids `slk-NNNN` (`lanes.py`), the
pilot's `slkg-NNNN`.

**What is asked** (`census`, then `open_questions`): every `UNVERIFIABLE` answer of `runs/mass` in the
scope (`writable` for the lane; `all` five fields on the gold-standard sites for the pilot), minus every
key that is not open any more, each named with its reason in the summary:

* **written** - production's journal (`remediation_change_log`, any stamp, exported read-only) holds a
  row for the (site, column): another lane has decided it;
* **planned by the mass lane** - the mass lane's pinned write plan (`lanes.REVIEWED_PLAN_KEYS_SHA256`)
  names the (site, column): written, held by hand (B7) or refused at the boundary (B8);
* **decided by hand** - the country of every site the owner-case classifier sorted out of T02
  (`bcases/b2.jsonl`, `HUMAN_ONLY.md` B2/B10), and every field of a duplicate loser or of the held
  duplicate pair (`bcases/DUPLICATES.jsonl`, `DUPLICATES_HELD.jsonl`, B6/B10);
* **changed in production** - the export's value is not the value the mass finder judged.

**Which item** (`item_for`): the site's `wikidata_qid` in the fresh export, withheld when the reviewed
external-id repair (both waves, `qid_repair.py`) replaces it or leaves it unresolved, when more than one
curated site carries it (a parent or a generic item, `gap_plan.shared_counts`), or when the owner-case
classifier marks the link suspect (`bcases/names.jsonl`: a wrong-link class or `link_suspect`).

**Which articles** (`candidates`, `order`, `select`), deterministic:

1. every sitelink of the item whose url is on `*.wikipedia.org` - the host, and so the language
   subdomain, read off Wikidata's own url, never off a table; English (`enwiki`, `simplewiki`) and the
   bot-generated wikis (`fetch_stage.BOT_GENERATED_WIKIS`) are refused, and so is a sitelink badged as
   a redirect (`fetch_stage.REDIRECT_BADGES`); a sitelink without its `badges` list stops the build;
2. in this order: the language(s) of the site's stored country (`COUNTRY_WIKIS`, keyed by the
   project's own `normalize_country`), then `FIXED_ORDER`, then every other wiki by site id;
3. walking that order, each candidate is pinned (`wikipedia_pages_url`: it exists, is the item's own
   article - not a redirect, not a disambiguation page - and its latest revision) and taken while
   fewer than three are taken and its size fits the site's evidence room; each one not taken is
   recorded with the reason (`wiki_sitelinks_skipped` on the record).

**The evidence room** (`evidence_room`): `model_stage.MAX_EVIDENCE_CHARS` less the English article as
the mass run stored it (the lane fetches the same title again) and `NARROW_RESERVE_CHARS` for the
narrowed Wikidata route the records use (as the gap run does). An article costs its source line, its
wikitext `length` capped at the page cap, and the truncation marker (`article_estimate`): the wikitext
is longer than the plain text the extracts API returns, so the estimate is an upper bound - measured
on the pilot's dry fetch (`measure`).

**Country by geometry** (`geometry`, reported, writes nothing): of the country fields asked, how many
the stored point already verifies - T02 of the 2026-09-20 census found the point inside the stored
country (`run_t02/census.jsonl`, `pass`), and neither the country nor the point has changed since
(the export against the census snapshot).

Subcommands (only `export` and `sitelinks` leave the machine, both read-only):

    census     runs/mass -> questions.json                                  offline
    export     questions.json -> export/ (production, read-only)            ssh + SELECT
    sitelinks  -> sitelinks.json (Wikidata and the Wikipedias, read-only)   HTTP GET
    plan       -> PLAN + summary.json (with the geometry count)             offline
    measure    a prepared and fetched run dir -> the evidence per site and every article's outcome

`--pilot` points every default at the pilot (`sitelink/pilot/`, scope `all`, the gold-standard sites,
prefix `slkg`). In a worktree, `--mass-run`, `--data` and `--rows` name the main checkout's copies:
the run, the census and snapshot, and the mass lane's plan are not in git.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import gap_plan as G  # noqa: E402 - the questions' shape, the export, the withheld and shared rules
import lanes  # noqa: E402 - paths, the JSON-lines reader and the read-only psql seam
import qid_repair  # noqa: E402 - the reviewed id repair, both waves

sys.path.insert(0, str(lanes.REPO / "scripts" / "remediation"))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import search_plan as SPL  # noqa: E402 - the mass run's UNVERIFIABLE answers
from phase3 import snapshot_plan as SP  # noqa: E402

from pipeline.utils.country_lookup import normalize_country  # noqa: E402 - the country key

SITELINK = lanes.REMEDIATION / "sitelink"
LANE_DIR = SITELINK / "lane"
PILOT_DIR = SITELINK / "pilot"
PLAN = lanes.REMEDIATION / "phase3_runner" / "PLAN.sitelink.jsonl"
PILOT_PLAN = PILOT_DIR / "PLAN.sitelink-gold.jsonl"
GOLD = lanes.REMEDIATION / "gold_standard" / "sites.json"
LANE = "sitelink"
PILOT_PREFIX = "slkg"
BATCH_SIZE = 15
WHY = "unverifiable"
#: The mass lane's pinned write plan and its hand holds (local; `lanes.lane(MASS)`).
ROWS = lanes.lane(lanes.MASS).rows

#: Characters kept free for the narrowed Wikidata evidence of a site. **A chosen bound**: the gap run
#: measured that route's rendering at a median 1,277 and a maximum 1,971 characters over its 187
#: sites, which were the largest items of the curated set (`runs/gap`, 2026-09-23); twice the maximum.
NARROW_RESERVE_CHARS = 4_000

#: How many items one sitelinks request asks for. Every sitelink comes with its url, and an item of a
#: well-known site carries 100-300 of them, so ten items stay far below `LOOKUP_MAX_BYTES`.
ITEMS_PER_REQUEST = 10
#: The page cap of the plan's own lookups (sitelinks, pins) - never of an evidence page. A lookup cut
#: at a cap cannot be read at all, and `wbgetentities` of ten well-linked items passes 60 KB.
LOOKUP_MAX_BYTES = 1024 * 1024
#: The plan's lookups are asked at most once a second per host (the WDQS pace of the fetch stage):
#: the first lane build of 2026-09-23 drew an HTTP 429 from ar.wikipedia.org at the default 0.2 s
#: pace, and the build is a few hundred requests, not a batch that has to finish in minutes.
LOOKUP_MIN_INTERVAL_SECONDS = 1.0
#: The pause before the second and third ask of a lookup the host refused for now (429, 5xx), when
#: the host names no longer `Retry-After`. **Chosen bounds**, longer than the fetch stage's (1 s, 3 s):
#: the 429 above answered 200 again when asked by hand a minute later.
LOOKUP_BACKOFF_SECONDS: tuple[float, ...] = (15.0, 60.0)

#: The order after the site's own language(s): the wikis in the order of how many of the lane's
#: writable fields they reach, measured 2026-09-23 on the bcases sitelink cache (dewiki 1,437 fields,
#: eswiki 1,418, frwiki 1,337, itwiki 1,038, cawiki 848, ruwiki 834), then by the sites they reach
#: (nlwiki 575 sites ... huwiki 285). Every wiki not named here comes after, by site id.
FIXED_ORDER: tuple[str, ...] = (
    "dewiki",
    "eswiki",
    "frwiki",
    "itwiki",
    "cawiki",
    "ruwiki",
    "nlwiki",
    "ptwiki",
    "plwiki",
    "svwiki",
    "ukwiki",
    "fawiki",
    "trwiki",
    "arwiki",
    "elwiki",
    "zhwiki",
    "fiwiki",
    "cswiki",
    "euwiki",
    "huwiki",
)

#: The site's own language(s), first in the order: the Wikipedias of the language(s) with nationwide
#: official status in the stored country, keyed by `pipeline.utils.country_lookup.normalize_country`
#: (every value the curated set stores, 2026-09-23). **An ordering, not evidence**: a wrong entry
#: costs a less useful article, never a write - the finder still has to quote the text it cites, and
#: the reviewer and the writer's rules apply. English-speaking countries have no entry of their own
#: (the English article is the name route's). A key this table lacks stops the build.
COUNTRY_WIKIS: dict[str, tuple[str, ...]] = {
    "AD": ("cawiki",),
    "AE": ("arwiki",),
    "AF": ("fawiki", "pswiki"),
    "AL": ("sqwiki",),
    "AM": ("hywiki",),
    "AT": ("dewiki",),
    "AU": (),
    "AZ": ("azwiki",),
    "BA": ("bswiki", "hrwiki", "srwiki"),
    "BE": ("nlwiki", "frwiki", "dewiki"),
    "BG": ("bgwiki",),
    "BH": ("arwiki",),
    "BO": ("eswiki", "quwiki", "aywiki"),
    "BR": ("ptwiki",),
    "BZ": (),
    "CA": ("frwiki",),
    "CH": ("dewiki", "frwiki", "itwiki"),
    "CL": ("eswiki",),
    "CN": ("zhwiki",),
    "CR": ("eswiki",),
    "CY": ("elwiki", "trwiki"),
    "DE": ("dewiki",),
    "DK": ("dawiki",),
    "DZ": ("arwiki",),
    "EC": ("eswiki",),
    "EG": ("arwiki",),
    "ER": ("tiwiki", "arwiki"),
    "ES": ("eswiki",),
    "ET": ("amwiki",),
    "FI": ("fiwiki", "svwiki"),
    "FR": ("frwiki",),
    "GB": (),
    "GE": ("kawiki",),
    "GL": ("klwiki", "dawiki"),
    "GM": (),
    "GR": ("elwiki",),
    "GT": ("eswiki",),
    "HN": ("eswiki",),
    "HR": ("hrwiki",),
    "HU": ("huwiki",),
    "ID": ("idwiki",),
    "IE": ("gawiki",),
    "IL": ("hewiki",),
    "IN": ("hiwiki",),
    "IQ": ("arwiki", "ckbwiki"),
    "IR": ("fawiki",),
    "IT": ("itwiki",),
    "JO": ("arwiki",),
    "JP": ("jawiki",),
    "KH": ("kmwiki",),
    "KP": ("kowiki",),
    "KR": ("kowiki",),
    "KZ": ("kkwiki", "ruwiki"),
    "LA": ("lowiki",),
    "LB": ("arwiki",),
    "LK": ("siwiki", "tawiki"),
    "LY": ("arwiki",),
    "MA": ("arwiki",),
    "MK": ("mkwiki", "sqwiki"),
    "MM": ("mywiki",),
    "MN": ("mnwiki",),
    "MR": ("arwiki",),
    "MT": ("mtwiki",),
    "MX": ("eswiki",),
    "NL": ("nlwiki",),
    "NO": ("nowiki", "nnwiki"),
    "PA": ("eswiki",),
    "PE": ("eswiki", "quwiki", "aywiki"),
    "PK": ("urwiki",),
    "PL": ("plwiki",),
    "PT": ("ptwiki",),
    "PY": ("eswiki", "gnwiki"),
    "RO": ("rowiki",),
    "RS": ("srwiki",),
    "RU": ("ruwiki",),
    "SA": ("arwiki",),
    "SD": ("arwiki",),
    "SE": ("svwiki",),
    "SK": ("skwiki",),
    "SY": ("arwiki",),
    "TH": ("thwiki",),
    "TM": ("tkwiki",),
    "TN": ("arwiki",),
    "TR": ("trwiki",),
    "TW": ("zhwiki",),
    "UA": ("ukwiki",),
    "US": (),
    "VE": ("eswiki",),
    "YE": ("arwiki",),
    # Two stored values `normalize_country` leaves as text: open water, and a US territory.
    "baltic sea": (),
    "northern mariana islands": (),
}

#: The reasons an article is not taken, as the summary counts them.
CAP_REASON = f"the site already has {F.MAX_WIKI_SITELINKS} articles (the lane's cap)"


# ------------------------------------------------------------------------------------ the census
def census(
    mass_run: pathlib.Path, *, scope: str, site_ids: Collection[str] | None = None
) -> list[G.Question]:
    """Every `UNVERIFIABLE` answer of the mass run in `scope`, in the run's own order (batch, site
    position, field). `site_ids` selects (the pilot's gold-standard sites); one the run lacks raises."""
    if scope not in SPL.SCOPES:
        raise SystemExit(f"scope {scope!r} is not one of {sorted(SPL.SCOPES)}")
    wanted = SPL.SCOPES[scope]
    questions: list[G.Question] = []
    seen: set[str] = set()
    for source in SPL.read_source_batches(mass_run):
        found = SPL.unverifiable_fields(source)
        for position, site in enumerate(source.sites):
            site_id = str(site["site_id"])
            if site_ids is not None and site_id not in site_ids:
                continue
            seen.add(site_id)
            questions.extend(
                G.Question(site_id, name, source.batch_id, position, WHY, SPL.WHY_UNVERIFIABLE)
                for name in DS.DISCOVER_FIELDS
                if name in wanted and name in found.get(site_id, [])
            )
    if site_ids is not None and set(site_ids) - seen:
        raise SystemExit(f"sites the mass run does not hold: {sorted(set(site_ids) - seen)[:5]}")
    if not questions:
        raise SystemExit(f"{mass_run}: no UNVERIFIABLE answer in the {scope!r} scope")
    return questions


# ------------------------------------------------------------------------------------ the export
#: The journal columns of the five fields: a row for one of them means another lane decided the field.
JOURNAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "unified_sites": ("description", "period_start", "site_type", "country"),
    "card_stats": ("card_description",),
}


def journal_sql(site_ids: Sequence[str]) -> str:
    """Every journal row of the five fields' columns for these sites, whatever its stamp."""
    ids = lanes.sql_literals(site_ids)
    columns = " OR ".join(
        f"(table_name = {lanes.sql_text(table)} AND column_name IN ({lanes.sql_literals(names)}))"
        for table, names in JOURNAL_COLUMNS.items()
    )
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT id, run_stamp, table_name, column_name, row_pk, "
        "site_id_ref::text AS site_id, old_value, new_value FROM remediation_change_log "
        f"WHERE ({columns}) AND (site_id_ref::text IN ({ids}) OR row_pk IN ({ids})) ORDER BY id) t;"
    )


def export(questions: list[G.Question], out: pathlib.Path, *, run=lanes.psql) -> dict[str, int]:
    """The gap lane's export of the questions' sites, plus their journal rows (`journal_sql`)."""
    site_ids = sorted({q.site_id for q in questions})
    return G.export(questions, out, run=run, extra={"journal": journal_sql(site_ids)})


@dataclass(frozen=True)
class Export:
    """What `export` wrote, read back and keyed."""

    sites: dict[str, dict[str, Any]]
    cards: dict[str, dict[str, Any]]
    external: list[dict[str, Any]]
    journal: list[dict[str, Any]]

    @classmethod
    def read(cls, root: pathlib.Path) -> Export:
        journal = lanes.read_jsonl(root / "journal.jsonl")
        unowned = [row["id"] for row in journal if not row.get("site_id")]
        if unowned:
            raise SystemExit(f"{root}: journal rows without the site they belong to: {unowned[:5]}")
        return cls(
            sites={row["id"]: row for row in lanes.read_jsonl(root / "unified_sites.jsonl")},
            cards={row["site_id"]: row for row in lanes.read_jsonl(root / "card_stats.jsonl")},
            external=lanes.read_jsonl(root / "site_external_ids.jsonl"),
            journal=journal,
        )


# ------------------------------------------------------------------------------ what is still open
@dataclass(frozen=True)
class HandDecided:
    """The keys decided by hand, read from the owner-case classifier's versioned output."""

    countries: frozenset[str]  #: sites whose country B2/B10 decided (`b2.jsonl`)
    duplicates: frozenset[str]  #: duplicate losers and the held pair (B6/B10)

    @classmethod
    def read(cls, bcases: pathlib.Path) -> HandDecided:
        countries = {row["site_id"] for row in lanes.read_jsonl(bcases / "b2.jsonl")}
        losers = {row["loser_id"] for row in lanes.read_jsonl(bcases / "DUPLICATES.jsonl")}
        held = {
            site_id
            for row in lanes.read_jsonl(bcases / "DUPLICATES_HELD.jsonl")
            for site_id in row["site_ids"]
        }
        return cls(countries=frozenset(countries), duplicates=frozenset(losers | held))


def mass_plan_keys(rows_path: pathlib.Path) -> set[tuple[str, str]]:
    """`(site_id, column)` of every row the mass lane planned - the pinned plan, or the build stops."""
    rows = lanes.read_jsonl(rows_path)
    lanes.assert_reviewed_plan(lanes.MASS, rows, path=rows_path)
    return {(str(row["site_id"]), str(row["column"])) for row in rows}


def judged_values(mass_run: pathlib.Path) -> dict[tuple[str, str], Any]:
    """`(site_id, field) -> the stored value the mass finder judged`, from each batch's own record."""
    values: dict[tuple[str, str], Any] = {}
    for source in SPL.read_source_batches(mass_run):
        for site in source.sites:
            for name in DS.DISCOVER_FIELDS:
                values[(str(site["site_id"]), name)] = DS.field_finding(site, name).get(
                    "current_value"
                )
    return values


def open_questions(
    questions: Sequence[G.Question],
    *,
    exported: Export,
    judged: Mapping[tuple[str, str], Any],
    planned: Collection[tuple[str, str]],
    hand: HandDecided,
) -> tuple[list[G.Question], list[dict[str, str]]]:
    """`(the questions still open, every other one with why)` - the rules in the module docstring,
    first match wins: a duplicate, a journal row, a mass-lane row, a hand-decided country, a value
    production no longer holds."""
    written: dict[tuple[str, str], str] = {}
    for row in exported.journal:
        written.setdefault((str(row["site_id"]), str(row["column_name"])), str(row["run_stamp"]))
    kept: list[G.Question] = []
    dropped: list[dict[str, str]] = []
    for question in questions:
        key = (question.site_id, question.field)
        site = exported.sites.get(question.site_id)
        if site is None:
            raise SystemExit(f"{question.site_id}: not in the export")
        card = exported.cards.get(question.site_id)
        now = SP.stored_value(site=site, card=card, field=question.field)
        if question.site_id in hand.duplicates:
            rule, why = "duplicate", "a duplicate held for the owner's decision (HUMAN_ONLY B6/B10)"
        elif key in written:
            rule, why = "written", f"written in production by {written[key]}"
        elif key in planned:
            rule = "mass-plan"
            why = "planned by the mass lane (written, held by hand or refused at the boundary)"
        elif question.field == "country" and question.site_id in hand.countries:
            rule, why = "hand-country", "decided by hand (bcases/b2.jsonl, HUMAN_ONLY B2/B10)"
        elif now != judged[key]:
            rule, why = "changed", f"changed in production: judged {judged[key]!r}, now {now!r}"
        else:
            kept.append(question)
            continue
        dropped.append(
            {"site_id": question.site_id, "field": question.field, "rule": rule, "reason": why}
        )
    return kept, dropped


# ------------------------------------------------------------------------------------ the item
#: Both waves of the reviewed external-id repair: their site sets do not overlap.
REPAIRS: tuple[qid_repair.Site, ...] = (*qid_repair.SITES, *qid_repair.WAVE2_SITES)
#: The owner-case classifier's wrong-link classes (`bcases/classify.py`).
WRONG_LINK_CLASSES = frozenset({"Q1", "Q2", "Q3", "Q4"})


def suspect_links(bcases: pathlib.Path) -> dict[str, tuple[str, str]]:
    """`site_id -> (the item the classifier judged, why the link is suspect)` from `names.jsonl`."""
    suspect: dict[str, tuple[str, str]] = {}
    for row in lanes.read_jsonl(bcases / "names.jsonl"):
        codes = sorted(set(row.get("link_suspect") or ()) | ({row["class"]} & WRONG_LINK_CLASSES))
        if codes and row.get("qid_now"):
            suspect[str(row["site_id"])] = (str(row["qid_now"]), "/".join(codes))
    return suspect


def item_for(
    site_id: str,
    qid: str | None,
    *,
    shared: Mapping[str, int],
    suspect: Mapping[str, tuple[str, str]],
) -> tuple[str | None, str | None]:
    """`(the item whose sitelinks the site is given, or None; why none)`."""
    kept, reason = G.withheld_reason(site_id, qid, shared=shared, repairs=REPAIRS)
    if kept is None:
        return None, reason or "the site carries no Wikidata item"
    flagged = suspect.get(site_id)
    if flagged is not None and flagged[0] == kept:
        return None, (
            f"{kept}: the owner-case classifier marks this link suspect ({flagged[1]}, "
            "bcases/names.jsonl)"
        )
    return kept, None


# ------------------------------------------------------------------------------------ the articles
@dataclass(frozen=True)
class Candidate:
    """One Wikipedia sitelink the site may be given."""

    wiki: str
    lang: str
    title: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.lang, self.title)


@dataclass(frozen=True)
class Pin:
    """A candidate that is the item's own article, pinned: its latest revision and wikitext length."""

    wiki: str
    lang: str
    title: str
    revid: int
    length: int

    def sitelink(self) -> F.WikiSitelink:
        return F.WikiSitelink(wiki=self.wiki, lang=self.lang, title=self.title, revid=self.revid)


def candidates(
    links: Mapping[str, F.Sitelink],
) -> tuple[list[Candidate], list[dict[str, str]]]:
    """`(the item's Wikipedia sitelinks that may be read, every other Wikipedia sitelink with why)`.

    A sitelink is a Wikipedia's when its url is on `*.wikipedia.org`; the language subdomain is read
    off that url. Other projects (Commons, Wikivoyage, Wikisource) are not languages and not listed.
    """
    usable: list[Candidate] = []
    refused: list[dict[str, str]] = []
    for wiki, link in sorted(links.items()):
        if link.url is None:
            raise SystemExit(f"{wiki}: a sitelink without its url - ask with all_wikis=True")
        host = urlsplit(link.url).hostname or ""
        if not host.endswith(F.WIKIPEDIA_HOST_SUFFIX):
            continue
        lang = host[: -len(F.WIKIPEDIA_HOST_SUFFIX)]
        if not F.WIKI_ID_PATTERN.fullmatch(wiki) or not F.WIKI_LANG_PATTERN.fullmatch(lang):
            raise SystemExit(f"{wiki} at {link.url}: not a Wikipedia site id and subdomain")
        redirect = link.redirect_badges()
        if wiki in F.ENGLISH_WIKIS:
            rule, why = "english", "English: the mass run had the English article"
        elif wiki in F.BOT_GENERATED_WIKIS:
            rule, why = "bot-generated", "a bot-generated wiki (fetch_stage.BOT_GENERATED_WIKIS)"
        elif redirect:
            rule, why = "redirect-badge", f"a sitelink to a redirect ({', '.join(redirect)})"
        else:
            usable.append(Candidate(wiki=wiki, lang=lang, title=link.title))
            continue
        refused.append(_skip(wiki, link.title, rule, why))
    return usable, refused


def _skip(wiki: str, title: str, rule: str, reason: str) -> dict[str, str]:
    """One sitelink not taken, as the record's `wiki_sitelinks_skipped` names it."""
    return {"reason": reason, "rule": rule, "title": title, "wiki": wiki}


def country_key(country: Any) -> str:
    """The key `COUNTRY_WIKIS` is read under; a stored country the table lacks stops the build."""
    key = normalize_country(str(country or ""))
    if key not in COUNTRY_WIKIS:
        raise SystemExit(
            f"stored country {country!r} (key {key!r}) is not in COUNTRY_WIKIS; add its language(s)"
        )
    return key


def order(usable: Iterable[Candidate], country: Any) -> list[Candidate]:
    """The candidates in the lane's order: the country's own wiki(s), `FIXED_ORDER`, the rest by id."""
    local = COUNTRY_WIKIS[country_key(country)]
    ranked = [*local, *(wiki for wiki in FIXED_ORDER if wiki not in local)]
    rank = {wiki: index for index, wiki in enumerate(ranked)}
    return sorted(usable, key=lambda c: (rank.get(c.wiki, len(rank)), c.wiki))


def article_estimate(pin: Pin) -> int:
    """What an article can cost against the evidence bound, at most (module docstring)."""
    header = F.wiki_article_header(pin.sitelink())
    return len(header) + min(pin.length, F.MAX_PAGE_BYTES) + 1 + len(F.TRUNCATION_MARKER)


def evidence_room(site_id: str, source_batch: str, *, mass_run: pathlib.Path) -> int:
    """The characters left for other-language articles under `MAX_EVIDENCE_CHARS` (module docstring).

    The English article is counted as the mass run stored it. A site whose English page the mass run
    could not fetch is charged a full page: the lane asks for it again, and it may arrive whole.
    """
    page = F.EvidenceStore(mass_run / source_batch / "evidence").path_for(site_id, F.FEATURE_ENWIKI)
    english = (
        len(page.read_text(encoding="utf-8"))
        if page.exists()
        else F.MAX_PAGE_BYTES + len(F.TRUNCATION_MARKER)
    )
    return MS.MAX_EVIDENCE_CHARS - english - NARROW_RESERVE_CHARS


@dataclass(frozen=True)
class Selection:
    """What `select` decided for one site - or, while `need` is not empty, which pins it waits for."""

    chosen: tuple[Pin, ...]
    skipped: tuple[dict[str, str], ...]
    need: tuple[Candidate, ...]


def select(
    ordered: Sequence[Candidate], pins: Mapping[tuple[str, str], Pin | str], *, room: int
) -> Selection:
    """Walk the order and take each pinned article that fits, up to `MAX_WIKI_SITELINKS`.

    A candidate whose pin is not known yet stops the walk: the decision for everything after it
    depends on what it costs. The selection then names the next unknown candidates (as many as
    articles are still open) and nothing else, and the caller pins them and walks again.
    """
    chosen: list[Pin] = []
    skipped: list[dict[str, str]] = []
    left = room
    for position, candidate in enumerate(ordered):
        if len(chosen) == F.MAX_WIKI_SITELINKS:
            skipped.extend(_skip(c.wiki, c.title, "cap", CAP_REASON) for c in ordered[position:])
            break
        pin = pins.get(candidate.key)
        if pin is None:
            unknown = [c for c in ordered[position:] if c.key not in pins]
            return Selection((), (), tuple(unknown[: F.MAX_WIKI_SITELINKS - len(chosen)]))
        if isinstance(pin, str):
            skipped.append(_skip(candidate.wiki, candidate.title, "not-the-items-article", pin))
            continue
        cost = article_estimate(pin)
        if cost > left:
            why = (
                f"does not fit the evidence room: up to {cost} characters (wikitext {pin.length}), "
                f"{left} left under the bound"
            )
            skipped.append(_skip(candidate.wiki, candidate.title, "room", why))
            continue
        chosen.append(pin)
        left -= cost
    return Selection(tuple(chosen), tuple(skipped), ())


def lookup(fetcher: F.Fetcher, url: str, *, sleep: Callable[[float], None]) -> F.FetchedPage:
    """One plan-time lookup, whole and 2xx, or the build stops with the status.

    A status the fetch stage re-asks (`fetch_stage.is_retryable_status`: 429, 408, 5xx) is asked
    again up to `fetch_stage.MAX_ATTEMPTS` times, after `LOOKUP_BACKOFF_SECONDS` or the host's own
    `Retry-After` when that is longer - never after more than `fetch_stage.RETRY_AFTER_CAP_SECONDS`:
    a host that asks for longer stops the build, as it stops a fetch target. Anything else stops it
    at once: a plan built on a lookup that did not answer would silently give fewer articles.
    """
    for attempt in range(F.MAX_ATTEMPTS):
        page = fetcher.get(url)
        if page.ok and not page.truncated:
            return page
        last = attempt == F.MAX_ATTEMPTS - 1
        if page.truncated or not F.is_retryable_status(page.status) or last:
            break
        wait = max(LOOKUP_BACKOFF_SECONDS[attempt], page.retry_after or 0.0)
        if wait > F.RETRY_AFTER_CAP_SECONDS:
            break
        sleep(wait)
    raise SystemExit(f"GET {url}: HTTP {page.status}, truncated={page.truncated}")


def pin_titles(
    wanted: Mapping[tuple[str, str], tuple[str, str]],
    *,
    fetcher: F.Fetcher,
    sleep: Callable[[float], None],
) -> dict[tuple[str, str], Pin | str]:
    """`{(lang, title): its pin, or why it is not the item's own article}` for `{(lang, title): (wiki,
    qid)}`, 50 titles per request per wiki. A failed or cut answer, or one that omits an asked title,
    stops the build: a plan built on a lookup that did not answer would silently give fewer articles.
    """
    by_lang: dict[str, list[str]] = collections.defaultdict(list)
    for lang, title in sorted(wanted):
        by_lang[lang].append(title)
    pins: dict[tuple[str, str], Pin | str] = {}
    for lang, titles in by_lang.items():
        for start in range(0, len(titles), 50):
            window = titles[start : start + 50]
            url = F.wikipedia_pages_url(lang, window)
            page = lookup(fetcher, url, sleep=sleep)
            query = json.loads(page.body.decode("utf-8")).get("query") or {}
            normalised = {row["from"]: row["to"] for row in query.get("normalized") or ()}
            answered = {row.get("title"): row for row in query.get("pages") or ()}
            for title in window:
                row = answered.get(normalised.get(title, title))
                if row is None:
                    raise SystemExit(f"{lang}: {title!r} was asked for and is absent from {url}")
                wiki, qid = wanted[(lang, title)]
                refused = F.wiki_page_refusal(row, wiki=wiki, title=title, qid=qid)
                if refused is not None:
                    pins[(lang, title)] = refused
                    continue
                revid, latest = F.page_revision(row, what=f"{wiki}:{title}")
                length = row.get("length")
                if revid != latest or not isinstance(length, int) or isinstance(length, bool):
                    raise SystemExit(
                        f"{wiki}:{title}: revision {revid}/{latest}, length {length!r}"
                    )
                pins[(lang, title)] = Pin(wiki, lang, title, revid, length)
    return pins


def item_sitelinks(
    qids: Sequence[str], *, fetcher: F.Fetcher, sleep: Callable[[float], None]
) -> dict[str, dict[str, F.Sitelink]]:
    """Every sitelink of the items, with urls, `ITEMS_PER_REQUEST` at a time; a failed, cut or
    incomplete answer stops the build."""
    items: dict[str, dict[str, F.Sitelink]] = {}
    ordered = sorted(set(qids))
    for start in range(0, len(ordered), ITEMS_PER_REQUEST):
        window = ordered[start : start + ITEMS_PER_REQUEST]
        url = F.wikidata_sitelinks_url(window, all_wikis=True)
        answer = F.item_sitelinks_from_answer(lookup(fetcher, url, sleep=sleep).body)
        for qid in window:
            if qid not in answer:
                raise SystemExit(f"{qid}: asked for, and absent from the answer")
            items[qid] = answer[qid]
    return items


@dataclass(frozen=True)
class SiteLinks:
    """One site's decision, as `sitelinks.json` records it."""

    qid: str | None
    withheld: str | None
    country: str | None
    room: int | None
    chosen: tuple[dict[str, Any], ...]
    skipped: tuple[dict[str, str], ...]


def resolve(
    sites: Mapping[str, Mapping[str, Any]],
    *,
    fetcher: F.Fetcher,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, SiteLinks]:
    """`{site_id: SiteLinks}` for `{site_id: {qid, withheld, country, room}}`: the sitelinks of every
    kept item, then rounds of `select` and `pin_titles` until every site is decided."""
    kept = {site_id: row for site_id, row in sites.items() if row["qid"] is not None}
    links = item_sitelinks([row["qid"] for row in kept.values()], fetcher=fetcher, sleep=sleep)
    orders: dict[str, list[Candidate]] = {}
    refused: dict[str, list[dict[str, str]]] = {}
    owner: dict[tuple[str, str], tuple[str, str]] = {}
    for site_id, row in sorted(kept.items()):
        usable, refused[site_id] = candidates(links[row["qid"]])
        orders[site_id] = order(usable, row["country"])
        for candidate in usable:
            known = owner.setdefault(candidate.key, (candidate.wiki, row["qid"]))
            if known != (candidate.wiki, row["qid"]):
                raise SystemExit(f"{candidate.key} is linked by {known} and {row['qid']}")
    pins: dict[tuple[str, str], Pin | str] = {}
    while True:
        need = {
            candidate.key: owner[candidate.key]
            for site_id in orders
            for candidate in select(orders[site_id], pins, room=kept[site_id]["room"]).need
        }
        if not need:
            break
        pins.update(pin_titles(need, fetcher=fetcher, sleep=sleep))
    decided: dict[str, SiteLinks] = {}
    for site_id, row in sorted(sites.items()):
        if row["qid"] is None:
            decided[site_id] = SiteLinks(None, row["withheld"], None, None, (), ())
            continue
        selection = select(orders[site_id], pins, room=row["room"])
        chosen = tuple(
            {**asdict(pin), "estimate": article_estimate(pin)} for pin in selection.chosen
        )
        decided[site_id] = SiteLinks(
            row["qid"],
            None,
            str(row["country"]),
            row["room"],
            chosen,
            (*refused[site_id], *selection.skipped),
        )
    return decided


def read_sitelinks(path: pathlib.Path) -> dict[str, SiteLinks]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {
        site_id: SiteLinks(
            row["qid"],
            row["withheld"],
            row["country"],
            row["room"],
            tuple(row["chosen"]),
            tuple(row["skipped"]),
        )
        for site_id, row in rows.items()
    }


# ------------------------------------------------------------------------------------ the plan
def site_records(
    questions: Sequence[G.Question],
    *,
    exported: Export,
    sitelinks: Mapping[str, SiteLinks],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """`(one plan record per site with an article, every open question left out for want of one)`."""
    qids = SP.qids_by_site(exported.external, origin="site_external_ids.jsonl")
    by_site: dict[str, list[G.Question]] = collections.OrderedDict()
    for question in questions:
        by_site.setdefault(question.site_id, []).append(question)
    records: list[dict[str, Any]] = []
    unlinked: list[dict[str, str]] = []
    for site_id, asked in by_site.items():
        links = sitelinks.get(site_id)
        if links is None:
            raise SystemExit(f"{site_id}: not in sitelinks.json - run `sitelinks` again")
        if not links.chosen:
            rule = "item-withheld" if links.withheld else "no-article"
            why = links.withheld or "no usable non-English Wikipedia article"
            unlinked.extend(
                {"site_id": site_id, "field": q.field, "rule": rule, "reason": why} for q in asked
            )
            continue
        if links.qid != qids.get(site_id):
            raise SystemExit(
                f"{site_id}: sitelinks.json was resolved for {links.qid}, the export carries "
                f"{qids.get(site_id)} - run `sitelinks` again"
            )
        record = SP.discover_site_record(
            site=exported.sites[site_id], card=exported.cards.get(site_id), qid=links.qid
        )
        record[SE.RERUN_FIELDS_KEY] = [q.field for q in asked]
        record["source_batch"] = asked[0].source_batch
        record[F.WIKIDATA_ROUTE_KEY] = F.WIKIDATA_ROUTE_NARROW
        record[F.WIKI_SITELINKS_KEY] = [
            F.WikiSitelink(pin["wiki"], pin["lang"], pin["title"], pin["revid"]).to_record()
            for pin in links.chosen
        ]
        record["wiki_sitelinks_skipped"] = [dict(row) for row in links.skipped]
        F.targets_for_site(record)  # a record the fetch stage would refuse is refused here
        records.append(record)
    return records, unlinked


def batches(records: list[dict[str, Any]], *, prefix: str) -> list[R.Batch]:
    """`<prefix>-0001` ... - the lane's own ids (`lanes.BATCH_PREFIX["sitelink"]`) or the pilot's."""
    if prefix not in (lanes.BATCH_PREFIX[LANE], PILOT_PREFIX):
        raise SystemExit(f"prefix {prefix!r}: the lane writes slk-NNNN, its pilot slkg-NNNN")
    return R.assign_batches(records, BATCH_SIZE, pass_name=R.DISCOVER_PASS, prefix=prefix)


def geometry(
    questions: Sequence[G.Question], *, exported: Export, data: pathlib.Path
) -> dict[str, Any]:
    """Of the country fields asked: how many the stored point verifies (module docstring)."""
    census_rows = [
        row for row in R.read_jsonl(data / "run_t02" / "census.jsonl") if row["test_id"] == "T02"
    ]
    status = {row["site_id"]: row["status"] for row in census_rows}
    snapshot = {
        str(row["id"]): row
        for row in SP.read_snapshot_jsonl(data / "snapshot" / SP.UNIFIED_SITES_FILE)
    }
    counts: collections.Counter[str] = collections.Counter()
    verified: list[str] = []
    for question in questions:
        if question.field != "country":
            continue
        counts["asked"] += 1
        if question.site_id not in status:
            raise SystemExit(f"{question.site_id}: not in the T02 census")
        now, then = exported.sites[question.site_id], snapshot[question.site_id]
        moved = any(now[key] != then[key] for key in ("country", "lat", "lon"))
        if status[question.site_id] != "pass":
            counts["t02_flagged"] += 1
        elif moved:
            counts["t02_pass_but_country_or_point_changed_since"] += 1
        else:
            counts["verified_by_geometry"] += 1
            verified.append(question.site_id)
    return {"counts": dict(sorted(counts.items())), "verified_site_ids": sorted(verified)}


# ------------------------------------------------------------------------------------ the measure
def measure(run_dir: pathlib.Path, *, sitelinks: Mapping[str, SiteLinks]) -> dict[str, Any]:
    """The gap lane's evidence measure per site, and every article's outcome: stored (its characters
    beside the plan's estimate) or refused with the fetch stage's reason."""
    sites = G.measure(run_dir)
    articles: list[dict[str, Any]] = []
    for batch in sorted(p for p in run_dir.iterdir() if (p / "fetch.json").exists()):
        report = json.loads((batch / "fetch.json").read_text(encoding="utf-8"))
        store = F.EvidenceStore(batch / "evidence")
        for site in report["sites"]:
            estimates = {
                f"{F.FEATURE_SITELINK_PREFIX}{pin['wiki']}": pin["estimate"]
                for pin in sitelinks[site["site_id"]].chosen
            }
            for target in site["targets"]:
                feature = target["feature"]
                if not feature.startswith(F.FEATURE_SITELINK_PREFIX):
                    continue
                path = store.path_for(site["site_id"], feature)
                failure = next(
                    (o["failure"] for o in site["outcomes"] if o["feature"] == feature), None
                )
                chars = len(path.read_text(encoding="utf-8")) if path.exists() else None
                articles.append(
                    {
                        "batch": batch.name,
                        "site_id": site["site_id"],
                        "feature": feature,
                        "url": target["url"],
                        "stored": path.exists(),
                        "chars": chars,
                        "estimate": estimates[feature],
                        "cut": bool(chars)
                        and path.read_text(encoding="utf-8").endswith(F.TRUNCATION_MARKER),
                        "failure": failure,
                    }
                )
    return {"sites": sites, "articles": articles}


# ------------------------------------------------------------------------------------ the CLI
def _paths(args: argparse.Namespace) -> dict[str, pathlib.Path]:
    root = PILOT_DIR if args.pilot else LANE_DIR
    return {
        "questions": pathlib.Path(args.questions or root / "questions.json"),
        "export": pathlib.Path(args.export or root / "export"),
        "sitelinks": pathlib.Path(args.sitelinks or root / "sitelinks.json"),
        "summary": pathlib.Path(args.summary or root / "summary.json"),
        "out": pathlib.Path(args.out or (PILOT_PLAN if args.pilot else PLAN)),
    }


def _write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _open(args: argparse.Namespace, paths: Mapping[str, pathlib.Path]) -> tuple[Any, ...]:
    """The questions still open and what they need, read the same way by `sitelinks` and `plan`."""
    questions = G.read_questions(paths["questions"])
    exported = Export.read(paths["export"])
    mass = pathlib.Path(args.mass_run)
    kept, dropped = open_questions(
        questions,
        exported=exported,
        judged=judged_values(mass),
        planned=mass_plan_keys(pathlib.Path(args.rows)),
        hand=HandDecided.read(lanes.REMEDIATION / "bcases"),
    )
    return questions, exported, mass, kept, dropped


def _sitelinks(args: argparse.Namespace, paths: Mapping[str, pathlib.Path]) -> int:
    _, exported, mass, kept, _ = _open(args, paths)
    qids = SP.qids_by_site(exported.external, origin="site_external_ids.jsonl")
    shared = G.shared_counts(exported.external, repairs=REPAIRS)
    suspect = suspect_links(lanes.REMEDIATION / "bcases")
    sites: dict[str, dict[str, Any]] = {}
    for question in kept:
        if question.site_id in sites:
            continue
        qid, withheld = item_for(
            question.site_id, qids.get(question.site_id), shared=shared, suspect=suspect
        )
        sites[question.site_id] = {
            "qid": qid,
            "withheld": withheld,
            "country": exported.sites[question.site_id]["country"],
            "room": evidence_room(question.site_id, question.source_batch, mass_run=mass),
        }
    http = F.HttpFetcher(max_bytes=LOOKUP_MAX_BYTES)
    try:
        pacer = F.HostPacer(pathlib.Path(args.pacing_dir), min_interval=LOOKUP_MIN_INTERVAL_SECONDS)
        fetcher = F.PacedFetcher(http, pacer)
        decided = resolve(sites, fetcher=fetcher)
    finally:
        http.close()
    _write_json(paths["sitelinks"], {site_id: asdict(row) for site_id, row in decided.items()})
    with_article = sum(1 for row in decided.values() if row.chosen)
    print(
        f"{len(decided)} sites with open questions; {sum(1 for r in decided.values() if r.qid)} "
        f"with a usable item; {with_article} given at least one article -> {paths['sitelinks']}"
    )
    return 0


def _plan(args: argparse.Namespace, paths: Mapping[str, pathlib.Path]) -> int:
    questions, exported, _, kept, dropped = _open(args, paths)
    sitelinks = read_sitelinks(paths["sitelinks"])
    records, unlinked = site_records(kept, exported=exported, sitelinks=sitelinks)
    planned = batches(records, prefix=args.prefix)
    out = paths["out"]
    R.write_batches(out, planned)
    asked = collections.Counter(name for record in records for name in record[SE.RERUN_FIELDS_KEY])
    chosen = collections.Counter(
        link["wiki"] for record in records for link in record[F.WIKI_SITELINKS_KEY]
    )
    in_plan_sites = {record["site_id"] for record in records}
    skipped = collections.Counter(
        row["rule"]
        for site_id, links in sitelinks.items()
        if site_id in in_plan_sites
        for row in links.skipped
    )
    geo = geometry(questions, exported=exported, data=pathlib.Path(args.data))
    in_plan = {r["site_id"] for r in records if "country" in r[SE.RERUN_FIELDS_KEY]}
    geo["counts"]["verified_by_geometry_and_in_this_plan"] = len(
        in_plan & set(geo["verified_site_ids"])
    )
    summary = {
        "plan": str(out),
        "sha256": R._sha256(out),
        "batches": len(planned),
        "sites": len(records),
        "fields": sum(asked.values()),
        "fields_by_field": dict(sorted(asked.items())),
        "questions_in_scope": len(questions),
        "questions_in_scope_by_field": dict(
            sorted(collections.Counter(q.field for q in questions).items())
        ),
        "not_open": _by_field_and_rule(dropped),
        "no_article": _by_field_and_rule(unlinked),
        "articles": sum(chosen.values()),
        "articles_by_wiki": dict(chosen.most_common()),
        "articles_per_site": dict(
            sorted(collections.Counter(len(r[F.WIKI_SITELINKS_KEY]) for r in records).items())
        ),
        "sitelinks_not_taken": dict(sorted(skipped.items())),
        "country_geometry": geo,
        "excluded": dropped,
        "unlinked": unlinked,
    }
    _write_json(paths["summary"], summary)
    brief = {k: v for k, v in summary.items() if k not in ("excluded", "unlinked")}
    brief["country_geometry"] = geo["counts"]
    print(json.dumps(brief, indent=1, ensure_ascii=False))
    return 0


def _by_field_and_rule(rows: Iterable[Mapping[str, str]]) -> dict[str, dict[str, int]]:
    """`{rule: {field: count}}`, the shape the plan document tabulates."""
    counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in rows:
        counts[row["rule"]][row["field"]] += 1
    return {rule: dict(sorted(fields.items())) for rule, fields in sorted(counts.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sitelink-plan")
    parser.add_argument("command", choices=("census", "export", "sitelinks", "plan", "measure"))
    parser.add_argument(
        "--pilot", action="store_true", help="the pilot: gold sites, all five fields"
    )
    parser.add_argument("--mass-run", default=str(lanes.lane().run_dir))
    parser.add_argument("--data", default=str(lanes.REMEDIATION), help="run_t02/ and snapshot/")
    parser.add_argument("--rows", default=str(ROWS), help="the mass lane's pinned ALL_ROWS.jsonl")
    parser.add_argument("--gold", default=str(GOLD))
    parser.add_argument("--pacing-dir", default=str(lanes.LOGS / "pacing"))
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--run-dir", default=None, help="measure: a prepared and fetched run")
    for name in ("questions", "export", "sitelinks", "summary", "out"):
        parser.add_argument(f"--{name}", default=None)
    args = parser.parse_args(argv)
    args.prefix = args.prefix or (PILOT_PREFIX if args.pilot else lanes.BATCH_PREFIX[LANE])
    paths = _paths(args)

    if args.command == "census":
        site_ids = R._gold_site_ids(pathlib.Path(args.gold)) if args.pilot else None
        scope = "all" if args.pilot else "writable"
        questions = census(pathlib.Path(args.mass_run), scope=scope, site_ids=site_ids)
        _write_json(paths["questions"], [asdict(q) for q in questions])
        by_field = collections.Counter(q.field for q in questions)
        print(
            f"{len(questions)} questions over {len({q.site_id for q in questions})} sites: "
            f"{dict(sorted(by_field.items()))} -> {paths['questions']}"
        )
        return 0
    if args.command == "export":
        counts = export(G.read_questions(paths["questions"]), paths["export"])
        print(f"exported {counts} -> {paths['export']}")
        return 0
    if args.command == "sitelinks":
        return _sitelinks(args, paths)
    if args.command == "plan":
        return _plan(args, paths)
    if args.run_dir is None or args.out is None:
        raise SystemExit("measure needs --run-dir and --out (the default --out is the plan)")
    result = measure(pathlib.Path(args.run_dir), sitelinks=read_sitelinks(paths["sitelinks"]))
    _write_json(paths["out"], result)
    stored = [a for a in result["articles"] if a["stored"]]
    over = [s for s in result["sites"] if not s["fits"]]
    ratios = [a["chars"] / a["estimate"] for a in stored]
    print(
        f"{len(result['sites'])} sites: {len(result['sites']) - len(over)} fit under "
        f"{MS.MAX_EVIDENCE_CHARS}, {len(over)} over; articles {len(result['articles'])}: stored "
        f"{len(stored)} (cut {sum(a['cut'] for a in stored)}), refused or failed "
        f"{len(result['articles']) - len(stored)}; stored/estimate max "
        f"{max(ratios) if ratios else None} -> {paths['out']}"
    )
    for article in result["articles"]:
        if not article["stored"]:
            print(f"  {article['site_id'][:8]} {article['feature']}: {article['failure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
