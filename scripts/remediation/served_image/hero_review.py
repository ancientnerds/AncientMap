"""The review of a hero-moves plan (D48/D49), answered by Opus agents through the handoff.

`hero_moves.py plan` writes `PLANNED.jsonl`, and `hero_moves.py emit --review` writes chunks only for the
sites a review accepted (one line per planned site: `accept` or `veto`, by the owner or a Claude answer
stamp). This module is the review's Claude half - the lane plan of 2026-11-05 asks for "one accept/veto
per PLANNED line answered by Opus agents (vision; a light check that the moved-to image shows the site and
that its licence/author fields are complete per D18)":

    export   one question per planned site into a handoff directory (`opus_handoff.export`): the site,
             the planned new hero as the project's vision JPEG (`image_roles.pictures`, 1280 px), the
             replaced hero beside it when there is one, the credit fields of the READ row (licence,
             licence URL, author) and what the check that chose the row said. Batches of `BATCH`.
    check-answer  the answer check an agent passes to `opus_handoff.py answer --check`.
    import   every answer read back against the prompt rebuilt byte for byte, by the Opus stamp
             (`OH.OPUS_MODEL`; the lane plan names Opus, and owner decision D157 put every answer on
             Opus again) or, for an answer given under owner decision D153, the Fable stamp
             (`REVIEW_MODELS`) and by no other, into `R/REVIEW.jsonl`, the file
             `hero_moves.py emit --review` reads. A missing, malformed or foreign answer refuses the
             whole import: a review is never partial, and nothing is read as an accept.

The answer is one JSON object: `{"decision": "accept" | "veto", "shows": "...", "reason": "..."}`.

    hero_review.py export        --run-dir R --handoff H
    hero_review.py check-answer  --text-file ANSWER.txt
    hero_review.py import        --run-dir R --handoff H
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import licenses as LIC  # noqa: E402
import opus_handoff as OH  # noqa: E402
from phase3.fetch_stage import write_once  # noqa: E402

from served_image import hero_moves as HM  # noqa: E402
from served_image import state as ST  # noqa: E402

STAGE = "hero-review"
BATCH = 8
REVIEW_FILE = "REVIEW.jsonl"
REVIEW_SOURCE = "REVIEW_SOURCE.json"
#: The lane plan of 2026-11-05 names Opus for this review. Under owner decision D153 of 2026-11-10
#: every answer was Fable's, so a review answered then carries the Fable stamp; owner decision D157
#: of 2026-11-11 put every answer on Opus again. Each keeps its stamp and stays valid. No other
#: stamp is the review's.
REVIEW_MODEL = OH.OPUS_MODEL
REVIEW_MODELS = (REVIEW_MODEL, OH.FABLE_MODEL)
DECISIONS = (HM.ACCEPT, HM.VETO)
ANSWER_FIELDS = frozenset({"decision", "shows", "reason"})


class HeroReviewError(HM.HeroMovesError):
    """The review cannot be exported or imported as asked. Nothing was written."""


def _planned(run: Path) -> list[dict[str, Any]]:
    summary = run / HM.SUMMARY
    if not summary.is_file():
        raise HeroReviewError(f"{summary} does not exist - run `hero_moves.py plan` first")
    recorded = json.loads(summary.read_text(encoding="utf-8"))["planned_sha256"]
    if ST.file_sha256(run / HM.PLANNED) != recorded:
        raise HeroReviewError(f"{run / HM.PLANNED} changed after the plan was made")
    planned = HM._jsonl(run / HM.PLANNED)
    if not planned:
        raise HeroReviewError(f"{run / HM.PLANNED} plans no site - there is nothing to review")
    return planned


def batch_of(index: int) -> str:
    return f"review-{index // BATCH + 1:02d}"


def image_names(line: Mapping[str, Any]) -> tuple[str, str | None]:
    """The handoff image names of the planned new hero and of the hero it replaces (None for an
    unflagged site, which has no hero)."""
    from image_roles.pictures import image_name

    sid = str(line["site_id"])
    new = image_name("new", sid, str(line["new_image_id"]))
    old = line.get("old_hero")
    return new, None if old is None else image_name("old", sid, str(old["image_id"]))


def _credit(row: Mapping[str, Any]) -> list[str]:
    demanded = LIC.credit_columns(str(row.get("license") or ""))
    return [
        f"  licence: {row.get('license') or '(none)'}",
        f"  licence URL: {row.get('license_url') or '(none)'}",
        f"  author: {row.get('author') or '(none)'}",
        f"  credit columns the licence demands (D18): {', '.join(demanded) or 'none (free licence)'}",
    ]


def prompt_for(line: Mapping[str, Any], read: HM.Read) -> str:
    """The exact question for one planned site; `import` rebuilds it byte for byte."""
    sid = str(line["site_id"])
    site = read.sites[sid]
    rows = {int(r["id"]): r for r in read.rows.get(sid, ())}
    new_row = rows[int(line["new_image_id"])]
    new_name, old_name = image_names(line)
    check = line["check"]
    said = check.get("shows") or check.get("answer_basis") or "(not recorded)"
    description = str(site.get("description") or "").strip() or "(none)"
    parts = [
        "You review one planned hero-image change on the Ancient Nerds map (owner decisions D48/D49).",
        "The hero is the site page's main picture and the globe thumbnail. A planner chose the new",
        "hero from a Claude check; you decide whether the move may be written.",
        "",
        f"Site: {site['name']} (id {sid})",
        f"Country: {site.get('country') or '(none)'}; type: {site.get('site_type') or '(none)'}; "
        f"lat {site['lat']}, lon {site['lon']}",
        f"Description (start): {description}",
        "",
        f"Why the site is planned: {', '.join(line['problems'])} -> {line['outcome']}",
        "  unflagged = the site's rows carry no hero flag; the row the page already shows is flagged.",
        "  no_author = the current hero's licence demands an author it lacks (D49): the hero moves to",
        "              a fully credited row.",
        "  strip/hotlink = the hero is a thin strip or the globe thumbnail is an unchecked remote link.",
        "",
        f"PLANNED NEW HERO: image {line['new_image_id']}, file {new_row['filename']!r}, "
        f"{new_row.get('width')}x{new_row.get('height')} px",
        f"  picture: {OH.image_relpath(new_name)} (in the handoff directory)",
        *_credit(new_row),
        f"  chosen as: {line['chosen_by']}; the check ({check.get('model')}) said: {said}",
    ]
    old = line.get("old_hero")
    if old is None:
        parts += ["", "CURRENT HERO: none (no row carries the hero flag)."]
    else:
        old_row = rows[int(old["image_id"])]
        assert old_name is not None
        parts += [
            "",
            f"CURRENT HERO (replaced): image {old['image_id']}, file {old_row['filename']!r}",
            f"  picture: {OH.image_relpath(old_name)} (in the handoff directory)",
            *_credit(old_row),
        ]
    parts += [
        "",
        "Open the picture(s) and decide:",
        "accept only when BOTH hold:",
        "  1. The new picture shows this site itself - its remains, its monument, or for a site that",
        "     is an object (a stone, a stela) that object - and can stand as the page's main picture.",
        "     Not another place, not a generic landscape with nothing of the site, not a map or a",
        "     museum find unrelated to the site's own remains.",
        "  2. Its credit is complete per D18: every credit column the licence demands is present and",
        "     plausible (an author that names a person, an organisation or an account - not",
        "     'Unknown', 'Own work' or a URL fragment; a licence URL that matches the licence).",
        "veto otherwise, naming the reason. For a move (D49), do NOT veto only because the current",
        "hero is the nicer picture: the move exists because the current hero lacks its credit.",
        "Veto a move whose new picture is a drawing, a plan or an object photo when the site has",
        "visible remains and the current picture shows them - say so in the reason.",
        "",
        "Answer with exactly one JSON object and nothing else:",
        '{"decision": "accept" | "veto", "shows": "<one sentence: what the new picture shows>", '
        '"reason": "<one or two sentences>"}',
    ]
    return "\n".join(parts) + "\n"


def export(run: Path, handoff: Path, path_of: Callable[[str, str], Path]) -> dict[str, Any]:
    """One question per planned site, its pictures beside it. Idempotent per question
    (`OH.export`); a different prompt for a question already exported is refused there."""
    from image_roles.pictures import DEPICTS_SIDE, picture_bytes

    planned = _planned(run)
    read = HM.load_read(run)
    written = 0
    for index, line in enumerate(planned):
        sid = str(line["site_id"])
        rows = {int(r["id"]): r for r in read.rows.get(sid, ())}
        new_name, old_name = image_names(line)
        new_row = rows[int(line["new_image_id"])]
        new_bytes = picture_bytes(path_of(sid, str(new_row["filename"])), DEPICTS_SIDE)
        if old_name is not None:
            old_row = rows[int(line["old_hero"]["image_id"])]
            old_bytes = picture_bytes(path_of(sid, str(old_row["filename"])), DEPICTS_SIDE)
            write_once(
                handoff / OH.image_relpath(old_name), old_bytes, source=f"the export of {sid}"
            )
        written += OH.export(
            handoff,
            batch_id=batch_of(index),
            stage=STAGE,
            label=sid,
            field="hero",
            prompt=prompt_for(line, read),
            image_name=new_name,
            image=new_bytes,
        )
    return {
        "planned": len(planned),
        "exported": written,
        "batches": sorted({batch_of(i) for i in range(len(planned))}),
        "handoff": str(handoff),
    }


def parse_answer(text: str) -> dict[str, str]:
    """The answer object, or `HeroReviewError` naming why it is none. No fence stripping, no repair."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HeroReviewError(f"the answer is not one JSON object ({exc})") from exc
    if not isinstance(data, dict) or set(data) != ANSWER_FIELDS:
        keys = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise HeroReviewError(f"the answer carries {keys}, not {sorted(ANSWER_FIELDS)}")
    if data["decision"] not in DECISIONS:
        raise HeroReviewError(f"decision {data['decision']!r} is not one of {DECISIONS}")
    for key in ("shows", "reason"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise HeroReviewError(f"{key} is empty or not a string")
    return {k: data[k].strip() for k in sorted(ANSWER_FIELDS)}


def import_review(run: Path, handoff: Path) -> dict[str, Any]:
    """`R/REVIEW.jsonl` from the answers, all or nothing, written once."""
    target = run / REVIEW_FILE
    if target.exists():
        raise HeroReviewError(f"{target} exists - a review is written once and never replaced")
    planned = _planned(run)
    read = HM.load_read(run)
    lines: list[dict[str, Any]] = []
    for index, line in enumerate(planned):
        sid = str(line["site_id"])
        answer = OH.read_answer(
            handoff, batch_id=batch_of(index), stage=STAGE, label=sid, prompt=prompt_for(line, read)
        )
        if answer.model not in REVIEW_MODELS:
            raise HeroReviewError(
                f"{sid}: answered by {answer.model!r}; this review is {REVIEW_MODEL!r}'s "
                f"(or, since D153, {OH.FABLE_MODEL!r}'s)"
            )
        parsed = parse_answer(answer.text)
        lines.append(
            {
                "site_id": sid,
                "new_image_id": int(line["new_image_id"]),
                "decision": parsed["decision"],
                "by": answer.model,
                "reason": parsed["reason"],
                "shows": parsed["shows"],
                "answered_by": answer.answered_by,
                "answered_at": answer.answered_at,
            }
        )
    digest = ST.write_text_once(target, ST.jsonl_text(lines))
    ST.write_text_once(
        run / REVIEW_SOURCE,
        ST.json_text({"handoff": str(handoff.resolve()), "review_sha256": digest}),
    )
    decisions = [entry["decision"] for entry in lines]
    return {
        "review": str(target),
        "sha256": digest,
        "accept": decisions.count(HM.ACCEPT),
        "veto": decisions.count(HM.VETO),
    }


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="served_image/hero_review.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "import"):
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True, type=Path)
        command.add_argument("--handoff", required=True, type=Path)
    sub.add_parser("check-answer").add_argument("--text-file", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "export":
            from gallery_audit.vision import Images

            payload: Any = export(args.run_dir, args.handoff, Images().path_for)
        elif args.command == "import":
            payload = import_review(args.run_dir, args.handoff)
        else:
            payload = parse_answer(args.text_file.read_text(encoding="utf-8"))
    except (ST.StateError, OH.HandoffError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
