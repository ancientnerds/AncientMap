"""C1, the prefilter (D17, owner decision D6): what kind of picture is each candidate, and is it usable?

A candidate search hands over about eleven thousand pictures for the 952 sites; most are maps, scanned
pages, portraits, museum objects on white and photographs of other places. The prefilter takes the
cheap cut before the "shows this site" judge looks at survivors: **Haiku 5.5 at low effort**, the
picture at 640 px, sixty to a question, no site named - the kind of a picture (`KINDS`, the six of
`vlm_pilot.common.EXPECTED_KINDS` the project's vision lane already uses) and one flag, `usable`.

A candidate survives when it is `usable` and of a kind that can show a site: `site_photo`, `artifact`
(a find from the site is a picture of it - the depicts judge decides whether it is), or
`painting_or_artwork` (a drawing or reconstruction of the site counts). A map or document, a picture
of people and anything else is dropped here and never looked at again. The role is calibrated before
its first answer (`image_roles/calibrate.py`: photo versus non-photo agreement and recall of what the
depicts role would call depicts-capable); a role that fails moves up one tier, Haiku to Sonnet.
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

from vlm_pilot.common import EXPECTED_KINDS  # noqa: E402

from image_roles import pictures as PX  # noqa: E402
from image_roles import stage as SG  # noqa: E402

#: Candidates per question (map section 3 C1).
BATCH_SIZE = 60
KINDS = EXPECTED_KINDS
#: The kinds that can show a site; every other kind is dropped.
SURVIVING_KINDS = ("site_photo", "artifact", "painting_or_artwork")

PROMPT_ID = "image-prefilter-v1"
PROMPT = """You sort candidate pictures for pages about archaeological sites. Below are {count} pictures, {first} to {last}, each a file in the handoff directory. Look at every picture and decide two things. Do not judge which site a picture shows: another step does that.

kind - one of: site_photo, artifact, map_or_document, painting_or_artwork, people, other.
site_photo = a site, its structures, remains or landscape photographed on location; artifact = an object in a museum or studio; map_or_document = maps, plans, diagrams, scans, book pages, screenshots; painting_or_artwork = a painting, engraving, print or artistic reconstruction rather than a photograph; people = a person or a crowd is the subject; other = anything else (an animal, a street, a building that is plainly modern, a logo).
usable - true when the picture could be shown as the picture of a page about an archaeological site: a still picture that is sharp and large enough to recognise what it shows, not mostly a watermark, a caption or a border. false otherwise.

Return JSON only, no prose:
{{"items": {{{labels}}}}}
where every picture gets {{"kind": "<one of the six>", "usable": true | false}}.

Pictures:
{pictures}"""


def label_of(number: int) -> str:
    return f"C{number:02d}"


def build_questions(
    candidates: Sequence[Mapping[str, Any]],
    read: Callable[[Mapping[str, Any]], bytes],
    *,
    batch_size: int = BATCH_SIZE,
) -> tuple[list[SG.Question], dict[str, bytes]]:
    """The questions of the prefilter and the pictures they show.

    `candidates` is a list of `{site_id, file, ...}` (a candidate row with its site); `read(c)` gives
    the picture at 1280 px (`vlm_bytes`), which is made 640 px here. Candidates are taken in order,
    `batch_size` to a question; each question's batch id and label are `pre-NNNN`. A candidate is
    identified in the answer by its label and in the result by `(site_id, file)`."""
    if not 1 <= batch_size <= BATCH_SIZE:
        raise SG.StageError(
            f"a prefilter question holds 1..{BATCH_SIZE} pictures, not {batch_size}"
        )
    questions: list[SG.Question] = []
    pictures: dict[str, bytes] = {}
    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start : start + batch_size]
        batch_id = f"pre-{start // batch_size + 1:04d}"
        images: list[SG.Image] = []
        lines: list[str] = []
        items: list[dict[str, str]] = []
        for number, candidate in enumerate(chunk, start=1):
            label = label_of(number)
            name = PX.image_name("pre", str(candidate["site_id"]), str(candidate["file"]))
            data = PX.downscale(read(candidate), PX.PREFILTER_SIDE)
            image = SG.image_ref(name, data)
            pictures[name] = data
            images.append(image)
            lines.append(f"{label}: {image.path}")
            items.append(
                {
                    "label": label,
                    "site_id": str(candidate["site_id"]),
                    "file": str(candidate["file"]),
                }
            )
        prompt = PROMPT.format(
            count=len(chunk),
            first=label_of(1),
            last=label_of(len(chunk)),
            labels=", ".join(f'"{i["label"]}": "..."' for i in items),
            pictures="\n".join(lines),
        )
        questions.append(SG.Question(batch_id, batch_id, prompt, {"items": items}, tuple(images)))
    return questions, pictures


def parse(meta: Mapping[str, Any], text: str) -> dict[str, Any]:
    """`{"items": {label: {"kind", "usable"}}}` for exactly the question's labels."""
    data = SG.json_object(text, frozenset({"items"}))
    wanted = [item["label"] for item in meta["items"]]
    given = data["items"]
    if not isinstance(given, dict) or set(given) != set(wanted):
        raise SG.AnswerShapeError(f"'items' must judge exactly {wanted[0]}..{wanted[-1]}")
    out: dict[str, dict[str, Any]] = {}
    for label in wanted:
        entry = given[label]
        if not isinstance(entry, dict) or set(entry) != {"kind", "usable"}:
            raise SG.AnswerShapeError(f"{label}: must carry exactly 'kind' and 'usable'")
        if entry["kind"] not in KINDS:
            raise SG.AnswerShapeError(
                f"{label}: kind {entry['kind']!r} is not one of {list(KINDS)}"
            )
        if not isinstance(entry["usable"], bool):
            raise SG.AnswerShapeError(f"{label}: 'usable' must be true or false")
        out[label] = {"kind": entry["kind"], "usable": entry["usable"]}
    return {"items": out}


SPEC = SG.Spec(
    name="image-prefilter",
    role="image_prefilter",
    prompt_id=PROMPT_ID,
    questions_file="QUESTIONS_PREFILTER.jsonl",
    export_file="EXPORT_PREFILTER.json",
    result_file="PREFILTER.jsonl",
    parse=parse,
    what="what kind of picture is each candidate, and is it usable?",
)


def survives(entry: Mapping[str, Any]) -> bool:
    """Whether a judged candidate goes on to the depicts role."""
    return bool(entry["usable"]) and entry["kind"] in SURVIVING_KINDS


def judged(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every judged candidate as `{site_id, file, kind, usable, survives, answered_by, model}`."""
    out = []
    for row in results:
        by_label = {item["label"]: item for item in row["meta"]["items"]}
        for label, entry in row["items"].items():
            out.append(
                {
                    "site_id": by_label[label]["site_id"],
                    "file": by_label[label]["file"],
                    "kind": entry["kind"],
                    "usable": entry["usable"],
                    "survives": survives(entry),
                    "answered_by": row["answered_by"],
                    "model": row["model"],
                }
            )
    return out
