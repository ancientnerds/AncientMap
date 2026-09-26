"""WD1 step 3: every site with a field in CONFLICT, MISSING or flagged, asked of Opus, imported.

No model is called here. The orchestrator's cycle (run from the repository root;
`F=scripts/remediation/fields/handoff.py`, `R=output/remediation/fields/wd1`,
`H=output/remediation/handoff/fields-wd1`):

    $F export --run $R --handoff $H-r0          one question per site, its flagged fields only,
                                                batches of `BATCH_SIZE` sites (country, name order)
    $F brief --run $R --handoff $H-r0 --batch-id B      the instruction of batch B's Opus agent;
        the agent answers each question and records it with `opus_handoff.py answer`
    $F check-answer --run $R --handoff $H-r0 --batch-id B --label L --text-file F
                                                the answer's shape and page-free checks
    opus_handoff.py validate --dir $H-r0        every answer in, in shape, by Opus
    $F import --run $R                          parse, fetch every quoted page once, quote-check,
                                                decide: ATTEMPTS.jsonl, DECISIONS.jsonl, REASK.json
    $F export-reask --run $R --handoff $H-r1    the fields without a counted answer, to new agents
                                                (at most `MAX_ROUND` times; answer, validate, import)
    $F status --run $R

**A question** is one site (`label` = its id) and exactly its flagged fields, rendered from
CLASSIFIED.jsonl (`classify.py`): the site, what the machine found per field and why it is asked,
the field's rules, how to research and quote (the acceptance's research text, `acceptance.questions.
RESEARCH`), and the answer format (`answers.py`). Import renders every prompt again and refuses one
that is not the prompt the manifest names - a question is answered as it was asked.

**A field counts** when its answer passes `answers.check_shape` and every quote is found verbatim in
its page as fetched once by this run (`opus_audit/quotes.py`: NFC and whitespace only), and - for a
source_url value - the value's page was served (2xx) at that URL, not redirected to another page,
and, on Wikipedia, is an article of its own (not missing, not a redirect, not a disambiguation page:
the wiki's API, `harvest.resolve_wiki_titles`). A field without a counted answer is asked again, of
a new agent, at most `MAX_ROUND` times; then it is **exhausted**: a clearable field is cleared (owner
decision O6: "replace only with a sourced value, else empty the field"), the coordinates stay and
are held for the owner - a point cannot be cleared.

Files in `--run` (beside CLASSIFIED.jsonl): ROUNDS.jsonl (every exported round, its directory, its
batches and each question's fields), ATTEMPTS.jsonl (every answer of every round as parsed, each
field's quotes and their outcomes, whether it counted), DECISIONS.jsonl (one line per decided
site and field - what `plan.py` writes from), REASK.json, PAGES.jsonl and `pages/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
from acceptance.answers import AnswerError  # noqa: E402
from acceptance.questions import RESEARCH, definitions  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from phase4.route_stage import wikipedia_title  # noqa: E402

from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import harvest as H  # noqa: E402

STAGE = "wd1"
BATCH_SIZE = 8
#: Round 0 and two re-asks, as the acceptance does.
MAX_ROUND = 2
ROUNDS_FILE = "ROUNDS.jsonl"
ATTEMPTS_FILE = "ATTEMPTS.jsonl"
DECISIONS_FILE = "DECISIONS.jsonl"
REASK_FILE = "REASK.json"
PAGES_DIR = "pages"
PAGES_INDEX = "PAGES.jsonl"
COUNTED, EXHAUSTED = "counted", "exhausted"


class HandoffStepError(ValueError):
    """The step must not run on this state. Nothing was written by it."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO / path


def _shown(path: Path) -> str:
    try:
        return _resolve(path).resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def read_classified(run: Path) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(run / C.CLASSIFIED_FILE)
    if not rows:
        raise HandoffStepError(f"{run / C.CLASSIFIED_FILE} is missing or empty - classify first")
    return {row["site_id"]: row for row in rows}


def read_rounds(run: Path) -> list[dict[str, Any]]:
    return _read_jsonl(run / ROUNDS_FILE)


# ------------------------------------------------------------------------------ the question
FIELD_RULES = {
    "coordinates": (
        "The site's point: the place of the site itself - its centre or its main monument - not "
        "the nearest village, a namesake, the museum that keeps its finds, the hill or island it "
        "stands on, or the region.\n"
        f"- keep: two independent sources give a point within {A.KEEP_KM:g} km of the stored point. "
        'value = "lat, lon" of the point they give, in decimal degrees.\n'
        f"- replace: the stored point is more than {A.KEEP_KM:g} km from the site; two independent "
        'sources give the site\'s point. value = "lat, lon" in decimal degrees (at most 6 '
        "decimals).\n"
        "- unresolved: no two independent sources can be quoted for the site's point. The point "
        "cannot be emptied: every site stays on the map, and an unresolved point is held for the "
        "owner.\n"
        "Each quote must hold exactly the two coordinates as the page prints them - signed decimal "
        'degrees, latitude first ("51.1789, -1.8262"), or degrees with a hemisphere letter each '
        '("51°10′44″N 1°49′34″W", "51.1789°N 1.8262°W") - with nothing around them but labels such '
        f'as "Coordinates:". They must lie within {A.KEEP_KM:g} km of your value. A grid reference '
        "(OSGB, UTM) is not read."
    ),
    "period_start": (
        "period_start is the year the site's securely attested history as a site begins - its "
        "construction, foundation or first occupation - negative for BC. The map shows only its "
        "bucket.\n"
        "- keep: two independent sources date the start into the stored value's bucket. value = "
        "the attested start year.\n"
        "- replace: the attested start lies in another bucket (or the field is empty). value = "
        'that year, e.g. "-2500" for c. 2500 BC; a century as its first year ("the 8th century BC" '
        '-> "-800", "the 2nd century AD" -> "101").\n'
        "- clear: no two independent sources date the start. The field is emptied - an empty "
        "field beats a wrong one.\n"
        "Each quote must carry the date as the page states it (a year, a century, a millennium)."
    ),
    "site_type": (
        "site_type is one canonical type: the most specific one that holds what the sources say "
        "the site is. A generic type (Ruin, Archaeological site, Site, Heritage site, Scheduled "
        "monument) only when nothing more specific fits.\n"
        "- keep: two independent sources describe the site as the stored type. value = the stored "
        "type.\n"
        "- replace: the sources describe it as another type. value = one canonical type.\n"
        "- clear: no two independent sources say what kind of site it is. The field is emptied.\n"
        'At least one quote must hold a word of the chosen type ("temple" for Temple, '
        '"tumulus" or "mound" for Mound/tumulus).'
    ),
    "source_url": (
        "source_url is the page the site's entry names as its source. It must load without a "
        "login or a script and be about this very site - not the island, town, region or hill it "
        "lies in, not a namesake, not a list. Prefer the site's own Wikipedia article in English, "
        "else in another language, else a heritage register entry or a scholarly page.\n"
        "- keep: the stored page is about this site. value = the stored URL, unchanged.\n"
        "- replace: another page is about this site. value = its URL - the article's own URL, not "
        "a redirect, a section link, a search or a translation proxy.\n"
        "- clear: no page about this site can be found. The field is emptied.\n"
        "For keep and replace, at least one quote is from the value's page itself and names the "
        "site; a second quote, from an independent source family, names it too."
    ),
}

KNOWN_FETCH_TROUBLE = (
    "## Pages the quote check cannot read\n"
    "\n"
    "The checker fetches each page once with a plain GET and no browser. From this workstation it "
    "has been refused by Historic England's list and the Heritage Gateway (403), the Megalithic "
    "Portal (megalithic.co.uk) did not answer it (all 46 pages asked on 2026-09-26 timed out or "
    "gave 503), and it cannot read scanned PDFs or pages that build their text with scripts. "
    "Wikipedia (every language), Wikidata, UNESCO, Pleiades and most national registers and "
    "museum pages work. Prefer pages that show their text as plain HTML; a quote from a page the "
    "checker cannot read does not count.\n"
)

ANSWER_FORMAT = (
    "## Your answer\n"
    "\n"
    'One JSON object and nothing else: {{"fields": {{...}}}} with exactly these keys: {keys}. Each '
    "is\n"
    '{{"decision": "...", "value": "..." or null, "quotes": [{{"url": "https://...", "quote": '
    '"verbatim text"}}], "reasoning": "..."}}\n'
    "keep and replace carry the value and at least two quotes from at least two independent "
    "source families; clear and unresolved carry value null and quotes []. The reasoning says, in "
    "a sentence or two, what the sources say and why that decides it.\n"
)


def _evidence_lines(field: str, status: Mapping[str, Any]) -> list[str]:
    ev = status["evidence"]
    lines: list[str] = []
    if field == "coordinates":
        for w in ev.get("witnesses", []):
            lines.append(
                f"  - {w['source']}: {w['point'][0]}, {w['point'][1]} "
                f"({w['km_from_stored']} km from the stored point)"
            )
        if ev.get("stacked"):
            lines.append(
                f"  - {ev['stacked']} other site(s) of the database hold exactly the stored point"
            )
    elif field == "period_start":
        for d in ev.get("dates", []):
            lines.append(f"  - wikidata {d['property']}: {d['time']}")
        for d in ev.get("modern", []):
            lines.append(
                f"  - wikidata {d['property']}: {d['time']} - not read: a date from "
                f"{C.MODERN} AD on is a designation, park or museum date, not the site's start"
            )
        if status["stored"] is not None:
            lines.append(f"  - the stored value's bucket: {C.bucket(int(status['stored']))}")
    elif field == "site_type":
        for c in ev.get("classes", []):
            lines.append(f"  - the item is an instance of: {c['label']} ({c['qid']})")
    else:
        kind = ev.get("kind")
        if kind == H.URL_WIKIPEDIA:
            lines.append(
                f"  - {ev['lang']}.wikipedia: resolves to {ev['resolved_title']!r}"
                + (f"#{ev['fragment']}" if ev.get("fragment") else "")
                + (" (a redirect)" if ev.get("redirected") else "")
                + (" - missing" if ev.get("missing") else "")
            )
        elif kind == H.URL_WEB:
            lines.append(
                f"  - HTTP {ev.get('status')}, served at {ev.get('final_url')}, title "
                f"{ev.get('page_title')!r}" + (f", error {ev['error']}" if ev.get("error") else "")
            )
    return lines


def render_prompt(line: Mapping[str, Any], fields: Sequence[str]) -> str:
    """The exact question for one site and `fields` - a pure function of the classified line."""
    fields = [f for f in C.FIELDS if f in fields]
    if not fields:
        raise HandoffStepError(f"{line['site_id']}: a question needs at least one field")
    item = line["qid"]
    out = [
        "You are an Opus researcher in the structured-field repair (lane WD1) of a curated database "
        "of ancient sites. This question is about ONE site and the fields listed below. Research "
        "each field on its own and decide it from sources you quote.",
        "",
        "## The site",
        "",
        f"- name: {line['name']}",
        f"- country: {line['country']}",
        f"- stored point: {line['fields']['coordinates']['stored']} (latitude, longitude)",
        f"- Wikidata item: {'https://www.wikidata.org/wiki/' + item if item else 'none'}"
        + (
            f" - possibly not the site: it is a {', '.join(line['identity']['containers'])}"
            if line["identity"]["doubt"]
            else ""
        ),
        f"- English Wikipedia article of the item: {line['enwiki'] or 'none'}",
        "",
        "## The fields you decide",
        "",
    ]
    for field in fields:
        status = line["fields"][field]
        out.append(f"### {field}")
        out.append("")
        out.append(f"Stored value: {json.dumps(status['stored'], ensure_ascii=False)}")
        out.append(f"Why you are asked: {status['status']} - {status['reason']}")
        evidence = _evidence_lines(field, status)
        if evidence:
            out.append("What the machine read:")
            out.extend(evidence)
        if status["flags"]:
            out.append(
                "An earlier reading found this field wrong (a lead to check, not evidence - "
                "decide from the sources you quote):"
            )
            out.extend(f"  - {flag}" for flag in status["flags"])
        if status["stored"] is None:
            out.append(
                "The field is empty, so keep is no answer: replace with a sourced value, or clear "
                "to leave it empty."
            )
        out.append("")
        out.append(FIELD_RULES[field])
        vocabulary = definitions(field)
        if vocabulary:
            out.append("")
            out.append(vocabulary)
        out.append("")
    out.append(RESEARCH)
    out.append(KNOWN_FETCH_TROUBLE)
    out.append(ANSWER_FORMAT.format(keys=", ".join(f'"{f}"' for f in fields)))
    return "\n".join(out)


# ------------------------------------------------------------------------------ export
def batches(
    labels: Sequence[str], classified: Mapping[str, Any], round_no: int
) -> list[tuple[str, list[str]]]:
    """Sites by country, then name, cut into batches of `BATCH_SIZE` - one agent reads one
    country's registers for a whole batch."""
    ordered = sorted(
        labels,
        key=lambda s: (classified[s]["country"] or "", classified[s]["name"].casefold(), s),
    )
    return [
        (f"wd1-r{round_no}-b{number + 1:04d}", ordered[i : i + BATCH_SIZE])
        for number, i in enumerate(range(0, len(ordered), BATCH_SIZE))
    ]


def _export_round(
    run: Path, handoff: Path, round_no: int, fields_of: Mapping[str, Sequence[str]]
) -> dict[str, Any]:
    rounds = read_rounds(run)
    if any(r["round"] == round_no for r in rounds):
        raise HandoffStepError(f"round {round_no} is already exported")
    target = _resolve(handoff)
    if target.exists() and any(target.iterdir()):
        raise HandoffStepError(f"{handoff} is not empty: a round gets a directory of its own")
    classified = read_classified(run)
    groups = batches(list(fields_of), classified, round_no)
    for batch_id, labels in groups:
        for label in labels:
            OH.export(
                target,
                batch_id=batch_id,
                stage=STAGE,
                label=label,
                field="+".join(fields_of[label]),
                prompt=render_prompt(classified[label], fields_of[label]),
            )
    record = {
        "round": round_no,
        "handoff": _shown(handoff),
        "batches": dict(groups),
        "fields": {label: list(fields_of[label]) for label in sorted(fields_of)},
        "exported_at": H.now(),
    }
    _write_jsonl(run / ROUNDS_FILE, [*rounds, record])
    return {
        "round": round_no,
        "handoff": record["handoff"],
        "sites": len(fields_of),
        "fields": sum(len(f) for f in fields_of.values()),
        "batches": len(groups),
    }


def export(run: Path, handoff: Path) -> dict[str, Any]:
    """Round 0: every site with a field in CONFLICT or MISSING or flagged, with exactly those fields."""
    if read_rounds(run):
        raise HandoffStepError("round 0 is exported already - re-asks go through export-reask")
    classified = read_classified(run)
    fields_of = {sid: line["asked"] for sid, line in classified.items() if line["asked"]}
    return _export_round(run, handoff, 0, fields_of)


def export_reask(run: Path, handoff: Path) -> dict[str, Any]:
    rounds = read_rounds(run)
    if not rounds:
        raise HandoffStepError("nothing was exported")
    last = max(r["round"] for r in rounds)
    reask_path = run / REASK_FILE
    if not reask_path.exists():
        raise HandoffStepError(f"import round {last} before a re-ask")
    reask = json.loads(reask_path.read_text(encoding="utf-8"))
    if reask["after_round"] != last:
        raise HandoffStepError(f"import round {last} before a re-ask")
    if not reask["fields"]:
        raise HandoffStepError("nothing to ask again")
    if last >= MAX_ROUND:
        raise HandoffStepError(
            f"round {last} was the last: a field is asked at most {MAX_ROUND + 1} times"
        )
    return _export_round(run, handoff, last + 1, reask["fields"])


# ------------------------------------------------------------------------------ the agent's aids
def _round_of(run: Path, handoff: Path) -> dict[str, Any]:
    wanted = _resolve(handoff).resolve()
    for record in read_rounds(run):
        if _resolve(Path(record["handoff"])).resolve() == wanted:
            return record
    raise HandoffStepError(f"{handoff} is not the directory of an exported round of {run}")


def check_answer(run: Path, handoff: Path, batch_id: str, label: str, text: str) -> dict[str, Any]:
    """The shape and page-free problems of one answer, per field - nothing is fetched."""
    record = _round_of(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise HandoffStepError(f"{batch_id}/{label} is no question of {handoff}")
    line = read_classified(run)[label]
    try:
        checked = A.check_shape(text, record["fields"][label], line)
    except AnswerError as exc:
        return {"ok": False, "problems": {"answer": str(exc)}}
    problems = {f: a for f, a in checked.items() if isinstance(a, str)}
    return {"ok": not problems, "problems": problems}


BRIEF = """You are Opus researcher {batch} of the WD1 structured-field repair. You answer {count} \
question(s), each about another site. Answer each one on its own, as if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the repository - \
no other batch, nothing else under output/ or docs/, no database, no git history. Your evidence is your \
own web research, as each prompt says: heritage registers, Wikidata, Wikipedia in any language, \
Pleiades, excavation reports, museum and university pages.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide each field, exactly as the prompt asks. Copy every quote from the \
page itself, character for character.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it (nothing is fetched; the quotes are checked against their pages at import):
   ./.venv/Scripts/python.exe scripts/remediation/fields/handoff.py check-answer --run {run} \
--handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problems per field, if any: fix the answer, never the finding - a field you cannot \
source is "clear" (or "unresolved" for coordinates).
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    record = _round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise HandoffStepError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return BRIEF.format(
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        stage=STAGE,
    )


# ------------------------------------------------------------------------------ import
def _value_page_problem(value: str, pages: Path, net: Fetcher | None) -> str | None:
    """Why a source_url value is not a served page of its own, or None."""
    meta_path = pages / f"{Q.url_key(value)}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta["status"] is None or not 200 <= int(meta["status"]) < 300:
        return f"the value's page was not served: {meta['error'] or 'HTTP ' + str(meta['status'])}"
    if not C._same_page(value, str(meta["final_url"])):
        return f"the value's page redirects to {meta['final_url']}"
    titled = wikipedia_title(value)
    if titled is None:
        return None
    if net is None:
        raise HandoffStepError("a Wikipedia value needs the API client to be resolved")
    lang, title = titled
    record = H.resolve_wiki_titles(net, lang, [title])[title]
    if record["missing"] or record["invalid"]:
        return "the value's article does not exist"
    if record["redirected"]:
        return (
            f"the value is a redirect to {record['resolved_title']!r}: give the article's own URL"
        )
    if record["disambiguation"]:
        return "the value is a disambiguation page"
    return None


def import_rounds(
    run: Path,
    *,
    client: httpx.Client | None = None,
    net: Fetcher | None = None,
    pace: float = Q.PACE_SECONDS,
) -> dict[str, Any]:
    """Every round's answers: validated, parsed, quote-checked, decided."""
    classified = read_classified(run)
    rounds = sorted(read_rounds(run), key=lambda r: r["round"])
    if not rounds:
        raise HandoffStepError("nothing was exported")
    attempts: list[dict[str, Any]] = []
    for record in rounds:
        handoff = _resolve(Path(record["handoff"]))
        check = OH.validate(handoff)
        if not check.ok:
            raise HandoffStepError(
                f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
                f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
                "answer is validated before anything is imported"
            )
        manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
        asked = {(b, label) for b, labels in record["batches"].items() for label in labels}
        if set(manifest) != asked:
            raise HandoffStepError(f"{record['handoff']}: the manifest is not the round's record")
        for (batch_id, label), line in sorted(manifest.items()):
            fields = record["fields"][label]
            prompt = render_prompt(classified[label], fields)
            if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
                raise HandoffStepError(
                    f"{batch_id}/{label}: the exported prompt is not this question's"
                )
            answer = OH.read_answer(
                handoff, batch_id=batch_id, stage=STAGE, label=label, prompt=prompt
            )
            try:
                checked = A.check_shape(answer.text, fields, classified[label])
            except AnswerError as exc:
                checked = dict.fromkeys(fields, f"malformed answer: {exc}")
            for field in fields:
                parsed = checked[field]
                attempts.append(
                    {
                        "round": record["round"],
                        "batch_id": batch_id,
                        "site_id": label,
                        "field": field,
                        "answered_by": answer.answered_by,
                        "answered_at": answer.answered_at,
                        "answer": None if isinstance(parsed, str) else parsed.to_dict(),
                        "problem": parsed if isinstance(parsed, str) else None,
                    }
                )

    pages = run / PAGES_DIR
    urls = sorted({q[0] for a in attempts if a["answer"] for q in a["answer"]["quotes"]})
    if urls:
        if client is None:
            with H.open_client() as own:
                Q.collect(urls, pages, own, now=H.now, pace=pace)
        else:
            Q.collect(urls, pages, client, now=H.now, pace=pace)
    library = Q.Library(REPO, pages)
    own_net = net is None and any(
        a["answer"] and a["field"] == "source_url" and wikipedia_title(str(a["answer"]["value"]))
        for a in attempts
    )
    api = H.open_fetcher(run) if own_net else net
    try:
        for attempt in attempts:
            answer = attempt["answer"]
            if answer is None:
                attempt.update(counted=False, reason=attempt["problem"], quotes=[])
                continue
            results = [
                asdict(
                    Q.check_quote(
                        {"source": u, "quote": q},
                        {"change_key": attempt["site_id"], "evidence_files": []},
                        library,
                    )
                )
                for u, q in answer["quotes"]
            ]
            failed = [r for r in results if r["outcome"] != Q.FOUND]
            reason = None
            if failed:
                reason = f"quote {failed[0]['outcome']}: {failed[0]['source']}"
            elif attempt["field"] == "source_url" and answer["decision"] in (A.KEEP, A.REPLACE):
                reason = _value_page_problem(str(answer["value"]), pages, api)
            attempt.update(counted=reason is None, reason=reason, quotes=results)
    finally:
        if own_net and api is not None:
            api.close()

    decisions, waiting = _decide(rounds, attempts, classified)
    _write_jsonl(run / ATTEMPTS_FILE, attempts)
    _write_jsonl(run / DECISIONS_FILE, decisions)
    _write_json(run / REASK_FILE, {"after_round": rounds[-1]["round"], "fields": waiting})
    _write_jsonl(run / PAGES_INDEX, Q.page_index(urls, pages) if urls else [])
    return {
        "rounds": len(rounds),
        "attempts": len(attempts),
        "counted": sum(1 for a in attempts if a["counted"]),
        "not_counted": dict(
            sorted(
                Counter(
                    str(a["reason"]).split(":")[0] for a in attempts if not a["counted"]
                ).items()
            )
        ),
        "decisions": dict(
            sorted(Counter(f"{d['field']}:{d['decision']}" for d in decisions).items())
        ),
        "waiting_sites": len(waiting),
        "waiting_fields": sum(len(v) for v in waiting.values()),
        "urls": len(urls),
    }


def _decide(
    rounds: Sequence[Mapping[str, Any]],
    attempts: Sequence[Mapping[str, Any]],
    classified: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Each asked (site, field): its counted answer, or - after the last round - exhausted."""
    by_cell: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for attempt in attempts:
        by_cell.setdefault((attempt["site_id"], attempt["field"]), []).append(attempt)
    decisions: list[dict[str, Any]] = []
    waiting: dict[str, list[str]] = {}
    for (site, field), tries in sorted(by_cell.items()):
        tries = sorted(tries, key=lambda a: a["round"])
        if [a["round"] for a in tries] != sorted({a["round"] for a in tries}):
            raise HandoffStepError(f"{site}/{field}: asked twice in one round")
        counted = [a for a in tries if a["counted"]]
        if len(counted) > 1 or (counted and counted[0] is not tries[-1]):
            raise HandoffStepError(f"{site}/{field}: asked again after a counted answer")
        line = classified[site]
        base = {
            "site_id": site,
            "name": line["name"],
            "field": field,
            "status": line["fields"][field]["status"],
            "stored": line["fields"][field]["stored"],
            "asked": len(tries),
        }
        if counted:
            answer = counted[0]["answer"]
            decisions.append(
                {
                    **base,
                    "decision": answer["decision"],
                    "value": answer["value"],
                    "via": COUNTED,
                    "round": counted[0]["round"],
                    "answered_by": counted[0]["answered_by"],
                    "quotes": counted[0]["quotes"],
                    "reasoning": answer["reasoning"],
                }
            )
        elif tries[-1]["round"] >= MAX_ROUND:
            decisions.append(
                {
                    **base,
                    "decision": A.UNRESOLVED if field == "coordinates" else A.CLEAR,
                    "value": None,
                    "via": EXHAUSTED,
                    "round": tries[-1]["round"],
                    "answered_by": None,
                    "quotes": [],
                    "reasoning": f"no counted answer in {len(tries)} rounds: "
                    + "; ".join(str(a["reason"]) for a in tries),
                }
            )
        else:
            waiting.setdefault(site, []).append(field)
    return decisions, {site: sorted(f, key=C.FIELDS.index) for site, f in sorted(waiting.items())}


def status(run: Path) -> dict[str, Any]:
    rounds = read_rounds(run)
    decisions = _read_jsonl(run / DECISIONS_FILE)
    return {
        "rounds": [
            {
                "round": r["round"],
                "handoff": r["handoff"],
                "batches": len(r["batches"]),
                "sites": len(r["fields"]),
            }
            for r in rounds
        ],
        "decisions": dict(
            sorted(Counter(f"{d['field']}:{d['decision']}:{d['via']}" for d in decisions).items())
        ),
    }


# ------------------------------------------------------------------------------ the CLI
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {}
    for name in ("export", "export-reask", "brief", "check-answer", "import", "status"):
        commands[name] = sub.add_parser(name)
        commands[name].add_argument("--run", type=Path, default=C.DEFAULT_OUT)
    for name in ("export", "export-reask", "brief", "check-answer"):
        commands[name].add_argument("--handoff", type=Path, required=True)
    for name in ("brief", "check-answer"):
        commands[name].add_argument("--batch-id", required=True)
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", type=Path, required=True)
    commands["import"].add_argument("--pace", type=float, default=Q.PACE_SECONDS)
    args = parser.parse_args(argv)
    run = _resolve(args.run)
    try:
        if args.command == "export":
            result: Any = export(run, args.handoff)
        elif args.command == "export-reask":
            result = export_reask(run, args.handoff)
        elif args.command == "brief":
            print(brief(run, args.handoff, args.batch_id))
            return 0
        elif args.command == "check-answer":
            text = _resolve(args.text_file).read_bytes().decode("utf-8")
            result = check_answer(run, args.handoff, args.batch_id, args.label, text)
            print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
            return 0 if result["ok"] else 1
        elif args.command == "import":
            result = import_rounds(run, pace=args.pace)
        else:
            result = status(run)
    except (HandoffStepError, OH.HandoffError, Q.AuditError, H.HarvestError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
