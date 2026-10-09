"""Lane wd5, step 6 of the map: the Opus adversarial re-check of every cell the lane would write.

The researchers of lane wd5 (Sonnet high, `roles.ROLES["field_researcher"]`) decide a field from one
quote of one source. Before any of it reaches production a second reader, Opus high
(`roles.ROLES["adversarial"]`), is asked to break each decision that would be written: **every
`replace`** (the cells the plan writes, the carried points among them) and **10 % of the `keep`s**
(a seeded draw: a keep writes nothing, but a MiniMax keep that Claude confirms is what lets the value
stand). It sees the quote and the page the machine found it in - the passage around the quote, the
head of the page, the lead of the site's own Wikipedia article from the shared cache - and answers one
of

* `confirm` - the quote, read in its page, states the value for this very site;
* `reject` - it does not (another site, a class of monuments, a wrong conversion, a better source
  says otherwise);
* `unclear` - the page and the sources the checker could reach do not decide it.

    adversarial.py select  --run RUN --seed N     adv/CELLS.json: the cells, frozen with their prompts
    adversarial.py export  --adv ADV --handoff H  round 0: one check question per cell, batches of 8
    adversarial.py brief   --adv ADV --handoff H --batch-id B     the instruction of batch B's agent
    adversarial.py check-answer --adv ADV --handoff H --batch-id B --label L --text-file F
    adversarial.py import  --adv ADV              parse, role-check, machine-check the counter-quotes
    adversarial.py export-reask --adv ADV --handoff H1      round 1: the cells nobody decided
    adversarial.py apply   --run RUN              DECISIONS.jsonl with the verdicts applied
    adversarial.py status  --adv ADV

**What a verdict does** (`apply`, the one place DECISIONS.jsonl is rewritten):

* `confirm` - the decision stands, with the verdict in its `adversarial` key (the journal's evidence
  carries it: `plan._decision_evidence`);
* `reject` - the decision becomes `unresolved` (`via: "adversarial"`, the researcher's decision kept
  whole in `adversarial.original`): the plan's own semantics follow - a start a rule made becomes
  `Undated`, a value a MiniMax agent wrote is restored from the journal, anything else stays - and the
  cell is listed for the owner (`OWNER.jsonl`);
* `unclear` after the re-ask (round 1, a new agent) - the decision becomes `held`: nothing is written,
  nothing is cleared, the cell is listed. An answer that is not in shape is read as `unclear`.

A rejected or unclear cell is never written, and the check is asked of cells the plan would *write*:
the check has no say over a cell nobody wanted to change.

`apply` pins the new DECISIONS.jsonl (`adv/APPLIED.json`); `plan.py wave` for a wd5 run reads no other
file, and `handoff.py import` refuses to run once the check was selected (it would write the decisions
again from the handoffs and drop the verdicts). The answers are recorded under the role (`opus_handoff.py
answer --role adversarial`): an answer that names another role or the stamp of another model is
refused by name at the import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from acceptance.answers import AnswerError, _quotes, load_object  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from fields import answers as A  # noqa: E402
from fields import carry as CA  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import rule as R  # noqa: E402
from fields import wiki as W  # noqa: E402

#: The handoff stage of the check, the role that gives its answers, and the `via` of a decision
#: this step rewrote.
STAGE = "adv"
ROLE = "adversarial"
ADVERSARIAL = "adversarial"
BATCH_SIZE = 8
#: Round 0 asks every cell; round 1 asks, of a new agent, the cells round 0 left undecided. Then the
#: cell is held.
MAX_ROUND = 1
#: The share of the `keep` decisions that are checked (the map: "10 % of the keeps, seeded").
KEEP_SHARE = 0.10
CELLS_FILE = "CELLS.json"
ROUNDS_FILE = "ROUNDS.jsonl"
VERDICTS_FILE = "VERDICTS.jsonl"
REASK_FILE = "REASK.json"
APPLIED_FILE = HO.ADV_APPLIED.name
PRE_FILE = "DECISIONS.pre-adversarial.jsonl"
OWNER_FILE = "OWNER.jsonl"
PAGES_DIR = "pages"
CONFIRM, REJECT, UNCLEAR = "confirm", "reject", "unclear"
VERDICTS = (CONFIRM, REJECT, UNCLEAR)
#: What the prompt shows of a page: the passage either side of the quote, the head of the page (what
#: the page is about), the lead of the site's own Wikipedia article, the researcher's reasoning.
EXCERPT_CHARS = 700
HEAD_CHARS = 500
LEAD_CHARS = 900
REASONING_SHOWN = 700
#: A reason is a sentence or two; shorter is no reason. A reject or unclear may quote at most this
#: many pages that show what it says (the checker finds each quote in its page).
MIN_REASON_CHARS = 30
MAX_COUNTER_QUOTES = 3
ANSWER_KEYS = frozenset({"fields"})
FIELD_KEYS = frozenset({"decision", "value", "quotes", "reasoning"})
#: A state of a cell: decided (`confirm`, `reject`, `unclear` after the last round), waiting for its
#: answer (`pending`), or waiting for a re-ask (`reask`).
PENDING, REASK = "pending", "reask"


class AdversarialError(ValueError):
    """The re-check cannot take this step. Nothing was written by it."""


def cell_id(site_id: str, field: str) -> str:
    """The question's label: the site and the field of the decision under check."""
    return f"{site_id}.{field}"


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ------------------------------------------------------------------------------ the cells
def excerpt(reading: str, wanted: str) -> str:
    """The passage of a page's reading around a quote, cut `EXCERPT_CHARS` either side."""
    at = reading.index(wanted)
    start, end = max(0, at - EXCERPT_CHARS), min(len(reading), at + len(wanted) + EXCERPT_CHARS)
    return ("... " if start else "") + reading[start:end] + (" ..." if end < len(reading) else "")


def quote_packet(quote: Mapping[str, Any], library: Q.Library) -> dict[str, Any]:
    """One quote of a decision with the page it was found in: the passage around it and the head of
    the page, from the reading the machine found it in. A quote the page does not hold is refused -
    a decision of the run has a found quote, so this is a page that changed under it."""
    source = str(quote["source"])
    read = library.url(source) if Q.is_url(source) else library.file(source)
    if read.failure:
        raise AdversarialError(f"{source}: the page cannot be read ({read.failure}: {read.detail})")
    wanted = Q.normalise(str(quote["quote"]))
    # the narrowest reading that holds the quote: a JSON page offers the whole text as served and,
    # beside it, each of its strings - the string is the passage a reader would see
    holding = [(len(text), reading, text) for reading, text in read.texts if wanted in text]
    if not holding:
        raise AdversarialError(
            f"{source}: the quote {str(quote['quote'])[:60]!r} is not in the page"
        )
    _, reading, text = min(holding, key=lambda found: found[0])
    return {
        "url": source,
        "quote": str(quote["quote"]),
        "outcome": str(quote.get("outcome", Q.FOUND)),
        "reading": reading,
        "head": text[:HEAD_CHARS],
        "passage": excerpt(text, wanted),
    }


def wiki_lead(site_id: str, cache: W.WikiCache) -> dict[str, Any] | None:
    """The lead of the site's own Wikipedia article (the first cached page that exists), or `None`."""
    for page in cache.pages(site_id):
        if not page.get("missing"):
            return {
                "title": page.get("resolved_title") or page["title"],
                "lang": page["lang"],
                "revid": page.get("revid"),
                "url": W.article_url(page),
                "lead": str(page["text"])[:LEAD_CHARS],
            }
    return None


def pages_dir(decision: Mapping[str, Any], run: Path) -> Path:
    """Where the decision's quoted pages are kept: the run's own, or - for a carried decision - the
    run it was made in."""
    if decision["via"] == CA.CARRIED:
        return HO._resolve(Path(decision["origin"]["run"])) / PAGES_DIR
    return run / PAGES_DIR


def packet(
    decision: Mapping[str, Any],
    line: Mapping[str, Any],
    library: Q.Library,
    wiki: W.WikiCache | None,
) -> dict[str, Any]:
    """The frozen question about one decision: everything the prompt shows, as plain JSON."""
    field = str(decision["field"])
    opened = line.get("open", {}).get(field) or {}
    return {
        "cell": cell_id(str(decision["site_id"]), field),
        "site_id": str(decision["site_id"]),
        "field": field,
        "name": str(line["name"]),
        "country": line.get("country"),
        "stored_point": line["fields"]["coordinates"]["stored"],
        "qid": line.get("qid"),
        "enwiki": line.get("enwiki"),
        "stored": decision["stored"],
        "decision": str(decision["decision"]),
        "value": decision["value"],
        "via": str(decision["via"]),
        "round": decision["round"],
        "answered_by": decision["answered_by"],
        "model": decision["model"],
        "why_open": opened.get("why"),
        "made": opened.get("made"),
        "reasoning": str(decision["reasoning"])[:REASONING_SHOWN],
        "value_page": decision.get("value_page"),
        "quotes": [quote_packet(q, library) for q in decision["quotes"]],
        "wiki": None if wiki is None else wiki_lead(str(decision["site_id"]), wiki),
    }


def select(
    run: Path, *, seed: int, wiki: W.WikiCache | None, keep_share: float = KEEP_SHARE
) -> dict[str, Any]:
    """adv/CELLS.json: every `replace` of the run's DECISIONS.jsonl and a seeded `keep_share` of its
    `keep`s, each frozen with the page passages its prompt shows.

    Refused: a run that is not a wd5 run, one with a field still waiting for a re-ask (the check is
    asked of the final decisions), one already selected, a share outside (0, 1], a decision of a site
    the run never classified."""
    if R.read_rule(run) is not R.RECHECK:
        raise AdversarialError(f"{run} is not a wd5 run (its rule is {R.read_rule(run).name!r})")
    if not 0 < keep_share <= 1:
        raise AdversarialError(f"the share of keeps {keep_share!r} is not in (0, 1]")
    adv = run / HO.ADV_DIR
    if (adv / CELLS_FILE).exists():
        raise AdversarialError(f"{adv / CELLS_FILE} exists: the cells are selected once")
    reask = json.loads((run / HO.REASK_FILE).read_text(encoding="utf-8"))
    if reask["fields"]:
        raise AdversarialError(
            f"{sum(len(v) for v in reask['fields'].values())} field(s) still wait for a re-ask: "
            "the re-check is asked of the final decisions"
        )
    decisions = HO._read_jsonl(run / HO.DECISIONS_FILE)
    classified = HO.read_classified(run)
    missing = sorted({d["site_id"] for d in decisions} - set(classified))
    if missing:
        raise AdversarialError(
            f"{len(missing)} decided site(s) are not in CLASSIFIED.jsonl, e.g. {missing[0]}"
        )

    def key(d: Mapping[str, Any]) -> tuple[str, str]:
        return str(d["site_id"]), str(d["field"])

    replaces = sorted((d for d in decisions if d["decision"] == A.REPLACE), key=key)
    keeps = sorted((d for d in decisions if d["decision"] == A.KEEP), key=key)
    # a seeded draw that must repeat, not a secret: the seed is recorded in CELLS.json
    draw = random.Random(seed)  # noqa: S311
    # 0.07 times 100 is 7.000000000000001: 7 % of 100 keeps are 7, not 8
    wanted = math.ceil(round(keep_share * len(keeps), 6))
    sampled = draw.sample(keeps, wanted)
    cells = [
        packet(d, classified[d["site_id"]], Q.Library(REPO, pages_dir(d, run)), wiki)
        for d in sorted([*replaces, *sampled], key=key)
    ]
    record = {
        "seed": seed,
        "keep_share": keep_share,
        "selected_at": H.now(),
        "decisions_sha256": _sha256_text(run / HO.DECISIONS_FILE),
        "classified_sha256": _sha256_text(run / C.CLASSIFIED_FILE),
        "counts": {
            "decisions": len(decisions),
            "replace": len(replaces),
            "keep": len(keeps),
            "keep_checked": len(sampled),
            "cells": len(cells),
            "carried": sum(1 for d in decisions if d["via"] == CA.CARRIED),
        },
        "cells": cells,
    }
    _write_json(adv / CELLS_FILE, record)
    return {"adv": HO._shown(adv), **record["counts"]}


def read_cells(adv: Path) -> dict[str, dict[str, Any]]:
    """`{cell id: frozen question}` of a stage directory."""
    path = adv / CELLS_FILE
    if not path.exists():
        raise AdversarialError(f"{path} is missing - run `select` first")
    return {c["cell"]: c for c in json.loads(path.read_text(encoding="utf-8"))["cells"]}


# ------------------------------------------------------------------------------ the question
CRITERIA = {
    "coordinates": (
        "The quote must give the position of THIS site's own place - its centre or main monument - "
        "not the nearest village, a namesake, a museum that keeps its finds, the island or hill it "
        "stands on, or the region. The value must be what the quote prints, in decimal degrees: "
        "check the conversion from degrees and minutes and the signs (south and west are negative)."
    ),
    "period_start": (
        "The quote must date the START of THIS site - its construction, foundation or first "
        "occupation - not a class of monuments, a later phase, a restoration, a namesake, or the "
        "park, museum or region around it. The value must be what the quote says: check a "
        "century (the 8th century BC is -800, the 2nd century AD is 101), a date before the "
        "present (BP counts from 1950: 12,000 BP is -10050; a site older than 6,450 BP lies in the "
        'band "< 4500 BC", written -4501) and a period word (the value is then the year the fixed '
        'table gives that period: "iron age" -800, "neolithic" -4000). A hedged date ("c.", '
        '"probably") counts when the page gives it for this site.'
    ),
    "site_type": (
        "The quote must describe THIS site as the chosen type - the most specific canonical type "
        "that holds. A quote that only holds the word of the type for something else (a nearby "
        "temple, the museum) does not."
    ),
    "source_url": (
        "The page at the value must be about THIS very site - not the island, town, region or "
        "hill it lies in, not a list, not a namesake - and be the article's own address."
    ),
}

QUESTION = """\
You are the adversarial checker (lane wd5, the re-check) of a curated database of ancient sites. A \
researcher decided ONE field of ONE site from the quote(s) below. Your job is to try to break that \
decision: confirm it only when you cannot. A wrong value in the database is worse than an empty \
field, so doubt is a reason to reject or to say unclear - never a reason to confirm.
"""

HOW_TO_CHECK = """\
## How to check

The passage and the head of the page are what the checker found the quote in. Read them as a sceptic: \
is the page about this very site (its name AND its place), does the quote say what the researcher \
says it says, is the value what the quote says? You may open other pages to test the decision - a few \
requests at most; the site's cached Wikipedia text is `handoff.py wiki-text --label <site id>` \
(the site id is the part of the label before the dot), and a 403 or 429 is a throttle, never a \
finding. Whatever you reject, say what the page says instead or why the quote does not state the \
value for this site, so that a reader can check it.
"""

ANSWER = """\
## Your answer

One JSON object and nothing else: {{"fields": {{"{field}": {{"decision": "...", "value": null, \
"quotes": [{{"url": "https://...", "quote": "verbatim text"}}], "reasoning": "..."}}}}}}

- decision "confirm": the quote, read in its page, states the value for this very site, and nothing \
in the page or in the sources you opened contradicts it. quotes is [].
- decision "reject": it does not - the page is about another place or a class of monuments, the quote \
says something else, the value was converted wrongly, or a better source contradicts it. quotes may \
hold up to {limit} quotes of the pages that show it; each must be found verbatim in its page.
- decision "unclear": the page and the sources you could reach do not decide it.

value is null. The reasoning is a sentence or two ({minimum} characters at least) that says what \
decides it.
"""


def render_prompt(cell: Mapping[str, Any], note: str | None = None) -> str:
    """The exact question for one frozen cell - a pure function of the cell and of the note a re-ask
    carries (why the last answer could not be used)."""
    field = str(cell["field"])
    out = [QUESTION, "## The site", ""]
    out += [
        f"- name: {cell['name']}",
        f"- country: {cell['country']}",
        "- Wikidata item: "
        + (f"https://www.wikidata.org/wiki/{cell['qid']}" if cell["qid"] else "none"),
        f"- English Wikipedia article of the item: {cell['enwiki'] or 'none'}",
    ]
    if cell["stored_point"] is not None:
        out.append(f"- stored point: {cell['stored_point']} (latitude, longitude)")
    wiki = cell["wiki"]
    if wiki is not None:
        out += [
            f"- the lead of the site's own Wikipedia article ({wiki['url']}, revision "
            f"{wiki['revid']}): {json.dumps(wiki['lead'], ensure_ascii=False)}"
        ]
    out += ["", "## The decision under check", "", f"- field: {field}"]
    out.append(f"- stored value: {json.dumps(cell['stored'], ensure_ascii=False)}")
    out.append(f"- the researcher decided: {cell['decision']}")
    out.append(f"- value: {json.dumps(cell['value'], ensure_ascii=False)}")
    if field == "period_start" and cell["value"] is not None:
        out.append(f"- the map shows only the bucket of the value: {C.bucket(int(cell['value']))}")
    if cell["why_open"]:
        out.append(f"- the field was asked because: {HO.OPEN_TEXT[cell['why_open']]}")
    out.append(f"- the researcher's reasoning: {json.dumps(cell['reasoning'], ensure_ascii=False)}")
    for number, quote in enumerate(cell["quotes"], start=1):
        out += [
            "",
            f"### Quote {number} - {quote['url']}",
            "",
            f"The quote (the checker found it in the page's {quote['reading']}):",
            f"> {quote['quote']}",
            "",
            "The page around it, whitespace-normalised:",
            f"> {quote['passage']}",
            "",
            f"The page begins: > {quote['head']}",
        ]
    if cell["value_page"]:
        out += ["", f"The page the value names was served: {json.dumps(cell['value_page'])}"]
    out += ["", "## What to check", "", CRITERIA[field], ""]
    if cell["decision"] == A.KEEP:
        out += [
            "This is a keep: the stored value stands on the quote(s). Check the same things "
            "against the stored value.",
            "",
        ]
    if note:
        out += [
            f"An earlier answer to this check could not be used: {note}. Decide confirm or "
            "reject when you can; unclear only when the page and the sources you could reach "
            "really do not decide it.",
            "",
        ]
    out += [
        HOW_TO_CHECK,
        ANSWER.format(field=field, limit=MAX_COUNTER_QUOTES, minimum=MIN_REASON_CHARS),
    ]
    return "\n".join(out)


# ------------------------------------------------------------------------------ the answer
def parse_answer(text: str, field: str) -> tuple[str, str, tuple[Any, ...]]:
    """`(decision, reasoning, quotes)` of an answer to the check of `field`; `AnswerError` when it is
    not in shape."""
    data = load_object(text, ANSWER_KEYS)
    fields = data["fields"]
    if not isinstance(fields, dict) or set(fields) != {field}:
        raise AnswerError(f"fields {sorted(fields)!r} are not the asked field {field!r}")
    row = fields[field]
    if not isinstance(row, dict) or set(row) != FIELD_KEYS:
        raise AnswerError(f"the answer carries {sorted(row)!r}, not {sorted(FIELD_KEYS)}")
    decision = row["decision"]
    if decision not in VERDICTS:
        raise AnswerError(f"decision {decision!r} is not one of {list(VERDICTS)}")
    if row["value"] is not None:
        raise AnswerError("the value of a check is null")
    reasoning = row["reasoning"]
    if not isinstance(reasoning, str) or len(reasoning.strip()) < MIN_REASON_CHARS:
        raise AnswerError(f"the reasoning is shorter than {MIN_REASON_CHARS} characters")
    quotes = _quotes(row["quotes"], A.QUOTE_KEYS)
    if decision == CONFIRM and quotes:
        raise AnswerError("a confirm carries no quote: the quote under check is the researcher's")
    if len(quotes) > MAX_COUNTER_QUOTES:
        raise AnswerError(f"at most {MAX_COUNTER_QUOTES} quotes, not {len(quotes)}")
    return str(decision), reasoning.strip(), quotes


# ------------------------------------------------------------------------------ the rounds
def read_rounds(adv: Path) -> list[dict[str, Any]]:
    return HO._read_jsonl(adv / ROUNDS_FILE)


def _round_of(adv: Path, handoff: Path) -> dict[str, Any]:
    wanted = HO._resolve(handoff).resolve()
    for record in read_rounds(adv):
        if HO._resolve(Path(record["handoff"])).resolve() == wanted:
            return record
    raise AdversarialError(f"{handoff} is not the directory of an exported round of {adv}")


def batches(cells: Sequence[Mapping[str, Any]], round_no: int) -> list[tuple[str, list[str]]]:
    """Cells by country, then name, cut into batches of `BATCH_SIZE`."""
    ordered = sorted(cells, key=lambda c: (c["country"] or "", c["name"].casefold(), c["cell"]))
    return [
        (f"{STAGE}-r{round_no}-b{number + 1:04d}", [c["cell"] for c in ordered[i : i + BATCH_SIZE]])
        for number, i in enumerate(range(0, len(ordered), BATCH_SIZE))
    ]


def _export_round(
    adv: Path, handoff: Path, round_no: int, asked: Sequence[str], notes: Mapping[str, str]
) -> dict[str, Any]:
    rounds = read_rounds(adv)
    target = HO._resolve(handoff)
    if target.exists() and any(target.iterdir()):
        raise AdversarialError(f"{handoff} is not empty: a round gets a directory of its own")
    cells = read_cells(adv)
    groups = batches([cells[c] for c in asked], round_no)
    for batch_id, labels in groups:
        for label in labels:
            OH.export(
                target,
                batch_id=batch_id,
                stage=STAGE,
                label=label,
                field=cells[label]["field"],
                prompt=render_prompt(cells[label], notes.get(label)),
            )
    record = {
        "round": round_no,
        "handoff": HO._shown(handoff),
        "model": RO.role(ROLE).model,
        "batches": dict(groups),
        "fields": {label: [cells[label]["field"]] for label in sorted(asked)},
        "notes": {label: notes[label] for label in sorted(notes)},
        "exported_at": H.now(),
    }
    HO._write_jsonl(adv / ROUNDS_FILE, [*rounds, record])
    return {
        "round": round_no,
        "handoff": record["handoff"],
        "cells": len(asked),
        "batches": len(groups),
    }


def export(adv: Path, handoff: Path) -> dict[str, Any]:
    """Round 0: one check question per selected cell."""
    if read_rounds(adv):
        raise AdversarialError("round 0 is exported already - re-asks go through export-reask")
    return _export_round(adv, handoff, 0, sorted(read_cells(adv)), {})


def export_reask(adv: Path, handoff: Path) -> dict[str, Any]:
    """Round 1: the cells the last import left undecided, to a new agent, each with why."""
    rounds = read_rounds(adv)
    if not rounds:
        raise AdversarialError("nothing was exported")
    last = max(r["round"] for r in rounds)
    path = adv / REASK_FILE
    if not path.exists() or json.loads(path.read_text(encoding="utf-8"))["after_round"] != last:
        raise AdversarialError(f"import round {last} before a re-ask")
    reask = json.loads(path.read_text(encoding="utf-8"))["cells"]
    if not reask:
        raise AdversarialError("nothing to ask again")
    return _export_round(adv, handoff, last + 1, sorted(reask), reask)


# ------------------------------------------------------------------------------ the agent's aids
def check_answer(adv: Path, handoff: Path, batch_id: str, label: str, text: str) -> dict[str, Any]:
    """The shape problems of one answer - nothing is fetched."""
    record = _round_of(adv, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise AdversarialError(f"{batch_id}/{label} is no question of {handoff}")
    try:
        parse_answer(text, record["fields"][label][0])
    except AnswerError as exc:
        return {"ok": False, "problems": {"answer": str(exc)}}
    return {"ok": True, "problems": {}}


BRIEF = """You are adversarial checker {batch} of the WD5 re-check of a curated database of ancient \
sites. You answer {count} check question(s), each about another decision. Answer each one on its own, \
as if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the repository - \
no other batch, nothing else under output/ or docs/, no database, no git history. To test a decision \
you may use the web (a few requests; 403 and 429 are a throttle, never a finding) and the cached \
Wikipedia text of the site:
   ./.venv/Scripts/python.exe scripts/remediation/fields/handoff.py wiki-text --label <site id>
where the site id is the part of the question's label before the dot.

For each question:
1. Read {handoff}/<prompt_path>.
2. Try to break the decision, as the prompt asks, and decide confirm, reject or unclear.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it (nothing is fetched; a counter-quote is checked against its page at import):
   ./.venv/Scripts/python.exe scripts/remediation/fields/adversarial.py check-answer --adv {adv} \
--handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} \
--model {model} --role {role} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(adv: Path, handoff: Path, batch_id: str) -> str:
    record = _round_of(adv, handoff)
    if batch_id not in record["batches"]:
        raise AdversarialError(f"{batch_id} is no batch of {handoff}")
    shown = HO._shown(handoff)
    return BRIEF.format(
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        adv=HO._shown(adv),
        stage=STAGE,
        model=record["model"],
        role=ROLE,
    )


# ------------------------------------------------------------------------------ the import
def role_problem(answer: OH.Answer) -> str | None:
    """Why an answer is not the adversarial role's, or `None`."""
    if RO.role_of(answer.answered_by) != ROLE:
        return (
            f"answered_by {answer.answered_by!r} names no {ROLE} role: the answer was recorded "
            f"without `--role {ROLE}`, so nothing says the registry's model wrote it - delete it "
            "and answer again"
        )
    return RO.answer_problem(answer.answered_by, answer.model)


def _attempts(adv: Path, cells: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every answer of every round, validated and parsed - the counter-quotes not yet checked."""
    rounds = sorted(read_rounds(adv), key=lambda r: r["round"])
    if not rounds:
        raise AdversarialError("nothing was exported")
    attempts: list[dict[str, Any]] = []
    for record in rounds:
        handoff = HO._resolve(Path(record["handoff"]))
        check = OH.validate(handoff)
        if not check.ok:
            raise AdversarialError(
                f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
                f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
                "answer is validated before anything is imported"
            )
        manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
        asked = {(b, label) for b, labels in record["batches"].items() for label in labels}
        if set(manifest) != asked:
            raise AdversarialError(f"{record['handoff']}: the manifest is not the round's record")
        for (batch_id, label), line in sorted(manifest.items()):
            prompt = render_prompt(cells[label], record["notes"].get(label))
            if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
                raise AdversarialError(
                    f"{batch_id}/{label}: the exported prompt is not this question's"
                )
            answer = OH.read_answer(
                handoff, batch_id=batch_id, stage=STAGE, label=label, prompt=prompt
            )
            problem = role_problem(answer)
            if problem is not None:
                raise AdversarialError(f"{batch_id}/{label}: {problem}")
            attempt = {
                "cell": label,
                "site_id": cells[label]["site_id"],
                "field": cells[label]["field"],
                "round": record["round"],
                "batch_id": batch_id,
                "answered_by": answer.answered_by,
                "model": answer.model,
                "answered_at": answer.answered_at,
                "verdict": None,
                "reasoning": None,
                "quotes": [],
                "problem": None,
            }
            try:
                verdict, reasoning, quotes = parse_answer(answer.text, cells[label]["field"])
            except AnswerError as exc:
                attempt["problem"] = f"malformed answer: {exc}"
            else:
                attempt.update(
                    verdict=verdict,
                    reasoning=reasoning,
                    quotes=[{"source": q.url, "quote": q.quote} for q in quotes],
                )
            attempts.append(attempt)
    return attempts


def state_of(attempts: Sequence[Mapping[str, Any]]) -> tuple[str, Mapping[str, Any] | None]:
    """A cell's state and the attempt that decides it: `confirm` and `reject` are decided by the
    latest answer; an undecided latest answer (`unclear`, or not in shape) is decided as `unclear`
    after the last round and waits for its re-ask before; no answer is `pending`."""
    if not attempts:
        return PENDING, None
    last = max(attempts, key=lambda a: a["round"])
    if last["verdict"] in (CONFIRM, REJECT):
        return str(last["verdict"]), last
    return (UNCLEAR if last["round"] >= MAX_ROUND else REASK), last


def import_answers(
    adv: Path, *, client: httpx.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """Every round's answers: validated, role-checked, parsed; the counter-quotes of a reject or an
    unclear found in their pages. Writes VERDICTS.jsonl (every answer) and REASK.json (the cells a
    new agent is to decide). A counter-quote that is not in its page does not change the verdict -
    a reject that cannot be shown is still no write - and is reported (`quote_problems`)."""
    cells = read_cells(adv)
    attempts = _attempts(adv, cells)
    pages = adv / PAGES_DIR
    urls = sorted({q["source"] for a in attempts for q in a["quotes"]})
    forgotten = HO.forget_transient(urls, pages)
    if urls:
        if client is None:
            with H.open_client() as own:
                Q.collect(urls, pages, own, now=H.now, pace=pace)
        else:
            Q.collect(urls, pages, client, now=H.now, pace=pace)
    library = Q.Library(REPO, pages)
    for attempt in attempts:
        attempt["quotes"] = [
            {
                "source": q["source"],
                "quote": q["quote"],
                "outcome": Q.check_quote(
                    q, {"change_key": attempt["cell"], "evidence_files": []}, library
                ).outcome,
            }
            for q in attempt["quotes"]
        ]
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        by_cell.setdefault(attempt["cell"], []).append(attempt)
    last = max(a["round"] for a in attempts)
    states = {cell: state_of(by_cell.get(cell, ())) for cell in cells}
    reask = {
        cell: str(attempt["problem"] or f"the answer was unclear: {attempt['reasoning']}")
        for cell, (state, attempt) in states.items()
        if state == REASK and attempt is not None
    }
    HO._write_jsonl(adv / VERDICTS_FILE, attempts)
    _write_json(adv / REASK_FILE, {"after_round": last, "cells": reask})
    if urls:
        HO._write_jsonl(adv / "PAGES.jsonl", Q.page_index(urls, pages))
    bad_quotes = [
        f"{a['cell']}: {q['source']} ({q['outcome']})"
        for a in attempts
        for q in a["quotes"]
        if q["outcome"] != Q.FOUND
    ]
    return {
        "rounds": last + 1,
        "attempts": len(attempts),
        "cells": len(cells),
        "states": dict(sorted(Counter(state for state, _ in states.values()).items())),
        "by_field": dict(
            sorted(Counter(f"{cells[c]['field']}:{s}" for c, (s, _) in states.items()).items())
        ),
        "waiting_for_reask": len(reask),
        "refetched": forgotten,
        "quote_problems": bad_quotes,
    }


def status(adv: Path) -> dict[str, Any]:
    """The cells' states from the last import's VERDICTS.jsonl (or `pending` before any)."""
    cells = read_cells(adv)
    path = adv / VERDICTS_FILE
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for attempt in HO._read_jsonl(path) if path.exists() else []:
        by_cell.setdefault(attempt["cell"], []).append(attempt)
    states = Counter(state_of(by_cell.get(cell, ()))[0] for cell in cells)
    return {
        "cells": len(cells),
        "rounds": [
            {"round": r["round"], "handoff": r["handoff"], "cells": len(r["fields"])}
            for r in read_rounds(adv)
        ],
        "states": dict(sorted(states.items())),
        "applied": (adv / APPLIED_FILE).exists(),
    }


# ------------------------------------------------------------------------------ apply
def _adversarial_note(state: str, attempt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "verdict": state,
        "round": attempt["round"],
        "answered_by": attempt["answered_by"],
        "model": attempt["model"],
        "reason": attempt["reasoning"] or attempt["problem"],
    }


def _rewritten(
    decision: Mapping[str, Any], state: str, attempt: Mapping[str, Any]
) -> dict[str, Any]:
    """The decision after its verdict: itself with the verdict noted (confirm), `unresolved` (reject)
    or `held` (unclear). The researcher's decision is kept whole in `adversarial.original`."""
    note = _adversarial_note(state, attempt)
    if state == CONFIRM:
        return {**decision, "adversarial": note}
    outcome = A.UNRESOLVED if state == REJECT else HO.HELD
    said = "reject" if state == REJECT else "unclear"
    return {
        **{k: decision[k] for k in ("site_id", "name", "field", "status", "stored", "asked")},
        "decision": outcome,
        "value": None,
        "via": ADVERSARIAL,
        "round": decision["round"],
        "counted_rounds": [],
        "answered_by": attempt["answered_by"],
        "model": attempt["model"],
        "quotes": [],
        "reasoning": (
            f"adversarial {said} (round {attempt['round']}, {attempt['answered_by']}): "
            f"{note['reason']} | the researcher decided {decision['decision']} "
            f"{decision['value']!r} ({decision['answered_by']}): "
            f"{str(decision['reasoning'])[:300]}"
        ),
        "value_page": None,
        "adversarial": {**note, "original": dict(decision)},
    }


def apply(run: Path) -> dict[str, Any]:
    """DECISIONS.jsonl with every verdict applied, once: the file before is kept as
    adv/DECISIONS.pre-adversarial.jsonl, adv/OWNER.jsonl lists the rejected and the held cells, and
    adv/APPLIED.json pins the new file for `plan.py wave`.

    Refused: a run without selected cells; one already applied; a half-applied one (the kept copy
    exists and the pin does not: restore DECISIONS.jsonl from the copy, delete the copy, apply
    again); DECISIONS.jsonl changed since the selection; a cell without a verdict; a cell waiting for
    its re-ask."""
    adv = run / HO.ADV_DIR
    cells = read_cells(adv)
    if (adv / APPLIED_FILE).exists():
        raise AdversarialError(f"{adv / APPLIED_FILE} exists: the re-check is applied once")
    if (adv / PRE_FILE).exists():
        raise AdversarialError(
            f"{adv / PRE_FILE} exists without {APPLIED_FILE}: a half-applied re-check - restore "
            "DECISIONS.jsonl from that copy, delete it and apply again"
        )
    selection = json.loads((adv / CELLS_FILE).read_text(encoding="utf-8"))
    if _sha256_text(run / HO.DECISIONS_FILE) != selection["decisions_sha256"]:
        raise AdversarialError(
            "DECISIONS.jsonl is not the file the cells were selected from: delete adv/ and select again"
        )
    path = adv / VERDICTS_FILE
    if not path.exists():
        raise AdversarialError(f"{path} is missing - import the answers first")
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for attempt in HO._read_jsonl(path):
        by_cell.setdefault(attempt["cell"], []).append(attempt)
    states = {cell: state_of(by_cell.get(cell, ())) for cell in cells}
    waiting = sorted(c for c, (s, _) in states.items() if s in (PENDING, REASK))
    if waiting:
        raise AdversarialError(
            f"{len(waiting)} cell(s) have no final verdict, e.g. {waiting[0]} "
            f"({states[waiting[0]][0]}): answer and import the round first"
        )
    decisions = HO._read_jsonl(run / HO.DECISIONS_FILE)
    out: list[dict[str, Any]] = []
    owner: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for decision in decisions:
        cell = cell_id(decision["site_id"], decision["field"])
        if cell not in cells:
            out.append(decision)
            continue
        state, attempt = states[cell]
        assert attempt is not None  # a cell without an attempt is `pending`, refused above
        counts[f"{decision['field']}:{state}"] += 1
        counts[state] += 1
        rewritten = _rewritten(decision, state, attempt)
        out.append(rewritten)
        if state != CONFIRM:
            owner.append(
                {
                    "site_id": decision["site_id"],
                    "name": decision["name"],
                    "field": decision["field"],
                    "state": state,
                    "stored": decision["stored"],
                    "researcher": {
                        k: decision[k] for k in ("decision", "value", "via", "answered_by", "model")
                    },
                    "researcher_quotes": decision["quotes"],
                    "reason": rewritten["adversarial"]["reason"],
                    "counter_quotes": attempt["quotes"],
                }
            )
    pre = adv / PRE_FILE
    pre.write_bytes((run / HO.DECISIONS_FILE).read_bytes())
    HO._write_jsonl(run / HO.DECISIONS_FILE, out)
    HO._write_jsonl(adv / OWNER_FILE, owner)
    record = {
        "applied_at": H.now(),
        "pre_sha256": selection["decisions_sha256"],
        "decisions_sha256": _sha256_text(run / HO.DECISIONS_FILE),
        "cells_sha256": _sha256_text(adv / CELLS_FILE),
        "counts": dict(sorted(counts.items())),
    }
    _write_json(adv / APPLIED_FILE, record)
    return {"decisions": len(out), "listed_for_the_owner": len(owner), **record["counts"]}


# ------------------------------------------------------------------------------------------ the CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        name: sub.add_parser(name)
        for name in (
            "select", "export", "export-reask", "brief", "check-answer", "import", "apply", "status",
        )
    }  # fmt: skip
    for name in ("select", "apply"):
        commands[name].add_argument("--run", type=Path, required=True, help="the wd5 run")
    for name in ("export", "export-reask", "brief", "check-answer", "import", "status"):
        commands[name].add_argument("--adv", type=Path, required=True, help="the stage directory")
    for name in ("export", "export-reask", "brief", "check-answer"):
        commands[name].add_argument("--handoff", type=Path, required=True)
    for name in ("brief", "check-answer"):
        commands[name].add_argument("--batch-id", required=True)
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", type=Path, required=True)
    commands["select"].add_argument("--seed", type=int, required=True)
    commands["select"].add_argument("--keep-share", type=float, default=KEEP_SHARE)
    commands["select"].add_argument("--wiki-cache", type=Path, default=W.WIKI_CACHE)
    commands["import"].add_argument("--pace", type=float, default=Q.PACE_SECONDS)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "select":
            result: Any = select(
                HO._resolve(args.run),
                seed=args.seed,
                wiki=W.WikiCache(args.wiki_cache),
                keep_share=args.keep_share,
            )
        elif args.command == "apply":
            result = apply(HO._resolve(args.run))
        else:
            adv = HO._resolve(args.adv)
            if args.command == "export":
                result = export(adv, args.handoff)
            elif args.command == "export-reask":
                result = export_reask(adv, args.handoff)
            elif args.command == "brief":
                print(brief(adv, args.handoff, args.batch_id))
                return 0
            elif args.command == "check-answer":
                text = HO._resolve(args.text_file).read_bytes().decode("utf-8")
                result = check_answer(adv, args.handoff, args.batch_id, args.label, text)
                print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
                return 0 if result["ok"] else 1
            elif args.command == "import":
                result = import_answers(adv, pace=args.pace)
            else:
                result = status(adv)
    except (AdversarialError, HO.HandoffStepError, OH.HandoffError, Q.AuditError, W.WikiCacheError,
            R.RuleError) as exc:  # fmt: skip
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
