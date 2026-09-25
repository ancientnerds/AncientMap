"""The orphan-citations lane: citation entries that no `[N]` of the description cites, taken out of
`raw_data`. This is the class the Phase-6 acceptance's D1 found on draw-2026-09-25.

## The class

D1 (`acceptance/checks.py`, PROTOCOL.md section 8) holds when every `[N]` marker of
`unified_sites.description` has an entry in `raw_data.description_citations` and every entry is
cited. It reads markers and entries with the census's T08 functions (`marker_sequence`, `entries`).
Measured on production on 2026-09-25, read-only, over all 5,004 curated sites (AUDIT_LOG
2026-09-25, "Acceptance draw-2026-09-25 ends FAIL on A3 (D1)"), D1 fails on **78** of them:

* 64 whose description carries no marker at all, next to 1 to 3 entries (T08 `no-markers`);
* 5 whose markers all have entries, plus entries no marker cites (T08 `entry-never-cited`);
* 7 with a marker that has no entry (T08 `marker-without-entry`);
* 2 with both halves (Absalom's Tomb, Killa Mach'ay).

The 78 are exactly the census's T08 sites of 2026-09-20 minus the 15 that Phase 4 rewrote. Its
arrays are assembled by code (V8), so no Phase-4 text fails D1. None of the 78 descriptions has a
journal row. 76 carry lane L's `_description_provenance` (the March text) and 2 carry none: Huichún
(same as the pre-March snapshot) and Temple of Baalshamin (not in it). All 78 descriptions and arrays
are byte for byte what snapshot `e4652afe` held on 2026-04-24. None of the 78 carried an array before
the March chain (snapshot `d4526691`, 2026-03-05).

## The root cause

The March enrichment chain wrote the text and the array as two values, and nothing ever compared
them:

* `scripts/audit_enrich.py::merge_verification` stored the LLM verifier's `verified_description`
  and `verified_citations` as they came. The verifier's prompt told the model to "remove the
  ENTIRE sentence containing the unverifiable [N]", to "renumber remaining [N] citations" and to
  "update the citations array to match". No code checked that it did.
* `api/routes/sites.py::batch_upload_sites` wrote the uploaded description, and then the array
  only when the upload carried one. It never removed an array. `sync_from_production` overwrote
  the local description with production's without touching `raw_data`. Either path can pair a
  text with the array of another state. Huichún proves this happened: its description is
  byte-identical to its pre-March text, which never had a marker, and its array is the chain's.

The March chain is retired (plan section 12). The Phase-4 writer assembles both sides by code and
checks them (V8, V12). The census found the class on 2026-09-20 (T08), and every finding stayed
`REVIEW` there. The boot citation seed that Push #1 removed touched 10 other sites, none of the 78.

## What the lane writes, and why (`classify`, `repaired`)

A site D1 holds on is not a candidate. For the others, the first rule that fails lists the site:

1. **The entries are readable** (`citations-not-readable`): a list of objects with an integer `n`,
   the check `entries` makes. None fails this on 2026-09-25.
2. **Every marker has an entry** (`marker-without-entry`). A marker without an entry is a claim
   whose source is not in the data. It could be cured by adding the entry, from a source nobody has
   fetched, or by removing the marker from the text. This lane rewrites no text and invents no
   source, so the site is listed for a human (HUMAN_ONLY.md D9) and **nothing of it is written**.
   That includes the uncited entries of a site with both halves: on Absalom's Tomb they are
   exactly the sources of the markers the array lacks (the text's 6/7/8 are the array's 4/5/6,
   claim for claim), and dropping them would destroy the evidence for the right repair.
3. **The cell's journal ends at the live value** (`journal-chain-broken`, `journal-disagrees`,
   `plan.journal_break`). The comparison is JSON with the keys sorted, not text: Postgres prints
   jsonb keys in its own order.
4. **The value can be written as Postgres prints it** (`raw-data-not-reprinted`). The journal
   records the plan's text. The planner writes JSON the way Postgres prints jsonb (`', '` and
   `': '`, UTF-8, the keys in the order read), and it proves this on the old value first. None
   fails this on 2026-09-25.

What remains has markers that all have entries, and entries that no marker cites. **Those entries
are removed; nothing else is written:**

* With no marker at all (`citations-without-markers`), the whole `description_citations` key goes,
  and every other `raw_data` key stays as it is. A row whose only key was the array keeps `{}`.
* Otherwise (`uncited-entries`), only the uncited entries go. The cited ones stay byte for byte and
  in their order, and a numbering gap stays: renumbering would rewrite the text.

This follows from how an entry is read. The popup builds its source links from **every** entry,
cited or not (`SitePopup/sections/DescriptionSection.tsx`, `citationSources`). The only exception
is entries on the domain of the site's own `source_url`, which the source line already links.
Each link carries the entry's `[n]` in its tooltip and presents the entry as a source of the text.
The text never cites that `n`, so the claim is not true, and the page's attribution only stays true
without the entry. On 2026-09-25 this applies to 8 of the 69 planned sites; the other 61 keep the
same links. The server-rendered page and the meta surfaces render an entry only through its marker,
so nothing there changes. The removed entries survive in the journal's old value, so a human can put
one back together with its marker. Temple of Baalshamin shows the risk of keeping them: its one
orphan entry cites "Byzantine settlements in northwestern Syria", which is not about this temple.

Every write is conditioned on the raw_data it read (guard 3) and on the description its markers
were read from (guard 5, `lane.ORPHAN_CITATIONS.premise_sql`: the description's sha256, the value
`_description_provenance.desc_sha256` pins). `build` then reads every planned value with the
acceptance's own `d1` and refuses the plan unless D1 holds on each.

## Files

`--export` reads production (read-only, one repeatable-read snapshot: every curated row and the
`raw_data` journal of the curated rows) into `<out>/export/export.jsonl` (gitignored). `--write`
plans from that file alone and writes `PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md` and `ROLLBACK.sql`
into `output/remediation/mechanical_citations/`. `apply.py --lane orphan-citations` renders the
statement, rehearses it and applies it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

from acceptance.checks import d1  # noqa: E402
from census.tests.t08_citation_markers import _excerpt, entries, marker_sequence  # noqa: E402
from phase4.model4 import CITATIONS_KEY, parse_json, text_sha256  # noqa: E402

from mechanical.apply import lane_dir  # noqa: E402
from mechanical.lane import ORPHAN_CITATIONS  # noqa: E402
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

LANE = ORPHAN_CITATIONS
COLUMN = "raw_data"
RULE_NO_MARKERS = "citations-without-markers"
RULE_UNCITED = "uncited-entries"
MARKER_WITHOUT_ENTRY = "marker-without-entry"
NOT_READABLE = "citations-not-readable"
NOT_REPRINTED = "raw-data-not-reprinted"
#: The census finding each rule repairs.
FINDING = {RULE_NO_MARKERS: "T08/no-markers", RULE_UNCITED: "T08/entry-never-cited"}
EXPORT_KINDS = ("site", "journal")
D1_SOURCE = "scripts/remediation/acceptance/checks.py"
POPUP = "ancient-nerds-map/src/components/SitePopup/sections/DescriptionSection.tsx"

SITES_SQL = (
    "SELECT u.id::text AS site_id, u.name, u.description, u.raw_data::text AS raw_data, "
    f"{LANE.premise_sql} AS premise FROM unified_sites u "
    f"WHERE u.source_id = '{CURATED_SOURCE}' ORDER BY u.id"
)
JOURNAL_SQL = (
    "SELECT l.id, l.row_pk, l.run_stamp, coalesce(l.test_id, '') AS test_id, l.old_value, "
    "l.new_value FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
    "AND l.column_name = 'raw_data' AND l.row_pk IN (SELECT u.id::text FROM unified_sites u "
    f"WHERE u.source_id = '{CURATED_SOURCE}') ORDER BY l.id"
)


# ------------------------------------------------------------------------------ the export
@dataclass(frozen=True)
class Site:
    """One curated row, as the export read it: `raw_data` as Postgres prints it, and the premise
    (`LANE.premise_sql`, the description's sha256) computed by Postgres."""

    site_id: str
    name: str
    description: str | None
    raw_data: str | None
    premise: str


@dataclass(frozen=True)
class Export:
    sites: tuple[Site, ...]
    journal: Mapping[str, tuple[JournalLink, ...]]
    exported_at: str


def export_script() -> str:
    """One read-only snapshot: every curated row, and every `raw_data` journal row of one."""
    return tagged_export_script([("site", SITES_SQL), ("journal", JOURNAL_SQL)])


def parse_export(text: str) -> Export:
    rows, exported_at = parse_tagged_export(text, EXPORT_KINDS)
    journal: dict[str, list[JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault(str(r["row_pk"]), []).append(
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
    return Export(sites, {sid: tuple(links) for sid, links in journal.items()}, exported_at)


def premise_of(description: str | None) -> str:
    """`LANE.premise_sql` in Python: the description's sha256, as the provenance pins it."""
    return text_sha256(description or "")


# ------------------------------------------------------------------------------ the decision
def canonical(text: str | None) -> str | None:
    """A `raw_data` value as the journal chain compares it: JSON with sorted keys."""
    return (
        None if text is None else json.dumps(parse_json(text), ensure_ascii=False, sort_keys=True)
    )


def reprint(value: Any) -> str:
    """A JSON value as Postgres prints jsonb: `', '` and `': '`, UTF-8, keys in the order given."""
    return json.dumps(value, ensure_ascii=False)


def repaired(raw: Mapping[str, Any], markers: set[int]) -> dict[str, Any]:
    """`raw` without the entries no marker cites - without the key when no marker is left."""
    if not markers:
        return {key: value for key, value in raw.items() if key != CITATIONS_KEY}
    return {
        key: [e for e in value if e["n"] in markers] if key == CITATIONS_KEY else value
        for key, value in raw.items()
    }


def _entry(e: Mapping[str, Any]) -> str:
    return f"[{e['n']}] {e.get('title')!r} <{e.get('url')}>" + (
        f" claim {e['claim']!r}" if e.get("claim") else ""
    )


def classify(site: Site, links: Sequence[JournalLink]) -> Verdict | None:
    """One site: None where D1 holds, else its repair or the reason it is listed (module doc)."""
    raw = None if site.raw_data is None else parse_json(site.raw_data)
    citations = raw.get(CITATIONS_KEY) if isinstance(raw, dict) else None
    failure = d1(
        {
            "site_id": site.site_id,
            "description": site.description,
            "description_citations": citations,
        }
    )
    if failure is None:
        return None
    text = site.description or ""
    found = {"source": "acceptance:D1", "url": D1_SOURCE, "quote": failure}

    def listed(reason: str, note: str, *evidence: dict[str, Any]) -> Verdict:
        return Verdict(
            site_id=site.site_id,
            site_name=site.name,
            ok=False,
            old_value=site.raw_data,
            new_value=None,
            rule=reason,
            reason=reason,
            note=note,
            phase3=False,
            finding_test_id="T08",
            evidence=(found, *evidence),
            column=COLUMN,
        )

    try:
        cited_entries = entries(citations, site.site_id)
    except ValueError as exc:
        return listed(NOT_READABLE, f"the citation entries cannot be read: {exc}")
    numbers = [e["n"] for e in cited_entries]
    markers = set(marker_sequence(text))
    unanswered = sorted(markers - set(numbers))
    uncited = sorted(set(numbers) - markers)
    if unanswered:
        return listed(
            MARKER_WITHOUT_ENTRY,
            "the description cites "
            + ", ".join(f"[{n}]" for n in unanswered)
            + f" with no entry (entries {numbers}): the source of a marker is not in the data - "
            "a human adds the entry or removes the marker (HUMAN_ONLY.md D9); nothing of this site "
            "is written"
            + (
                f", not even its entr{'y' if len(uncited) == 1 else 'ies'} "
                f"{', '.join(map(str, uncited))} that no marker cites"
                if uncited
                else ""
            ),
            *(
                {
                    "source": "unified_sites.description",
                    "url": "unified_sites.description",
                    "quote": _excerpt(text, n),
                }
                for n in unanswered
            ),
            {
                "source": "unified_sites.raw_data.description_citations",
                "url": "unified_sites.raw_data",
                "quote": "; ".join(_entry(e) for e in cited_entries),
            },
        )
    broken = journal_break(
        [
            JournalLink(
                link.id,
                link.run_stamp,
                link.test_id,
                canonical(link.old_value),
                canonical(link.new_value),
            )
            for link in links
        ],
        canonical(site.raw_data),
    )
    if broken is not None:
        return listed(*broken)
    if site.raw_data is None or reprint(raw) != site.raw_data:
        return listed(
            NOT_REPRINTED,
            "raw_data is not the text this planner would print for its value: the journal would "
            "record another spelling of the value than the one the row holds",
        )
    rule = RULE_UNCITED if markers else RULE_NO_MARKERS
    removed = [e for e in cited_entries if e["n"] not in markers]
    note = (
        f"entries {uncited} are cited by no marker (the description cites {sorted(markers)}); "
        "they are removed, the cited entries stay byte for byte"
        if markers
        else "the description cites no [N], so its "
        + (
            f"entry {numbers} cites"
            if len(numbers) == 1
            else f"{len(numbers)} entries {numbers} cite"
        )
        + " nothing; the array is removed"
    )
    return Verdict(
        site_id=site.site_id,
        site_name=site.name,
        ok=True,
        old_value=site.raw_data,
        new_value=reprint(repaired(raw, markers)),
        rule=rule,
        reason="",
        note=note + "; the description and the rest of raw_data stay as they are",
        phase3=False,
        finding_test_id=FINDING[rule],
        evidence=(
            found,
            {
                "source": "unified_sites.raw_data.description_citations",
                "url": "remediation_change_log.old_value",
                "quote": "removed: " + "; ".join(_entry(e) for e in removed),
            },
            {
                "source": "unified_sites.description",
                "url": "unified_sites.description",
                "quote": f"markers {sorted(markers)}; sha256 {site.premise} (the premise)",
            },
            {
                "source": POPUP,
                "url": POPUP,
                "quote": "citationSources: every entry becomes a source link with its [n], "
                "whether or not a marker of the text cites it",
            },
        ),
        premise=site.premise,
        column=COLUMN,
    )


def build(export: Export, *, built_at: str) -> Plan:
    """The plan over every curated row, read against the acceptance's own D1 before it is kept."""
    changes: list[Verdict] = []
    skipped: list[Verdict] = []
    holds = 0
    for site in sorted(export.sites, key=lambda s: s.site_id):
        verdict = classify(site, export.journal.get(site.site_id, ()))
        if verdict is None:
            holds += 1
        elif verdict.ok:
            written = json.loads(str(verdict.new_value))
            after = d1(
                {
                    "site_id": site.site_id,
                    "description": site.description,
                    "description_citations": written.get(CITATIONS_KEY),
                }
            )
            if after is not None:
                raise PlanError(f"{site.site_id}: D1 would still fail after the write: {after}")
            changes.append(verdict)
        else:
            skipped.append(verdict)
    counters = Counter(v.rule for v in changes) + Counter(v.reason for v in skipped)
    return Plan(
        changes=tuple(changes),
        skipped=tuple(skipped),
        built_at=built_at,
        counters={
            "curated": len(export.sites),
            "d1_holds": holds,
            "d1_fails": len(changes) + len(skipped),
            **dict(sorted(counters.items())),
        },
        lane=LANE,
    )


# ------------------------------------------------------------------------------ the files
REFUSAL_MEANING = {
    MARKER_WITHOUT_ENTRY: "a marker of the description has no entry: its source is not in the "
    "data - for a human (HUMAN_ONLY.md D9)",
    NOT_READABLE: "the citation entries are not a list of objects with an integer n",
    "journal-chain-broken": "the raw_data journal is not continuous",
    "journal-disagrees": "the raw_data journal does not end at the live value",
    NOT_REPRINTED: "raw_data is not printed the way this planner prints JSON",
}


def write_plan_md(plan: Plan, export: Export, path: Path, *, export_sha256: str) -> None:
    lane = plan.lane
    counters = plan.counters
    add = (lines := []).append
    add(f"# Orphan citation entries - plan ({lane.name})")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/citations.py` from the export "
        f"read at {export.exported_at} (`export/export.jsonl`, sha256 {export_sha256}). Lane "
        f"`{lane.name}`: run stamp `{lane.run_stamp}`, journal test id `{lane.test_id}`, change "
        f"keys `{lane.key_prefix}:<site_id>:raw_data`."
    )
    add("")
    add(
        f"D1 (`acceptance/checks.py`) over **{counters['curated']}** curated rows: holds on "
        f"{counters['d1_holds']}, fails on **{counters['d1_fails']}**. **{len(plan.changes)} "
        f"site(s) will be written** - {counters.get(RULE_NO_MARKERS, 0)} whose description "
        f"cites nothing lose the array, {counters.get(RULE_UNCITED, 0)} lose only the entries no "
        f"marker cites - and **{len(plan.skipped)} are listed, not written.** Each write is "
        "conditioned on the raw_data it read (guard 3) and on the sha256 of the description its "
        "markers were read from (guard 5); D1 holds on every planned value (`build`)."
    )
    add("")
    add("## Written")
    add("")
    add("| site | rule | the note |")
    add("|---|---|---|")
    for change in plan.changes:
        add(f"| {change.site_name} (`{change.site_id}`) | `{change.rule}` | {change.note} |")
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
        for e in v.evidence[1:]:
            add(f"  * {e['source']}: {e['quote']}")
    add("")
    add("## After the apply")
    add("")
    add(
        "Lane L's acceptance reads the rows this lane rewrote as superseded once it is told the "
        f"stamp: `verify_writes4.py --lane p4l ... --complete --allow-stamp '{lane.run_stamp}'`. "
        "The static export on the VPS carries `dc` into `/data/sites/index.json` and must be run "
        "again; the SSR page and the API read the database."
    )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the orphan-citations lane (mechanical)")
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
            write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
            print(json.dumps(dict(plan.counters), indent=1))
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
