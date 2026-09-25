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
* **The counterfactual.** Rebuild the inputs the stored cards were computed from - their *basis* -
  and recompute: the result must equal the stored `card_stats` cell for cell, or the plan is
  refused - a model that cannot reproduce the stored cards would mix its own error into every
  change it plans. Measured 2026-09-23 on the first wave: 0 of 60,048 cells differ.

## The basis a wave's proof stands on (`resolve_basis`)

A card reads `unified_sites` - every write to it is journalled - and four tables no remediation
write journals: content links, wiki images, likes and bookmarks (`UNJOURNALLED`). So a basis is
a journal horizon (`since`: every journalled input value written after it is put back) plus the
unjournalled inputs of every curated site as they were at that horizon. Every `--write` records
its own in `BASIS.json` (versioned): the export's journal horizon, its unjournalled inputs, the
cells it planned (as a digest) and refused, and the basis its own proof stood on. The last
card_stats row of the journal in one of the twelve columns names the basis the stored cards have
now (Phase 5's `card_description` rows are neither an input nor a cell of the recompute, and are
not read):

* no such row at all - the first wave: every journalled input put back, and the unjournalled
  inputs as exported (they were never written by the remediation);
* the last row is wave W's write - W's own export: after W, every card W recomputed is what the
  generator computes from it, except the cells W refused;
* the last row is W's undo - the basis W's proof stood on, since the undo restored what W found;
* anything else - a write to the twelve columns this lane did not make - refuses: no basis
  explains it.

The basis wave's journal rows must be exactly the cells its `BASIS.json` names (and an undo's
rows their exact inverse), so a `BASIS.json` of a plan that was not the one applied refuses too.
A like, a new content link or a journalled write that lands between an export and its apply is
therefore put back, not mistaken for a model error (measured before this rule: one like on a
curated site made every later wave refuse to plan).

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

## The undo holds only while the premise does

`ROLLBACK.sql` carries the same guard 5 as the write: the undo refuses once any curated site's
`site_type` or `period_name` has been written anywhere, or any input of a planned site has moved
(its fields, content links, images, likes, bookmarks). That is deliberate - restoring old cards
over moved inputs restores values that were derived from nothing the database still holds - but
it means the versioned `ROLLBACK.sql` is usable only until the next such write. After that a
wave is not undone from its file: the cards are recomputed by the next wave (the recompute of the
inputs as they are is the correct state), or a reversal is planned from the journal as a new
decision - no lane plans a card_stats reversal from the journal today.

`--export` reads production (read-only, one `READ ONLY` transaction) into
`output/remediation/mechanical_card_stats/<wave>/export/`; `--write` plans from that export and
writes `PLAN.jsonl`, `PLAN.md`, `SKIPPED.jsonl`, `BASIS.json`, `ROLLBACK.sql`. `apply.py --lane
card-stats-<wave>` renders and runs the transaction. `BASIS.json` and `ROLLBACK.sql` are the
applied plan's only when they come from the `--write` run that was applied: commit them after the
last re-plan before the apply.

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

from prod_write import SSH_HOST, SSH_OPTIONS  # noqa: E402

from api.cardgame.constants import GROUP_FORTIFICATION, RARITY_NAMES  # noqa: E402
from mechanical.apply import lane_dir  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CARD_STATS,
    CARD_STATS_LANE,
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
    parse_tagged_export,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
    write_tagged_export,
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
    """The card_stats recompute of one wave: its own stamp, key prefix and directory.

    `wave` is a date label (`2026-09-24`, `2026-09-24b`): the only labels `apply.py --lane
    card-stats-<wave>` resolves, so a plan written under any other label could never be applied.
    """
    if CARD_STATS_LANE.match(f"card-stats-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-09-24 or 2026-09-24b")
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
    """The sites and the journal from one read-only snapshot, tagged by kind."""
    return tagged_export_script((("site", EXPORT_SITES_SQL), ("journal", EXPORT_JOURNAL_SQL)))


@dataclass(frozen=True)
class Export:
    """What the recompute reads: the curated rows, the journal, and production's empire order."""

    sites: tuple[dict[str, Any], ...]
    journal: tuple[dict[str, Any], ...]
    empire_order: tuple[str, ...]
    exported_at: str
    sha256: str


def parse_export(text: str, empire_order: Sequence[str]) -> Export:
    """The export's tagged lines as an `Export` (`plan.parse_tagged_export` refuses a line of
    another kind and an export without its one snapshot line)."""
    rows, exported_at = parse_tagged_export(text, ("site", "journal"))
    if not rows["site"]:
        raise PlanError("the export holds no curated site - refusing to plan against nothing")
    if not empire_order:
        raise PlanError("the export carries no empire order")
    return Export(
        sites=tuple(rows["site"]),
        journal=tuple(rows["journal"]),
        empire_order=tuple(empire_order),
        exported_at=exported_at,
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
    path = write_tagged_export(export_script(), directory / "export.jsonl", host=host)
    order = production_empire_order(host)
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


#: The inputs of a card that live outside `unified_sites`, in tables no remediation write
#: journals - as the export names them (`EXPORT_SITES_SQL`).
UNJOURNALLED = ("links", "wiki_images", "likes", "bookmarks")
BASIS_FILE = "BASIS.json"


@dataclass(frozen=True)
class Basis:
    """The inputs a set of stored cards was computed from.

    `since`: every journalled input value written after this journal id is put back, and
    `journal_rows` is how many exported journal rows the basis saw at or below it - a row that
    commits below the horizon after the export would otherwise pass for one the basis saw.
    `unjournalled`: each curated site's `UNJOURNALLED` inputs at that horizon. `excluded`: the
    `(site_id, column)` cells the basis does not explain - cells its wave refused to write.
    """

    label: str
    since: int
    unjournalled: Mapping[str, Mapping[str, Any]]
    journal_rows: int = 0
    excluded: frozenset[tuple[str, str]] = frozenset()


def unjournalled_of(sites: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each site's unjournalled inputs, as the export holds them."""
    return {str(row["id"]): {key: row[key] for key in UNJOURNALLED} for row in sites}


def encode_unjournalled(inputs: Mapping[str, Any]) -> list[Any]:
    """One site's unjournalled inputs as `BASIS.json` keeps them: the content links as a multiset
    (`[type, source, count]`, sorted - `generator.content_stats` reads no order), then the three
    counts."""
    pairs = Counter((link[0], link[1]) for link in inputs["links"])
    links = [[a, b, n] for (a, b), n in sorted(pairs.items(), key=lambda kv: (str(kv[0]), kv[1]))]
    return [links, int(inputs["wiki_images"]), int(inputs["likes"]), int(inputs["bookmarks"])]


def decode_unjournalled(encoded: Sequence[Any]) -> dict[str, Any]:
    """`encode_unjournalled`, read back."""
    links, wiki_images, likes, bookmarks = encoded
    return {
        "links": [[a, b] for a, b, n in links for _ in range(int(n))],
        "wiki_images": int(wiki_images),
        "likes": int(likes),
        "bookmarks": int(bookmarks),
    }


def cells_digest(cells: Iterable[tuple[str, str, str | None, str | None]]) -> str:
    """sha256 of a set of `(site_id, column, old, new)` cells, order-free: what a wave planned,
    compared with what its journal rows say it wrote."""
    lines = sorted(json.dumps(list(cell), ensure_ascii=False) for cell in cells)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def first_wave_basis(sites: Sequence[Mapping[str, Any]]) -> Basis:
    """No card_stats row was ever journalled: every journalled input goes back to its first old
    value, and the unjournalled inputs are as exported - the state the generator last saw."""
    return Basis(
        "the first wave's: every journalled input value put back, the unjournalled inputs as "
        "exported",
        since=0,
        unjournalled=unjournalled_of(sites),
    )


def basis_pointer(journal: Sequence[Mapping[str, Any]]) -> tuple[str, str] | None:
    """`(wave, side)` of the basis the stored cards have now, read off the last card_stats journal
    row of the twelve columns: `after` a wave's write, `before` it once its undo ran. `None` when
    no such row was ever journalled.

    A row of another card_stats column is not read: Phase 5 journals `card_description`
    (`phase4/write4.py`, `phase5:p5-NNNN:chunk-NNNN`), which is neither an input nor a cell of
    the recompute, so it cannot change what the proof compares.
    """
    cards = [j for j in journal if j["table_name"] == "card_stats" and j["column_name"] in COLUMNS]
    if not cards:
        return None
    last = max(cards, key=lambda j: int(j["id"]))
    stamp = str(last["run_stamp"])
    wave = stamp.partition("_")[0]
    if CARD_STATS_LANE.match(f"card-stats-{wave}") is not None:
        lane = card_stats_lane(wave)
        if stamp == lane.run_stamp:
            return wave, "after"
        if stamp == lane.rollback_run_stamp:
            return wave, "before"
    raise PlanError(
        f"card_stats journal row {last['id']} was written by {stamp!r}, which is no card_stats "
        "wave's write or undo: no basis explains the stored cards"
    )


def read_basis_file(wave: str) -> Mapping[str, Any]:
    """A wave's `BASIS.json`, as its `--write` left it (versioned with the wave)."""
    path = lane_dir(card_stats_lane(wave)) / BASIS_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - the basis of wave {wave} is what the proof needs")
    return json.loads(path.read_text(encoding="utf-8"))


def check_basis_journal(
    record: Mapping[str, Any], journal: Sequence[Mapping[str, Any]], side: str
) -> None:
    """The basis wave's journal rows are the cells its `BASIS.json` names - and, for `before`,
    its undo's rows their exact inverse - or the file is not the applied plan's."""
    lane = card_stats_lane(str(record["wave"]))

    def cells(stamp: str, *, inverted: bool) -> list[tuple[str, str, Any, Any]]:
        return [
            (
                str(j["row_pk"]),
                str(j["column_name"]),
                j["new_value"] if inverted else j["old_value"],
                j["old_value"] if inverted else j["new_value"],
            )
            for j in journal
            if j["table_name"] == "card_stats" and j["run_stamp"] == stamp
        ]

    wrote = cells(lane.run_stamp, inverted=False)
    if cells_digest(wrote) != record["cells_sha256"]:
        raise PlanError(
            f"the journal holds {len(wrote)} card_stats row(s) of {lane.run_stamp}, and they are "
            f"not the {record['cells']} cell(s) {BASIS_FILE} of wave {record['wave']} planned: that "
            "file is not the applied plan's"
        )
    if side == "before":
        undone = cells(lane.rollback_run_stamp, inverted=True)
        if cells_digest(undone) != record["cells_sha256"]:
            raise PlanError(
                f"the undo of wave {record['wave']} journalled {len(undone)} row(s) that are not "
                "the exact inverse of its write: the stored cards are neither wave's"
            )


def resolve_basis(
    pointer: tuple[str, str] | None,
    export: Export,
    bases: Callable[[str], Mapping[str, Any]],
) -> Basis:
    """The basis a pointer names (`basis_pointer`), read from the waves' `BASIS.json` files."""
    if pointer is None:
        return first_wave_basis(export.sites)
    wave, side = pointer
    record = bases(wave)
    if record["wave"] != wave:
        raise PlanError(f"the {BASIS_FILE} read for wave {wave} is wave {record['wave']}'s")
    check_basis_journal(record, export.journal, side)
    unjournalled = {sid: decode_unjournalled(v) for sid, v in record["unjournalled"].items()}
    if side == "after":
        return Basis(
            f"wave {wave}'s own export ({record['exported_at']})",
            since=int(record["journal_max_id"]),
            unjournalled=unjournalled,
            journal_rows=int(record["journal_rows"]),
            excluded=frozenset((str(s), str(c)) for s, c in record["refused_cells"]),
        )
    inner = record["proof_basis"]
    if inner is None:
        return Basis(
            f"the first wave's, which wave {wave}'s undo restored: every journalled input value "
            "put back, the unjournalled inputs as that wave exported them",
            since=0,
            unjournalled=unjournalled,
        )
    return resolve_basis((str(inner["wave"]), str(inner["side"])), export, bases)


def counterfactual_sites(
    sites: Sequence[Mapping[str, Any]], journal: Sequence[Mapping[str, Any]], basis: Basis
) -> tuple[list[dict[str, Any]], int]:
    """The rows as they were at the basis: every journalled input value written after its horizon
    is put back, newest first, and every unjournalled input is the basis's. Returns the rows and
    how many journal rows were undone.

    Refused unless the curated sites are the basis's own: a site added or removed since changes
    every `mystery` share it takes part in, and no basis says what it was.
    """
    by_id = {row["id"]: dict(row) for row in sites}
    if set(by_id) != set(basis.unjournalled):
        added, gone = set(by_id) - set(basis.unjournalled), set(basis.unjournalled) - set(by_id)
        raise PlanError(
            f"the curated sites are not the basis's ({basis.label}): {len(added)} added "
            f"{sorted(added)[:3]}, {len(gone)} gone {sorted(gone)[:3]}"
        )
    seen = sum(1 for j in journal if int(j["id"]) <= basis.since)
    if seen != basis.journal_rows:
        raise PlanError(
            f"the journal holds {seen} row(s) at or below the horizon {basis.since} of the basis "
            f"({basis.label}), the basis saw {basis.journal_rows}: a row committed below the "
            "horizon after that export, and the basis does not know what it changed"
        )
    for row in by_id.values():
        row.update(basis.unjournalled[row["id"]])
    undone = 0
    for entry in sorted(journal, key=lambda j: int(j["id"]), reverse=True):
        if entry["table_name"] != "unified_sites" or int(entry["id"]) <= basis.since:
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
    sites: Sequence[Mapping[str, Any]],
    computed: Mapping[str, Mapping[str, Any]],
    excluded: frozenset[tuple[str, str]] = frozenset(),
) -> list[tuple[str, str, Any, Any]]:
    """`(site_id, column, stored, computed)` for every cell the recompute would change, except the
    `excluded` cells (the ones a basis does not explain)."""
    out = []
    for row in sites:
        stats = computed.get(row["id"])
        if stats is None or not row["has_card"]:
            continue
        for column in COLUMNS:
            if (row["id"], column) in excluded:
                continue
            if stored(row, column) != stats[column]:
                out.append((row["id"], column, stored(row, column), stats[column]))
    return out


@dataclass(frozen=True)
class Proof:
    """The counterfactual that passed: the basis it stood on, and what it measured."""

    basis: Basis
    pointer: tuple[str, str] | None
    counters: Mapping[str, int]


def prove_the_model(
    export: Export,
    generator: Any = None,
    *,
    bases: Callable[[str], Mapping[str, Any]] = read_basis_file,
) -> Proof:
    """The counterfactual, measured: refuse to plan unless the stored cards are what the model
    computes from their basis (`resolve_basis`)."""
    pointer = basis_pointer(export.journal)
    basis = resolve_basis(pointer, export, bases)
    rows, undone = counterfactual_sites(export.sites, export.journal, basis)
    computed = recompute(rows, export.empire_order, generator=generator)
    differ = diff_cells(rows, computed, basis.excluded)
    if differ:
        sample = ", ".join(f"{sid}/{col}: {old!r} vs {new!r}" for sid, col, old, new in differ[:5])
        raise PlanError(
            f"the counterfactual (basis: {basis.label}; journal undone: {undone} rows) does not "
            f"reproduce the stored card_stats: {len(differ)} cell(s) differ ({sample}) - the "
            "model must be explained before it plans a write"
        )
    compared = sum(
        1
        for r in rows
        if r["id"] in computed and r["has_card"]
        for column in COLUMNS
        if (r["id"], column) not in basis.excluded
    )
    return Proof(
        basis=basis,
        pointer=pointer,
        counters={
            "counterfactual_journal_rows_undone": undone,
            "counterfactual_cells_compared": compared,
            "counterfactual_cells_differing": 0,
        },
    )


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class CardStatsPlan:
    plan: Plan
    proof: Proof
    counters: Mapping[str, int] = field(default_factory=dict)
    tier_moves: Mapping[tuple[int, int], int] = field(default_factory=dict)
    group_moves: Mapping[tuple[str, str], int] = field(default_factory=dict)


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
    export: Export, computed: Mapping[str, Mapping[str, Any]], proof: Proof
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
        "card_stats in all {cells} cells{basis}".format(
            undone=proof.counters["counterfactual_journal_rows_undone"],
            cells=proof.counters["counterfactual_cells_compared"],
            basis="" if proof.pointer is None else f" (basis: {proof.basis.label})",
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
    export: Export,
    lane: Lane,
    *,
    built_at: str,
    generator: Any = None,
    bases: Callable[[str], Mapping[str, Any]] = read_basis_file,
) -> CardStatsPlan:
    """A pure function of the export and the earlier waves' `BASIS.json`: no database, no clock of
    its own."""
    applied = sum(1 for j in export.journal if j["run_stamp"] == lane.run_stamp)
    if applied:
        raise PlanError(
            f"the journal holds {applied} row(s) of {lane.run_stamp}: wave {lane.name} is applied, "
            "and re-planning it would overwrite the BASIS.json and ROLLBACK.sql of that write - "
            "plan the next wave under a label of its own"
        )
    check_jsonb_spelling(export.sites)
    proof = prove_the_model(export, generator, bases=bases)
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
        **proof.counters,
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
        proof=proof,
        counters=counters,
        tier_moves=dict(tier_moves),
        group_moves=dict(group_moves),
    )


def basis_record(result: CardStatsPlan, export: Export, wave: str) -> dict[str, Any]:
    """What `BASIS.json` keeps of a plan: the basis its cards will stand on once applied (the
    export's journal horizon and unjournalled inputs, the cells planned and refused), and the
    basis its own proof stood on - which the undo of this wave restores."""
    plan = result.plan
    pointer = result.proof.pointer
    return {
        "wave": wave,
        "export_sha256": export.sha256,
        "exported_at": export.exported_at,
        "journal_max_id": max((int(j["id"]) for j in export.journal), default=0),
        "journal_rows": len(export.journal),
        "cells": len(plan.changes),
        "cells_sha256": cells_digest(
            (c.site_id, str(c.column), c.old_value, c.new_value) for c in plan.changes
        ),
        "refused_cells": sorted(
            [s.site_id, s.column] for s in plan.skipped if s.column is not None
        ),
        "proof_basis": None if pointer is None else {"wave": pointer[0], "side": pointer[1]},
        "unjournalled": {
            sid: encode_unjournalled(inputs)
            for sid, inputs in sorted(unjournalled_of(export.sites).items())
        },
    }


def write_basis_json(record: Mapping[str, Any], path: Path) -> None:
    """`BASIS.json`: the header fields one per line, then one line per site, so a later wave's
    change to it reads as a diff of the sites that moved."""
    head = {
        "_about": "The basis of one card_stats wave (scripts/remediation/mechanical/card_stats.py, "
        "resolve_basis). Written by --write; the applied plan's only when it comes from the "
        "--write run that was applied.",
        **{k: v for k, v in record.items() if k != "unjournalled"},
    }
    lines = ["{"]
    lines += [f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}," for k, v in head.items()]
    lines.append(' "unjournalled": {')
    lines.append(
        ",\n".join(
            f"  {json.dumps(sid)}: {json.dumps(value, ensure_ascii=False)}"
            for sid, value in record["unjournalled"].items()
        )
    )
    lines += [" }", "}", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


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
    add(
        f"The basis the proof stood on: {result.proof.basis.label} (journal horizon "
        f"{result.proof.basis.since}, `card_stats.resolve_basis`). This plan's own basis is in "
        f"`{BASIS_FILE}` next to this file: the export's journal horizon, every curated site's "
        "content links, images, likes and bookmarks, and the cells planned. The next wave's proof "
        "reads it - commit it with the plan that is applied, and never re-plan an applied wave "
        "(`--write` refuses one whose run stamp is in the journal)."
    )
    add("")
    add("## The undo holds only while the premise does")
    add("")
    add(
        "`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's "
        "`site_type` or `period_name` has been written anywhere, or any input of a planned site "
        "has moved (its fields, content links, images, likes, bookmarks). From then on this wave "
        "is not undone from its file: the next wave recomputes the cards from the inputs as they "
        "are, or a reversal is planned from the journal as a new decision (no lane does that for "
        "card_stats today)."
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
        "A wave that is applied must plan 0 cells on the next wave's export, re-planned under a "
        "new label (`--wave <wave>b`): that is the read-back that the recompute is complete."
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
def _wave_argument(value: str) -> str:
    """`--wave`: a label `apply.py --lane card-stats-<wave>` resolves; anything else is argparse's
    error, before a plan is written under a name nothing could apply."""
    try:
        card_stats_lane(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the card_stats recompute (mechanical lane)")
    ap.add_argument(
        "--wave",
        type=_wave_argument,
        default=FIRST_WAVE,
        help=f"the wave's date label, like 2026-09-24 or 2026-09-24b (default {FIRST_WAVE})",
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
        help="plan from export/: PLAN.jsonl, PLAN.md, SKIPPED.jsonl, BASIS.json, ROLLBACK.sql "
        "(no database)",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    lane = card_stats_lane(args.wave)
    out = args.out if args.out is not None else lane_dir(lane)
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
            write_basis_json(basis_record(result, export, args.wave), out / BASIS_FILE)
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
