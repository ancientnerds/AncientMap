"""`public/data/card_descriptions.json` for the P5 sitting: pre-render, regenerate, check.

Design entry [6], production_write ("JSON HANDLING", and the P5 sitting's steps d, f and the
acceptance), work item WB-D3. The file is the authoritative copy of `card_stats.card_description`
(`docs/procedures/FIELD_CONTRACT.md`): every API boot upserts each key it carries into `card_stats`
(`api/services/card_descriptions.py`). So the card write and the file must move together:

* **the database first, then the file.** Pushing the file before the journalled write would let the
  boot import write without a journal, and the journalled write would then refuse with matched_0.
* `--prerender` (step d) renders the file the P5 plan will leave behind - from the plan alone, before
  anything is written - so it can be committed locally before the write;
* `--regenerate` (step f) renders the file again from a read-only production SELECT after the write,
  and asserts it is byte for byte the pre-render;
* `--check` (acceptance) asserts the file equals production for every entry and carries no key that
  is not a curated site.

The form: `json.dumps(obj, ensure_ascii=False, indent=2) + '\\n'`, which reproduces today's file byte
for byte (a normal blob, not LFS; LF line ends - a Windows working copy with `core.autocrlf` shows
CRLF, which is normalised on read and never written). The existing key order is kept; a new key (the
7 curated sites without a card today, and the card that exists only in the database) is appended in
UUID order; a cleared card's key is removed, because the importer only upserts keys that are
present. The file's shape does not change: one top-level key, `descriptions`, no provenance map.

Never used for this work: `scripts/import_card_descriptions.py`, `merge_rewrites.py` and the
audit_enrich Wave-4 merge.

    card_json.py --prerender   [--file F] [--plan4 PLAN4.jsonl] [--p5-root logs/_write_apply_p5]
    card_json.py --regenerate  [--file F]      # read-only SELECT; WRITE_EXIT=0 only if identical
    card_json.py --check       [--file F]      # ACCEPT_EXIT=0 only with 0 deviations
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import write_stage as W  # noqa: E402 - the psql seam
from phase3.run import read_jsonl  # noqa: E402

from phase4 import model4 as M  # noqa: E402
from phase4 import write4 as W4  # noqa: E402 - the P5 plan rows and the exit line

REPO = Path(__file__).resolve().parents[3]
CARD_FILE = REPO / "public" / "data" / "card_descriptions.json"
PLAN4 = REPO / "output" / "remediation" / "phase4_runner" / "PLAN4.jsonl"
P5_ROOT = REPO / "output" / "remediation" / "logs" / "_write_apply_p5"
TOP_KEY = "descriptions"


class CardFileRefused(W.WriteRefused):
    """The file or the cards are not what this module will render."""


def canonical(obj: Mapping[str, Any]) -> str:
    """The file's exact text for `obj`."""
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def read_text(path: Path) -> str:
    """The file's text with LF line ends: the committed blob's form (a `core.autocrlf` checkout
    has CRLF on disk; a raw CR never occurs inside a JSON string, which escapes it)."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def read_cards(path: Path) -> dict[str, str]:
    """The file's `descriptions`, in file order. Any other shape is refused."""
    obj = M.parse_json(read_text(path))
    if not isinstance(obj, dict) or list(obj) != [TOP_KEY] or not isinstance(obj[TOP_KEY], dict):
        raise CardFileRefused(f"{path}: expected exactly one top-level key {TOP_KEY!r}")
    cards = obj[TOP_KEY]
    for site_id, text in cards.items():
        if not isinstance(text, str):
            raise CardFileRefused(f"{path}: the card of {site_id} is not a string")
    return dict(cards)


def file_from_cards(current: Mapping[str, str], cards: Mapping[str, str | None]) -> dict[str, Any]:
    """The file object for the curated `cards` (site id -> card, `None` = no card), keeping the key
    order of `current`: existing keys stay where they are (with their new value), a key whose card
    is gone is removed, a new card is appended in UUID order. A key of `current` that is not a
    curated site, and a card longer than the column, are refused."""
    foreign = [site_id for site_id in current if site_id not in cards]
    if foreign:
        raise CardFileRefused(f"{len(foreign)} key(s) are not curated sites: {foreign[:5]}")
    for site_id, card in cards.items():
        uuid.UUID(site_id)
        if card is not None and len(card) > W4.CARD_MAX_CHARS:
            raise CardFileRefused(f"{site_id}: {len(card)} characters; the column holds 200")
    ordered: dict[str, str] = {}
    for site_id in current:
        card = cards[site_id]
        if card is not None:
            ordered[site_id] = card
    for site_id in sorted(set(cards) - set(current)):
        card = cards[site_id]
        if card is not None:
            ordered[site_id] = card
    return {TOP_KEY: ordered}


def curated_cards_sql() -> str:
    """Read-only: every curated site and its card (`null` where it has none)."""
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT u.id::text AS id, c.card_description AS card "
        "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
        f"WHERE u.source_id = {W._sql_text(W.CURATED_SOURCE)}) t;\n"
    )


def production_cards(run: Callable[[str], str]) -> dict[str, str | None]:
    """Every curated site's live card, from one read-only SELECT."""
    return {str(row["id"]): row["card"] for row in W._json_rows(run(curated_cards_sql()))}


def planned_cards(plan4: Path, p5_root: Path) -> dict[str, str | None]:
    """The cards production will hold once the P5 plan is written: every plan site's card as S0 read
    it (`PlanSite.card`), with each P5 row's new value (a card, or `None` for a clear) on top."""
    cards: dict[str, str | None] = {}
    for batch in read_jsonl(plan4):
        for raw in batch["sites"]:
            site = M.PlanSite.from_dict(raw)
            cards[site.site_id] = site.card
    for out in sorted(path for path in p5_root.iterdir() if (path / W4.PLAN_FILE).exists()):
        for row in W4.read_plan(out, group=W4.Group.P5):
            if row.site_id not in cards:
                raise CardFileRefused(f"{out.name}: {row.site_id} is not a site of the plan")
            if cards[row.site_id] != row.old_value:
                raise CardFileRefused(
                    f"{out.name}: {row.site_id}'s P5 row starts from another card than S0 read"
                )
            cards[row.site_id] = row.new_value
    return cards


def deviations(file_cards: Mapping[str, str], live: Mapping[str, str | None]) -> list[str]:
    """What differs between the file and production: a key that is not a curated site, a value
    that is not the live card, a live card the file does not carry."""
    found: list[str] = []
    for site_id, card in file_cards.items():
        if site_id not in live:
            found.append(
                f"NOT CURATED {site_id}: the file carries a key that is not a curated site"
            )
        elif live[site_id] != card:
            found.append(f"DIFFERS {site_id}: the file and production hold different cards")
    for site_id, card in live.items():
        if card is not None and site_id not in file_cards:
            found.append(f"MISSING {site_id}: production holds a card the file does not carry")
    return found


def prerender(path: Path, *, plan4: Path, p5_root: Path) -> str:
    """Render the file the P5 plan leaves behind and write it (LF). Returns the text."""
    text = canonical(file_from_cards(read_cards(path), planned_cards(plan4, p5_root)))
    path.write_text(text, encoding="utf-8", newline="\n")
    return text


def regenerate(path: Path, *, run: Callable[[str], str]) -> tuple[bool, str]:
    """Render the file from production in the current file's key order, and say whether it is byte
    for byte the file on disk (the pre-render). The file is never overwritten here: a difference is
    a finding, written beside it (`<file>.regenerated`) for a person to read."""
    text = canonical(file_from_cards(read_cards(path), production_cards(run)))
    identical = text == read_text(path)
    if not identical:
        path.with_name(path.name + ".regenerated").write_text(text, encoding="utf-8", newline="\n")
    return identical, text


def check(path: Path, *, run: Callable[[str], str]) -> list[str]:
    """The acceptance: the file is in its canonical form and equals production for every entry."""
    found = deviations(read_cards(path), production_cards(run))
    raw = read_text(path)
    if canonical(M.parse_json(raw)) != raw:
        found.append(f"FORM {path}: not json.dumps(obj, ensure_ascii=False, indent=2) + LF")
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="card-json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--prerender", action="store_true")
    mode.add_argument("--regenerate", action="store_true")
    parser.add_argument("--file", default=str(CARD_FILE))
    parser.add_argument("--plan4", default=str(PLAN4))
    parser.add_argument("--p5-root", default=str(P5_ROOT))
    parser.add_argument("--host", default=W.SSH_HOST)
    return parser


def _run(args: argparse.Namespace, runner: W.SqlRunner | None) -> int:
    path = Path(args.file)

    def run(sql: str) -> str:
        return W._exec(runner, sql, host=args.host)

    if args.prerender:
        text = prerender(path, plan4=Path(args.plan4), p5_root=Path(args.p5_root))
        print(f"pre-rendered {path}: {len(M.parse_json(text)[TOP_KEY])} cards")
        return 0
    if args.regenerate:
        identical, _ = regenerate(path, run=run)
        print(
            "REGENERATE: byte-identical with the pre-render"
            if identical
            else f"REGENERATE: differs from the pre-render; see {path.name}.regenerated"
        )
        return 0 if identical else 1
    found = check(path, run=run)
    for line in found:
        print(f"  {line}")
    print(f"RESULT: {len(found)} deviation(s)")
    return 1 if found else 0


def main(argv: list[str] | None = None, *, runner: W.SqlRunner | None = None) -> int:
    """`--check` is the acceptance (`ACCEPT_EXIT=`); the two renderings write (`WRITE_EXIT=`)."""
    tokens = sys.argv[1:] if argv is None else argv
    tag = "ACCEPT" if "--check" in tokens else "WRITE"
    return W4.exit_line(tag, lambda: _run(build_parser().parse_args(argv), runner))


if __name__ == "__main__":
    raise SystemExit(main())
