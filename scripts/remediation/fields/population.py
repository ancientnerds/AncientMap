"""WD3 step 1: the open fields of the curated sites, and the run that asks them.

Lane WD3 (`rule.py`, the `one-family` rule) is WD1 again for the fields WD1 left open. A field is
**open** when no source stands behind what the database holds for it:

* `empty` - the column holds nothing: `period_start` NULL, `site_type` or `source_url` NULL or
  empty (read from production now, after WD1's clears landed). `lat`/`lon` are NOT NULL;
* `unresolved` - the stored point: WD1 found no two independent sources for it (a counted
  `unresolved` answer, or exhausted after three rounds). A site WD1 never saw is read by the
  machine's own status: a point no witness confirms is open. A point a journalled lane wrote with
  sourced evidence is **not** open, whatever WD1 decided before: the site's newest lat/lon journal
  row carries `two_source`, `authoritative` or `one_source` confidence and the value the row holds
  now (`POINTS.jsonl`, one SELECT) - another lane's sourced write is never asked again;
* `held` - WD1 held the field because the pages its agents cited could not be read (`HELD.jsonl` of
  its waves), so the stored value neither got a source nor was cleared;
* `unsourced` - WD1 decided `clear`, the value is still stored: the clear was refused at write
  (the step's SKIPPED.jsonl names why). It has no source either.

A field WD1 decided `keep` or `replace` stands on two quotes and is **never asked again**; a site
that is retired is not in the run. A site with at least one open field gets one question with exactly
those fields. What the question shows beyond WD1's: the field's open reason, WD1's reasoning for it (a
lead, not evidence) and the site's own links - `site_content_links`, the link icons of its page - with
its stored source_url (`LINKS.jsonl`, one SELECT).

    population.py --out DIR export                 STORED.jsonl, LINKS.jsonl, POINTS.jsonl, MADE.jsonl and
                                                   an empty SEEDS.jsonl
                                                   (a WD3 run asks no seeded field: WD1 asked them)
    population.py --out DIR build --root HARVEST [--pilot N --seed S | --without RUN]
                                                   RUN.json (the rule, pinned), CLASSIFIED.jsonl and
                                                   COUNTS.json - from files only

`HARVEST` is a copy of the shared harvest, refreshed (`harvest.py --root HARVEST export`, then
`fetch`): the shared one stays as the other lanes read it, and WD1's writes moved points and URLs
that the stored export must agree with (`classify.py` refuses a harvest and an export of different
states). The run reads WD1's own records - the four runs' CLASSIFIED/DECISIONS and the waves' HELD.jsonl
under `output/remediation/fields/wd1/write/` - and refuses a WD1 wave that is not fully accepted: the
population is what is left after WD1's writes landed.

**Lane wd5** (`rule.RECHECK`, owner decisions D10, D12, D19 of 2026-10-08) asks the fields that stand
without a source *behind a value the database holds*, not the empty ones (`recheck_fields`):

* `rule-made` - a `period_start` whose newest journal row carries evidence `status: RULE` and the
  value the row holds now (`MADE.jsonl`, one SELECT; 1,254 sites on 2026-10-08);
* `minimax-answered` - a field the newest journal row of which a MiniMax agent wrote, or which the
  latest decision of WD1, WD3 or WD4 names a MiniMax model for (`history`): its calibration failed
  at 64.71 % (bar 90 %), so whatever it decided - a value, a keep, no value - no reliable pass has
  checked a source for it;
* `unsourced-point` - a point no journalled lane and no counted answer sourced: the latest decision
  is `unresolved`/`held`, or a better point that a guard refused, or a site no pass asked whose
  machine status is not confirmed.

A field whose newest journal row is another lane's sourced write is never asked, whatever else
says so. The question shows the stored value, why it is asked and what stands (`open[field]["made"]`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.plan import psql_json_reader, sql_ids  # noqa: E402

from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import dates as D  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import rule as R  # noqa: E402
from pipeline import periods as P  # noqa: E402

WHY_EMPTY, WHY_UNRESOLVED, WHY_HELD, WHY_UNSOURCED = "empty", "unresolved", "held", "unsourced"
#: The reasons of lane wd5 (`recheck_fields`).
WHY_RULE_MADE, WHY_MINIMAX, WHY_UNSOURCED_POINT = "rule-made", "minimax-answered", "unsourced-point"
#: The reason of a wd5 run built with `--reask-cleared` / `--sites` (`reader_gap_fields`): an empty
#: period a counted Claude answer left `unresolved` although its reasoning names a dated value.
WHY_READER_GAP = "reader-gap"
WHYS = (
    WHY_EMPTY, WHY_UNRESOLVED, WHY_HELD, WHY_UNSOURCED,
    WHY_RULE_MADE, WHY_MINIMAX, WHY_UNSOURCED_POINT, WHY_READER_GAP,
)  # fmt: skip
HELD = "held"  # `handoff.HELD`, the import's decision for a field whose pages could not be read

FIELDS_DIR = REPO / "output" / "remediation" / "fields"
WD1_RUN_NAMES = ("wd1-pilot", "wd1", "wd1-rest-pilot", "wd1-rest")
DEFAULT_OUT = FIELDS_DIR / "wd3"
LINKS_FILE = "LINKS.jsonl"
POINTS_FILE = "POINTS.jsonl"
MADE_FILE = "MADE.jsonl"
#: The journal confidences that stand for a sourced value (`remediation_change_log.confidence`):
#: two quotes (`two_source`, WD1 and the owner-case lanes), a register (`authoritative`), one quote
#: (`one_source`, WD3). `opus-checked` is a judgement without a quoted source: not one of them.
SOURCED_CONFIDENCE = frozenset({"two_source", "authoritative", "one_source"})
#: How a question describes WD1's decision of a field: the first characters of its reasoning.
WD1_SHOWN_CHARS = 600

LINKS_SQL = """\
SELECT u.id::text AS site_id,
       coalesce((SELECT json_agg(json_build_object(
                    'title', l.title, 'url', l.content_url,
                    'type', coalesce(l.link_metadata->>'link_type', l.content_type),
                    'domain', l.link_metadata->>'domain', 'score', l.relevance_score)
                  ORDER BY l.relevance_score DESC NULLS LAST, l.id)
                   FROM site_content_links l WHERE l.site_id = u.id), '[]'::json) AS links
  FROM unified_sites u
 WHERE u.source_id = 'ancient_nerds'
 ORDER BY u.id"""
LINK_KEYS = ("title", "url", "type", "domain", "score")
#: The newest journal row of each curated site's `lat` or `lon` (the point is written whole, but
#: only a coordinate that changed is journalled: the newest row of the two is the last write).
POINTS_SQL = """\
SELECT DISTINCT ON (c.row_pk) c.row_pk AS site_id, c.column_name, c.run_stamp,
       c.confidence, c.new_value
  FROM remediation_change_log c
  JOIN unified_sites u ON u.id::text = c.row_pk
 WHERE c.table_name = 'unified_sites' AND c.column_name IN ('lat', 'lon')
   AND u.source_id = 'ancient_nerds'
 ORDER BY c.row_pk, c.id DESC"""
POINT_KEYS = ("site_id", "column_name", "run_stamp", "confidence", "new_value")

#: The newest journal row of each curated site's `lat`, `lon`, `period_start`, `site_type` and
#: `source_url`, with what its evidence says of who made the value: a rule (`status: RULE`, the
#: `reasoning` of that entry is the rule's) or a MiniMax agent (an entry's `model`). A site no lane
#: ever moved has no row. Read-only; the journal is the truth of how a value came to be.
MADE_SQL_TEMPLATE = """\
SELECT DISTINCT ON (c.row_pk, c.column_name) c.row_pk AS site_id, c.column_name, c.run_stamp,
       c.confidence, c.new_value, e.rule_made, e.minimax, e.withdrawn, e.note
  FROM remediation_change_log c
  JOIN unified_sites u ON u.id::text = c.row_pk
 CROSS JOIN LATERAL (
       SELECT coalesce(bool_or(x ->> 'status' = 'RULE'), false) AS rule_made,
              coalesce(bool_or(lower(coalesce(x ->> 'model', '')) LIKE '%minimax%'), false)
                AS minimax,
              coalesce(bool_or(x ->> 'decision' = 'unresolved'), false) AS withdrawn,
              max(CASE WHEN x ->> 'status' = 'RULE' THEN x ->> 'reasoning' END) AS note
         FROM jsonb_array_elements(CASE WHEN jsonb_typeof(c.evidence) = 'array'
                                        THEN c.evidence ELSE '[]'::jsonb END) x) e
 WHERE c.table_name = 'unified_sites'
   AND c.column_name IN ('lat', 'lon', 'period_start', 'site_type', 'source_url')
   AND u.source_id = 'ancient_nerds'{only}
 ORDER BY c.row_pk, c.column_name, c.id DESC"""
MADE_SQL = MADE_SQL_TEMPLATE.format(only="")


def made_sql(site_ids: Sequence[str]) -> str:
    """`MADE_SQL` for these sites only - the write plan reads the step's own."""
    return MADE_SQL_TEMPLATE.format(only=f"\n   AND c.row_pk IN ({sql_ids(site_ids)})")


MADE_KEYS = (*POINT_KEYS, "rule_made", "minimax", "withdrawn", "note")
#: The column(s) a field is stored in.
FIELD_COLUMNS = {
    "coordinates": ("lat", "lon"),
    "period_start": ("period_start",),
    "site_type": ("site_type",),
    "source_url": ("source_url",),
}
RULE, MINIMAX, SOURCED = "rule", "minimax", "sourced"
#: How much of a MiniMax answer's reasoning the question quotes.
MADE_SHOWN_CHARS = 400


class PopulationError(RuntimeError):
    """The population cannot be built from these inputs. Nothing is written."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise PopulationError(f"{path} is missing")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------------------ WD1's records
@dataclass(frozen=True)
class Wd1:
    """What WD1 decided: each (site, field)'s decision, the sites it classified, and the held
    pairs its waves listed."""

    decisions: Mapping[tuple[str, str], Mapping[str, Any]]
    classified: frozenset[str]
    held: frozenset[tuple[str, str]]
    runs: tuple[str, ...]
    waves: tuple[str, ...]


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        # the resolved path, never the path as spelled: a run reached through a junction or a
        # `..` component is the same run, and the waves compare this string (2026-10-04)
        return path.resolve().as_posix()


def _names_run(recorded: str, run: Path) -> bool:
    """Whether a wave's recorded run (a path relative to the repository that planned it) is `run`:
    the main checkout's runs are read from a worktree too. An absolute record is compared as it is."""
    here = run.resolve().as_posix()
    if Path(recorded).is_absolute():
        return Path(recorded).resolve().as_posix() == here
    return here.endswith("/" + recorded.removeprefix("./"))


def _wave_held(wave: Path) -> tuple[str, list[tuple[str, str]]]:
    """A WD1 wave's run and the (site, field) pairs of its HELD.jsonl - refused unless the wave is
    the pinned file and every one of its steps is accepted with 0 deviations."""
    record_path = wave / "WAVE.json"
    if _sha256_text(record_path) != (wave / "WAVE.sha256").read_text(encoding="utf-8").strip():
        raise PopulationError(f"{record_path} is not the pinned wave: it was edited")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    for number in range(1, len(record["steps"]) + 1):
        accepted = wave / f"s{number:03d}" / "ACCEPTED.json"
        if not accepted.exists():
            raise PopulationError(f"{wave.name} step {number} is not accepted ({accepted})")
        if json.loads(accepted.read_text(encoding="utf-8"))["deviations"] != 0:
            raise PopulationError(f"{wave.name} step {number} was accepted with deviations")
    held = _read_jsonl(wave / "HELD.jsonl")
    return str(record["run"]), [(row["site_id"], row["field"]) for row in held]


def wd1_files(fields_dir: Path = FIELDS_DIR) -> tuple[list[Path], Path]:
    """WD1's four runs and the directory of its waves, under `fields_dir`."""
    return [fields_dir / name for name in WD1_RUN_NAMES], fields_dir / "wd1" / "write"


def read_wd1(runs: Sequence[Path], waves: Path) -> Wd1:
    """WD1's four runs: every decision (a cell decided by two runs is refused), the sites classified,
    and the held pairs of the waves that wrote them. Each run's unresolved and held decisions must
    be exactly the pairs its waves listed - a run whose wave was not planned has nothing written."""
    decisions: dict[tuple[str, str], Mapping[str, Any]] = {}
    classified: set[str] = set()
    held_of_run: dict[str, set[tuple[str, str]]] = {}
    for run in runs:
        reask_file = run / "REASK.json"
        if not reask_file.exists():
            raise PopulationError(
                f"{run} is not there - WD1's runs are untracked files of the checkout that holds "
                f"output/, and this one has none; --wd1-dir points the read at that checkout"
            )
        reask = json.loads(reask_file.read_text(encoding="utf-8"))
        if reask["fields"]:
            raise PopulationError(f"{run}: fields still wait for a re-ask - WD1 is not finished")
        rows = _read_jsonl(run / "DECISIONS.jsonl")
        if not rows:
            raise PopulationError(f"{run / 'DECISIONS.jsonl'} holds no decision")
        for row in rows:
            cell = (row["site_id"], row["field"])
            if cell in decisions:
                raise PopulationError(f"{cell} is decided by two WD1 runs")
            decisions[cell] = {**row, "run": _shown(run)}
        classified |= {line["site_id"] for line in _read_jsonl(run / C.CLASSIFIED_FILE)}
        held_of_run[_shown(run)] = {
            (row["site_id"], row["field"])
            for row in rows
            if row["decision"] in (A.UNRESOLVED, HELD)
        }
    listed: dict[str, set[tuple[str, str]]] = {}
    used: list[str] = []
    for wave in sorted(p for p in waves.iterdir() if (p / "WAVE.json").exists()):
        recorded, held = _wave_held(wave)
        for run in runs:
            if _names_run(recorded, run):
                listed.setdefault(_shown(run), set()).update(held)
                used.append(wave.name)
    for run, wanted in held_of_run.items():
        if listed.get(run) != wanted:
            raise PopulationError(
                f"{run}: its decisions hold {len(wanted)} unresolved/held field(s), the HELD.jsonl "
                f"of its waves {len(listed.get(run, ()))} - WD1's records disagree"
            )
    return Wd1(
        decisions,
        frozenset(classified),
        frozenset(cell for held in held_of_run.values() for cell in held),
        tuple(_shown(run) for run in runs),
        tuple(used),
    )


# ------------------------------------------------------------------------------ the open fields
def is_empty(field: str, stored: Mapping[str, Any]) -> bool:
    """Whether the column holds nothing (`''` and NULL both: `site_type` and `source_url` were
    written either way). A point is never empty: `lat`/`lon` are NOT NULL."""
    if field == "coordinates":
        return False
    value = stored[field]
    return value is None or (isinstance(value, str) and not value.strip())


def _wd1_summary(decision: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "decision": decision["decision"],
        "via": decision["via"],
        "run": decision["run"],
        "reasoning": str(decision["reasoning"])[:WD1_SHOWN_CHARS],
    }


def journal_sourced_point(stored: Mapping[str, Any], last: Mapping[str, Any] | None) -> bool:
    """Whether the stored point is the one a journalled lane wrote with sourced evidence: the site's
    newest lat/lon journal row (`POINTS_SQL`) carries a sourced confidence and the value the row
    holds now (compared as numbers: the journal keeps the text a writer gave)."""
    if last is None or last["confidence"] not in SOURCED_CONFIDENCE or last["new_value"] is None:
        return False
    return float(last["new_value"]) == float(stored[last["column_name"] + "_text"])


def open_fields(
    line: Mapping[str, Any],
    stored: Mapping[str, Any],
    wd1: Wd1,
    last_point_write: Mapping[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The open fields of one classified site: `{field: {"why", "wd1"}}`, and the fields WD1 decided
    with sources that are empty now (a state nothing explains - listed, never asked). A point whose
    newest journal row is a sourced write (`last_point_write`) is not open."""
    site = str(line["site_id"])
    seen = site in wd1.classified
    opened: dict[str, dict[str, Any]] = {}
    contradictions: list[str] = []
    for field in C.FIELDS:
        decision = wd1.decisions.get((site, field))
        verdict = None if decision is None else decision["decision"]
        empty = is_empty(field, stored)
        if verdict in (A.KEEP, A.REPLACE):
            if empty:
                contradictions.append(field)
            continue
        if empty:
            why = WHY_EMPTY
        elif field == "coordinates":
            if journal_sourced_point(stored, last_point_write):
                continue
            if verdict in (A.UNRESOLVED, HELD):
                why = WHY_UNRESOLVED
            elif not seen and line["fields"][field]["status"] != C.CONFIRMED:
                why = WHY_UNRESOLVED
            else:
                continue
        elif verdict == HELD:
            why = WHY_HELD
        elif verdict == A.CLEAR:
            why = WHY_UNSOURCED
        else:
            continue
        opened[field] = {"why": why, "wd1": _wd1_summary(decision)}
    return opened, contradictions


# ------------------------------------------------------------------------------ the links
def export_links(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    """LINKS.jsonl: each curated site's own links, best first, from one read-only SELECT."""
    rows = reader(LINKS_SQL)
    if not rows:
        raise PopulationError("the links export returned no curated site")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    tmp = out / (LINKS_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / LINKS_FILE)
    return len(rows)


def read_links(out: Path) -> dict[str, list[dict[str, Any]]]:
    path = out / LINKS_FILE
    if not path.exists():
        raise PopulationError(f"{path} is missing - run `population.py export` first")
    links: dict[str, list[dict[str, Any]]] = {}
    for row in _read_jsonl(path):
        for link in row["links"]:
            if set(link) != set(LINK_KEYS):
                raise PopulationError(
                    f"{path}: a link carries {sorted(link)}, not {sorted(LINK_KEYS)}"
                )
        links[str(row["site_id"])] = row["links"]
    return links


def export_points(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    """POINTS.jsonl: each curated site's newest lat/lon journal row, from one read-only SELECT. A
    site no lane ever moved has none."""
    rows = reader(POINTS_SQL)
    for row in rows:
        if set(row) != set(POINT_KEYS):
            raise PopulationError(f"a point journal row carries {sorted(row)}, not {POINT_KEYS}")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in sorted(rows, key=lambda r: r["site_id"])
    )
    tmp = out / (POINTS_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / POINTS_FILE)
    return len(rows)


def read_points(out: Path) -> dict[str, dict[str, Any]]:
    path = out / POINTS_FILE
    if not path.exists():
        raise PopulationError(f"{path} is missing - run `population.py export` first")
    points: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        if set(row) != set(POINT_KEYS):
            raise PopulationError(f"{path}: a row carries {sorted(row)}, not {sorted(POINT_KEYS)}")
        points[str(row["site_id"])] = row
    return points


def export_made(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    """MADE.jsonl: each curated site's newest journal row per field column, with who made the value
    (`MADE_SQL`), from one read-only SELECT."""
    rows = reader(MADE_SQL)
    for row in rows:
        if set(row) != set(MADE_KEYS):
            raise PopulationError(f"a made-by row carries {sorted(row)}, not {sorted(MADE_KEYS)}")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in sorted(rows, key=lambda r: (r["site_id"], r["column_name"]))
    )
    tmp = out / (MADE_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / MADE_FILE)
    return len(rows)


def read_made(out: Path) -> dict[tuple[str, str], dict[str, Any]]:
    path = out / MADE_FILE
    if not path.exists():
        raise PopulationError(f"{path} is missing - run `population.py export` first")
    made: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _read_jsonl(path):
        if set(row) != set(MADE_KEYS):
            raise PopulationError(f"{path}: a row carries {sorted(row)}, not {sorted(MADE_KEYS)}")
        made[(str(row["site_id"]), str(row["column_name"]))] = row
    return made


#: The runs after WD1 that hold decisions, in the order they ran: WD3's pilot (80 sites, answered
#: before its run was built without them), WD3's run, WD4's.
HISTORY_RUNS = ("wd3-pilot", R.ONE_FAMILY.stage, R.ONE_FAMILY_PERIOD.stage)


def read_answers(
    wd1: Wd1, fields_dir: Path = FIELDS_DIR, runs: Sequence[str] = HISTORY_RUNS
) -> dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]]:
    """Every decision of each (site, field) as `(run, row)`, oldest first: WD1's, then the
    `DECISIONS.jsonl` of each of `runs` under `fields_dir`, in the order given."""
    answers: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = {}
    for cell, row in wd1.decisions.items():
        answers.setdefault(cell, []).append((str(row["run"]), dict(row)))
    for run in runs:
        for row in _read_jsonl(fields_dir / run / "DECISIONS.jsonl"):
            answers.setdefault((str(row["site_id"]), str(row["field"])), []).append((run, row))
    return answers


def read_history(wd1: Wd1, fields_dir: Path = FIELDS_DIR) -> dict[tuple[str, str], dict[str, Any]]:
    """The latest decision of each (site, field) across the lanes in the order they ran: WD1's,
    then WD3's pilot, WD3's and WD4's `DECISIONS.jsonl` under `fields_dir`. A field a later lane
    asked again is decided by the later lane; a rule row (`DERIVED.jsonl`) is not an answer and is
    not read."""
    return {cell: dict(rows[-1][1]) for cell, rows in read_answers(wd1, fields_dir).items()}


def column_kind(column: str, stored: Mapping[str, Any], made: Mapping[tuple[str, str], Any],
                site: str) -> str | None:  # fmt: skip
    """Who made the value `column` holds now, from its newest journal row: `rule` (evidence status
    RULE), `minimax` (an evidence entry names a MiniMax model), `sourced` (another lane's write at
    a sourced confidence), or None - no journal row, a row of a confidence no source backs, a
    withdrawal (wd5 cleared or restored the value on an `unresolved` answer), or one that no longer ends at the stored value (written around the journal: nothing is claimed of it)."""
    row = made.get((site, column))
    if row is None:
        return None
    held = stored[column + "_text"] if column in ("lat", "lon") else stored[column]
    if row["new_value"] is None or held is None:
        same = row["new_value"] is None and held is None
    elif column in ("lat", "lon"):
        same = float(row["new_value"]) == float(held)
    else:
        same = str(row["new_value"]) == str(held)
    if not same:
        return None
    # wd5 cleared or restored the value: no source stands behind it
    if row["withdrawn"]:
        return None
    if row["rule_made"]:
        return RULE
    if row["minimax"]:
        return MINIMAX
    return SOURCED if row["confidence"] in SOURCED_CONFIDENCE else None


def field_kind(kinds: Mapping[str, str | None], field: str) -> str | None:
    """The kind of a field from the kinds of its columns: a point is written whole, so one column a
    MiniMax agent wrote makes the point its; `minimax` wins over `sourced`, over None."""
    own = [kinds.get(column) for column in FIELD_COLUMNS[field]]
    for kind in (RULE, MINIMAX, SOURCED):
        if kind in own:
            return kind
    return None


def made_kinds(stored: Mapping[str, Any], made: Mapping[tuple[str, str], Any],
               site: str) -> dict[str, str | None]:  # fmt: skip
    """`column_kind` of every column a field is stored in."""
    return {
        column: column_kind(column, stored, made, site)
        for columns in FIELD_COLUMNS.values()
        for column in columns
    }


def _answered_by_minimax(decision: Mapping[str, Any] | None) -> bool:
    return decision is not None and "minimax" in str(decision.get("model") or "").lower()


def _made_note(kind: str | None, field: str, site: str, decision: Mapping[str, Any] | None,
               made: Mapping[tuple[str, str], Any]) -> str | None:  # fmt: skip
    """What stands, in a sentence for the question: the rule that made the value, or the earlier
    decision (a lead to check, not evidence)."""
    if kind == RULE:
        note = made[(site, FIELD_COLUMNS[field][0])]["note"]
        return f"made by a rule, not found in a source: {note}"
    if decision is None:
        return None
    said = (
        f"{decision['decision']} {decision['value']!r}"
        if decision["value"]
        else decision["decision"]
    )
    who = "a MiniMax model" if _answered_by_minimax(decision) else "an earlier pass"
    return f"{who} decided {said}: {str(decision['reasoning'])[:MADE_SHOWN_CHARS]}"


def recheck_fields(
    line: Mapping[str, Any],
    stored: Mapping[str, Any],
    history: Mapping[tuple[str, str], Mapping[str, Any]],
    made: Mapping[tuple[str, str], Mapping[str, Any]],
    wd1: Wd1,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The fields of one classified site that lane wd5 asks, `{field: {"why", "wd1", "made"}}`, and
    the fields it leaves alone because another lane's source stands behind them (`sourced`).

    Never asked: a field whose newest journal row is another lane's sourced write (`sourced`) - that
    lane's source stands; a period or type or URL that no rule and no MiniMax agent made and none
    decided (it stands on WD1's two quotes or on the import); a point with a counted keep. Asked:
    `rule-made` (a period a rule made, whoever else answered it), `minimax-answered`, and an
    `unsourced-point`."""
    site = str(line["site_id"])
    opened: dict[str, dict[str, Any]] = {}
    sourced: list[str] = []
    kinds = made_kinds(stored, made, site)
    for field in C.FIELDS:
        decision = history.get((site, field))
        kind = field_kind(kinds, field)
        if kind == SOURCED:
            sourced.append(field)
            continue
        if field == "period_start" and kind == RULE:
            why = WHY_RULE_MADE
        elif kind == MINIMAX or _answered_by_minimax(decision):
            why = WHY_MINIMAX
        elif field == "coordinates" and _point_unsourced(line, decision, kind):
            why = WHY_UNSOURCED_POINT
        else:
            continue
        opened[field] = {
            "why": why,
            "wd1": _wd1_summary(wd1.decisions.get((site, field))),
            "made": _made_note(kind, field, site, decision, made),
        }
    return opened, sourced


def _point_unsourced(line: Mapping[str, Any], decision: Mapping[str, Any] | None,
                     kind: str | None) -> bool:  # fmt: skip
    """Whether the stored point has no source: the latest decision is `unresolved` or `held`, or a
    `replace` that nothing wrote (a guard refused the better point - the journal would otherwise say
    `sourced`), or no pass asked and the machine does not confirm it. A counted `keep` is sourced."""
    if decision is None:
        return line["fields"]["coordinates"]["status"] != C.CONFIRMED
    return decision["decision"] != A.KEEP


# ------------------------------------------------------------------------------ the reader gap
#: The decisions a reader-gap build reads beyond WD1's: the pilot and the rest run of lane wd5,
#: whose `unresolved` answers cleared the periods this path asks again.
REASK_HISTORY_RUNS = (*HISTORY_RUNS, "wd5-pilot", R.RECHECK.stage)
#: The directory of the reader-gap run itself under `fields_dir`: a site it has decided is never
#: asked a second time by a later build.
REASK_RUN = "wd5-reask"
#: The latest year a dated value may state to count as an ancient one (the scope rule: nothing after
#: 1500 AD): "in 1998" is a modern year, not a start.
READER_GAP_LATEST_YEAR = 1500
READER_GAP_BP, READER_GAP_STATEMENT = "bp-age", "dated-statement"
READER_GAP_PERIOD, READER_GAP_LISTED = "period-name", "listed"
#: What an answer says when a machine reader, not the sources, is why it gave up: "none states it
#: in a form the check reads", "the checker cannot read ...", "not a period name this lane's table
#: holds". The three periods wd5's pilot cleared to Undated (2026-10-09) said it in these words.
READER_BLAME = re.compile(
    r"\bthe check(?:er)?\b|\bchecker\b|\bthe machine\b|\bthe reader\b|"
    r"\blane'?s? (?:period )?(?:table|reader|vocabulary)\b|\bperiod (?:table|reader)\b|"
    r"\b(?:does|do|did) not read\b|\b(?:can ?not|can'?t|could ?not) (?:be )?read\b|"
    r"\bthe import (?:does|cannot|refuses|reads)\b",
    re.IGNORECASE,
)
READER_GAP_SHOWN_CHARS = 400
#: Why a site a reader-gap build looked at is left alone (counted in COUNTS.json).
SKIP_NOT_EMPTY, SKIP_SOURCED, SKIP_ALREADY = "not-empty", "sourced", "already-reasked"


def _answered_by_claude(decision: Mapping[str, Any]) -> bool:
    return "claude" in str(decision.get("model") or "").lower()


def _answer_text(decision: Mapping[str, Any]) -> str:
    """What an answer wrote: its reasoning and the sentences it quoted."""
    quoted = [str(q.get("quote") or "") for q in decision.get("quotes") or ()]
    return "\n".join([str(decision["reasoning"]), *quoted])


def readable_date(text: str) -> tuple[str, str] | None:
    """The first dated value the readers of today read in `text`, as `(kind, what)`: an age in years
    before the present (`answers.bp_dates`: "12,000 BP", "vor 12.000 Jahren"), or a year, century
    or millennium with its era marker (`dates.statements`) not later than `READER_GAP_LATEST_YEAR`.
    A number with no era marker is a modern year and counts for nothing. A period of
    `pipeline.periods` named in the text (`READER_GAP_PERIOD`) counts last."""
    bp = A.bp_dates(text)
    if bp:
        year, tolerance = bp[0]
        return READER_GAP_BP, f"an age in years before the present: {year} (+-{tolerance} years)"
    for statement in D.statements(text):
        if statement.era is not None and statement.hi <= READER_GAP_LATEST_YEAR:
            return (
                READER_GAP_STATEMENT,
                f"the {statement.kind} {statement.number} {statement.era} "
                f"({statement.lo} to {statement.hi})",
            )
    for name, (start, _end) in P.PERIODS.items():
        if P.states_period(text, name):
            return READER_GAP_PERIOD, f"the period {name!r} (a start of {start})"
    return None


def reader_gap_reading(
    answers: Sequence[tuple[str, Mapping[str, Any]]],
) -> tuple[str, str, str] | None:
    """Whether the period answers of a site (oldest first, `read_answers`) are a reader gap, as
    `(run, kind, what)`: the latest is a counted `unresolved` of a Claude agent (an adversarial
    rejection is not: a source was read and a checker refused it), it blames a machine reader for
    giving up (`READER_BLAME`) and it names a value the readers of today read (`readable_date`).
    Both are asked of the answer's own words: a date in a reasoning that blames no reader is a lead
    the agent weighed and dropped, and wd5's rest run asked 409 such sites after the readers were
    fixed (measured 2026-10-18)."""
    if not answers:
        return None
    run, latest = answers[-1]
    if (
        latest["decision"] != A.UNRESOLVED
        or latest.get("via") != "counted"
        or not _answered_by_claude(latest)
    ):
        return None
    if READER_BLAME.search(str(latest["reasoning"])) is None:
        return None
    found = readable_date(_answer_text(latest))
    return None if found is None else (run, *found)


def reader_gap_fields(
    line: Mapping[str, Any],
    stored: Mapping[str, Any],
    answers: Sequence[tuple[str, Mapping[str, Any]]],
    made: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    listed: str | None,
    detect: bool,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """The one field a reader-gap run asks of a site, `{"period_start": {"why", "wd1", "made"}}`
    (empty when the site is not one), and the reason it is left alone (`SKIP_NOT_EMPTY`: a period is
    stored now; `SKIP_SOURCED`: the newest journal row of the period is another lane's sourced
    write), or None. A site is asked when `listed` names it (the orchestrator's reason) or, with
    `detect`, when its period answers are a reader gap (`reader_gap_reading`)."""
    site = str(line["site_id"])
    reading = reader_gap_reading(answers) if detect else None
    if listed is None and reading is None:
        return {}, None
    if not is_empty("period_start", stored):
        return {}, SKIP_NOT_EMPTY
    if column_kind("period_start", stored, made, site) == SOURCED:
        return {}, SKIP_SOURCED
    if listed is not None:
        kind = READER_GAP_LISTED
        note = f"the orchestrator listed this site for a second look: {listed}"
    else:
        run, kind, what = reading  # type: ignore[misc]  # not None: listed is None and reading is not
        said = str(answers[-1][1]["reasoning"])[:READER_GAP_SHOWN_CHARS]
        note = (
            f"the period is empty: the pass of {run} answered unresolved ({said}), and an answer "
            f"about this site names a dated value - {what} - that the readers of that day could "
            "not read and today's read. A source may state the start: look for it, quote it"
        )
    opened = {"why": WHY_READER_GAP, "wd1": None, "made": note, "reader_gap": kind}
    return {"period_start": opened}, None


def read_listed(path: Path) -> dict[str, str]:
    """`--sites FILE`: one JSON object per line, `{"site_id": <id>, "reason": <text>}`. A line of
    another shape, an empty reason, a site named twice and an empty file are refused."""
    if not path.exists():
        raise PopulationError(f"{path} is missing")
    listed: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not isinstance(row, dict) or set(row) != {"site_id", "reason"}:
            raise PopulationError(f'{path}:{number} is not {{"site_id", "reason"}}: {raw[:120]}')
        site, reason = str(row["site_id"]), str(row["reason"]).strip()
        if not reason:
            raise PopulationError(f"{path}:{number}: {site} comes with no reason")
        if site in listed:
            raise PopulationError(f"{path}:{number}: {site} is listed twice")
        listed[site] = reason
    if not listed:
        raise PopulationError(f"{path} lists no site")
    return listed


@dataclass(frozen=True)
class Reask:
    """What a reader-gap build is: the period answers it reads (`read_answers` over
    `REASK_HISTORY_RUNS`), whether it detects the sites (`--reask-cleared`), the sites the
    orchestrator listed with their reasons (`--sites`) and the sites an earlier reader-gap run
    decided (`already`, never asked twice)."""

    answers: Mapping[tuple[str, str], Sequence[tuple[str, Mapping[str, Any]]]]
    detect: bool
    listed: Mapping[str, str]
    already: frozenset[str]


def check_listed(
    listed: Mapping[str, str],
    stored: Mapping[str, Mapping[str, Any]],
    made: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    """Refuses (every offender named, nothing written) a listed site that is no curated site of the
    export, a retired one, one whose period is not empty now and one whose period's newest journal
    row is another lane's sourced write."""
    bad = []
    for site in sorted(listed):
        row = stored.get(site)
        if row is None:
            bad.append(f"{site}: not a curated site of {C.STORED_FILE}")
        elif row["scope_status"] == "retired":
            bad.append(f"{site}: retired")
        elif not is_empty("period_start", row):
            bad.append(f"{site}: holds period_start {row['period_start']!r} now")
        elif column_kind("period_start", row, made, site) == SOURCED:
            bad.append(f"{site}: its period was written by another lane's sourced write")
    if bad:
        raise PopulationError("the listed site(s) cannot be asked again: " + "; ".join(bad))


def decided_by_reask(fields_dir: Path = FIELDS_DIR) -> frozenset[str]:
    """The sites a reader-gap run of `REASK_RUN` decided a period of, once it has decisions: a site
    is asked by a reader-gap run once. No decisions file is a run not answered yet."""
    path = fields_dir / REASK_RUN / "DECISIONS.jsonl"
    if not path.exists():
        return frozenset()
    return frozenset(
        str(row["site_id"]) for row in _read_jsonl(path) if row["field"] == "period_start"
    )


def export(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> dict[str, Any]:
    """STORED.jsonl (`classify.export_stored`), LINKS.jsonl, POINTS.jsonl, MADE.jsonl and the empty
    SEEDS.jsonl a run needs."""
    stored = C.export_stored(out, reader=reader)
    links = export_links(out, reader=reader)
    points = export_points(out, reader=reader)
    made = export_made(out, reader=reader)
    (out / C.SEEDS_FILE).write_text("", encoding="utf-8", newline="\n")
    return {"stored": stored, "links": links, "points": points, "made": made}


# ------------------------------------------------------------------------------ the run
def build(
    root: Path,
    out: Path,
    *,
    table: Mapping[str, C.ClassEntry],
    wd1: Wd1,
    stage: str = "wd3",
    pilot: tuple[int, int] | None = None,
    without: Path | None = None,
    history: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    reask: Reask | None = None,
) -> dict[str, Any]:
    """RUN.json, CLASSIFIED.jsonl and COUNTS.json of the population (or of its pilot, or of the
    population less a pilot): every live curated site with an open field, each with exactly those.
    `stage` picks the rule `RUN.json` pins: `wd3` fills open fields, `wd4` asks the same question
    and adds the answer kind `period_name`, `wd5` asks the values no source stands behind
    (`recheck_fields`; it needs `history`, the latest decision of every field, and reads MADE.jsonl),
    and a run pinned to another rule is refused.

    `reask` (stage wd5 only) makes the run a **reader-gap** run: it asks `period_start` and nothing
    else, of the empty periods a counted Claude answer left `unresolved` although it names a dated
    value (`reader_gap_fields`) and of the sites the orchestrator listed. It is one run: no pilot,
    no `without`."""
    rule = R.BY_STAGE.get(stage)
    if rule is None:
        raise R.RuleError(f"stage {stage!r} is not one of {sorted(R.BY_STAGE)}")
    if rule.recheck and history is None:
        raise PopulationError(
            "a wd5 run is built from the decisions of WD1, WD3 and WD4: no history"
        )
    if reask is not None and not rule.recheck:
        raise PopulationError(f"a reader-gap run is a stage wd5 run, not {stage!r}")
    if reask is not None and (pilot is not None or without is not None):
        raise PopulationError("a reader-gap run is one run of its own: no pilot, no --without")
    if reask is not None and not (reask.detect or reask.listed):
        raise PopulationError("a reader-gap run needs --reask-cleared or --sites")
    if (out / "ROUNDS.jsonl").exists():
        raise PopulationError(f"{out} was asked already (ROUNDS.jsonl): a run is built once")
    stored_all = C.read_stored(out)  # refused here, before anything is pinned, when it is missing
    links = read_links(out)
    points = read_points(out)
    made = read_made(out) if rule.recheck else {}
    if reask is not None:
        check_listed(reask.listed, stored_all, made)
        again = sorted(set(reask.listed) & reask.already)
        if again:
            raise PopulationError(
                f"the listed site(s) were decided by {REASK_RUN} already: {', '.join(again)}"
            )
    gap_asked: Counter[str] = Counter()
    gap_skipped: Counter[str] = Counter()
    unseen: set[str] = set()
    journal_sourced: set[str] = set()
    skipped_sourced: Counter[str] = Counter()
    contradictions: dict[str, list[str]] = {}

    def refine(line: Mapping[str, Any], stored: Mapping[str, Any]) -> dict[str, Any] | None:
        site = str(line["site_id"])
        if reask is not None:
            wrong = []
            if site in reask.already:
                gap_skipped[SKIP_ALREADY] += 1
                return None
            opened, skipped = reader_gap_fields(
                line, stored, reask.answers.get((site, "period_start"), ()), made,
                listed=reask.listed.get(site), detect=reask.detect,
            )  # fmt: skip
            if skipped is not None:
                gap_skipped[skipped] += 1
            gap_asked.update(o["reader_gap"] for o in opened.values())
        elif rule.recheck:
            opened, sourced = recheck_fields(line, stored, history or {}, made, wd1)
            skipped_sourced.update(sourced)
            wrong = []
        else:
            opened, wrong = open_fields(line, stored, wd1, points.get(site))
            if "coordinates" in open_fields(line, stored, wd1)[0] and "coordinates" not in opened:
                journal_sourced.add(site)  # open but for the journal's sourced write
        if site not in wd1.classified:
            unseen.add(site)
        if wrong:
            contradictions[site] = wrong
        if not opened:
            return None
        return {
            "asked": [field for field in C.FIELDS if field in opened],
            "open": opened,
            "links": links[site],
        }

    R.write_run(
        out,
        rule,
        built_from={
            "harvest": _shown(root),
            "wd1_runs": list(wd1.runs),
            "wd1_waves": list(wd1.waves),
        },
        reask=None
        if reask is None
        else {
            "detect": reask.detect,
            "listed": dict(sorted(reask.listed.items())),
            "reads": list(REASK_HISTORY_RUNS),
        },
        pilot=None if pilot is None else {"size": pilot[0], "seed": pilot[1]},
        without=None if without is None else _shown(without),
    )
    counts = C.classify_all(
        root, out, table=table, part="all", pilot=pilot, without=without, refine=refine
    )
    mine = {json.loads(raw)["site_id"] for raw in (out / C.CLASSIFIED_FILE).open(encoding="utf-8")}
    counts["population"] = {
        "sites": counts["sites"],
        **_tally(out),
        "wd1_unseen_sites": sorted(unseen & mine),
        "skipped_sourced": dict(sorted(skipped_sourced.items())),
        "journal_sourced_points": {
            site: points[site]["run_stamp"] for site in sorted(journal_sourced)
        },
        "wd1_sourced_but_empty": {
            site: fields for site, fields in sorted(contradictions.items()) if site in mine
        },
    }
    if reask is not None:
        counts["reader_gap"] = {
            "asked": dict(sorted(gap_asked.items())),
            "skipped": dict(sorted(gap_skipped.items())),
            "detect": reask.detect,
            "listed": len(reask.listed),
            "already_decided_sites": len(reask.already),
        }
    counts["wd1"] = {
        "runs": list(wd1.runs),
        "waves": list(wd1.waves),
        "decisions": len(wd1.decisions),
        "unresolved_or_held": len(wd1.held),
        "sites_classified": len(wd1.classified),
    }
    (out / C.COUNTS_FILE).write_text(
        json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return counts


def _tally(out: Path) -> dict[str, Any]:
    """How many sites and fields of the run's CLASSIFIED.jsonl are open, and why."""
    fields: Counter[str] = Counter()
    why: Counter[str] = Counter()
    sets: Counter[str] = Counter()
    for raw in (out / C.CLASSIFIED_FILE).open(encoding="utf-8"):
        line = json.loads(raw)
        sets["+".join(line["asked"])] += 1
        for field in line["asked"]:
            fields[field] += 1
            why[f"{field}:{line['open'][field]['why']}"] += 1
    return {
        "fields": dict(sorted(fields.items())),
        "why": dict(sorted(why.items())),
        "field_sets": dict(sorted(sets.items())),
    }


# ------------------------------------------------------------------------------ the CLI
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "export",
        help="STORED.jsonl, LINKS.jsonl, POINTS.jsonl, MADE.jsonl, an empty SEEDS.jsonl "
        "(read-only)",
    )
    run = sub.add_parser("build", help="RUN.json, CLASSIFIED.jsonl, COUNTS.json, from files only")
    run.add_argument("--root", type=Path, required=True, help="the refreshed harvest copy")
    run.add_argument(
        "--stage",
        default="wd3",
        choices=sorted(R.BY_STAGE),
        help="the rule RUN.json pins: wd3 fills open fields, wd4 asks the same question and adds "
        "the answer kind period_name, wd5 asks the values no source stands behind (default: wd3)",
    )
    run.add_argument(
        "--wd1-dir",
        type=Path,
        default=FIELDS_DIR,
        help="where WD1's runs (wd1, wd1-pilot, wd1-rest, wd1-rest-pilot) and its waves "
        "(wd1/write) live - this checkout's output/remediation/fields, which holds them only "
        "where the run itself was built; from a worktree, name the checkout that has them. "
        "Stage wd5 also reads wd3's and wd4's DECISIONS.jsonl there",
    )
    cut = run.add_mutually_exclusive_group()
    cut.add_argument("--pilot", type=int, help="a pilot: this many of the population's sites")
    cut.add_argument("--without", type=Path, help="the population less this pilot run's sites")
    run.add_argument("--seed", type=int, help="the pilot's draw (with --pilot)")
    run.add_argument(
        "--reask-cleared",
        action="store_true",
        help="stage wd5: a reader-gap run (see `reader_gap_fields`) - ask period_start again of "
        "every empty period whose latest decision is a counted Claude unresolved that names a "
        "dated value today's readers read; one run, no --pilot, no --without",
    )
    run.add_argument(
        "--sites",
        type=Path,
        help='stage wd5: a reader-gap run of the sites in FILE (JSON lines {"site_id", "reason"}); '
        "with --reask-cleared, those sites are added to the detected ones",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result: Any = export(args.out, reader=psql_json_reader())
        else:
            if (args.pilot is None) != (args.seed is None):
                parser.error("--pilot and --seed go together")
            if (args.reask_cleared or args.sites is not None) and args.stage != R.RECHECK.stage:
                parser.error("--reask-cleared and --sites are for --stage wd5")
            listed = {} if args.sites is None else read_listed(args.sites)
            wd1 = read_wd1(*wd1_files(args.wd1_dir))
            reask = None
            if args.reask_cleared or args.sites is not None:
                reask = Reask(
                    read_answers(wd1, args.wd1_dir, REASK_HISTORY_RUNS),
                    args.reask_cleared,
                    listed,
                    decided_by_reask(args.wd1_dir),
                )
            result = build(
                args.root,
                args.out,
                table=C.load_table(),
                wd1=wd1,
                stage=args.stage,
                pilot=None if args.pilot is None else (args.pilot, args.seed),
                without=args.without,
                history=read_history(wd1, args.wd1_dir) if args.stage == R.RECHECK.stage else None,
                reask=reask,
            )
    except (PopulationError, R.RuleError, C.ClassifyError, H.HarvestError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
