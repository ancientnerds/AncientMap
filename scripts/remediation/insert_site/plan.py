"""D57 step 3: the insert plan - one curated row per researched site, from the decisions and one read.

A curated (`ancient_nerds`) row is what the SSR route, the sitemap, the static export, the card lane
and every remediation lane read, so a new one carries **exactly the column set a curated row
carries** (measured on production 2026-10-24 over the 5,004 rows): `id`, `source_id`,
`source_record_id`, `name`, `name_normalized` (the database's own key, `site_key_sql`, which the
Lyra boot reconciliation would otherwise rewrite), `lat`, `lon`, `geom` (the point, SRID 4326),
`site_type`, `period_start`, `period_name` (the bucket of the start, `Undated` without one - the
period lanes' residual), `country`, `source_url`, `edited_by`, `raw_data`, `scope_status`,
`scope_reason`, `updated_at` (no curated row has it NULL) and, for a pinned component, its
`parent_site_id`. `description` and `thumbnail_url` stay NULL: the description lane and the picture
lane (D17) write them through their own journalled lanes. `h3_index`, `period_end` and
`last_audited` stay NULL as on the curated rows (`h3_index` is NULL on all 5,004).

Beside the row, in the same transaction, what a curated site carries in its own tables:

* `unified_site_names` - its `label` row (the name, `language_code` NULL, as the 5,010 curated
  labels), and an `alias` row for each name a closed proposal knew it by whose key differs (what
  `POST /api/proposals/{id}/approve` writes, so the Prospector's same-name check finds the site);
* `site_external_ids` - its `wikidata_qid` and `enwiki_title` (the Prospector's rung 0; the daily
  `refresh_site_external_ids` writes only for sites without one, so it leaves these alone);
* `site_proposals` - every open proposal that names the item or the article, closed as `approved`
  with `promoted_site_id` (D57); a proposal that names only the name is listed in PLAN.md, never
  closed.

**`raw_data`** carries the provenance: `_insert_provenance` (the decision, the run, the item, every
field's quotes and who answered them, the description's sources), and the two markers the fields
lanes write (`mechanical/field_prov.py`, D12/D19): `_period_provenance` (`quote`, or `undated` for a
start nobody could source) and `_coord_provenance` (`quote`), each hashing the value it describes.

**`scope_status` is `in_scope`** with a reason naming D57: the site was assessed (E8's hand review,
D57, D58's window), and the undo is the transition `in_scope -> retired` (`writer.py`).

**What makes a candidate a refusal** (`REFUSALS.jsonl`, first failure wins; the site is not
inserted and goes on the owner list):

* the candidate list does not hold it as a candidate, or a curated row holds its item or article now
  (`not-a-candidate`, `already-curated`);
* its name, point, country or page has no counted, resolved answer (`<field>-unresolved`,
  `<field>-held`, `<field>-exhausted`) - a type or a start nobody could source does not refuse;
* its country does not hold its point (`country-disagrees`: `bcases.classify.country_after_move`
  with D19's coast tolerance), or a shown curated row carries its name within `NAME_TWIN_METRES`
  (`name-twin`: a possible duplicate is D14's question, never a second row);
* the scope rule D58 keeps it out: a start after 1500 (`scope-after-1500`), or a start from 500 AD in
  a European country outside the Americas and Oceania (`scope-d58-europe`, the medieval Old World);
* its pinned parent is not one shown curated site of its country within 5 km at depth one
  (`parent-*`, the D25 lane's invariants);
* a proposal it would close is already promoted or merged, or mirrors a radar contribution
  (`proposal-promoted`, `proposal-contribution`: the radar's own row is not this lane's to change).

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/insert_site/run.py plan --run d57-2026-10-24 --step 1   (read-only)
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from census.tests import t05_country_values as T05  # noqa: E402
from fields import answers as A  # noqa: E402
from mechanical.field_prov import COORD, PERIOD, QUOTE, SPECS, UNDATED, sha_of  # noqa: E402
from mechanical.lane import PARENT_METRES, sql_literal  # noqa: E402
from mechanical.plan import parse_tagged_export, write_tagged_export  # noqa: E402

from insert_site import candidates as C  # noqa: E402
from insert_site import research as RS  # noqa: E402
from pipeline.lyra.site_key import site_key_sql  # noqa: E402
from pipeline.normalizers.dates import AMERICAS, OCEANIA, e3_region  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402
from pipeline.utils.public_sites import RETIRED, not_retired  # noqa: E402
from pipeline.utils.text import UNDATED as UNDATED_LABEL  # noqa: E402
from pipeline.utils.text import categorize_period  # noqa: E402

CURATED = C.CURATED
MAX_SITES = 100
#: A shown curated row with the new site's name key this close is a possible duplicate (D14): the
#: site is refused rather than inserted twice. The distance is a chosen line - the curated set's
#: same-named sites lie in other countries (Pella in Jordan is 1,487 km from Pella in Greece).
NAME_TWIN_METRES = 50_000
EDITED_BY = "remediation-d57"  # `edited_by` is character varying(20)
REVIEWED_BY = "remediation-d57"
IN_SCOPE = "in_scope"
TEST_ID = "D57/insert-site"
#: The journal's confidence: one quote from one source per value (the `recheck` rule of the fields
#: lanes, `fields/rule.py`), the vocabulary of the fields lanes' one-source writes.
CONFIDENCE = "one_source"
RAW_KEY = "_insert_provenance"
#: The scope rule's year bounds (D58 of 2026-10-24, the E3 cut-offs it replaces).
LAST_YEAR = 1500
EUROPE_LAST_YEAR = 500

STEP_FILE, PLAN_FILE, REFUSALS_FILE, PLAN_MD = (
    "STEP.json",
    "PLAN.jsonl",
    "REFUSALS.jsonl",
    "PLAN.md",
)
READ_FILE, KEYS_FILE = "READ.jsonl", "READ_KEYS.jsonl"
REQUIRED = ("name", "coordinates", "country", "source_url")
FLAGS_TS = REPO / "ancient-nerds-map" / "src" / "utils" / "countryFlags.ts"
_CONTINENT = re.compile(r"\b([A-Z]{2}): '([A-Za-z ]+)'")
#: The proposal columns the insert writes and the undo restores, each compared as text.
PROPOSAL_COLUMNS = (
    "status",
    "promoted_site_id",
    "reviewed_by",
    "reviewed_at",
    "review_notes",
    "updated_at",
)


class InsertPlanError(ValueError):
    """The plan cannot be built on this state. Nothing was written."""


# ------------------------------------------------------------------------------------ the records
@dataclass(frozen=True)
class Insert:
    """One curated row this step creates, and everything it carries."""

    qid: str
    site_id: str
    source_record_id: str
    name: str
    name_key: str
    lat: float
    lon: float
    site_type: str | None
    period_start: int | None
    period_name: str
    country: str
    source_url: str
    enwiki_title: str
    raw_data: dict[str, Any]
    scope_reason: str
    parent_site_id: str | None
    names: list[dict[str, str]]
    external_ids: list[dict[str, str]]
    proposals: list[dict[str, Any]]
    evidence: list[dict[str, str]]

    @property
    def change_key(self) -> str:
        return f"{C.LANE}:{self.qid}"

    def site_columns(self) -> dict[str, str]:
        """Every `unified_sites` column the INSERT names that is not NULL, as Postgres prints it
        back - the journal carries one row each (a NULL type, start or parent is not written)."""
        out = {
            "id": self.site_id,
            "source_id": CURATED,
            "source_record_id": self.source_record_id,
            "name": self.name,
            "name_normalized": self.name_key,
            "lat": pg_float(self.lat),
            "lon": pg_float(self.lon),
            "geom": f"SRID=4326;POINT({pg_float(self.lon)} {pg_float(self.lat)})",
            "site_type": self.site_type,
            "period_start": None if self.period_start is None else str(self.period_start),
            "period_name": self.period_name,
            "country": self.country,
            "source_url": self.source_url,
            "edited_by": EDITED_BY,
            "raw_data": None,  # compared as jsonb, not as text: see `journal_rows`
            "scope_status": IN_SCOPE,
            "scope_reason": self.scope_reason,
            "updated_at": None,  # now(): read back, never planned
            "parent_site_id": self.parent_site_id,
        }
        return {k: v for k, v in out.items() if v is not None}

    @property
    def journal_rows(self) -> int:
        """The rows the journal must carry for this site: the row's columns (`raw_data` and
        `updated_at` are written too and journalled from the row), four per name row, one per
        external id, six per closed proposal."""
        return (
            len(self.site_columns())
            + 2
            + 4 * len(self.names)
            + len(self.external_ids)
            + len(PROPOSAL_COLUMNS) * len(self.proposals)
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "qid": self.qid,
            "site_id": self.site_id,
            "source_record_id": self.source_record_id,
            "name": self.name,
            "name_key": self.name_key,
            "lat": self.lat,
            "lon": self.lon,
            "site_type": self.site_type,
            "period_start": self.period_start,
            "period_name": self.period_name,
            "country": self.country,
            "source_url": self.source_url,
            "enwiki_title": self.enwiki_title,
            "raw_data": self.raw_data,
            "scope_reason": self.scope_reason,
            "parent_site_id": self.parent_site_id,
            "names": self.names,
            "external_ids": self.external_ids,
            "proposals": self.proposals,
            "evidence": self.evidence,
        }

    @classmethod
    def from_json(cls, record: Mapping[str, Any]) -> Insert:
        return cls(**{k: record[k] for k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Refusal:
    qid: str
    name: str | None
    reason: str
    detail: str

    def as_json(self) -> dict[str, Any]:
        return {"qid": self.qid, "name": self.name, "reason": self.reason, "detail": self.detail}


@dataclass
class Step:
    """One step of the lane: its inserts, its refusals, its identity and the read it rests on."""

    run: str
    number: int
    inserts: list[Insert]
    refusals: list[Refusal] = field(default_factory=list)
    read_at: str = ""
    probe: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, list[str]] = field(default_factory=dict)
    #: proposals that name only a site's name (never closed), per item, for the owner list
    name_proposals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def run_stamp(self) -> str:
        return f"{self.run}_{C.LANE}-s{self.number:03d}"

    @property
    def rollback_stamp(self) -> str:
        return f"{self.run_stamp}-rollback"

    @property
    def digest(self) -> str:
        return digest_of(self.inserts)


def digest_of(inserts: Sequence[Insert]) -> str:
    payload = json.dumps(
        [row.as_json() for row in inserts], ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def pg_float(value: float) -> str:
    """A `double precision` as Postgres 12+ prints it: the shortest text that reads back as the same
    number - Python's `repr`, but without the `.0` an integral value carries there ("12", not
    "12.0"). The coordinate marker's sha is taken over this text (`field_prov.sha_sql`), and the
    transaction proves the two agree (invariant 2)."""
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


# ------------------------------------------------------------------------------------ the rules
@functools.cache
def _continents() -> dict[str, str]:
    """ISO code -> continent, from the frontend's own map (`countryFlags.ts:CODE_TO_CONTINENT`)."""
    text = FLAGS_TS.read_text(encoding="utf-8")
    block = re.search(r"CODE_TO_CONTINENT[^=]*=\s*\{(.*?)\n\}", text, re.S)
    if block is None:
        raise InsertPlanError(f"cannot locate CODE_TO_CONTINENT in {FLAGS_TS}")
    found = dict(_CONTINENT.findall(block.group(1)))
    if len(found) < 150:  # the map holds about 200 codes; a partial parse must not pass silently
        raise InsertPlanError(f"parsed only {len(found)} continents from {FLAGS_TS}")
    return found


def iso_of(country: str) -> str | None:
    """The ISO code the project's vocabularies give a country spelling (T05's two readers)."""
    codes, normalize = RS._country_vocabulary()
    return T05._flag_code(country, codes) or T05._iso(country, normalize)


def scope_refusal(period_start: int | None, country: str, lat: float, lon: float) -> str | None:
    """D58: the scope rule's refusal of a dated site, or None. An undated site is in scope (E3)."""
    if period_start is None:
        return None
    if period_start > LAST_YEAR:
        return "scope-after-1500"
    region = e3_region({"country": country, "lat": lat, "lon": lon})
    if period_start >= EUROPE_LAST_YEAR and region not in (AMERICAS, OCEANIA):
        iso = iso_of(country)
        if iso is not None and _continents().get(iso) == "Europe":
            return "scope-d58-europe"
    return None


def marker(kind: str, run_stamp: str, premise: str) -> dict[str, Any]:
    """A `field_prov` marker: where the value comes from, and the sha of the value it describes."""
    return {"kind": kind, "run": run_stamp, "journal_id": None, "sha": sha_of(premise)}


# ------------------------------------------------------------------------------------ the read
KINDS = ("ids", "twins", "proposals", "name_proposals", "parents", "taken", "probe")
KEY_KINDS = ("keys",)


def _values(rows: Sequence[Sequence[Any]], names: str) -> str:
    def lit(v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, float):
            return f"{pg_float(v)}::double precision"
        return sql_literal(str(v))

    body = ",\n".join("(" + ", ".join(lit(v) for v in row) + ")" for row in rows)
    return f"(VALUES\n{body}\n) AS {names}"


def keys_sql(strings: Sequence[str]) -> list[tuple[str, str]]:
    """The match key of every name the plan writes, computed by Postgres (`site_key_sql`): the key
    is `lower(unaccent(...))` there, which no Python function reproduces (the dotless i, the o with
    a stroke, measured 2026-09-14). A pure function of the text, so it needs no snapshot of its own."""
    s = _values([(x,) for x in strings], "s(text)")
    return [("keys", f"SELECT s.text, {site_key_sql('s.text')} AS key FROM {s}")]


def read_sql(
    sites: Sequence[Mapping[str, Any]], parent_qids: Sequence[str]
) -> list[tuple[str, str]]:
    """The plan's read, one snapshot: `sites` are `{qid, title, name, lat, lon, site_id, record}`
    per candidate with a researched point and the id and record the plan would give it."""
    k = _values(
        [
            (s["qid"], s["title"], s["name"], s["lat"], s["lon"], s["site_id"], s["record"])
            for s in sites
        ],
        "k(qid, title, name, lat, lon, site_id, record)",
    )
    parents = ", ".join(sql_literal(q) for q in parent_qids) or "NULL"
    prefix = (
        "(left(replace(k.site_id, '-', ''), 8) || '-0000-0000-0000-000000000000')::uuid",
        "(left(replace(k.site_id, '-', ''), 8) || '-ffff-ffff-ffff-ffffffffffff')::uuid",
    )
    return [
        (
            "ids",
            f"SELECT k.qid, e.kind, e.value, u.id::text AS site_id, u.scope_status FROM {k} "
            "JOIN site_external_ids e ON (e.kind = 'wikidata_qid' AND e.value = k.qid) "
            "OR (e.kind = 'enwiki_title' AND e.value = k.title) "
            f"JOIN unified_sites u ON u.id = e.site_id AND u.source_id = '{CURATED}'",
        ),
        (
            "twins",
            f"SELECT k.qid, u.id::text AS site_id, u.name, u.country, round(ST_DistanceSphere("
            f"ST_MakePoint(u.lon, u.lat), ST_MakePoint(k.lon, k.lat))::numeric) AS metres FROM {k} "
            f"JOIN unified_sites u ON u.source_id = '{CURATED}' AND {not_retired('u')} "
            f"AND u.name_normalized = {site_key_sql('k.name')}",
        ),
        (
            "proposals",
            "SELECT k.qid, p.id::text AS proposal_id, p.name, p.aliases, p.status, "
            "p.promoted_site_id::text AS promoted_site_id, p.contribution_id::text AS "
            "contribution_id, p.reviewed_by, p.reviewed_at::text AS reviewed_at, p.review_notes, "
            f"p.updated_at::text AS updated_at FROM {k} "
            "JOIN site_proposals p ON p.wikidata_qid = k.qid OR p.enwiki_title = k.title",
        ),
        (
            "parents",
            "SELECT e.value AS parent_qid, u.id::text AS site_id, u.name, u.country, u.lat, u.lon, "
            "u.scope_status, u.parent_site_id::text AS parent_site_id FROM site_external_ids e "
            f"JOIN unified_sites u ON u.id = e.site_id AND u.source_id = '{CURATED}' "
            f"WHERE e.kind = 'wikidata_qid' AND e.value IN ({parents})",
        ),
        (
            # proposals that name only the researched name: listed in PLAN.md, never closed - a
            # name alone does not say which place a proposal meant
            "name_proposals",
            "SELECT k.qid, p.id::text AS proposal_id, p.name, p.status, p.evidence_count "
            f"FROM {k} JOIN site_proposals p ON p.wikidata_qid IS NULL AND p.enwiki_title IS NULL "
            f"AND p.name_key = {site_key_sql('k.name')}",
        ),
        (
            "taken",
            f"SELECT k.qid, u.id::text AS site_id, u.source_id, u.source_record_id FROM {k} "
            f"JOIN unified_sites u ON (u.id >= {prefix[0]} AND u.id <= {prefix[1]}) "
            f"OR (u.source_id = '{CURATED}' AND u.source_record_id = k.record)",
        ),
        (
            "probe",
            # rows the guard probes name (`writer.probe_cases`): a shown curated site with an item
            # and no parent, and a retired curated site - read, never written
            "(SELECT 'shown' AS kind, u.id::text AS site_id, u.name, u.name_normalized, u.country, "
            "u.lat, u.lon, u.source_record_id, e.value AS qid FROM unified_sites u "
            "JOIN site_external_ids e "
            f"ON e.site_id = u.id AND e.kind = 'wikidata_qid' WHERE u.source_id = '{CURATED}' AND "
            f"{not_retired('u')} AND u.parent_site_id IS NULL AND u.country IS NOT NULL "
            "ORDER BY u.id LIMIT 1) UNION ALL (SELECT 'retired', u.id::text, u.name, "
            "u.name_normalized, u.country, "
            "u.lat, u.lon, u.source_record_id, NULL FROM unified_sites u WHERE u.source_id = "
            f"'{CURATED}' AND u.scope_status = '{RETIRED}' ORDER BY u.id LIMIT 1)",
        ),
    ]


# ------------------------------------------------------------------------------------ the plan
def _point(decision: Mapping[str, Any]) -> tuple[float, float]:
    lat, lon = (float(x) for x in str(decision["value"]).split(","))
    return lat, lon


def _missing(decisions: Mapping[str, Mapping[str, Any]], field_name: str) -> str | None:
    """The refusal of a required field that has no counted, resolved answer, or None."""
    d = decisions.get(field_name)
    if d is None:
        return f"{field_name}-unanswered"
    if d["status"] != RS.COUNTED:
        return f"{field_name}-{d['status']}"
    if d["decision"] == A.UNRESOLVED:
        return f"{field_name}-unresolved"
    return None


def _value(decisions: Mapping[str, Mapping[str, Any]], field_name: str) -> Any:
    d = decisions.get(field_name)
    if d is None or d["status"] != RS.COUNTED or d["decision"] == A.UNRESOLVED:
        return None
    return d["value"]


def _field_record(d: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if d is None:
        return None
    return {
        k: d.get(k)
        for k in (
            "status",
            "decision",
            "value",
            "period_name",
            "quotes",
            "round",
            "batch_id",
            "answered_by",
            "model",
            "answered_at",
        )
    }


def _evidence(qid: str, decisions: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    """The journal's evidence of a site: every quote a written value rests on, by field."""
    out = []
    for field_name in RS.FIELDS:
        d = decisions.get(field_name)
        if d is None or d["status"] != RS.COUNTED:
            continue
        for url, quote in d["quotes"]:
            out.append({"source": f"{field_name} ({d['answered_by']})", "url": url, "quote": quote})
    if not out:
        raise InsertPlanError(f"{qid}: a planned site with no quote behind any of its values")
    return out


def plan_step(
    run: Path,
    number: int,
    *,
    export: Callable[[str, Path], Path] = write_tagged_export,
    country_check: Callable[[str, float, float], Mapping[str, Any]],
    new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> Step:
    """Plan step `number` of the run from its decisions and a fresh read-only production read:
    refused while a re-ask waits, and when the step was planned already."""
    waiting = RS.waiting(run)
    if waiting:
        raise InsertPlanError(
            f"{len(waiting)} question(s) wait for a re-ask (run.py research export-reask, answer, "
            "validate, import): plan once every field is decided"
        )
    if number != 1:
        raise InsertPlanError(f"step {number}: the lane plans its candidates in one step")
    target = step_dir(run, number)
    if (target / PLAN_FILE).exists():
        raise InsertPlanError(f"{target / PLAN_FILE} exists: a step is planned once")
    by_qid = {str(line["qid"]): line for line in C.read_candidates(run)}
    decisions = RS.read_decisions(run)
    step = Step(run=run.name, number=number, inserts=[])
    sites: list[dict[str, Any]] = []
    for qid in sorted(decisions):
        line = by_qid.get(qid)
        if line is None or line["status"] != C.CANDIDATE:
            step.refusals.append(
                Refusal(qid, None, "not-a-candidate", "the candidate list holds no candidate")
            )
            continue
        mine = decisions[qid]
        missing = next(((f, m) for f in REQUIRED if (m := _missing(mine, f))), None)
        if missing is not None:
            reason = (mine.get(missing[0]) or {}).get("reason") or "answered unresolved"
            step.refusals.append(Refusal(qid, line["label_en"], missing[1], str(reason)))
            continue
        lat, lon = _point(mine["coordinates"])
        sites.append(
            {
                "qid": qid,
                "title": line["enwiki_title"],
                "name": _value(mine, "name"),
                "lat": lat,
                "lon": lon,
                "site_id": new_id(),
                "record": f"d57-{qid}",
            }
        )
    if len(sites) > MAX_SITES:
        raise InsertPlanError(f"{len(sites)} sites in one step: D8 allows {MAX_SITES}")
    if not sites:
        raise InsertPlanError("no candidate has its name, point, country and page decided")
    parent_qids = sorted({str(by_qid[s["qid"]]["parent_qid"]) for s in sites
                          if by_qid[s["qid"]]["parent_qid"]})  # fmt: skip
    target.mkdir(parents=True, exist_ok=True)
    script = C.read_only_script(read_sql(sites, parent_qids))
    rows, read_at = parse_tagged_export(
        export(script, target / READ_FILE).read_text(encoding="utf-8"), KINDS
    )
    proposals = _by_qid(rows["proposals"])
    strings = sorted(
        {str(s["name"]) for s in sites}
        | {str(p["name"]) for ps in proposals.values() for p in ps}
        | {str(a) for ps in proposals.values() for p in ps for a in (p["aliases"] or [])}
    )
    keys, _ = parse_tagged_export(
        export(C.read_only_script(keys_sql(strings)), target / KEYS_FILE).read_text(
            encoding="utf-8"
        ),
        KEY_KINDS,
    )
    step.read_at = read_at
    step.probe = {str(p["kind"]): p for p in rows["probe"]}
    step.name_proposals = _by_qid(rows["name_proposals"])
    build_inserts(step, sites, by_qid, decisions, {**rows, **keys}, country_check)
    return step


def _by_qid(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["qid"]), []).append(dict(row))
    return out


def build_inserts(
    step: Step,
    sites: Sequence[Mapping[str, Any]],
    by_qid: Mapping[str, Mapping[str, Any]],
    decisions: Mapping[str, Mapping[str, Mapping[str, Any]]],
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    country_check: Callable[[str, float, float], Mapping[str, Any]],
) -> None:
    """Every site's row, names, ids, parent and proposals - or its refusal. A pure function of
    the decisions and the read (`rows`), which is what the tests drive."""
    ids, twins, proposals, taken = (
        _by_qid(rows[k]) for k in ("ids", "twins", "proposals", "taken")
    )
    keys = {str(r["text"]): str(r["key"]) for r in rows["keys"]}
    parents = {}
    for row in rows["parents"]:
        if str(row["parent_qid"]) in parents:
            raise InsertPlanError(
                f"the parent item {row['parent_qid']} is held by two curated rows"
            )
        parents[str(row["parent_qid"])] = dict(row)
    for site in sites:
        qid = str(site["qid"])
        line = by_qid[qid]
        mine = decisions[qid]
        name = str(site["name"])

        def refuse(reason: str, detail: str, qid: str = qid, name: str = name) -> None:
            step.refusals.append(Refusal(qid, name, reason, detail))

        if ids.get(qid):
            refuse(
                "already-curated",
                "; ".join(f"{r['site_id']} holds {r['kind']} {r['value']}" for r in ids[qid]),
            )
            continue
        if taken.get(qid):
            raise InsertPlanError(
                f"{qid}: the planned id {site['site_id']} or record {site['record']} is taken "
                f"({taken[qid]}) - plan again for fresh ids"
            )
        lat, lon = float(site["lat"]), float(site["lon"])
        country = str(_value(mine, "country"))
        verdict = country_check(country, lat, lon)
        if not verdict["agrees"]:
            refuse(
                "country-disagrees",
                f"{lat}, {lon} lies in {verdict.get('polygon') or 'no country'}, not {country}",
            )
            continue
        near = [t for t in twins.get(qid, []) if float(t["metres"]) <= NAME_TWIN_METRES]
        if near:
            refuse(
                "name-twin",
                "; ".join(f"{t['name']} ({t['site_id']}, {t['metres']} m)" for t in near),
            )
            continue
        start_text = _value(mine, "period_start")
        start = None if start_text is None else int(str(start_text))
        out_of_scope = scope_refusal(start, country, lat, lon)
        if out_of_scope is not None:
            refuse(out_of_scope, f"period_start {start}, {country}")
            continue
        parent_id, parent_problem = _parent(line, parents, country, lat, lon)
        if parent_problem is not None:
            refuse(parent_problem[0], parent_problem[1])
            continue
        closing, problem = _proposals(proposals.get(qid, []))
        if problem is not None:
            refuse(problem[0], problem[1])
            continue
        label_key = keys[name]
        names = [{"name": name, "name_key": label_key, "name_type": "label"}]
        seen = {label_key}
        for proposal in closing:
            for alias in [proposal["name"], *(proposal.get("aliases") or [])]:
                key = keys[str(alias)]
                if key not in seen:
                    seen.add(key)
                    names.append({"name": str(alias), "name_key": key, "name_type": "alias"})
        period_name = categorize_period(start) if start is not None else UNDATED_LABEL
        coord_text = f"{pg_float(lat)}|{pg_float(lon)}"
        period_text = f"{'NULL' if start is None else start}|{period_name}"
        sources = mine.get(RS.SOURCES)
        raw = {
            RAW_KEY: {
                "v": 1,
                "lane": C.LANE,
                "decision": "D57",
                "run": step.run,
                "run_stamp": step.run_stamp,
                "qid": qid,
                "qid_asked": line.get("qid_asked"),
                "enwiki_title": line["enwiki_title"],
                "origin": line["origin"],
                "fields": {f: _field_record(mine.get(f)) for f in RS.FIELDS},
                "description_sources": (
                    [list(q) for q in sources["quotes"]]
                    if sources and sources["status"] == RS.COUNTED
                    else []
                ),
            },
            SPECS[PERIOD].key: marker(
                QUOTE if start is not None else UNDATED, step.run_stamp, period_text
            ),
            SPECS[COORD].key: marker(QUOTE, step.run_stamp, coord_text),
        }
        step.inserts.append(
            Insert(
                qid=qid,
                site_id=str(site["site_id"]),
                source_record_id=str(site["record"]),
                name=name,
                name_key=label_key,
                lat=lat,
                lon=lon,
                site_type=_value(mine, "site_type"),
                period_start=start,
                period_name=str(period_name),
                country=country,
                source_url=str(_value(mine, "source_url")),
                enwiki_title=str(line["enwiki_title"]),
                raw_data=raw,
                scope_reason=(
                    f"D57 (owner, 2026-10-24): inserted as an Ancient Nerds Original by the insert "
                    f"lane, {step.run_stamp}; in scope under D58"
                ),
                parent_site_id=parent_id,
                names=names,
                external_ids=[
                    {"kind": "wikidata_qid", "value": qid},
                    {"kind": "enwiki_title", "value": str(line["enwiki_title"])},
                ],
                proposals=closing,
                evidence=_evidence(qid, mine),
            )
        )
        for field_name in ("site_type", "period_start"):
            if _value(mine, field_name) is None:
                step.notes.setdefault(qid, []).append(
                    f"{field_name} {(mine.get(field_name) or {}).get('status', 'unanswered')}"
                    " - written empty, on the owner list"
                )


def _parent(
    line: Mapping[str, Any],
    parents: Mapping[str, Mapping[str, Any]],
    country: str,
    lat: float,
    lon: float,
) -> tuple[str | None, tuple[str, str] | None]:
    """The pinned parent's id, or why it cannot be the parent (D25's invariants)."""
    qid = line.get("parent_qid")
    if qid is None:
        return None, None
    row = parents.get(str(qid))
    if row is None:
        return None, ("parent-missing", f"no curated row holds the parent item {qid}")
    if row["scope_status"] == RETIRED:
        return None, ("parent-retired", f"{row['name']} ({row['site_id']}) is retired")
    if row["parent_site_id"] is not None:
        return None, ("parent-depth", f"{row['name']} names a parent of its own")
    metres = haversine_distance(lat, lon, float(row["lat"]), float(row["lon"])) * 1000.0
    if row["country"] != country or metres > PARENT_METRES:
        return None, (
            "parent-far",
            f"{row['name']} is in {row['country']}, {metres:.0f} m away (D25: same country, "
            f"within {PARENT_METRES} m)",
        )
    return str(row["site_id"]), None


def _proposals(
    found: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[str, str] | None]:
    """The open proposals to close, each with the values it holds now; or why the site is refused."""
    closing = []
    for p in sorted(found, key=lambda p: str(p["proposal_id"])):
        if p["status"] in C.CLOSED_PROPOSALS:
            return [], (
                "proposal-promoted",
                f"proposal {p['proposal_id']} ({p['name']}) is {p['status']}"
                + (f", promoted to {p['promoted_site_id']}" if p["promoted_site_id"] else ""),
            )
        if p["contribution_id"] is not None:
            return [], (
                "proposal-contribution",
                f"proposal {p['proposal_id']} mirrors the radar contribution "
                f"{p['contribution_id']}, which this lane does not change",
            )
        closing.append(
            {
                "proposal_id": str(p["proposal_id"]),
                "name": str(p["name"]),
                "aliases": list(p["aliases"] or []),
                "old": {c: p[c] for c in PROPOSAL_COLUMNS},
            }
        )
    return closing, None


# ------------------------------------------------------------------------------------ the files
def step_dir(run: Path, number: int) -> Path:
    return run / f"step-{number:03d}"


def write_step(step: Step, target: Path) -> None:
    """PLAN.jsonl, STEP.json, REFUSALS.jsonl and PLAN.md. The ROLLBACK.sql is the writer's."""
    target.mkdir(parents=True, exist_ok=True)
    C.write_jsonl(target / PLAN_FILE, [row.as_json() for row in step.inserts])
    C.write_jsonl(target / REFUSALS_FILE, [r.as_json() for r in step.refusals])
    C.write_json(
        target / STEP_FILE,
        {
            "run": step.run,
            "step": step.number,
            "run_stamp": step.run_stamp,
            "rollback_stamp": step.rollback_stamp,
            "digest": step.digest,
            "sites": len(step.inserts),
            "refused": len(step.refusals),
            "read_at": step.read_at,
            "probe": step.probe,
            "notes": step.notes,
            "name_proposals": step.name_proposals,
            "planned_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    (target / PLAN_MD).write_text(render_md(step), encoding="utf-8", newline="\n")


def load_step(target: Path) -> Step:
    header = json.loads((target / STEP_FILE).read_text(encoding="utf-8"))
    inserts = [Insert.from_json(r) for r in C.read_jsonl(target / PLAN_FILE)]
    step = Step(
        run=header["run"],
        number=int(header["step"]),
        inserts=inserts,
        refusals=[Refusal(**r) for r in C.read_jsonl(target / REFUSALS_FILE)]
        if (target / REFUSALS_FILE).read_text(encoding="utf-8").strip()
        else [],
        read_at=header["read_at"],
        probe=header["probe"],
        notes=header["notes"],
        name_proposals=header["name_proposals"],
    )
    if header["digest"] != step.digest or header["run_stamp"] != step.run_stamp:
        raise InsertPlanError(
            f"{target / STEP_FILE} names digest {header['digest'][:12]} and stamp "
            f"{header['run_stamp']!r}; the plan on disk is {step.digest[:12]} {step.run_stamp!r}"
        )
    return step


def render_md(step: Step) -> str:
    refused = Counter(r.reason for r in step.refusals)
    out = [
        f"# D57 insert lane - {step.run} step {step.number}",
        "",
        f"Run stamp `{step.run_stamp}`, plan sha256 `{step.digest}`, read {step.read_at}.",
        f"{len(step.inserts)} site(s) to insert, {len(step.refusals)} refused"
        + (f" ({', '.join(f'{k} {v}' for k, v in sorted(refused.items()))})" if refused else "")
        + f"; {sum(len(i.proposals) for i in step.inserts)} proposal(s) to close, "
        f"{sum(i.journal_rows for i in step.inserts)} journal rows.",
        "",
        "| item | name | country | point | type | start | period | page | parent | names | "
        "proposals closed |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i in step.inserts:
        out.append(
            f"| {i.qid} | {i.name} | {i.country} | {pg_float(i.lat)}, {pg_float(i.lon)} | "
            f"{i.site_type or '-'} | {i.period_start if i.period_start is not None else '-'} | "
            f"{i.period_name} | {i.source_url} | {i.parent_site_id or '-'} | "
            f"{', '.join(n['name'] for n in i.names)} | "
            f"{', '.join(p['name'] for p in i.proposals) or '-'} |"
        )
    if step.refusals:
        out += ["", "## Refused (the owner list)", "", "| item | name | reason | detail |"]
        out.append("|---|---|---|---|")
        out += [f"| {r.qid} | {r.name or '-'} | {r.reason} | {r.detail} |" for r in step.refusals]
    if step.name_proposals:
        out += ["", "## Proposals naming only the name (listed, not closed)", ""]
        out += [
            f"- {qid}: " + "; ".join(f"{p['name']} ({p['status']}, {p['proposal_id']})" for p in ps)
            for qid, ps in sorted(step.name_proposals.items())
        ]
    if step.notes:
        out += ["", "## Written empty (the owner list)", ""]
        out += [f"- {qid}: {'; '.join(n)}" for qid, n in sorted(step.notes.items())]
    return "\n".join(out) + "\n"
