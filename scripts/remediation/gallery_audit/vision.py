"""S6 - the vision stage: two frozen questions, the Opus handoff, an append-only verdict ledger.

The model classifies; it never writes a value. `decide.py` maps a verdict to a database value by a
sealed rule table, and every planned row cites the verdict it rests on by `verdict_id` - the
sha256 of that verdict's ledger line.

The two questions (frozen - their sha256 is pinned in `tests/remediation/test_gallery_vision.py`)
-------------------------------------------------------------------------------------------------
``GALLERY_PROMPT`` (``gallery-v1``) - the first pass on every judged image. It gets the site's
name, country and type, the Commons file title and the file's Commons categories (T10's cache),
and deliberately **no card text**: `shorts_select.VLM_PROMPT` puts the narration into the question,
and Phase 5 regenerates those texts, which would invalidate every verdict. The kind vocabulary and
its definitions are copied byte for byte from `VLM_PROMPT`, so the kind competence the pilot measured
(`output/remediation/vlm_pilot/COMPETENCE.md`) carries over; `other_site` is redefined strictly,
because `VLM_PROMPT` says "a related site next door ... does not count" and so cannot catch a
neighbouring monument (Agri Bavnehoj's gallery shows the mound Stabelhoje, 1 km away).

``HERO_PROMPT`` (``hero-v1``) - the strict positive pass, only on served images and hero candidates
the first pass called ``site_photo``. The pilot measured ``site_photo`` as over-inclusive in the
hero tier (74 % claimed, about 40 % accepted: empty fields, hillsides, a coastline, one engraving),
so an unconfirmed ``site_photo`` is never written as clean.

Transport - the Opus handoff (owner order 2026-09-23)
-----------------------------------------------------
"No DeepSeek any more - everything with Opus": every question is answered by an Opus agent of the
orchestrating Claude Code session (`opus_handoff.OPUS_MODEL`) through the handoff directory
(`scripts/remediation/opus_handoff.py`), never by a model API called from here. Until 2026-09-23
the pilot's opencode gateway (`deepseek-v4-flash-vision-exp`, `vlm_pilot/ask_vlm.py`) answered; it is
not imported any more, and `vlm_pilot/` stays as the pilot's history.

* ``export`` hands every job the ledger holds no ok verdict for to the handoff: the filled frozen
  question (batch = the job's stage, stage ``vision``, label ``<image_id>/<prompt_id>``) and the image
  as the exact bytes the pilot sent - `pipeline.video.shorts_select.vlm_bytes` (RGB, longest side
  1280, JPEG q85) of the offsite copy, read through `vlm_pilot/common.py`'s exact-case lookup, main
  tree first, then the case-collision tree - to ``images/<image_id>.jpg``.
* the orchestrator's Opus agents answer each question with the JSON the question asks for, and
  ``opus_handoff.py validate`` checks every answer before anything is imported.
* ``import`` refuses to start while any job lacks a valid answer, then writes one ledger line per
  job from its answer through the same parsing as ever (`extract_json`, `validate`: the
  in-vocabulary check, status ``ok`` or ``failed``). A line names ``model`` = `MODEL`, says
  ``metering: unmetered`` and carries ``cost_usd`` 0: an Opus answer has no per-call meter. There is
  one answer per question and no retry: a question answered badly is answered again by the
  orchestrator, never re-asked here.

Stops, never skips
------------------
* An image whose file cannot be found or read, an answer given about other bytes than today's JPEG
  of the image, or an answer with no parseable in-vocabulary verdict is written to the ledger as
  ``status: failed`` and **stops the run with exit 3**. It is never written as ``other`` or
  ``unknown``: an empty answer that reads as a verdict is the silent failure this lane exists to rule
  out.
* The spend is summed from the ledger (every line carries its cost, failed lines included); once
  it reaches the budget no further line is written and the run exits 4. The Opus lines add 0; the
  lines of the pilot's transport, where a ledger carries them, still count.

Usage:
    vision.py export --jobs JOBS.jsonl --run-dir DIR --handoff HANDOFF [--dry-run]
    vision.py import --jobs JOBS.jsonl --run-dir DIR --handoff HANDOFF [--budget-usd 75]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION = ROOT / "scripts" / "remediation"
_PILOT = _REMEDIATION / "vlm_pilot"
for _entry in (ROOT, _REMEDIATION, _PILOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import common as pilot  # noqa: E402  (the pilot's offsite lookup, kinds and answer reader)
import opus_handoff as OH  # noqa: E402  (the handoff directory every answer comes through)
from phase3.ledger import UNMETERED  # noqa: E402  (the one spelling of "no meter read it")

from pipeline.video.shorts_select import vlm_bytes  # noqa: E402

#: The model every answer is by, and every ledger line names (`verdicts_by_image` refuses another).
MODEL = OH.OPUS_MODEL
KINDS: tuple[str, ...] = pilot.EXPECTED_KINDS
#: The stage every vision question is handed off under: a path component of the handoff directory.
HANDOFF_STAGE = "vision"

GALLERY = "gallery"
HERO = "hero"
PASSES = (GALLERY, HERO)

GALLERY_PROMPT_ID = "gallery-v1"
HERO_PROMPT_ID = "hero-v1"

GALLERY_PROMPT = """You judge one picture from the image gallery of the archaeological site "{site}" ({site_type}, {country}).
The picture's file title on Wikimedia Commons is: "{title}"
The file's Commons categories are: {categories}

Return JSON only, no prose:
{{"kind": "site_photo" | "artifact" | "map_or_document" | "painting_or_artwork" | "people" | "other",
 "other_site": true | false,
 "other_place": "<the place shown when other_site is true, at most 8 words, else an empty string>",
 "subject": "<2-4 words naming what the photo shows>"}}
kind: site_photo = the site, its structures or landscape photographed on location; artifact = an object in a museum or studio; map_or_document = maps, drawings, scans, diagrams, book pages; painting_or_artwork = a painting, engraving, print or artistic reconstruction of the site rather than a photograph; people = a person or crowd is the subject.
other_site: true if the title, the categories or the picture show a place other than "{site}", including a neighbouring monument, a nearby modern park, town or zoo, or a comparison site; false only if it shows "{site}" itself or objects found there."""

HERO_PROMPT = """You check whether a picture can be the title image of the page about the archaeological site "{site}" ({site_type}, {country}).
The picture's file title on Wikimedia Commons is: "{title}"
The file's Commons categories are: {categories}

Return JSON only, no prose:
{{"shows_archaeology": true | false,
 "structure": "<at most 8 words naming the visible monument, ruin, earthwork or rock art, else an empty string>",
 "generic_landscape": true | false}}
shows_archaeology: true only if the picture is a photograph, taken on location, that clearly shows the archaeological remains of "{site}" - a monument, ruin, earthwork, excavation or rock art. Empty fields, hillsides, coastlines, roads, sky, modern buildings, engravings, drawings and maps are false.
generic_landscape: true if the picture is mainly scenery - fields, hills, water, sky or vegetation - in which no archaeological remains can be recognised."""

PROMPTS: dict[str, tuple[str, str]] = {
    GALLERY: (GALLERY_PROMPT_ID, GALLERY_PROMPT),
    HERO: (HERO_PROMPT_ID, HERO_PROMPT),
}


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: A budget stop is read from the ledger (design: $52 expected, $65 upper bound, stop at $75).
DEFAULT_BUDGET_USD = 75.0

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_NO_VERDICT = 3
EXIT_BUDGET = 4

#: The categories line when a file has no Commons category list to show (no Commons identity, or
#: T10 could not fetch it) - said as such, never as an empty list, which would claim "none".
CATEGORIES_UNKNOWN = "(not available)"
CATEGORIES_NONE = "(none)"


class VisionError(RuntimeError):
    """The stage cannot go on without guessing. Never downgraded to a skip."""


# ------------------------------------------------------------------------------ jobs
@dataclass(frozen=True)
class Job:
    """One question about one image. Built by `worklist.py`, executed here."""

    image_id: int
    site_id: str
    filename: str
    pass_: str
    stage: str
    site_name: str
    country: str
    site_type: str
    title: str
    title_source: str
    categories: tuple[str, ...] | None
    tier: str | None = None

    def key(self) -> tuple[int, str]:
        """A job is done once per image and question: the prompt id names the question."""
        return (self.image_id, PROMPTS[self.pass_][0])

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["pass"] = out.pop("pass_")
        out["categories"] = None if self.categories is None else list(self.categories)
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Job:
        fields = {
            "image_id",
            "site_id",
            "filename",
            "pass",
            "stage",
            "site_name",
            "country",
            "site_type",
            "title",
            "title_source",
            "categories",
            "tier",
        }
        if set(data) != fields:
            raise VisionError(f"a job line with the keys {sorted(data)} is not a job")
        if data["pass"] not in PASSES:
            raise VisionError(f"unknown pass {data['pass']!r}")
        cats = data["categories"]
        return cls(
            image_id=int(data["image_id"]),
            site_id=str(data["site_id"]),
            filename=str(data["filename"]),
            pass_=str(data["pass"]),
            stage=str(data["stage"]),
            site_name=str(data["site_name"]),
            country=str(data["country"]),
            site_type=str(data["site_type"]),
            title=str(data["title"]),
            title_source=str(data["title_source"]),
            categories=None if cats is None else tuple(str(c) for c in cats),
            tier=None if data["tier"] is None else str(data["tier"]),
        )


def read_jobs(path: Path) -> list[Job]:
    if not path.is_file():
        raise VisionError(f"{path} does not exist")
    jobs = [
        Job.from_json(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    keys = [job.key() for job in jobs]
    if len(set(keys)) != len(keys):
        raise VisionError(f"{path} asks the same question about one image twice")
    return jobs


def jobs_text(jobs: Iterable[Job]) -> str:
    """The text of JOBS.jsonl: one canonical line per job."""
    return "".join(
        json.dumps(job.as_json(), ensure_ascii=False, sort_keys=True) + "\n" for job in jobs
    )


def write_jobs(path: Path, jobs: Iterable[Job]) -> str:
    """JOBS.jsonl, one canonical line per job. Returns its sha256."""
    text = jobs_text(jobs)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def categories_text(categories: Sequence[str] | None) -> str:
    """The categories line: raw Commons titles without the namespace, in a fixed order."""
    if categories is None:
        return CATEGORIES_UNKNOWN
    names = sorted({re.sub(r"^Category:", "", c).strip() for c in categories if c.strip()})
    return "; ".join(f'"{n}"' for n in names) if names else CATEGORIES_NONE


def job_label(job: Job) -> str:
    """A question's label in the handoff: the image and the frozen question's id."""
    return f"{job.image_id}/{PROMPTS[job.pass_][0]}"


def prompt_for(job: Job) -> str:
    """The frozen question of the job's pass, filled from the job. Nothing else goes in."""
    _, template = PROMPTS[job.pass_]
    return template.format(
        site=job.site_name,
        country=job.country or "country unknown",
        site_type=job.site_type or "type unknown",
        title=job.title,
        categories=categories_text(job.categories),
    )


# ------------------------------------------------------------------------------ images
class Images:
    """The offsite copy, looked up by exact-case name (`vlm_pilot/common.locate`).

    Main tree first, then `images-case-collisions/` - three files exist only there, and a Windows
    `Path.is_file()` would accept the wrong-case twin instead.
    """

    def __init__(
        self, roots: Sequence[Path] = (pilot.OFFSITE_IMAGES, pilot.OFFSITE_CASE_COLLISIONS)
    ) -> None:
        self.trees = tuple((root, pilot.build_tree(root)) for root in roots)

    def path_for(self, site_id: str, filename: str) -> Path:
        hit = pilot.locate(self.trees, site_id, filename)
        if hit is None:
            raise VisionError(
                f"no offsite file {pilot.shard_for(site_id)}/{filename} in "
                f"{[str(root) for root, _ in self.trees]}"
            )
        return hit[0]


# ------------------------------------------------------------------------------ verdicts
def validate(
    pass_: str, parsed: Mapping[str, Any] | None
) -> tuple[dict[str, Any] | None, str | None]:
    """The verdict the rules may read, or the reason there is none.

    Only the fields a rule reads are kept, each with its exact type: `"true"` is not a boolean,
    and a kind outside the six the prompt prints is not a kind.
    """
    if parsed is None:
        return None, "unparsable JSON in the response"
    if pass_ == GALLERY:
        kind = parsed.get("kind")
        if kind not in KINDS:
            return None, f"'kind' out of vocabulary: {kind!r}"
        if not isinstance(parsed.get("other_site"), bool):
            return None, f"'other_site' is not a boolean: {parsed.get('other_site')!r}"
        for key in ("other_place", "subject"):
            if not isinstance(parsed.get(key), str):
                return None, f"'{key}' is not a string: {parsed.get(key)!r}"
        return {k: parsed[k] for k in ("kind", "other_site", "other_place", "subject")}, None
    for key in ("shows_archaeology", "generic_landscape"):
        if not isinstance(parsed.get(key), bool):
            return None, f"'{key}' is not a boolean: {parsed.get(key)!r}"
    if not isinstance(parsed.get("structure"), str):
        return None, f"'structure' is not a string: {parsed.get('structure')!r}"
    return {k: parsed[k] for k in ("shows_archaeology", "structure", "generic_landscape")}, None


@dataclass
class Judge:
    """Everything one judgement needs besides the job: the images and the Opus answers."""

    handoff: Path
    images: Images
    now: Callable[[], str] = field(default=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def __call__(self, job: Job) -> dict[str, Any]:
        prompt_id, template = PROMPTS[job.pass_]
        prompt = prompt_for(job)
        line: dict[str, Any] = {
            "image_id": job.image_id,
            "site_id": job.site_id,
            "stage": job.stage,
            "tier": job.tier,
            "pass": job.pass_,
            "model": MODEL,
            "metering": UNMETERED,
            "prompt_id": prompt_id,
            "prompt_sha256": prompt_sha256(template),
            "prompt": prompt,
            "evidence": {
                "site_name": job.site_name,
                "country": job.country,
                "site_type": job.site_type,
                "title": job.title,
                "title_source": job.title_source,
                "categories": None if job.categories is None else sorted(job.categories),
            },
            "image_file": None,
            "image_sha256": None,
            "jpeg_sha256": None,
            "status": "failed",
            "verdict": None,
            "parsed": None,
            "raw_response": None,
            "error": None,
            "answered_by": None,
            "answered_at": None,
            "cost_usd": 0.0,
            "judged_at": self.now(),
        }
        try:
            path = self.images.path_for(job.site_id, job.filename)
        except VisionError as exc:
            line["error"] = f"image: {exc}"
            return line
        line["image_file"] = f"{pilot.shard_for(job.site_id)}/{path.name}"
        try:
            line["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            jpeg = vlm_bytes(path)
        except OSError as exc:  # PIL's UnidentifiedImageError is an OSError too
            line["error"] = f"image: {path} cannot be read as an image: {exc}"
            return line
        line["jpeg_sha256"] = hashlib.sha256(jpeg).hexdigest()
        shown = self.handoff / OH.image_relpath(str(job.image_id))
        if not shown.is_file() or shown.read_bytes() != jpeg:
            line["error"] = (
                f"image: the answer was given about {shown}, which is not today's JPEG of "
                f"{line['image_file']} - export the job again"
            )
            return line
        answer = OH.read_answer(
            self.handoff,
            batch_id=job.stage,
            stage=HANDOFF_STAGE,
            label=job_label(job),
            prompt=prompt,
        )
        parsed = pilot.extract_json(answer.text)
        verdict, problem = validate(job.pass_, parsed)
        line.update(
            raw_response=answer.text,
            answered_by=answer.answered_by,
            answered_at=answer.answered_at,
            parsed=parsed,
        )
        if verdict is None:
            line["error"] = problem
            return line
        line.update(status="ok", verdict=verdict)
        return line


# ------------------------------------------------------------------------------ ledger
def line_text(line: Mapping[str, Any]) -> str:
    return json.dumps(line, ensure_ascii=False, sort_keys=True)


def verdict_id(text: str) -> str:
    """A verdict's id: the sha256 of its ledger line, exactly as written (without the newline)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerLine:
    verdict_id: str
    line: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.line["status"] == "ok"


class Ledger:
    """`VERDICTS.jsonl`: append-only, one line per judgement, failures and their cost included."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.lines: list[LedgerLine] = list(read_ledger(path)) if path.exists() else []
        self._spent = sum(float(entry.line["cost_usd"]) for entry in self.lines)

    @property
    def spent_usd(self) -> float:
        """The sum of the cost the ledger's lines record - the lines read at start plus every line
        this process appended, never a figure kept anywhere else."""
        return round(self._spent, 8)

    def done(self) -> set[tuple[int, str]]:
        return {(int(e.line["image_id"]), str(e.line["prompt_id"])) for e in self.lines if e.ok}

    def append(self, line: Mapping[str, Any]) -> LedgerLine:
        text = line_text(line)
        entry = LedgerLine(verdict_id(text), json.loads(text))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(text + "\n")
            self.lines.append(entry)
            self._spent += float(entry.line["cost_usd"])
        return entry


def read_ledger(path: Path) -> Iterator[LedgerLine]:
    """Every ledger line with its id. A damaged line stops the reader: an append-only ledger with a
    torn line is not a ledger any more, and the budget read from it would be wrong."""
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            text = raw.rstrip("\n")
            if not text:
                continue
            try:
                line = json.loads(text)
            except json.JSONDecodeError as exc:
                raise VisionError(f"{path}:{lineno}: a damaged ledger line ({exc})") from exc
            if line.get("status") not in ("ok", "failed") or "cost_usd" not in line:
                raise VisionError(f"{path}:{lineno}: not a verdict line")
            yield LedgerLine(verdict_id(text), line)


@dataclass(frozen=True)
class Verdict:
    """One ok ledger line of one question, as the rules read it."""

    verdict_id: str
    verdict: dict[str, Any]
    line: dict[str, Any]


def verdicts_by_image(lines: Iterable[LedgerLine], prompt_id: str) -> dict[int, Verdict]:
    """image id -> the one verdict the ledger holds for the question `prompt_id`.

    A verdict counts only if it was asked with today's frozen prompt of that id and answered by
    `MODEL` (design: verification 3; since 2026-09-23 the Opus model, so a verdict of the pilot's
    transport counts no more). Two ok verdicts for one question mean the ledger
    was written by two runs that did not see each other, and the reader refuses to pick one.
    """
    template = dict(PROMPTS.values())[prompt_id]
    out: dict[int, Verdict] = {}
    for entry in lines:
        line = entry.line
        if not entry.ok or line["prompt_id"] != prompt_id:
            continue
        if line["prompt_sha256"] != prompt_sha256(template):
            raise VisionError(
                f"verdict {entry.verdict_id[:12]}: asked with another {prompt_id} than the frozen one"
            )
        if line["model"] != MODEL:
            raise VisionError(
                f"verdict {entry.verdict_id[:12]}: answered by {line['model']!r}, not {MODEL!r}"
            )
        image_id = int(line["image_id"])
        if image_id in out:
            raise VisionError(f"image {image_id}: two ok verdicts for {prompt_id}")
        out[image_id] = Verdict(entry.verdict_id, dict(line["verdict"]), line)
    return out


# ------------------------------------------------------------------------------ running
@dataclass
class RunResult:
    judged: int = 0
    failed: list[str] = field(default_factory=list)
    budget_stop: bool = False
    skipped_done: int = 0

    @property
    def exit_code(self) -> int:
        if self.failed:
            return EXIT_NO_VERDICT
        if self.budget_stop:
            return EXIT_BUDGET
        return EXIT_OK


def run_jobs(
    jobs: Sequence[Job],
    ledger: Ledger,
    judge: Callable[[Job], dict[str, Any]],
    *,
    workers: int,
    budget_usd: float,
) -> RunResult:
    """Judge every job the ledger does not already hold a verdict for.

    At most `workers` judgements are in flight. No new one starts once a judgement failed (the run
    then exits 3) or once the ledger's spend reached `budget_usd` (exit 4); those already in flight
    are finished and written, so no answer is lost.
    """
    result = RunResult()
    done = ledger.done()
    todo = [job for job in jobs if job.key() not in done]
    result.skipped_done = len(jobs) - len(todo)
    stop = threading.Event()
    pending: set[Future[dict[str, Any]]] = set()
    queue = iter(todo)

    crashes: list[BaseException] = []

    def record(future: Future[dict[str, Any]]) -> None:
        error = future.exception()
        if (
            error is not None
        ):  # a bug, not a verdict: stop, keep writing what is in flight, re-raise
            crashes.append(error)
            stop.set()
            return
        entry = ledger.append(future.result())
        result.judged += 1
        if not entry.ok:
            result.failed.append(
                f"image {entry.line['image_id']} ({entry.line['pass']}): {entry.line['error']}"
            )
            stop.set()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            while not stop.is_set() and len(pending) < workers:
                job = next(queue, None)
                if job is None:
                    break
                if ledger.spent_usd >= budget_usd:
                    result.budget_stop = True
                    stop.set()
                    break
                pending.add(pool.submit(judge, job))
            if not pending:
                break
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                record(future)
    if crashes:
        raise crashes[0]
    return result


def export_jobs(
    jobs: Sequence[Job], ledger: Ledger, images: Images, handoff: Path, *, dry_run: bool
) -> tuple[dict[str, int], list[str]]:
    """Hand every job the ledger holds no ok verdict for to the Opus handoff: its filled frozen
    question and the exact JPEG the question is about. `dry_run` resolves every image and writes
    nothing. Returns the counts and every image that could not be found or read."""
    done = ledger.done()
    counts = {"exported": 0, "already": 0, "done": 0}
    missing: list[str] = []
    for job in jobs:
        if job.key() in done:
            counts["done"] += 1
            continue
        prompt = prompt_for(job)
        try:
            path = images.path_for(job.site_id, job.filename)
        except VisionError as exc:
            missing.append(str(exc))
            continue
        if dry_run:
            continue
        try:
            jpeg = vlm_bytes(path)
        except OSError as exc:  # an image that cannot be decoded cannot be handed off
            missing.append(f"{path} cannot be read as an image: {exc}")
            continue
        new = OH.export(
            handoff,
            batch_id=job.stage,
            stage=HANDOFF_STAGE,
            label=job_label(job),
            field=job.pass_,
            prompt=prompt,
            image_name=str(job.image_id),
            image=jpeg,
        )
        counts["exported" if new else "already"] += 1
    return counts, missing


def unanswered(jobs: Sequence[Job], ledger: Ledger, handoff: Path) -> list[str]:
    """Every job without a valid Opus answer to its exact question: the import starts only at none."""
    done = ledger.done()
    problems: list[str] = []
    for job in jobs:
        if job.key() in done:
            continue
        try:
            OH.read_answer(
                handoff,
                batch_id=job.stage,
                stage=HANDOFF_STAGE,
                label=job_label(job),
                prompt=prompt_for(job),
            )
        except OH.HandoffError as exc:
            problems.append(str(exc))
    return problems


def command_export(jobs: Sequence[Job], run_dir: Path, handoff: Path, *, dry_run: bool) -> int:
    """`export`: the questions of every job the run's ledger holds no verdict for, to `handoff`."""
    ledger = Ledger(run_dir / "VERDICTS.jsonl")
    counts, missing = export_jobs(jobs, ledger, Images(), handoff, dry_run=dry_run)
    print(
        f"{'dry run' if dry_run else 'export'}: {len(jobs)} jobs, {counts['done']} already "
        f"in the ledger, {counts['exported']} handed off, {counts['already']} handed off "
        f"before, {len(missing)} image(s) not found or unreadable -> {handoff}"
    )
    for problem in missing[:20]:
        print(f"  {problem}")
    return EXIT_NO_VERDICT if missing else EXIT_OK


def command_import(jobs: Sequence[Job], run_dir: Path, handoff: Path, *, budget_usd: float) -> int:
    """`import`: nothing until every job has a valid Opus answer, then one ledger line per job."""
    ledger = Ledger(run_dir / "VERDICTS.jsonl")
    problems = unanswered(jobs, ledger, handoff)
    if problems:
        print(f"{len(problems)} job(s) have no valid Opus answer in {handoff}; nothing was written")
        for problem in problems[:20]:
            print(f"  {problem}")
        return EXIT_INPUT
    print(f"model={MODEL} handoff={handoff} jobs={len(jobs)}")
    judge = Judge(handoff=handoff, images=Images())
    result = run_jobs(jobs, ledger, judge, workers=1, budget_usd=budget_usd)
    print(
        f"judged {result.judged}, already in the ledger {result.skipped_done}, "
        f"ledger spend ${ledger.spent_usd:.4f}"
    )
    for failure in result.failed:
        print(f"NO VERDICT: {failure}")
    if result.budget_stop:
        print(f"BUDGET STOP: the ledger's spend reached ${budget_usd:.2f}")
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="hand the jobs' questions and images to the handoff")
    answers = sub.add_parser("import", help="write the Opus answers into the run's VERDICTS.jsonl")
    for command in (export, answers):
        command.add_argument("--jobs", required=True)
        command.add_argument("--run-dir", required=True)
        command.add_argument("--handoff", required=True, help="the Opus handoff directory")
    export.add_argument(
        "--dry-run", action="store_true", help="resolve every image and prompt, write nothing"
    )
    answers.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    args = parser.parse_args(argv)

    jobs = read_jobs(Path(args.jobs))
    run_dir, handoff = Path(args.run_dir), Path(args.handoff)
    if args.command == "export":
        return command_export(jobs, run_dir, handoff, dry_run=args.dry_run)
    return command_import(jobs, run_dir, handoff, budget_usd=args.budget_usd)


if __name__ == "__main__":
    raise SystemExit(main())
