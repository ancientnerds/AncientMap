"""L5's Opus handoff: rounds of questions, the agents' brief, the shape check and the import.

Every model judgement goes through `opus_handoff.py` (owner, 2026-09-23): this module exports the
questions, Opus agents of the orchestrating session answer them, `opus_handoff.py validate` checks
every answer's shape and prompt, and `import_round` reads them back - fetching every cited page
(`opus_audit/quotes.py`), resolving every article kept or written (`web.resolve_titles`) and
deciding each site (`decide.py`).

**A round** is one export into its own handoff directory (an exported question is never replaced):
round `r1` asks every site of the population that is asked; a re-ask round `r<n>` asks the sites
whose latest answer was held, each prompt carrying why (`questions.prompt(earlier=...)`), so the
import can rebuild each prompt exactly and refuse an answer to any other. Batches of `PER_BATCH`
sites, one Opus agent each (O11: up to 16 agents at a time). The rounds are recorded in
`ROUNDS.jsonl`; a round is imported once `answers/<round>.jsonl` exists. Only the newest round is
imported (an older one would overwrite the newer decisions), a re-ask and the plan wait until it is,
and there are at most `MAX_ROUNDS` rounds: round 1 and two re-asks.

**The import** of a round writes `answers/<round>.jsonl` (every answer as decided: the verdicts,
their quotes, each quote's outcome, the machine notes, or why it was held), merges `DECISIONS.jsonl`
(per site, the decision of its latest imported round), `TITLES.json` (each title's resolution,
kept once resolved) and `PAGES.jsonl` (the fetch record and the sha256 of the bytes of each page
read: every cited URL, and the entity page of each item a rename is checked against; the bytes
stay under `pages/`, not versioned).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import opus_handoff as OH  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from l5 import decide as D  # noqa: E402
from l5 import population as POP  # noqa: E402
from l5 import questions as QN  # noqa: E402
from l5 import web  # noqa: E402

ROUNDS_FILE = "ROUNDS.jsonl"
DECISIONS_FILE = "DECISIONS.jsonl"
TITLES_FILE = "TITLES.json"
PAGES_FILE = "PAGES.jsonl"
PAGES_DIR = "pages"
ANSWERS_DIR = "answers"
PER_BATCH = 10
#: Round 1 and at most two re-asks (the runbook); what is held after them stays held.
MAX_ROUNDS = 3


class HandoffError(ValueError):
    """A round that cannot be exported or imported as asked. Nothing was written."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _shown(path: Path) -> str:
    """A path relative to the repository where it lies inside it, as the brief prints it."""
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO / candidate


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records),
        encoding="utf-8",
        newline="\n",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ------------------------------------------------------------------------------------ the rounds
@dataclass(frozen=True)
class Round:
    name: str
    handoff: str
    exported_at: str
    read_at: str
    batches: dict[str, list[str]]
    #: site id -> why its answer of the round before was held (re-ask rounds only)
    earlier: dict[str, str]

    @property
    def sites(self) -> list[str]:
        return [sid for batch in self.batches.values() for sid in batch]


def load_rounds(out: Path) -> list[Round]:
    return [Round(**r) for r in _read_jsonl(out / ROUNDS_FILE)]


def find_round(out: Path, name: str) -> Round:
    for r in load_rounds(out):
        if r.name == name:
            return r
    raise HandoffError(f"no round {name!r} in {out / ROUNDS_FILE}")


def imported(out: Path, name: str) -> bool:
    return (out / ANSWERS_DIR / f"{name}.jsonl").exists()


def latest_imported(out: Path, doing: str) -> list[Round]:
    """The rounds, only if the newest one is imported: `doing` would otherwise read decisions
    older than the answers already exported, and those answers could never be written."""
    rounds = load_rounds(out)
    if not rounds:
        raise HandoffError(f"no round is exported yet - {doing} reads the imported answers")
    if not imported(out, rounds[-1].name):
        raise HandoffError(
            f"round {rounds[-1].name} is exported but not imported - import it before {doing}"
        )
    return rounds


def reask_sites(out: Path) -> dict[str, str]:
    """The held sites a new round asks, with their reasons - once the newest round is imported,
    and only while fewer than `MAX_ROUNDS` rounds are out."""
    rounds = latest_imported(out, "a re-ask")
    if len(rounds) >= MAX_ROUNDS:
        raise HandoffError(
            f"{len(rounds)} rounds are out: a held site is asked at most twice more - what stays "
            "held is listed in UNTRUSTED_LINKS.jsonl by the plan"
        )
    return held_sites(out)


def batches(site_ids: Sequence[str], round_name: str, per_batch: int) -> dict[str, list[str]]:
    """`<round>-bNN -> site ids`, in site order, at most `per_batch` each."""
    if per_batch < 1:
        raise HandoffError("a batch holds at least one question")
    ordered = sorted(site_ids)
    return {
        f"{round_name}-b{i // per_batch + 1:02d}": ordered[i : i + per_batch]
        for i in range(0, len(ordered), per_batch)
    }


def _question(
    read: Mapping[str, Any], members: Mapping[str, Mapping[str, Any]], sid: str, earlier: str | None
) -> str:
    return QN.prompt(read["sites"][sid], members[sid], read, earlier)


def export_round(
    out: Path,
    handoff: Path,
    site_ids: Sequence[str],
    *,
    earlier: Mapping[str, str] | None = None,
    per_batch: int = PER_BATCH,
    now: Callable[[], str] = now_utc,
) -> Round:
    """Export one round of questions into a new handoff directory and record it."""
    earlier = dict(earlier or {})
    if not site_ids:
        raise HandoffError("no site to ask - nothing to export")
    if handoff.exists() and any(handoff.iterdir()):
        raise HandoffError(f"{handoff} is not empty: a round is exported into a new directory")
    read = POP.load_read(out)
    members = {str(r["site_id"]): r for r in POP.load_population(out)}
    not_asked = [s for s in site_ids if s not in members or members[s]["excluded"] is not None]
    if not_asked:
        raise HandoffError(f"{len(not_asked)} site(s) are not asked by L5: {not_asked[:3]}")
    name = f"r{len(load_rounds(out)) + 1}"
    grouped = batches(site_ids, name, per_batch)
    handoff.mkdir(parents=True, exist_ok=True)
    for batch_id, sids in grouped.items():
        for sid in sids:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=QN.STAGE,
                label=sid,
                field=None,
                prompt=_question(read, members, sid, earlier.get(sid)),
            )
    record = Round(name, _shown(handoff), now(), str(read["read_at"]), grouped, earlier)
    with (out / ROUNDS_FILE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return record


def first_round_sites(out: Path) -> list[str]:
    """Round 1 asks every member of the population that is not excluded."""
    return [str(r["site_id"]) for r in POP.load_population(out) if r["excluded"] is None]


def held_sites(out: Path) -> dict[str, str]:
    """The sites whose latest decision is held, with the reason a re-ask shows."""
    return {d["site_id"]: d["reason"] for d in load_decisions(out) if d["status"] == D.HELD}


# ------------------------------------------------------------------------------ the agent's aids
BRIEF = """You are Opus reader {batch} of lane L5 of the Ancient Nerds sites remediation (round \
{round}). You answer {count} question(s), each about another curated site: is its Wikidata item and \
its English Wikipedia article exactly this site{names}? Answer each one on its own.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no other file of \
the repository, no database, no git history. Your evidence is your own web research, as each prompt \
says. The machine fetches every URL you cite with a plain HTTP GET and looks for your quote in what \
it serves (for an HTML page: its visible text; for Special:EntityData/<QID>.json: the JSON's \
strings) - quote verbatim, and cite the page you quote, never a search result page. Keep each quote short (one clause, about 5 to 25 words) and never let it run across a footnote marker such as [1], a table cell or a list item: the served text carries those markers where you may not see them.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide, exactly as the prompt's rules say.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched and your verdict is not judged):
   {python} {run} check-answer --round {round} --batch-id {batch} --label <label> \
--text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   {python} {handoff_tool} answer --dir {handoff} --batch-id {batch} --stage {stage} \
--label <label> --answered-by {batch} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(out: Path, round_name: str, batch_id: str) -> str:
    """The instruction of the Opus agent that answers one batch of one round."""
    record = find_round(out, round_name)
    if batch_id not in record.batches:
        raise HandoffError(f"{batch_id} is no batch of round {round_name}")
    members = {str(r["site_id"]): r for r in POP.load_population(out)}
    asks_names = any(members[s]["ask_name"] for s in record.batches[batch_id])
    return BRIEF.format(
        batch=batch_id,
        round=round_name,
        count=len(record.batches[batch_id]),
        names=", and for some of them its name" if asks_names else "",
        handoff=record.handoff,
        scratch=f"{record.handoff}-scratch/{batch_id}",
        stage=QN.STAGE,
        python="./.venv/Scripts/python.exe",
        run="scripts/remediation/l5/run.py",
        handoff_tool="scripts/remediation/opus_handoff.py",
    )


def check_answer(out: Path, round_name: str, batch_id: str, label: str, text: str) -> str | None:
    """The shape problem of an answer text, or None - no page is fetched, no verdict judged."""
    record = find_round(out, round_name)
    if label not in record.batches.get(batch_id, []):
        raise HandoffError(f"{batch_id}/{label} is no question of round {round_name}")
    read = POP.load_read(out)
    members = {str(r["site_id"]): r for r in POP.load_population(out)}
    try:
        QN.parse(text, read["sites"][label], members[label])
    except QN.AnswerError as exc:
        return str(exc)
    return None


# ------------------------------------------------------------------------------------ the import
def load_decisions(out: Path) -> list[dict[str, Any]]:
    return _read_jsonl(out / DECISIONS_FILE)


def load_titles(out: Path) -> dict[str, dict[str, Any]]:
    path = out / TITLES_FILE
    if not path.exists():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8"))["titles"])


def _final_titles(site: Mapping[str, Any], answer: QN.Answer) -> set[str]:
    title = D.final_links(site, answer)["enwiki_title"]
    return {title} if title else set()


def _pages(site: Mapping[str, Any], answer: QN.Answer) -> set[str]:
    """Every page the checks read: each cited URL, and the entity page of the item a rename is
    checked against (`decide._rename`), cited or not."""
    cells = [answer.qid, answer.title, answer.source_url]
    if answer.name is not None:
        cells.append(answer.name)
    urls = {q["source"] for cell in cells for q in cell.quotes}
    item = D.final_links(site, answer)["wikidata_qid"]
    if D.renames(answer) and item is not None:
        urls.add(QN.ENTITY_DATA.format(item))
    return urls


def _shape_held(
    site: Mapping[str, Any], round_name: str, answered_by: str, reason: str
) -> D.Decision:
    return D.Decision(
        site_id=str(site["site_id"]),
        name=str(site["name"]),
        status=D.HELD,
        reason=f"shape: {reason}",
        round=round_name,
        answered_by=answered_by,
        cells={},
    )


def import_round(
    out: Path,
    round_name: str,
    *,
    http: Callable[[], httpx.Client] = web.client,
    resolver: Callable[[list[str], httpx.Client], dict[str, dict[str, Any]]] = web.resolve_titles,
    now: Callable[[], str] = now_utc,
    pace: float = Q.PACE_SECONDS,
) -> dict[str, Any]:
    """Parse, fetch, resolve and decide every answer of one round; merge the decisions."""
    record = find_round(out, round_name)
    newest = load_rounds(out)[-1].name
    if record.name != newest:
        raise HandoffError(
            f"round {round_name} is not the newest ({newest}): its answers would overwrite the "
            "newer round's decisions"
        )
    root = resolve_path(record.handoff)
    check = OH.validate(root)
    if not check.ok:
        raise HandoffError(
            f"{root} does not validate ({len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan(s)) - run "
            "`opus_handoff.py validate` and have the questions answered first"
        )
    read = POP.load_read(out)
    members = {str(r["site_id"]): r for r in POP.load_population(out)}
    parsed: dict[str, tuple[QN.Answer, OH.Answer]] = {}
    held: dict[str, D.Decision] = {}
    for batch_id, sids in record.batches.items():
        for sid in sids:
            site, member = read["sites"][sid], members[sid]
            answer = OH.read_answer(
                root,
                batch_id=batch_id,
                stage=QN.STAGE,
                label=sid,
                prompt=_question(read, members, sid, record.earlier.get(sid)),
            )
            try:
                parsed[sid] = (QN.parse(answer.text, site, member), answer)
            except QN.AnswerError as exc:
                held[sid] = _shape_held(site, round_name, answer.answered_by, str(exc))

    pages = out / PAGES_DIR
    urls = sorted({u for sid, (a, _) in parsed.items() for u in _pages(read["sites"][sid], a)})
    titles = load_titles(out)
    wanted = sorted(
        {t for sid, (a, _) in parsed.items() for t in _final_titles(read["sites"][sid], a)}
        - set(titles)
    )
    with http() as client:
        fetched = Q.collect(urls, pages, client, now=now, pace=pace)
        resolved_at = now()
        if wanted:
            titles.update(
                {t: {**r, "resolved_at": resolved_at} for t, r in resolver(wanted, client).items()}
            )
    missing = [t for t in wanted if t not in titles]
    if missing:
        raise HandoffError(f"{len(missing)} title(s) came back unresolved: {missing[:3]}")

    library = Q.Library(REPO, pages)
    decisions: dict[str, D.Decision] = dict(held)
    for sid, (answer, raw) in parsed.items():
        decisions[sid] = D.decide(
            read["sites"][sid],
            members[sid],
            answer,
            round_name=round_name,
            answered_by=f"{raw.answered_by} ({raw.answered_at})",
            library=library,
            titles=titles,
            sharers=read["sharers"],
        )
    records = [json.loads(decisions[sid].to_json()) for sid in sorted(decisions)]
    write_jsonl(out / ANSWERS_DIR / f"{round_name}.jsonl", records)
    merged = {d["site_id"]: d for d in load_decisions(out)}
    merged.update({r["site_id"]: r for r in records})
    write_jsonl(out / DECISIONS_FILE, [merged[s] for s in sorted(merged)])
    (out / TITLES_FILE).write_text(
        json.dumps({"titles": titles}, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    known = {r["url"]: r for r in _read_jsonl(out / PAGES_FILE)}
    known.update({r["url"]: r for r in Q.page_index(urls, pages)})
    write_jsonl(out / PAGES_FILE, [known[u] for u in sorted(known)])
    statuses = Counter(r["status"] for r in records)
    return {
        "round": round_name,
        "answers": len(records),
        "decided": statuses.get(D.DECIDED, 0),
        "held": statuses.get(D.HELD, 0),
        "held_reasons": dict(
            Counter(r["reason"].split(":")[0] for r in records if r["status"] == D.HELD)
        ),
        "pages": fetched,
        "titles_resolved": len(wanted),
        "sites_decided_overall": sum(1 for d in merged.values() if d["status"] == D.DECIDED),
        "sites_held_overall": sum(1 for d in merged.values() if d["status"] == D.HELD),
    }
