# SPDX-License-Identifier: AGPL-3.0-only
"""The INSERT wave: a row for the picture the owner linked by hand.

`chunk_writer` writes conditional UPDATEs through `apply_remediation_change()` (migrations
0017/0018/0022), and its lint refuses an INSERT - so the 326 `no_target_row` sites whose rows exist
but hold no file of the 2025 import could not be given the owner's picture. Measured 2026-10-06 on
the read of run `import-hero-2026-10-06-005`: **326** such sites (289 of them link an
`upload.wikimedia.org` file the fetch can download, 37 link en.wikipedia, UNESCO, a blog or a
Twitter image and stay refused), and 150 more whose sites carry no image row at all - those stay
with the owner's 2026-10-05 decision (18:32): a site with only a `thumbnail_url` gets no gallery
image made up out of nothing.

**No migration is needed.** The journal's own columns carry an insert: one row per column the
statement writes, with `old_value` NULL and `new_value` what the created row actually holds,
`row_pk` the new row's `id` from `RETURNING`, and the lane's `change_key`. The write and its journal
rows happen in one transaction, so a journal that disagrees with the data cannot be committed.

That is fourteen columns per row, not eleven: `wiki_images` declares `is_lead`, `sort_order` and
`source_type` NOT NULL without a default (measured 2026-10-06), so the statement has to write them
too, and a journal that left them out would not describe the write. `sort_order` is derived - the
next free number of that site - never invented; `is_lead` stays false, because the import's link is
the owner's picture and not a measured lead image of the article; `source_type` is `wikimedia`,
which 49,683 of the 49,691 curated rows carry.

The guards are the shared writer's, restated for a row that must not exist yet:

1. every planned site is a curated, shown site;
2. no row of that site holds the file (`original_url`) - so a re-run inserts nothing instead of a
   second copy, and the unique constraint `(site_id, original_url)` is a second line of defence;
3. the file is at least 1600x900, the floor `plan.py` applies everywhere else;
4. the row that holds the hero flag is still the one the plan demotes;
5. the site's `thumbnail_url` still holds the value the read found.

The reversal is a guarded DELETE, not a truncation: the row is named by `(site_id, original_url,
file_size_bytes)` - the triple this lane wrote - and the demotion and the thumbnail go back to the
values the plan recorded. `unified_sites` is never deleted from; its site-owned tables stay behind
their `CASCADE`.

`image_kind` stays NULL on the new row, which is the honest value: no vision model has looked at it.
That is not a serving gate (`pipeline/utils/public_sites.py` names `image_kind` as a column the
page does not show), and NULL is what the 310 rows of the hero wave carry today.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation", _HERE.parent.parent):
    if str(_path) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(_path))

from hero_repair.thumbnail import local_path  # noqa: E402
from served_image import state as ST  # noqa: E402

from import_hero import verify as IV  # noqa: E402
from import_hero.plan import (  # noqa: E402
    CURATED_SOURCE,
    FETCH_COLUMNS,
    HERO_MIN_HEIGHT,
    HERO_MIN_WIDTH,
    ImportHeroError,
)

#: The columns the fetch manifest carries, in the order the row is written. `filename` first: it
#: names the file, and the rest credit it (owner decision 2026-10-05, 17:43).
INSERT_COLUMNS = FETCH_COLUMNS

#: How `wiki_images` holds the file's numbers, measured on production 2026-10-06
#: (`information_schema.columns`): `width`, `height`, `file_size_bytes` and `id` are all
#: `integer`. The temp table has to use the same types - as text, guard 3 would compare '800' with
#: '900' lexicographically and invariant 1 would compare an integer with a text.
NUMERIC_TYPES = {"width": "INTEGER", "height": "INTEGER", "file_size_bytes": "INTEGER"}

#: The three columns `wiki_images` declares NOT NULL without a default and that the fetch does not
#: carry (measured 2026-10-06, `information_schema.columns`): `is_lead`, `sort_order` and
#: `source_type`. An INSERT that leaves them out does not land, so the statement has to write them:
#: `is_lead` false (the import's link is the owner's picture, not a measured lead image of the
#: article), `sort_order` the next free number of that site (derived, never invented) and
#: `source_type` 'wikimedia' - 49,683 of the 49,691 curated rows carry it, the 8 others 'manual'.
STRUCTURAL_COLUMNS = ("is_lead", "sort_order", "source_type")
SOURCE_TYPE = "wikimedia"

#: One journal row per column this lane writes on the new row: the file's eleven plus the three
#: above. The journal has to carry every write or the reversal is not complete.
JOURNAL_COLUMNS = (*INSERT_COLUMNS, *STRUCTURAL_COLUMNS)

#: The journal's own identity, as the hero wave of this lane wrote it (measured 2026-10-06 in
#: `remediation_change_log`): `test_id` names the decision, `confidence` stays inside 0017's
#: vocabulary.
LANE_TEST_ID = "import-hero/insert/owner-2026-10-05"
LANE_CONFIDENCE = "authoritative"

#: What this lane calls itself in the journal's `change_key`, like every other lane's name.
LANE = "import-hero/insert"
LANE_LABEL = "ih6"

#: The line both statements end with, so `--rehearse` recognises the run the way the shared
#: writer's does (`chunk_writer.READBACK_LABEL`).
READBACK_LABEL = "journal rows for this run"


@dataclass(frozen=True)
class Insert:
    """One row this wave creates, plus the two updates it makes in the same transaction."""

    site_id: str
    demoted_id: str | None
    old_thumbnail: str | None
    new_thumbnail: str
    change_key: str
    reason: str
    evidence: list[dict[str, Any]]
    values: dict[str, str]

    def as_json(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "values": dict(self.values),
            "demoted_id": self.demoted_id,
            "old_thumbnail": self.old_thumbnail,
            "new_thumbnail": self.new_thumbnail,
            "change_key": self.change_key,
            "reason": self.reason,
            "evidence": self.evidence,
        }

    @classmethod
    def from_json(cls, record: Mapping[str, Any]) -> Insert:
        return cls(
            site_id=str(record["site_id"]),
            demoted_id=record.get("demoted_id"),
            old_thumbnail=record.get("old_thumbnail"),
            new_thumbnail=str(record["new_thumbnail"]),
            change_key=str(record["change_key"]),
            reason=str(record["reason"]),
            evidence=list(record.get("evidence") or ()),
            values={str(k): str(v) for k, v in dict(record["values"]).items()},
        )

    @property
    def filename(self) -> str:
        return self.values["filename"]

    @property
    def thumbnail_changes(self) -> bool:
        return self.old_thumbnail != self.new_thumbnail

    @property
    def journal_rows(self) -> int:
        """What the journal must carry for this site: one per column the statement writes on the new
        row, the demotion and the thumbnail - the last only when the plan changes it."""
        return (
            len(JOURNAL_COLUMNS)
            + (1 if self.demoted_id else 0)
            + (1 if self.thumbnail_changes else 0)
        )


@dataclass(frozen=True)
class Refusal:
    """A site this wave will not touch, and the reason in words."""

    site_id: str
    reason: str
    detail: str

    def as_json(self) -> dict[str, Any]:
        return {"site_id": self.site_id, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class InsertPlan:
    inserts: list[Insert]
    refusals: list[Refusal] = field(default_factory=list)

    @property
    def sites(self) -> list[str]:
        return [row.site_id for row in self.inserts]

    def as_json(self) -> dict[str, Any]:
        from collections import Counter

        by_reason = Counter(refusal.reason for refusal in self.refusals)
        return {
            "planned_rows": len(self.inserts),
            "planned_sites": len(self.inserts),
            "refused_sites": len(self.refusals),
            "refusals": dict(by_reason),
        }


def _hero_row(state: ST.State, site_id: str) -> Mapping[str, Any] | None:
    """The row of this site the gallery shows with the flag, if there is one."""
    heroes = IV.live_heroes(state.rows.get(site_id, ()))
    return heroes[0] if heroes else None


def _shows_a_picture_of_its_own(site: Mapping[str, Any]) -> bool:
    """Whether the page shows something without a gallery row: the `thumbnail_url` the read holds.

    This is where the owner's two decisions meet. On 2026-10-05 (18:32) a site with no row kept its
    `thumbnail_url` and got no gallery row - the picture it already shows is the picture, and a row
    would have replaced it. That reason holds only where such a `thumbnail_url` exists. Measured on
    the read `b053ac17` (2026-10-06, 4,900 shown sites): 1,144 sites have neither a row nor a
    `thumbnail_url`, so they show nothing at all, and for those the owner allowed the first row on
    2026-10-06 after the candidate search confirmed a picture of 9 of them in one wave.
    """
    return bool(str(site.get("thumbnail_url") or "").strip())


def seed_from_import_run(
    source_run: Path,
    insert_run: Path,
    sites: Sequence[str],
) -> dict[str, Any]:
    """This INSERT wave's own two records, taken out of an import run for the sites named.

    `fetch --target insert` reads `IMPORT_CLAIMS.json` and `IMPORT_HERO_REFUSALS.jsonl` out of the run
    directory, and `insert-plan` reads the refusals. The 2025 import wrote both - but into its own run
    directories, over its own target list. So a wave over the sites that show nothing although the
    import links a picture has nothing to read, and would end in an empty plan with no refusal naming
    anything. This writes the two records from the run that has them, for the sites the caller names.

    **Only sites the source run refused as `no_target_row` are seeded.** Every other refusal of that
    run means the import's file was refused for another reason - too small, no credit, no rendering -
    and copying its claim into a wave would turn that refusal into a written row.

    Claims are **merged, never replaced**, exactly as `candidate_search.judge.insert_claims` does it:
    a site this run already claims keeps its URL, and a second claim for one site is refused by name
    rather than silently overwriting the first. The refusal carries a `source` and an
    `evidence_source` that name the run the claim came out of, because the row this produces is
    journalled with both and they must not read as if the 2025 import had asked for it in this wave.
    """
    claims_path = source_run / "IMPORT_CLAIMS.json"
    refusals_path = source_run / "IMPORT_HERO_REFUSALS.jsonl"
    if not claims_path.is_file():
        raise ImportHeroError(
            f"{claims_path} does not exist - the source run has no claims to seed from"
        )
    if not refusals_path.is_file():
        raise ImportHeroError(
            f"{refusals_path} does not exist - the source run has no refusals to seed from"
        )

    source_claims = json.loads(claims_path.read_text(encoding="utf-8"))
    source_refusals = {
        str(row.get("site_id") or ""): row
        for row in (
            json.loads(line)
            for line in refusals_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    out_claims_path = insert_run / "IMPORT_CLAIMS.json"
    out_refusals_path = insert_run / "IMPORT_HERO_REFUSALS.jsonl"
    claims: dict[str, Any] = (
        json.loads(out_claims_path.read_text(encoding="utf-8")) if out_claims_path.is_file() else {}
    )
    refusals: list[dict[str, Any]] = (
        [
            json.loads(line)
            for line in out_refusals_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if out_refusals_path.is_file()
        else []
    )
    refused_sites = {str(row.get("site_id") or "") for row in refusals}

    seeded = 0
    out_refusals: list[dict[str, str]] = []
    for site_id in sites:
        site_id = str(site_id).strip()
        if not site_id:
            continue
        claim = source_claims.get(site_id)
        if claim is None:
            out_refusals.append(
                {
                    "site_id": site_id,
                    "reason": "no_import_claim",
                    "detail": (
                        f"{site_id}: {source_run.name} records no claim for this site, so the wave "
                        f"has no picture to fetch for it"
                    ),
                }
            )
            continue
        refusal = source_refusals.get(site_id)
        if refusal is None or str(refusal.get("reason")) != "no_target_row":
            reason = (refusal or {}).get("reason") or "not_refused"
            out_refusals.append(
                {
                    "site_id": site_id,
                    "reason": "not_a_candidate",
                    "detail": (
                        f"{site_id}: {source_run.name} refused this site as {reason!r}, not as "
                        f"'no_target_row'; only a site whose rows hold no file of the import can "
                        f"gain one here"
                    ),
                }
            )
            continue
        url = str(claim.get("image") or "")
        if ST.file_of_url(url) is None:
            out_refusals.append(
                {
                    "site_id": site_id,
                    "reason": "unreadable_url",
                    "detail": f"{site_id}: {url!r} names no Commons file",
                }
            )
            continue
        if site_id in claims:
            if str(claims[site_id].get("image") or "") != url:
                out_refusals.append(
                    {
                        "site_id": site_id,
                        "reason": "claim_conflict",
                        "detail": (
                            f"{site_id}: the run already claims "
                            f"{claims[site_id].get('image')!r}, {source_run.name} brings {url!r}"
                        ),
                    }
                )
            continue

        claims[site_id] = dict(claim)
        if site_id not in refused_sites:
            refusals.append(
                {
                    "site_id": site_id,
                    "reason": "no_target_row",
                    "detail": (
                        f"the 2025 import links {url!r} for this site and no row of it holds the "
                        f"file: {refusal.get('detail') or ''}".strip()
                    ),
                    "source": (
                        f"the 2025 import's own link for this site, recorded as {url!r} in "
                        f"{source_run.name}/IMPORT_CLAIMS.json; the site showed nothing at all - no "
                        "gallery row and no thumbnail_url (owner decision 2026-10-06)"
                    ),
                    "evidence_source": (
                        f"the import run {source_run.name}, which refused this site as "
                        "'no_target_row' because its rows hold no file of the import"
                    ),
                }
            )
            refused_sites.add(site_id)
        seeded += 1

    insert_run.mkdir(parents=True, exist_ok=True)
    out_claims_path.write_text(
        json.dumps(claims, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    out_refusals_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in refusals),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "source_run": str(source_run),
        "insert_run": str(insert_run),
        "sites_seeded": seeded,
        "claims_total": len(claims),
        "refusals_total": len(refusals),
        "refused_sites": out_refusals,
    }


def plan(
    state: ST.State,
    refusals: Sequence[Mapping[str, Any]],
    *,
    fetched: Mapping[str, Mapping[str, str]],
) -> InsertPlan:
    """The rows the wave would create, and the sites it refuses by name.

    Only `no_target_row` refusals are candidates, and only those the fetch actually delivered: a
    row cannot name a file that is not on disk, so a site whose fetch was refused stays refused with
    that reason rather than receiving a row that points nowhere.
    """
    inserts: list[Insert] = []
    out: list[Refusal] = []
    for refusal in refusals:
        if str(refusal.get("reason")) != "no_target_row":
            continue
        site_id = str(refusal.get("site_id") or "")
        site = state.sites.get(site_id)
        if site is None:
            out.append(Refusal(site_id, "retired", "the site is not in the read"))
            continue
        rows = state.rows.get(site_id, ())
        if not rows and _shows_a_picture_of_its_own(site):
            out.append(
                Refusal(
                    site_id,
                    "no_row_at_all",
                    "the site carries no image row at all but shows a thumbnail_url of its own: the "
                    "owner decided on 2026-10-05 (18:32) that such a site keeps its thumbnail_url "
                    "and gets no gallery row",
                )
            )
            continue
        entry = fetched.get(site_id)
        if entry is None:
            out.append(
                Refusal(
                    site_id,
                    "not_fetched",
                    "the 1600 px file of the import's picture has not been fetched, so a row "
                    "would name a file that is not there",
                )
            )
            continue
        values = {column: str(entry[column]) for column in INSERT_COLUMNS}
        # the read's own twin of guard 2: a site that already holds the file needs no row, and an
        # insert for it would be refused by the unique constraint (site_id, original_url). Measured
        # 2026-10-06: 3 of the 90 planned rows, whose import link carries a different Commons slug
        # than the stored row (`pf` for `of`, a `Mount Nemrut -` prefix) - the hero lane moves the
        # flag onto that row instead.
        held = next(
            (
                str(row["id"])
                for row in rows
                if str(row.get("original_url") or "") == values["original_url"]
            ),
            None,
        )
        if held is not None:
            out.append(
                Refusal(
                    site_id,
                    "already_holds_the_file",
                    f"row {held} of this site already holds {values['original_url']}: the row "
                    "exists, so this wave creates nothing - the hero lane moves the flag onto it",
                )
            )
            continue
        hero = _hero_row(state, site_id)
        thumb = site.get("thumbnail_url")
        # The row's reason is read out of the refusal that named this site, because the refusal is
        # the run's own record of *why* the file is wanted - and a wave built from something other
        # than the 2025 import must not sign its journal rows with the import's name. Only a
        # refusal that names a source of its own overrides the import's wording.
        source = str(refusal.get("source") or "")
        inserts.append(
            Insert(
                site_id=site_id,
                demoted_id=str(hero["id"]) if hero else None,
                old_thumbnail=str(thumb) if thumb else None,
                new_thumbnail=local_path(site_id, values["filename"]),
                change_key=f"{LANE}:{site_id}",
                reason=source
                or (
                    "the 2025 import links this file for the site and no row of it holds the file; "
                    "the owner's decision of 2026-10-05 (17:43) is that the import's image is the "
                    "hero"
                ),
                evidence=[
                    {
                        "source": str(refusal.get("evidence_source") or "")
                        or "the 2025 import's own link (ancient_nerds_original.geojson)",
                        "url": str(entry.get("commons_page_url") or ""),
                        "quote": values["original_url"],
                    },
                    {
                        "source": "the plan's read of production",
                        "url": f"wiki_images WHERE site_id = {site_id}",
                        "quote": (
                            f"{len(rows)} row(s) of this site, none holding {values['original_url']}"
                        ),
                    },
                ],
                values=values,
            )
        )
    return InsertPlan(inserts=inserts, refusals=out)


# --------------------------------------------------------------------------- the statement
def _literal(value: Any) -> str:
    """A SQL literal: strings quoted, None as the keyword, numbers bare."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _temp_columns() -> str:
    """The temp table's columns: the file's eleven, then what the statement needs besides them.

    Each column is declared exactly once and in the type `wiki_images` holds it: naming `width`
    twice - once from `INSERT_COLUMNS`, once because guard 3 needs a number - made the statement
    fail with `column "width" specified more than once` before it wrote anything (measured
    2026-10-06, while the fetch of the INSERT wave was still running).
    """
    parts = ["    seq               INTEGER PRIMARY KEY", "    site_id           UUID NOT NULL"]
    for column in INSERT_COLUMNS:
        parts.append(f"    {column:<17} {NUMERIC_TYPES.get(column, 'TEXT')} NOT NULL")
    parts += [
        "    demoted_id        INTEGER",
        "    old_thumbnail     TEXT",
        "    new_thumbnail     TEXT NOT NULL",
        "    change_key        TEXT NOT NULL",
        "    reason            TEXT NOT NULL",
        "    evidence          JSONB NOT NULL",
    ]
    return ",\n".join(parts)


def _plan_columns() -> str:
    """The `VALUES` list of the temp table, in the order `_temp_columns` declares."""
    return ", ".join(
        (
            "seq",
            "site_id",
            *INSERT_COLUMNS,
            "demoted_id",
            "old_thumbnail",
            "new_thumbnail",
            "change_key",
            "reason",
            "evidence",
        )
    )


def _tuples(inserts: Sequence[Insert]) -> str:
    """One row per site, with exactly one value per column of `_plan_columns`."""
    lines = []
    for seq, row in enumerate(inserts, start=1):
        values = [
            str(int(row.values[column]))
            if column in NUMERIC_TYPES
            else _literal(row.values[column])
            for column in INSERT_COLUMNS
        ]
        lines.append(
            f"    ({seq}, {_literal(row.site_id)}::uuid, {', '.join(values)}, "
            f"{_literal(int(row.demoted_id) if row.demoted_id else None)}, "
            f"{_literal(row.old_thumbnail)}, {_literal(row.new_thumbnail)}, "
            f"{_literal(row.change_key)}, {_literal(row.reason)}, "
            f"{_literal(json.dumps(row.evidence, ensure_ascii=False, sort_keys=True))}::jsonb)"
        )
    return ",\n".join(lines)


def _journal_values() -> str:
    """One value row per written column, read back from the row the INSERT created.

    The value is the column itself (`w.filename::text`), never the text of a name - a journal that
    recorded the string `r.filename` would pass every count in invariant 3 and mean nothing.
    `LATERAL` is what lets the row `w` be named inside the `VALUES` list.
    """
    return ",\n".join(
        f"              ({_literal(column)}, w.{column}::text)" for column in JOURNAL_COLUMNS
    )


def _undo_tuples(inserts: Sequence[Insert]) -> str:
    """The reversal's value rows: the triple this lane wrote, plus what it has to put back."""
    rows = []
    for seq, row in enumerate(inserts, start=1):
        rows.append(
            "    ({seq}, {site}::uuid, {url}, {size}, {demoted}, {old}, {new}, {key})".format(
                seq=seq,
                site=_literal(row.site_id),
                url=_literal(row.values["original_url"]),
                size=_literal(int(row.values["file_size_bytes"])),
                demoted=_literal(int(row.demoted_id) if row.demoted_id else None),
                old=_literal(row.old_thumbnail),
                new=_literal(row.new_thumbnail),
                key=_literal(row.change_key),
            )
        )
    return ",\n".join(rows)


def render_apply(inserts: Sequence[Insert], run_stamp: str, *, digest: str) -> str:
    """APPLY.sql of one chunk: the guards, then the row and its journal in one transaction."""
    stamp = _literal(run_stamp)
    insert_columns = ", ".join(INSERT_COLUMNS)
    return f"""-- Generated by scripts/remediation/import_hero/insert.py - do not edit by hand.
-- pin: {digest}
-- lane {LANE_LABEL!r} ({LANE}), {len(inserts)} row(s) to create; run stamp {run_stamp!r}.
-- Every row is created together with its journal rows, inside this transaction: a journal that
-- disagrees with the data cannot be committed, and a rolled-back statement leaves nothing behind.
\\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE _ih_insert (
{_temp_columns()}
) ON COMMIT DROP;

INSERT INTO _ih_insert ({_plan_columns()}) VALUES
{_tuples(inserts)};

DO $$
DECLARE
    bad  integer;
    r    RECORD;
    new_id integer;
    cols TEXT;
BEGIN
    -- guard 1: every planned site is a curated site (the message names the source in words, so
    -- the log of a refused wave says what was expected)
    SELECT count(*) INTO bad FROM (SELECT DISTINCT site_id FROM _ih_insert) p
      LEFT JOIN unified_sites u ON u.id = p.site_id
     WHERE u.id IS NULL OR u.source_id <> {_literal(CURATED_SOURCE)};
    IF bad > 0 THEN
        RAISE EXCEPTION '%: % planned site(s) are not {CURATED_SOURCE} sites',
            {_literal(run_stamp)}, bad;
    END IF;

    FOR r IN SELECT * FROM _ih_insert ORDER BY seq LOOP
        -- guard 2: no row of this site holds the file yet. The unique constraint on
        -- (site_id, original_url) is a second line of defence behind this one.
        IF EXISTS (SELECT 1 FROM wiki_images w
                    WHERE w.site_id = r.site_id AND w.original_url = r.original_url) THEN
            RAISE EXCEPTION '%: site % already holds this file', r.change_key, r.site_id;
        END IF;

        -- guard 3: the file reaches the hero floor
        IF r.width < {HERO_MIN_WIDTH} OR r.height < {HERO_MIN_HEIGHT} THEN
            RAISE EXCEPTION '%: the file is %x%, under the %x% this lane serves', r.change_key,
                r.width, r.height, {HERO_MIN_WIDTH}, {HERO_MIN_HEIGHT};
        END IF;

        -- guard 4: the row that holds the flag is still the one the plan demotes
        IF r.demoted_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM wiki_images w
             WHERE w.id = r.demoted_id AND w.site_id = r.site_id AND w.is_hero) THEN
            RAISE EXCEPTION '%: the row that held the flag for site % moved since the read',
                r.change_key, r.site_id;
        END IF;

        -- guard 5: the thumbnail still holds the value the read found
        IF (SELECT u.thumbnail_url FROM unified_sites u WHERE u.id = r.site_id)
           IS DISTINCT FROM r.old_thumbnail THEN
            RAISE EXCEPTION '%: the thumbnail of site % moved since the read', r.change_key, r.site_id;
        END IF;

        -- the row that gives up the flag, and the row that takes it
        IF r.demoted_id IS NOT NULL THEN
            UPDATE wiki_images SET is_hero = false
             WHERE id = r.demoted_id AND is_hero AND site_id = r.site_id;
        END IF;

        -- the three columns the file does not carry: the next free number of this site (derived,
        -- never invented), the owner's picture rather than a measured lead image of the article,
        -- and the source 49,683 of the 49,691 curated rows carry
        INSERT INTO wiki_images
            (site_id, {insert_columns}, is_lead, sort_order, source_type, is_hero, is_excluded)
        SELECT r.site_id, {", ".join(f"r.{column}" for column in INSERT_COLUMNS)}, false,
               (SELECT COALESCE(MAX(w2.sort_order), -1) + 1 FROM wiki_images w2
                 WHERE w2.site_id = r.site_id),
               {_literal(SOURCE_TYPE)}, true, false
        RETURNING id INTO new_id;

        IF r.new_thumbnail IS DISTINCT FROM r.old_thumbnail THEN
            UPDATE unified_sites SET thumbnail_url = r.new_thumbnail WHERE id = r.site_id;
        END IF;

        -- the journal, in this transaction: one row per column this statement wrote,
        -- read back from the row it created, so the journal records what the database holds
        INSERT INTO remediation_change_log
            (run_stamp, test_id, table_name, column_name, row_pk, old_value, new_value, change_key,
             confidence, evidence, site_id_ref)
        SELECT {stamp}, {_literal(LANE_TEST_ID)}, 'wiki_images', t.col, new_id::text, NULL, t.val,
               r.change_key || ':' || t.col, {_literal(LANE_CONFIDENCE)}, r.evidence, r.site_id
          FROM wiki_images w
          CROSS JOIN LATERAL (VALUES
{_journal_values()}
          ) AS t(col, val)
         WHERE w.id = new_id;

        IF r.demoted_id IS NOT NULL THEN
            INSERT INTO remediation_change_log
                (run_stamp, test_id, table_name, column_name, row_pk, old_value, new_value,
                 change_key, confidence, evidence, site_id_ref)
            VALUES ({stamp}, {_literal(LANE_TEST_ID)}, 'wiki_images', 'is_hero',
                    r.demoted_id::text, 'true', 'false', r.change_key || ':demote',
                    {_literal(LANE_CONFIDENCE)}, r.evidence, r.site_id);
        END IF;

        IF r.new_thumbnail IS DISTINCT FROM r.old_thumbnail THEN
            INSERT INTO remediation_change_log
                (run_stamp, test_id, table_name, column_name, row_pk, old_value, new_value,
                 change_key, confidence, evidence, site_id_ref)
            VALUES ({stamp}, {_literal(LANE_TEST_ID)}, 'unified_sites', 'thumbnail_url',
                    r.site_id::text, r.old_thumbnail, r.new_thumbnail,
                    r.change_key || ':thumbnail', {_literal(LANE_CONFIDENCE)}, r.evidence, r.site_id);
        END IF;
    END LOOP;

    -- invariant 1: every planned row stands, with the planned values, the flag and the three
    -- columns the statement derived for it. The temp table is aliased `p`, never `r`: the loop
    -- variable of this block is `r`, and Postgres refuses a reference that could mean either
    -- (measured 2026-10-06, in the rehearsal of chunk-001).
    SELECT count(*) INTO bad FROM _ih_insert p
      LEFT JOIN wiki_images w ON w.site_id = p.site_id AND w.original_url = p.original_url
     WHERE w.id IS NULL OR w.is_hero IS NOT TRUE OR w.is_excluded IS NOT FALSE
        OR w.width IS DISTINCT FROM p.width OR w.height IS DISTINCT FROM p.height
        OR w.file_size_bytes IS DISTINCT FROM p.file_size_bytes
        OR w.filename IS DISTINCT FROM p.filename OR w.original_url IS DISTINCT FROM p.original_url
        OR w.is_lead IS NOT FALSE OR w.source_type IS DISTINCT FROM {_literal(SOURCE_TYPE)}
        OR w.sort_order <> (SELECT COALESCE(MAX(w3.sort_order), 0) FROM wiki_images w3
                             WHERE w3.site_id = p.site_id);
    IF bad > 0 THEN
        RAISE EXCEPTION '%: % inserted row(s) do not stand as planned', {_literal(run_stamp)}, bad;
    END IF;

    -- invariant 2: at most one live hero per touched site (T09's invariant)
    SELECT count(*) INTO bad FROM (
        SELECT w.site_id FROM wiki_images w
          JOIN _ih_insert p ON p.site_id = w.site_id
         WHERE w.is_hero AND w.is_excluded IS NOT TRUE
         GROUP BY w.site_id HAVING count(*) > 1) d;
    IF bad > 0 THEN
        RAISE EXCEPTION '%: % touched site(s) hold more than one live hero row',
            {_literal(run_stamp)}, bad;
    END IF;

    -- invariant 3: the journal carries every write, and nothing else
    SELECT count(*) INTO bad FROM _ih_insert p
      LEFT JOIN (SELECT site_id_ref, count(*) AS n FROM remediation_change_log
                  WHERE run_stamp = {stamp} GROUP BY site_id_ref) l
        ON l.site_id_ref = p.site_id
     WHERE COALESCE(l.n, 0) <> {len(JOURNAL_COLUMNS)}
        + CASE WHEN p.demoted_id IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN p.new_thumbnail IS DISTINCT FROM p.old_thumbnail THEN 1 ELSE 0 END;
    IF bad > 0 THEN
        RAISE EXCEPTION '%: % site(s) do not have exactly their planned journal rows',
            {_literal(run_stamp)}, bad;
    END IF;
END $$;

-- the same two read-back lines the shared writer ends with, so `--rehearse` recognises the run
SELECT '{READBACK_LABEL}', count(*)::text FROM remediation_change_log WHERE run_stamp = {stamp};
SELECT 'planned rows', count(*)::text FROM _ih_insert;
COMMIT;
"""


def render_rollback(inserts: Sequence[Insert], run_stamp: str, *, digest: str) -> str:
    """ROLLBACK.sql of one chunk: a guarded DELETE of exactly the rows this wave created."""
    stamp = _literal(run_stamp)
    undo_tuples = _undo_tuples(inserts)
    return f"""-- Generated by scripts/remediation/import_hero/insert.py - do not edit by hand.
-- pin: {digest}
-- The reversal of lane {LANE_LABEL!r}: the rows this wave created go back out, the flag returns to
-- the row that held it, and the thumbnail returns to the value the read found.
-- The row is named by the triple this lane wrote - (site_id, original_url, file_size_bytes) - so
-- the statement cannot delete a row somebody else created.
\\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE _ih_uninsert (
    seq               INTEGER PRIMARY KEY,
    site_id           UUID NOT NULL,
    original_url      TEXT NOT NULL,
    file_size_bytes   INTEGER NOT NULL,
    demoted_id        INTEGER,
    old_thumbnail     TEXT,
    new_thumbnail     TEXT,
    change_key        TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _ih_uninsert VALUES
{undo_tuples};

DO $$
DECLARE
    bad integer;
BEGIN
    -- every named row is still the one this wave created
    SELECT count(*) INTO bad FROM _ih_uninsert r
      LEFT JOIN wiki_images w
        ON w.site_id = r.site_id AND w.original_url = r.original_url
       AND w.file_size_bytes = r.file_size_bytes
     WHERE w.id IS NULL;
    IF bad > 0 THEN
        RAISE EXCEPTION 'rollback %: % row(s) this wave created are not there to undo',
            {_literal(run_stamp)}, bad;
    END IF;

    DELETE FROM wiki_images w USING _ih_uninsert r
     WHERE w.site_id = r.site_id AND w.original_url = r.original_url
       AND w.file_size_bytes = r.file_size_bytes;

    UPDATE wiki_images w SET is_hero = true
      FROM _ih_uninsert r
     WHERE r.demoted_id IS NOT NULL AND w.id = r.demoted_id AND w.is_hero IS NOT TRUE;

    UPDATE unified_sites u SET thumbnail_url = r.old_thumbnail
      FROM _ih_uninsert r
     WHERE u.id = r.site_id AND r.new_thumbnail IS DISTINCT FROM r.old_thumbnail
       AND u.thumbnail_url IS DISTINCT FROM r.old_thumbnail;

    -- the journal goes with the write it describes
    DELETE FROM remediation_change_log l USING _ih_uninsert r
     WHERE l.run_stamp = {stamp} AND l.change_key LIKE r.change_key || '%';
END $$;

SELECT '{READBACK_LABEL}', count(*)::text FROM remediation_change_log WHERE run_stamp = {stamp};
SELECT 'rows this chunk created',
       count(*)::text
  FROM wiki_images w
  JOIN _ih_uninsert r ON w.site_id = r.site_id AND w.original_url = r.original_url
                    AND w.file_size_bytes = r.file_size_bytes;
COMMIT;
"""


def lint_statement(sql: str, kind: str = "apply") -> None:
    """Refuse anything but this lane's shape, the way `chunk_writer.lint_statement` does.

    Two shapes, two sets of rules. An *apply* creates the row and its journal inside one
    transaction; a *rollback* deletes exactly that row and its journal again. What matters in both:
    the journal moves inside the transaction - a rolled-back row must not keep its record and a
    deleted row must not keep one either - and a DELETE names the row by the triple this lane wrote.

    `COMMIT` is matched as a statement, never as the word: `ON COMMIT DROP` is not the end of the
    transaction, and reading it as one refused this lane's own SQL on the first run (2026-10-06).
    """
    if kind not in ("apply", "rollback"):
        raise ImportHeroError(f"unknown statement kind {kind!r}")
    code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    begins = list(re.finditer(r"(?im)^BEGIN;\s*$", code))
    commits = list(re.finditer(r"(?im)^COMMIT;\s*$", code))
    if len(begins) != 1 or len(commits) != 1:
        raise ImportHeroError(
            f"the statement must open and close exactly one transaction, found {len(begins)} "
            f"BEGIN and {len(commits)} COMMIT"
        )
    if kind == "apply":
        if "INSERT INTO wiki_images" not in code:
            raise ImportHeroError("the statement creates no wiki_images row")
        if "DELETE" in code:
            raise ImportHeroError("an apply creates rows and deletes none")
    else:
        if "INSERT INTO wiki_images" in code:
            raise ImportHeroError("a rollback creates no row")
        if "DELETE FROM wiki_images" not in code:
            raise ImportHeroError("the reversal deletes no wiki_images row")
        if "file_size_bytes = r.file_size_bytes" not in code:
            raise ImportHeroError("a DELETE must name the row by the triple this lane wrote")
    journal = (
        "INSERT INTO remediation_change_log"
        if kind == "apply"
        else "DELETE FROM remediation_change_log"
    )
    if journal not in code:
        raise ImportHeroError(
            "the statement writes no journal row"
            if kind == "apply"
            else "the reversal takes the row away and leaves its journal rows behind"
        )
    if code.index(journal) > commits[0].start():
        raise ImportHeroError("the journal rows must be written before the COMMIT")
    touched = [
        code.index(statement)
        for statement in ("INSERT INTO wiki_images", "DELETE FROM wiki_images")
        if statement in code
    ]
    if not touched or begins[0].start() > min(touched):
        raise ImportHeroError("the rows must be written inside the transaction")
    for forbidden in ("TRUNCATE", "DROP TABLE", "DELETE FROM unified_sites"):
        if forbidden in code:
            raise ImportHeroError(f"{forbidden} is not a statement this lane may make")


def digest_of(inserts: Iterable[Insert]) -> str:
    """The plan's digest, over the rows themselves - the pin every chunk carries."""
    payload = json.dumps(
        [row.as_json() for row in inserts], ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- the chunks
@dataclass(frozen=True)
class InsertChunk:
    stamp: str
    number: int
    inserts: list[Insert]

    @property
    def run_stamp(self) -> str:
        """One journal stamp per chunk, as the shared writer numbers them: measured 2026-10-06 in
        `remediation_change_log`, the hero wave's five chunks carry `…-005-001` … `…-005-004`. A
        stamp without the number would let a second chunk's read-back see the first one's rows."""
        return f"{self.stamp}-{self.number:03d}"

    @property
    def rollback_stamp(self) -> str:
        return f"{self.run_stamp}-rollback"

    @property
    def digest(self) -> str:
        return digest_of(self.inserts)

    def apply_sql(self) -> str:
        sql = render_apply(self.inserts, self.run_stamp, digest=self.digest)
        lint_statement(sql)
        return sql

    def rollback_sql(self) -> str:
        sql = render_rollback(self.inserts, self.run_stamp, digest=self.digest)
        lint_statement(sql, kind="rollback")
        return sql


def chunks_of(plan_rows: InsertPlan, run_stamp: str, per_chunk: int = 50) -> list[InsertChunk]:
    if not plan_rows.inserts:
        raise ImportHeroError(
            "the plan holds no row: the wave would write nothing, and an empty chunk directory is "
            "not a record of that"
        )
    if per_chunk < 1:
        raise ImportHeroError(f"per_chunk = {per_chunk} makes no chunk")
    return [
        InsertChunk(
            stamp=run_stamp,
            number=number,
            inserts=list(plan_rows.inserts[start : start + per_chunk]),
        )
        for number, start in enumerate(range(0, len(plan_rows.inserts), per_chunk), start=1)
    ]


def write_chunks(plan_rows: InsertPlan, run: Path, *, per_chunk: int = 50) -> list[InsertChunk]:
    """`INSERT.jsonl`, `APPLY.sql`, `ROLLBACK.sql` and `CHUNK.json` per chunk, and the summary."""
    chunks = chunks_of(plan_rows, run.name, per_chunk=per_chunk)
    run.mkdir(parents=True, exist_ok=True)
    for chunk in chunks:
        directory = run / f"chunk-{chunk.number:03d}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "INSERT.jsonl").write_text(
            "".join(
                json.dumps(row.as_json(), ensure_ascii=False, sort_keys=True) + "\n"
                for row in chunk.inserts
            ),
            encoding="utf-8",
            newline="\n",
        )
        (directory / "APPLY.sql").write_text(chunk.apply_sql(), encoding="utf-8", newline="\n")
        (directory / "ROLLBACK.sql").write_text(
            chunk.rollback_sql(), encoding="utf-8", newline="\n"
        )
        (directory / "CHUNK.json").write_text(
            json.dumps(
                {
                    "run_id": run.name,
                    "lane": LANE,
                    "chunk": chunk.number,
                    "rows": len(chunk.inserts),
                    "sites": len(chunk.inserts),
                    "digest": chunk.digest,
                },
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    (run / "INSERT_SUMMARY.json").write_text(
        json.dumps(
            {"run_id": run.name, "chunks": len(chunks), **plan_rows.as_json()},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (run / "INSERT_REFUSALS.jsonl").write_text(
        "".join(
            json.dumps(refusal.as_json(), ensure_ascii=False, sort_keys=True) + "\n"
            for refusal in plan_rows.refusals
        ),
        encoding="utf-8",
        newline="\n",
    )
    return chunks


# --------------------------------------------------------------------------- the acceptance
def check(state: ST.State, inserts: Sequence[Insert]) -> dict[str, Any]:
    """The three questions, per inserted site, over a fresh read of production.

    The same three the hero wave asks: does the page serve the file the import links, does the
    thumbnail name the row that serves it, and is it the only live hero row.
    """
    problems: list[str] = []
    served = 0
    thumbs = 0
    heroes = 0
    for row in inserts:
        site = state.sites.get(row.site_id, {})
        rows = state.rows.get(row.site_id, ())
        live = IV.live_heroes(rows)
        if len(live) != 1:
            problems.append(f"{row.site_id}: {len(live)} live hero row(s), expected one")
        else:
            heroes += 1
            holding = live[0]
            if (
                str(holding.get("filename") or "") == row.filename
                and str(holding.get("original_url") or "") == row.values["original_url"]
            ):
                served += 1
            else:
                problems.append(
                    f"{row.site_id} ({site.get('name')!r}): the served row is "
                    f"{holding.get('filename')!r}, not the file the import links"
                )
        if str(site.get("thumbnail_url") or "") == row.new_thumbnail:
            thumbs += 1
        else:
            problems.append(
                f"{row.site_id} ({site.get('name')!r}): thumbnail "
                f"{site.get('thumbnail_url')!r} does not name the served row "
                f"{row.new_thumbnail!r}"
            )
    return {
        "ok": not problems,
        "sites": len(inserts),
        "served_the_import": served,
        "thumbnail_follows": thumbs,
        "one_hero": heroes,
        "problems": problems,
    }
