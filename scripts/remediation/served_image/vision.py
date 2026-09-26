"""The two Opus vision stages of the served-image lane, through the handoff (`opus_handoff.py`).

**Stage `served-check`** asks, for one served image, whether it depicts its site or an object from
it (`depicts`), shows only the region or the type (`region_or_type`), or shows another site
(`other_site`). Twelve images per batch agent (`CHECK_PER_BATCH`).

**Stage `served-replace`** asks, for every served image that does not depict its site, which
candidate should replace it: the site's other live gallery rows (`G1`...) and the files of its
Wikidata item that the gallery does not hold - its image (P18) and the first `MEMBERS_CAP` files of
its Commons category (P373) in the API's order (`W1`...). The agent gives every candidate a verdict
and picks the best one it called `depicts` - a `G` candidate whenever one depicts the site, because
only a gallery row can become the page's picture - or none. Candidates are packed by image count
(`REPLACE_IMAGES_PER_BATCH`), a site never split.

**Which served images are checked (`--population`).** The design of 2026-09-26 sent only the
images the pre-check could not confirm. Measured before any code relied on it (200-site sample,
docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md): of the 10 served images the fresh acceptance judged
WRONG, the pre-check CONFIRMED 8 - a Wikidata image that is a satellite photo of the whole island,
a view from the hill, a moss photograph and an information panel in the site's own category. So the
default is `all`: every served image is checked; `unconfirmed` is the original design, kept only as
an explicit choice.

**The image bytes** are the ones production serves: a gallery row's file from the offsite copy of
the image tree (`gallery_audit.vision.Images`, the exact-case lookup the gallery audit uses),
accepted only when its size is the row's `file_size_bytes` (all 1,994 live rows of the sample
matched); a thumbnail or a Commons candidate by its URL (`commons.Commons.download`). A thumbnail
whose address serves no picture but names a Commons file Commons still holds is shown through that
file's own rendering, and the question records the repair (`file_behind`): read on 2026-09-26, all
262 Commons `/thumb/` thumbnails ask a width Commons no longer renders (HTTP 400), while the file
behind them stands - 10 of them are the only image their site serves. Every image is
handed over as `pipeline.video.shorts_select.vlm_bytes` (RGB, longest side 1280, JPEG q85), like
the gallery audit's. A file that cannot be found or read stops the export - never a skip.

Each question is recorded when it is exported (`QUESTIONS_CHECK.jsonl`, `QUESTIONS_REPLACE.jsonl` in
the run directory); the import re-renders every prompt from its record and refuses one that is not
the prompt the manifest names, reads every answer through `opus_handoff.read_answer`, parses it with
the same parser `check-answer` runs, and writes `CHECK.jsonl` / `REPLACE.jsonl`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
from gallery_audit.vision import Images, VisionError, pilot  # noqa: E402
from phase3.fetch_stage import write_once  # noqa: E402 - the handoff's one write rule

from pipeline.video.shorts_select import vlm_bytes  # noqa: E402
from served_image import precheck as PC  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image.commons import OK, Commons, Unfetchable  # noqa: E402

STAGE_CHECK = "served-check"
STAGE_REPLACE = "served-replace"
CHECK_PER_BATCH = 12
REPLACE_IMAGES_PER_BATCH = 36
MEMBERS_CAP = 12

DEPICTS = "depicts"
REGION_OR_TYPE = "region_or_type"
OTHER_SITE = "other_site"
VERDICTS = (DEPICTS, REGION_OR_TYPE, OTHER_SITE)
#: A CHECK.jsonl verdict no agent gives: the served thumbnail's address serves no picture
#: (`commons.Unfetchable`). Such an image depicts nothing, so it goes to the replacement stage.
UNFETCHABLE = "unfetchable"
MECHANICAL = "served_image/vision.py (no picture to show)"

ALL = "all"
UNCONFIRMED_ONLY = "unconfirmed"
POPULATIONS = (ALL, UNCONFIRMED_ONLY)

QUESTIONS_CHECK = "QUESTIONS_CHECK.jsonl"
QUESTIONS_REPLACE = "QUESTIONS_REPLACE.jsonl"
EXPORT_CHECK = "EXPORT_CHECK.json"
EXPORT_REPLACE = "EXPORT_REPLACE.json"
CHECK = "CHECK.jsonl"
REPLACE = "REPLACE.jsonl"

GALLERY_CANDIDATE = "gallery"
COMMONS_CANDIDATE = "commons"

MAX_TEXT = 400
#: Where production serves its local files - read only for a thumbnail no image row names.
PRODUCTION_ORIGIN = "https://ancientnerds.com"

_VERDICT_TERMS = """depicts: the picture shows this site itself - its remains, structures, excavation or rock art, or a setting in which the site is recognisable - or an object found at this site. A drawing, plan or reconstruction of this site counts.
region_or_type: the picture shows only the region, island, landscape, town or country around the site, a view from the site, a map, a generic example of the site's type, a portrait, a museum object that is not from this site, an information panel, plants or animals, or anything else in which this site is not what is shown.
other_site: the picture shows another archaeological site or monument - a namesake elsewhere, a neighbour, a comparison."""

CHECK_PROMPT_ID = "served-check-v1"
CHECK_PROMPT = """You check the picture a public page shows as the main image of the archaeological site "{name}" ({site_type}, {country}; latitude {lat}, longitude {lon}).
The site's Wikidata item: {qid}
The picture is the file {image} in the handoff directory. It is served from: {source}

Look at the picture. Where it does not decide the question by itself, research on the web - the picture's Commons file page, the site's Wikipedia article or Wikidata item.

Return JSON only, no prose:
{{"verdict": "depicts" | "region_or_type" | "other_site",
 "shows": "<what the picture shows, at most 20 words>",
 "basis": "<what the verdict rests on - the visible feature, or the page and what it says - at most 40 words>"}}

""" + _VERDICT_TERMS.replace("{", "{{").replace("}", "}}")

REPLACE_PROMPT_ID = "served-replace-v1"
REPLACE_PROMPT = (
    """The main image of the archaeological site "{name}" ({site_type}, {country}; latitude {lat}, longitude {lon}) was judged not to show the site: {verdict} - {shows}
The site's Wikidata item: {qid}
Choose its replacement among these candidates, each a file in the handoff directory:

{candidates}

Look at every candidate. Where a picture alone does not decide it, research on the web.

Return JSON only, no prose:
{{"candidates": {{{labels}}},
 "pick": "<the label of the best candidate you called depicts>" | null,
 "basis": "<what the pick (or null) rests on, at most 40 words>"}}
Every candidate gets one of "depicts", "region_or_type", "other_site":
"""
    + _VERDICT_TERMS.replace("{", "{{").replace("}", "}}")
    + """
pick: a candidate you called depicts that is the best main image of the site - a clear photograph of its remains before a drawing, a plan or an object. If any G candidate depicts the site, pick a G candidate: only the gallery's pictures can become the page's image. Pick a W candidate only when no G candidate depicts the site. null only when you called no candidate depicts."""
)


def prompt_sha256(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


class AnswerError(ST.StateError):
    """An answer that is not in the stage's exact shape. The problem is printed, never repaired."""


# ------------------------------------------------------------------------------ the images
class Pictures:
    """The bytes a question shows: production's files, handed over as `vlm_bytes`."""

    def __init__(self, images: Images, commons: Commons) -> None:
        self.images = images
        self.commons = commons

    def gallery(self, site_id: str, row: Mapping[str, Any]) -> bytes:
        try:
            path = self.images.path_for(site_id, str(row["filename"]))
        except VisionError as exc:
            raise ST.StateError(f"image {row['id']}: {exc} - refresh the offsite copy") from exc
        size = path.stat().st_size
        if size != row["file_size_bytes"]:
            raise ST.StateError(
                f"image {row['id']}: the offsite file {pilot.shard_for(site_id)}/{path.name} has {size} "
                f"bytes, production's row {row['file_size_bytes']} - refresh the offsite copy"
            )
        return vlm_bytes(path)

    def url(self, url: str) -> bytes:
        path = self.commons.download(url)
        try:
            return vlm_bytes(path)
        except OSError as exc:  # PIL's UnidentifiedImageError is an OSError: a page, not a picture
            raise Unfetchable(f"{url} serves no image: {exc}") from exc


def _image_ref(name: str, data: bytes) -> tuple[str, str]:
    """An image's path relative to the handoff and the sha256 of the bytes shown."""
    return OH.image_relpath(name), hashlib.sha256(data).hexdigest()


def write_image(handoff: Path, name: str, data: bytes) -> tuple[str, str]:
    """A candidate's picture beside the handoff's own images, written once (`write_once`, the
    handoff's own rule): a replace question shows several, and a manifest line names one."""
    relpath, digest = _image_ref(name, data)
    write_once(handoff / relpath, data, source=f"the export of {name}")
    return relpath, digest


# ------------------------------------------------------------------------------ the questions
def _site_fields(site: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "site_id": str(site["id"]),
        "name": str(site["name"]),
        "country": site.get("country") or "country unknown",
        "site_type": site.get("site_type") or "type unknown",
        "lat": site["lat"],
        "lon": site["lon"],
    }


@dataclass(frozen=True)
class CheckQuestion:
    batch_id: str
    site_id: str
    name: str
    country: str
    site_type: str
    lat: float
    lon: float
    qid: str | None
    served: Mapping[str, Any]
    source: str
    image: str
    jpeg_sha256: str
    #: A thumbnail shown through its file's own rendering: `{"file_url", "stored_url", "error"}`.
    repair: Mapping[str, str] | None = None

    def prompt(self) -> str:
        return CHECK_PROMPT.format(
            name=self.name,
            site_type=self.site_type,
            country=self.country,
            lat=self.lat,
            lon=self.lon,
            qid=_qid_line(self.qid),
            image=self.image,
            source=self.source,
        )

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["served"] = dict(self.served)
        out["repair"] = None if self.repair is None else dict(self.repair)
        return out


@dataclass(frozen=True)
class Candidate:
    label: str
    kind: str
    image_id: int | None
    file: str | None
    why: str
    url: str | None
    image: str
    jpeg_sha256: str

    def line(self) -> str:
        named = f'Commons file "{self.file}"' if self.file else "no Commons file"
        return f"{self.label}: {self.image} - {self.why}; {named}"


@dataclass(frozen=True)
class ReplaceQuestion:
    batch_id: str
    site_id: str
    name: str
    country: str
    site_type: str
    lat: float
    lon: float
    qid: str | None
    served: Mapping[str, Any]
    verdict: str
    shows: str
    candidates: tuple[Candidate, ...]

    def prompt(self) -> str:
        return REPLACE_PROMPT.format(
            name=self.name,
            site_type=self.site_type,
            country=self.country,
            lat=self.lat,
            lon=self.lon,
            verdict=self.verdict,
            shows=self.shows,
            qid=_qid_line(self.qid),
            candidates="\n".join(c.line() for c in self.candidates),
            labels=", ".join(f'"{c.label}": "..."' for c in self.candidates),
        )

    def labels(self) -> dict[str, Candidate]:
        return {c.label: c for c in self.candidates}

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["served"] = dict(self.served)
        out["candidates"] = [asdict(c) for c in self.candidates]
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> ReplaceQuestion:
        fields = dict(data)
        fields["candidates"] = tuple(Candidate(**c) for c in data["candidates"])
        return cls(**fields)


def _qid_line(qid: str | None) -> str:
    return f"{qid} (https://www.wikidata.org/wiki/{qid})" if qid else "none"


# ------------------------------------------------------------------------------ the answers
def _text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise AnswerError(f"'{key}' must be a non-empty string of at most {MAX_TEXT} characters")
    return value.strip()


def parse_check(text: str) -> dict[str, str]:
    data = pilot.extract_json(text)
    if data is None:
        raise AnswerError("no JSON object in the answer")
    if set(data) != {"verdict", "shows", "basis"}:
        raise AnswerError(f"the answer carries {sorted(data)}, not ['basis', 'shows', 'verdict']")
    if data["verdict"] not in VERDICTS:
        raise AnswerError(f"'verdict' {data['verdict']!r} is not one of {list(VERDICTS)}")
    return {
        "verdict": data["verdict"],
        "shows": _text(data["shows"], "shows"),
        "basis": _text(data["basis"], "basis"),
    }


def parse_replace(text: str, question: ReplaceQuestion) -> dict[str, Any]:
    data = pilot.extract_json(text)
    if data is None:
        raise AnswerError("no JSON object in the answer")
    if set(data) != {"candidates", "pick", "basis"}:
        raise AnswerError(f"the answer carries {sorted(data)}, not ['basis', 'candidates', 'pick']")
    labels = question.labels()
    given = data["candidates"]
    if not isinstance(given, dict) or set(given) != set(labels):
        raise AnswerError(f"'candidates' must give a verdict for exactly {sorted(labels)}")
    for label, verdict in given.items():
        if verdict not in VERDICTS:
            raise AnswerError(f"candidate {label}: {verdict!r} is not one of {list(VERDICTS)}")
    depicting = {label for label, verdict in given.items() if verdict == DEPICTS}
    gallery = {label for label in depicting if labels[label].kind == GALLERY_CANDIDATE}
    pick = data["pick"]
    if pick is None:
        if depicting:
            raise AnswerError(f"pick is null, but {sorted(depicting)} depict the site")
    elif pick not in depicting:
        raise AnswerError(f"pick {pick!r} is not a candidate you called depicts")
    elif gallery and pick not in gallery:
        raise AnswerError(
            f"pick {pick!r} is a W candidate, but G candidates {sorted(gallery)} depict"
        )
    return {"candidates": dict(given), "pick": pick, "basis": _text(data["basis"], "basis")}


# ------------------------------------------------------------------------------ files
def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    if path.exists():
        raise ST.StateError(f"{path} exists - an export or import is written once per run")
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return ST.sha256_text(text)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    if path.exists():
        raise ST.StateError(f"{path} exists - an export or import is written once per run")
    path.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ST.StateError(f"{path} does not exist")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ------------------------------------------------------------------------------ export: check
def file_behind(
    pictures: Pictures, served: Mapping[str, Any], stored_url: str, error: Unfetchable
) -> tuple[dict[str, str], bytes] | None:
    """A served thumbnail whose address serves no picture: the Commons file it names, when Commons
    still holds it - its own URL (the repair) and a rendering of it - else None (no picture). A
    rendering Commons names but does not serve stops the export, like every other missing file."""
    if served["file"] is None:
        return None
    info = pictures.commons.imageinfo([served["file"]])[served["file"]]
    if info["status"] != OK:
        return None
    data = pictures.url(info["render_url"])
    return {"file_url": info["url"], "stored_url": stored_url, "error": str(error)}, data


def export_check(
    run: Path,
    handoff: Path,
    state: ST.State,
    prechecks: Mapping[str, Mapping[str, Any]],
    pictures: Pictures,
    *,
    population: str = ALL,
    per_batch: int = CHECK_PER_BATCH,
) -> dict[str, Any]:
    """Every served image of the population into `handoff`, `per_batch` per batch."""
    if population not in POPULATIONS:
        raise ST.StateError(f"population {population!r} is not one of {list(POPULATIONS)}")
    if not 1 <= per_batch <= CHECK_PER_BATCH:
        raise ST.StateError(f"a check batch holds 1..{CHECK_PER_BATCH} images, not {per_batch}")
    asked = [
        sid
        for sid in state.site_ids()
        if sid in prechecks
        and prechecks[sid]["status"] != PC.NO_IMAGE
        and (population == ALL or prechecks[sid]["status"] == PC.UNCONFIRMED)
    ]
    questions: list[CheckQuestion] = []
    unfetchable: list[dict[str, Any]] = []
    for sid in asked:
        n = len(questions)
        site, check = state.sites[sid], prechecks[sid]
        served = check["served"]
        repair: dict[str, str] | None = None
        if served["image_id"] is not None:
            row = next(r for r in state.rows[sid] if int(r["id"]) == served["image_id"])
            data = pictures.gallery(sid, row)
            source = str(row.get("commons_page_url") or row.get("original_url") or served["url"])
        else:
            # a thumbnail: its address, or - a local file no row of the site names - the file as
            # production serves it
            local = served["url"].startswith("/data/")
            source = PRODUCTION_ORIGIN + served["url"] if local else served["url"]
            try:
                data = pictures.url(source)
            except Unfetchable as exc:
                behind = file_behind(pictures, served, source, exc)
                if behind is None:
                    unfetchable.append({"site_id": sid, "url": source, "error": str(exc)})
                    continue
                repair, data = behind
                source = repair["file_url"]
        image, digest = _image_ref(f"check-{sid}", data)
        question = CheckQuestion(
            batch_id=f"check-{n // per_batch + 1:03d}",
            **_site_fields(site),
            qid=check["qid"],
            served=served,
            source=source,
            image=image,
            jpeg_sha256=digest,
            repair=repair,
        )
        OH.export(
            handoff,
            batch_id=question.batch_id,
            stage=STAGE_CHECK,
            label=sid,
            field="served_image",
            prompt=question.prompt(),
            image_name=f"check-{sid}",
            image=data,
        )
        questions.append(question)
    digest = _write_jsonl(run / QUESTIONS_CHECK, [q.as_json() for q in questions])
    batches: dict[str, list[str]] = {}
    for q in questions:
        batches.setdefault(q.batch_id, []).append(q.site_id)
    summary = {
        "handoff": str(handoff),
        "population": population,
        "prompt_id": CHECK_PROMPT_ID,
        "questions": len(questions),
        "questions_sha256": digest,
        "read_sha256": state.sha256,
        "unfetchable": unfetchable,
        "batches": batches,
    }
    _write_json(run / EXPORT_CHECK, summary)
    return {k: v for k, v in summary.items() if k not in ("batches", "unfetchable")} | {
        "batches": len(batches),
        "unfetchable": len(unfetchable),
    }


# ------------------------------------------------------------------------------ export: replace
def candidates_for(
    state: ST.State,
    precheck: Mapping[str, Any],
    harvest: PC.Harvest,
    commons: Commons,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The candidates of one site, in label order, and the Wikidata files that cannot be shown.

    G: every live row but the failed served one, in the order the page would serve them.
    W: the item's P18 files, then the first `MEMBERS_CAP` files of its P373 categories, that are
    neither a gallery row's file nor the failed served file - each once, in that order.
    """
    sid = str(precheck["site_id"])
    served = precheck["served"]
    rows = ST.live_rows(state.rows.get(sid, ()))
    gallery = [r for r in rows if int(r["id"]) != served.get("image_id")]
    known = {ST.file_of_row(r) for r in rows} | {served.get("file")}
    known.discard(None)
    wanted: list[tuple[str, str]] = []
    qid = precheck["qid"]
    if qid:
        entity = harvest.entity(qid)
        for name in PC.p18_files(entity):
            wanted.append((name, "the site's Wikidata image (P18)"))
        for category in PC.p373_categories(entity):
            for name in commons.members(category, MEMBERS_CAP):
                wanted.append((name, f'in the site\'s Commons category "{category}" (P373)'))
    seen: set[str] = set()
    files: list[tuple[str, str]] = []
    for name, why in wanted:
        if name not in known and name not in seen:
            seen.add(name)
            files.append((name, why))
    info = commons.imageinfo(name for name, _ in files)
    out: list[dict[str, Any]] = [
        {"kind": GALLERY_CANDIDATE, "row": r, "why": "from the site's gallery"} for r in gallery
    ]
    unavailable: list[dict[str, Any]] = []
    for name, why in files:
        if info[name]["status"] != OK:
            unavailable.append({"file": name, "why": why, "status": info[name]["status"]})
            continue
        out.append({"kind": COMMONS_CANDIDATE, "file": name, "why": why, "info": info[name]})
    return out, unavailable


def export_replace(
    run: Path,
    handoff: Path,
    state: ST.State,
    prechecks: Mapping[str, Mapping[str, Any]],
    harvest: PC.Harvest,
    pictures: Pictures,
    *,
    images_per_batch: int = REPLACE_IMAGES_PER_BATCH,
) -> dict[str, Any]:
    """Every served image the check did not call `depicts`, with its candidates."""
    checks = read_jsonl(run / CHECK)
    failed = [c for c in checks if c["verdict"] != DEPICTS]
    questions: list[ReplaceQuestion] = []
    without: list[dict[str, Any]] = []
    batch, in_batch = 1, 0
    for check in failed:
        sid = str(check["site_id"])
        precheck = prechecks[sid]
        found, unavailable = candidates_for(state, precheck, harvest, pictures.commons)
        if not found:
            without.append({"site_id": sid, "unavailable": unavailable})
            continue
        if in_batch and in_batch + len(found) > images_per_batch:
            batch, in_batch = batch + 1, 0
        in_batch += len(found)
        candidates: list[Candidate] = []
        g = w = 0
        for c in found:
            if c["kind"] == GALLERY_CANDIDATE:
                g += 1
                row = c["row"]
                label, name = f"G{g}", f"replace-g-{int(row['id'])}"
                data = pictures.gallery(sid, row)
                image_id, file, url = int(row["id"]), ST.file_of_row(row), None
            else:
                w += 1
                label = f"W{w}"
                name = "replace-w-" + hashlib.sha256(c["file"].encode("utf-8")).hexdigest()[:24]
                data = pictures.url(c["info"]["render_url"])
                image_id, file, url = None, c["file"], c["info"]["url"]
            image, digest = write_image(handoff, name, data)
            candidates.append(
                Candidate(label, c["kind"], image_id, file, c["why"], url, image, digest)
            )
        site = state.sites[sid]
        question = ReplaceQuestion(
            batch_id=f"replace-{batch:03d}",
            **_site_fields(site),
            qid=precheck["qid"],
            served=precheck["served"],
            verdict=check["verdict"],
            shows=check["shows"],
            candidates=tuple(candidates),
        )
        OH.export(
            handoff,
            batch_id=question.batch_id,
            stage=STAGE_REPLACE,
            label=sid,
            field="served_image",
            prompt=question.prompt(),
        )
        questions.append(question)
    digest = _write_jsonl(run / QUESTIONS_REPLACE, [q.as_json() for q in questions])
    batches: dict[str, list[str]] = {}
    for q in questions:
        batches.setdefault(q.batch_id, []).append(q.site_id)
    summary = {
        "handoff": str(handoff),
        "prompt_id": REPLACE_PROMPT_ID,
        "failed": len(failed),
        "questions": len(questions),
        "questions_sha256": digest,
        "check_sha256": ST.file_sha256(run / CHECK),
        "without_candidates": without,
        "batches": batches,
    }
    _write_json(run / EXPORT_REPLACE, summary)
    return {
        "failed": len(failed),
        "questions": len(questions),
        "without_candidates": len(without),
        "batches": len(batches),
    }


# ------------------------------------------------------------------------------ the agent's aids
def _questions(run: Path, stage: str) -> dict[tuple[str, str], Any]:
    if stage == STAGE_CHECK:
        rows = read_jsonl(run / QUESTIONS_CHECK)
        return {(r["batch_id"], r["site_id"]): CheckQuestion(**r) for r in rows}
    rows = read_jsonl(run / QUESTIONS_REPLACE)
    return {(r["batch_id"], r["site_id"]): ReplaceQuestion.from_json(r) for r in rows}


def stage_of(run: Path, handoff: Path) -> str:
    """Which stage's handoff this is, by the export record that names it."""
    for stage, name in ((STAGE_CHECK, EXPORT_CHECK), (STAGE_REPLACE, EXPORT_REPLACE)):
        path = run / name
        if path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            if Path(record["handoff"]).resolve() == handoff.resolve():
                return stage
    raise ST.StateError(f"{handoff} is the handoff of no export of {run}")


def parse(stage: str, question: Any, text: str) -> dict[str, Any]:
    return parse_check(text) if stage == STAGE_CHECK else parse_replace(text, question)


def check_answer(run: Path, handoff: Path, batch_id: str, label: str, text: str) -> str | None:
    """The shape problem of one answer text, or None. Nothing is recorded."""
    stage = stage_of(run, handoff)
    question = _questions(run, stage).get((batch_id, label))
    if question is None:
        raise ST.StateError(f"{batch_id}/{label} is no question of {handoff}")
    try:
        parse(stage, question, text)
    except AnswerError as exc:
        return str(exc)
    return None


BRIEF = """You are Opus agent {batch} of the served-image check ({what}). You answer {count} \
question(s), each about another archaeological site. Answer each one on its own.

Read ONLY your own files: {handoff}/{batch}/MANIFEST.jsonl lists your questions, one JSON line \
each with its "label" and its "prompt_path" (relative to {handoff}). Each prompt names its picture \
file(s) under {handoff}/images/ - open every picture with your Read tool, which shows it to you. \
Open no other file of the repository: no other batch, nothing else under output/ or docs/, no \
database. Where a prompt allows it, research on the web.

For each question:
1. Read {handoff}/<prompt_path> and look at every picture it names.
2. Decide exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is judged):
   ./.venv/Scripts/python.exe scripts/remediation/served_image/run.py check-answer --run-dir {run} \
--handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def _shown(path: Path) -> str:
    return path.resolve().as_posix()


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    stage = stage_of(run, handoff)
    labels = [label for batch, label in _questions(run, stage) if batch == batch_id]
    if not labels:
        raise ST.StateError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return BRIEF.format(
        batch=batch_id,
        what="does each main image show its site?"
        if stage == STAGE_CHECK
        else "which candidate replaces a main image that does not show its site?",
        count=len(labels),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        stage=stage,
    )


# ------------------------------------------------------------------------------ import
def import_stage(run: Path, stage: str) -> dict[str, Any]:
    """Every answer of the stage, validated, re-prompted and parsed, into CHECK/REPLACE.jsonl."""
    record_path = run / (EXPORT_CHECK if stage == STAGE_CHECK else EXPORT_REPLACE)
    if not record_path.is_file():
        raise ST.StateError(f"{record_path} does not exist - export the stage first")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    handoff = Path(record["handoff"])
    questions_file = run / (QUESTIONS_CHECK if stage == STAGE_CHECK else QUESTIONS_REPLACE)
    if ST.file_sha256(questions_file) != record["questions_sha256"]:
        raise ST.StateError(f"{questions_file} is not the file the export recorded")
    validation = OH.validate(handoff)
    if not validation.ok:
        raise ST.StateError(
            f"{handoff} does not validate: {len(validation.missing)} missing, "
            f"{len(validation.stale)} stale, {len(validation.malformed)} malformed, "
            f"{len(validation.orphans)} orphan answers - `opus_handoff.py validate --dir {handoff}`"
        )
    manifest = {(m["batch_id"], m["label"]): m for m in OH.manifest(handoff)}
    out: list[dict[str, Any]] = []
    problems: list[str] = []
    for (batch_id, label), question in _questions(run, stage).items():
        line = manifest.get((batch_id, label))
        prompt = question.prompt()
        if line is None or line["prompt_sha256"] != OH.prompt_sha256(prompt):
            raise ST.StateError(f"{batch_id}/{label}: the manifest does not name this prompt")
        if stage == STAGE_CHECK:
            shown = handoff / question.image
            if hashlib.sha256(shown.read_bytes()).hexdigest() != question.jpeg_sha256:
                raise ST.StateError(f"{shown} is not the picture the question showed")
        else:
            for c in question.candidates:
                shown = handoff / c.image
                if hashlib.sha256(shown.read_bytes()).hexdigest() != c.jpeg_sha256:
                    raise ST.StateError(f"{shown} is not the picture candidate {c.label} showed")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=label, prompt=prompt)
        try:
            parsed = parse(stage, question, answer.text)
        except AnswerError as exc:
            problems.append(f"{batch_id}/{label}: {exc}")
            continue
        base = {
            "site_id": label,
            "batch_id": batch_id,
            "prompt_id": CHECK_PROMPT_ID if stage == STAGE_CHECK else REPLACE_PROMPT_ID,
            "prompt_sha256": line["prompt_sha256"],
            "answered_by": answer.answered_by,
            "answered_at": answer.answered_at,
            "model": OH.OPUS_MODEL,
            "served": dict(question.served),
        }
        if stage == STAGE_CHECK:
            base["repair"] = None if question.repair is None else dict(question.repair)
        else:
            base["candidates_shown"] = [asdict(c) for c in question.candidates]
        out.append(base | parsed)
    if problems:
        raise ST.StateError(
            f"{len(problems)} answer(s) are not in shape - delete them and have them answered "
            "again: " + "; ".join(problems[:5])
        )
    if stage == STAGE_CHECK:
        served = {q.site_id: q.served for q in _questions(run, stage).values()}
        prechecks = PC.load_prechecks(run / "PRECHECK.jsonl")
        for gone in record["unfetchable"]:
            served[gone["site_id"]] = prechecks[gone["site_id"]]["served"]
            out.append(
                {
                    "site_id": gone["site_id"],
                    "batch_id": None,
                    "prompt_id": None,
                    "prompt_sha256": None,
                    "answered_by": MECHANICAL,
                    "answered_at": None,
                    "model": None,
                    "served": dict(served[gone["site_id"]]),
                    "repair": None,
                    "verdict": UNFETCHABLE,
                    "shows": f"no picture: {gone['error']}",
                    "basis": f"{gone['url']} serves no picture ({gone['error']})",
                }
            )
    digest = _write_jsonl(run / (CHECK if stage == STAGE_CHECK else REPLACE), out)
    counts: dict[str, int] = {}
    for row in out:
        key = row["verdict"] if stage == STAGE_CHECK else ("pick" if row["pick"] else "no pick")
        counts[key] = counts.get(key, 0) + 1
    return {"answers": len(out), "sha256": digest, "counts": counts}
