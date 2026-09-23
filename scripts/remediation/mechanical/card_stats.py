"""Phase 6 item 4: recompute `card_stats` the way the card generator would - the card_stats lane.

## The defect

`card_stats` is derived: `api/cardgame/generator.py::generate_stats()` computes twelve columns per
curated site from `unified_sites` and a few counts, and nothing re-runs it after a field write. The
remediation has corrected `site_type`, `period_start`, `period_name` and `country` on about a
thousand sites since 2026-09-20, so the cards still show the old values: `civilization` is the old
country on every journalled country row, `fortification`/`category_group` the old type, `antiquity`
the old year - and `mystery`, which counts how many curated sites share a `(site_type,
period_name)` pair, has moved on sites nobody touched.

Running the generator itself is not the route: it writes every row with an ORM setattr, keeps no
journal, and runs seven `ALTER TABLE` blocks each time (`generator.py:93-116`, `:161-177`). This
lane computes the same values and writes only the cells that differ, each through
`apply_remediation_change()` with its old value in the WHERE and a journal row.

## "The same values" - by construction, and proven

* The values are `generator.site_card_stats()` - the function the generator's own upsert loop
  calls - fed by `generator.content_stats()` and `generator._count_combos`' rule (a `Counter` over
  every curated `(site_type, period_name)`), from a read-only export of exactly the inputs the
  generator reads (`EXPORT_SQL`). No rule of the generator is re-typed here.
* **The empire order.** `tag_site()` returns empires in the order `Path.iterdir()` lists the
  boundary directories, and that order is the filesystem's: alphabetical on this Windows checkout,
  hash order on the VPS's ext4. The export reads production's order (`ls -f`, the order the API
  container's bind mount lists) and the matched empires are put in it. The boundary files
  themselves are the repository's (`public/data/historical`, 1,090 files, identical to the VPS's
  after CRLF normalisation - measured 2026-09-23).
* **The counterfactual.** Put back every journalled `unified_sites` value written since the last
  card_stats write (all of them, the first time) and recompute: the result must equal the stored
  `card_stats` cell for cell, or the plan is refused - a model that cannot reproduce the stored
  cards would mix its own error into every change it plans. Measured 2026-09-23: 0 of 60,048
  cells differ.

## What a cell must satisfy (`classify_cells`)

1. the site is curated; 2. the generator recomputes it (`description` is not empty,
   `generate_stats()`'s own filter) - otherwise the row is left as the generator leaves it;
3. a `card_stats` row exists (the generator would INSERT one; `apply_remediation_change()` only
   updates, so a missing row is reported, not written); 4. the recomputed value differs from the
   stored one; 5. the new value is not NULL (a lane never clears a column).

Every cell carries the site's premise - an md5 of every input the recompute read for that site,
and of every curated `(site_type, period_name)` pair, which `mystery` counts - so the transaction
refuses a site whose inputs moved after the export, and every site once any site's type or period
label moved (guard 5). Re-run the export and the plan after every later write wave: a
wave is a lane of its own (`card-stats-<wave>`, `lane.resolve_lane`), with its own run stamp.

`--export` reads production (read-only, one `READ ONLY` transaction) into
`output/remediation/mechanical_card_stats/<wave>/export/`; `--write` plans from that export and
writes `PLAN.jsonl`, `PLAN.md`, `SKIPPED.jsonl`, `ROLLBACK.sql`. `apply.py --lane
card-stats-<wave>` renders and runs the transaction.

Importing the API package runs `api.routes.vector_sync`'s import-time `SELECT` on the configured
database (a read, caught when it fails); this module opens no database session of its own - every
production read goes through psql over ssh, like every other lane.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import logging
import os
import shlex
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from prod_write import SSH_HOST, SSH_OPTIONS, send  # noqa: E402

from api.cardgame.constants import GROUP_FORTIFICATION, RARITY_NAMES  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CARD_STATS,
    LOCK_TIMEOUT,
    STATEMENT_TIMEOUT,
    Column,
    Lane,
    Residual,
    journal_readback,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    Plan,
    PlanError,
    Verdict,
    _now,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)

log = logging.getLogger("mechanical.card_stats")

LANE_ROOT = "mechanical_card_stats"
#: The wave this branch plans. A later wave passes its own (`--wave 2026-09-24`).
FIRST_WAVE = "2026-09-23"
#: Where production keeps the empire boundaries the API container reads (bind-mounted to
#: /app/public/data/historical, `docker-compose.yml`), and where the tagger reads them locally.
PRODUCTION_HISTORICAL = "/var/www/ancientnerds/public/data/historical"
HISTORICAL = REPO / "public" / "data" / "historical"

#: The twelve columns `site_card_stats()` returns and `_upsert_stats` sets, with their types as
#: the catalog names them on production (2026-09-23). The group and tier vocabularies are the
#: generator's own constants.
CELLS: tuple[Column, ...] = (
    Column("antiquity", "integer"),
    Column("fortification", "integer"),
    Column("cultural_influence", "integer"),
    Column("mystery", "integer"),
    Column("legacy", "integer"),
    Column("total_power", "integer"),
    Column("rarity_score", "integer"),
    Column(
        "rarity_tier", "integer", allowed_new_values=tuple(str(t) for t in sorted(RARITY_NAMES))
    ),
    Column(
        "category_group",
        "character varying",
        max_chars=50,
        allowed_new_values=tuple(sorted(GROUP_FORTIFICATION)),
    ),
    Column("civilization", "character varying", max_chars=100),
    Column("empires", "jsonb"),
    Column("empire_count", "integer"),
)
COLUMNS: tuple[str, ...] = tuple(cell.name for cell in CELLS)

#: The site's premise: every input the recompute reads for it, as the database prints it, hashed -
#: and the `(site_type, period_name)` pairs of every curated site, which `mystery` counts. That
#: last part is one uncorrelated subquery, so Postgres evaluates it once per statement; counting
#: the site's own pair with a correlated `IS NOT DISTINCT FROM` subquery instead took 10 ms a row
#: on production (51.7 s over the 5,004 curated rows, measured 2026-09-23), the rest 1 s together.
PREMISE_SQL = (
    "md5(concat_ws('|', coalesce(u.site_type, '<NULL>'), coalesce(u.period_name, '<NULL>'), "
    "coalesce(u.period_start::text, '<NULL>'), coalesce(u.period_end::text, '<NULL>'), "
    "coalesce(u.country, '<NULL>'), coalesce(u.lat::text, '<NULL>'), "
    "coalesce(u.lon::text, '<NULL>'), md5(coalesce(u.description, '<NULL>')), "
    "md5(coalesce(u.source_url, '<NULL>')), md5(coalesce(u.thumbnail_url, '<NULL>')), "
    "(SELECT count(*) || ':' || coalesce(md5(string_agg(coalesce(s.content_type, '<NULL>') || '/' "
    "|| coalesce(s.content_source, '<NULL>'), ',' ORDER BY s.id)), '') "
    "FROM site_content_links s WHERE s.site_id = u.id), "
    "(SELECT count(*)::text FROM wiki_images w WHERE w.site_id = u.id), "
    "(SELECT count(*)::text FROM site_likes k WHERE k.site_id = u.id), "
    "(SELECT count(*)::text FROM site_bookmarks b WHERE b.site_id = u.id), "
    "(SELECT md5(string_agg(coalesce(x.site_type, '<NULL>') || '/' || "
    "coalesce(x.period_name, '<NULL>'), ',' ORDER BY x.id)) FROM unified_sites x "
    "WHERE x.source_id = 'ancient_nerds')))"
)

_CIVILIZATION_DRIFT = Residual(
    "curated rows whose card_stats civilization differs from the site country",
    "EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = unified_sites.id "
    "AND cs.civilization IS DISTINCT FROM unified_sites.country)",
)


@functools.cache
def card_stats_lane(wave: str) -> Lane:
    """The card_stats recompute of one wave: its own stamp, key prefix and directory."""
    return Lane(
        name=f"card-stats-{wave}",
        key_prefix=f"card-stats-{wave}",
        run_stamp=f"{wave}_mechanical-card-stats",
        test_id="P6/card-stats-recompute",
        confidence="authoritative",
        label="card_stats recompute",
        plan_table="_card_stats_plan",
        out_dir_name=f"{LANE_ROOT}/{wave}",
        post_commit_residual=_CIVILIZATION_DRIFT,
        rehearsal_residual=_CIVILIZATION_DRIFT,
        premise_sql=PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=CARD_STATS,
        cells=CELLS,
    )


@functools.cache
def card_stats_readback(lane: Lane) -> str:
    """The read-only verification of a card_stats wave, before and after its write - one text per
    wave, built once, like the registered lanes' `LANE_READBACKS`."""
    stamp = sql_literal(lane.run_stamp)
    return journal_readback(
        lane,
        [
            (
                _CIVILIZATION_DRIFT.metric,
                "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
                + _CIVILIZATION_DRIFT.predicate,
            ),
            *(
                (
                    f"card_stats rows of tier {tier}",
                    "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "
                    f"WHERE u.source_id = 'ancient_nerds' AND cs.rarity_tier = {int(tier)}",
                )
                for tier in sorted(RARITY_NAMES)
            ),
            (
                "curated sites without a card_stats row",
                "FROM unified_sites u WHERE u.source_id = 'ancient_nerds' "
                "AND NOT EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = u.id)",
            ),
            (
                "card_stats rows whose total_power is not the sum of the five stats",
                "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "
                "WHERE u.source_id = 'ancient_nerds' AND cs.total_power <> cs.antiquity + "
                "cs.fortification + cs.cultural_influence + cs.mystery + cs.legacy",
            ),
            (
                "journal rows for this run whose row is not a card_stats row",
                "FROM remediation_change_log l WHERE l.run_stamp = "
                f"{stamp} AND NOT EXISTS (SELECT 1 FROM card_stats cs "
                "WHERE cs.site_id::text = l.row_pk)",
            ),
        ],
    )


# ------------------------------------------------------------------------------- the export
EXPORT_SITES_SQL = (
    "SELECT u.id::text AS id, u.name, u.source_id, u.site_type, u.period_name, u.period_start, "
    "u.period_end, u.description, u.source_url, u.thumbnail_url, u.country, u.lat, u.lon, "
    "(SELECT coalesce(json_agg(json_build_array(s.content_type, s.content_source) ORDER BY s.id), "
    "'[]'::json) FROM site_content_links s WHERE s.site_id = u.id) AS links, "
    "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS wiki_images, "
    "(SELECT count(*) FROM site_likes k WHERE k.site_id = u.id) AS likes, "
    "(SELECT count(*) FROM site_bookmarks b WHERE b.site_id = u.id) AS bookmarks, "
    f"{PREMISE_SQL} AS premise, c.site_id IS NOT NULL AS has_card, "
    + ", ".join(
        f"c.{column}::text AS stored_{column}"
        if column == "empires"
        else f"c.{column} AS stored_{column}"
        for column in COLUMNS
    )
    + " FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
    f"WHERE u.source_id = {sql_literal(CURATED_SOURCE)} ORDER BY u.id"
)

#: Every journal row that could explain a card: the unified_sites inputs, and card_stats itself.
EXPORT_JOURNAL_SQL = (
    "SELECT l.id, l.row_pk, l.table_name, l.column_name, l.old_value, l.new_value, l.run_stamp "
    "FROM remediation_change_log l WHERE l.table_name IN ('unified_sites', 'card_stats') ORDER BY l.id"
)


def export_script() -> str:
    """One read-only, repeatable-read transaction: the sites and the journal from one snapshot.

    Every line of its output is one JSON object tagged with its `kind`; `QUIET` keeps psql's
    `BEGIN`/`COMMIT` tags out of it.
    """
    return (
        "\\set QUIET on\n"
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        f"SELECT json_build_object('kind', 'site', 'row', row_to_json(t)) FROM ({EXPORT_SITES_SQL}) t;\n"
        f"SELECT json_build_object('kind', 'journal', 'row', row_to_json(t)) FROM ({EXPORT_JOURNAL_SQL}) t;\n"
        "SELECT json_build_object('kind', 'snapshot', 'row', json_build_object('exported_at', "
        "now()::text));\n"
        "COMMIT;\n"
    )


@dataclass(frozen=True)
class Export:
    """What the recompute reads: the curated rows, the journal, and production's empire order."""

    sites: tuple[dict[str, Any], ...]
    journal: tuple[dict[str, Any], ...]
    empire_order: tuple[str, ...]
    exported_at: str
    sha256: str


def parse_export(text: str, empire_order: Sequence[str]) -> Export:
    """The export's tagged lines as an `Export`; a line of any other kind is refused."""
    sites: list[dict[str, Any]] = []
    journal: list[dict[str, Any]] = []
    stamps: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        kind = payload.get("kind")
        if kind == "site":
            sites.append(payload["row"])
        elif kind == "journal":
            journal.append(payload["row"])
        elif kind == "snapshot":
            stamps.append(str(payload["row"]["exported_at"]))
        else:
            raise PlanError(f"the export holds a line of kind {kind!r}: {line[:80]!r}")
    if len(stamps) != 1:
        raise PlanError(f"the export must hold one snapshot line, it has {len(stamps)}")
    if not sites:
        raise PlanError("the export holds no curated site - refusing to plan against nothing")
    if not empire_order:
        raise PlanError("the export carries no empire order")
    return Export(
        sites=tuple(sites),
        journal=tuple(journal),
        empire_order=tuple(empire_order),
        exported_at=stamps[0],
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def production_empire_order(host: str = SSH_HOST) -> list[str]:
    """The order production's API lists the boundary directories in - `ls -f`, read-only."""
    proc = subprocess.run(
        shlex.split(f"ssh {SSH_OPTIONS} {host} ls -f {PRODUCTION_HISTORICAL}"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise PlanError(f"ls -f {PRODUCTION_HISTORICAL} failed: {proc.stderr.strip()}")
    names = [n for n in proc.stdout.splitlines() if n and n not in (".", "..")]
    if not names:
        raise PlanError(f"{PRODUCTION_HISTORICAL} lists nothing on production")
    return names


def write_export(directory: Path, *, host: str = SSH_HOST) -> Path:
    """Read production (read-only) and keep the export as it came, with the empire order."""
    proc = send(export_script(), host=host, rows=True, timeout=900)
    if proc.returncode != 0:
        raise PlanError(f"the export failed (psql exit {proc.returncode}): {proc.stderr.strip()}")
    order = production_empire_order(host)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "export.jsonl"
    path.write_text(proc.stdout, encoding="utf-8", newline="\n")
    (directory / "empire_order.json").write_text(
        json.dumps(order, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def load_export(directory: Path) -> Export:
    """The export `write_export` kept - refused unless it is complete."""
    path = directory / "export.jsonl"
    order_path = directory / "empire_order.json"
    for needed in (path, order_path):
        if not needed.exists():
            raise PlanError(f"{needed} is missing - run --export first (reads production)")
    return parse_export(
        path.read_text(encoding="utf-8"), json.loads(order_path.read_text(encoding="utf-8"))
    )


# ------------------------------------------------------------------------------- the model
def _generator() -> tuple[Callable[..., dict], Callable[..., tuple[int, int, bool]]]:
    """The generator's own two functions (imported late: the API package is heavy)."""
    from api.cardgame.generator import content_stats, site_card_stats

    return site_card_stats, content_stats


def check_boundaries(empire_order: Sequence[str]) -> None:
    """The tagger reads `public/data/historical` relative to the working directory and quietly
    tags nothing when it is not there (`tagger._load_all_empires`). Refuse instead - and refuse
    an empire production does not list, whose place in the order would be a guess."""
    from pipeline.historical_boundaries import tagger

    here = (Path.cwd() / tagger.HISTORICAL_DIR).resolve()
    if here != HISTORICAL.resolve():
        raise PlanError(
            f"the empire tagger reads {here}, not {HISTORICAL} - run from the repository root"
        )
    empires = set(tagger._get_empires())
    if not empires:
        raise PlanError(f"the empire tagger found no empire under {here}")
    unlisted = sorted(empires - set(empire_order))
    if unlisted:
        raise PlanError(f"production does not list these empires: {unlisted}")


def site_namespace(row: Mapping[str, Any]) -> SimpleNamespace:
    """An exported row in the shape the generator reads a UnifiedSite in."""
    return SimpleNamespace(
        id=row["id"],
        site_type=row["site_type"],
        period_name=row["period_name"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        description=row["description"],
        source_url=row["source_url"],
        thumbnail_url=row["thumbnail_url"],
        country=row["country"],
        lat=row["lat"],
        lon=row["lon"],
    )


def recompute(
    sites: Sequence[Mapping[str, Any]],
    empire_order: Sequence[str],
    *,
    generator: tuple[Callable[..., dict], Callable[..., tuple[int, int, bool]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """What `generate_stats()` would write for these rows, per site id.

    `_count_combos` counts every curated row; `generate_stats()` recomputes only the rows with a
    description - both rules are the generator's, applied to the export. The empires are put in
    production's directory order, which is the order `tag_site` returns them in there.
    """
    site_card_stats, content_stats = generator or _generator()
    rank = {name: i for i, name in enumerate(empire_order)}
    combos = Counter((row["site_type"], row["period_name"]) for row in sites)
    out: dict[str, dict[str, Any]] = {}
    for row in sites:
        if not row["description"]:
            continue
        links = [SimpleNamespace(content_type=a, content_source=b) for a, b in row["links"]]
        stats = site_card_stats(
            site_namespace(row),
            combo_counts=combos,
            content=content_stats(links),
            wiki_image_count=int(row["wiki_images"]),
            engagement=(int(row["likes"]), int(row["bookmarks"])),
        )
        unranked = [e for e in stats["empires"] if e not in rank]
        if unranked:
            raise PlanError(f"{row['id']}: empires {unranked} have no place in production's order")
        stats["empires"] = sorted(stats["empires"], key=rank.__getitem__)
        out[row["id"]] = stats
    return out


def cell_text(column: str, value: Any) -> str | None:
    """A cell value as the database prints it (`jsonb` compact with `, ` and `: `, like Postgres)."""
    if value is None:
        return None
    if column == "empires":
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def stored(row: Mapping[str, Any], column: str) -> Any:
    """The stored cell, in the type the generator computes (the export prints jsonb as text)."""
    value = row[f"stored_{column}"]
    if column == "empires" and value is not None:
        return json.loads(value)
    return value


def check_jsonb_spelling(sites: Sequence[Mapping[str, Any]]) -> None:
    """The journal records the text of a cell; `cell_text` must spell `empires` the way the
    database prints it, or an old value would not read back as the stored one."""
    for row in sites:
        text = row.get("stored_empires")
        if text is not None and cell_text("empires", json.loads(text)) != text:
            raise PlanError(
                f"{row['id']}: the database prints empires as {text!r}, this module would write "
                f"{cell_text('empires', json.loads(text))!r}"
            )


# ------------------------------------------------------------------------ the counterfactual
INPUT_COLUMNS = (
    "site_type",
    "period_name",
    "period_start",
    "period_end",
    "country",
    "lat",
    "lon",
    "description",
    "source_url",
    "thumbnail_url",
)


def counterfactual_sites(
    sites: Sequence[Mapping[str, Any]], journal: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """The rows as they were when `card_stats` was last written: every journalled input value
    written after the last card_stats journal row is put back. Returns the rows and how many
    journal rows were undone.

    The first time, no card_stats row is journalled, so every journalled input goes back to its
    first old value - the state the generator last saw.
    """
    card_ids = [int(j["id"]) for j in journal if j["table_name"] == "card_stats"]
    since = max(card_ids) if card_ids else 0
    by_id = {row["id"]: dict(row) for row in sites}
    undone = 0
    for entry in sorted(journal, key=lambda j: int(j["id"]), reverse=True):
        if entry["table_name"] != "unified_sites" or int(entry["id"]) <= since:
            continue
        column = entry["column_name"]
        if column not in INPUT_COLUMNS:
            continue
        row = by_id.get(entry["row_pk"])
        if row is None:
            continue
        old = entry["old_value"]
        if column in ("period_start", "period_end"):
            row[column] = None if old is None else int(old)
        elif column in ("lat", "lon"):
            row[column] = None if old is None else float(old)
        else:
            row[column] = old
        undone += 1
    return list(by_id.values()), undone


def diff_cells(
    sites: Sequence[Mapping[str, Any]], computed: Mapping[str, Mapping[str, Any]]
) -> list[tuple[str, str, Any, Any]]:
    """`(site_id, column, stored, computed)` for every cell the recompute would change."""
    out = []
    for row in sites:
        stats = computed.get(row["id"])
        if stats is None or not row["has_card"]:
            continue
        for column in COLUMNS:
            if stored(row, column) != stats[column]:
                out.append((row["id"], column, stored(row, column), stats[column]))
    return out


def prove_the_model(export: Export, generator: Any = None) -> dict[str, int]:
    """The counterfactual, measured: refuse to plan unless it reproduces the stored cards."""
    rows, undone = counterfactual_sites(export.sites, export.journal)
    computed = recompute(rows, export.empire_order, generator=generator)
    differ = diff_cells(rows, computed)
    if differ:
        sample = ", ".join(f"{sid}/{col}: {old!r} vs {new!r}" for sid, col, old, new in differ[:5])
        raise PlanError(
            f"the counterfactual (journal undone: {undone} rows) does not reproduce the stored "
            f"card_stats: {len(differ)} cell(s) differ ({sample}) - the model must be explained "
            "before it plans a write"
        )
    return {
        "counterfactual_journal_rows_undone": undone,
        "counterfactual_cells_compared": sum(
            1 for r in rows if r["id"] in computed and r["has_card"]
        )
        * len(COLUMNS),
        "counterfactual_cells_differing": 0,
    }


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class CardStatsPlan:
    plan: Plan
    counters: Mapping[str, int] = field(default_factory=dict)
    tier_moves: Mapping[tuple[int, int], int] = field(default_factory=dict)
    group_moves: Mapping[tuple[str, str], int] = field(default_factory=dict)
    changed_sites: int = 0


def _explain(column: str, row: Mapping[str, Any], stats: Mapping[str, Any], combos: int) -> str:
    """The inputs a column is computed from, in words - the cell's own evidence."""
    group = stats["category_group"]
    if column == "antiquity":
        return f"period_start {row['period_start']}"
    if column in ("fortification", "category_group"):
        return f"site_type {row['site_type']!r} is in group {group!r}"
    if column == "cultural_influence":
        return (
            f"description {'yes' if row['description'] else 'no'}, thumbnail "
            f"{'yes' if row['thumbnail_url'] else 'no'}, {len(row['links'])} content link(s), "
            f"{row['wiki_images']} image(s), source_url {'yes' if row['source_url'] else 'no'}"
        )
    if column == "mystery":
        return (
            f"({row['site_type']!r}, {row['period_name']!r}) is shared by {combos} curated site(s)"
        )
    if column == "legacy":
        return (
            f"period {row['period_start']}..{row['period_end']}, {row['likes']} like(s), "
            f"{row['bookmarks']} bookmark(s)"
        )
    if column == "total_power":
        return "antiquity + fortification + cultural_influence + mystery + legacy = " + " + ".join(
            str(stats[c])
            for c in ("antiquity", "fortification", "cultural_influence", "mystery", "legacy")
        )
    if column == "rarity_score":
        return f"mystery {stats['mystery']}, cultural_influence {stats['cultural_influence']}"
    if column == "rarity_tier":
        return f"rarity_score {stats['rarity_score']}"
    if column == "civilization":
        return f"country {row['country']!r}"
    return f"tag_site({row['lat']}, {row['lon']}, period_start {row['period_start']})"


def classify_cells(
    export: Export, computed: Mapping[str, Mapping[str, Any]], proof: Mapping[str, int]
) -> tuple[list[Verdict], list[Verdict]]:
    """Every changed cell, decided: `(changes, skipped)`."""
    combos = Counter((row["site_type"], row["period_name"]) for row in export.sites)
    journal: dict[str, list[Mapping[str, Any]]] = {}
    for entry in export.journal:
        if entry["table_name"] == "unified_sites" and entry["column_name"] in INPUT_COLUMNS:
            journal.setdefault(entry["row_pk"], []).append(entry)
    export_evidence = {
        "source": f"production export {export.sha256[:16]} ({export.exported_at})",
        "url": "remediation_change_log + unified_sites + card_stats (read-only)",
        "quote": "counterfactual: {undone} journalled input value(s) put back reproduce the stored "
        "card_stats in all {cells} cells".format(
            undone=proof["counterfactual_journal_rows_undone"],
            cells=proof["counterfactual_cells_compared"],
        ),
    }
    changes: list[Verdict] = []
    skipped: list[Verdict] = []
    for row in sorted(export.sites, key=lambda r: r["id"]):
        stats = computed.get(row["id"])

        def verdict(ok: bool, column: str | None, reason: str, note: str, **kw: Any) -> Verdict:
            return Verdict(
                site_id=row["id"],
                site_name=str(row["name"]),
                ok=ok,
                old_value=kw.get("old_value"),
                new_value=kw.get("new_value"),
                rule=kw.get("rule", ""),
                reason=reason,
                note=note,
                phase3=any(
                    str(j["run_stamp"]).startswith("phase3:") for j in journal.get(row["id"], ())
                ),
                finding_test_id="live:card_stats",
                evidence=tuple(kw.get("evidence", ())),
                premise=row["premise"] if ok else None,
                column=column,
            )

        if row["source_id"] != CURATED_SOURCE:
            skipped.append(verdict(False, None, "row-not-in-curated-source", "not a curated row"))
            continue
        if stats is None:
            skipped.append(
                verdict(
                    False,
                    None,
                    "no-description",
                    "generate_stats() recomputes only sites with a description; the row is left "
                    "as the generator leaves it",
                )
            )
            continue
        if not row["has_card"]:
            skipped.append(
                verdict(
                    False,
                    None,
                    "no-card-stats-row",
                    "the generator would INSERT a row; apply_remediation_change() only updates one",
                )
            )
            continue
        inputs = [
            {
                "source": f"remediation_change_log:{j['id']}",
                "url": "remediation_change_log",
                "quote": f"{j['run_stamp']}: {j['column_name']} {j['old_value']!r} -> "
                f"{j['new_value']!r}",
            }
            for j in journal.get(row["id"], ())
        ]
        combo = combos[(row["site_type"], row["period_name"])]
        for column in COLUMNS:
            old, new = stored(row, column), stats[column]
            if old == new:
                continue
            if new is None:
                skipped.append(
                    verdict(
                        False,
                        column,
                        "new-value-null",
                        f"the generator computes NULL for {column}; this lane never clears a column",
                        old_value=cell_text(column, old),
                    )
                )
                continue
            changes.append(
                verdict(
                    True,
                    column,
                    "",
                    f"{column} {cell_text(column, old)} -> {cell_text(column, new)}",
                    old_value=cell_text(column, old),
                    new_value=cell_text(column, new),
                    rule="generator-recompute",
                    evidence=(
                        {
                            "source": "api/cardgame/generator.py:site_card_stats",
                            "url": "api/cardgame/generator.py",
                            "quote": f"{column} = {cell_text(column, new)} from "
                            f"{_explain(column, row, stats, combo)}",
                        },
                        export_evidence,
                        *inputs,
                    ),
                )
            )
    return changes, skipped


def build_card_stats_plan(
    export: Export, lane: Lane, *, built_at: str, generator: Any = None
) -> CardStatsPlan:
    """A pure function of the export: no database, no clock of its own."""
    check_jsonb_spelling(export.sites)
    proof = prove_the_model(export, generator)
    computed = recompute(export.sites, export.empire_order, generator=generator)
    changes, skipped = classify_cells(export, computed, proof)
    journalled = {
        str(j["row_pk"])
        for j in export.journal
        if j["table_name"] == "unified_sites" and j["column_name"] in INPUT_COLUMNS
    }
    tier_moves: Counter = Counter()
    group_moves: Counter = Counter()
    for change in changes:
        if change.column == "rarity_tier":
            tier_moves[(int(str(change.old_value)), int(str(change.new_value)))] += 1
        if change.column == "category_group":
            group_moves[(str(change.old_value), str(change.new_value))] += 1
    counters: dict[str, int] = {
        "curated_rows": len(export.sites),
        "recomputed_rows": len(computed),
        "cells": len(changes),
        "changed_rows": len({c.site_id for c in changes}),
        "skipped": len(skipped),
        **proof,
        **{f"cells:{column}": sum(1 for c in changes if c.column == column) for column in COLUMNS},
        "changed_rows_on_journalled_sites": len({c.site_id for c in changes} & journalled),
    }
    plan = Plan(
        changes=tuple(changes),
        skipped=tuple(skipped),
        built_at=built_at,
        counters=counters,
        lane=lane,
    )
    return CardStatsPlan(
        plan=plan,
        counters=counters,
        tier_moves=dict(tier_moves),
        group_moves=dict(group_moves),
        changed_sites=counters["changed_rows"],
    )


# ------------------------------------------------------------------------------ the output
def write_plan_md(result: CardStatsPlan, export: Export, path: Path) -> None:
    plan, lane, c = result.plan, result.plan.lane, result.counters
    add = (lines := []).append
    add(f"# Phase 6 item 4 - card_stats recomputed as the generator would: plan ({lane.name})")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/card_stats.py` from the production "
        f"export `{export.sha256}` ({export.exported_at}). Lane `{lane.name}`: run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`, change keys "
        f"`{lane.key_prefix}:<site_id>:<column>`, target `card_stats.site_id`."
    )
    add("")
    add(
        f"**{c['cells']} cell(s) over {c['changed_rows']} of {c['recomputed_rows']} card(s) will be "
        f"written, {c['skipped']} refused.** {c['changed_rows_on_journalled_sites']} of the changed "
        "cards belong to sites with a journalled field write; the others change only because a "
        "`(site_type, period_name)` share moved."
    )
    add("")
    add("## The model is the generator's, and it reproduces the stored cards")
    add("")
    add(
        f"Counterfactual: {c['counterfactual_journal_rows_undone']} journalled input value(s) put "
        f"back, recomputed with `generator.site_card_stats()`: **{c['counterfactual_cells_differing']} "
        f"of {c['counterfactual_cells_compared']} cells differ** from the stored `card_stats`. The "
        "empires are ordered as production lists its boundary directories: "
        + ", ".join(f"`{e}`" for e in export.empire_order)
        + "."
    )
    add("")
    add("## Cells per column")
    add("")
    add("| column | cells |")
    add("|---|---|")
    for column in COLUMNS:
        add(f"| `{column}` | {c[f'cells:{column}']} |")
    add("")
    add("## rarity_tier moves")
    add("")
    add("| from | to | cards |")
    add("|---|---|---|")
    for (old, new), n in sorted(result.tier_moves.items()):
        add(f"| {old} {RARITY_NAMES.get(old, '')} | {new} {RARITY_NAMES.get(new, '')} | {n} |")
    add("")
    add(
        f"{sum(n for (o, w), n in result.tier_moves.items() if w > o)} card(s) move up, "
        f"{sum(n for (o, w), n in result.tier_moves.items() if w < o)} down."
    )
    add("")
    add("## category_group moves")
    add("")
    add("| from | to | cards |")
    add("|---|---|---|")
    for (old, new), n in sorted(result.group_moves.items(), key=lambda kv: (-kv[1], kv[0])):
        add(f"| {old} | {new} | {n} |")
    add("")
    if plan.skipped:
        add("## Refusals")
        add("")
        for reason, n in sorted(Counter(s.reason for s in plan.skipped).items()):
            add(f"* `{reason}`: {n}")
        add("")
    add("## Re-run after every later write wave")
    add("")
    add("```bash")
    add(
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export"
    )
    add(
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write"
    )
    add(
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit"
    )
    add("```")
    add("")
    add(
        "A wave that is applied must plan 0 cells on its next export: that is the read-back that "
        "the recompute is complete."
    )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_statements_or_none(plan: Plan, out: Path) -> bool:
    """The undo of a plan with cells - or, for a plan with none, no statement at all.

    A wave re-planned after its apply must plan 0 cells: that is the read-back that the recompute
    is complete. An empty plan has no transaction to render (`render_transaction` refuses one),
    and a statement left in the directory from an earlier plan is not this plan's: it is removed,
    so `apply.py` finds nothing to send instead of a stale file its pin would refuse anyway.
    """
    if plan.changes:
        write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
        return True
    for stale in ("APPLY.sql", "ROLLBACK.sql"):
        if (out / stale).exists():
            (out / stale).unlink()
            log.info("removed %s: it belonged to an earlier plan of this wave", out / stale)
    log.info("0 cells: the stored card_stats are what the generator computes")
    return False


# ------------------------------------------------------------------------------------- CLI
def lane_directory(lane: Lane) -> Path:
    return REPO / "output" / "remediation" / lane.out_dir_name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the card_stats recompute (mechanical lane)")
    ap.add_argument(
        "--wave", default=FIRST_WAVE, help=f"the wave's date label (default {FIRST_WAVE})"
    )
    ap.add_argument(
        "--out", type=Path, help="default: output/remediation/mechanical_card_stats/<wave>"
    )
    ap.add_argument(
        "--export", action="store_true", help="read production (read-only) into export/"
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="plan from export/: PLAN.jsonl, PLAN.md, SKIPPED.jsonl, ROLLBACK.sql (no database)",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    lane = card_stats_lane(args.wave)
    out = args.out if args.out is not None else lane_directory(lane)
    if not (args.export or args.write):
        ap.print_help()
        return 0
    try:
        if args.export:
            path = write_export(out / "export")
            log.info("export written: %s", path)
        if args.write:
            export = load_export(out / "export")
            check_boundaries(export.empire_order)
            result = build_card_stats_plan(export, lane, built_at=_now())
            out.mkdir(parents=True, exist_ok=True)
            write_plan_jsonl(result.plan, out / "PLAN.jsonl")
            write_skipped_jsonl(result.plan, out / "SKIPPED.jsonl")
            write_plan_md(result, export, out / "PLAN.md")
            write_statements_or_none(result.plan, out)
            print(json.dumps(dict(result.counters), indent=1, sort_keys=True))
            print(
                "rarity_tier moves:",
                json.dumps({f"{o}->{n}": k for (o, n), k in sorted(result.tier_moves.items())}),
            )
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    os.chdir(REPO)
    raise SystemExit(main())
