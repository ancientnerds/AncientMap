"""The owner's defect scope: the only sites Phases 4 and 5 write (`SCOPE4.json`, pinned).

Owner decision 2026-09-23 (Martin, "Nur Defekt-Sites (Recommended)"): after a passing Phase-4 pilot,
Phases 4/5 write only the sites with proven text defects - the Phase-3 cleared defects plus the
ungrounded card texts, in the design's order; every other site's description and card stay exactly
as they are. This module is that sentence as data: three lists, each derived from a pinned input,
joined in one file that is pinned by its sha256 (`SCOPE_SHA256`). A new scope is a new version and
a new pin in this file, never an edit of `SCOPE4.json`.

The lists
---------
* `phase3-cleared-description`, `phase3-cleared-card` - the description and card defects Phase 3's
  reviewer cleared: the rows of `logs/_write_dry/ALL_REFUSED.jsonl` under the rule
  `report-only-field` (`plan4.cleared_defects`), the 322 and 709 of the design.
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
inside the scope - V9's floor waiver and the plan's order.

Pure: no database, no network. `plan4.py scope` writes the file, `write4` refuses every site outside
it (`RULE_OUT_OF_SCOPE`), `plan4.py build --defect-scope` builds the mass run's plan from it, and
`mass4` asks no model question for a site outside it.
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

REPO = Path(__file__).resolve().parents[3]

#: The version of the scope file's form and content; a new scope is a new version and a new pin.
SCOPE_VERSION = 1
SCOPE_FILE = REPO / "output" / "remediation" / "phase4_runner" / "SCOPE4.json"
#: The sha256 of `SCOPE_FILE`'s bytes: the gate, the plan and the mass run read this file or none.
SCOPE_SHA256 = "19a57e9fd17f53601fecdd5424d3ea3e085c2690e8250cb72b004f010f833d6a"

CLEARED_DESCRIPTION = "phase3-cleared-description"
CLEARED_CARD = "phase3-cleared-card"
UNGROUNDED_CARD = "ungrounded-card"
#: The lists, in the order a site names them.
LISTS = (CLEARED_DESCRIPTION, CLEARED_CARD, UNGROUNDED_CARD)
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
) -> dict[str, Any]:
    """The scope file's content: every list, each site with the lists it came from, sorted.

    `rows` are the S0 export's rows, `cleared` is `plan4.cleared_defects` over Phase 3's refusals
    (`{site_id: {field}}`), `inputs` the sha256 of each input file by its name.
    """
    known = {str(row["id"]) for row in rows}
    unknown = sorted(set(cleared) - known)
    if unknown:
        raise ScopeError(f"cleared defects name sites that are not curated rows: {unknown[:5]}")
    members: dict[str, set[str]] = {name: set() for name in LISTS}
    for site_id, fields in cleared.items():
        for field_name in fields:
            if field_name not in CLEARED_LISTS:
                raise ScopeError(f"{site_id}: a cleared defect of {field_name!r}, not a text field")
            members[CLEARED_LISTS[field_name]].add(site_id)
    claimed, unclaimed = ungrounded_cards(rows)
    members[UNGROUNDED_CARD].update(claimed)
    by_site: dict[str, list[str]] = {}
    for name in LISTS:
        for site_id in sorted(members[name]):
            by_site.setdefault(site_id, []).append(name)
    sites = [{"site_id": site_id, "lists": by_site[site_id]} for site_id in sorted(by_site)]
    return {
        "version": SCOPE_VERSION,
        "decision": DECISION,
        "inputs": dict(sorted(inputs.items())),
        "methods": dict(METHODS),
        "lists": {name: len(members[name]) for name in LISTS},
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
        return f"{SCOPE_FILE.name} v{self.version} {self.sha256[:16]}"


def parse_scope(data: bytes) -> DefectScope:
    """The scope a file's bytes hold, read strictly: every key, every site id a UUID once and in
    order, every list one of `LISTS` in their order, the counts and the digest the list's own."""
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict) or set(payload) != _KEYS:
        found = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise ScopeError(f"the scope's keys are {found}, not {sorted(_KEYS)}")
    if payload["version"] != SCOPE_VERSION:
        raise ScopeError(f"scope version {payload['version']!r}; this reader is {SCOPE_VERSION}")
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
        if list(lists) != sorted(set(lists), key=LISTS.index):
            raise ScopeError(f"{site_id}: lists {lists} are not in the scope's order, once each")
        order.append(site_id)
        sites[site_id] = tuple(lists)
    if order != sorted(set(order)):
        raise ScopeError("the scope's sites are not sorted by site id, each once")
    counts = {name: sum(name in lists for lists in sites.values()) for name in LISTS}
    if payload["lists"] != counts:
        raise ScopeError(f"the list counts {payload['lists']} are not the sites' {counts}")
    if payload["sites_sha256"] != sites_digest(payload["sites"]):
        raise ScopeError("sites_sha256 is not the digest of the scope's own site list")
    return DefectScope(
        version=payload["version"], sha256=hashlib.sha256(data).hexdigest(), sites=sites
    )


def load_scope() -> DefectScope:
    """The owner's defect scope: `SCOPE_FILE`, whose bytes must hash to `SCOPE_SHA256`."""
    data = SCOPE_FILE.read_bytes()
    found = hashlib.sha256(data).hexdigest()
    if found != SCOPE_SHA256:
        raise ScopeError(
            f"{SCOPE_FILE}: sha256 {found} is not the pinned scope {SCOPE_SHA256} - a new scope "
            "is a new version and a new pin (phase4/scope4.py), never an edit of the file"
        )
    return parse_scope(data)
