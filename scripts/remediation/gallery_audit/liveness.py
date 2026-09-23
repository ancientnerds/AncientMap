"""S1 - which Commons files the curated galleries reference are still live, and what happened to
the ones that are not.

Why this lane runs before any other image write: on 2026-09-22 seven of the 46,070 referenced
files were gone, five of them deleted as copyright violations between 2026-09-02 and 09-14 - one
of them the served hero of the Lion Tombs of Dedan. Those images are still public on our pages
under a licence Commons has withdrawn. The 2026-09-20 cache (`cache/commons_imageinfo.json`)
carries no retrieval date, so it cannot say when a file died; this sweep writes a dated store
that can.

What is asked, per referenced file
----------------------------------
1. `prop=imageinfo` in batches of 50 titles (`census.tests.t09_commons_dimensions.BATCH`, the
   anonymous limit), with `redirects=1` and `maxlag=5`, `iiprop=timestamp|size|url`: the latest
   image revision's timestamp, the original's pixel size and its URL.
2. For every title Commons reports as missing: `list=logevents` for that title. The newest
   `delete/delete` or `move/move|move_redir` entry decides the class. Measured 2026-09-23 on the
   seven known dead files: a copyright deletion carries the comment
   `[[COM:L|Copyright violation]]: ...`, a deletion request `per [[Commons:Deletion
   requests/...]]`, and the renamed Roman Forum file a `move` entry with
   `params.suppressredirect: true` and `params.target_title`.
3. For every move target: `prop=imageinfo` again, so an L2 write can require a live target.

The classes
-----------
``live``                    the file exists under the name the row references
``moved-with-redirect``     the name redirects to another file page (the page link still works,
                            the upload URL of the old name does not)
``moved-without-redirect``  missing, and the newest relevant log entry is a move
``deleted-copyvio``         missing, deleted with a comment naming a copyright violation
``deleted-other``           missing, deleted for any other stated reason
``missing-no-log``          missing, and the log carries no deletion or move for the title
``page-without-file``       the File page exists but carries no file revision
``invalid-title``           the API refuses the title itself

Nothing is inferred: a title the answer does not mention, an answer without `query`, an API
error that persists, or a truncated log raise :class:`LivenessError` - a partial sweep must never
look like a finished one.

Politeness: one request at a time, at least ``INTERVAL_S`` seconds apart (the Wikimedia robot
policy the downloader follows, `pipeline/wiki_image_downloader.py` COMMONS_DELAY), the census
User-Agent (`census.fetch.USER_AGENT`), `maxlag=5`. The Fetcher's cache namespace is dated, so a
same-day re-run resumes from the cache and a later day asks again.

Output (``output/remediation/gallery_audit/liveness-<date>/``)
--------------------------------------------------------------
``COMMONS.jsonl``   one line per referenced file (about 46,070), sorted by file name
``NOT_LIVE.jsonl``  the lines whose class is not ``live``
``SUMMARY.json``    counts per class, the sha256 of both JSONL files, the snapshot it read
``RECHECK.json``    (``recheck``) the re-query of every logged line: its title still missing, its
                    log entry unchanged and nothing newer, its move target still live
``chunk-NNN/``      (``chunk``) the L1/L2 rows of ``PLANNED.jsonl`` (``decide.py liveness``) as a
                    chunk of the shared image writer (``chunk_writer.py``)

The write
---------
``chunk`` turns ``PLANNED.jsonl`` into ``chunk_writer.Change`` records, old and new values exactly
as planned (a boolean in its text form), each citing the store line it rests on - a planned row
whose ``liveness_sha256`` names no line of ``NOT_LIVE.jsonl``, or a line that does not state what
the row claims, is refused. It runs only on a store whose ``RECHECK.json`` found nothing. The one
production read (read-only) is the live rows of every touched site: the sites the plan leaves
without a live image are computed from it, and the chunk is emitted only when they are exactly the
sites the operator names with ``--may-empty`` (an image lost from a page is a decision, not a side
effect). The lane journals as ``img-liveness`` under the store's date.

Usage:
    liveness.py sweep [--date YYYY-MM-DD] [--snapshot DIR] [--cache DIR] [--out DIR]
    liveness.py recheck --store DIR [--cache DIR]
    liveness.py chunk --store DIR [--may-empty SITE_ID ...]
    chunk_writer.py <store>/chunk-NNN --check|--rehearse|--apply|--readback|--rehearse-rollback
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
_REMEDIATION = ROOT / "scripts" / "remediation"
for _path in (ROOT, _REMEDIATION, _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import chunk_writer as CW  # noqa: E402
from census.fetch import Fetcher, FetchError  # noqa: E402
from census.snapshot import Snapshot  # noqa: E402
from census.tests.t09_commons_dimensions import (  # noqa: E402
    BATCH,
    COMMONS_API,
    _commons_file_name,
)

from gallery_audit.planned import PlanError, PlannedRow, read_plan  # noqa: E402
from pipeline.commons_urls import commons_page_url_for  # noqa: E402
from pipeline.utils.mediawiki import dereference  # noqa: E402

log = logging.getLogger("gallery_audit.liveness")

OUTPUT = ROOT / "output" / "remediation" / "gallery_audit"
DEFAULT_SNAPSHOT = ROOT / "output" / "remediation" / "snapshot"
DEFAULT_CACHE = ROOT / "output" / "remediation" / "cache"
CURATED_SOURCE = "ancient_nerds"

IIPROP = "timestamp|size|url"
LEPROP = "ids|title|type|timestamp|comment|details"
#: One request per second at most, like the project's own downloader (COMMONS_DELAY = 1.0).
INTERVAL_S = 1.0
#: An API error answer (HTTP 200 with an `error` object, e.g. maxlag) is asked again this often.
MAX_ATTEMPTS = 3
#: How long to wait after an API error before asking again, per attempt (maxlag asks for 5 s).
ERROR_BACKOFF_S = 5.0

LIVE = "live"
MOVED_WITH_REDIRECT = "moved-with-redirect"
MOVED_WITHOUT_REDIRECT = "moved-without-redirect"
DELETED_COPYVIO = "deleted-copyvio"
DELETED_OTHER = "deleted-other"
MISSING_NO_LOG = "missing-no-log"
PAGE_WITHOUT_FILE = "page-without-file"
INVALID_TITLE = "invalid-title"
CLASSES = (
    LIVE,
    MOVED_WITH_REDIRECT,
    MOVED_WITHOUT_REDIRECT,
    DELETED_COPYVIO,
    DELETED_OTHER,
    MISSING_NO_LOG,
    PAGE_WITHOUT_FILE,
    INVALID_TITLE,
)
#: The classes a log entry decides - and the ones `recheck` re-proves.
LOGGED = (MOVED_WITHOUT_REDIRECT, DELETED_COPYVIO, DELETED_OTHER)

#: The comment Commons' deletion tooling writes for a copyright deletion links COM:L with the
#: words "Copyright violation" (measured on all five known cases, 2026-09-23).
COPYVIO_RE = re.compile(r"copyright[ _-]violation|copyvio", re.IGNORECASE)
#: (type, action) of the log entries that can explain a missing file.
RELEVANT_LOG = frozenset({("delete", "delete"), ("move", "move"), ("move", "move_redir")})
#: (type, action) of the log entries that can bring a logged file back or replace it: a restore
#: (after a VRT permission, a normal Commons event), a new upload under the name, an overwrite or a
#: revert - besides the deletions and moves that decide the class. `recheck` reports any of them
#: that is newer than the stored entry.
RECHECK_LOG = RELEVANT_LOG | frozenset(
    {("delete", "restore"), ("upload", "upload"), ("upload", "overwrite"), ("upload", "revert")}
)

#: The fields every store line carries, so a reader never has to guess whether a key is absent
#: because it does not apply or because it was forgotten.
LINE_KEYS = (
    "file",
    "image_ids",
    "class",
    "requested_title",
    "title",
    "pageid",
    "timestamp",
    "width",
    "height",
    "url",
    "invalidreason",
    "retrieved_at",
    "raw_sha256",
    "log",
    "log_retrieved_at",
    "log_raw_sha256",
    "move_target",
)


class LivenessError(RuntimeError):
    """The sweep cannot state a class for every file. Never downgraded to a partial store."""


@dataclass(frozen=True)
class Answer:
    """One parsed API answer and the proof of what was received."""

    body: dict[str, Any]
    raw_sha256: str
    retrieved_at: str


class Pace:
    """At least `interval` seconds between the starts of two requests that reached the network.

    A cache hit costs Commons nothing and is not paced; `mark` is called only for a request that
    was not answered from the cache, with the time it started. `deadline_s` bounds the whole run:
    once it has passed, the next request is refused instead of made, so a sweep cannot run longer
    than it was allowed to - the Fetcher's cache keeps every answer, and a re-run of the same date
    resumes where this one stopped.
    """

    def __init__(
        self,
        interval: float = INTERVAL_S,
        *,
        deadline_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval = interval
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._deadline = None if deadline_s is None else clock() + deadline_s
        self.network_requests = 0

    def wait(self) -> float:
        """Sleep until the next request may start; return that start time."""
        now = self._clock()
        if self._deadline is not None and now > self._deadline:
            raise LivenessError(
                f"the run's deadline has passed after {self.network_requests} network requests - "
                "re-run the same --date to resume from the cache"
            )
        gap = self._next - now
        if gap > 0:
            self._sleep(gap)
            now = self._clock()
        return now

    def mark(self, started: float) -> None:
        self.network_requests += 1
        self._next = max(self._next, started + self.interval)

    def hold(self, seconds: float) -> None:
        """The next request waits at least `seconds` from now (after an API error)."""
        self._next = max(self._next, self._clock() + seconds)


# ------------------------------------------------------------------------------ inputs
def referenced_files(snapshot: Snapshot, *, source: str = CURATED_SOURCE) -> dict[str, list[int]]:
    """Commons file name -> the ids of the curated `wiki_images` rows that reference it.

    The name is T09's (`_commons_file_name`), derived from the row's URLs - one spelling of
    "which Commons file is this row" across the census, the hero lane and this sweep. Rows of a
    site outside `source` are not referenced by a curated gallery and are left out.
    """
    curated = {str(site["id"]) for site in snapshot.sites if site.get("source_id") == source}
    out: dict[str, list[int]] = defaultdict(list)
    for row in snapshot.rows("wiki_images"):
        if str(row["site_id"]) not in curated:
            continue
        name = _commons_file_name(row)
        if name:
            out[name].append(int(row["id"]))
    return {name: sorted(ids) for name, ids in sorted(out.items())}


def imageinfo_params(titles: Sequence[str]) -> dict[str, Any]:
    return {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "imageinfo",
        "iiprop": IIPROP,
        "titles": "|".join(titles),
        "redirects": 1,
        "maxlag": 5,
    }


def logevents_params(title: str) -> dict[str, Any]:
    return {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "list": "logevents",
        "leprop": LEPROP,
        "letitle": title,
        "lelimit": "max",
        "maxlag": 5,
    }


# ------------------------------------------------------------------------------ asking
def ask(fetcher: Fetcher, params: Mapping[str, Any], *, ns: str, pace: Pace) -> Answer:
    """One API answer with its raw sha256, or a raised error - never an empty result.

    Wikimedia reports `maxlag` and other trouble as HTTP 200 with an `error` object, which the
    Fetcher caches like an answer; the retry therefore asks past the cache.
    """
    last = ""
    for attempt in range(MAX_ATTEMPTS):
        started = pace.wait()
        hits = fetcher.stats["cache_hits"]
        payload = fetcher.get_text(COMMONS_API, dict(params), ns=ns, force=attempt > 0)
        if fetcher.stats["cache_hits"] == hits:
            pace.mark(started)
        if payload.get("status") != 200:
            raise LivenessError(f"{COMMONS_API} answered HTTP {payload.get('status')} for {params}")
        text = payload.get("text") or ""
        try:
            body = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LivenessError(
                f"{COMMONS_API} answered something that is not JSON: {exc}"
            ) from exc
        if not isinstance(body, dict):
            raise LivenessError(f"{COMMONS_API} answered a {type(body).__name__}, not an object")
        error = body.get("error")
        if error is None:
            if "query" not in body:
                raise LivenessError(f"{COMMONS_API}: an answer without 'query' for {params}")
            return Answer(
                body=body,
                raw_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                retrieved_at=str(payload.get("fetched_at")),
            )
        last = f"{error.get('code')}: {error.get('info')}"
        log.warning("commons API error (attempt %d/%d): %s", attempt + 1, MAX_ATTEMPTS, last)
        pace.hold(ERROR_BACKOFF_S * (attempt + 1))
    raise LivenessError(f"{COMMONS_API} refused {MAX_ATTEMPTS} times: {last}")


def _empty_line(name: str | None, requested: str) -> dict[str, Any]:
    line: dict[str, Any] = dict.fromkeys(LINE_KEYS)
    line["file"] = name
    line["requested_title"] = requested
    return line


def read_pages(titles: Sequence[str], answer: Answer) -> dict[str, dict[str, Any]]:
    """Every requested title -> its store fields. A title the answer does not mention raises.

    Commons answers under the name it normalised (`_` -> space) and, with `redirects=1`, under the
    redirect target; both chains are applied with `pipeline.utils.mediawiki.dereference` (the
    function T09 reads its answers with), so a moved-with-redirect
    file is recognised by its normalised title differing from the page that answered.
    """
    query = answer.body["query"]
    pages = {page["title"]: page for page in query.get("pages") or [] if page.get("title")}
    normalized = {entry["from"]: entry["to"] for entry in query.get("normalized") or []}
    redirects = {entry["from"]: entry["to"] for entry in query.get("redirects") or []}

    out: dict[str, dict[str, Any]] = {}
    for requested in titles:
        norm = dereference(requested, normalized)
        title = dereference(norm, redirects)
        page = pages.get(title)
        if page is None:
            raise LivenessError(
                f"the imageinfo answer carries no page for {requested!r} (resolved to {title!r})"
            )
        line = _empty_line(None, requested)
        line.update(
            title=title,
            pageid=page.get("pageid"),
            retrieved_at=answer.retrieved_at,
            raw_sha256=answer.raw_sha256,
        )
        if page.get("invalid"):
            line.update({"class": INVALID_TITLE, "invalidreason": page.get("invalidreason")})
        elif page.get("missing"):
            line["class"] = None  # decided by the log (`classify_missing`)
        else:
            info = (page.get("imageinfo") or [None])[0]
            if not info or not info.get("width") or not info.get("height"):
                line["class"] = PAGE_WITHOUT_FILE
            else:
                line.update(
                    {
                        "class": LIVE if norm == title else MOVED_WITH_REDIRECT,
                        "timestamp": info.get("timestamp"),
                        "width": int(info["width"]),
                        "height": int(info["height"]),
                        # The URL carries ?utm_... analytics since 2026 (the same strip as
                        # `pipeline/wiki_image_downloader.py::parse_attribution`).
                        "url": (info.get("url") or "").split("?")[0] or None,
                    }
                )
        out[requested] = line
    return out


def ask_pages(
    fetcher: Fetcher, titles: Sequence[str], *, ns: str, pace: Pace
) -> dict[str, dict[str, Any]]:
    """`read_pages` for one batch, halving it when Commons refuses the URI as too long.

    HTTP 414 is the one refusal a smaller request fixes (T09 split 4 batches of 50 long titles);
    every other failure is raised as it is.
    """
    try:
        return read_pages(titles, ask(fetcher, imageinfo_params(titles), ns=ns, pace=pace))
    except FetchError as exc:
        # `Fetcher.get_text` raises "<url>: HTTP <status>"; the URL itself may contain "414".
        if not str(exc).endswith(": HTTP 414") or len(titles) == 1:
            raise
        mid = len(titles) // 2
        log.warning("HTTP 414 on a %d-title batch, asking in two halves", len(titles))
        out = ask_pages(fetcher, titles[:mid], ns=ns, pace=pace)
        out.update(ask_pages(fetcher, titles[mid:], ns=ns, pace=pace))
        return out


def log_order(entry: Mapping[str, Any]) -> tuple[str, int]:
    """The order of two log entries: their timestamp, then their log id."""
    return (str(entry.get("timestamp") or ""), int(entry.get("logid") or 0))


def latest_relevant(events: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The newest deletion or move of a title, or None when the log holds neither."""
    relevant = [e for e in events if (e.get("type"), e.get("action")) in RELEVANT_LOG]
    if not relevant:
        return None
    return max(relevant, key=log_order)


def classify_log(answer: Answer) -> tuple[str, dict[str, Any] | None]:
    """The class a missing file's log states, and the entry that states it."""
    events = answer.body["query"].get("logevents") or []
    entry = latest_relevant(events)
    if entry is None:
        if "continue" in answer.body:
            raise LivenessError(
                "the log answer is truncated and its first page holds no deletion or move - "
                "refusing to call the file unexplained on half a log"
            )
        return MISSING_NO_LOG, None
    kept = {key: entry.get(key) for key in ("logid", "type", "action", "timestamp", "comment")}
    kept["params"] = dict(entry.get("params") or {})
    if entry["type"] == "delete":
        cls = (
            DELETED_COPYVIO if COPYVIO_RE.search(str(entry.get("comment") or "")) else DELETED_OTHER
        )
        return cls, kept
    if not kept["params"].get("target_title"):
        raise LivenessError(f"a move log entry without a target title: {kept}")
    return MOVED_WITHOUT_REDIRECT, kept


def sweep(
    files: Mapping[str, Sequence[int]], fetcher: Fetcher, *, ns: str, pace: Pace
) -> list[dict[str, Any]]:
    """One store line per referenced file, sorted by file name."""
    names = sorted(files)
    titles = {name: f"File:{name}" for name in names}
    lines: dict[str, dict[str, Any]] = {}
    for start in range(0, len(names), BATCH):
        batch = names[start : start + BATCH]
        answered = ask_pages(fetcher, [titles[n] for n in batch], ns=ns, pace=pace)
        for name in batch:
            line = answered[titles[name]]
            line["file"] = name
            line["image_ids"] = list(files[name])
            lines[name] = line
        if (start // BATCH) % 50 == 0:
            log.info("imageinfo %d/%d files", min(start + BATCH, len(names)), len(names))

    targets: dict[str, list[str]] = defaultdict(list)
    for name in names:
        line = lines[name]
        if line["class"] is not None:
            continue
        answer = ask(fetcher, logevents_params(line["requested_title"]), ns=ns, pace=pace)
        cls, entry = classify_log(answer)
        line.update(
            {
                "class": cls,
                "log": entry,
                "log_retrieved_at": answer.retrieved_at,
                "log_raw_sha256": answer.raw_sha256,
            }
        )
        if cls == MOVED_WITHOUT_REDIRECT:
            assert entry is not None
            targets[str(entry["params"]["target_title"])].append(name)

    ordered_targets = sorted(targets)
    for start in range(0, len(ordered_targets), BATCH):
        batch = ordered_targets[start : start + BATCH]
        answered = ask_pages(fetcher, batch, ns=ns, pace=pace)
        for target in batch:
            got = answered[target]
            summary = {
                key: got[key]
                for key in (
                    "title",
                    "class",
                    "pageid",
                    "timestamp",
                    "width",
                    "height",
                    "url",
                    "retrieved_at",
                    "raw_sha256",
                )
            }
            if summary["class"] is None:
                summary["class"] = "missing"
            for name in targets[target]:
                lines[name]["move_target"] = summary

    out = [lines[name] for name in names]
    unclassified = [line["file"] for line in out if line["class"] not in CLASSES]
    if unclassified:
        raise LivenessError(f"{len(unclassified)} file(s) left without a class: {unclassified[:3]}")
    return out


# ------------------------------------------------------------------------------ the store
def _line_text(line: Mapping[str, Any]) -> str:
    return json.dumps({key: line[key] for key in LINE_KEYS}, ensure_ascii=False, sort_keys=True)


def _write_atomic(path: Path, text: str) -> str:
    """Write `text` via a temporary file and return its sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_store(
    out_dir: Path, lines: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]
) -> dict[str, Any]:
    """COMMONS.jsonl, NOT_LIVE.jsonl and SUMMARY.json. Returns the summary."""
    everything = "".join(_line_text(line) + "\n" for line in lines)
    not_live = "".join(_line_text(line) + "\n" for line in lines if line["class"] != LIVE)
    summary = {
        **meta,
        "files": len(lines),
        "rows": sum(len(line["image_ids"]) for line in lines),
        "classes": dict(sorted(Counter(line["class"] for line in lines).items())),
        "commons_sha256": _write_atomic(out_dir / "COMMONS.jsonl", everything),
        "not_live_sha256": _write_atomic(out_dir / "NOT_LIVE.jsonl", not_live),
    }
    _write_atomic(out_dir / "SUMMARY.json", json.dumps(summary, indent=1, sort_keys=True) + "\n")
    return summary


def load_store(path: Path) -> list[dict[str, Any]]:
    """A store file's lines, refusing one that is damaged or carries an unknown class."""
    if not path.is_file():
        raise LivenessError(f"{path} does not exist")
    out: list[dict[str, Any]] = []
    for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not text.strip():
            continue
        try:
            line = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LivenessError(f"{path}:{lineno}: not JSON ({exc})") from exc
        if not isinstance(line, dict) or set(line) != set(LINE_KEYS):
            raise LivenessError(
                f"{path}:{lineno}: not a liveness line (keys differ from LINE_KEYS)"
            )
        if line["class"] not in CLASSES:
            raise LivenessError(f"{path}:{lineno}: unknown class {line['class']!r}")
        out.append(line)
    return out


def text_sha256(path: Path) -> str:
    """The sha256 SUMMARY.json records for a store file: over its text with LF line ends, so a
    checkout that turned LF into CRLF still proves the same content."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def line_sha256(line: Mapping[str, Any]) -> str:
    """The id a journal row cites for a liveness line: the sha256 of its canonical text."""
    return hashlib.sha256(_line_text(line).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------ recheck
def recheck(
    lines: Sequence[Mapping[str, Any]], fetcher: Fetcher, *, ns: str, pace: Pace
) -> list[str]:
    """Re-query every logged line (design: verification 7). Returns the discrepancies.

    This is the day-of-write pre-flight of the L1/L2 write, so it re-proves the class itself, not
    only the entry that gave it: the title must still be missing (`imageinfo` again - a file
    restored after a VRT permission, or uploaded anew under the name, is live and must not be
    excluded), the stored log entry must still be there with the same id, type, action and
    timestamp, no restore, upload, overwrite, revert, deletion or move may be newer than it, and a
    move target must still be a live file.
    """
    problems: list[str] = []
    targets: dict[str, str] = {}
    titles: dict[str, str] = {}
    for line in lines:
        if line["class"] not in LOGGED:
            continue
        answer = ask(fetcher, logevents_params(line["requested_title"]), ns=ns, pace=pace)
        events = answer.body["query"].get("logevents") or []
        stored = line["log"]
        same = [
            e
            for e in events
            if e.get("logid") == stored["logid"]
            and (e.get("type"), e.get("action"), e.get("timestamp"))
            == (stored["type"], stored["action"], stored["timestamp"])
        ]
        if not same:
            problems.append(f"{line['file']}: log entry {stored['logid']} is no longer in the log")
        newer = sorted(
            (
                e
                for e in events
                if (e.get("type"), e.get("action")) in RECHECK_LOG
                and log_order(e) > log_order(stored)
            ),
            key=log_order,
        )
        for entry in newer:
            problems.append(
                f"{line['file']}: a newer entry {entry.get('logid')} "
                f"({entry.get('type')}/{entry.get('action')}, {entry.get('timestamp')}) "
                f"is in the log after {stored['logid']}"
            )
        titles[str(line["requested_title"])] = str(line["file"])
        if line["class"] == MOVED_WITHOUT_REDIRECT:
            targets[str(stored["params"]["target_title"])] = str(line["file"])
    asked = sorted(titles)
    for start in range(0, len(asked), BATCH):
        batch = asked[start : start + BATCH]
        answered = ask_pages(fetcher, batch, ns=ns, pace=pace)
        for title in batch:
            if answered[title]["class"] is not None:
                problems.append(
                    f"{titles[title]}: Commons answers {title!r} as "
                    f"{answered[title]['class']} again - it is no longer missing"
                )
    ordered = sorted(targets)
    for start in range(0, len(ordered), BATCH):
        batch = ordered[start : start + BATCH]
        answered = ask_pages(fetcher, batch, ns=ns, pace=pace)
        for target in batch:
            if answered[target]["class"] != LIVE:
                problems.append(
                    f"{targets[target]}: move target {target!r} is "
                    f"{answered[target]['class'] or 'missing'}, not live"
                )
    return problems


# ------------------------------------------------------------------------------ the write
#: The store directory `sweep` writes; its date is the write's journal stamp.
STORE_NAME_RE = re.compile(r"liveness-(\d{4}-\d{2}-\d{2})")
#: Where every store lives, as the journal evidence names it (repository-relative).
STORE_HOME = "output/remediation/gallery_audit"
#: The roles `decide.plan_liveness` plans, the rule each belongs to and the columns it writes.
ROLE_RULE = {"exclude": "L1", "hero-drop": "L1", "hero-promote": "L1", "url": "L2"}
ROLE_COLUMNS = {
    "exclude": frozenset({"is_excluded"}),
    "hero-drop": frozenset({"is_hero"}),
    "hero-promote": frozenset({"is_hero"}),
    "url": frozenset({"commons_page_url", "original_url"}),
}
#: The classes a role acts on. A hero-promote row rests on the hero repair's rule, not on a line.
ROLE_CLASSES = {
    "exclude": frozenset({DELETED_COPYVIO, DELETED_OTHER}),
    "hero-drop": frozenset({DELETED_COPYVIO, DELETED_OTHER}),
    "url": frozenset({MOVED_WITHOUT_REDIRECT}),
}
#: (old, new) of the boolean roles, in the text form the chunk writer compares.
ROLE_FLIP = {
    "exclude": ("false", "true"),
    "hero-drop": ("true", "false"),
    "hero-promote": ("false", "true"),
}
CAUSE = {
    DELETED_COPYVIO: "Commons deleted File:{file} as a copyright violation (log {logid}, {when})",
    DELETED_OTHER: "Commons deleted File:{file} for a stated reason other than copyright "
    "(log {logid}, {when})",
    MOVED_WITHOUT_REDIRECT: "Commons renamed File:{file} to {target} without a redirect "
    "(log {logid}, {when})",
}
CONSEQUENCE = {
    "exclude": "the row is excluded",
    "hero-drop": "an excluded row cannot stay the site's hero",
    "url": "{column} points at the live target",
}

LIVE_ROWS_SQL = """SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.is_excluded FROM wiki_images w
   WHERE w.site_id IN ({sites}) ORDER BY w.site_id, w.id
) t;"""


def chunk_lane(store: Path) -> CW.Lane:
    """The journal identity of a store's write: lane `img-liveness`, stamped with the store's date."""
    match = STORE_NAME_RE.fullmatch(store.name)
    if match is None:
        raise LivenessError(f"{store} is not a liveness store directory (liveness-YYYY-MM-DD)")
    return CW.Lane(
        "img-liveness",
        "T09/liveness",
        f"img-liveness-{match.group(1)}",
        "authoritative",
        "img liveness",
    )


def as_text(value: Any) -> str | None:
    """A planned value in the text form `chunk_writer` compares (`column::text`)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None or isinstance(value, str):
        return value
    raise LivenessError(f"a planned value {value!r} is neither a boolean, a text nor NULL")


def require_recheck(store: Path, lines: Sequence[Mapping[str, Any]]) -> None:
    """The store's `RECHECK.json` re-proved every logged line and found nothing."""
    path = store / "RECHECK.json"
    if not path.is_file():
        raise LivenessError(f"{path} does not exist - run `liveness.py recheck` before the chunk")
    report = json.loads(path.read_text(encoding="utf-8"))
    logged = sum(1 for line in lines if line["class"] in LOGGED)
    if report.get("problems") != [] or report.get("checked") != logged:
        raise LivenessError(
            f"{path} is not a clean recheck of this store: checked {report.get('checked')!r} of "
            f"{logged} logged line(s), problems {report.get('problems')!r}"
        )


def _line_for(row: PlannedRow, by_sha: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    """The store line a planned row cites, proven to state what the row claims."""
    evidence = row.evidence
    line = by_sha.get(str(evidence.get("liveness_sha256")))
    if line is None:
        raise LivenessError(
            f"image {row.key} {row.column}: its liveness_sha256 names no line of NOT_LIVE.jsonl"
        )
    log = line["log"] or {}
    claims = {
        "class": (evidence.get("class"), line["class"]),
        "commons_file": (evidence.get("commons_file"), line["file"]),
        "logid": (evidence.get("logid"), log.get("logid")),
        "rule": (evidence.get("rule"), row.rule),
    }
    wrong = sorted(name for name, (said, stated) in claims.items() if said != stated)
    if wrong or row.key not in line["image_ids"]:
        raise LivenessError(
            f"image {row.key} {row.column}: its store line does not state what the row claims "
            f"({', '.join(wrong) or 'the line does not reference the row'})"
        )
    if line["class"] not in ROLE_CLASSES[row.role]:
        raise LivenessError(f"image {row.key}: a {line['class']} line does not allow {row.role}")
    return line


def _url_target(line: Mapping[str, Any], column: str) -> str:
    """The value L2 writes: the store's live move target, spelled as the downloader stores it."""
    target = line["move_target"] or {}
    if target.get("class") != LIVE or not target.get("url"):
        raise LivenessError(f"{line['file']}: the move target is not a live file")
    if column == "original_url":
        return str(target["url"])
    return commons_page_url_for(str(target["title"]))


def plan_changes(
    planned: Sequence[PlannedRow], lines: Sequence[Mapping[str, Any]], store: Path
) -> list[CW.Change]:
    """PLANNED.jsonl as chunk-writer changes: values exactly as planned, reasons from the class,
    evidence the planned pointers plus the store they point into. Refuses what it cannot prove."""
    by_sha = {line_sha256(line): line for line in lines}
    dropped = {row.site_id for row in planned if row.role == "hero-drop"}
    source = f"{STORE_HOME}/{store.name}/NOT_LIVE.jsonl"
    out: list[CW.Change] = []
    for row in planned:
        if ROLE_RULE.get(row.role) != row.rule or row.column not in ROLE_COLUMNS[row.role]:
            raise LivenessError(
                f"image {row.key}: {row.rule}/{row.role} does not write {row.column}"
            )
        if row.table != "wiki_images":
            raise LivenessError(f"image {row.key}: the liveness lane writes wiki_images only")
        old, new = as_text(row.old), as_text(row.new)
        if row.role in ROLE_FLIP and (old, new) != ROLE_FLIP[row.role]:
            raise LivenessError(
                f"image {row.key}: {row.role} is {ROLE_FLIP[row.role]}, not {old!r} -> {new!r}"
            )
        if row.role == "hero-promote":
            if row.site_id not in dropped or not row.evidence.get("replacement_rule"):
                raise LivenessError(
                    f"image {row.key}: a hero promotion without the hero L1 took on its site"
                )
            reason = (
                f"L1 took the site's hero; {row.evidence['replacement_rule']} chose this row "
                f"(tier {row.evidence.get('tier')}, Commons original "
                f"{row.evidence.get('commons_original')})"
            )
            evidence = {"source": "the hero repair's rule over the rows L1 leaves live"}
        else:
            line = _line_for(row, by_sha)
            if row.role == "url" and new != _url_target(line, row.column):
                raise LivenessError(f"image {row.key} {row.column}: {new!r} is not the move target")
            log = line["log"]
            cause = CAUSE[line["class"]].format(
                file=line["file"],
                logid=log["logid"],
                when=log["timestamp"],
                target=(line["move_target"] or {}).get("title"),
            )
            reason = f"{cause}; {CONSEQUENCE[row.role].format(column=row.column)}"
            evidence = {"source": "Commons log, read by the liveness sweep", "store": source}
        out.append(
            CW.Change(
                row.table,
                row.column,
                str(row.key),
                row.site_id,
                old,
                new,
                row.rule,
                reason,
                [{**evidence, **row.evidence}],
            )
        )
    return out


def emptied_sites(changes: Sequence[CW.Change], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The touched sites that have a live image now and none once the exclusions are applied.

    `rows` are every `wiki_images` row of the touched sites as production holds them (id, site,
    is_excluded); a NULL `is_excluded` is live, as everywhere else (`IS NOT TRUE`).
    """
    excluded = {int(c.row_key): c.new_value == "true" for c in changes if c.column == "is_excluded"}
    live: dict[str, list[int]] = defaultdict(list)
    after: dict[str, list[int]] = defaultdict(list)
    seen: dict[int, str] = {}
    for row in rows:
        image_id, site_id = CW.pv._as_int(row["id"], what="wiki_images.id"), str(row["site_id"])
        seen[image_id] = site_id
        if row["is_excluded"] is not True:
            live[site_id].append(image_id)
        if not excluded.get(image_id, row["is_excluded"] is True):
            after[site_id].append(image_id)
    for change in changes:
        if seen.get(int(change.row_key)) != change.site_id:
            raise LivenessError(
                f"image {change.row_key} is not a row of site {change.site_id} in production"
            )
    return sorted(site for site in live if not after[site])


def command_chunk(args: argparse.Namespace) -> int:
    store = Path(args.store)
    lines = load_store(store / "NOT_LIVE.jsonl")
    require_recheck(store, lines)
    lane = chunk_lane(store)
    changes = plan_changes(read_plan(store / "PLANNED.jsonl"), lines, store)
    sites = sorted({c.site_id for c in changes})
    rows = CW.pv.read_rows(
        LIVE_ROWS_SQL.replace("{sites}", ", ".join(f"{CW.L(s)}::uuid" for s in sites))
    )
    emptied = emptied_sites(changes, rows)
    named = sorted(set(args.may_empty))
    if emptied != named:
        raise LivenessError(
            f"the plan leaves {emptied} without a live image, --may-empty names {named}: "
            "every site that loses its last image must be named, and only those"
        )
    chunks = CW.chunk_changes(lane, changes, may_empty=emptied)
    for directory in CW.emit_chunks(store, chunks):
        print(f"{directory}: {len(changes)} row(s) over {len(sites)} site(s), may_empty {emptied}")
    return 0


# ------------------------------------------------------------------------------ CLI
def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def command_sweep(args: argparse.Namespace) -> int:
    snapshot = Snapshot(args.snapshot)
    snapshot.verify()
    files = referenced_files(snapshot)
    if args.limit:
        files = dict(list(files.items())[: args.limit])
    out_dir = Path(args.out) if args.out else OUTPUT / f"liveness-{args.date}"
    ns = f"liveness-{args.date}"
    pace = Pace(
        args.interval, deadline_s=args.deadline_minutes * 60 if args.deadline_minutes else None
    )
    started = _utc_now()
    log.info(
        "%d referenced files, %d rows -> %s", len(files), sum(map(len, files.values())), out_dir
    )
    with Fetcher(args.cache, workers=1) as fetcher:
        lines = sweep(files, fetcher, ns=ns, pace=pace)
        stats = fetcher.stats
    summary = write_store(
        out_dir,
        lines,
        {
            "api": COMMONS_API,
            "iiprop": IIPROP,
            "leprop": LEPROP,
            "batch": BATCH,
            "cache_namespace": ns,
            "snapshot": str(args.snapshot),
            "snapshot_exported_at": snapshot.exported_at(),
            "started_at": started,
            "finished_at": _utc_now(),
            "network_requests": pace.network_requests,
            "cache_hits": stats["cache_hits"],
            "limited_to": args.limit or None,
        },
    )
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def command_recheck(args: argparse.Namespace) -> int:
    store = Path(args.store)
    lines = load_store(store / "NOT_LIVE.jsonl")
    pace = Pace(args.interval)
    ns = f"liveness-recheck-{datetime.now(UTC).strftime('%Y-%m-%dT%H%M%S')}"
    with Fetcher(args.cache, workers=1) as fetcher:
        problems = recheck(lines, fetcher, ns=ns, pace=pace)
    report = {
        "store": str(store),
        "checked": sum(1 for line in lines if line["class"] in LOGGED),
        "cache_namespace": ns,
        "rechecked_at": _utc_now(),
        "problems": problems,
    }
    _write_atomic(store / "RECHECK.json", json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0 if not problems else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sw = sub.add_parser("sweep", help="ask Commons about every referenced file")
    sw.add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    sw.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    sw.add_argument("--cache", default=str(DEFAULT_CACHE))
    sw.add_argument("--out", default=None)
    sw.add_argument("--interval", type=float, default=INTERVAL_S)
    sw.add_argument("--limit", type=int, default=0, help="only the first N files (a probe)")
    sw.add_argument(
        "--deadline-minutes",
        type=float,
        default=0,
        help="stop (resumably) once the run has taken this long; 0 = no deadline",
    )
    rc = sub.add_parser("recheck", help="re-query every logged line of a store")
    rc.add_argument("--store", required=True)
    rc.add_argument("--cache", default=str(DEFAULT_CACHE))
    rc.add_argument("--interval", type=float, default=INTERVAL_S)
    ch = sub.add_parser("chunk", help="the store's PLANNED.jsonl as a chunk of the image writer")
    ch.add_argument("--store", required=True)
    ch.add_argument(
        "--may-empty",
        action="append",
        default=[],
        help="a site the plan may leave without a live image (repeat; exactly those it empties)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs every URL at INFO; a 50-title URL is 5 kB, 922 of them bury the progress lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    commands = {"sweep": command_sweep, "recheck": command_recheck, "chunk": command_chunk}
    try:
        return commands[args.command](args)
    except (LivenessError, FetchError, PlanError, CW.pv.PersistError) as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
