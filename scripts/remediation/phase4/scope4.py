"""The owner's defect scope: the only sites Phases 4 and 5 write (`SCOPE4.v2.json`, pinned).

Owner decision 2026-09-23 (Martin, "Nur Defekt-Sites (Recommended)"): after a passing Phase-4 pilot,
Phases 4/5 write only the sites with proven text defects - the Phase-3 cleared defects plus the
ungrounded card texts, in the design's order; every other site's description and card stay exactly
as they are. This module is that sentence as data: lists, each derived from a pinned input, joined
in one file that is pinned by its sha256 (`SCOPE_SHA256`). A new scope is a new version and a new
pin in this file, never an edit of a pinned file.

Versions
--------
* **1** (`SCOPE4.json`, `SCOPE_V1_SHA256`, 2026-09-23/24): the three lists below, 1,623 sites. The mass
  run was planned (`plan4.py build --defect-scope`) and written under it; it stays byte for byte,
  rebuilt by `plan4.py scope --version 1` and read only to rebuild that plan.
* **2** (`SCOPE4.v2.json`, `SCOPE_SHA256`, owner order 2026-09-25 "keine Fragen mehr, autonom
  Empfehlungen umsetzen", HUMAN_ONLY D9 (c)): version 1 and the list `d1-marker-without-entry` - a
  site whose description sets a `[N]` marker that `raw_data.description_citations` has no entry for
  is a proven text defect: the reader sees a bare number, and the source is not in the data. Every
  version-1 site keeps its lists, the new list is appended: version 2 refuses nothing version 1
  allowed. Its sites get a sourced description through the same Phase-4 pipeline
  (`plan4.py build --scope-list`), or stay held with a closed-list reason.

The lists
---------
* `phase3-cleared-description`, `phase3-cleared-card` - the description and card defects Phase 3's
  reviewer cleared: the rows of `logs/_write_dry/ALL_REFUSED.jsonl` under the rule
  `report-only-field` (`plan4.cleared_defects`), the 322 and 709 of the design.
* `d1-marker-without-entry` (version 2) - the orphan-citations lane's listing
  (`output/remediation/mechanical_citations/SKIPPED.jsonl`, reason `marker-without-entry`), whose
  export read acceptance D1 over every curated row on 2026-09-25; the build checks each listed site
  against its own S0 row with D1's reading (census T08's `marker_sequence` and `entries`), so no
  site is taken on the listing's word (`markers_without_entry`).
* `ungrounded-card` - plan section 5.1 (`docs/procedures/SITES_DB_REMEDIATION_2026-09.md`): a card
  that writes a number which never appeared in the generator's input, `LEFT(description, 500)`
  (`scripts/export_card_sites.py:36`) of the pre-March snapshot d4526691. The measurement of
  2026-09-19 counted 904 and kept no list, so the list is recomputed from the S0 export
  (`S0_ROWS.jsonl`: `card` is the stored card, `snapshot_description` the snapshot's text). A number
  is a numeral as written - ASCII digits, with comma thousands separators and a decimal part - read
  as its value (`10,000` is `10000`, `7.10` is `7.1`); it appeared when the same value is a numeral
  of the input's first 500 characters, not a digit run inside a longer numeral (`50` did not appear
  in `500`). A site the snapshot does not have has no known input: its card is not claimed, and
  the file lists it under `unclaimed`.

What admits no site
-------------------
`t03` and `t03-severe` (`model4.SiteFlag`) name a contradiction between the text's years and the
period bucket, not which of the two is wrong: T03's findings are proposals for human review (the
census counts 0 of them applicable), plan section 4.3 names two severe T03 patterns as false alarms
(7 and 8), and V14 holds a severe finding "for reading" for that reason. The flags keep their jobs
inside the scope - V9's floor waiver and the plan's order. The D1 list adds no flag: a marker
without an entry says nothing about the truth of the text around it, so V9's 50 % floor stays for
its sites unless another flag waives it.

Pure: no database, no network. `plan4.py scope` writes the file, `write4` refuses every site outside
it (`RULE_OUT_OF_SCOPE`), `plan4.py build --defect-scope` builds the mass run's plan from version 1
and `build --scope-list` the plan of one later list, and `mass4` asks no model question for a site
outside it.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from census.tests import t08_citation_markers as T08

from phase4 import model4 as M

REPO = Path(__file__).resolve().parents[3]
RUNNER = REPO / "output" / "remediation" / "phase4_runner"

#: The current version of the scope file's form and content; a new scope is a new version and a new
#: pin, and the file of every earlier version stays as it was pinned.
SCOPE_VERSION = 2
SCOPE_FILE = RUNNER / "SCOPE4.v2.json"
#: The sha256 of `SCOPE_FILE`'s bytes: the gate, the plan and the mass run read this file or none.
SCOPE_SHA256 = "7256a1962ffe1b2449c7028e1174fe623d7de19fdddde2083f560790f7003173"
#: Version 1, the mass run's (2026-09-23/24), kept byte for byte at its own pin.
SCOPE_V1_FILE = RUNNER / "SCOPE4.json"
SCOPE_V1_SHA256 = "19a57e9fd17f53601fecdd5424d3ea3e085c2690e8250cb72b004f010f833d6a"

CLEARED_DESCRIPTION = "phase3-cleared-description"
CLEARED_CARD = "phase3-cleared-card"
UNGROUNDED_CARD = "ungrounded-card"
D1_MARKER_WITHOUT_ENTRY = "d1-marker-without-entry"
#: The lists, in the order a site names them: a later version's lists come after an earlier one's.
LISTS = (CLEARED_DESCRIPTION, CLEARED_CARD, UNGROUNDED_CARD, D1_MARKER_WITHOUT_ENTRY)
#: The lists each version carries; a version keeps every list of the one before it.
VERSION_LISTS: Mapping[int, tuple[str, ...]] = {1: LISTS[:3], 2: LISTS}
#: The orphan-citations lane's reason for a listed site (`mechanical/citations.MARKER_WITHOUT_ENTRY`,
#: census T08's name): the one reason of its listing that is the list `d1-marker-without-entry`.
D1_REASON = "marker-without-entry"
#: The field a Phase-3 cleared defect names -> its list.
CLEARED_LISTS: Mapping[str, str] = {
    "description": CLEARED_DESCRIPTION,
    "card_description": CLEARED_CARD,
}
#: Why a numeral-bearing card is not claimed ungrounded: the snapshot does not have its site.
NOT_IN_SNAPSHOT = "not-in-snapshot"
#: `scripts/export_card_sites.py:36`: the generator was given `LEFT(us.description, 500)`.
GENERATOR_INPUT_CHARS = 500

DECISION = (
    "Owner decision 2026-09-23 (Martin, 'Nur Defekt-Sites (Recommended)'): after a passing Phase-4 "
    "pilot, Phases 4/5 write only the sites with proven text defects - the Phase-3 cleared defects "
    "plus the ungrounded card texts, in the design's order; every other site's description and "
    "card stay exactly as they are."
)
#: What version 2 adds to the decision (HUMAN_ONLY D9, recommendation (c)).
ORDER_2026_09_25 = (
    "Owner order 2026-09-25 (Martin, 'keine Fragen mehr, autonom Empfehlungen umsetzen'), HUMAN_ONLY "
    "D9 (c): a [N] marker without an entry in raw_data.description_citations is a proven text "
    "defect, so its sites join the scope and get a sourced description through the same Phase-4 "
    "pipeline, or stay held with a closed-list reason."
)
DECISIONS: Mapping[int, str] = {1: DECISION, 2: f"{DECISION} {ORDER_2026_09_25}"}
METHODS: Mapping[str, str] = {
    CLEARED_DESCRIPTION: (
        "ALL_REFUSED.jsonl, rule report-only-field, field description: a description defect "
        "Phase 3's reviewer cleared"
    ),
    CLEARED_CARD: (
        "ALL_REFUSED.jsonl, rule report-only-field, field card_description: a card defect Phase "
        "3's reviewer cleared"
    ),
    UNGROUNDED_CARD: (
        "plan section 5.1: the stored card writes a number that is no numeral of the first 500 "
        "characters of the site's description in pre-March snapshot d4526691 (the generator's "
        "input, scripts/export_card_sites.py:36); a number is a numeral as written (ASCII digits, "
        "comma thousands separators, a decimal part) read as its value; recomputed from "
        "S0_ROWS.jsonl because the measurement of 2026-09-19 (904) kept no list; a site the "
        "snapshot does not have is not claimed"
    ),
}
VERSION_METHODS: Mapping[int, Mapping[str, str]] = {
    1: METHODS,
    2: {
        **METHODS,
        D1_MARKER_WITHOUT_ENTRY: (
            "output/remediation/mechanical_citations/SKIPPED.jsonl, reason marker-without-entry: "
            "the orphan-citations lane's listing of the curated sites whose description sets an [N] "
            "that raw_data.description_citations has no entry for - acceptance D1 "
            "(scripts/remediation/acceptance/checks.py) over every curated row of its export of "
            "2026-09-25 16:00:18 UTC (HUMAN_ONLY D9); each listed site's S0 row fails D1 the same "
            "way (census T08 marker_sequence and entries), checked when the scope is built"
        ),
    },
}

#: A numeral as written: digits with comma thousands separators and a decimal part, or plain digits.
_NUMERAL = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?")
_KEYS = frozenset(
    {"version", "decision", "inputs", "methods", "lists", "unclaimed", "sites", "sites_sha256"}
)
_SITE_KEYS = frozenset({"site_id", "lists"})


class ScopeError(ValueError):
    """The scope's inputs or its file are not what the owner's decision was pinned from."""


# ------------------------------------------------------------------------ the ungrounded card


def numerals(text: str) -> list[Decimal]:
    """The numbers a text writes in digits, as values, in order."""
    return [Decimal(found.replace(",", "")) for found in _NUMERAL.findall(text)]


def generator_input(snapshot_description: str | None) -> str:
    """What the card generator was given: the first 500 characters of the snapshot's text."""
    return (snapshot_description or "")[:GENERATOR_INPUT_CHARS]


def ungrounded_card(card: str | None, snapshot_description: str | None) -> bool:
    """True when the card writes a number that is no numeral of the generator's input."""
    if card is None:
        return False
    given = set(numerals(generator_input(snapshot_description)))
    return any(number not in given for number in numerals(card))


def ungrounded_cards(rows: Iterable[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    """The S0 rows' ungrounded cards, sorted: the claimed site ids, and the site ids whose card
    writes a number but whose site the snapshot does not have (no known input: never claimed)."""
    claimed: list[str] = []
    unknown: list[str] = []
    for row in rows:
        if ungrounded_card(row["card"], row["snapshot_description"]):
            (claimed if row["in_snapshot"] else unknown).append(str(row["id"]))
    return sorted(claimed), sorted(unknown)


# ---------------------------------------------------------------- the marker without an entry


def markers_without_entry(row: Mapping[str, Any]) -> list[int]:
    """The `[N]` a row's description sets that its `raw_data.description_citations` has no entry
    for, sorted: the first half of acceptance D1 (`acceptance/checks.d1`), read with the census's
    own T08 functions - `marker_sequence` (grouped and range markers expanded first) and `entries`
    (an array that cannot be read raises). A row without an array has no entry."""
    raw = row["raw_data"]
    citations = raw.get(M.CITATIONS_KEY) if isinstance(raw, Mapping) else None
    numbers = {entry["n"] for entry in T08.entries(citations, str(row["id"]))}
    return sorted(set(T08.marker_sequence(row["description"] or "")) - numbers)


def listed_markers(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """The site ids the orphan-citations lane listed with a marker without an entry (its
    `SKIPPED.jsonl`, reason `D1_REASON`), in the listing's order. A record of another reason is not
    this list's; a record without a site id and a reason, or a site listed twice, is refused."""
    found: list[str] = []
    for number, record in enumerate(records, start=1):
        site_id, reason = record.get("site_id"), record.get("reason")
        if not isinstance(site_id, str) or not isinstance(reason, str):
            raise ScopeError(f"listing record {number} lacks a site id and a reason: {record!r}")
        if reason != D1_REASON:
            continue
        if site_id in found:
            raise ScopeError(f"listing record {number}: {site_id} is listed twice")
        found.append(site_id)
    return found


# ---------------------------------------------------------------------------------- the scope


def sites_digest(sites: Sequence[Mapping[str, Any]]) -> str:
    """The sha256 of the site list, one canonical JSON object per line."""
    body = "".join(json.dumps(site, ensure_ascii=False, sort_keys=True) + "\n" for site in sites)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def scope_payload(
    rows: Sequence[Mapping[str, Any]],
    cleared: Mapping[str, Collection[str]],
    *,
    inputs: Mapping[str, str],
    version: int,
    markers: Collection[str] = (),
) -> dict[str, Any]:
    """The scope file's content of `version`: every list, each site with the lists it came from,
    sorted.

    `rows` are the S0 export's rows, `cleared` is `plan4.cleared_defects` over Phase 3's refusals
    (`{site_id: {field}}`), `inputs` the sha256 of each input file by its name, `markers` the site
    ids of the D1 listing (`listed_markers`; version 2 on): each must be a curated row that sets a
    marker without an entry in its own row (`markers_without_entry`).
    """
    if version not in VERSION_LISTS:
        raise ScopeError(f"no scope version {version!r}; the versions are {sorted(VERSION_LISTS)}")
    carried = VERSION_LISTS[version]
    if markers and D1_MARKER_WITHOUT_ENTRY not in carried:
        raise ScopeError(f"version {version} carries no list {D1_MARKER_WITHOUT_ENTRY!r}")
    known = {str(row["id"]) for row in rows}
    unknown = sorted(set(cleared) - known)
    if unknown:
        raise ScopeError(f"cleared defects name sites that are not curated rows: {unknown[:5]}")
    stray = sorted(set(markers) - known)
    if stray:
        raise ScopeError(f"the D1 listing names sites that are not curated rows: {stray[:5]}")
    members: dict[str, set[str]] = {name: set() for name in carried}
    for site_id, fields in cleared.items():
        for field_name in fields:
            if field_name not in CLEARED_LISTS:
                raise ScopeError(f"{site_id}: a cleared defect of {field_name!r}, not a text field")
            members[CLEARED_LISTS[field_name]].add(site_id)
    claimed, unclaimed = ungrounded_cards(rows)
    members[UNGROUNDED_CARD].update(claimed)
    by_row = {str(row["id"]): row for row in rows}
    for site_id in markers:
        if not markers_without_entry(by_row[site_id]):
            raise ScopeError(
                f"{site_id}: its description sets no marker without an entry in these rows - D1 "
                "does not fail on it as the listing says"
            )
        members[D1_MARKER_WITHOUT_ENTRY].add(site_id)
    by_site: dict[str, list[str]] = {}
    for name in carried:
        for site_id in sorted(members[name]):
            by_site.setdefault(site_id, []).append(name)
    sites = [{"site_id": site_id, "lists": by_site[site_id]} for site_id in sorted(by_site)]
    return {
        "version": version,
        "decision": DECISIONS[version],
        "inputs": dict(sorted(inputs.items())),
        "methods": dict(VERSION_METHODS[version]),
        "lists": {name: len(members[name]) for name in carried},
        "unclaimed": {UNGROUNDED_CARD: {NOT_IN_SNAPSHOT: unclaimed}},
        "sites": sites,
        "sites_sha256": sites_digest(sites),
    }


def render_scope(payload: Mapping[str, Any]) -> bytes:
    """The file's bytes: sorted keys, UTF-8, one-space indent, a final newline."""
    text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return text.encode("utf-8")


@dataclass(frozen=True)
class DefectScope:
    """The scope as the writer, the plan and the mass run read it: site id -> its lists."""

    version: int
    sha256: str
    sites: Mapping[str, tuple[str, ...]]

    def __contains__(self, site_id: object) -> bool:
        return site_id in self.sites

    @property
    def label(self) -> str:
        return f"{pinned_file(self.version)[0].name} v{self.version} {self.sha256[:16]}"


def parse_scope(data: bytes) -> DefectScope:
    """The scope a file's bytes hold, read strictly: every key, a known version, every site id a
    UUID once and in order, every list one of its version's (`VERSION_LISTS`) in their order, the
    counts and the digest the list's own."""
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict) or set(payload) != _KEYS:
        found = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise ScopeError(f"the scope's keys are {found}, not {sorted(_KEYS)}")
    version = payload["version"]
    if version not in VERSION_LISTS:
        raise ScopeError(f"scope version {version!r}; this reader knows {sorted(VERSION_LISTS)}")
    carried = VERSION_LISTS[version]
    sites: dict[str, tuple[str, ...]] = {}
    order: list[str] = []
    for site in payload["sites"]:
        if not isinstance(site, dict) or set(site) != _SITE_KEYS:
            raise ScopeError(f"a scope site's keys are not {sorted(_SITE_KEYS)}: {site!r}")
        site_id, lists = site["site_id"], site["lists"]
        try:
            uuid.UUID(site_id)
        except (ValueError, AttributeError, TypeError):
            raise ScopeError(f"{site_id!r} is not a site id") from None
        if not lists:
            raise ScopeError(f"{site_id}: no list")
        for name in lists:
            if name not in LISTS:
                raise ScopeError(f"{site_id}: {name!r} is not a list of the scope {LISTS}")
            if name not in carried:
                raise ScopeError(f"{site_id}: version {version} carries no list {name!r}")
        if list(lists) != sorted(set(lists), key=LISTS.index):
            raise ScopeError(f"{site_id}: lists {lists} are not in the scope's order, once each")
        order.append(site_id)
        sites[site_id] = tuple(lists)
    if order != sorted(set(order)):
        raise ScopeError("the scope's sites are not sorted by site id, each once")
    counts = {name: sum(name in lists for lists in sites.values()) for name in carried}
    if payload["lists"] != counts:
        raise ScopeError(f"the list counts {payload['lists']} are not the sites' {counts}")
    if payload["sites_sha256"] != sites_digest(payload["sites"]):
        raise ScopeError("sites_sha256 is not the digest of the scope's own site list")
    return DefectScope(
        version=payload["version"], sha256=hashlib.sha256(data).hexdigest(), sites=sites
    )


def pinned_file(version: int) -> tuple[Path, str]:
    """The file of a scope version and the sha256 its bytes must hash to: the current version's
    (`SCOPE_FILE`, `SCOPE_SHA256`), or version 1's, kept byte for byte beside it."""
    if version == SCOPE_VERSION:
        return SCOPE_FILE, SCOPE_SHA256
    if version == 1:
        return SCOPE_V1_FILE, SCOPE_V1_SHA256
    raise ScopeError(f"no pinned scope of version {version!r}")


def load_scope(version: int = SCOPE_VERSION) -> DefectScope:
    """The owner's defect scope of `version` - the current one unless named: its pinned file, whose
    bytes must hash to its pin and which must hold that version. The writers and the mass run read
    the current version; version 1 is read to rebuild the mass run's plan (`build --defect-scope`)."""
    path, pin = pinned_file(version)
    data = path.read_bytes()
    found = hashlib.sha256(data).hexdigest()
    if found != pin:
        raise ScopeError(
            f"{path}: sha256 {found} is not the pinned scope {pin} - a new scope is a new version "
            "and a new pin (phase4/scope4.py), never an edit of the file"
        )
    scope = parse_scope(data)
    if scope.version != version:
        raise ScopeError(f"{path}: a scope of version {scope.version}, pinned as version {version}")
    return scope
