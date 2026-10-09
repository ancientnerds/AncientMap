"""The rounds of an identity question stage: export, the agents' answers, the import's reading.

The identity stages (the duplicate verdict, its adversarial recheck, the parent question) all run
the same way as L5 (`l5/handoff.py`): the stage exports its questions, Claude agents of the
orchestrating session answer them through `opus_handoff.py answer --role`, `opus_handoff.py validate`
checks every answer's shape and prompt, and the stage's import reads them back. This module is the
part they share, and nothing of any one question's content:

* **a round** is one export into its own handoff directory (an exported question is never
  replaced); a re-ask round asks the labels whose latest answer was held, each prompt carrying why,
  so the import can rebuild every prompt exactly and refuse an answer to any other;
* **a batch** is `PER_BATCH` questions for one agent;
* **an answer is the role's** (`roles.ROLES`, owner decision D6): it must name the role the stage
  asks (`answered_by = "<role>:<agent>"`), carry that role's model stamp, and never be a MiniMax
  stamp (master plan X6, owner decision D10: a MiniMax answer is no ground truth).

The rounds of a stage are recorded in `<run>/<stage>/ROUNDS.jsonl`; only the newest round is imported
and there are at most `MAX_ROUNDS` of them (the first and two re-asks).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from identity import common  # noqa: E402
from identity.wiki import WikiIndex  # noqa: E402

ROUNDS_FILE = "ROUNDS.jsonl"
ANSWERS_DIR = "answers"
PER_BATCH = 5
#: The first round and two re-asks: what is held after them stays held and is listed.
MAX_ROUNDS = 3


class RoundError(ValueError):
    """A round that cannot be exported or imported as asked. Nothing was written."""


class AnswerError(ValueError):
    """An answer that is not in its exact shape, or breaks a rule it can break on its own."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Round:
    name: str
    stage: str
    handoff: str
    exported_at: str
    #: what the questions were built from (the export's snapshot clock), so an import can refuse
    #: to read answers against another state of the data
    basis: str
    batches: dict[str, list[str]]
    #: label -> why its answer of the round before was held (re-ask rounds only)
    earlier: dict[str, str]

    @property
    def labels(self) -> list[str]:
        return [label for batch in self.batches.values() for label in batch]


def stage_dir(run: Path, stage: str) -> Path:
    return run / stage


def load_rounds(run: Path, stage: str) -> list[Round]:
    path = stage_dir(run, stage) / ROUNDS_FILE
    if not path.exists():
        return []
    return [
        Round(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]


def find_round(run: Path, stage: str, name: str) -> Round:
    for r in load_rounds(run, stage):
        if r.name == name:
            return r
    raise RoundError(f"no round {name!r} in {stage_dir(run, stage) / ROUNDS_FILE}")


def imported(run: Path, stage: str, name: str) -> bool:
    return (stage_dir(run, stage) / ANSWERS_DIR / f"{name}.jsonl").exists()


def newest_imported(run: Path, stage: str, doing: str) -> list[Round]:
    """The rounds, only when the newest is imported: `doing` would read decisions older than the
    answers already exported."""
    rounds = load_rounds(run, stage)
    if not rounds:
        raise RoundError(f"no {stage} round is exported yet - {doing} reads the imported answers")
    if not imported(run, stage, rounds[-1].name):
        raise RoundError(
            f"{stage} round {rounds[-1].name} is exported but not imported - import it before {doing}"
        )
    return rounds


def batches(
    labels: Sequence[str], round_name: str, per_batch: int = PER_BATCH
) -> dict[str, list[str]]:
    """`<round>-bNN -> labels`, in label order, at most `per_batch` each."""
    if per_batch < 1:
        raise RoundError("a batch holds at least one question")
    ordered = sorted(labels)
    return {
        f"{round_name}-b{i // per_batch + 1:02d}": ordered[i : i + per_batch]
        for i in range(0, len(ordered), per_batch)
    }


def shown(path: Path) -> str:
    """A path as the brief prints it: relative to the main checkout where it lies inside."""
    try:
        return path.resolve().relative_to(common.main_checkout().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve(path: str | Path, root: Path | None = None) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (root or common.main_checkout()) / candidate


def export_round(
    run: Path,
    stage: str,
    labels: Sequence[str],
    prompt_of: Callable[[str, str | None], str],
    handoff: Path,
    *,
    basis: str,
    earlier: Mapping[str, str] | None = None,
    per_batch: int = PER_BATCH,
    now: Callable[[], str] = now_utc,
) -> Round:
    """Export one round of questions into a new handoff directory and record it."""
    earlier = dict(earlier or {})
    if not labels:
        raise RoundError("no question to ask - nothing to export")
    if len(set(labels)) != len(labels):
        raise RoundError("a label is asked twice in one round")
    if handoff.exists() and any(handoff.iterdir()):
        raise RoundError(f"{handoff} is not empty: a round is exported into a new directory")
    name = f"r{len(load_rounds(run, stage)) + 1}"
    if len(load_rounds(run, stage)) >= MAX_ROUNDS:
        raise RoundError(
            f"{MAX_ROUNDS} {stage} rounds are out: what stays held is listed, not asked"
        )
    grouped = batches(labels, name, per_batch)
    handoff.mkdir(parents=True, exist_ok=True)
    for batch_id, members in grouped.items():
        for label in members:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=stage,
                label=label,
                field=None,
                prompt=prompt_of(label, earlier.get(label)),
            )
    record = Round(name, stage, shown(handoff), now(), basis, grouped, earlier)
    path = stage_dir(run, stage) / ROUNDS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return record


def role_problem(answer: OH.Answer, allowed_roles: Iterable[str]) -> str | None:
    """Why an answer is not given by one of `allowed_roles`, or `None`.

    An answer must name its role (`answer --role` records `<role>:<agent>`), be one of the allowed
    roles, carry the stamp of that role's registered model, and not be a MiniMax stamp: master plan
    X6 (owner decision D10) - MiniMax answers are never ground truth."""
    allowed = list(allowed_roles)
    if answer.model == OH.MINIMAX_MODEL:
        return "answered by MiniMax - a MiniMax answer is never ground truth (D10)"
    named = RO.role_of(answer.answered_by)
    if named is None:
        return f"answered_by {answer.answered_by!r} names no role (answer --role {allowed[0]})"
    if named not in allowed:
        return f"answered in role {named}, but this stage asks {' or '.join(allowed)}"
    return RO.answer_problem(answer.answered_by, answer.model)


def read_answers(
    run: Path,
    stage: str,
    record: Round,
    prompt_of: Callable[[str, str | None], str],
    *,
    root: Path | None = None,
) -> dict[str, OH.Answer]:
    """Every answer of a round, read against the prompt rebuilt from the data (`OH.read_answer`
    refuses an answer to another prompt)."""
    handoff = resolve(record.handoff, root)
    check = OH.validate(handoff)
    if not check.ok:
        raise RoundError(
            f"{handoff} does not validate ({len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan(s)) - run "
            "`opus_handoff.py validate` and have the questions answered first"
        )
    answers: dict[str, OH.Answer] = {}
    for batch_id, labels in record.batches.items():
        for label in labels:
            answers[label] = OH.read_answer(
                handoff,
                batch_id=batch_id,
                stage=stage,
                label=label,
                prompt=prompt_of(label, record.earlier.get(label)),
            )
    return answers


def write_answers_file(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    common.write_jsonl(path, records)


def check_importable(run: Path, stage: str, name: str) -> Round:
    """The round `name`, only if it is the newest one: an older one would overwrite newer decisions."""
    record = find_round(run, stage, name)
    newest = load_rounds(run, stage)[-1].name
    if record.name != newest:
        raise RoundError(
            f"round {name} is not the newest ({newest}): its answers would overwrite the newer "
            "round's decisions"
        )
    return record


def parse_quotes(data: Any, where: str) -> tuple[dict[str, str], ...]:
    if not isinstance(data, list):
        raise AnswerError(f"{where}: quotes is not a list")
    checked = []
    for q in data:
        if not isinstance(q, dict) or set(q) != {"source", "quote"}:
            raise AnswerError(f"{where}: a quote is not {{source, quote}}: {q!r}")
        if not all(isinstance(q[k], str) and q[k].strip() for k in ("source", "quote")):
            raise AnswerError(f"{where}: a quote needs a source and a text")
        if not Q.is_url(q["source"]):
            raise AnswerError(
                f"{where}: a quote's source must be the URL of the page: {q['source']!r}"
            )
        refused = Q.not_fetchable(q["source"])
        if refused:
            raise AnswerError(f"{where}: {q['source']} is never fetched here ({refused})")
        checked.append({"source": q["source"], "quote": q["quote"]})
    return tuple(checked)


# ------------------------------------------------------------------------------ the decisions
DECIDED, HELD = "decided", "held"
DECISIONS_FILE = "DECISIONS.jsonl"
PAGES_DIR = "pages"
Fetch = Callable[[list[str], Path], dict[str, int]]


def load_decisions(stage_run: Path, stage: str) -> dict[str, dict[str, Any]]:
    """The latest decision per label of a stage (`<stage_run>/<stage>/DECISIONS.jsonl`)."""
    path = stage_dir(stage_run, stage) / DECISIONS_FILE
    if not path.exists():
        return {}
    return {r["label"]: r for r in common.read_jsonl(path)}


def labels_for_round(
    stage_run: Path, stage: str, first: Sequence[str]
) -> tuple[list[str], dict[str, str]]:
    """`(labels, earlier)` of the next round: `first` for round 1; later the labels whose latest
    decision is held (with why), once the newest round is imported."""
    if not load_rounds(stage_run, stage):
        return sorted(first), {}
    newest_imported(stage_run, stage, "a re-ask")
    held = {
        label: d for label, d in load_decisions(stage_run, stage).items() if d["status"] == HELD
    }
    return sorted(held), {label: d["reason"] for label, d in held.items()}


def shape_held(label: str, round_name: str, answered_by: str, reason: str) -> dict[str, Any]:
    """A label whose answer is not in shape: held, with the reason a re-ask shows."""
    return {
        "label": label,
        "status": HELD,
        "reason": f"shape: {reason}",
        "round": round_name,
        "answered_by": answered_by,
        "members": [],
    }


def quote_outcomes(
    quotes: Sequence[Mapping[str, str]], key: str, library: Q.Library
) -> tuple[list[str], str | None]:
    """Each quote's outcome, and the first failure in words (or `None` when every quote is found)."""
    if not quotes:
        return [], None
    check = Q.check_verdict(
        {"quotes": list(quotes)}, {"change_key": key, "evidence_files": []}, library
    )
    outcomes = [f"{r.outcome}: {r.detail}".rstrip(": ") for r in check.quotes]
    if check.counted:
        return outcomes, None
    failed = next(r for r in check.quotes if r.outcome != Q.FOUND)
    return outcomes, f"a quote does not count ({failed.outcome}: {failed.source})"


def keep_pages(
    pages: Path,
    urls: Iterable[str],
    wiki: WikiIndex | None,
    fetch: Fetch,
    *,
    now: Callable[[], str] = now_utc,
) -> dict[str, int]:
    """Keep every cited page under `pages`: a Wikipedia article the shared cache holds is stored
    from the cache (the very text the agent read), every other URL is fetched live by `fetch`."""
    live: list[str] = []
    counts = {"cache": 0}
    for url in sorted(set(urls)):
        cached = wiki.for_url(url) if wiki is not None else None
        if cached is None:
            live.append(url)
            continue
        if not (pages / f"{Q.url_key(url)}.json").exists():
            Q.store_page(
                pages,
                url,
                status=200,
                final_url=url,
                content_type="text/plain; charset=utf-8",
                body=cached.text().encode("utf-8"),
                error="",
                fetched_at=cached.fetched_at or now(),
            )
        counts["cache"] += 1
    counts.update(fetch(live, pages) if live else {})
    return counts


def import_stage(
    stage_run: Path,
    stage: str,
    round_name: str,
    *,
    prompt_of: Callable[[str, str | None], str],
    allowed_roles: Sequence[str],
    parse: Callable[[str, str], Any],
    decide: Callable[[str, Any, str, str, Q.Library], dict[str, Any]],
    wiki: WikiIndex | None,
    fetch: Fetch,
    extra_urls: Iterable[str] = (),
    now: Callable[[], str] = now_utc,
    root: Path | None = None,
    repo: Path | None = None,
) -> dict[str, Any]:
    """Read, parse, fetch and decide every answer of one round of `stage`; merge the decisions.

    `parse(label, text)` returns the answer's items (each with `.quotes`) or raises `AnswerError`;
    `decide(label, items, round_name, answered_by, library)` is the stage's machine checks. A
    wrong role, a MiniMax stamp or an answer to another prompt stops the import (`RoundError`):
    those are not answers a re-ask can mend, they are answers that do not count at all."""
    record = check_importable(stage_run, stage, round_name)
    answers = read_answers(stage_run, stage, record, prompt_of, root=root)
    parsed: dict[str, tuple[Any, OH.Answer]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for label, answer in answers.items():
        problem = role_problem(answer, allowed_roles)
        if problem is not None:
            raise RoundError(f"{stage}/{label}: {problem}")
        try:
            parsed[label] = (parse(label, answer.text), answer)
        except AnswerError as exc:
            decisions[label] = shape_held(label, round_name, answer.answered_by, str(exc))
    urls = {
        q["source"] for items, _ in parsed.values() for item in items.values() for q in item.quotes
    }
    counts = keep_pages(
        stage_dir(stage_run, stage) / PAGES_DIR, urls | set(extra_urls), wiki, fetch, now=now
    )
    library = Q.Library(repo or common.REPO, stage_dir(stage_run, stage) / PAGES_DIR)
    for label, (items, answer) in parsed.items():
        by = f"{answer.answered_by} ({answer.answered_at})"
        decisions[label] = decide(label, items, round_name, by, library)
    out = stage_dir(stage_run, stage)
    write_answers_file(
        out / ANSWERS_DIR / f"{round_name}.jsonl", [decisions[c] for c in sorted(decisions)]
    )
    merged = load_decisions(stage_run, stage)
    merged.update(decisions)
    common.write_jsonl(out / DECISIONS_FILE, [merged[c] for c in sorted(merged)])
    statuses = {s: sum(1 for d in decisions.values() if d["status"] == s) for s in (DECIDED, HELD)}
    reasons: dict[str, int] = {}
    for d in decisions.values():
        if d["status"] == HELD:
            reasons[d["reason"].split(":")[0]] = reasons.get(d["reason"].split(":")[0], 0) + 1
    return {
        "stage": stage,
        "round": round_name,
        "answers": len(decisions),
        "decided": statuses[DECIDED],
        "held": statuses[HELD],
        "held_reasons": reasons,
        "pages": counts,
    }
