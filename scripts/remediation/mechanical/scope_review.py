"""The E3 scope review of 2026-09-26 (WD2): entries that are no archaeological site, and O7.

Two decisions, written as the scope lane writes them - `scope_status` and `scope_reason` of one
site in one transaction, journalled (`lane.scope_review_lane`, `apply.py --lane
scope-review-<wave>`):

**Not an archaeological site at all.** The acceptance of 2026-09-25 met the Baltic Sea Anomaly, a
natural rock formation, as a curated site. Whether an entry is a site is decided per site by an
Opus agent through the handoff, with sources - never by a pattern: the agent researches the entry
and answers `site` or `not_a_site` with a kind (`natural_formation`, `modern`, `object`,
`legend_or_hoax`), a reason and verbatim quotes. A `not_a_site` counts only when its quotes
found word for word on the fetched pages come from at least `MIN_SITES` different websites
(`opus_audit/quotes.py`, the one quote check; the Wikimedia projects count as one website, and
the project's own site is never fetched) - so at least `MIN_SITES` quotes are found. A counted `not_a_site` retires the site
with the reason `E3: not an archaeological site (<kind>): <reason>`; a `site` writes nothing; a
`not_a_site` that does not count writes nothing and goes to the next round (`export-round --round
N` asks the ones round N-1 left uncounted again, the same prompt to a new agent, as the acceptance
judges re-ask; at most `MAX_ROUND`).

Which entries are asked is a funnel - it chooses the questions, never an answer - and every
candidate names the signals that put it there:

* `type`: the site type is one that does not itself say "human-made" (`NON_SITE_TYPES`);
* `wikidata`: the site's Wikidata item is an instance (P31) of a natural feature
  (`NATURAL_CLASSES`, each label read on Wikidata on 2026-09-26). Cave and hill are not in it: most
  caves and hills of the map carry their archaeology (rock shelters, hillforts);
* `no-item`: the site has no Wikidata item in WD1's harvest;
* `pending`: an earlier scope decision left the row `pending`.

**O7 (owner, 2026-09-26): Oceania through 1500 AD.** A scope-e4 retirement by rule (a) - the
`period_start` past the cutoff (`E3: period_start ...`) - that the O7 rule no longer carries is
taken back: `retired` -> `in_scope`. Measured read-only on 2026-09-26: scope-e4 retired no Oceania
site, so this plans nothing today; it stays in the planner so every wave re-reads the scope-e4
retirements under the rule as it now stands.

**Waves.** A write lands at most `MAX_SITES` sites and a run stamp is applied once, so the plan is
written wave by wave: `write --wave <label>` plans the first `MAX_SITES` open sites (by id) of a
fresh export into `mechanical_scope_review/<label>/`, the lane `scope-review-<label>` applies it,
and the next wave starts from a new export - in which the written sites are no longer open. A wave
is refused when an earlier wave was planned from the same export.

Files (`output/remediation/mechanical_scope_review/`): `export/export.jsonl` (read-only, the
current snapshot), per round `QUESTIONS_R<n>.jsonl`, `SNAPSHOT_R<n>.jsonl` (the export its prompts
were rendered from), `EXPORT_R<n>.json` and `NONSITE_R<n>.jsonl` (every answer, counted or not,
with each quote's outcome and the premise it judged), `pages/` (every cited page, fetched once);
per wave `<label>/PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md`, `ROLLBACK.sql`, `SOURCE.json`.
The runbook is `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import research_web  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from served_image.precheck import Harvest, load_harvest  # noqa: E402
from served_image.state import sha256_text  # noqa: E402
from vlm_pilot.common import extract_json  # noqa: E402

from mechanical.lane import (  # noqa: E402
    NOT_A_SITE_PREFIX,
    SCOPE,
    SCOPE_REVIEW_PREMISE_SQL,
    SCOPE_REVIEW_ROOT,
    Lane,
    scope_review_lane,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    Plan,
    PlanError,
    Verdict,
    _claims,
    _now,
    parse_tagged_export,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
    write_tagged_export,
)
from pipeline.normalizers.dates import OCEANIA, e3_region, passes_date_cutoff  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

DEFAULT_OUT = REPO / "output" / "remediation" / SCOPE_REVIEW_ROOT
DEFAULT_HARVEST = REPO / "output" / "remediation" / "fields" / "harvest"
IN_SCOPE = "in_scope"
STAGE = "scope-nonsite"
PER_BATCH = 12
MAX_ROUND = 2
MAX_SITES = 100
MIN_SITES = 2
EXCERPT = 600
TEST_ID = "E3/scope-review"

#: Site types that do not by themselves say "human-made" (each a canonical type).
NON_SITE_TYPES = frozenset(
    {
        "Natural feature",
        "Geological interest",
        "Magnetic anomaly",
        "Underwater structures",
        "Impact crater",
        "Elongated skulls",
        "Unknown",
    }
)

#: Wikidata classes of natural features, each label read with `wbgetentities` on 2026-09-26.
NATURAL_CLASSES: Mapping[str, str] = {
    "Q631305": "rock formation",
    "Q567555": "anomaly",
    "Q8502": "mountain",
    "Q46831": "mountain range",
    "Q8072": "volcano",
    "Q23397": "lake",
    "Q4022": "river",
    "Q34038": "waterfall",
    "Q39816": "valley",
    "Q150784": "canyon",
    "Q2042028": "ravine",
    "Q23442": "island",
    "Q34763": "peninsula",
    "Q185113": "cape",
    "Q40080": "beach",
    "Q107679": "cliff",
    "Q1322134": "gulf",
    "Q35666": "glacier",
    "Q4421": "forest",
    "Q8514": "desert",
    "Q1286517": "natural landscape",
}

SITE, NOT_A_SITE = "site", "not_a_site"
KINDS = ("natural_formation", "modern", "object", "legend_or_hoax")

PROMPT_ID = "scope-nonsite-v1"
PROMPT = """You decide whether an entry of a map of archaeological sites is an archaeological site at all.

The entry: "{name}" - site type "{site_type}", {country}; latitude {lat}, longitude {lon}.
Its Wikidata item: {qid}
Its source on the map: {source_url}
The map's description of it (an excerpt): "{excerpt}"

The map keeps a place of past human activity - ruins, monuments, earthworks, rock art, a cave or a landscape with human remains or traces, a place known from ancient sources - and a museum that exhibits ancient material. It does not keep:
- natural_formation: a natural landform or rock formation without human-made remains (also one claimed by some to be a structure);
- modern: a structure or place made after antiquity, without ancient remains;
- object: a movable object or a collection, not a place;
- legend_or_hoax: a place that exists only in legend, fiction or an unsupported claim.
Whether the entry's date is inside the map's time window is NOT the question.

Research the entry on the web. Return JSON only, no prose:
{{"decision": "site" | "not_a_site",
 "kind": "natural_formation" | "modern" | "object" | "legend_or_hoax" | null,
 "reason": "<one sentence>",
 "quotes": [{{"url": "<the page>", "quote": "<text copied word for word from that page>"}}]}}

site: kind is null; quotes may be empty.
not_a_site: kind is one of the four; give quotes from at least {min_sites} different websites that show it (the Wikipedias, Wikidata and Commons count as one website) - each copied word for word from a page you read. The pages are fetched and every quote is checked character for character (whitespace aside), so copy, never paraphrase. Prefer plain HTML pages (Wikipedia, a museum, a university, a heritage register); a PDF may not be readable, and some registers refuse automated requests.
"""


class ScopeReviewError(PlanError):
    """The step must not run on this state. Nothing was written by it."""


# ------------------------------------------------------------------------------ the export
EXPORT_SITES_SQL = (
    "SELECT u.id::text AS id, u.name, u.country, u.site_type, u.lat, u.lon, u.period_start, "
    "u.period_end, left(coalesce(u.description, ''), "
    f"{EXCERPT}) AS excerpt, u.source_url, u.scope_status, u.scope_reason, "
    f"{SCOPE_REVIEW_PREMISE_SQL} AS premise "
    f"FROM unified_sites u WHERE u.source_id = {sql_literal(CURATED_SOURCE)} ORDER BY u.id"
)
#: The scope-e4 journal rows of each site's `scope_status` - which retirements O7 may take back.
EXPORT_JOURNAL_SQL = (
    "SELECT l.id, l.row_pk, l.column_name, l.old_value, l.new_value, l.run_stamp "
    "FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
    f"AND l.column_name = 'scope_status' AND l.run_stamp = {sql_literal(SCOPE.run_stamp)} "
    "ORDER BY l.id"
)
EXPORT_PARTS = (("site", EXPORT_SITES_SQL), ("journal", EXPORT_JOURNAL_SQL))


@dataclass(frozen=True)
class Export:
    sites: tuple[dict[str, Any], ...]
    journal: tuple[dict[str, Any], ...]
    exported_at: str
    sha256: str

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {str(s["id"]): s for s in self.sites}


def parse_export(text: str) -> Export:
    rows, exported_at = parse_tagged_export(text, (kind for kind, _sql in EXPORT_PARTS))
    if not rows["site"]:
        raise ScopeReviewError("the export holds no curated site")
    return Export(tuple(rows["site"]), tuple(rows["journal"]), exported_at, sha256_text(text))


def export_path(out: Path) -> Path:
    return out / "export" / "export.jsonl"


def read_export(path: Path) -> Export:
    if not path.is_file():
        raise ScopeReviewError(f"{path} does not exist - run `export` first")
    return parse_export(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------ the funnel
@dataclass(frozen=True)
class Candidate:
    site_id: str
    signals: tuple[str, ...]
    qid: str | None


def p31_items(entity: Mapping[str, Any]) -> list[str]:
    """The item's classes (P31, not deprecated)."""
    out = []
    for claim in _claims(entity, "P31"):
        value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(str(value["id"]))
    return out


def candidates(export: Export, harvest: Harvest) -> list[Candidate]:
    """Every shown site with at least one signal, in id order, each with all of its signals."""
    out: list[Candidate] = []
    for site in export.sites:
        if site["scope_status"] == RETIRED:
            continue
        sid = str(site["id"])
        if sid not in harvest.qids:
            raise ScopeReviewError(f"{sid} is not in the harvest - it must cover every shown site")
        qid = harvest.qids[sid]
        signals = []
        if site["site_type"] in NON_SITE_TYPES:
            signals.append("type")
        if qid is not None:
            natural = sorted(set(p31_items(harvest.entity(qid))) & set(NATURAL_CLASSES))
            if natural:
                signals.append("wikidata:" + ",".join(natural))
        else:
            signals.append("no-item")
        if site["scope_status"] == "pending":
            signals.append("pending")
        if signals:
            out.append(Candidate(sid, tuple(signals), qid))
    return out


# ------------------------------------------------------------------------------ the questions
def prompt_for(site: Mapping[str, Any], qid: str | None) -> str:
    return PROMPT.format(
        name=site["name"],
        site_type=site["site_type"] or "unknown",
        country=site["country"] or "country unknown",
        lat=site["lat"],
        lon=site["lon"],
        qid=f"{qid} (https://www.wikidata.org/wiki/{qid})" if qid else "none",
        source_url=site["source_url"] or "none",
        excerpt=" ".join(str(site["excerpt"]).split()) or "(no description)",
        min_sites=MIN_SITES,
    )


@dataclass(frozen=True)
class RoundFiles:
    questions: Path
    snapshot: Path
    record: Path
    answers: Path


def round_files(out: Path, round_no: int) -> RoundFiles:
    return RoundFiles(
        out / f"QUESTIONS_R{round_no}.jsonl",
        out / f"SNAPSHOT_R{round_no}.jsonl",
        out / f"EXPORT_R{round_no}.json",
        out / f"NONSITE_R{round_no}.jsonl",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ScopeReviewError(f"{path} does not exist")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_once(path: Path, text: str) -> None:
    if path.exists():
        raise ScopeReviewError(f"{path} exists - a round's or a wave's files are written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _jsonl(rows: Sequence[Mapping[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def export_round(out: Path, handoff: Path, round_no: int, harvest: Harvest) -> dict[str, Any]:
    """Round 0: every funnel candidate. Round N: every `not_a_site` of round N-1 that did not
    count. The prompts are rendered from the current export, kept as the round's snapshot."""
    if not 0 <= round_no <= MAX_ROUND:
        raise ScopeReviewError(f"round {round_no}: rounds run 0..{MAX_ROUND}")
    files = round_files(out, round_no)
    for path in (files.questions, files.snapshot, files.record):
        if path.exists():
            raise ScopeReviewError(f"{path} exists - round {round_no} was exported already")
    if not export_path(out).is_file():
        raise ScopeReviewError(f"{export_path(out)} does not exist - run `export` first")
    text = export_path(out).read_text(encoding="utf-8")
    export = parse_export(text)
    by_id = export.by_id()
    if round_no == 0:
        asked = candidates(export, harvest)
    else:
        before = round_files(out, round_no - 1)
        previous = {c["site_id"]: c for c in _read_jsonl(before.questions)}
        asked = [
            Candidate(r["site_id"], tuple(previous[r["site_id"]]["signals"]), r["qid"])
            for r in _read_jsonl(before.answers)
            if r["decision"] == NOT_A_SITE and not r["counted"]
        ]
    questions = []
    for n, cand in enumerate(asked):
        batch_id = f"r{round_no}-{n // PER_BATCH + 1:03d}"
        prompt = prompt_for(by_id[cand.site_id], cand.qid)
        OH.export(
            handoff,
            batch_id=batch_id,
            stage=STAGE,
            label=cand.site_id,
            field="scope_status",
            prompt=prompt,
        )
        questions.append(
            asdict(cand) | {"batch_id": batch_id, "prompt_sha256": OH.prompt_sha256(prompt)}
        )
    _write_once(files.snapshot, text)
    _write_once(files.questions, _jsonl(questions))
    signals: dict[str, int] = {}
    for q in questions:
        for signal in q["signals"]:
            key = signal.split(":", 1)[0]
            signals[key] = signals.get(key, 0) + 1
    record = {
        "round": round_no,
        "handoff": str(handoff),
        "prompt_id": PROMPT_ID,
        "exported_at": export.exported_at,
        "snapshot_sha256": export.sha256,
        "questions": len(questions),
        "batches": len({q["batch_id"] for q in questions}),
        "signals": signals,
    }
    _write_once(files.record, json.dumps(record, indent=1, sort_keys=True) + "\n")
    return record


# ------------------------------------------------------------------------------ the answers
@dataclass(frozen=True)
class Answer:
    decision: str
    kind: str | None
    reason: str
    quotes: tuple[dict[str, str], ...]


def parse_answer(text: str) -> Answer:
    data = extract_json(text)
    if data is None:
        raise ScopeReviewError("no JSON object in the answer")
    if set(data) != {"decision", "kind", "reason", "quotes"}:
        raise ScopeReviewError(f"the answer carries {sorted(data)}")
    decision, kind, reason, quotes = data["decision"], data["kind"], data["reason"], data["quotes"]
    if decision not in (SITE, NOT_A_SITE):
        raise ScopeReviewError(f"'decision' {decision!r} is neither 'site' nor 'not_a_site'")
    if decision == SITE and kind is not None:
        raise ScopeReviewError("a site has no kind: 'kind' must be null")
    if decision == NOT_A_SITE and kind not in KINDS:
        raise ScopeReviewError(f"'kind' {kind!r} is not one of {list(KINDS)}")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 400:
        raise ScopeReviewError("'reason' must be one sentence of at most 400 characters")
    if not isinstance(quotes, list) or not all(
        isinstance(q, dict)
        and set(q) == {"url", "quote"}
        and Q.is_url(str(q["url"]))
        and isinstance(q["quote"], str)
        and q["quote"].strip()
        for q in quotes
    ):
        raise ScopeReviewError("'quotes' must be a list of {url, quote} with an http(s) url")
    if decision == NOT_A_SITE:
        sites = {website(q["url"]) for q in quotes}
        if len(sites) < MIN_SITES:
            raise ScopeReviewError(
                f"not_a_site needs quotes from at least {MIN_SITES} websites "
                "(the Wikimedia projects count as one)"
            )
    return Answer(decision, kind, " ".join(reason.split()), tuple(quotes))


#: Second-level labels under which a country code registers names (bbc.co.uk, abc.net.au).
_SECOND_LEVEL = frozenset({"ac", "co", "com", "edu", "gov", "net", "org", "or", "ne", "go"})
#: The Wikimedia projects: one editorial family, so one website for the two-website rule - a
#: Wikipedia article and its Wikidata item are not two independent sources.
WIKIMEDIA = "wikimedia"
_WIKIMEDIA_DOMAINS = frozenset(
    {
        "wikipedia.org",
        "wikidata.org",
        "wikimedia.org",
        "wikisource.org",
        "wikivoyage.org",
        "wiktionary.org",
        "wikibooks.org",
        "wikinews.org",
        "wikiquote.org",
        "wikiversity.org",
        "mediawiki.org",
    }
)


def website(url: str) -> str:
    """The registered domain a URL belongs to - two pages of en. and de.wikipedia.org are one
    website; `bbc.co.uk` keeps its three labels; every Wikimedia project is `WIKIMEDIA`."""
    labels = (urlsplit(url).hostname or "").lower().split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    domain = ".".join(labels[-2:])
    return WIKIMEDIA if domain in _WIKIMEDIA_DOMAINS else domain


def _record(out: Path, round_no: int) -> dict[str, Any]:
    path = round_files(out, round_no).record
    if not path.is_file():
        raise ScopeReviewError(f"{path} does not exist - export round {round_no} first")
    return json.loads(path.read_text(encoding="utf-8"))


def check_answer(out: Path, round_no: int, batch_id: str, label: str, text: str) -> str | None:
    """The shape problem of an answer, or None - no page is fetched, no quote checked."""
    asked = {
        (q["batch_id"], q["site_id"]) for q in _read_jsonl(round_files(out, round_no).questions)
    }
    if (batch_id, label) not in asked:
        raise ScopeReviewError(f"{batch_id}/{label} is no question of round {round_no}")
    try:
        parse_answer(text)
    except ScopeReviewError as exc:
        return str(exc)
    return None


BRIEF = """You are Opus agent {batch} of the E3 scope review. You answer {count} question(s), each \
about another entry of a map of archaeological sites: is it an archaeological site at all? Answer \
each one on its own.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the \
repository - no other batch, nothing else under output/ or docs/, no database. Your evidence is \
your own web research.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide, exactly as the prompt asks. A not_a_site needs verbatim quotes \
from pages you read - copy them, never paraphrase.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched, your decision is not judged):
   ./.venv/Scripts/python.exe scripts/remediation/mechanical/scope_review.py check-answer \
--out {out} --round {round} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(out: Path, round_no: int, batch_id: str) -> str:
    handoff = Path(_record(out, round_no)["handoff"])
    count = sum(
        1 for q in _read_jsonl(round_files(out, round_no).questions) if q["batch_id"] == batch_id
    )
    if not count:
        raise ScopeReviewError(f"{batch_id} is no batch of round {round_no}")
    shown = handoff.resolve().as_posix()
    return BRIEF.format(
        batch=batch_id,
        count=count,
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        round=round_no,
        stage=STAGE,
        out=out.resolve().as_posix(),
    )


def import_round(out: Path, round_no: int, library: Q.Library, collect: Any) -> dict[str, Any]:
    """Every answer of a round: validated, re-prompted from the round's snapshot, parsed and, for a
    `not_a_site`, every cited page fetched once (`collect`) and every quote checked (`library`)."""
    record = _record(out, round_no)
    files = round_files(out, round_no)
    snapshot_text = files.snapshot.read_text(encoding="utf-8")
    if sha256_text(snapshot_text) != record["snapshot_sha256"]:
        raise ScopeReviewError(f"{files.snapshot} is not the snapshot round {round_no} recorded")
    snapshot = parse_export(snapshot_text)
    handoff = Path(record["handoff"])
    validation = OH.validate(handoff)
    if not validation.ok:
        raise ScopeReviewError(f"{handoff} does not validate: {validation.to_dict()}")
    by_id = snapshot.by_id()
    parsed: list[tuple[dict[str, Any], Answer, OH.Answer]] = []
    for q in _read_jsonl(files.questions):
        prompt = prompt_for(by_id[q["site_id"]], q["qid"])
        if OH.prompt_sha256(prompt) != q["prompt_sha256"]:
            raise ScopeReviewError(f"{q['site_id']}: the prompt is not the one the round asked")
        answer = OH.read_answer(
            handoff, batch_id=q["batch_id"], stage=STAGE, label=q["site_id"], prompt=prompt
        )
        parsed.append((q, parse_answer(answer.text), answer))
    collect(
        [quote["url"] for _q, a, _r in parsed if a.decision == NOT_A_SITE for quote in a.quotes]
    )
    rows = []
    for q, a, raw in parsed:
        results = [
            Q.check_quote(
                {"source": quote["url"], "quote": quote["quote"]},
                {"change_key": q["site_id"], "evidence_files": []},
                library,
            )
            for quote in a.quotes
        ]
        found = [r for r in results if r.outcome == Q.FOUND]
        counted = a.decision == SITE or len({website(r.source) for r in found}) >= MIN_SITES
        rows.append(
            {
                "site_id": q["site_id"],
                "qid": q["qid"],
                "round": round_no,
                "decision": a.decision,
                "kind": a.kind,
                "reason": a.reason,
                "quotes": [asdict(r) for r in results],
                "counted": counted,
                "premise": by_id[q["site_id"]]["premise"],
                "answered_by": raw.answered_by,
                "answered_at": raw.answered_at,
                "prompt_sha256": q["prompt_sha256"],
            }
        )
    _write_once(files.answers, _jsonl(rows))
    tally: dict[str, int] = {}
    for r in rows:
        key = f"{r['decision']}{'' if r['counted'] else ' (not counted)'}"
        tally[key] = tally.get(key, 0) + 1
    return {"round": round_no, "answers": len(rows), "tally": tally}


# ------------------------------------------------------------------------------ the plan
def decisions(out: Path) -> dict[str, dict[str, Any]]:
    """The counted `not_a_site` of every imported round, by site; a site counted twice is
    refused. A round exported but not yet imported stops the plan."""
    out_rows: dict[str, dict[str, Any]] = {}
    for round_no in range(MAX_ROUND + 1):
        files = round_files(out, round_no)
        if not files.record.is_file():
            break
        if not files.answers.is_file():
            raise ScopeReviewError(f"round {round_no} is exported but not imported")
        for row in _read_jsonl(files.answers):
            if row["decision"] == NOT_A_SITE and row["counted"]:
                if row["site_id"] in out_rows:
                    raise ScopeReviewError(f"{row['site_id']} is decided in two rounds")
                out_rows[row["site_id"]] = row
    return out_rows


def reinstatements(export: Export) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """The scope-e4 rule-(a) retirements the O7 rule no longer carries: (site, journal row)."""
    by_id = export.by_id()
    out = []
    for entry in export.journal:
        if entry["new_value"] != RETIRED:
            continue
        site = by_id.get(str(entry["row_pk"]))
        if site is None or site["scope_status"] != RETIRED:
            continue
        if not str(site["scope_reason"] or "").startswith("E3: period_start"):
            continue
        if e3_region(site) == OCEANIA and passes_date_cutoff(site):
            out.append((site, entry))
    return out


def _cells(
    site: Mapping[str, Any], status: str, reason: str, rule: str, evidence: Sequence[dict[str, Any]]
) -> list[Verdict]:
    return [
        Verdict(
            site_id=str(site["id"]),
            site_name=str(site["name"]),
            ok=True,
            old_value=site[column],
            new_value=value,
            rule=rule,
            reason="",
            note=f"{column} {site[column]!r} -> {value!r}",
            phase3=False,
            finding_test_id=TEST_ID,
            evidence=tuple(evidence),
            premise=str(site["premise"]),
            column=column,
        )
        for column, value in (("scope_status", status), ("scope_reason", reason))
    ]


def _skip(site: Mapping[str, Any], rule: str, note: str) -> Verdict:
    return Verdict(
        site_id=str(site["id"]),
        site_name=str(site["name"]),
        ok=False,
        old_value=site["scope_status"],
        new_value=None,
        rule="",
        reason=rule,
        note=note,
        phase3=False,
        finding_test_id=TEST_ID,
        column="scope_status",
    )


def build_plan(
    export: Export, decided: Mapping[str, Mapping[str, Any]], *, built_at: str, lane: Lane
) -> Plan:
    """Every decision the export still leaves open, as the lane's cells - all of them; a wave is
    its first `MAX_SITES` sites (`first_wave`)."""
    by_id = export.by_id()
    changes: list[Verdict] = []
    skipped: list[Verdict] = []
    for sid, row in sorted(decided.items()):
        site = by_id.get(sid)
        if site is None:
            raise ScopeReviewError(f"{sid} is decided but not in the export")
        if site["scope_status"] == RETIRED:
            skipped.append(_skip(site, "already-retired", "retired since the question was asked"))
            continue
        if site["premise"] != row["premise"]:
            skipped.append(
                _skip(
                    site,
                    "premise-moved",
                    f"the entry the answer judged ({row['premise']}) is now {site['premise']}: "
                    "ask it again in a new review",
                )
            )
            continue
        reason = f"{NOT_A_SITE_PREFIX} ({row['kind']}): {row['reason']}"
        evidence = [
            {"source": q["source"], "url": q["source"], "quote": q["quote"]}
            for q in row["quotes"]
            if q["outcome"] == Q.FOUND
        ] + [{"source": f"opus:{row['answered_by']}", "url": "handoff", "quote": row["reason"]}]
        changes += _cells(site, RETIRED, reason, "e3-not-a-site", evidence)
    for site, entry in reinstatements(export):
        reason = (
            "E3 with O7 (owner, 2026-09-26: Oceania through 1500 AD): period_start "
            f"{site['period_start']} lies inside the window; the scope-e4 retirement no longer holds"
        )
        evidence = [
            {
                "source": f"remediation_change_log:{entry['id']}",
                "url": "remediation_change_log",
                "quote": f"{entry['run_stamp']}: scope_status {entry['old_value']} -> retired",
            },
            {"source": "pipeline/normalizers/dates.py", "url": "e3_region", "quote": "Oceania"},
        ]
        changes += _cells(site, IN_SCOPE, reason, "o7-oceania", evidence)
    sites = {c.site_id for c in changes}
    counters = {
        "sites": len(sites),
        "cells": len(changes),
        "not_a_site": sum(1 for c in changes if c.rule == "e3-not-a-site") // 2,
        "o7_reinstated": sum(1 for c in changes if c.rule == "o7-oceania") // 2,
        "skipped": len(skipped),
    }
    return Plan(tuple(changes), tuple(skipped), built_at=built_at, counters=counters, lane=lane)


def first_wave(plan: Plan) -> Plan:
    """The plan's first `MAX_SITES` sites (by id), whole sites only; the rest waits for the next
    wave, planned from a new export."""
    chosen = set(sorted({c.site_id for c in plan.changes})[:MAX_SITES])
    return Plan(
        tuple(c for c in plan.changes if c.site_id in chosen),
        plan.skipped,
        built_at=plan.built_at,
        counters=dict(plan.counters)
        | {"wave_sites": len(chosen), "left_for_later_waves": plan.counters["sites"] - len(chosen)},
        lane=plan.lane,
    )


SOURCE = "SOURCE.json"


def write_wave(out: Path, wave: str, *, built_at: str) -> dict[str, Any]:
    """The next wave: the first `MAX_SITES` open sites of the current export, into `out/<wave>/` -
    with the default `out` the wave lane's own directory (`apply.lane_dir`), where `apply.py
    --lane scope-review-<wave>` reads it. Refused when the export already planned a wave, or the
    wave has a plan."""
    lane = scope_review_lane(wave)
    target = out / wave
    export = read_export(export_path(out))
    for earlier in sorted(out.glob(f"*/{SOURCE}")):
        if json.loads(earlier.read_text(encoding="utf-8"))["export_sha256"] == export.sha256:
            raise ScopeReviewError(
                f"{earlier.parent.name} was planned from this export - run `export` again first"
            )
    if (target / "PLAN.jsonl").exists():
        raise ScopeReviewError(
            f"{target} holds a plan already - a delivered plan is never replaced"
        )
    plan = first_wave(build_plan(export, decisions(out), built_at=built_at, lane=lane))
    if not plan.changes:
        raise ScopeReviewError("the export leaves nothing to write - the review is done")
    target.mkdir(parents=True, exist_ok=True)
    write_plan_jsonl(plan, target / "PLAN.jsonl")
    write_skipped_jsonl(plan, target / "SKIPPED.jsonl")
    write_rollback_sql(plan, target / "ROLLBACK.sql", plan_path=target / "PLAN.jsonl")
    lines = [
        f"# E3 scope review - wave {wave}",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/scope_review.py` from the export "
        f"of {export.exported_at}. Lane `{lane.name}`, run stamp `{lane.run_stamp}`, test id "
        f"`{lane.test_id}`.",
        "",
        "```json",
        json.dumps(dict(plan.counters), indent=1, sort_keys=True),
        "```",
        "",
    ]
    for change in plan.changes:
        if change.column == "scope_reason":
            lines.append(f"* **{change.site_name}** (`{change.site_id}`): {change.new_value}")
            lines += [f"  * {e['source']}: {e['quote']}" for e in change.evidence]
    (target / "PLAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    source = {"export_sha256": export.sha256, "exported_at": export.exported_at, "wave": wave}
    _write_once(target / SOURCE, json.dumps(source, indent=1, sort_keys=True) + "\n")
    return dict(plan.counters) | {"lane": lane.name, "dir": str(target)}


# ------------------------------------------------------------------------------------- CLI
def _wave(label: str) -> str:
    """`--wave`: a label `apply.py --lane scope-review-<label>` resolves, else argparse's error."""
    try:
        scope_review_lane(label)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return label


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    cmds = {
        name: sub.add_parser(name, help=helps)
        for name, helps in (
            ("export", "read production (read-only) into export/export.jsonl"),
            ("export-round", "the round's questions into a new handoff directory"),
            ("brief", "the instruction of one batch's Opus agent"),
            ("check-answer", "the shape of one answer, before it is recorded"),
            ("import-round", "parse, fetch every cited page once, check every quote"),
            ("write", "the next wave's plan: PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql"),
        )
    }
    for cmd in cmds.values():
        cmd.add_argument("--out", type=Path, default=DEFAULT_OUT)
    for name in ("export-round", "brief", "check-answer", "import-round"):
        cmds[name].add_argument("--round", type=int, required=True)
    cmds["export-round"].add_argument("--handoff", type=Path, required=True)
    cmds["export-round"].add_argument("--harvest", type=Path, default=DEFAULT_HARVEST)
    for name in ("brief", "check-answer"):
        cmds[name].add_argument("--batch-id", required=True)
    cmds["check-answer"].add_argument("--label", required=True)
    cmds["check-answer"].add_argument("--text-file", type=Path, required=True)
    cmds["write"].add_argument(
        "--wave",
        required=True,
        type=_wave,
        help="the wave's date label (2026-09-26, 2026-09-26b, ...)",
    )
    args = ap.parse_args(argv)
    out: Path = args.out
    try:
        if args.command == "export":
            path = write_tagged_export(tagged_export_script(EXPORT_PARTS), export_path(out))
            export = read_export(path)
            print(json.dumps({"export": str(path), "sites": len(export.sites)}))
        elif args.command == "export-round":
            record = export_round(out, args.handoff, args.round, load_harvest(args.harvest))
            print(json.dumps(record, indent=1, sort_keys=True))
        elif args.command == "brief":
            print(brief(out, args.round, args.batch_id))
        elif args.command == "check-answer":
            text = args.text_file.read_bytes().decode("utf-8")
            problem = check_answer(out, args.round, args.batch_id, args.label, text)
            print(json.dumps({"ok": problem is None, "problem": problem}))
            return 0 if problem is None else 1
        elif args.command == "import-round":
            pages = out / "pages"
            client = research_web.client()

            def collect(urls: Sequence[str]) -> None:
                Q.collect(urls, pages, client, now=lambda: datetime.now(UTC).isoformat())

            result = import_round(out, args.round, Q.Library(REPO, pages), collect)
            print(json.dumps(result, indent=1, sort_keys=True))
        else:
            result = write_wave(out, args.wave, built_at=_now())
            print(json.dumps(result, indent=1, sort_keys=True))
    except (PlanError, OH.HandoffError, Q.AuditError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
