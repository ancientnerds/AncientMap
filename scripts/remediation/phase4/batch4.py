"""Track B's batch-directory reading and writing, one spelling for every Track-B stage.

A batch directory is `output/remediation/phase4_runner/runs/<run>/<batch>/` (contracts, section 4).
The cross-track files are `model4`'s (`input.json`, `lanes.jsonl`, `holds.jsonl`, `evidence/`,
`assembly.jsonl`); the files below them are Track B's own: the candidate pools, the parsed answers,
the prompts and answers of every model call, and one report per stage.

Rules every stage keeps through these helpers:

* **Holds are appended, never rewritten, and never twice.** `holds.jsonl` is written by every stage
  of every track. A hold whose exact line is already there is not appended again, so a resumed stage
  (whose details are deterministic) leaves the file as it was.
* **A prompt is write-once.** It is stored under `prompts/` before the call, through the Phase-3
  evidence store, which refuses different bytes over a stored file: an answer on disk is only reused
  for the very prompt it answered (resume works by answer existence, design "DRIVER").
* **Absence is a fact, a broken file is an error.** A missing `holds.jsonl` means nothing is held
  yet; a line that does not parse raises.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402  - the write-once store
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402  - the model seam
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError, read_jsonl  # noqa: E402

#: The file hash `review4.json` records over `assembly.jsonl`: Phase 3's own.
from phase3.run import _sha256 as sha256_file  # noqa: E402

from phase4 import model4 as M  # noqa: E402

#: `input.json`, the one reader of every phase-4 stage: the batch id is the directory's name, the
#: record Phase 3's single batch (`phase3.run._single_batch`), the sites `PlanSite`s, at least one.
from phase4.sources_stage import read_batch  # noqa: E402

#: Track B's own files in a batch directory.
POOLS_FILE = "pools.jsonl"  #: the candidate pool each selector prompt showed
SELECTIONS_FILE = "selection.jsonl"  #: `model4.Selection`, one per parsed selector answer
TRANSLATIONS_FILE = "translations.jsonl"  #: lane T: the English sentence per chosen sid
RESTATEMENTS_FILE = "restatements.jsonl"  #: lane R: the restated sentence per located quote
ANSWERS_DIR = "answers"  #: selector, translate and restricted answers (write-once)
REVIEWS_DIR = "reviews"  #: reviewer answers (write-once)
PROMPTS_DIR = "prompts"  #: every prompt, written before its call (write-once)
SELECT_REPORT = "select.json"
TRANSLATE_REPORT = "translate.json"
RESTRICTED_REPORT = "restricted.json"
REVIEW_REPORT = "review4.json"

#: The ledger labels' field part and the answer file names (`ModelCall.field`).
SELECT_FIELD = "select"
TRANSLATE_FIELD = "translate"
RESTRICTED_FIELD = "restricted"
REVIEW_FIELD = "review"


# ------------------------------------------------------------------------------------ the inputs


def run_name(batch_dir: Path) -> str:
    """The run a batch belongs to: `runs/<run>/<batch>`. It is `provenance.run`."""
    return batch_dir.resolve().parent.name


def read_lanes(batch_dir: Path, sites: Sequence[M.PlanSite]) -> dict[str, M.LaneAssignment]:
    """`lanes.jsonl`: exactly one `LaneAssignment` per site of the batch, and no other."""
    rows = M.load_jsonl(batch_dir / M.LANES_FILE, M.LaneAssignment)
    lanes: dict[str, M.LaneAssignment] = {}
    for row in rows:
        if row.site_id in lanes:
            raise InputError(f"{batch_dir}: {row.site_id} has two lane assignments")
        lanes[row.site_id] = row
    wanted = {site.site_id for site in sites}
    if set(lanes) != wanted:
        raise InputError(
            f"{batch_dir}: lanes.jsonl covers {sorted(set(lanes) ^ wanted)} wrongly; it needs "
            "exactly one line per site of the batch"
        )
    return lanes


def read_holds(batch_dir: Path) -> list[M.Hold]:
    path = batch_dir / M.HOLDS_FILE
    if not path.exists():
        return []
    return M.load_jsonl(path, M.Hold)


def site_held(holds: Iterable[M.Hold]) -> set[str]:
    """The sites a site-scope hold keeps unwritten; a card hold leaves its site going."""
    return {hold.site_id for hold in holds if hold.scope is M.HoldScope.SITE}


def append_holds(batch_dir: Path, new: Iterable[M.Hold]) -> int:
    """Append the holds that are not already in `holds.jsonl`, byte for byte. Returns how many."""
    path = batch_dir / M.HOLDS_FILE
    present = {hold.to_json() for hold in read_holds(batch_dir)}
    lines: list[str] = []
    for hold in new:
        line = hold.to_json()
        if line not in present:
            present.add(line)
            lines.append(line + "\n")
    if lines:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(lines))
    return len(lines)


def evidence_store(batch_dir: Path) -> F.EvidenceStore:
    return F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)


def read_meta(batch_dir: Path, site_id: str, source_id: str) -> dict[str, Any]:
    """The raw `src.<id>.meta` object (what `verify4.verify_site` reads as `metas`)."""
    path = evidence_store(batch_dir).path_for(site_id, M.source_feature(source_id, "meta"))
    data = M.parse_json(path.read_bytes().decode("utf-8"))
    if not isinstance(data, dict):
        raise InputError(f"{path}: a source meta is a JSON object")
    return data


def read_source(batch_dir: Path, site_id: str, source_id: str) -> tuple[M.SourceDoc, str]:
    """A source's meta as a record and its pinned text: the exact UTF-8 bytes, decoded."""
    meta = M.SourceDoc.from_dict(read_meta(batch_dir, site_id, source_id))
    if meta.id != source_id:
        raise InputError(f"{batch_dir}: {site_id}'s src.{source_id}.meta names {meta.id}")
    path = evidence_store(batch_dir).path_for(site_id, M.source_feature(source_id, "txt"))
    return meta, path.read_bytes().decode("utf-8")


# --------------------------------------------------------------------------- Track B's own files


def write_text_atomic(path: Path, body: str) -> None:
    """A derived file, rewritten whole: written beside and swapped in, so a kill leaves the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(body, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_records(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    write_text_atomic(path, body)


def read_records(path: Path, keys: frozenset[str]) -> dict[str, dict[str, Any]]:
    """One of Track B's own JSONL files, keyed by site id; every line has exactly `keys`."""
    records: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if set(row) != keys:
            raise InputError(f"{path}: a line carries {sorted(row)}, not {sorted(keys)}")
        site_id = row["site_id"]
        if not isinstance(site_id, str) or site_id in records:
            raise InputError(f"{path}: site id {site_id!r} is missing or listed twice")
        records[site_id] = row
    return records


POOL_KEYS = frozenset({"site_id", "source", "sentences"})


def pool_record(site_id: str, source_id: str, pool: Sequence[M.Sentence]) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "source": source_id,
        "sentences": [sentence.to_dict() for sentence in pool],
    }


def read_pools(batch_dir: Path) -> dict[str, tuple[str, tuple[M.Sentence, ...]]]:
    rows = read_records(batch_dir / POOLS_FILE, POOL_KEYS)
    return {
        site_id: (row["source"], tuple(M.Sentence.from_dict(s) for s in row["sentences"]))
        for site_id, row in rows.items()
    }


def read_selections(batch_dir: Path) -> dict[str, M.Selection]:
    selections: dict[str, M.Selection] = {}
    for selection in M.load_jsonl(batch_dir / SELECTIONS_FILE, M.Selection):
        if selection.site_id in selections:
            raise InputError(f"{batch_dir}: {selection.site_id} has two selections")
        selections[selection.site_id] = selection
    return selections


TRANSLATION_KEYS = frozenset({"site_id", "sentences"})


def read_translations(batch_dir: Path) -> dict[str, dict[str, str]]:
    """Lane T: `site_id -> {sid: English sentence}`."""
    out: dict[str, dict[str, str]] = {}
    for site_id, row in read_records(batch_dir / TRANSLATIONS_FILE, TRANSLATION_KEYS).items():
        pairs = row["sentences"]
        if not isinstance(pairs, list) or not all(
            isinstance(p, dict) and set(p) == {"sid", "text"} for p in pairs
        ):
            raise InputError(f"{batch_dir}: {site_id}'s translations are not sid/text pairs")
        out[site_id] = {p["sid"]: p["text"] for p in pairs}
    return out


RESTATEMENT_KEYS = frozenset({"site_id", "sentences"})


@dataclass(frozen=True)
class Restatement:
    """Lane R: one restated sentence and the exact range of its quote in its page."""

    text: str
    src: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "src": self.src, "start": self.start, "end": self.end}


def read_restatements(batch_dir: Path) -> dict[str, tuple[Restatement, ...]]:
    out: dict[str, tuple[Restatement, ...]] = {}
    for site_id, row in read_records(batch_dir / RESTATEMENTS_FILE, RESTATEMENT_KEYS).items():
        items = row["sentences"]
        if not isinstance(items, list) or not all(
            isinstance(i, dict) and set(i) == {"text", "src", "start", "end"} for i in items
        ):
            raise InputError(f"{batch_dir}: {site_id}'s restatements are malformed")
        out[site_id] = tuple(Restatement(**item) for item in items)
    return out


def write_report(path: Path, payload: Mapping[str, Any]) -> None:
    write_text_atomic(
        path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    )


# ------------------------------------------------------------------------------ one model call


@dataclass(frozen=True)
class Bought:
    """One answered call: its text, the digests the journal evidence needs, and what it cost."""

    text: str
    label: str
    prompt_sha256: str
    answer_sha256: str
    cost_usd: float
    wrote: bool


def buy(
    *,
    batch_dir: Path,
    batch_id: str,
    site_id: str,
    field: str,
    stage: Stage,
    prompt: MS.Prompt,
    runner: MS.ModelRunner,
    ledger: L.Ledger,
    answers: F.EvidenceStore,
) -> Bought:
    """One call through `model_stage.judge_site`: ledger line first, answer stored write-once.

    The prompt is stored first, write-once, so an answer already on disk is reused only for the
    very prompt it answered. `UnreadableStream` (the provider answered with no usable text) and
    `ModelCallFailed` (the call could not be made) propagate; the stage decides which one holds the
    site and which one stops the batch. Nothing here retries.
    """
    rendered = prompt.render()
    F.EvidenceStore(batch_dir / PROMPTS_DIR).write(
        site_id=site_id, feature=field, body=rendered.encode("utf-8")
    )
    call = MS.ModelCall(
        stage=stage, batch_id=batch_id, site_id=site_id, prompt=rendered, field=field
    )
    judged = MS.judge_site(
        prepared=MS.PreparedCall(call=call, excerpts=[]),
        runner=runner,
        ledger=ledger,
        answers=answers,
    )
    return Bought(
        text=judged.answer.text,
        label=call.label,
        prompt_sha256=M.text_sha256(rendered),
        answer_sha256=M.text_sha256(judged.answer.text),
        cost_usd=judged.answer.cost_usd,
        wrote=judged.wrote,
    )
