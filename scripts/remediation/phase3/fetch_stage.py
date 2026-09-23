"""Stage "fetch" of the Phase-3 runner: collect the evidence the finder stage reads.

The pilot (`output/remediation/phase3_pilot/`) ran 76 fetches over 5 sites and measured what
they bought: 2,343 KB delivered for a 200, 19 non-200 answers (403 x8, 404 x3, transport
failure x5, 504 x2, 429 x1 - **one request in four bought nothing**), and two raw OSM bbox
dumps that were 1.0 MB of the 2.34 MB total, fetched only to find one or two named features in
a 2 km box (`COST.md` §3, §7). Decision 12 (`phase3_worklist/FINDER_BRIEF.md`, quoted in
`BATCH_PLAN.md`) turned those measurements into two binding rules, both enforced here:

1. **A 60 KB per-page cap.** `MAX_PAGE_BYTES` states the arithmetic, because the source says
   "60 KB" and never a byte count.
2. **Named features, never a raw geometry dump.** `assert_named_feature` refuses the URL shape
   the pilot measured as the two expensive pages (`api.openstreetmap.org/api/0.6/map?bbox=`)
   and the Overpass spelling of the same thing (`out geom`), and the only Overpass query this
   module builds is a name-filtered one around the site's *stored* point (4.1 KB and 287 bytes
   for the same box that cost 400 KB as a dump).

What a fetch writes, and where the pilot's shape is mirrored:

* **One line per fetch through `ledger.append`**, with the url, the site (through `label`), the
  observed status and the byte count. A non-2xx is *data* - the pilot's 403/404/504/429 all got
  recorded and the run continued - so it is recorded, never raised.
* **One evidence file per fetch**, under `<run_dir>/<batch_id>/evidence/<site_id>%2F<feature>.txt`,
  URL-encoded exactly like the pilot's `evidence/` names (`urllib.parse.quote(label, safe="")`
  in `phase3_pilot/http_get.py`), holding the bytes actually read.

Two deliberate deviations from the pilot's log shape, both named because they are not free:

* The pilot's `fetch_log.jsonl` line carries `final_url`; `phase3.ledger.Entry` (piece 1, frozen
  line shape) has no field for it, and a redirect is followed by the transport anyway. The line
  records the URL that was *asked for*; the final URL is not recorded anywhere. Adding it means
  changing piece 1's ledger contract, which this piece does not do.
* The pilot's `label` was a hand-written site tag ("Satsurblia/wikidata"). Here it is
  `f"{site_id}/{feature}"`, because the batch input carries the `site_id` and no stable short
  name, and a label derived from the mutable `name` column would move between runs.

On "stage 'fetch'": the fetch line is written with `kind="fetch"` (`LedgerKind.FETCH`, the
ledger's own spelling) and `stage` set to the *audit* stage that asked for it
(`Stage.FINDER`/`Stage.REVIEWER`). Writing the string `"fetch"` into the ledger's `stage` field
is not possible without changing `model.Stage`, and it would collapse the dimension the pilot
reports with: `COST.md` §1 splits its 76 fetches into 62 finder + 14 reviewer **by the `stage`
field**, and `ledger.summarise` groups by stage. So the line carries the string "fetch" as its
`kind`, which is what a reader of `LEDGER.jsonl` sees on every fetch row.

What this layer does not do, stated so it is not mistaken for covered: it does not parse the
evidence it stores (that is the finder's job, and the pilot's warning is that reading the two
OSM dumps instead of parsing them would have cost ~3x the plan's token anchor).

**Piece 4 replaced "one target is one fetch and one ledger line" with "one target is up to three
attempts, and every attempt has its own line".** The first live batch (2026-09-21) measured why:
a single `ReadTimeout` on the Overpass target ended the whole batch **and** wrote no ledger line,
so the ledger undercounted exactly what the pilot had counted (19 non-200 of 76 requests; COST.md
§1). Three recorded outcomes now stand apart, because "I could not look" and "I looked and there
was nothing" justify different verdicts:

* **`FetchOutcome.OK`** - a 2xx answer, its bytes on disk. A valid **empty** result (Overpass
  `"elements": []`, the pilot's 287-byte `Petroglyph/overpass.txt`) is an OK attempt.
* **`FetchOutcome.HTTP_ERROR`** - a response with a non-2xx status. Recorded data.
* **`FetchOutcome.TRANSPORT_FAILURE`** - no response at all. Recorded with its reason and no
  status, and **retried** (see `MAX_ATTEMPTS`), because 25 % of the pilot's requests failed this
  way and a design that dies on one of them cannot finish a wave.

A retried target is bounded: `MAX_ATTEMPTS` attempts total, a `RETRY_BACKOFF_SECONDS` pause between
them through an injectable sleeper, and **no** fallback endpoint - which host to ask is a decision
for the operator, not something a retry loop may change silently.

**Piece 4b bounds the retries by host instead of per target.** The first live batch's ledger
measured where its 38 minutes went: 117 of its 121 fetch lines are `overpass-api.de` - 39 targets x
`MAX_ATTEMPTS`, every one of them a TLS reset the runner then slept 20 s over - while the 15 model
calls of the same batch took 39 seconds. So a host is now asked **once per run, before its first
pending target**, through a probe of its own root URL (`host_probe_url`): one request, one ledger
line (`label="host_probe:<host>"`), never retried. Any HTTP answer means the host is reachable and
nothing else about the run changes; only a `TransportFailure` marks it down, and then every pending
target on it is recorded `host_unreachable` - one line each, `attempt=0`, carrying the probe's
reason, and **no request to their URLs** - while the batch continues with the other hosts. A host
whose targets are all already on disk is not probed at all: a re-run costs exactly what it cost
before. No host is substituted and no endpoint is rotated; picking `overpass.osm.ch` because it
answers is a decision for the operator, not for this module.

**Piece 5 adds the `wikidata_entity` target and two fields.** The discover pass asks every site
about its own fields, one call per (site, field), so `period_start` and `site_type` join
`FEATURES_FOR_FIELD`, and the same stored `country`/`description`/`card_description`/year/type are
also asked against the site's **own** Wikidata item - by id, never by search - when the record
carries one. A record without a `wikidata_qid` buys no entity target (the name search answers the
`name` field's question, which is a different one). The id is read from `site_external_ids`
(`kind='wikidata_qid'`, 4,618 rows of the snapshot's 9,237), not from `card_stats.wikidata_qid`:
that column is NULL in **all 5,004** snapshot rows and no code in this repository writes it - the
only writer of a Q-id is `pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`
(`phase3/snapshot_plan.py` carries the measurement). A qid that is not a Q-number is refused
rather than written into an `ids=` parameter that would answer with no entities at all.

**2026-09-22: three additions (the gap run of the 152 over-bound sites).** The two routes change no
target of a record that does not ask for them, so `runs/mass` and every plan built before them fetch
and prompt the targets they always did. The truncation marker is **not** gated: it applies to every
page stored from now on, in any run - a page of `runs/mass` fetched again (a deleted or failed target
re-asked) is stored with the marker, beside the 27 cut pages that run stored without one. A marked
page says what the unmarked one hid, so the mixed convention is the lesser defect, and it is named
here rather than claimed away:

* **A cut page says so.** A page that stopped at `MAX_PAGE_BYTES` is stored with `TRUNCATION_MARKER`
  after the bytes read, so the prompt names what was not read instead of presenting half a page as a
  page (27 already-judged sites of the mass run were judged against such a page, unmarked). An
  incomplete UTF-8 sequence the cut left at the very end is dropped first - it is not text, and the
  judge reads the file as UTF-8.
* **A narrowed Wikidata route** (`wikidata_route: "narrow"` on the record). The full `wbgetentities`
  answer is the bulk of an over-bound site's evidence: 92 of the 152 are cut at the page cap, and a
  whitelist of the claims the five fields need is a median 2,147 characters. The narrowed route asks
  for exactly that - the English label and description and the best-rank values of P31, P17, P131,
  P2348 and P625 through the Wikidata Query Service (one query, the values' English labels included),
  and the four time-valued properties P571, P580, P582, P1619 one by one through the JSON API
  (`wbgetclaims`, every rank, each statement's rank shown). **Not the dates through WDQS**, measured
  2026-09-22: WDQS rewrites a year-precision BCE date by one year (Q37200 P571: the API says
  `-2560`, WDQS `-2559`, because XSD 1.1 counts a year 0) and converts Julian day dates to Gregorian
  (Q12506: `537-12-27` becomes `537-12-29`), so a date read there is not the value Wikidata states.
  Each answer is stored as a plain-text rendering, one statement per line, because that is a text a
  finder can quote word for word - 12 of the 44 production rows whose citation fails the writer's
  check quoted re-typed Wikidata JSON. The bytes actually read are kept beside it
  (`evidence_raw/`), so the rendering is checkable against its source. The WDQS query is shown and
  cited as the item's page (`Target.url`, 2026-09-23), not as its 2 KB GET address (`query_url`).
* **The English article through the item's own sitelink** (`enwiki_sitelink: {qid, title}` on the
  record, W12): 974 sites of the mass run had no article under their stored name while their item
  links one. The title is resolved when the plan is built (`resolve_enwiki_sitelinks`), refused for
  an item that more than one curated site shares (a parent or a generic item: 212 sites share 90
  items) and for a sitelink badged as a redirect (`REDIRECT_BADGES`), and fetched through the same
  extract URL as the name route.
"""

from __future__ import annotations

import email.utils
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote, unquote, urlencode, urlsplit

import httpx

# Dual use: `python -m phase3.fetch_stage` and `python scripts/remediation/phase3/fetch_stage.py`.
# The package is not installed, so the parent directory must be importable first (same shim as
# `run.py`); `census` is the sibling package that solved HTTP fetching for this project already.
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from census.fetch import USER_AGENT  # noqa: E402  - the project's one User-Agent string

from phase3 import ledger as L  # noqa: E402
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

#: The binding per-page cap (decision 12; `COST.md` §7 item 1). **The sources say "60 KB" and
#: never a byte count.** 60 x 1024 = **61,440 bytes** is my reading of "60 KB" (binary KB);
#: the decimal reading, 60 x 1000 = 60,000, is not stated anywhere. That is an interpretation,
#: not a measurement, and it is the only number in this module that is read off a phrase
#: rather than off the pilot's log.
MAX_PAGE_BYTES = 60 * 1024

#: Radius of the named-feature Overpass query, in metres. `COST.md` §3 measures the box the two
#: dumps covered as "a 2 km box"; the pilot's own named-feature queries used `around:600` and
#: `around:2000` metres (`fetch_log.jsonl`: `Petroglyph/overpass_stored_features`,
#: `Petroglyph/overpass_beach`). This is the pilot's 2 km, not a new guess.
NAMED_FEATURE_RADIUS_M = 2000

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
WIKIPEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"
#: The Wikidata Query Service. Verified 2026-09-22 with the project's User-Agent: a truthy query for
#: Q10288 answered HTTP 200, `application/sparql-results+json`, 2,622 bytes.
WDQS_ENDPOINT = "https://query.wikidata.org/sparql"

#: What a stored page that stopped at `MAX_PAGE_BYTES` carries after its bytes. The finder reads it in
#: the prompt and the citation check reads it in the page, and neither can mistake it for the page:
#: it is in square brackets, like the prompt's other markers (`[failed:`, `[absent:`).
TRUNCATION_MARKER = (
    f"\n[truncated: this page was cut at the fetch stage's {MAX_PAGE_BYTES:,}-byte page cap "
    "(fetch_stage.MAX_PAGE_BYTES). Everything after this point was never read, so it shows "
    "nothing about the stored value either way.]\n"
)

#: The User-Agent this client sends, re-exported under this module's own name so the string is
#: visible where the request is built. `census.fetch.USER_AGENT` is the project's one spelling of
#: it: `AncientNerdsSiteAudit/1.0 (https://ancientnerds.com; database audit;
#: ancient.nerds@protonmail.com)` - a named client, a real site and a contact address.
#:
#: Why this is pinned here: overpass-api.de answers a request it will not serve with 89 bytes of
#: plain text (`output/remediation/phase3_pilot/evidence/Didnauri%2Foverpass_shiraki.txt`):
#:
#:     Please include a meaningful User-Agent string with your requests to avoid rate-limiting.
#:
#: The pilot's own client did send one (`http_get.py:UA`, `AncientMap-Phase3-Pilot/1.0
#: (https://github.com/ancientnerds; martin@example.invalid)`) and still got that body - with
#: **HTTP 429** from `overpass.kumi.systems` (`fetch_log.jsonl`, 2026-09-20T22:22:35), i.e. it is
#: this service's rate-limit body, not proof of a missing header. "Meaningful" is the service's
#: word and no source states what satisfies it: whether the runner's own string is accepted is
#: **unverified** - no live request is made from this piece. What *is* pinned is that every request
#: carries this non-default, identifying string instead of httpx's own `python-httpx/x.y`.
PHASE3_USER_AGENT = USER_AGENT

#: How many times one target may be asked in total (so: two retries). **A chosen bound, not a
#: measurement**: no source states an attempt budget. What the sources state is that the weather
#: is bad - `COST.md` §1: 19 non-200 of 76 requests (403 x8, 404 x3, transport x5, 504 x2, 429 x1)
#: - and that the pilot's own retried 504 and 429 succeeded.
MAX_ATTEMPTS = 3

#: The pause before retry 1 and retry 2, in seconds. **A chosen bound**, and the only number here
#: whose source is a log line rather than a phrase: `fetch_log.jsonl` has the failed 504 at
#: 2026-09-20T22:21:01Z (`Pannonian/overpass_stored_point`) and its successful re-ask 20 s later at
#: 22:21:21Z. That 20 s is a request *plus* a pause, so it is read as "the pilot waited on the
#: order of seconds", not as a delay to copy.
RETRY_BACKOFF_SECONDS = (1.0, 3.0)

#: The longest a retry may be postponed because a **host asked for it** (`Retry-After`, RFC 9110
#: section 10.2.3). **A chosen bound**, deliberately the same 60 s as `HOST_LOCK_WAIT_SECONDS`, so
#: no path in this module blocks longer than a minute on one host. A host that asks for more is not
#: disobeyed: the target is recorded as given up on, with the asked-for delay in its own line, and
#: the batch carries on. Re-asking sooner than the host asked is the impoliteness the pacer exists
#: to prevent, so waiting less is not an option either.
RETRY_AFTER_CAP_SECONDS = 60.0

#: Statuses worth a second attempt: 429 (with the body above) and every 5xx. Everything else -
#: 400, 403, 404 - is an answer the same question gets again unchanged, so it is recorded once and
#: not re-asked.
RETRYABLE_STATUSES = frozenset({408, 429})

#: How long the Overpass target may take, in seconds, versus the client's own `timeout` for the
#: other hosts. **A chosen bound, not a measurement.** What is measured: the first live batch lost
#: the Overpass request to a read timeout at 40 s (`run.py --timeout`), and the enwiki target for
#: the same site answered in the same batch (`LEDGER.jsonl`, `31860bc4.../enwiki`, 4,356 bytes).
#: Wikipedia's `prop=extracts|coordinates` already carries the article's coordinate claim, so
#: Overpass is a **second opinion** here - it is kept, bounded, and must never be the reason a site
#: is unverifiable when the enwiki evidence answered the question.
OVERPASS_TIMEOUT = 20.0

#: The ledger label of a host probe: `host_probe:<host>`. A probe line is a fetch line like any
#: other (the ledger records every request that left the machine), and this prefix is what tells it
#: from a target's attempt when a reader totals a run.
HOST_PROBE_PREFIX = "host_probe:"

#: Feature slugs. The first two are the pilot's own label suffixes (`fetch_log.jsonl`:
#: `Satsurblia/enwiki`, `Karpasia/wd_kition_label`); `overpass_named` names the query shape the
#: pilot used for the same job under `overpass_bbox`/`overpass_stored_features`, kept distinct
#: from the dumps those labels also covered. `wikidata_entity` names the pilot's
#: `Special:EntityData/Q28220554.json` fetch - here as the API query the project already uses for
#: the same data (`scripts/audit_wikidata_batch.py:56`), so one request carries claims, labels and
#: descriptions of the **site's own** item instead of a full JSON dump.
FEATURE_ENWIKI = "enwiki"
FEATURE_WIKIDATA_SEARCH = "wikidata_search"
FEATURE_WIKIDATA_ENTITY = "wikidata_entity"
FEATURE_OVERPASS_NAMED = "overpass_named"

#: The narrowed Wikidata route (2026-09-22, new runs only; see the module docstring). It stands in for
#: `FEATURE_WIKIDATA_ENTITY` on a record that carries `wikidata_route: "narrow"`, and only there.
WIKIDATA_ROUTE_KEY = "wikidata_route"
WIKIDATA_ROUTE_NARROW = "narrow"
FEATURE_WIKIDATA_TRUTHY = "wikidata_truthy"
#: The item-valued and coordinate properties read through WDQS, best rank, English labels included.
TRUTHY_PROPERTIES: tuple[str, ...] = ("P31", "P17", "P131", "P2348", "P625")
#: The time-valued properties, each read through the JSON API - never through WDQS, which rewrites
#: BCE years and Julian dates (measured; module docstring).
DATE_PROPERTIES: tuple[str, ...] = ("P571", "P580", "P582", "P1619")
#: `wikidata_claims.P571` and so on: one target per time-valued property.
DATE_FEATURE_PREFIX = "wikidata_claims."
#: The English property labels the renderings print, as Wikidata states them (verified 2026-09-22).
#: Fixed here rather than fetched, so a rendering is a function of the answer alone.
PROPERTY_LABELS: dict[str, str] = {
    "P31": "instance of",
    "P17": "country",
    "P131": "located in the administrative territorial entity",
    "P2348": "time period",
    "P625": "coordinate location",
    "P571": "inception",
    "P580": "start time",
    "P582": "end time",
    "P1619": "date of official opening",
}
#: The qualifiers a date statement carries that change what it says, and the values of the first,
#: as Wikidata labels them (verified 2026-09-22). `circa` on a year is part of the year.
QUALIFIER_LABELS: dict[str, str] = {
    "P1480": "sourcing circumstances",
    "P1319": "earliest date",
    "P1326": "latest date",
}
SOURCING_CIRCUMSTANCES: dict[str, str] = {
    "Q5727902": "circa",
    "Q18122778": "presumably",
    "Q56644435": "probably",
    "Q18603603": "hypothetically",
}
#: Wikidata's time precisions (`wikibase:timePrecision`), named for the reader of a rendering.
TIME_PRECISION: dict[int, str] = {
    6: "millennium",
    7: "century",
    8: "decade",
    9: "year",
    10: "month",
    11: "day",
}
#: The two calendar models Wikidata dates carry.
CALENDAR_MODEL: dict[str, str] = {
    "http://www.wikidata.org/entity/Q1985727": "proleptic Gregorian calendar",
    "http://www.wikidata.org/entity/Q1985786": "proleptic Julian calendar",
}
#: The English article through the item's own sitelink (W12, new runs only).
ENWIKI_SITELINK_KEY = "enwiki_sitelink"
FEATURE_ENWIKI_SITELINK = "enwiki_sitelink"
#: Where the bytes actually read are kept for a feature whose evidence file is a rendering.
RAW_EVIDENCE_DIR = "evidence_raw"

#: The fields the **discover pass** asks about (`phase3/snapshot_plan.py`), and what each buys.
#: `card_description` lives in `card_stats` (see `snapshot_plan.FIELD_STORED_IN`); its evidence is
#: the same article and item as the other four fields'. `period_start` and `site_type` join the
#: table in piece 5: neither buys Overpass - a year and a type are claims about the site, not
#: features around its stored point - and both are asked against the article and, when the record
#: carries one, the Wikidata item.
FEATURES_FOR_FIELD: dict[str, tuple[str, ...]] = {
    "lat/lon": (FEATURE_ENWIKI, FEATURE_OVERPASS_NAMED),
    "name": (FEATURE_ENWIKI, FEATURE_WIKIDATA_SEARCH),
    "country": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "description": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "card_description": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "period_start": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "site_type": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
}

#: Census check families that buy **no** fetch at all (decision 12: "T02 is one human
#: vocabulary decision plus a short exception list, not 117 reviews"; `COST.md` §7 item 5
#: measured the three T02 findings of the pilot: none was a data error). A finder run per T02
#: finding would be money burnt, so no target is built for them - and the tally of that
#: decision is visible in the report as a site with fewer targets than findings.
NO_FETCH_PREFIXES = frozenset({"T02"})

#: URL shapes the pilot measured as raw geometry dumps. `api/0.6/map?bbox=` delivered 598 KB
#: and 400 KB; `out geom` is Overpass's spelling of the same thing. Both are refused.
RAW_GEOMETRY_MARKERS = ("/api/0.6/map?", "out geom", "out:geom")

#: A Wikidata item id: `Q` followed by digits. The one shape `wikidata_entity_url` accepts; the
#: snapshot's own qids are read against it at plan time (`phase3/snapshot_plan.py`), so the plan
#: refuses the same ids the URL builder would refuse instead of building a URL that answers with
#: no entities.
QID_PATTERN = re.compile(r"Q[1-9][0-9]*")


class TransportFailure(RuntimeError):
    """No response arrived at all (DNS, connect, reset, timeout mid-body).

    Raised, never turned into an empty result: a caller must be able to tell "answered with
    nothing usable" from "could not ask" (`census/fetch.py` makes the same distinction).
    """


class RawGeometryRefused(ValueError):
    """A URL asks for raw geometry. Decision 12 forbids it; see `assert_named_feature`."""


class EvidenceConflict(RuntimeError):
    """An evidence file for this (site, feature) exists and holds *different* bytes."""


def write_once(path: Path, body: bytes, *, source: str) -> bool:
    """Write `body` to `path` unless it is already there: the evidence store's one write rule.

    Identical bytes are left alone (`False`). Different bytes raise `EvidenceConflict`, naming
    `source` - where the new bytes came from - because a recorded file is never overwritten. Otherwise
    the bytes go to a `.tmp` beside `path` and are swapped in, so a kill leaves no half file behind
    (`True`). Shared by `EvidenceStore.write` and the search lane's byte-identical copies
    (`search_plan.prepare_search_batch`), so the rule has one spelling.
    """
    if path.exists():
        if path.read_bytes() != body:
            raise EvidenceConflict(
                f"{path} holds different bytes than {source}; refusing to overwrite a recorded file"
            )
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(path)
    return True


def is_retryable_status(status: int | None) -> bool:
    """429/408 or any 5xx. A 400/403/404 is asked once: the next answer would be the same one."""
    if status is None:
        return False
    return status in RETRYABLE_STATUSES or 500 <= status < 600


def parse_retry_after(value: str | None, *, received_at: float) -> float | None:
    """How long a host asked to be left alone, or `None` when it did not say.

    RFC 9110 section 10.2.3 gives the field exactly two forms - `Retry-After = HTTP-date /
    delay-seconds`, `delay-seconds = 1*DIGIT` - and only those two are read. A value in neither
    form is treated as if the field were absent, so the run waits its own backoff rather than a
    delay it could not read; that is the conservative side of the choice, and it is not a
    fallback: nothing is asked twice and no endpoint is substituted.

    `delay-seconds` is ASCII digits by its own grammar, so `isascii()` is tested first: Python's
    `str.isdigit()` is true for other scripts' digits (`"\u0663"`), and this module does not
    accept a header value that the grammar it cites excludes.

    `received_at` is the moment the response arrived, passed in rather than read here so the
    HTTP-date branch can be tested without a wall clock. An HTTP-date is GMT by definition; a
    parse that comes back naive is read as UTC, because reading it as the machine's local time
    would move the delay by this machine's own offset.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.isascii() and text.isdigit():
        return float(text)
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, when.timestamp() - received_at)


def host_of(url: str) -> str:
    """The host a URL belongs to, lowercased. The key every per-host decision is taken under."""
    host = urlsplit(url).hostname
    if not host:
        raise InputError(f"{url!r} carries no host; a request needs one to leave the machine")
    return host


def host_probe_url(url: str) -> str:
    """`scheme://host/` for `url`: the one address that belongs to the host and to no target.

    The probe is a request, and the ledger records it as one. Asking the host's own root - the bare
    host URL the brief's `curl` measurements used (`overpass-api.de http=000 time=0.077s`) - keeps
    the probe's ledger line from being read as an attempt on some target: no target is ever asked
    for `/`. The other candidate, reusing the first target's URL as the probe, would make that one
    request both a probe and an attempt, and one of the two would go unrecorded.
    """
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


#: Which hosts get the shorter bound, by host name. Keyed by host rather than by URL so that the
#: run's probe - which asks the host's root, not the endpoint - waits exactly as long as the targets
#: it gates: a host that never answers costs one bounded wait per run, never a longer one than the
#: operator's own `OVERPASS_TIMEOUT`.
SHORT_TIMEOUT_HOSTS: dict[str, float] = {host_of(OVERPASS_ENDPOINT): OVERPASS_TIMEOUT}


def timeout_for(url: str) -> float | None:
    """The per-target bound for this URL's host, or `None` for the client's own default.

    Overpass is the one host this module asks a *second opinion* of, and the one the first live
    batch lost to a read timeout, so it gets the shorter bound (`OVERPASS_TIMEOUT`).
    """
    return SHORT_TIMEOUT_HOSTS.get(host_of(url))


@dataclass(frozen=True)
class FetchedPage:
    """One answer from the wire. `body` is what was actually read, capped."""

    status: int
    final_url: str
    body: bytes
    truncated: bool
    #: What the host asked in `Retry-After`, in seconds, or `None` when it did not ask. A field on
    #: the answer rather than a decision: the retry loop is what decides, and other callers (a
    #: probe) read no delay from it at all.
    retry_after: float | None = None

    @property
    def ok(self) -> bool:
        """2xx. A non-2xx is a measured outcome, not an error: it is recorded as data."""
        return 200 <= self.status < 300


@runtime_checkable
class Fetcher(Protocol):
    """The seam. Anything with this method can stand in for the network."""

    def get(self, url: str) -> FetchedPage:
        """Fetch `url`, or raise `TransportFailure` if no response arrives."""
        ...


def _read_capped(chunks: Iterable[bytes], max_bytes: int = MAX_PAGE_BYTES) -> tuple[bytes, bool]:
    """Read at most `max_bytes` (`MAX_PAGE_BYTES` unless a caller says otherwise), **stopping the
    stream** at the cap.

    Truncation is a stop, not a slice: the body is never buffered in full and then cut. The
    pilot's two dumps (598 KB, 400 KB) are exactly the pages that must not be pulled over the
    wire to be thrown away, and a test that counts the bytes the transport actually yielded
    fails if this ever becomes read-then-slice.

    A page whose body is exactly `max_bytes` is reported `truncated=True`: telling an
    exactly-capped page from a cut one requires reading past the cap, which is the thing the
    cap forbids.
    """
    body = bytearray()
    for chunk in chunks:
        room = max_bytes - len(body)
        if len(chunk) > room:
            body.extend(chunk[:room])
            return bytes(body), True
        body.extend(chunk)
        if len(body) == max_bytes:
            return bytes(body), True
    return bytes(body), False


class HttpFetcher:
    """The real client: httpx, a descriptive User-Agent, redirects followed, cap enforced.

    `transport` is the injectable seam (`census/fetch.py` takes an `httpx.BaseTransport` the
    same way): tests pass `httpx.MockTransport` or a counting stream and never open a socket.

    `max_bytes` is the page cap this client stops every stream at. The default is
    `MAX_PAGE_BYTES`, so every Phase-3 caller reads exactly what it read before (2026-09-23, WB-A1
    of the Phase-4 design). Phase 4 builds a second client with 1 MiB for `*.wikipedia.org` and
    `wikidata.org` only: at 60 KB, 18 of the mass run's 5,004 enwiki answers and 115 of its 4,618
    `wikidata_entity` answers stopped at exactly 61,440 bytes, JSON nobody can parse (measured
    2026-09-23; five of the cut entities re-measured at 64-146 KB). Which host gets which client
    is Phase 4's decision (`phase4/sources_stage.py`), not this class's.
    """

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 40.0,
        user_agent: str = USER_AGENT,
        clock: Callable[[], float] = time.time,
        max_bytes: int = MAX_PAGE_BYTES,
    ) -> None:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise ValueError(f"max_bytes={max_bytes!r} is not a positive byte count")
        self._max_bytes = max_bytes
        self._clock = clock
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "*/*"},
        )

    def get(self, url: str) -> FetchedPage:
        """GET `url`. Every URL is checked against decision 12 before a socket is opened."""
        assert_named_feature(url)
        timeout = self._timeout(url)
        try:
            with self._client.stream("GET", url, timeout=timeout) as response:
                body, truncated = _read_capped(response.iter_bytes(), self._max_bytes)
                return FetchedPage(
                    status=response.status_code,
                    final_url=str(response.url),
                    body=body,
                    truncated=truncated,
                    retry_after=parse_retry_after(
                        response.headers.get("retry-after"), received_at=self._clock()
                    ),
                )
        except httpx.HTTPError as exc:
            # No response, or the body died mid-stream: both are "could not ask". A partial
            # body is not a result and is not returned.
            raise TransportFailure(f"GET {url}: {type(exc).__name__}: {exc}") from exc

    def _timeout(self, url: str) -> httpx.Timeout | float:
        """`httpx`'s own default for this client, or the target's shorter bound (`timeout_for`)."""
        bound = timeout_for(url)
        return self._client.timeout if bound is None else bound

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


HOST_MIN_INTERVAL_SECONDS = 0.2
#: Hosts that are asked more slowly than `HOST_MIN_INTERVAL_SECONDS`. WDQS limits each client to 60
#: seconds of query time per minute and answers `429` with `Retry-After: 120` beyond it (measured
#: 2026-09-22, seven times in one scratch fetch of the gap plan at the default pace), so it gets one
#: query per second from this machine. A chosen bound, not a measured optimum.
HOST_MIN_INTERVAL_OVERRIDES: dict[str, float] = {"query.wikidata.org": 1.0}
HOST_LOCK_STALE_SECONDS = 30.0
HOST_LOCK_WAIT_SECONDS = 60.0
HOST_LOCK_POLL_SECONDS = 0.05


class PacerTimeout(RuntimeError):
    """A host's lock was held so long that waiting further would only hide a stuck neighbour."""


class HostPacer:
    """One request at a time per host, **across processes**.

    Parallel batches are separate processes, so an in-memory limiter would multiply the rate per
    host by the number of jobs - which is the impoliteness a pacer exists to prevent. The mutex is
    therefore a file beside a per-host stamp: take the lock, measure the time since this host's last
    request, sleep the rest of the interval, rewrite the stamp, release the lock. The **stamp**, not
    the lock, is what sets the interval, so a lock lost to a crash costs at most one early request.

    `clock` and `sleep` are injected, and the lock records its own acquisition time in the file
    rather than relying on the filesystem clock, so tests drive both without mocking `os.stat`.

    **Ownership is carried in the lock's content**, and three rules were added on 2026-09-21 after
    eight processes on one host were measured: four died with `PermissionError: [WinError 32]`
    (Windows refuses to delete a file another process holds open) and four timed out waiting. The
    cause was not the speed of the loop but the identity of a lock: it is created empty and filled a
    moment later, and treating that moment as "a leftover" stole a lock from a live holder - whose
    release then deleted a file that was no longer its own. So: a lock's **age** (its mtime when its
    content says nothing) decides whether it may be taken over; a lock is deleted only while its
    content is still ours; and a lock that cannot be deleted is waited out rather than spun on.

    Honest about its reach: this is **machine-local**. Two machines running this fleet share no
    per-host state, so the claim it supports is "this machine does not hammer a host", not "a host
    sees at most five requests a second worldwide".
    """

    def __init__(
        self,
        root: Path,
        *,
        min_interval: float = HOST_MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        stale_after: float = HOST_LOCK_STALE_SECONDS,
        wait_seconds: float = HOST_LOCK_WAIT_SECONDS,
    ) -> None:
        self.root = Path(root)
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._stale_after = stale_after
        self._wait_seconds = wait_seconds

    def stamp_of(self, host: str) -> Path:
        return self.root / f"{host}.stamp"

    def lock_of(self, host: str) -> Path:
        return self.root / f"{host}.lock"

    def wait(self, host: str) -> float:
        """Block until a request to `host` is polite. Returns the seconds slept (0.0 = no wait)."""
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.lock_of(host)
        deadline = self._clock() + self._wait_seconds
        while True:
            try:
                handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                # Best effort on purpose: a lock that outlived its process must not wedge the
                # whole fleet, and the worst case of losing this race is one early request. A lock
                # that is *not* stale, or that cannot be deleted, is waited for - never spun on.
                if self._is_stale(lock) and self._take_over(lock):
                    continue
                if self._clock() > deadline:
                    raise PacerTimeout(
                        f"{lock} was held for {self._wait_seconds:.0f}s - the holder is stuck, "
                        "not busy"
                    ) from None
                self._sleep(HOST_LOCK_POLL_SECONDS)
                continue
            token = f"{self._clock():.6f} {os.urandom(8).hex()}"
            try:
                os.write(handle, token.encode())
                return self._hold(host)
            finally:
                os.close(handle)
                self._release(lock, token)

    def _hold(self, host: str) -> float:
        """Inside the lock: sleep the rest of the interval, then claim this request's time."""
        stamp = self.stamp_of(host)
        last = self._read_stamp(stamp)
        interval = max(self.min_interval, HOST_MIN_INTERVAL_OVERRIDES.get(host, 0.0))
        wait = 0.0 if last is None else max(0.0, interval - (self._clock() - last))
        if wait > 0:
            self._sleep(wait)
        stamp.write_text(f"{self._clock():.6f}", encoding="utf-8")
        return wait

    @staticmethod
    def _read_stamp(stamp: Path) -> float | None:
        """The time a stamp or lock records. A lock carries `"<time> <token>"`; a stamp the time."""
        try:
            text = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        try:
            return float(text.split(" ", 1)[0])
        except ValueError:
            return None

    def _is_stale(self, lock: Path) -> bool:
        """Whether a lock that exists may be taken over.

        The **age of the file** decides, because a lock is created empty and written a moment later.
        Until 2026-09-21 unreadable content meant "a leftover", which stole a lock from a live
        holder - measured: with eight processes on one host, four of them then failed with
        `WinError 32` (deleting a file another process has open) and four timed out. An mtime is set
        at creation, so it has no such window.
        """
        held_since = self._read_stamp(lock)
        if held_since is None:
            try:
                held_since = lock.stat().st_mtime
            except OSError:
                return False  # gone under us; the next create attempt decides
        return self._clock() - held_since > self._stale_after

    @staticmethod
    def _take_over(lock: Path) -> bool:
        """Delete a lock that outlived its holder. False when it cannot be deleted right now."""
        try:
            lock.unlink()
        except FileNotFoundError:
            return True  # already gone; the caller's next create attempt decides
        except OSError:
            return False  # held open somewhere (Windows refuses): wait, do not spin
        return True

    @staticmethod
    def _release(lock: Path, token: str) -> None:
        """Delete the lock only while it is still ours, and never let that failure out.

        A lock we do not own is not ours to delete: taking it over is `_take_over`'s job and it
        respects the age rule. On Windows, deleting a file another process holds open raises
        `PermissionError` - which used to abort the whole fetch, the failure this method exists to
        contain.
        """
        try:
            if lock.read_text(encoding="utf-8").strip() != token:
                return
            lock.unlink(missing_ok=True)
        except OSError:
            return


class PacedFetcher:
    """A `Fetcher` that waits its turn per host before delegating.

    It decorates the seam instead of threading a pacer through `probe_host`, `one_attempt` and
    `collect_batch`: every request in this module goes through `Fetcher.get`, so one decorator paces
    the reachability probe, every retry and every target, and no call site can forget.
    """

    def __init__(self, inner: Fetcher, pacer: HostPacer) -> None:
        self._inner = inner
        self._pacer = pacer

    def get(self, url: str) -> FetchedPage:
        self._pacer.wait(host_of(url))
        return self._inner.get(url)


def assert_named_feature(url: str) -> None:
    """Refuse a raw geometry dump (decision 12). Named features, not "give me the bbox".

    The pilot paid 1.0 MB of its 2.34 MB for two such dumps to find one or two named features;
    the same box answered in 287 bytes for a name-filtered Overpass query.

    The URL is unquoted before the check: an Overpass query travels percent-encoded, so
    `out%20geom` is the same request as `out geom`.
    """
    marker = next((m for m in RAW_GEOMETRY_MARKERS if m in unquote(url)), None)
    if marker is not None:
        raise RawGeometryRefused(
            f"{url!r} asks for raw geometry ({marker!r}); decision 12 wants named features "
            "(COST.md §3: two OSM bbox dumps were 1.0 MB of 2.34 MB)"
        )


def wikipedia_extract_url(name: str) -> str:
    """The `enwiki` target: the article's plaintext extract plus its own coordinate claim.

    The same parameters the pilot used (`fetch_log.jsonl`, `Satsurblia/enwiki`).
    """
    return (
        WIKIPEDIA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "query",
                "prop": "extracts|coordinates",
                "explaintext": "1",
                "redirects": "1",
                "titles": name,
                "format": "json",
            },
            quote_via=quote,
        )
    )


def wikidata_search_url(name: str) -> str:
    """The `wikidata_search` target: candidate items for a *name*, not for a geometry.

    The worklist findings carry no Q-id (re-verified: no `Q\\d+` in any of the 2,210 findings'
    `note`/`current_value`), so the entity data the pilot fetched by id has to be reached by
    search first. This is the search hop the pilot had to make by hand for Petroglyph's URL.
    """
    return (
        WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "uselang": "en",
                "limit": "5",
                "format": "json",
            },
            quote_via=quote,
        )
    )


def _require_qid(qid: str) -> str:
    if not QID_PATTERN.fullmatch(qid):
        raise InputError(
            f"wikidata_qid {qid!r} is not a Q-number (Q followed by digits); refusing to build a "
            "Wikidata URL that would answer with no entities"
        )
    return qid


def wikidata_entity_url(qid: str) -> str:
    """The `wikidata_entity` target: one Q-id's claims, labels and descriptions, by id.

    This is the hop the pilot made by hand (`Special:EntityData/Q28220554.json`,
    `phase3_pilot/evidence/`): the item is **known**, so nothing is searched for and nothing is
    guessed. The API query is the project's existing one for the same data
    (`scripts/audit_wikidata_batch.py:56` uses `props=claims|labels`); `descriptions` is added
    because a description is one of the fields the discover pass asks about.

    A qid that is not a Q-number raises instead of being written into the URL: a mangled `ids=`
    value answers `{"entities":{}}`, which reads as "the item says nothing" and would be recorded
    as evidence against the site's value.
    """
    return (
        WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbgetentities",
                "ids": _require_qid(qid),
                "props": "claims|labels|descriptions",
                "languages": "en",
                "format": "json",
            },
            quote_via=quote,
        )
    )


def wikidata_truthy_query(qid: str) -> str:
    """One WDQS query: the item's English label and description, and the best-rank values of the
    `TRUTHY_PROPERTIES` with their English labels. No time-valued property is in it (docstring).

    One `UNION` branch per property, each naming its `p:`/`ps:` predicates, rather than one pattern
    over a variable predicate: measured 2026-09-22 on Q99151 (Ourense), the variable-predicate form
    took 20.0 s and the explicit one 0.3 s, and the gap run's scratch fetch with the first form drew
    seven `429` answers (`Retry-After: 120`) and six read timeouts from WDQS over 194 sites.
    """
    item = f"wd:{_require_qid(qid)}"
    branches = [
        f"{{ BIND(wd:{pid} AS ?property) {item} p:{pid} ?statement . "
        f"?statement ps:{pid} ?value ; a wikibase:BestRank . "
        'OPTIONAL { ?value rdfs:label ?valueLabel . FILTER(LANG(?valueLabel) = "en") } }'
        for pid in TRUTHY_PROPERTIES
    ]
    branches.append(
        f'{{ BIND("label" AS ?property) {item} rdfs:label ?value . FILTER(LANG(?value) = "en") }}'
    )
    branches.append(
        f'{{ BIND("description" AS ?property) {item} schema:description ?value . '
        'FILTER(LANG(?value) = "en") }'
    )
    return "SELECT ?property ?value ?valueLabel WHERE { " + " UNION ".join(branches) + " }"


def wikidata_truthy_url(qid: str) -> str:
    """The `wikidata_truthy` request: `wikidata_truthy_query` as a WDQS GET (`Target.query_url`)."""
    return (
        WDQS_ENDPOINT
        + "?"
        + urlencode({"query": wikidata_truthy_query(qid), "format": "json"}, quote_via=quote)
    )


def wikidata_truthy_citation_url(qid: str) -> str:
    """The `wikidata_truthy` target's address in the prompt and in a citation (`Target.url`).

    The item's own page - a reader who opens it sees the statements the rendering lists - with the
    feature as its fragment, so it is distinct from any other target of the site. Not the query
    itself: that is ~2 KB of percent-encoding, and a citation is matched by URL byte for byte.
    """
    return f"https://www.wikidata.org/wiki/{_require_qid(qid)}#{FEATURE_WIKIDATA_TRUTHY}"


def wikidata_claims_url(qid: str, pid: str) -> str:
    """One `wikidata_claims.<pid>` target: every statement of one property, as the JSON API has it.

    `wbgetclaims` takes one property per request (a `P31|P17` list is refused with `param-invalid`,
    measured by the remaining-work map), which is why each time-valued property is its own target.
    """
    if pid not in DATE_PROPERTIES:
        raise InputError(f"{pid!r} is not one of the time-valued properties {DATE_PROPERTIES}")
    return (
        WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbgetclaims",
                "entity": _require_qid(qid),
                "property": pid,
                "format": "json",
            },
            quote_via=quote,
        )
    )


def wikidata_sitelinks_url(qids: Iterable[str]) -> str:
    """The items' English sitelinks, up to 50 ids per request (the API's own limit)."""
    wanted = [_require_qid(qid) for qid in qids]
    if not wanted or len(wanted) > 50:
        raise InputError(f"{len(wanted)} ids: wbgetentities takes 1 to 50 per request")
    return (
        WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(wanted),
                "props": "sitelinks",
                "sitefilter": "enwiki",
                "format": "json",
            },
            quote_via=quote,
        )
    )


class EvidenceUnrenderable(ValueError):
    """A 2xx answer for a rendered feature that is not the shape its renderer reads. Raised: a
    rendering of an answer nobody can read would be evidence nobody fetched."""


def _json_answer(body: bytes, *, what: str) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceUnrenderable(f"{what}: the answer is not JSON: {exc}") from None


def _entity_id(uri: str) -> str:
    """`http://www.wikidata.org/entity/Q41` -> `Q41`; any other value is returned unchanged."""
    prefix = "http://www.wikidata.org/entity/"
    return uri[len(prefix) :] if uri.startswith(prefix) else uri


def render_truthy(qid: str, body: bytes) -> str:
    """The WDQS answer as text: one line per value, sorted, and `none` for an absent property.

    Sorted, so two answers with the same content render identically whatever order WDQS returned
    them in; `none` is printed because "the item states no P2348" is evidence too, and a missing line
    could not be told from a line that was lost.
    """
    what = f"{qid}/{FEATURE_WIKIDATA_TRUTHY}"
    payload = _json_answer(body, what=what)
    try:
        bindings = payload["results"]["bindings"]
    except (KeyError, TypeError):
        raise EvidenceUnrenderable(f"{what}: no results.bindings in the answer") from None
    label: list[str] = []
    description: list[str] = []
    values: dict[str, set[str]] = {pid: set() for pid in TRUTHY_PROPERTIES}
    for binding in bindings:
        try:
            prop = _entity_id(binding["property"]["value"])
            value = binding["value"]["value"]
        except (KeyError, TypeError):
            raise EvidenceUnrenderable(f"{what}: a binding without property/value") from None
        if prop == "label":
            label.append(value)
        elif prop == "description":
            description.append(value)
        elif prop in values:
            shown = _entity_id(value)
            named = binding.get("valueLabel", {}).get("value")
            if shown != value or named is not None:
                shown = f"{shown} {named}" if named is not None else f"{shown} (no English label)"
            values[prop].add(shown)
        else:
            raise EvidenceUnrenderable(f"{what}: a binding for a property nobody asked for: {prop}")
    lines = [
        f"Wikidata item {qid}, read through the Wikidata Query Service: its English label and "
        f"description, and the best-rank values of {', '.join(TRUTHY_PROPERTIES)}.",
        f"label (en): {' | '.join(sorted(label)) if label else 'none'}",
        f"description (en): {' | '.join(sorted(description)) if description else 'none'}",
    ]
    for pid in TRUTHY_PROPERTIES:
        head = f"{pid} {PROPERTY_LABELS[pid]}"
        if not values[pid]:
            lines.append(f"{head}: none")
        lines.extend(f"{head}: {value}" for value in sorted(values[pid]))
    return "\n".join(lines) + "\n"


def _render_datavalue(snak: Mapping[str, Any]) -> str:
    """One snak's value in words: a time with its precision and calendar, an item id, or the text."""
    kind = snak.get("snaktype")
    if kind == "novalue":
        return "no value"
    if kind == "somevalue":
        return "unknown value"
    datavalue = snak.get("datavalue") or {}
    value = datavalue.get("value")
    if datavalue.get("type") == "time" and isinstance(value, Mapping):
        precision = value.get("precision")
        calendar = CALENDAR_MODEL.get(str(value.get("calendarmodel")), value.get("calendarmodel"))
        return (
            f"{value.get('time')} (precision {precision} = "
            f"{TIME_PRECISION.get(precision, 'unnamed')}, {calendar})"
        )
    if datavalue.get("type") == "wikibase-entityid" and isinstance(value, Mapping):
        item = str(value.get("id"))
        return f"{item} {SOURCING_CIRCUMSTANCES[item]}" if item in SOURCING_CIRCUMSTANCES else item
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def render_claims(qid: str, pid: str, body: bytes) -> str:
    """The `wbgetclaims` answer for one property as text: one line per statement, every rank.

    References are left out (they are what makes an entity 60 KB); qualifiers stay, because a
    `sourcing circumstances: circa` qualifier is part of what a date says.
    """
    what = f"{qid}/{DATE_FEATURE_PREFIX}{pid}"
    payload = _json_answer(body, what=what)
    if not isinstance(payload, Mapping) or "claims" not in payload:
        raise EvidenceUnrenderable(f"{what}: no `claims` in the answer: {str(payload)[:200]}")
    claims = payload["claims"]
    statements = claims.get(pid, []) if isinstance(claims, Mapping) else None
    if statements is None or (isinstance(claims, Mapping) and set(claims) - {pid}):
        raise EvidenceUnrenderable(f"{what}: the answer carries claims other than {pid}")
    head = f"{pid} {PROPERTY_LABELS[pid]}"
    lines = [
        f"Wikidata item {qid}, property {head}, read through the Wikidata API (wbgetclaims), "
        "every statement with its rank; references are not shown."
    ]
    if not statements:
        lines.append(f"{head}: none")
    for statement in statements:
        lines.append(
            f"{head}: {_render_datavalue(statement.get('mainsnak') or {})} "
            f"(rank {statement.get('rank')})"
        )
        for qualifier, snaks in sorted((statement.get("qualifiers") or {}).items()):
            named = (
                f"{qualifier} {QUALIFIER_LABELS[qualifier]}"
                if qualifier in QUALIFIER_LABELS
                else qualifier
            )
            for snak in snaks:
                lines.append(f"  qualifier {named}: {_render_datavalue(snak)}")
    return "\n".join(lines) + "\n"


def rendered_evidence(target: Target, body: bytes) -> str | None:
    """The text a rendered feature stores instead of the answer, or `None` for a verbatim feature."""
    qid = target.qid
    if target.feature == FEATURE_WIKIDATA_TRUTHY:
        return render_truthy(str(qid), body)
    if target.feature.startswith(DATE_FEATURE_PREFIX):
        return render_claims(str(qid), target.feature[len(DATE_FEATURE_PREFIX) :], body)
    return None


#: The sitelink badges that say the linked title is a **redirect**, not an article: "sitelink to
#: redirect" and "intentional sitelink to redirect". Verified 2026-09-23 with the project's
#: User-Agent: Q4810863 (Astibo, Estipeon's item after the external-id repair) links enwiki `Astibo`
#: with badge Q70893996, and `Astibo` redirects to `Štip#History` - the extract route follows
#: redirects, so the site would be judged on the whole article of the modern town. That is the
#: section-fragment failure behind the `History` ids the repair corrects (`qid_repair.py`).
REDIRECT_BADGES: dict[str, str] = {
    "Q70893996": "sitelink to redirect",
    "Q70894304": "intentional sitelink to redirect",
}


@dataclass(frozen=True)
class Sitelink:
    """An item's English sitelink as the API states it: the title and the badges on it."""

    title: str
    badges: tuple[str, ...]


def enwiki_sitelinks_from_answer(body: bytes) -> dict[str, Sitelink | None]:
    """`{qid: its English sitelink, or None}` out of a `wikidata_sitelinks_url` answer.

    An id the answer marks `missing` raises: that item does not exist, which is a fact about the
    record's id, not an item without an article. A sitelink without its `badges` list raises too:
    the API always sends it (`[]` when there is none), and a badge is what says a title is a redirect.
    """
    payload = _json_answer(body, what="wbgetentities sitelinks")
    entities = payload.get("entities") if isinstance(payload, Mapping) else None
    if not isinstance(entities, Mapping):
        raise EvidenceUnrenderable(f"sitelinks answer carries no entities: {str(payload)[:200]}")
    links: dict[str, Sitelink | None] = {}
    for qid, entity in entities.items():
        if "missing" in entity:
            raise EvidenceUnrenderable(f"{qid}: Wikidata says this item does not exist")
        link = (entity.get("sitelinks") or {}).get("enwiki")
        if link is None:
            links[qid] = None
            continue
        title = link.get("title") if isinstance(link, Mapping) else None
        badges = link.get("badges") if isinstance(link, Mapping) else None
        if not isinstance(title, str) or not title or not isinstance(badges, list):
            raise EvidenceUnrenderable(
                f"{qid}: an enwiki sitelink without title and badges: {link!r}"
            )
        links[qid] = Sitelink(title=title, badges=tuple(str(badge) for badge in badges))
    return links


@dataclass(frozen=True)
class SitelinkResolution:
    """What the item's sitelink gives a site: an article title, or the reason it gives none."""

    qid: str
    title: str | None
    refused: str | None

    def to_record(self) -> dict[str, str]:
        """The record field targets_for_site reads. Only a resolution with a title has one."""
        if self.title is None or self.refused is not None:
            raise InputError(f"{self.qid}: no usable sitelink ({self.refused or 'no article'})")
        return {"qid": self.qid, "title": self.title}


def resolve_enwiki_sitelinks(
    qids_by_site: Mapping[str, str],
    *,
    shared: Mapping[str, int],
    fetcher: Fetcher,
) -> dict[str, SitelinkResolution]:
    """`{site_id: resolution}` for the sites to route through their item's English sitelink.

    `shared` is `{qid: number of curated sites carrying it}` over the whole curated set, not over
    this selection: an item that more than one site shares is a parent or a generic item (212 sites
    share 90 items; `Dolmens of Sardinia` links `Dolmen`), and its article describes something other
    than any one of them - so it is refused, with the count, and nothing is fetched for it. Every
    other item is asked in batches of 50; a request that is not a 2xx raises (the plan builder is
    run by hand, and a plan built on a failed lookup would silently route fewer sites). A sitelink
    that carries a redirect badge (`REDIRECT_BADGES`) is refused with the badge named: its title is
    another article's, or a section of one, not the item's own article.
    """
    resolutions: dict[str, SitelinkResolution] = {}
    wanted: dict[str, list[str]] = {}
    for site_id, qid in sorted(qids_by_site.items()):
        count = shared.get(_require_qid(qid), 0)
        if count > 1:
            resolutions[site_id] = SitelinkResolution(
                qid=qid,
                title=None,
                refused=f"{qid} is carried by {count} curated sites: a shared item describes a "
                "parent or a generic entity, not this site",
            )
            continue
        wanted.setdefault(qid, []).append(site_id)
    ordered = sorted(wanted)
    for start in range(0, len(ordered), 50):
        window = ordered[start : start + 50]
        url = wikidata_sitelinks_url(window)
        page = fetcher.get(url)
        if not page.ok or page.truncated:
            raise EvidenceUnrenderable(
                f"GET {url}: HTTP {page.status}, truncated={page.truncated}; no sitelink resolved"
            )
        links = enwiki_sitelinks_from_answer(page.body)
        for qid in window:
            if qid not in links:
                raise EvidenceUnrenderable(f"{qid}: asked for, and absent from the answer")
            link = links[qid]
            refused: str | None = None
            if link is None:
                refused = f"{qid} has no English Wikipedia sitelink"
            else:
                redirect = [
                    f"{badge} {REDIRECT_BADGES[badge]}"
                    for badge in link.badges
                    if badge in REDIRECT_BADGES
                ]
                if redirect:
                    refused = (
                        f"{qid}'s English sitelink {link.title!r} is a redirect "
                        f"({', '.join(redirect)}): it leads to another article or a section of "
                        "one, not the item's own"
                    )
            for site_id in wanted[qid]:
                resolutions[site_id] = SitelinkResolution(
                    qid=qid, title=None if link is None else link.title, refused=refused
                )
    return resolutions


def overpass_named_feature_url(name: str, *, lat: float, lon: float) -> str:
    """The Overpass target: named nodes/ways within `NAMED_FEATURE_RADIUS_M` of the stored point.

    Name-filtered and `around`-based, with `out center tags;` - never `out geom`, never a bbox
    dump. A stored name that cannot be written into an Overpass string literal (a `"` or a
    backslash) raises rather than being silently mangled: a quietly wrong query returns
    "nothing found", which reads as evidence that the name is absent.
    """
    if '"' in name or "\\" in name:
        raise InputError(
            f"name {name!r} cannot be written into an Overpass string literal; "
            "refusing to fetch a mangled query"
        )
    pattern = _overpass_regex(name)
    clauses = "".join(
        f'{element}["name"~"{pattern}",i](around:{NAMED_FEATURE_RADIUS_M},{lat},{lon});'
        for element in ("node", "way")
    )
    query = f"[out:json];({clauses});out center tags;"
    return OVERPASS_ENDPOINT + "?" + urlencode({"data": query}, quote_via=quote)


def _overpass_regex(name: str) -> str:
    """Escape a stored name for Overpass's POSIX-ish regex (`.`, `-`, `(` are all live there)."""
    escaped = name.replace("\\", "")
    for char in ".[]{}()^$*+?|":
        escaped = escaped.replace(char, "\\" + char)
    return escaped


@dataclass(frozen=True)
class Target:
    """One URL to try, and the finding that asked for it.

    `url` is the page's address as the prompt shows it and as a finder's citation must name it, byte
    for byte (`discover_stage.claim_problems` looks pages up by it). For every feature but one it is
    also the address requested. The exception is the narrowed route's WDQS query, whose GET address
    is some 2 KB of percent-encoded SPARQL (1,951 characters for Q10288): a finder cannot be expected
    to copy that exactly, so the target shows and is cited by its item's page
    (`wikidata_truthy_citation_url`) and carries the query in `query_url`.
    """

    site_id: str
    feature: str
    url: str
    reason: str  #: "<test_id> <field>" of the finding that bought this target
    #: The item a rendered Wikidata feature is about - its rendering names it. `None` elsewhere.
    qid: str | None = None
    #: The address actually requested, where it is not `url`. `None` for every verbatim feature.
    query_url: str | None = None

    @property
    def request_url(self) -> str:
        """What is sent, recorded in the ledger and the fetch report: `query_url` or `url`."""
        return self.url if self.query_url is None else self.query_url

    @property
    def label(self) -> str:
        """The pilot's `<site>/<feature>` label, with the stable `site_id` as the site part."""
        return f"{self.site_id}/{self.feature}"


def _finding(row: Mapping[str, Any], key: str, what: str) -> Any:
    if key not in row or row[key] in (None, ""):
        raise InputError(f"{what}: finding carries no {key!r}: {dict(row)!r}")
    return row[key]


def _stored_coordinates(site: Mapping[str, Any], site_id: str) -> tuple[float, float]:
    """The site's own stored point, from the finding that flagged it. Never guessed.

    The Overpass target is centred on the coordinate the worklist already carries; a site whose
    findings carry none gets no Overpass target, because a centre I invented would be evidence
    of nothing.
    """
    for finding in site["findings"]:
        if finding.get("field") != "lat/lon":
            continue
        value = finding.get("current_value")
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        ):
            return float(value[0]), float(value[1])
        raise InputError(f"{site_id}: lat/lon finding carries {value!r}, not a coordinate pair")
    raise InputError(f"{site_id}: no lat/lon finding to centre the named-feature query on")


def targets_for_site(site: Mapping[str, Any]) -> list[Target]:
    """The targets this site's findings buy, in finding order, deduplicated by feature.

    Driven by the findings: the census check family decides *whether* to fetch at all (T02 buys
    none), the field decides *what*, and the record supplies the name and the stored point.

    A record that carries no `wikidata_qid` buys no `wikidata_entity` target: there is no id to ask
    about, and the name search (`wikidata_search`) answers a **different** question - it returns
    candidate items for a name, which is what the `name` field needs and not what a stored
    description, year, type, country or card text is judged against. The finding-driven worklist
    records carry no qid at all (`WORKLIST.jsonl`, 1,840 records, re-verified), so their targets
    are unchanged by this rule.
    """
    site_id = str(_finding(site, "site_id", "site record"))
    name = str(_finding(site, "name", f"site {site_id}"))
    findings = site.get("findings")
    if not isinstance(findings, list) or not findings:
        raise InputError(f"{site_id}: a site with no findings buys no evidence... and none came")

    usable = [
        f for f in findings if str(f.get("test_id", "")).partition("/")[0] not in NO_FETCH_PREFIXES
    ]
    qid = site.get("wikidata_qid")
    routes = _routes(site, site_id, name)
    targets: dict[str, Target] = {}
    for finding in usable:
        test_id = str(_finding(finding, "test_id", f"site {site_id}"))
        field_name = str(_finding(finding, "field", f"site {site_id}"))
        if field_name not in FEATURES_FOR_FIELD:
            raise InputError(
                f"{site_id}: {test_id} is filed on field {field_name!r}, which no target rule "
                f"covers (known fields: {sorted(FEATURES_FOR_FIELD)})"
            )
        reason = f"{test_id} {field_name}"
        for slot in FEATURES_FOR_FIELD[field_name]:
            if slot == FEATURE_WIKIDATA_ENTITY and not qid:
                continue
            for feature in routes.get(slot, (slot,)):
                if feature in targets:
                    continue
                targets[feature] = Target(
                    site_id=site_id,
                    feature=feature,
                    url=_url_for(feature, site, site_id, name),
                    reason=reason,
                    qid=str(qid) if feature in _QID_FEATURES or _is_date(feature) else None,
                    query_url=(
                        wikidata_truthy_url(str(qid))
                        if feature == FEATURE_WIKIDATA_TRUTHY
                        else None
                    ),
                )
    return list(targets.values())


#: The rendered features whose rendering names the item.
_QID_FEATURES = frozenset({FEATURE_WIKIDATA_TRUTHY})


def _is_date(feature: str) -> bool:
    return feature.startswith(DATE_FEATURE_PREFIX)


def _routes(site: Mapping[str, Any], site_id: str, name: str) -> dict[str, tuple[str, ...]]:
    """Which concrete features a record's slots expand to. Empty for every record that asks for
    nothing new - so a plan built before 2026-09-22 buys exactly the targets it always bought.

    `wikidata_route: "narrow"` puts the narrowed features in the `wikidata_entity` slot;
    `enwiki_sitelink: {qid, title}` adds the item's English article after the name route. Any other
    value of either key is refused rather than ignored: a misspelt route would silently buy the full
    entity again, the evidence the route exists to avoid.
    """
    routes: dict[str, tuple[str, ...]] = {}
    route = site.get(WIKIDATA_ROUTE_KEY)
    if route is not None:
        if route != WIKIDATA_ROUTE_NARROW:
            raise InputError(
                f"{site_id}: {WIKIDATA_ROUTE_KEY}={route!r}; the one route this stage knows is "
                f"{WIKIDATA_ROUTE_NARROW!r}"
            )
        if not site.get("wikidata_qid"):
            raise InputError(
                f"{site_id}: {WIKIDATA_ROUTE_KEY}={route!r} on a record without a wikidata_qid"
            )
        routes[FEATURE_WIKIDATA_ENTITY] = (
            FEATURE_WIKIDATA_TRUTHY,
            *(f"{DATE_FEATURE_PREFIX}{pid}" for pid in DATE_PROPERTIES),
        )
    link = site.get(ENWIKI_SITELINK_KEY)
    if link is not None:
        if not isinstance(link, Mapping) or set(link) != {"qid", "title"}:
            raise InputError(f"{site_id}: {ENWIKI_SITELINK_KEY} is {link!r}, not {{qid, title}}")
        if link["qid"] != site.get("wikidata_qid"):
            raise InputError(
                f"{site_id}: the sitelink was resolved for {link['qid']!r}, the record carries "
                f"{site.get('wikidata_qid')!r} - a stale resolution routes to another item's article"
            )
        title = link["title"]
        if not isinstance(title, str) or not title.strip():
            raise InputError(f"{site_id}: {ENWIKI_SITELINK_KEY} carries no title")
        if title == name:
            raise InputError(
                f"{site_id}: the sitelink title is the stored name {name!r}; the name route already "
                "fetches that article, and a second copy would count twice against the bound"
            )
        routes[FEATURE_ENWIKI] = (FEATURE_ENWIKI, FEATURE_ENWIKI_SITELINK)
    return routes


def _url_for(feature: str, site: Mapping[str, Any], site_id: str, name: str) -> str:
    if feature == FEATURE_ENWIKI:
        return wikipedia_extract_url(name)
    if feature == FEATURE_ENWIKI_SITELINK:
        return wikipedia_extract_url(str(site[ENWIKI_SITELINK_KEY]["title"]))
    if feature == FEATURE_WIKIDATA_TRUTHY:
        return wikidata_truthy_citation_url(str(_finding(site, "wikidata_qid", f"site {site_id}")))
    if _is_date(feature):
        return wikidata_claims_url(
            str(_finding(site, "wikidata_qid", f"site {site_id}")),
            feature[len(DATE_FEATURE_PREFIX) :],
        )
    if feature == FEATURE_WIKIDATA_SEARCH:
        return wikidata_search_url(name)
    if feature == FEATURE_WIKIDATA_ENTITY:
        return wikidata_entity_url(str(_finding(site, "wikidata_qid", f"site {site_id}")))
    if feature == FEATURE_OVERPASS_NAMED:
        lat, lon = _stored_coordinates(site, site_id)
        return overpass_named_feature_url(name, lat=lat, lon=lon)
    raise InputError(f"{site_id}: no URL builder for feature {feature!r}")


@dataclass(frozen=True)
class EvidenceFile:
    """One written evidence file. `wrote=False` means an identical file was already there."""

    site_id: str
    feature: str
    path: Path
    wrote: bool


class EvidenceStore:
    """`evidence/<site_id>%2F<feature>.txt`, the pilot's layout, one file per fetch.

    Existence is the record: a target whose file is already on disk is not fetched again, so a
    re-run costs nothing and cannot silently pile up a second copy of the same page. Deleting a
    file is how a human asks for that one page again. The file is written to a `.tmp` and
    replaced, so a kill leaves no half page behind (the census cache's convention).
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @staticmethod
    def slug(site_id: str, feature: str) -> str:
        """The pilot's URL-encoded label: `quote("Satsurblia/wikidata", safe="")`."""
        return quote(f"{site_id}/{feature}", safe="")

    def path_for(self, site_id: str, feature: str) -> Path:
        return self.root / f"{self.slug(site_id, feature)}.txt"

    def exists(self, site_id: str, feature: str) -> bool:
        return self.path_for(site_id, feature).exists()

    def raw_path_for(self, site_id: str, feature: str) -> Path:
        """Where the bytes read for a rendered feature are kept: `evidence_raw/` beside the store."""
        return self.root.parent / RAW_EVIDENCE_DIR / f"{self.slug(site_id, feature)}.txt"

    def write_raw(self, *, site_id: str, feature: str, body: bytes) -> Path:
        """Keep the bytes a rendering was made from. Overwritten on a re-fetch, because the rendered
        file - not this one - is the record `exists` reads, and a re-fetch only happens when that
        file was deleted to ask again."""
        path = self.raw_path_for(site_id, feature)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        return path

    def write(self, *, site_id: str, feature: str, body: bytes) -> EvidenceFile:
        path = self.path_for(site_id, feature)
        wrote = write_once(
            path,
            body,
            source="the answer just received (delete the file to refetch this one target)",
        )
        return EvidenceFile(site_id=site_id, feature=feature, path=path, wrote=wrote)


@dataclass(frozen=True)
class FetchAttempt:
    """One HTTP attempt on one target: what happened, and what it bought.

    Exactly the shape of the ledger line written for it, so the report and the ledger cannot
    disagree about a request (the report is for a human, the ledger carries the clock).
    """

    attempt: int  #: 1-based
    outcome: L.FetchOutcome
    http_status: int | None  #: None for a transport failure: no response arrived
    bytes: int  #: 0 when nothing arrived
    error: str | None  #: the reason, for a transport failure only

    @property
    def ok(self) -> bool:
        return self.outcome is L.FetchOutcome.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "bytes": self.bytes,
            "error": self.error,
        }


@dataclass
class TargetOutcome:
    """Every attempt made on one target, and what the target ended with."""

    feature: str
    url: str
    bought_by: str  #: the finding's "<test_id> <field>"
    attempts: list[FetchAttempt] = field(default_factory=list)
    #: Set only by `collect_batch` when the target's host did not answer the run's probe: the
    #: probe's reason, and the fact that **no attempt was made** - `attempts` stays empty and no
    #: request went to `url`. Kept apart from a failed attempt on purpose: "the host never
    #: answered, so this was not tried" and "this was tried and failed" are different sentences,
    #: and the judge reads them back as the reason a site has no evidence.
    not_attempted: str | None = None
    #: Set only by `one_attempt` when the target was given up on for a reason of *ours* rather
    #: than the host's - today exactly one case, a `Retry-After` longer than this run will block
    #: on a single host. It lives here and not on the attempt's `error`, because the ledger's own
    #: invariant is that a request that got a response is recorded by its status and carries no
    #: error string; the sentence is what the judge reads, not what the ledger stores.
    given_up_reason: str | None = None
    #: Set only by `one_attempt`: the page this target bought is on disk, and whether it was cut
    #: at `MAX_PAGE_BYTES`.
    stored: bool = False
    truncated: bool = False

    @property
    def requests(self) -> int:
        """HTTP requests made for this target. Zero for one that was never attempted."""
        return len(self.attempts)

    @property
    def final(self) -> FetchAttempt:
        if not self.attempts:  # pragma: no cover - `failure` handles a not-attempted target first
            raise RuntimeError(f"{self.feature}: no attempt was recorded")
        return self.attempts[-1]

    @property
    def succeeded(self) -> bool:
        return bool(self.attempts) and self.final.ok

    @property
    def failure(self) -> str | None:
        """Why this target has no evidence, or `None` when it does have some.

        This is the sentence the judge stage reads back out of the report before it decides
        whether a missing evidence file is an explained failure or a hole in the record. It says
        which of the two facts it is: a target nobody asked because its host did not answer, or a
        target that was asked and failed.
        """
        if self.succeeded:
            return None
        if self.not_attempted is not None:
            return (
                f"not attempted: this target's host did not answer the run's host probe "
                f"({self.not_attempted}); 0 request(s) recorded, no evidence on disk"
            )
        final = self.final
        if final.outcome is L.FetchOutcome.TRANSPORT_FAILURE:
            what = f"no response: {final.error}"
        elif self.given_up_reason:
            # An HTTP failure can carry a reason of our own. The one case today is a `Retry-After`
            # longer than this run will wait for - a *decision* of ours, not the host's fault, and
            # the reason it is not simply re-asked. Without it the judge reads a bare `HTTP 429`
            # and cannot tell a rate limit we honoured from one we walked into.
            what = f"HTTP {final.http_status}: {self.given_up_reason}"
        else:
            what = f"HTTP {final.http_status}"
        return (
            f"{what} ({self.requests} request(s) recorded, the last one given up; "
            "no evidence on disk)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": [a.to_dict() for a in self.attempts],
            "bought_by": self.bought_by,
            "feature": self.feature,
            "failure": self.failure,
            "not_attempted": self.not_attempted,
            "requests": self.requests,
            "truncated": self.truncated,
            "url": self.url,
        }


@dataclass
class SiteEvidence:
    """What the fetch stage did for one site. Counts, not prose."""

    site_id: str
    targets: list[Target] = field(default_factory=list)
    fetched: int = 0  #: targets that produced an evidence file
    skipped_existing: int = 0
    truncated: int = 0
    bytes: int = 0
    non_2xx: list[tuple[str, int]] = field(default_factory=list)
    #: One record per attempted target, in attempt order. A failed target is here too - that is
    #: the whole point of piece 4: a request that bought nothing must be visible in the report.
    outcomes: list[TargetOutcome] = field(default_factory=list)

    @property
    def requests(self) -> int:
        """HTTP attempts made for this site (every one of them has its own ledger line)."""
        return sum(o.requests for o in self.outcomes)

    @property
    def failed(self) -> list[TargetOutcome]:
        return [o for o in self.outcomes if not o.succeeded]

    @property
    def not_attempted(self) -> list[TargetOutcome]:
        """Targets recorded as `host_unreachable`: their host never answered, so nothing was asked."""
        return [o for o in self.outcomes if o.not_attempted is not None]

    def failures(self) -> dict[str, str]:
        """`feature -> why it has no evidence`, for the targets that have none."""
        return {o.feature: str(o.failure) for o in self.failed}

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            # `url` is what the prompt shows and a citation names; a target that requests another
            # address (the narrowed route's WDQS query) says so, and its outcome records that one.
            "targets": [
                {"feature": t.feature, "reason": t.reason, "url": t.url}
                | ({} if t.query_url is None else {"request_url": t.query_url})
                for t in self.targets
            ],
            "outcomes": [o.to_dict() for o in self.outcomes],
            "fetched": self.fetched,
            "not_attempted": len(self.not_attempted),
            "skipped_existing": self.skipped_existing,
            "truncated": self.truncated,
            "bytes": self.bytes,
            "non_2xx": [{"url": url, "http_status": status} for url, status in self.non_2xx],
        }


@dataclass(frozen=True)
class HostProbe:
    """One host's reachability decision for this run, and the single request that bought it.

    `reachable` is decided by *any* HTTP answer: a 400, a 404, a 429 and a 500 all mean the host
    answered, so only a `TransportFailure` marks a host down (the brief's measurement: the same
    `curl` gets a reset from `overpass-api.de` and a 400 from `overpass.osm.ch`, and only the reset
    means "not there"). `reason` carries what was observed, so the report and the prompt can say
    which of the two facts is on the table.
    """

    host: str
    url: str  #: the probe URL (the host's root), not any target's
    reachable: bool
    outcome: L.FetchOutcome
    http_status: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "url": self.url,
            "reachable": self.reachable,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "reason": self.reason,
        }


@dataclass
class BatchFetchReport:
    """The batch's fetch outcome. Deterministic: no timestamp (the ledger carries the clock)."""

    batch_id: str
    stage: Stage
    sites: list[SiteEvidence] = field(default_factory=list)
    #: One record per host this run actually asked, in the order the batch reached them. Empty when
    #: every target was already on disk: then no host was asked at all.
    probes: list[HostProbe] = field(default_factory=list)

    @property
    def fetches(self) -> int:
        return sum(s.fetched for s in self.sites)

    @property
    def skipped_existing(self) -> int:
        return sum(s.skipped_existing for s in self.sites)

    @property
    def truncated(self) -> int:
        return sum(s.truncated for s in self.sites)

    @property
    def bytes(self) -> int:
        return sum(s.bytes for s in self.sites)

    @property
    def non_2xx(self) -> list[tuple[str, int]]:
        return [row for s in self.sites for row in s.non_2xx]

    @property
    def requests(self) -> int:
        """Every HTTP request the batch made: one probe per host asked, plus every target attempt.

        A target recorded `host_unreachable` contributes 0 - no request went to its URL - while the
        probe that decided that contributes 1. Both have a ledger line, so this figure and the
        ledger's `fetches` for the batch stay the same number.
        """
        return sum(s.requests for s in self.sites) + len(self.probes)

    @property
    def probe_requests(self) -> int:
        return len(self.probes)

    @property
    def not_attempted(self) -> list[TargetOutcome]:
        """Targets no request was made for: their host did not answer the run's probe."""
        return [o for s in self.sites for o in s.not_attempted]

    @property
    def failed(self) -> list[TargetOutcome]:
        return [o for s in self.sites for o in s.failed]

    def failures_by_site(self) -> dict[str, dict[str, str]]:
        """The record the judge stage reads: `site_id -> {feature: why it has no evidence}`.

        A target that was never attempted is in here too, with the sentence that says so: the
        judge must be told which of the two facts it is holding.
        """
        return {s.site_id: s.failures() for s in self.sites if s.failed}

    def to_json(self) -> str:
        payload = {
            "batch_id": self.batch_id,
            "stage": self.stage.value,
            "probes": [p.to_dict() for p in self.probes],
            "sites": [s.to_dict() for s in self.sites],
            "totals": {
                "fetches": self.fetches,
                "requests": self.requests,
                "probes": self.probe_requests,
                "failed": len(self.failed),
                "not_attempted": len(self.not_attempted),
                "skipped_existing": self.skipped_existing,
                "truncated": self.truncated,
                "bytes": self.bytes,
                "non_2xx": len(self.non_2xx),
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def probe_host(
    *,
    host: str,
    url: str,
    fetcher: Fetcher,
    ledger: L.Ledger,
    batch_id: str,
    stage: Stage,
) -> HostProbe:
    """Ask a host once, before its first pending target, and record that one request.

    The probe is **not** retried, and that is the whole point: `MAX_ATTEMPTS` copies of the same
    wait is what the first live batch measured as 38 minutes (117 lines on one host, every one of
    them a nested wait over a host that answered nothing). One bounded request per host per run
    turns that into one; when the host answers, the run proceeds exactly as it did before.

    Its line is an ordinary fetch line, written *before* the decision is applied (piece 2's rule:
    a request that left the machine is visible even if the next byte of code does not run), and it
    carries `given_up=False` even when the host is down: `given_up` records that a *target's* last
    attempt ended without evidence, and no target was attempted here.
    """
    try:
        page = fetcher.get(url)
    except TransportFailure as exc:
        reason = str(exc)
        probe = HostProbe(
            host=host,
            url=url,
            reachable=False,
            outcome=L.FetchOutcome.TRANSPORT_FAILURE,
            http_status=None,
            reason=reason,
        )
        status: int | None = None
        size = 0
        error: str | None = reason
    else:
        # **Any** HTTP answer means reachable - 400, 404, 429, 500 included. A host that says "no"
        # is a host that is there; only silence is absence (the brief's curl: a reset from
        # `overpass-api.de`, a 400 from `overpass.osm.ch`).
        status = page.status
        size = len(page.body)
        error = None
        probe = HostProbe(
            host=host,
            url=url,
            reachable=True,
            outcome=L.FetchOutcome.OK if page.ok else L.FetchOutcome.HTTP_ERROR,
            http_status=status,
            reason=f"HTTP {status}",
        )
    ledger.append(
        L.Entry(
            kind=L.LedgerKind.FETCH,
            stage=stage,
            batch_id=batch_id,
            label=f"{HOST_PROBE_PREFIX}{host}",
            url=url,
            http_status=status,
            bytes=size,
            outcome=probe.outcome,
            attempt=1,
            error=error,
            given_up=False,
        )
    )
    return probe


def one_attempt(
    *,
    target: Target,
    fetcher: Fetcher,
    store: EvidenceStore,
    ledger: L.Ledger,
    batch_id: str,
    stage: Stage,
    sleep: Callable[[float], None],
) -> TargetOutcome:
    """Ask one target, up to `MAX_ATTEMPTS` times, and record every attempt exactly once.

    The order inside an attempt is the ledger's rule from piece 2 and it does not change: the
    **line goes down first**, because the request happened and a crash after it must leave a
    visible measurement rather than an invisible one; the page is stored second.

    What is retried is decided by `is_retryable_status` plus a transport failure, and what is
    *not*: a fallback host. `HttpFetcher` keeps asking the same URL, because which endpoint to ask
    is a decision for the operator (and `overpass.kumi.systems` - the third-party mirror the pilot
    fell back to by hand - is a different service with different terms).
    """
    outcome = TargetOutcome(feature=target.feature, url=target.request_url, bought_by=target.reason)
    for number in range(1, MAX_ATTEMPTS + 1):
        attempt, page = _ask(target=target, fetcher=fetcher, number=number)
        retryable = attempt.outcome is L.FetchOutcome.TRANSPORT_FAILURE or is_retryable_status(
            attempt.http_status
        )
        last = not retryable or number == MAX_ATTEMPTS
        asked = page.retry_after if page is not None else None
        if not last and asked is not None and asked > RETRY_AFTER_CAP_SECONDS:
            # The host asked to be left alone for longer than this run will block on one host.
            # Waiting less and asking again would be the impoliteness the pacer exists to prevent,
            # so the target is given up on instead - and the reason names the delay, because a
            # `given_up` line without one reads like an ordinary failure.
            last = True
            refusal: str | None = (
                f"HTTP {attempt.http_status} asked for {asked:.0f}s; given up rather than block "
                f"longer than {RETRY_AFTER_CAP_SECONDS:.0f}s and then re-ask sooner than asked"
            )
        else:
            refusal = None
        outcome.given_up_reason = refusal
        ledger.append(
            L.Entry(
                kind=L.LedgerKind.FETCH,
                stage=stage,
                batch_id=batch_id,
                label=target.label,
                url=target.request_url,
                http_status=attempt.http_status,
                bytes=attempt.bytes,
                outcome=attempt.outcome,
                attempt=number,
                # No `error` here: a request that got a response is recorded by its status (the
                # ledger refuses an error string on an answered attempt). The refusal - ours, not
                # the host's - travels on `outcome.given_up_reason` for the judge to read.
                error=attempt.error,
                given_up=last and not attempt.ok,
            )
        )
        if page is not None and page.ok:
            # A valid *empty* answer (Overpass `"elements": []`) is an OK attempt like any other:
            # the file is the record that the question was asked *and answered with nothing*.
            store.write(
                site_id=target.site_id,
                feature=target.feature,
                body=stored_body(target, store, page),
            )
            outcome.stored = True
            outcome.truncated = page.truncated
        outcome.attempts.append(attempt)
        if last:
            return outcome
        wait = RETRY_BACKOFF_SECONDS[number - 1]
        if asked is not None and asked > wait:
            wait = asked
        sleep(wait)
    raise AssertionError("unreachable: the loop returns on its last attempt")  # pragma: no cover


def record_not_attempted(
    *, target: Target, probe: HostProbe, ledger: L.Ledger, batch_id: str, stage: Stage
) -> TargetOutcome:
    """Record a target whose host did not answer the run's probe, and make no request for it.

    One line, and no request to this target's URL: nothing was asked, so there is no attempt to
    number (`attempt=0`) and the reason is the probe's own. Extracted from `collect_batch` on
    2026-09-23 so Phase 4's stages record such a target with this one spelling of the line.
    """
    ledger.append(
        L.Entry(
            kind=L.LedgerKind.FETCH,
            stage=stage,
            batch_id=batch_id,
            label=target.label,
            url=target.request_url,
            http_status=None,
            bytes=0,
            outcome=L.FetchOutcome.HOST_UNREACHABLE,
            attempt=0,
            error=probe.reason,
            given_up=False,
        )
    )
    return TargetOutcome(
        feature=target.feature,
        url=target.request_url,
        bought_by=target.reason,
        not_attempted=probe.reason,
    )


def tally(result: SiteEvidence, target: Target, outcome: TargetOutcome) -> None:
    """Add one attempted target's outcome to its site's counts (extracted from `collect_batch`)."""
    result.outcomes.append(outcome)
    if outcome.stored:
        result.fetched += 1
        result.bytes += outcome.final.bytes
        result.truncated += int(outcome.truncated)
    for attempt in outcome.attempts:
        if not attempt.ok and attempt.http_status is not None:
            # Data, not an exception: the pilot recorded 403/404/504/429 and continued.
            result.non_2xx.append((target.request_url, attempt.http_status))


def _complete_utf8(body: bytes) -> bytes:
    """`body` without the incomplete UTF-8 sequence a cut can leave at its very end.

    Only the last three bytes are looked at: a cut splits at most one character, and anything wrong
    earlier in the page is the page's own and stays as it was read.
    """
    for drop in range(0, min(3, len(body)) + 1):
        try:
            (body[: len(body) - drop] if drop else body).decode("utf-8")
        except UnicodeDecodeError:
            continue
        return body[: len(body) - drop] if drop else body
    return body


def stored_body(target: Target, store: EvidenceStore, page: FetchedPage) -> bytes:
    """What goes into the evidence file for one 2xx answer.

    A verbatim feature stores the bytes read, plus `TRUNCATION_MARKER` when the page stopped at the
    cap. A rendered feature (the narrowed Wikidata route) keeps the bytes read in `evidence_raw/` and
    stores its rendering; such an answer is a few kilobytes, and one that nevertheless hit the cap is
    refused rather than rendered from half a JSON document.
    """
    if target.feature in _QID_FEATURES or _is_date(target.feature):
        if page.truncated:
            raise EvidenceUnrenderable(
                f"{target.label}: the answer hit the {MAX_PAGE_BYTES}-byte cap; a rendering of a "
                "cut JSON document would be a rendering of evidence nobody read"
            )
        store.write_raw(site_id=target.site_id, feature=target.feature, body=page.body)
        rendered = rendered_evidence(target, page.body)
        return str(rendered).encode("utf-8")
    if page.truncated:
        return _complete_utf8(page.body) + TRUNCATION_MARKER.encode("utf-8")
    return page.body


def _ask(
    *, target: Target, fetcher: Fetcher, number: int
) -> tuple[FetchAttempt, FetchedPage | None]:
    """One request. A transport failure is turned into a recorded attempt, never into a stop.

    Nothing else is caught: an exception the fetcher was not asked to raise (a `ValueError`, a
    `RawGeometryRefused`) is a bug in the caller, not weather, and propagates.
    """
    try:
        page = fetcher.get(target.request_url)
    except TransportFailure as exc:
        return (
            FetchAttempt(
                attempt=number,
                outcome=L.FetchOutcome.TRANSPORT_FAILURE,
                http_status=None,
                bytes=0,
                error=str(exc),
            ),
            None,
        )
    return (
        FetchAttempt(
            attempt=number,
            outcome=L.FetchOutcome.OK if page.ok else L.FetchOutcome.HTTP_ERROR,
            http_status=page.status,
            bytes=len(page.body),
            error=None,
        ),
        page,
    )


def collect_batch(
    *,
    batch: Mapping[str, Any],
    fetcher: Fetcher,
    store: EvidenceStore,
    ledger: L.Ledger,
    stage: Stage = Stage.FINDER,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchFetchReport:
    """Fetch every target the batch's sites buy, writing one ledger line per *attempt*.

    No failure of one target stops the batch. A transport failure is recorded as that target's
    outcome with its reason and the next target is asked; a 429/5xx is retried up to
    `MAX_ATTEMPTS` times; anything else is recorded once. Nothing is caught into an empty result,
    and nothing is retried without a ledger line - an unrecorded retry is the invisible charge
    this ledger exists to prevent.

    Each host is probed **once per run, immediately before its first pending target**
    (`probe_host`), and only then: a host whose targets are all already on disk is not asked at
    all, so a re-run costs exactly what it cost before. A host that does not answer the probe
    leaves every pending target on it recorded as `host_unreachable` - one line each, `attempt=0`,
    the probe's reason, and **no request to their URLs** - while the targets of the other hosts are
    fetched normally. No other host is tried in its place.

    `sleep` is the retry pause, injected so a test never waits on a real clock.
    """
    batch_id = str(_finding(batch, "batch_id", "batch"))
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    report = BatchFetchReport(batch_id=batch_id, stage=stage)
    probes: dict[str, HostProbe] = {}
    for site in sites:
        result = SiteEvidence(site_id=str(_finding(site, "site_id", "site record")))
        result.targets = targets_for_site(site)
        report.sites.append(result)
        for target in result.targets:
            if store.exists(target.site_id, target.feature):
                result.skipped_existing += 1
                continue
            host = host_of(target.request_url)
            probe = probes.get(host)
            if probe is None:
                probe = probe_host(
                    host=host,
                    url=host_probe_url(target.request_url),
                    fetcher=fetcher,
                    ledger=ledger,
                    batch_id=batch_id,
                    stage=stage,
                )
                probes[host] = probe
            if not probe.reachable:
                result.outcomes.append(
                    record_not_attempted(
                        target=target, probe=probe, ledger=ledger, batch_id=batch_id, stage=stage
                    )
                )
                continue
            outcome = one_attempt(
                target=target,
                fetcher=fetcher,
                store=store,
                ledger=ledger,
                batch_id=batch_id,
                stage=stage,
                sleep=sleep,
            )
            tally(result, target, outcome)
    report.probes = list(probes.values())
    return report


def write_report(path: Path, report: BatchFetchReport) -> None:
    """Write the batch's fetch report: sorted keys, LF, no timestamp (a re-run is identical)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
