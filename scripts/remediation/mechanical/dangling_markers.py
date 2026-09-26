"""The dangling-markers lane: a `[N]` of the description that has no citation entry is taken out of
the text, and lane L's provenance hash is moved with it. This is HUMAN_ONLY D9's option (b).

## The class

D1 (`acceptance/checks.py`) holds when every `[N]` marker of `unified_sites.description` has an
entry in `raw_data.description_citations` and every entry is cited. The orphan-citations lane
(`citations.py`) repaired the second half on 69 sites. It listed the 9 sites with a marker that has
no entry, because the source of such a marker is not in the data (HUMAN_ONLY D9). The D9 run then
gave 6 of them a sourced Phase-4 description. The rest were held by Phase 4 with a closed-list
reason: Killa Mach'ay (`abstained`, the mass run), Afrodit Tapınağı and A Figa (`search-stopped`,
the D9 run). Read on production on 2026-09-25 with the orphan-citations lane's own read, D1 fails on
exactly these 3.

## The decision

The owner's order of 2026-09-25 ("autonom Empfehlungen umsetzen") takes D9's recommended option
for a held site: **remove the marker from the text**. A marker that points to no source is a false
attribution. The server-rendered page shows it as a bare `<sup>[N]</sup>`. The text's claims stay
as they are: the site keeps lane L's `_description_provenance`, which marks the text as generated
by the March LLM chain (`ai: generated`), and the acceptance judges that marking, not the claims.
No source is invented, and no marker is renumbered to point at an entry: the data does not say
which source a dangling marker meant.

## What the lane writes (`classify`, `without_dangling`, `rewritten`)

Two cells of one site, in one transaction, each journalled:

* **`description`**: the text without its dangling markers. **The rule:** each maximal run of
  adjacent markers, with the horizontal whitespace directly before it, loses exactly its dangling
  markers. The whitespace goes too, but only when no marker of the run is left. This is the
  frontend's own marker shape (`seo/text.ts` `stripCitations`: `[^\\S\\n]*\\[\\d+\\]`), taken as a
  run so that `worship [4][1]` keeps its space. A marker is a dangling one when its number has no
  entry, and then every occurrence of it goes. Every other character stays. `removal_faults` proves
  it on each planned text:
  * the kept markers are the old ones, in order;
  * with all whitespace taken out, the new text is the old one without those tokens;
  * no leading or trailing whitespace, double space, space before punctuation or empty bracket
    appears that the old text did not have.

  A text that fails any of these is listed, not written.
* **`raw_data`**: `_description_provenance.desc_sha256` becomes the sha256 of the new description,
  so D4 keeps holding. Every other key and value stays byte for byte, in its order.
  `description_citations` stays as it is, with one exception: an entry that no marker cites once
  the dangling markers are gone is removed. That is the orphan-citations lane's rule (`repaired`,
  imported). That lane held the entry back only as the evidence for option (a), which is now not
  taken. Only Killa Mach'ay has such an entry: entry 2 ("3,400 metres"), whose URL entries 1 and 3
  still carry. Without its removal D1 would still fail there. The removed entry survives in the
  journal's `old_value`.

`build` reads every planned site with the acceptance's own `d1` and `d4` and refuses the plan
unless both hold.

## What is refused (listed, never written)

The first rule that fails lists the site:

1. **D1 holds** - no candidate.
2. **The entries are readable** (`citations-not-readable`).
3. **A marker has no entry** (`no-dangling-marker`): a D1 failure made only of uncited entries is
   the orphan-citations lane's class, not this one's.
4. **Plain markers only** (`grouped-markers`): a grouped or range form (`[1, 2]`) is expanded by
   the census before it is read; this rule removes plain `[N]` tokens only.
5. **The text carries lane L's marking**:
   * `no-legacy-provenance`: no provenance means nothing marks the text as generated, and the
     reason the claims may stay is gone;
   * `phase4-provenance`: a lane other than L. A Phase-4 text is assembled by code, whose markers
     all have entries (V8);
   * `provenance-not-readable`: the lane is L but the provenance does not parse;
   * `provenance-hash-differs`: the provenance already disagrees with the text (D4 fails before
     the write).
6. **Each cell's journal ends at the live value** (`journal-chain-broken`, `journal-disagrees`).
   `raw_data` is compared as JSON with sorted keys.
7. **The value can be written as Postgres prints it** (`raw-data-not-reprinted`).
8. **The removal is clean** (`removal-not-clean`, `removal_faults` above).

Every write is conditioned on the description and the raw_data it read (guard 3, full text and
jsonb). It is also conditioned on the premise (guard 5, `lane.DANGLING_MARKERS.premise_sql`): the
legacy provenance without the hash the lane moves. That premise is a Phase-4 text's refusal in the
database, and it holds for the write and for its reversal alike.

## Files

`--export` reads production (read-only, one repeatable-read snapshot): every curated row and the
`description` and `raw_data` journal of the curated rows. It writes
`<out>/export/export.jsonl` (gitignored). `--write` plans from that file alone and writes
`PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md` and `ROLLBACK.sql` into
`output/remediation/mechanical_dangling_markers/`. `apply.py --lane dangling-markers` renders,
rehearses and applies the statement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from acceptance.checks import d1, d4  # noqa: E402
from census.tests.t08_citation_markers import _excerpt, entries, marker_sequence  # noqa: E402
from phase4.model4 import (  # noqa: E402
    CITATIONS_KEY,
    PROVENANCE_KEY,
    LegacyProvenance,
    parse_json,
    text_sha256,
)
from phase4.model4 import (
    Lane as TextLane,
)

from mechanical.apply import lane_dir  # noqa: E402
from mechanical.citations import (  # noqa: E402
    D1_SOURCE,
    NOT_READABLE,
    NOT_REPRINTED,
    canonical,
    repaired,
    reprint,
)
from mechanical.lane import DANGLING_MARKERS  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    _now,
    journal_break,
    parse_tagged_export,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
    write_tagged_export,
)

LANE = DANGLING_MARKERS
TEXT, RAW = "description", "raw_data"
RULE_REMOVED = "dangling-markers-removed"
RULE_HASH = "provenance-hash"
RULE_HASH_ENTRIES = "provenance-hash-and-uncited-entries"
NO_DANGLING = "no-dangling-marker"
GROUPED = "grouped-markers"
NO_PROVENANCE = "no-legacy-provenance"
PHASE4 = "phase4-provenance"
PROVENANCE_NOT_READABLE = "provenance-not-readable"
HASH_DIFFERS = "provenance-hash-differs"
NOT_CLEAN = "removal-not-clean"
HASH_KEY = "desc_sha256"
EXPORT_KINDS = ("site", "journal")
ORDER = "HUMAN_ONLY.md D9 option (b), the owner's order of 2026-09-25"

#: A marker run and the horizontal whitespace before it: the frontend's marker shape
#: (`seo/text.ts` stripCitations, `/[^\S\n]*\[\d+\]/g`), taken as a run of adjacent markers.
_RUN = re.compile(r"(?P<space>[^\S\n]*)(?P<run>(?:\[\d+\])+)")
_TOKEN = re.compile(r"\[(\d+)\]")
#: What a clean removal never adds: `(name, pattern)`, each counted in the old and the new text.
_SPACING = (
    ("leading whitespace", re.compile(r"^\s")),
    ("trailing whitespace", re.compile(r"\s$")),
    ("double space", re.compile(r"[^\S\n]{2,}")),
    ("space before punctuation", re.compile(r"[^\S\n]+[.,;:!?)]")),
    ("empty brackets", re.compile(r"\(\s*\)")),
)

SITES_SQL = (
    "SELECT u.id::text AS site_id, u.name, u.description, u.raw_data::text AS raw_data, "
    f"{LANE.premise_sql} AS premise FROM unified_sites u "
    f"WHERE u.source_id = '{CURATED_SOURCE}' ORDER BY u.id"
)
JOURNAL_SQL = (
    "SELECT l.id, l.row_pk, l.column_name, l.run_stamp, coalesce(l.test_id, '') AS test_id, "
    "l.old_value, l.new_value FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
    "AND l.column_name IN ('description', 'raw_data') AND l.row_pk IN (SELECT u.id::text FROM "
    f"unified_sites u WHERE u.source_id = '{CURATED_SOURCE}') ORDER BY l.id"
)


# ------------------------------------------------------------------------------ the export
@dataclass(frozen=True)
class Site:
    """One curated row as the export read it; `premise` is `LANE.premise_sql`, by Postgres."""

    site_id: str
    name: str
    description: str | None
    raw_data: str | None
    premise: str


@dataclass(frozen=True)
class Export:
    sites: tuple[Site, ...]
    #: Each cell's journal, oldest first, keyed by `(site_id, column)`.
    journal: Mapping[tuple[str, str], tuple[JournalLink, ...]]
    exported_at: str


def export_script() -> str:
    """One read-only snapshot: every curated row, and every description/raw_data journal row."""
    return tagged_export_script([("site", SITES_SQL), ("journal", JOURNAL_SQL)])


def parse_export(text: str) -> Export:
    rows, exported_at = parse_tagged_export(text, EXPORT_KINDS)
    journal: dict[tuple[str, str], list[JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault((str(r["row_pk"]), str(r["column_name"])), []).append(
            JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    sites = tuple(
        Site(
            site_id=str(r["site_id"]),
            name=str(r["name"]),
            description=r["description"],
            raw_data=r["raw_data"],
            premise=str(r["premise"]),
        )
        for r in rows["site"]
    )
    return Export(sites, {cell: tuple(links) for cell, links in journal.items()}, exported_at)


def premise_of(raw: Mapping[str, Any]) -> str:
    """`LANE.premise_sql` in Python: the provenance without its hash, as Postgres prints it.

    Postgres' `jsonb - text` drops the key of an object and the equal string elements of an array,
    and refuses a scalar - so an export never holds a scalar provenance's premise, and this refuses
    it too (audit 2026-09-25 m7: a non-object used to crash here, before `classify` could list it).
    """
    provenance = raw.get(PROVENANCE_KEY)
    if provenance is None:
        return "null"
    if isinstance(provenance, dict):
        return reprint({key: value for key, value in provenance.items() if key != HASH_KEY})
    if isinstance(provenance, list):
        return reprint([item for item in provenance if item != HASH_KEY])
    raise PlanError(
        f"a scalar provenance {provenance!r}: Postgres refuses `- '{HASH_KEY}'` on a scalar, so no "
        "export carries its premise"
    )


# ---------------------------------------------------------------------------- the removal
def without_dangling(text: str, dangling: set[int]) -> str:
    """`text` without the markers numbered in `dangling` (the module docstring's rule)."""

    def cut(match: re.Match[str]) -> str:
        kept = "".join(
            token.group(0)
            for token in _TOKEN.finditer(match["run"])
            if int(token.group(1)) not in dangling
        )
        return match["space"] + kept if kept else ""

    return _RUN.sub(cut, text)


def removal_faults(old: str, new: str, dangling: set[int]) -> list[str]:
    """Why `new` is not `old` less its dangling markers and the space before them; [] when it is."""
    faults = []
    kept = [n for n in marker_sequence(old) if n not in dangling]
    if marker_sequence(new) != kept:
        faults.append(f"the kept markers are {marker_sequence(new)}, not {kept}")
    tokens_out = _TOKEN.sub(lambda t: "" if int(t.group(1)) in dangling else t.group(0), old)
    if re.sub(r"\s", "", new) != re.sub(r"\s", "", tokens_out):
        faults.append("other characters than the dangling markers changed")
    for name, pattern in _SPACING:
        if len(pattern.findall(new)) > len(pattern.findall(old)):
            faults.append(f"the removal adds {name}")
    return faults


def rewritten(raw: Mapping[str, Any], description: str, markers: set[int]) -> dict[str, Any]:
    """`raw` for the new description: its entries no marker cites removed (`repaired`), and the
    provenance hash moved to the new text. Every other key keeps its value and its place."""
    fixed = repaired(raw, markers)
    return {
        key: {**value, HASH_KEY: text_sha256(description)} if key == PROVENANCE_KEY else value
        for key, value in fixed.items()
    }


# ------------------------------------------------------------------------------ the decision
def _entry(e: Mapping[str, Any]) -> str:
    return f"[{e['n']}] {e.get('title')!r} <{e.get('url')}>" + (
        f" claim {e['claim']!r}" if e.get("claim") else ""
    )


def classify(
    site: Site, journal: Mapping[tuple[str, str], Sequence[JournalLink]]
) -> tuple[Verdict, ...] | None:
    """One site: None where D1 holds; else its two cells, or the one reason it is listed."""
    raw = None if site.raw_data is None else parse_json(site.raw_data)
    raw = raw if isinstance(raw, dict) else {}
    citations = raw.get(CITATIONS_KEY)
    failure = d1(
        {
            "site_id": site.site_id,
            "description": site.description,
            "description_citations": citations,
        }
    )
    if failure is None:
        return None
    if parse_json(site.premise) != parse_json(premise_of(raw)):
        raise PlanError(
            f"{site.site_id}: the export's premise {site.premise!r} is not the provenance its "
            "raw_data carries - the export is not one snapshot"
        )
    text = site.description or ""
    found = {"source": "acceptance:D1", "url": D1_SOURCE, "quote": failure}

    def listed(reason: str, note: str) -> tuple[Verdict, ...]:
        return (
            Verdict(
                site_id=site.site_id,
                site_name=site.name,
                ok=False,
                old_value=site.description,
                new_value=None,
                rule=reason,
                reason=reason,
                note=note,
                phase3=False,
                finding_test_id="T08",
                evidence=(found,),
                column=TEXT,
            ),
        )

    try:
        cited_entries = entries(citations, site.site_id)
    except ValueError as exc:
        return listed(NOT_READABLE, f"the citation entries cannot be read: {exc}")
    numbers = {e["n"] for e in cited_entries}
    markers = marker_sequence(text)
    dangling = set(markers) - numbers
    if not dangling:
        return listed(
            NO_DANGLING,
            "every marker has an entry; the entries no marker cites are the orphan-citations "
            "lane's class",
        )
    if [int(n) for n in _TOKEN.findall(text)] != markers:
        return listed(GROUPED, "the text carries a grouped or range marker; plain [N] only")
    provenance = raw.get(PROVENANCE_KEY)
    if provenance is None:
        return listed(NO_PROVENANCE, "no _description_provenance marks the text as generated")
    if not isinstance(provenance, dict) or provenance.get("lane") != TextLane.L.value:
        lane = provenance.get("lane") if isinstance(provenance, dict) else provenance
        return listed(PHASE4, f"the provenance is lane {lane!r}, not the March text's L")
    try:
        legacy = LegacyProvenance.from_dict(provenance)
    except ValueError as exc:
        return listed(PROVENANCE_NOT_READABLE, f"the legacy provenance does not read: {exc}")
    if legacy.desc_sha256 != text_sha256(text):
        return listed(HASH_DIFFERS, "desc_sha256 is already not the sha256 of the description")
    for column, links, live in (
        (TEXT, journal.get((site.site_id, TEXT), ()), site.description),
        (
            RAW,
            [
                JournalLink(
                    link.id,
                    link.run_stamp,
                    link.test_id,
                    canonical(link.old_value),
                    canonical(link.new_value),
                )
                for link in journal.get((site.site_id, RAW), ())
            ],
            canonical(site.raw_data),
        ),
    ):
        broken = journal_break(links, live)
        if broken is not None:
            return listed(broken[0], f"{column}: {broken[1]}")
    if site.raw_data is None or reprint(raw) != site.raw_data:
        return listed(
            NOT_REPRINTED,
            "raw_data is not the text this planner would print for its value: the journal would "
            "record another spelling of the value than the one the row holds",
        )
    new_text = without_dangling(text, dangling)
    faults = removal_faults(text, new_text, dangling)
    if faults:
        return listed(NOT_CLEAN, "; ".join(faults))
    kept = set(marker_sequence(new_text))
    new_raw = rewritten(raw, new_text, kept)
    dropped = [e for e in cited_entries if e["n"] not in kept]
    tokens = ", ".join(f"[{n}] x{text.count(f'[{n}]')}" for n in sorted(dangling))
    evidence_text = (
        found,
        *(
            {"source": "unified_sites.description", "url": "unified_sites.description", "quote": q}
            for q in (_excerpt(text, n) for n in sorted(dangling))
        ),
        {
            "source": "unified_sites.raw_data.description_citations",
            "url": "unified_sites.raw_data",
            "quote": "; ".join(_entry(e) for e in cited_entries) or "no entry",
        },
        {
            "source": "unified_sites.raw_data._description_provenance",
            "url": "unified_sites.raw_data",
            "quote": f"lane L, ai generated ({legacy.ai_system}), desc_sha256 {legacy.desc_sha256}",
        },
    )
    note = (
        f"the description cites {', '.join(f'[{n}]' for n in sorted(dangling))} with no entry "
        f"(entries {sorted(numbers)}): {tokens} removed, the space before a marker run only with "
        "the run's last marker; every other character stays, and the claims stay under lane L's "
        f"generated marking ({ORDER})"
    )
    hash_note = (
        f"_description_provenance.desc_sha256 {legacy.desc_sha256} -> "
        f"{text_sha256(new_text)}, the sha256 of the new description (D4)"
    )
    if dropped:
        rule = RULE_HASH_ENTRIES
        hash_note += (
            f"; entr{'y' if len(dropped) == 1 else 'ies'} {[e['n'] for e in dropped]} cited by no "
            "marker once the dangling markers are gone removed (the orphan-citations rule)"
        )
    else:
        rule = RULE_HASH
        hash_note += "; description_citations unchanged"
    common = {
        "site_id": site.site_id,
        "site_name": site.name,
        "ok": True,
        "reason": "",
        "phase3": False,
        "premise": site.premise,
    }
    return (
        Verdict(
            **common,
            old_value=text,
            new_value=new_text,
            rule=RULE_REMOVED,
            note=note,
            finding_test_id="T08/marker-without-entry",
            evidence=evidence_text,
            column=TEXT,
        ),
        Verdict(
            **common,
            old_value=site.raw_data,
            new_value=reprint(new_raw),
            rule=rule,
            note=hash_note + "; every other raw_data key stays as it is",
            finding_test_id="D4/provenance-hash",
            evidence=(
                {
                    "source": "acceptance:D4",
                    "url": D1_SOURCE,
                    "quote": "desc_sha256 must be the sha256 of the served description",
                },
                {
                    "source": "unified_sites.raw_data.description_citations",
                    "url": "remediation_change_log.old_value",
                    "quote": "removed: " + ("; ".join(_entry(e) for e in dropped) or "nothing"),
                },
            ),
            column=RAW,
        ),
    )


def build(export: Export, *, built_at: str) -> Plan:
    """The plan over every curated row, read against the acceptance's own D1 and D4."""
    changes: list[Verdict] = []
    skipped: list[Verdict] = []
    holds = 0
    for site in sorted(export.sites, key=lambda s: s.site_id):
        verdicts = classify(site, export.journal)
        if verdicts is None:
            holds += 1
            continue
        if not verdicts[0].ok:
            skipped.extend(verdicts)
            continue
        text, data = verdicts
        written = json.loads(str(data.new_value))
        after = {
            "site_id": site.site_id,
            "description": text.new_value,
            "description_citations": written.get(CITATIONS_KEY),
            "description_provenance": written.get(PROVENANCE_KEY),
        }
        for check, result in (("D1", d1(after)), ("D4", d4(after))):
            if result is not None:
                raise PlanError(
                    f"{site.site_id}: {check} would still fail after the write: {result}"
                )
        changes.extend(verdicts)
    counters = Counter(v.rule for v in changes) + Counter(v.reason for v in skipped)
    return Plan(
        changes=tuple(changes),
        skipped=tuple(skipped),
        built_at=built_at,
        counters={
            "curated": len(export.sites),
            "d1_holds": holds,
            "d1_fails": len(export.sites) - holds,
            "sites_written": len({v.site_id for v in changes}),
            "cells": len(changes),
            **dict(sorted(counters.items())),
        },
        lane=LANE,
    )


# ------------------------------------------------------------------------------ the files
REFUSAL_MEANING = {
    NOT_READABLE: "the citation entries are not a list of objects with an integer n",
    NO_DANGLING: "every marker has an entry - the orphan-citations lane's class",
    GROUPED: "a grouped or range marker; the rule removes plain [N] tokens only",
    NO_PROVENANCE: "no provenance marks the text as generated",
    PHASE4: "the text is not lane L's (a Phase-4 provenance)",
    PROVENANCE_NOT_READABLE: "the legacy provenance does not parse",
    HASH_DIFFERS: "the provenance hash already disagrees with the text",
    "journal-chain-broken": "a cell's journal is not continuous",
    "journal-disagrees": "a cell's journal does not end at the live value",
    NOT_REPRINTED: "raw_data is not printed the way this planner prints JSON",
    NOT_CLEAN: "the removal would change more than the markers and the space before them",
}


def write_plan_md(plan: Plan, export: Export, path: Path, *, export_sha256: str) -> None:
    lane, counters = plan.lane, plan.counters
    add = (lines := []).append
    add(f"# Dangling citation markers - plan ({lane.name})")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/dangling_markers.py` from the "
        f"export read at {export.exported_at} (`export/export.jsonl`, sha256 {export_sha256}). "
        f"Lane `{lane.name}`: run stamp `{lane.run_stamp}`, journal test id `{lane.test_id}`, "
        f"change keys `{lane.key_prefix}:<site_id>:<column>`. The premise (guard 5) is "
        f"`{lane.premise_sql}`."
    )
    add("")
    add(
        f"D1 (`acceptance/checks.py`) over **{counters['curated']}** curated rows: holds on "
        f"{counters['d1_holds']}, fails on **{counters['d1_fails']}**. **{counters['sites_written']} "
        f"site(s), {counters['cells']} cell(s) will be written**, **{len(plan.skipped)} listed**. "
        f"The decision is {ORDER}: a marker that points to no source leaves the text, the claims "
        "stay under lane L's generated marking. D1 and D4 hold on every planned value (`build`)."
    )
    add("")
    add("## Written")
    by_site: dict[str, list[Verdict]] = {}
    for change in plan.changes:
        by_site.setdefault(change.site_id, []).append(change)
    for cells in by_site.values():
        text, data = cells
        add("")
        add(f"### {text.site_name} (`{text.site_id}`)")
        add("")
        add(f"* `description` (`{text.rule}`): {text.note}")
        add(f"* `raw_data` (`{data.rule}`): {data.note}")
        add("")
        add(f"Old: {text.old_value}")
        add("")
        add(f"New: {text.new_value}")
    add("")
    add("## Listed, not written")
    add("")
    add("| reason | sites | what it means |")
    add("|---|---|---|")
    for reason, count in sorted(Counter(v.reason for v in plan.skipped).items()):
        add(f"| `{reason}` | {count} | {REFUSAL_MEANING.get(reason, '')} |")
    add("")
    for v in plan.skipped:
        add(f"* {v.site_name} (`{v.site_id}`): `{v.reason}` - {v.note}")
    if not plan.skipped:
        add("None: every site D1 fails on is written.")
    add("")
    add("## After the apply")
    add("")
    add(
        "Lane L's acceptance reads the raw_data rows this lane rewrote as superseded once it is told "
        f"the stamp (`verify_writes4.py --lane p4l ... --allow-stamp '{lane.run_stamp}'`). The SSR "
        "page and the API read the database; the static export, the Qdrant resync and IndexNow of "
        "the Phase-6 runbook carry the new texts out. The next card_stats wave's premise reads "
        "`md5(description)` of these sites."
    )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the dangling-markers lane (mechanical)")
    ap.add_argument(
        "--export", action="store_true", help="read production (read-only) into export/"
    )
    ap.add_argument("--write", action="store_true", help="plan from export/ (no database)")
    ap.add_argument("--out", type=Path, help="the lane's directory unless given")
    args = ap.parse_args(argv)
    if not (args.export or args.write):
        ap.print_help()
        return 0
    out = lane_dir(LANE) if args.out is None else args.out
    export_path = out / "export" / "export.jsonl"
    try:
        if args.export:
            write_tagged_export(export_script(), export_path)
        if args.write:
            text = export_path.read_text(encoding="utf-8")
            export = parse_export(text)
            plan = build(export, built_at=_now())
            write_plan_jsonl(plan, out / "PLAN.jsonl")
            write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
            write_plan_md(
                plan,
                export,
                out / "PLAN.md",
                export_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
            print(json.dumps(dict(plan.counters), indent=1))
            if plan.changes:
                write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
