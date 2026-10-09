"""C3, the adversarial re-check of a hero pick (D17, owner decision D6): Opus 5.5 at high effort.

The page's picture is the one candidate the depicts role called `depicts` with the best quality - and
the one whose mistake the page shows to everybody. Before it is written, a second judge looks at it
alone, with the context the first one had and the first one's verdict: the same question and the same
stricter answer shape as the D15 re-check of the 47 heroes (`served_image.vision.CHECK_PROMPT_V2`,
`parse_check`), so the two re-checks cannot drift apart. An `other_site` verdict must name what the
picture shows and cite its Commons page.

A pick the re-check confirms (`depicts`) is written; a pick it does not confirm is dropped, and the
site's next-best `depicts` candidate is re-checked in the next round (`targets.pick_round`) until a
pick is confirmed or the site has none left. Twelve pictures to an agent
(`served_image.vision.CHECK_PER_BATCH`).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image import vision as V  # noqa: E402

from image_roles import pictures as PX  # noqa: E402
from image_roles import stage as SG  # noqa: E402

PROMPT_ID = V.CHECK_PROMPT_V2_ID
PER_BATCH = V.CHECK_PER_BATCH
#: The earlier stage the context names: the depicts role's verdict is what is re-checked.
EARLIER_STAGE = "image-depicts"


def build_questions(
    picks: Sequence[Mapping[str, Any]],
    read: Callable[[Mapping[str, Any]], bytes],
    *,
    round_number: int,
) -> tuple[list[SG.Question], dict[str, bytes]]:
    """One question per pick, twelve to a batch, batch ids `rck-<round>-NNN` and labels the site ids.

    A pick is `{site_id, name, country, site_type, lat, lon, qid, file, why, note, answered_by,
    description, wikipedia_title, wikipedia_lead, picture_url}`: the site, the candidate the depicts
    role chose, its note and who judged it. `read(pick)` gives the picture at 1280 px."""
    if round_number < 1:
        raise SG.StageError("a round is numbered from 1")
    questions: list[SG.Question] = []
    pictures: dict[str, bytes] = {}
    for start in range(0, len(picks), PER_BATCH):
        batch_id = f"rck-{round_number:02d}-{start // PER_BATCH + 1:03d}"
        for pick in picks[start : start + PER_BATCH]:
            name = PX.image_name("rck", str(pick["site_id"]), str(pick["file"]))
            data = PX.downscale(read(pick), PX.DEPICTS_SIDE)
            image = SG.image_ref(name, data)
            pictures[name] = data
            context = {
                "site_id": str(pick["site_id"]),
                "description": pick.get("description"),
                "wikipedia_title": pick.get("wikipedia_title"),
                "wikipedia_cache_file": pick.get("wikipedia_cache_file"),
                "wikipedia_lead_image": None,
                "owner_link_url": None,
                "owner_link_file": None,
                "earlier_stage": EARLIER_STAGE,
                "earlier_verdict": "depicts",
                "earlier_shows": pick["note"],
                "earlier_answered_by": pick["answered_by"],
            }
            check = V.CheckQuestion(
                batch_id=batch_id,
                site_id=str(pick["site_id"]),
                name=str(pick["name"]),
                country=str(pick.get("country") or "country unknown"),
                site_type=str(pick.get("site_type") or "type unknown"),
                lat=pick["lat"],
                lon=pick["lon"],
                qid=pick.get("qid"),
                served={"image_id": None, "file": pick["file"], "kind": "candidate"},
                source=str(pick.get("picture_url") or pick["file"]),
                image=image.path,
                jpeg_sha256=image.sha256,
                context=context,
            )
            meta = {
                "site_id": str(pick["site_id"]),
                "file": str(pick["file"]),
                "round": round_number,
            }
            questions.append(
                SG.Question(batch_id, str(pick["site_id"]), check.prompt(), meta, (image,))
            )
    return questions, pictures


def parse(meta: Mapping[str, Any], text: str) -> dict[str, Any]:
    """The re-check's verdict, with the stricter shape of an `other_site` (`V.parse_check`)."""
    try:
        return V.parse_check(text, strict=True)
    except V.AnswerError as exc:
        raise SG.AnswerShapeError(str(exc)) from exc


SPEC = SG.Spec(
    name="image-recheck",
    role="adversarial",
    prompt_id=PROMPT_ID,
    questions_file="QUESTIONS_RECHECK.jsonl",
    export_file="EXPORT_RECHECK.json",
    result_file="RECHECK.jsonl",
    parse=parse,
    what="does the chosen candidate really show this site?",
    web=True,
)


def spec_for_round(round_number: int) -> SG.Spec:
    """The stage of one round: its own question, export and result files, so that a second round in
    the same run directory writes nothing the first one wrote."""
    return replace(
        SPEC,
        questions_file=f"QUESTIONS_RECHECK_{round_number:02d}.jsonl",
        export_file=f"EXPORT_RECHECK_{round_number:02d}.json",
        result_file=f"RECHECK_{round_number:02d}.jsonl",
    )


def confirmed(results: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    """`{site id: files the re-check confirmed as depicts}`."""
    out: dict[str, set[str]] = {}
    for row in results:
        if row["verdict"] == V.DEPICTS:
            out.setdefault(row["meta"]["site_id"], set()).add(row["meta"]["file"])
    return out


def rejected(results: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    """`{site id: files the re-check did not confirm}` (region_or_type or other_site)."""
    out: dict[str, set[str]] = {}
    for row in results:
        if row["verdict"] != V.DEPICTS:
            out.setdefault(row["meta"]["site_id"], set()).add(row["meta"]["file"])
    return out
