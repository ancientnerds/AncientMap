"""C2, "shows this site" (D17, owner decision D6): one verdict and one quality per candidate.

The prefilter's survivors reach the role that decides. **Sonnet 5.5 at medium effort**, the picture at
1280 px, packed by site (`candidate_search.judge.pack`: at most 36 pictures and six sites to an
agent, a site never split). The prompt is English and richer than the German name-and-country one of
2026-10-06: the site's type, the head of its description, its coordinates, the lead of its English
article, where each candidate came from (the route that named it and, for a geotagged file, its
distance from the site's point) and the judge line the first run paid for.

**The judge line** (measured 2026-10-07 on 57 pictures of 8 sites: 1 depicts, 17 region_or_type, 39
other_site): a refusal beats a false `depicts`. A wrong picture on a page costs credibility, a missing
one costs nothing, and **the file name lies** - two Aosta files promised tall towers and showed low
rubble. Three classes recur and are told to the judge by name: a site named for a street (no legible
sign of the site itself is no evidence), museum objects (coins, vases on white ground, no find
context), and a generically named site ("Roman Walls": the name is a type, not a place).

One verdict per candidate - `depicts`, `region_or_type`, `other_site` - and, for a `depicts`, a quality
from 1 to 5 so that the page's picture is the best candidate, not the largest. `write-targets` takes
the best-quality `depicts` of a site (`image_roles/targets.py`); the hero re-check
(`hero_recheck.py`) then looks at that pick again.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from candidate_search import judge as CJ  # noqa: E402

from image_roles import pictures as PX  # noqa: E402
from image_roles import stage as SG  # noqa: E402

DEPICTS, REGION, OTHER = CJ.DEPICTS, CJ.REGION, CJ.OTHER
VERDICTS = (DEPICTS, REGION, OTHER)
QUALITIES = (1, 2, 3, 4, 5)
#: The most candidates of one site that one question holds (`judge.IMAGES_PER_BATCH`).
MAX_PER_SITE = CJ.IMAGES_PER_BATCH

PROMPT_ID = "image-depicts-v1"
JUDGE_LINE = """How to judge:
- The picture decides, never the file name or the title: a name often promises more than the picture shows (low rubble under a name that claims tall towers).
- A refusal is better than a wrong depicts. A wrong picture on a site's page costs credibility; a missing picture costs nothing. When the picture does not make this site recognisable, answer region_or_type and say why in the note.
- A site named for a street or a road: a modern street scene is not evidence. Without a legible sign of this site the answer is region_or_type ("sign not legible"); a legible sign of another place makes it other_site; only a sign or feature of this site itself is evidence for depicts.
- Museum objects (coins, vases, statues photographed on a white or neutral ground) with no find context are not the site: other_site. An inscription that names a mint or a workshop names where the object was made, not where it was found.
- A site whose name is generic (a type such as "Roman Walls" or "Stone Circle") names no place: a picture of one example is not this site unless the picture shows something that identifies it (a sign, a caption, a landmark in view). Otherwise region_or_type.
- A geotag is a hint, not proof: a file geotagged near the point can show a modern building, a view or a neighbouring monument.
- A drawing, plan or reconstruction counts as depicts when it is clearly of this site."""

VERDICT_TERMS = """depicts: the picture shows this site itself - its remains, structures, excavation or rock art, or a setting in which the site is recognisable - or an object found at this site.
region_or_type: the picture shows only the region, the landscape, a town or village around the site, a view from it, a map, a generic example of the site's type, an information panel, plants or animals, or anything else in which this site is not what is shown; also a picture that does not make the site recognisable.
other_site: the picture shows another archaeological site or monument, an object from elsewhere, a person, a coin or a modern scene unrelated to this site."""

PROMPT = """You judge candidate pictures for the archaeological site "{name}" ({site_type}, {country}; latitude {lat}, longitude {lon}).
The site's description begins: {description}
The English Wikipedia article begins: {wikipedia}

Below are {count} candidate pictures, {first} to {last}, each a file in the handoff directory, with the route that named it. For each candidate give one verdict:
{verdict_terms}
For a depicts also give a quality from 1 to 5: 5 = sharp, well exposed, shows the remains as the main subject and suits the main picture of the site's page; 3 = usable; 1 = poor. Any other verdict has no quality (null).

{judge_line}

Return JSON only, no prose:
{{"candidates": {{{labels}}}}}
where every candidate gets {{"verdict": "depicts" | "region_or_type" | "other_site", "quality": 1-5 | null, "note": "<what the picture shows and why, at most 30 words>"}}.

Candidates:
{candidates}"""


def label_of(number: int) -> str:
    return f"C{number}"


def source_line(candidate: Mapping[str, Any]) -> str:
    """Where a candidate came from, for the judge: its route's reason and, for a geotagged file, how
    far from the site's point it lies."""
    line = str(candidate.get("why") or "a Commons search")
    if candidate.get("distance_m") is not None:
        line += f"; geotagged {round(float(candidate['distance_m']))} m from the site's point"
    return line


def build_questions(
    sites: Sequence[Mapping[str, Any]],
    read: Callable[[Mapping[str, Any]], bytes],
    *,
    first_batch: int = 1,
) -> tuple[list[SG.Question], dict[str, bytes], list[dict[str, Any]]]:
    """The questions of the depicts role, the pictures and the candidates left out by name.

    `sites` are `{site_id, name, country, site_type, lat, lon, description, wikipedia_lead,
    candidates: [{file, why, distance_m?, ...}]}` - the survivors of the prefilter. They are packed by
    `judge.pack` (a site never split); a site with more than `MAX_PER_SITE` survivors is judged on the
    first ones and the rest are returned as `left_out`, never dropped silently. `read(c)` gives a
    candidate's picture at 1280 px."""
    batches = CJ.pack(sites)
    questions: list[SG.Question] = []
    pictures: dict[str, bytes] = {}
    left_out: list[dict[str, Any]] = []
    for number, batch in enumerate(batches, start=first_batch):
        batch_id = f"dep-{number:04d}"
        for site in batch["sites"]:
            full = next(s for s in sites if s["site_id"] == site["site_id"])
            for candidate in list(full["candidates"])[len(site["candidates"]) :]:
                left_out.append({"site_id": site["site_id"], "file": candidate["file"]})
            images: list[SG.Image] = []
            lines: list[str] = []
            items: list[dict[str, Any]] = []
            for position, candidate in enumerate(site["candidates"], start=1):
                label = label_of(position)
                name = PX.image_name("dep", str(site["site_id"]), str(candidate["file"]))
                data = PX.downscale(read(candidate), PX.DEPICTS_SIDE)
                image = SG.image_ref(name, data)
                pictures[name] = data
                images.append(image)
                lines.append(f"{label}: {image.path} - {source_line(candidate)}")
                items.append({"label": label, "file": str(candidate["file"])})
            prompt = PROMPT.format(
                name=site["name"],
                site_type=site.get("site_type") or "type unknown",
                country=site.get("country") or "country unknown",
                lat=site["lat"],
                lon=site["lon"],
                description=site.get("description") or "none",
                wikipedia=site.get("wikipedia_lead") or "none (no article)",
                count=len(items),
                first=label_of(1),
                last=label_of(len(items)),
                verdict_terms=VERDICT_TERMS,
                judge_line=JUDGE_LINE,
                labels=", ".join(f'"{i["label"]}": "..."' for i in items),
                candidates="\n".join(lines),
            )
            meta = {"site_id": site["site_id"], "name": site["name"], "items": items}
            questions.append(
                SG.Question(batch_id, str(site["site_id"]), prompt, meta, tuple(images))
            )
    return questions, pictures, left_out


def parse(meta: Mapping[str, Any], text: str) -> dict[str, Any]:
    """`{"candidates": {label: {"verdict", "quality", "note"}}}` for exactly the question's labels.
    A `depicts` carries a quality 1-5, any other verdict none."""
    data = SG.json_object(text, frozenset({"candidates"}))
    wanted = [item["label"] for item in meta["items"]]
    given = data["candidates"]
    if not isinstance(given, dict) or set(given) != set(wanted):
        raise SG.AnswerShapeError(f"'candidates' must judge exactly {wanted}")
    out: dict[str, dict[str, Any]] = {}
    for label in wanted:
        entry = given[label]
        if not isinstance(entry, dict) or set(entry) != {"verdict", "quality", "note"}:
            raise SG.AnswerShapeError(
                f"{label}: must carry exactly 'verdict', 'quality' and 'note'"
            )
        verdict, quality = entry["verdict"], entry["quality"]
        if verdict not in VERDICTS:
            raise SG.AnswerShapeError(
                f"{label}: verdict {verdict!r} is not one of {list(VERDICTS)}"
            )
        if verdict == DEPICTS:
            if isinstance(quality, bool) or quality not in QUALITIES:
                raise SG.AnswerShapeError(f"{label}: a depicts needs a quality of 1 to 5")
        elif quality is not None:
            raise SG.AnswerShapeError(f"{label}: only a depicts has a quality")
        out[label] = {
            "verdict": verdict,
            "quality": quality,
            "note": SG.text_field(entry["note"], f"{label} note"),
        }
    return {"candidates": out}


SPEC = SG.Spec(
    name="image-depicts",
    role="image_depicts",
    prompt_id=PROMPT_ID,
    questions_file="QUESTIONS_DEPICTS.jsonl",
    export_file="EXPORT_DEPICTS.json",
    result_file="DEPICTS.jsonl",
    parse=parse,
    what="does each candidate show this site, and how well?",
)


def verdict_rows(
    results: Sequence[Mapping[str, Any]], sizes: Mapping[tuple[str, str], tuple[int, int]]
) -> list[dict[str, Any]]:
    """The judged candidates as `VERDICTS.jsonl` rows - the shape `candidate_search/judge.py` reads:
    `{site_id, name, file, verdict, quality, note, width, height, answered_by, model}`. `sizes` is
    `{(site id, file): (width, height)}` from the search; a candidate it does not know is an error."""
    rows = []
    for result in results:
        site_id = result["meta"]["site_id"]
        files = {item["label"]: item["file"] for item in result["meta"]["items"]}
        for label, entry in result["candidates"].items():
            file = files[label]
            if (site_id, file) not in sizes:
                raise SG.StageError(f"{site_id}: no size recorded for {file!r}")
            width, height = sizes[(site_id, file)]
            rows.append(
                {
                    "site_id": site_id,
                    "name": result["meta"]["name"],
                    "file": file,
                    "verdict": entry["verdict"],
                    "quality": entry["quality"],
                    "note": entry["note"],
                    "width": width,
                    "height": height,
                    "answered_by": result["answered_by"],
                    "model": result["model"],
                }
            )
    return rows
