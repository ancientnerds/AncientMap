"""S6 - the vision stage: two frozen questions, one transport, an append-only verdict ledger.

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

Transport - the pilot's, imported unchanged
-------------------------------------------
`scripts/remediation/vlm_pilot/ask_vlm.py`: ``ask_once`` (one POST to the opencode gateway),
``extract_json``, ``usage_cost``, ``load_api_key``, ``GATEWAY_URL``, ``MODEL``
(``deepseek-v4-flash-vision-exp``), ``MAX_TOKENS``. The image bytes are
`pipeline.video.shorts_select.vlm_bytes` (RGB, longest side 1280, JPEG q85 - the bytes the pilot
sent), read from the offsite copy through `vlm_pilot/common.py`'s exact-case lookup, main tree
first, then the case-collision tree. Retry policy: ``VLM_ATTEMPTS`` (3) with ``VLM_RETRY_WAIT_S``
(8 s) between attempts. There is no second transport and no fallback model.

Stops, never skips
------------------
* An image whose file cannot be found, or a job with no parseable in-vocabulary verdict after 3
  attempts, is written to the ledger as ``status: failed`` and **stops the run with exit 3**. It is
  never written as ``other`` or ``unknown``: an empty answer that reads as a verdict is the silent
  failure this lane exists to rule out.
* The spend is summed from the ledger (every line carries its cost, failed lines included); once
  it reaches the budget no further call starts and the run exits 4.
* More than ``MAX_WORKERS_UNPROVEN`` workers only when the ledger's first ``RAMP_CALLS`` lines show
  0 failures and a p90 latency under ``RAMP_P90_MS``.

Usage:
    vision.py run --jobs JOBS.jsonl --run-dir DIR [--budget-usd 75] [--workers 4] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_PILOT = ROOT / "scripts" / "remediation" / "vlm_pilot"
for _entry in (ROOT, _PILOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import ask_vlm  # noqa: E402  (the pilot's transport, imported - not copied)
import common as pilot  # noqa: E402  (the pilot's offsite paths and exact-case lookup)
import httpx  # noqa: E402

from pipeline.video.shorts_select import (  # noqa: E402
    VLM_ATTEMPTS,
    VLM_RETRY_WAIT_S,
    vlm_bytes,
)

#: The model and gateway are the pilot's; the ledger records them per line.
MODEL = ask_vlm.MODEL
KINDS: tuple[str, ...] = ask_vlm.EXPECTED_KINDS

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
MAX_WORKERS_UNPROVEN = 4
RAMP_CALLS = 500
RAMP_P90_MS = 40_000

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


def write_jobs(path: Path, jobs: Iterable[Job]) -> str:
    """JOBS.jsonl, one canonical line per job. Returns its sha256."""
    text = "".join(
        json.dumps(job.as_json(), ensure_ascii=False, sort_keys=True) + "\n" for job in jobs
    )
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


Transport = Callable[[Any, str, str, bytes], dict[str, Any]]


@dataclass
class Judge:
    """Everything one judgement needs besides the job."""

    transport: Transport
    client: Any
    session: str
    images: Images
    sleep: Callable[[float], None] = time.sleep
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
            "finish_reason": None,
            "http_status": None,
            "error": None,
            "attempts": 0,
            "attempts_detail": [],
            "usage_totals": {},
            "cost_usd": 0.0,
            "latency_ms": None,
            "session_id": self.session,
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

        costs: list[dict[str, Any]] = []
        for attempt in range(1, VLM_ATTEMPTS + 1):
            line["attempts"] = attempt
            try:
                call = self.transport(self.client, self.session, prompt, jpeg)
            except (httpx.HTTPError, ValueError) as exc:  # a transport failure is data
                line["attempts_detail"].append(
                    {"attempt": attempt, "transport_error": f"{type(exc).__name__}: {exc}"[:400]}
                )
                line["error"] = f"transport: {type(exc).__name__}: {exc}"[:400]
                if attempt < VLM_ATTEMPTS:
                    self.sleep(VLM_RETRY_WAIT_S)
                continue
            usage = call.get("usage") or {}
            if usage:
                costs.append(ask_vlm.usage_cost(usage))
            line["attempts_detail"].append(
                {
                    "attempt": attempt,
                    "http_status": call["http_status"],
                    "latency_ms": call["latency_ms"],
                    "finish_reason": call["finish_reason"],
                    "usage": usage,
                }
            )
            line.update(
                http_status=call["http_status"],
                latency_ms=call["latency_ms"],
                raw_response=call["raw_response"],
                finish_reason=call["finish_reason"],
            )
            if call["http_status"] != 200:
                line["error"] = (
                    f"http {call['http_status']}: {str(call.get('body_text') or '')[:200]}"
                )
            else:
                parsed = ask_vlm.extract_json(call["raw_response"])
                verdict, problem = validate(job.pass_, parsed)
                line["parsed"] = parsed
                if verdict is not None:
                    line.update(status="ok", verdict=verdict, error=None)
                    break
                line["error"] = problem
            if attempt < VLM_ATTEMPTS:
                self.sleep(VLM_RETRY_WAIT_S)
        line["cost_usd"] = round(sum(c["cost_usd"] for c in costs), 8)
        line["usage_totals"] = {
            key: sum(c[key] for c in costs)
            for key in ("prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens")
        }
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
    the pilot's model (design: verification 3). Two ok verdicts for one question mean the ledger
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


def ramp_allows(lines: Sequence[LedgerLine], workers: int) -> tuple[bool, str]:
    """May the run use `workers` workers? Above MAX_WORKERS_UNPROVEN only after the ramp probe."""
    if workers <= MAX_WORKERS_UNPROVEN:
        return True, f"{workers} workers need no ramp proof"
    first = lines[:RAMP_CALLS]
    if len(first) < RAMP_CALLS:
        return False, f"the ramp probe needs {RAMP_CALLS} ledger lines, the ledger has {len(first)}"
    failed = sum(1 for e in first if not e.ok)
    latencies = sorted(int(e.line["latency_ms"] or 0) for e in first)
    p90 = latencies[math.ceil(0.9 * len(latencies)) - 1]
    if failed or p90 >= RAMP_P90_MS:
        return False, f"ramp probe: {failed} failures, p90 {p90} ms (needs 0 and < {RAMP_P90_MS})"
    return True, f"ramp probe passed: 0 failures, p90 {p90} ms over {RAMP_CALLS} calls"


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

    At most `workers` calls are in flight. No new call starts once a judgement failed (the run then
    exits 3) or once the ledger's spend reached `budget_usd` (exit 4); calls already in flight are
    finished and written, so no paid answer is lost.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="judge the jobs of a JOBS.jsonl into a run's VERDICTS.jsonl")
    run.add_argument("--jobs", required=True)
    run.add_argument("--run-dir", required=True)
    run.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    run.add_argument("--workers", type=int, default=MAX_WORKERS_UNPROVEN)
    run.add_argument(
        "--dry-run", action="store_true", help="resolve every image and prompt, call nothing"
    )
    args = parser.parse_args(argv)

    jobs = read_jobs(Path(args.jobs))
    ledger = Ledger(Path(args.run_dir) / "VERDICTS.jsonl")
    allowed, why = ramp_allows(ledger.lines, args.workers)
    print(why)
    if not allowed:
        return EXIT_INPUT
    images = Images()
    if args.dry_run:
        missing = []
        for job in jobs:
            try:
                images.path_for(job.site_id, job.filename)
            except VisionError as exc:
                missing.append(str(exc))
            prompt_for(job)
        todo = [job for job in jobs if job.key() not in ledger.done()]
        print(
            f"dry run: {len(jobs)} jobs, {len(todo)} not yet in the ledger, {len(missing)} image(s) "
            f"not found, ledger spend ${ledger.spent_usd:.4f} of ${args.budget_usd:.2f}"
        )
        for problem in missing[:20]:
            print(f"  {problem}")
        return EXIT_NO_VERDICT if missing else EXIT_OK

    key = ask_vlm.load_api_key(ask_vlm.AUTH_FILE)
    session = str(uuid.uuid4())
    print(
        f"model={MODEL} url={ask_vlm.GATEWAY_URL} jobs={len(jobs)} workers={args.workers} session={session}"
    )
    with httpx.Client(
        timeout=180.0,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    ) as client:
        judge = Judge(transport=ask_vlm.ask_once, client=client, session=session, images=images)
        result = run_jobs(jobs, ledger, judge, workers=args.workers, budget_usd=args.budget_usd)
    print(
        f"judged {result.judged}, already in the ledger {result.skipped_done}, "
        f"ledger spend ${ledger.spent_usd:.4f}"
    )
    for failure in result.failed:
        print(f"NO VERDICT: {failure}")
    if result.budget_stop:
        print(f"BUDGET STOP: the ledger's spend reached ${args.budget_usd:.2f}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
