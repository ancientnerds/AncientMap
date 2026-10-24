"""Owner decision D25 "fill the dead card_stats columns from the Wikidata ids": the card_stats_ext lane.

## The defect

`card_stats` carries five enrichment columns no generator fills - `wikidata_qid`, `best_wiki_url`,
`heritage_designation`, `inception_year`, `commons_image` (`api/cardgame/models.py`, added by
`api/boot_schema.py`). Measured on production 2026-10-24: all five are NULL on all 5,004 curated
cards, while 4,623 curated sites have a verified Wikidata item and 4,602 an English article in
`site_external_ids`. `api/routes/sites.py` and `sites_html.py` already read `best_wiki_url` (the
site page shows it only beside a non-English `source_language`, which this lane does not touch:
`plans/fields.md` item 9), the other four are read by nobody yet.

## Where each value comes from (`derive`)

* `wikidata_qid` - the site's `site_external_ids` row of kind `wikidata_qid`; nothing else is a
  site's item (`fields/harvest.py`'s module docstring);
* `best_wiki_url` - `https://en.wikipedia.org/wiki/<title>` from the row of kind `enwiki_title`,
  spaces as underscores (the form the remediation writes `source_url` in);
* `commons_image` - P18 of that item, the first value of the best rank (preferred, else normal;
  deprecated is never read), as Wikidata serves the file name;
* `heritage_designation` - the English labels of every best-rank P1435 value, `; `-joined in
  Wikidata's order; a value without an English label refuses the cell (it is never guessed);
* `inception_year` - P571 at year precision or finer (9, 10, 11), when every such best-rank value
  names one year and that year passes every refusal of `plans/fields.md` trap 9 and the scope rule:
  - before 1500 (`fields/classify.MODERN`): a later inception is the item's park, museum or
    designation, not the site's start (the modern cases of `period_wave/structured_refused.json`);
  - not a (QID, year) the period wave refused (`structured_refused.json`, `usable_as_period:
    false`, read whole: the file is the trap's own list);
  - within the site's E3 window (`pipeline.normalizers.dates`: 500 AD in the Old World, 1500 AD in
    the Americas and Oceania): a P571 of 1165 on a Roman city is its medieval charter, a castle's or
    a city wall's 1192 or 1336 is a medieval build - the project's scope has no medieval site, so
    such a year is never a curated site's start. A site without a longitude has no region and
    refuses the cell;
  - within or before the band of the site's stored period: the year `passes_date_cutoff` reads
    (`period_end or period_start`) falls in one of the nine `PERIOD_BUCKETS`, the band the card
    shows (`categorize_period`), and the inception may not lie past that band's upper bound. A
    period_start is often the band's edge, not a precise year (`bucket_edge`: a site the import
    dates "3000 - 1500 BC" stores -3000), so the band and not the year is what the card asserts;
    a year after it is a later phase. A site without a stored period refuses the cell (nothing to
    check the year against).
  A coarser value states no year.

The item is read from a field harvest (`fields/harvest.py`: `<harvest>/entities/<QID>.json`, the raw
`wbgetentities` answer). An item the harvest answered under another id (a merged item) refuses every
item-derived cell: the stored QID is stale, which is the external-id wave's repair, not this lane's.

## The write

`card-stats-ext-<wave>-sNNN`, a cell lane on `card_stats` (keyed by `site_id`) of at most 100 sites a
step (D8), one journalled cell per filled column. It only **fills**: a cell whose stored value is not
NULL is never planned (a differing one is listed). Guard 3 holds the NULL, guard 5 what the values
were derived from - the site's two external ids, its period and its place (the inception's checks):
an id repaired or a period rewritten after the plan refuses the step. The five columns are neither
an input nor a cell of the card_stats recompute (`card_stats.COLUMNS`), so this lane and the
recompute waves do not void each other's proof.

## Its place in the order: after every lane that writes a site's ids

Because it only fills, a `wikidata_qid` or `best_wiki_url` it wrote is never corrected by a later
wave of this lane: an id moved afterwards (a D13/D14 identity retarget, the stale-id and external-id
waves, a qid repair) leaves the card on the old item, and the readback only counts it
(`_QID_DRIFT`, and the best_wiki_url metric beside it). So the lane runs **after the last identity
and id-repair lane is accepted** (the D13/D14 retarget, the scope window's retargets, the stale-id
and external-id waves): `docs/procedures/FIELDS_WD5.md` section 13 orders it there. A card either
metric names after that is an owner question (`owner_list_final.py` lists it), never a silent
rewrite by this lane.

    M=scripts/remediation/mechanical
    H=<a field harvest root, e.g. output/remediation/fields/wd5/harvest>
    $M/card_stats_ext.py fetch  --wave W --harvest $H   (read-only production read; Wikidata GETs:
                                                         the missing items into $H, LABELS.json)
    $M/card_stats_ext.py wave   --wave W --harvest $H [--refused R]
                                                        (read-only; WAVE.json, steps of 100)
    $M/card_stats_ext.py step   --wave W --step N       (read-only; PLAN.jsonl, ROLLBACK.sql)
    $M/apply.py --lane card-stats-ext-W-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane card-stats-ext-W-sNNN --rehearse-rollback
    $M/card_stats_ext.py accept --wave W --step N       (read-only; 0 deviations)
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from bcases.collect import WIKIDATA_API, api_json  # noqa: E402 - the Wikimedia API seam
from census.fetch import Fetcher, chunked  # noqa: E402
from fields import classify as C  # noqa: E402 - MODERN and the time-value form
from fields import harvest as H  # noqa: E402 - the harvest layout and its fetcher

from mechanical.field_prov import read_production, sha256_file, step_name  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CARD_STATS,
    CARD_STATS_EXT_LANE,
    LOCK_TIMEOUT,
    STATEMENT_TIMEOUT,
    Column,
    Lane,
    Residual,
    e3_cutoff_sql,
    journal_readback,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    Plan,
    PlanError,
    Verdict,
    _claims,
    parse_tagged_export,
    sql_ids,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline.normalizers.dates import E3_CUTOFFS, e3_region  # noqa: E402
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

ROOT_NAME = "mechanical_card_stats_ext"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
MAX_SITES = 100
WAVE_FILE, WAVE_PIN_FILE, ACCEPTED_FILE = "WAVE.json", "WAVE.sha256", "ACCEPTED.json"
LABELS_FILE = "LABELS.json"
#: The period wave's refused structured dates (`plans/fields.md` trap 9): gitignored run data, so
#: a worktree reads the main checkout's copy (`--refused` names another).
REFUSED_PATH = Path("output") / "remediation" / "period_wave" / "structured_refused.json"
RETIRED = "retired"
ENWIKI = "https://en.wikipedia.org/wiki/"
P_IMAGE, P_HERITAGE, P_INCEPTION = "P18", "P1435", "P571"
#: Wikidata time precision 9 is a year, 10 a month, 11 a day; anything coarser states no year.
YEAR_PRECISION = 9
SEPARATOR = "; "

#: The five columns, with their types as `api/cardgame/models.py` and `api/boot_schema.py` declare
#: them. Each is filled where it is NULL (`fills_null`); none is ever cleared.
CELLS: tuple[Column, ...] = (
    Column("wikidata_qid", "character varying", max_chars=20, fills_null=True),
    Column("best_wiki_url", "character varying", max_chars=500, fills_null=True),
    Column("heritage_designation", "text", fills_null=True),
    Column("inception_year", "integer", fills_null=True),
    Column("commons_image", "character varying", max_chars=500, fills_null=True),
)
COLUMNS: tuple[str, ...] = tuple(cell.name for cell in CELLS)
ITEM_COLUMNS = ("heritage_designation", "inception_year", "commons_image")


def _id_sql(kind: str, site: str = "u.id") -> str:
    return (
        f"(SELECT e.value FROM site_external_ids e WHERE e.site_id = {site} "
        f"AND e.kind = {sql_literal(kind)})"
    )


#: What the values are derived from: the site's two external ids, and its period and place (the
#: inception's checks), as text. Guard 5 refuses a site whose ids moved after the plan (the D25 id
#: wave or a D13 retarget writes them), or whose period or point was rewritten.
PREMISE_SQL = (
    f"coalesce({_id_sql('wikidata_qid')}, '<NULL>') || '|' || "
    f"coalesce({_id_sql('enwiki_title')}, '<NULL>') || '|' || "
    "concat_ws('|', coalesce(u.period_start::text, '<NULL>'), coalesce(u.period_end::text, "
    "'<NULL>'), coalesce(u.country, '<NULL>'), coalesce(u.lat::text, '<NULL>'), "
    "coalesce(u.lon::text, '<NULL>'))"
)

_QID_DRIFT = Residual(
    "curated cards whose wikidata_qid is not their site's item",
    "EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = unified_sites.id AND cs.wikidata_qid "
    f"IS NOT NULL AND cs.wikidata_qid IS DISTINCT FROM {_id_sql('wikidata_qid', 'unified_sites.id')})",
)


# ------------------------------------------------------------------------------ the lanes
def ext_lane(wave: str, step: int) -> Lane:
    """The lane of one step: its own stamp, key prefix and directory."""
    name = f"card-stats-ext-{wave}-{step_name(step)}"
    if CARD_STATS_EXT_LANE.match(name) is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-25 or 2026-10-25b")
    return Lane(
        name=name,
        key_prefix=name,
        run_stamp=f"{wave}_mechanical-card-stats-ext-{step_name(step)}",
        test_id="D25/card-stats-ext",
        confidence="authoritative",
        label="D25 card_stats ext",
        plan_table="_card_stats_ext_plan",
        out_dir_name=f"{ROOT_NAME}/{wave}/{step_name(step)}",
        post_commit_residual=_QID_DRIFT,
        rehearsal_residual=_QID_DRIFT,
        premise_sql=PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=CARD_STATS,
        cells=CELLS,
    )


def lane_of(name: str) -> Lane:
    """`card-stats-ext-2026-10-25-s001` -> the lane; `KeyError` for any other name."""
    match = CARD_STATS_EXT_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return ext_lane(match.group(1), int(match.group(2)))


#: `passes_date_cutoff`'s date in SQL: `period_end or period_start` (a 0 end falls through).
_DATED = "coalesce(nullif(u.period_end, 0), u.period_start)"


def band_end(year: int) -> int:
    """The upper bound (exclusive) of the period band `year` falls in (`categorize_period`)."""
    label = categorize_period(year)
    return next(hi for name, _lo, hi in PERIOD_BUCKETS if name == label)


#: `band_end(_DATED)` in SQL, rendered from the same table (the last band is open above).
_BAND_END = (
    "(CASE "
    + " ".join(f"WHEN {_DATED} < {hi} THEN {hi}" for _name, _lo, hi in PERIOD_BUCKETS[:-1])
    + f" ELSE {PERIOD_BUCKETS[-1][2]} END)"
)
_CARDS = "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id WHERE u.source_id = 'ancient_nerds' AND "


@functools.cache
def readback(lane: Lane) -> str:
    """The read-only verification of one step, before and after its write."""
    stamp = sql_literal(lane.run_stamp)
    return journal_readback(
        lane,
        [
            *((f"curated cards with a {c}", _CARDS + f"cs.{c} IS NOT NULL") for c in COLUMNS),
            (
                _QID_DRIFT.metric,
                "FROM unified_sites WHERE source_id = 'ancient_nerds' AND " + _QID_DRIFT.predicate,
            ),
            (
                "curated cards whose best_wiki_url is not their site's English article",
                _CARDS + f"cs.best_wiki_url IS NOT NULL AND cs.best_wiki_url IS DISTINCT FROM "
                f"{sql_literal(ENWIKI)} || replace({_id_sql('enwiki_title')}, ' ', '_')",
            ),
            (
                f"curated cards whose inception_year is from {C.MODERN} on",
                _CARDS + f"cs.inception_year >= {int(C.MODERN)}",
            ),
            (
                "curated cards whose inception_year lies past the site's E3 cutoff",
                _CARDS + "cs.inception_year IS NOT NULL AND (u.lon IS NULL OR cs.inception_year > "
                f"{e3_cutoff_sql('u.')})",
            ),
            (
                "curated cards whose inception_year lies after the band of the site's period",
                _CARDS + f"cs.inception_year IS NOT NULL AND ({_DATED} IS NULL OR "
                f"cs.inception_year >= {_BAND_END})",
            ),
            (
                "journal rows for this run that overwrite a value",
                f"FROM remediation_change_log WHERE run_stamp = {stamp} AND old_value IS NOT NULL",
            ),
        ],
    )


# ------------------------------------------------------------------------------ the values
def english_url(title: str) -> str:
    return ENWIKI + title.replace(" ", "_")


def best_rank(entity: Mapping[str, Any], prop: str) -> list[Mapping[str, Any]]:
    """The statements of `prop` Wikidata calls truthy: the preferred ones if any, else the normal
    ones (`plan._claims` already drops the deprecated)."""
    statements = _claims(entity, prop)
    preferred = [s for s in statements if s.get("rank") == "preferred"]
    return preferred or statements


def _value(statement: Mapping[str, Any]) -> Any:
    return ((statement.get("mainsnak") or {}).get("datavalue") or {}).get("value")


@dataclass(frozen=True)
class Derived:
    """One column's derived value, or the reason there is none."""

    value: str | None
    reason: str
    note: str
    source: str = ""


def commons_image(entity: Mapping[str, Any]) -> Derived:
    files = [v for v in (_value(s) for s in best_rank(entity, P_IMAGE)) if isinstance(v, str) and v]
    if not files:
        return Derived(None, "no-p18", "the item has no P18 of the best rank")
    note = f"P18 {files[0]!r}" + (
        f", the first of {len(files)} best-rank values in Wikidata's order"
        if len(files) > 1
        else ""
    )
    return Derived(files[0], "", note, P_IMAGE)


def heritage_designation(entity: Mapping[str, Any], labels: Mapping[str, str | None]) -> Derived:
    qids = [
        v["id"]
        for v in (_value(s) for s in best_rank(entity, P_HERITAGE))
        if isinstance(v, dict) and v.get("id")
    ]
    if not qids:
        return Derived(None, "no-p1435", "the item has no P1435 of the best rank")
    unlabelled = [q for q in qids if not labels.get(q)]
    if unlabelled:
        return Derived(
            None,
            "designation-without-label",
            f"P1435 {unlabelled} has no English label in {LABELS_FILE} - never guessed",
        )
    names: list[str] = []
    for qid in qids:
        label = str(labels[qid])
        if label not in names:
            names.append(label)
    return Derived(SEPARATOR.join(names), "", f"P1435 {qids} -> {names}", P_HERITAGE)


def inception_year(
    entity: Mapping[str, Any], site: Live, refused: frozenset[tuple[str, int]]
) -> Derived:
    """P571 as the site's start, or why not (the module docstring's checks, in order)."""
    statements = best_rank(entity, P_INCEPTION)
    if not statements:
        return Derived(None, "no-p571", "the item has no P571 of the best rank")
    years: list[int] = []
    for statement in statements:
        value = _value(statement)
        if not isinstance(value, dict):
            continue
        match = C._TIME.match(str(value.get("time") or ""))
        if match is None or int(value.get("precision") or 0) < YEAR_PRECISION:
            continue
        years.append(int(match[2]) * (-1 if match[1] == "-" else 1))
    if not years:
        return Derived(
            None, "inception-not-a-year", "every best-rank P571 is coarser than a year: no year"
        )
    if len(set(years)) > 1:
        return Derived(
            None, "inception-conflict", f"the best-rank P571 values name {sorted(set(years))}"
        )
    year = years[0]
    if year >= C.MODERN:
        return Derived(
            None,
            "inception-modern",
            f"P571 {year} is from {C.MODERN} on: the item's park, museum or designation, not "
            "the site's start",
        )
    if (str(entity.get("id")), year) in refused:
        return Derived(
            None,
            "inception-refused-by-period-wave",
            f"P571 {year} of {entity.get('id')} is in {REFUSED_PATH.name}: usable_as_period false",
        )
    region = e3_region({"lon": site.lon, "lat": site.lat, "country": site.country})
    if region is None:
        return Derived(
            None,
            "inception-region-unknown",
            "the site has no longitude: its E3 cutoff, and so the year, cannot be checked",
        )
    if year > E3_CUTOFFS[region]:
        return Derived(
            None,
            "inception-past-scope",
            f"P571 {year} lies past the {region} cutoff of {E3_CUTOFFS[region]} AD: a medieval or "
            "later charter, castle or wall, not the start of a site in the project's scope",
        )
    dated = site.period_end or site.period_start
    if dated is None:
        return Derived(
            None,
            "inception-without-period",
            f"P571 {year}, but the site stores no period to check the year against",
        )
    if year >= band_end(dated):
        return Derived(
            None,
            "inception-after-period",
            f"P571 {year} lies after the band of the site's stored period ({dated}, "
            f"{categorize_period(dated)!r}): a later phase, not the site's start",
        )
    return Derived(str(year), "", f"P571 {year}", P_INCEPTION)


@dataclass(frozen=True)
class Live:
    """A curated site and its card's five cells, as production holds them."""

    site_id: str
    name: str
    source_id: str
    scope_status: str | None
    qid: str | None
    enwiki_title: str | None
    has_card: bool
    stored: Mapping[str, str | None]
    premise: str
    lat: float | None
    lon: float | None
    country: str | None
    period_start: int | None
    period_end: int | None


def derive(
    site: Live,
    entity: Mapping[str, Any] | None,
    labels: Mapping[str, str | None],
    refused: frozenset[tuple[str, int]],
) -> dict[str, Derived]:
    """Every column's value for one site, or why there is none. Pure."""
    out: dict[str, Derived] = {}
    out["wikidata_qid"] = (
        Derived(site.qid, "", f"site_external_ids wikidata_qid {site.qid}", "site_external_ids")
        if site.qid
        else Derived(None, "no-qid", "the site has no wikidata_qid in site_external_ids")
    )
    out["best_wiki_url"] = (
        Derived(
            english_url(site.enwiki_title),
            "",
            f"site_external_ids enwiki_title {site.enwiki_title!r}",
            "site_external_ids",
        )
        if site.enwiki_title
        else Derived(None, "no-enwiki-title", "the site has no enwiki_title in site_external_ids")
    )
    if not site.qid:
        missing = Derived(None, "no-qid", "the site has no item to read")
        out.update(dict.fromkeys(ITEM_COLUMNS, missing))
    elif entity is None:
        missing = Derived(
            None, "entity-not-harvested", f"{site.qid} is not in the harvest: run `fetch`"
        )
        out.update(dict.fromkeys(ITEM_COLUMNS, missing))
    elif entity.get("id") != site.qid:
        merged = Derived(
            None,
            "qid-redirects",
            f"Wikidata answers {site.qid} as {entity.get('id')}: the stored item is stale (the "
            "external-id wave repairs it)",
        )
        out.update(dict.fromkeys(ITEM_COLUMNS, merged))
    else:
        out["commons_image"] = commons_image(entity)
        out["heritage_designation"] = heritage_designation(entity, labels)
        out["inception_year"] = inception_year(entity, site, refused)
    return out


def classify(
    site_id: str,
    site: Live | None,
    entity: Mapping[str, Any] | None,
    labels: Mapping[str, str | None],
    refused: frozenset[tuple[str, int]],
    *,
    entity_sha: str | None,
) -> list[Verdict]:
    """Every cell of one site, decided: a fill, or the reason there is none."""

    def verdict(ok: bool, column: str | None, reason: str, note: str, **kw: Any) -> Verdict:
        return Verdict(
            site_id=site_id,
            site_name=site.name if site is not None else "",
            ok=ok,
            old_value=kw.get("old_value"),
            new_value=kw.get("new_value"),
            rule=kw.get("rule", ""),
            reason=reason,
            note=note,
            phase3=False,
            finding_test_id="live:card_stats",
            evidence=tuple(kw.get("evidence", ())),
            premise=site.premise if ok and site is not None else None,
            column=column,
        )

    if site is None:
        return [verdict(False, None, "site-gone", "the wave listed the site; production lacks it")]
    if site.source_id != CURATED_SOURCE:
        return [verdict(False, None, "row-not-in-curated-source", "not a curated row")]
    if site.scope_status == RETIRED:
        return [verdict(False, None, "retired", "a retired site's card is never drawn")]
    if not site.has_card:
        return [
            verdict(
                False,
                None,
                "no-card-stats-row",
                "apply_remediation_change() only updates a row; the generator inserts it",
            )
        ]
    derived = derive(site, entity, labels, refused)
    out: list[Verdict] = []
    for cell in CELLS:
        column = cell.name
        found = derived[column]
        stored = site.stored[column]
        if found.value is None:
            out.append(verdict(False, column, found.reason, found.note, old_value=stored))
            continue
        if cell.max_chars is not None and len(found.value) > cell.max_chars:
            out.append(
                verdict(
                    False,
                    column,
                    "value-too-long",
                    f"{len(found.value)} characters, the column holds {cell.max_chars}",
                    old_value=stored,
                    new_value=found.value,
                )
            )
            continue
        if stored is not None:
            if stored != found.value:
                out.append(
                    verdict(
                        False,
                        column,
                        "stored-differs",
                        f"the card holds {stored!r}, the ids give {found.value!r}: the lane only fills",
                        old_value=stored,
                        new_value=found.value,
                    )
                )
            continue
        source = (
            {
                "source": f"site_external_ids ({site.premise})",
                "url": "site_external_ids",
                "quote": found.note,
            }
            if found.source == "site_external_ids"
            else {
                "source": f"wikidata:{site.qid} {found.source} (harvest entity sha256 {entity_sha})",
                "url": f"https://www.wikidata.org/wiki/{site.qid}",
                "quote": found.note,
            }
        )
        out.append(
            verdict(
                True,
                column,
                "",
                f"{column} NULL -> {found.value}",
                new_value=found.value,
                rule=f"fill-{column}",
                evidence=(source,),
            )
        )
    return out


@dataclass(frozen=True)
class StepPlan:
    plan: Plan


def build_step(
    wave: str,
    step: int,
    sites: Sequence[str],
    live: Mapping[str, Live],
    entities: Mapping[str, Mapping[str, Any] | None],
    entity_shas: Mapping[str, str | None],
    labels: Mapping[str, str | None],
    refused: frozenset[tuple[str, int]],
    *,
    built_at: str,
) -> StepPlan:
    """The lane plan of one step over `sites` (at most 100). Pure."""
    if len(sites) > MAX_SITES:
        raise PlanError(f"a step writes at most {MAX_SITES} sites, not {len(sites)}")
    verdicts = [
        v
        for s in sorted(sites)
        for v in classify(
            s, live.get(s), entities.get(s), labels, refused, entity_sha=entity_shas.get(s)
        )
    ]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters: dict[str, int] = {
        "cells": len(changes),
        "sites": len({v.site_id for v in changes}),
        **{f"cells:{c}": sum(1 for v in changes if v.column == c) for c in COLUMNS},
        **{
            f"skip:{column or 'site'}:{reason}": n
            for (column, reason), n in sorted(
                Counter((v.column, v.reason) for v in skipped).items(), key=lambda kv: str(kv[0])
            )
        },
    }
    plan = Plan(
        changes=changes,
        skipped=skipped,
        built_at=built_at,
        counters=counters,
        lane=ext_lane(wave, step),
    )
    return StepPlan(plan)


# ------------------------------------------------------------------------------ the read
def candidates_sql() -> str:
    """The shown curated sites whose card holds a NULL in one of the five columns."""
    nulls = " OR ".join(f"c.{c} IS NULL" for c in COLUMNS)
    return (
        f"SELECT u.id::text AS site_id, {_id_sql('wikidata_qid')} AS qid FROM unified_sites u "
        f"JOIN card_stats c ON c.site_id = u.id WHERE u.source_id = {sql_literal(CURATED_SOURCE)} "
        f"AND u.scope_status IS DISTINCT FROM {sql_literal(RETIRED)} AND ({nulls}) ORDER BY u.id"
    )


def site_sql(site_ids: Iterable[str]) -> str:
    return (
        "SELECT u.id::text AS site_id, u.name, u.source_id, u.scope_status, "
        f"{_id_sql('wikidata_qid')} AS qid, {_id_sql('enwiki_title')} AS enwiki_title, "
        "u.lat, u.lon, u.country, u.period_start, u.period_end, "
        "c.site_id IS NOT NULL AS has_card, "
        + ", ".join(f"c.{c}::text AS stored_{c}" for c in COLUMNS)
        + f", {PREMISE_SQL} AS premise FROM unified_sites u LEFT JOIN card_stats c ON "
        f"c.site_id = u.id WHERE u.id::text IN ({sql_ids(site_ids)}) ORDER BY u.id"
    )


def parse_sites(rows: Iterable[Mapping[str, Any]]) -> dict[str, Live]:
    return {
        str(r["site_id"]): Live(
            site_id=str(r["site_id"]),
            name=str(r["name"]),
            source_id=str(r["source_id"]),
            scope_status=r["scope_status"],
            qid=r["qid"],
            enwiki_title=r["enwiki_title"],
            has_card=bool(r["has_card"]),
            stored={c: r[f"stored_{c}"] for c in COLUMNS},
            premise=str(r["premise"]),
            lat=None if r["lat"] is None else float(r["lat"]),
            lon=None if r["lon"] is None else float(r["lon"]),
            country=r["country"],
            period_start=r["period_start"],
            period_end=r["period_end"],
        )
        for r in rows
    }


def entity_of(harvest: Path, qid: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """The harvested entity of `qid` and the sha256 of its file, or `(None, None)`."""
    if not qid:
        return None, None
    path = H.entity_path(harvest, qid)
    if not path.exists():
        return None, None
    return json.loads(path.read_text(encoding="utf-8")), sha256_file(path)


# ------------------------------------------------------------------------------ the fetch
def designation_ids(entities: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every item the entities name as a best-rank P1435 value."""
    return sorted(
        {
            v["id"]
            for e in entities
            for v in (_value(s) for s in best_rank(e, P_HERITAGE))
            if isinstance(v, dict) and v.get("id")
        }
    )


def fetch_labels(net: Fetcher, qids: Sequence[str]) -> dict[str, str | None]:
    """The English label of each item, 50 per `wbgetentities` request; None for an item without
    one. An item Wikidata does not answer raises (`harvest._answered`)."""
    labels: dict[str, str | None] = {}
    for chunk in chunked(qids, H.BATCH):
        body = api_json(
            net,
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
            ns="card_stats_ext_labels",
        )
        for qid, entity in H._answered(chunk, body.get("entities") or {}).items():
            labels[qid] = ((entity.get("labels") or {}).get("en") or {}).get("value")
    return labels


def wave_dir(wave: str, root: Path = ROOT) -> Path:
    return root / wave


def fetch(
    wave: str,
    harvest: Path,
    *,
    read: Callable[[str], str] = read_production,
    net: Fetcher | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    """The items of the candidate sites the harvest lacks (into the harvest, `harvest.py`'s way),
    then the English labels of every P1435 value they name (`LABELS.json` in the wave's directory).
    Production is read only; Wikidata is asked with GET only."""
    ext_lane(wave, 1)  # refuses a wave label no lane resolves
    if not (harvest / H.ENTITIES).is_dir():
        raise PlanError(f"{harvest / H.ENTITIES} is no harvest's entity directory")
    rows, _at = parse_tagged_export(
        read(tagged_export_script([("site", candidates_sql())])), ("site",)
    )
    qids = sorted({str(r["qid"]) for r in rows["site"] if r["qid"]})
    net = net if net is not None else H.open_fetcher(harvest)
    fetched = H.fetch_entities(net, harvest, qids)
    entities = [H.load_entity(harvest, q) for q in qids]
    labels = fetch_labels(net, designation_ids(entities))
    target = wave_dir(wave, root)
    target.mkdir(parents=True, exist_ok=True)
    (target / LABELS_FILE).write_text(
        json.dumps(
            {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds"), "labels": labels},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"sites": len(rows["site"]), "items": fetched, "designations": len(labels)}


def default_refused() -> Path:
    """The main checkout's `structured_refused.json` (a worktree carries no `output/`)."""
    from identity.common import main_checkout

    return main_checkout() / REFUSED_PATH


def read_refused(path: Path) -> frozenset[tuple[str, int]]:
    """Every (QID, year) the period wave refused as a P571 (`usable_as_period: false`). A record
    without its QID, property, year or verdict refuses the file: the trap's list is read whole."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the period wave's refused dates (fields.md trap 9)")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise PlanError(f"{path} is not a non-empty list of refused dates")
    refused: set[tuple[str, int]] = set()
    for n, r in enumerate(records):
        if not {"qid", "property", "year", "usable_as_period"} <= set(r) or not isinstance(
            r["year"], int
        ):
            raise PlanError(f"{path} record {n} lacks its qid, property, year or verdict: {r}")
        if r["property"] == P_INCEPTION and r["usable_as_period"] is False:
            refused.add((str(r["qid"]), int(r["year"])))
    return frozenset(refused)


def read_labels(wave: str, root: Path = ROOT) -> dict[str, str | None]:
    path = wave_dir(wave, root) / LABELS_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `card_stats_ext.py fetch` first")
    return dict(json.loads(path.read_text(encoding="utf-8"))["labels"])


# ------------------------------------------------------------------------------ the wave
def build_wave(
    wave: str,
    harvest: Path,
    refused: Path,
    *,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> dict[str, Any]:
    """WAVE.json: the candidate sites in steps of 100, the harvest, the sha256 of each site's
    entity file, of LABELS.json and of the refused dates - from one read-only production read.
    Refused while an item of a candidate is missing from the harvest."""
    ext_lane(wave, 1)
    target = wave_dir(wave, root)
    if (target / WAVE_FILE).exists():
        raise PlanError(f"{target / WAVE_FILE} exists: a wave is planned once")
    read_labels(wave, root)
    read_refused(refused)
    rows, at = parse_tagged_export(
        read(tagged_export_script([("site", candidates_sql())])), ("site",)
    )
    sites = sorted(str(r["site_id"]) for r in rows["site"])
    shas: dict[str, str | None] = {}
    missing: list[str] = []
    for r in rows["site"]:
        entity, sha = entity_of(harvest, r["qid"])
        if r["qid"] and entity is None:
            missing.append(str(r["qid"]))
        shas[str(r["site_id"])] = sha
    if missing:
        raise PlanError(
            f"{len(missing)} item(s) of the candidates are not in {harvest} ({missing[:5]}): run "
            "`card_stats_ext.py fetch` first"
        )
    steps = [sites[i : i + MAX_SITES] for i in range(0, len(sites), MAX_SITES)]
    record = {
        "wave": wave,
        "read_at": at,
        "harvest": harvest.resolve().as_posix(),
        "labels_sha256": sha256_file(target / LABELS_FILE),
        "refused": refused.resolve().as_posix(),
        "refused_sha256": sha256_file(refused),
        "entity_sha256": dict(sorted(shas.items())),
        "sites": len(sites),
        "steps": steps,
    }
    (target / WAVE_FILE).write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    (target / WAVE_PIN_FILE).write_text(
        sha256_file(target / WAVE_FILE) + "\n", encoding="utf-8", newline="\n"
    )
    return {"wave": wave, "sites": len(sites), "steps": len(steps)}


def read_wave(wave: str, root: Path = ROOT) -> dict[str, Any]:
    target = wave_dir(wave, root)
    path = target / WAVE_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `card_stats_ext.py wave` first")
    if sha256_file(path) != (target / WAVE_PIN_FILE).read_text(encoding="utf-8").strip():
        raise PlanError(f"{path} is not the pinned wave: it was edited")
    return json.loads(path.read_text(encoding="utf-8"))


def _step_dir(wave: str, step: int, root: Path) -> Path:
    return wave_dir(wave, root) / step_name(step)


def plan_step(
    wave: str, step: int, *, read: Callable[[str], str] = read_production, root: Path = ROOT
) -> dict[str, Any]:
    """Plan step `step` from the pinned wave and a fresh read-only production read - never a step
    before the one before it is accepted, never from an entity or a label file that moved."""
    record = read_wave(wave, root)
    if not 1 <= step <= len(record["steps"]):
        raise PlanError(f"wave {wave} has steps 1..{len(record['steps'])}, not {step}")
    if step > 1 and not (_step_dir(wave, step - 1, root) / ACCEPTED_FILE).exists():
        raise PlanError(
            f"step {step - 1} is not accepted: `card_stats_ext.py accept --step {step - 1}`"
        )
    if sha256_file(wave_dir(wave, root) / LABELS_FILE) != record["labels_sha256"]:
        raise PlanError(f"{LABELS_FILE} is not the file wave {wave} was built from")
    refused_path = Path(record["refused"])
    if not refused_path.exists() or sha256_file(refused_path) != record["refused_sha256"]:
        raise PlanError(f"{refused_path} is not the refused-dates file wave {wave} was built from")
    out = _step_dir(wave, step, root)
    if out.exists():
        raise PlanError(f"{out} exists: a step is planned once")
    sites = record["steps"][step - 1]
    text = read(tagged_export_script([("site", site_sql(sites))]))
    live = parse_sites(parse_tagged_export(text, ("site",))[0]["site"])
    harvest = Path(record["harvest"])
    entities: dict[str, dict[str, Any] | None] = {}
    shas: dict[str, str | None] = {}
    for site in sites:
        here = live.get(site)
        entity, sha = entity_of(harvest, here.qid if here is not None else None)
        pinned = record["entity_sha256"].get(site)
        if here is not None and here.qid and sha != pinned:
            raise PlanError(
                f"{site}: the harvest entity of {here.qid} is not the one wave {wave} pinned "
                f"(sha256 {str(sha)[:16]}, pinned {str(pinned)[:16]}) - the site's item moved: "
                "plan a new wave"
            )
        entities[site], shas[site] = entity, sha
    built = build_step(
        wave,
        step,
        sites,
        live,
        entities,
        shas,
        read_labels(wave, root),
        read_refused(refused_path),
        built_at=datetime.now(UTC).isoformat(),
    )
    out.mkdir(parents=True)
    (out / "export.jsonl").write_text(text, encoding="utf-8", newline="\n")
    write_skipped_jsonl(built.plan, out / "SKIPPED.jsonl")
    if built.plan.changes:
        write_plan_jsonl(built.plan, out / "PLAN.jsonl")
        write_rollback_sql(built.plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    return {"step": step, "lane": built.plan.lane.name, **built.plan.counters}


# ------------------------------------------------------------------------------ the acceptance
def deviations(
    lane: Lane,
    rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    written = [j for j in journal if j["run_stamp"] == lane.run_stamp]
    undone = [j for j in journal if j["run_stamp"] == lane.rollback_run_stamp]
    if undone:
        found.append(f"{lane.name}: {len(undone)} rollback journal row(s)")
    by_cell = {(j["row_pk"], j["column_name"]): j for j in written}
    planned = {(r["site_id"], r["column"]) for r in rows}
    if len(by_cell) != len(written) or set(by_cell) != planned:
        found.append(f"{lane.name}: {len(written)} journal row(s) for {len(rows)} planned cell(s)")
    for row in rows:
        site = live.get(row["site_id"])
        if site is None or site.stored[row["column"]] != row["new_value"]:
            found.append(
                f"{row['site_id']}/{row['column']}: the card does not hold the planned value"
            )
        entry = by_cell.get((row["site_id"], row["column"]))
        if entry is None or (entry["old_value"], entry["new_value"]) != (None, row["new_value"]):
            found.append(f"{row['site_id']}/{row['column']}: the journal row is not the plan's")
    return found


def accept_step(
    wave: str, step: int, *, read: Callable[[str], str] = read_production, root: Path = ROOT
) -> tuple[int, list[str]]:
    """Re-read production (read-only) for one step; record its acceptance at 0 deviations - once."""
    lane = ext_lane(wave, step)
    out = _step_dir(wave, step, root)
    plan_path = out / "PLAN.jsonl"
    rows = (
        [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines() if line]
        if plan_path.exists()
        else []
    )
    stamps = ", ".join(sql_literal(s) for s in (lane.run_stamp, lane.rollback_run_stamp))
    parts = [
        (
            "journal",
            "SELECT l.row_pk, l.column_name, l.run_stamp, l.old_value, l.new_value FROM "
            f"remediation_change_log l WHERE l.run_stamp IN ({stamps}) ORDER BY l.id",
        )
    ]
    if rows:
        parts.insert(0, ("site", site_sql({r["site_id"] for r in rows})))
    parsed, at = parse_tagged_export(read(tagged_export_script(parts)), ("site", "journal"))
    found = deviations(lane, rows, parse_sites(parsed["site"]), parsed["journal"])
    accepted = out / ACCEPTED_FILE
    if not found and not accepted.exists():
        accepted.write_text(
            json.dumps(
                {
                    "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "read_at": at,
                    "cells": len(rows),
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return (0 if not found else 1), found


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "wave", "step", "accept"):
        command = sub.add_parser(name)
        command.add_argument(
            "--wave", required=True, help="a date label: 2026-10-25 or 2026-10-25b"
        )
        if name in ("fetch", "wave"):
            command.add_argument("--harvest", type=Path, required=True, help="a field harvest root")
        else:
            command.add_argument("--step", type=int, required=True)
        if name == "wave":
            command.add_argument(
                "--refused",
                type=Path,
                default=None,
                help=f"the period wave's refused dates (default: the main checkout's {REFUSED_PATH})",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            _print(fetch(args.wave, args.harvest))
        elif args.command == "wave":
            _print(build_wave(args.wave, args.harvest, args.refused or default_refused()))
        elif args.command == "step":
            _print(plan_step(args.wave, args.step))
        else:
            code, found = accept_step(args.wave, args.step)
            _print({"deviations": found})
            print(f"ACCEPT_EXIT={code}")
            return code
    except (PlanError, ValueError, H.HarvestError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
