"""D14: merge the duplicates - the waves, the move of their rows, and their retirement.

Owner decision D14 of 2026-10-08: a duplicate is merged - "judged survivor, loser retired
(journalled), images and links moved". `identity/dup_judge.py` produces the judged pairs
(`DUP_DECISIONS.jsonl`); this module turns them into three things, in this order:

1. **`waves`** - the pairs in waves of at most `MAX_SITES` sites (a wave is a lane: its own stamp,
   its own directory, applied once), each wave's `PAIRS.json` in
   `output/remediation/mechanical_dup_merge/<wave>/`. A survivor that is itself merged into another
   record (a chain across two decisions) is followed to the final survivor. `--exclude FILE`
   leaves named losers out, each with its reason, recorded in the wave's `EXCLUDED.json` (O5 of
   2026-11-05: Tarxien and Dodona wait for part B). Nothing is read from production and nothing is
   written to it.
2. **`plan-move`** - lane `dup-merge-move-<wave>` (a row lane, `rowlane.py`): the loser's images and
   content links go to the survivor, a collision stays on the loser, a moved hero that would be a
   second hero is demoted, and the loser's name row becomes an alias of the survivor - in one
   transaction. The plan, its `ROLLBACK.sql` and `PLAN.md` are written from one read-only production
   snapshot and one read-only listing of the wave's image folders on the VPS (`DISK.json`).
3. **`files`** - the pictures of the moved image rows. Every reader serves a row's picture from
   `/data/images/wiki/<site id, 8 hex>/<filename>`, so a row that changes site needs its file in the
   survivor's folder: `FILES.jsonl` (written with the move plan) names each one with its sha256,
   `files --copy` copies them on the VPS (never moves one, never overwrites one), `files --verify`
   reads that each is there, byte for byte, and `files --served` asks the site for each after the
   apply. `apply.py --apply` refuses a move whose files are not in place. A row whose filename the
   survivor's folder uses for another picture (`hero.webp`) stays on the loser, like a URL collision.
4. **`plan-retire`** - lane `dup-merge-retire-<wave>`: the loser is retired as `duplicate_of:<survivor>`
   (`scope_status` and `scope_reason`, `dup-retire`'s cells and survivor checks), planned from a
   **fresh** read taken after the move was applied - its premise counts what the loser holds then. A
   loser whose move is not complete (a movable row left on it, its name not among the survivor's, a
   live image the survivor does not show) is refused, never retired.

An already-retired loser (`duplicate_of:` since the scope lane or `dup-retire`) has a move and no
retirement. The reversal is the opposite order: retire first, then move; a copied file stays in the
survivor's folder, where no row names it after the reversal.

Operator commands (docs in `output/remediation/final-2026-10-08/HANDOVER_IDENTITY_A.md` of the run):

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/mechanical/dup_merge.py waves --date 2026-10-10
    $PY scripts/remediation/mechanical/dup_merge.py plan-move   --wave 2026-10-10 --write
    $PY scripts/remediation/mechanical/dup_merge.py files --wave 2026-10-10 --copy
    $PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-10-10 --emit --rehearse \\
        --probe-guards --apply --rehearse-rollback
    $PY scripts/remediation/mechanical/dup_merge.py files --wave 2026-10-10 --served
    $PY scripts/remediation/mechanical/dup_merge.py plan-retire --wave 2026-10-10 --write
    $PY scripts/remediation/mechanical/apply.py --lane dup-merge-retire-2026-10-10 --emit --rehearse \\
        --probe-guards --apply --rehearse-rollback
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from prod_write import SSH_HOST, SSH_OPTIONS, jsonl_lines  # noqa: E402

from mechanical import plan as P  # noqa: E402
from mechanical.lane import (  # noqa: E402
    DUP_MERGE_MOVE_LANE,
    DUP_RETIRE_METRES,
    DUPLICATE_PREFIX,
    REMEDIATION_ROOT,
    Lane,
    MergePair,
    check_wave,
    dup_merge_move_lane,
    dup_merge_retire_lane,
    load_pairs,
    pairs_path,
    sphere_metres,
    sql_literal,
)
from pipeline.lyra.site_key import site_key_sql  # noqa: E402
from pipeline.sites_html_renderer import site_id_short  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

log = logging.getLogger("mechanical.dup_merge")

#: A wave writes at most this many sites (owner decision D8: every step <= 100 sites). A pair is two.
MAX_SITES = 100
RULE_MOVE = "d14-dup-merge-move"
RULE_RETIRE = "d14-dup-merge-retire"
QID = "wikidata_qid"
ENWIKI = "enwiki_title"
ALIAS = "alias"
READ_FILE = "READ.jsonl"
HELD_FILE = "HELD.jsonl"
#: The decided pairs a `waves --exclude` left out, written beside each wave's `PAIRS.json`.
EXCLUDED_FILE = "EXCLUDED.json"
#: The listing of the wave's image folders a plan was built on, beside its `READ.jsonl`.
DISK_FILE = "DISK.json"
#: The picture of every image row a move plan moves: one line per planned `wiki_images.site_id` cell.
FILES_FILE = "FILES.jsonl"
#: The wiki image tree on the VPS, `<site id, 8 hex>/<filename>` (`site_id_short`), and the URL the
#: site serves it under. Every reader builds a row's path from the id of the row's site
#: (`api/routes/wiki_images.py`, `api/routes/sites_html.py`, `pipeline/static_exporter.py`).
WIKI_TREE = "/var/www/ancientnerds/public/data/images/wiki"
SERVED_ROOT = "https://ancientnerds.com/data/images/wiki"
#: The last record of a folder listing: without it the listing stopped early.
LISTED = "d14-folders-listed"
#: A copy is written under this suffix and renamed when it is whole.
PARTIAL = ".d14-part"
_FOLDER = re.compile(r"^[0-9a-f]{8}\Z")
_SHA256 = re.compile(r"^[0-9a-f]{64}\Z")


# ------------------------------------------------------------------------------------ the waves
@dataclass(frozen=True)
class WavePair:
    """A pair of a wave with the decision that made it: what the plans cite as evidence."""

    loser: str
    survivor: str
    loser_name: str
    survivor_name: str
    metres_limit: int
    already_retired: bool
    cluster_id: str
    why: str
    quotes: tuple[Mapping[str, str], ...]
    limit_evidence: tuple[Mapping[str, str], ...]

    def lane_pair(self) -> MergePair:
        return MergePair(self.loser, self.survivor, self.metres_limit)

    def to_json(self) -> dict[str, Any]:
        return {
            "loser": self.loser,
            "survivor": self.survivor,
            "loser_name": self.loser_name,
            "survivor_name": self.survivor_name,
            "metres_limit": self.metres_limit,
            "already_retired": self.already_retired,
            "cluster_id": self.cluster_id,
            "why": self.why,
            "quotes": [dict(q) for q in self.quotes],
            "limit_evidence": [dict(q) for q in self.limit_evidence],
        }


def decided_pairs(decisions: Sequence[Mapping[str, Any]]) -> list[WavePair]:
    """Every decided MERGE of `DUP_DECISIONS.jsonl`, the final survivor followed through a chain.

    A cluster that is `held` or `pending-recheck` contributes the merges it has decided: the members
    held are listed in the decision, and a decided MERGE does not depend on them (its recheck
    confirmed it). A merge whose survivor is merged away itself points at that record's survivor."""
    merges = [m for r in decisions for m in r["merges"]]
    target_of = {m["site_id"]: m["target"] for m in merges}
    names = {m["site_id"]: m["name"] for m in merges} | {
        m["target"]: m["target_name"] for m in merges
    }
    pairs = []
    for r in decisions:
        for m in r["merges"]:
            final = m["target"]
            for _ in range(len(target_of)):  # a chain is never longer than the merges are many
                if final not in target_of:
                    break
                final = target_of[final]
            else:
                raise P.PlanError(f"{m['site_id']}: the decisions merge it in a circle")
            pairs.append(
                WavePair(
                    loser=m["site_id"],
                    survivor=final,
                    loser_name=m["name"],
                    survivor_name=names[final],
                    metres_limit=int(m.get("metres_limit", DUP_RETIRE_METRES)),
                    already_retired=bool(m.get("already_retired")),
                    cluster_id=r["cluster_id"],
                    why=m["why"],
                    quotes=tuple(m["quotes"]),
                    limit_evidence=tuple(m["limit_evidence"]),
                )
            )
    return sorted(pairs, key=lambda p: (p.cluster_id, p.loser))


def wave_labels(date: str, count: int) -> list[str]:
    """`2026-10-10`, `2026-10-10b`, `2026-10-10c`, ... - the labels the lanes resolve."""
    letters = "bcdefghijklmnopqrstuvwxyz"
    if count > len(letters) + 1:
        raise P.PlanError(f"{count} waves under one date: split the date")
    labels = [date] + [f"{date}{letters[i]}" for i in range(count - 1)]
    for label in labels:
        check_wave(label)
    return labels


def split_waves(pairs: Sequence[WavePair], max_sites: int = MAX_SITES) -> list[list[WavePair]]:
    """Greedy waves of whole pairs, each at most `max_sites` distinct sites; the pairs of one
    survivor stay together (a wave moves onto a survivor once, so its hero and name checks see
    every loser at once)."""
    by_survivor: dict[str, list[WavePair]] = {}
    for p in pairs:
        by_survivor.setdefault(p.survivor, []).append(p)
    waves: list[list[WavePair]] = []
    current: list[WavePair] = []
    sites: set[str] = set()
    for group in by_survivor.values():
        ids = {i for p in group for i in (p.loser, p.survivor)}
        if len(ids) > max_sites:
            raise P.PlanError(
                f"{group[0].survivor}: one survivor has {len(ids)} sites, a wave holds {max_sites}"
            )
        if current and len(sites | ids) > max_sites:
            waves.append(current)
            current, sites = [], set()
        current.extend(group)
        sites |= ids
    if current:
        waves.append(current)
    return waves


def exclude_pairs(
    pairs: Sequence[WavePair], exclusions: Sequence[Mapping[str, Any]]
) -> tuple[list[WavePair], list[dict[str, Any]]]:
    """The pairs without the losers an exclusion names, and the excluded pairs with their reason.

    An exclusion is `{"loser": <site id>, "reason": <why>}` (a decision of the owner or the
    orchestrator, e.g. O5: Tarxien and Dodona wait for part B's survivor swap). An exclusion without
    a reason, a loser named twice, or a loser no decided pair holds is refused: an exclusion that
    excludes nothing is a typo, never a no-op."""
    reasons: dict[str, str] = {}
    for ex in exclusions:
        loser, reason = ex.get("loser"), ex.get("reason")
        if not isinstance(loser, str) or not isinstance(reason, str) or not reason.strip():
            raise P.PlanError(f"an exclusion needs a loser id and a reason: {dict(ex)!r}")
        if loser in reasons:
            raise P.PlanError(f"{loser}: excluded twice")
        reasons[loser] = reason
    unknown = sorted(set(reasons) - {p.loser for p in pairs})
    if unknown:
        raise P.PlanError(
            f"{', '.join(unknown)}: excluded, but no decided pair has it as its loser"
        )
    kept = [p for p in pairs if p.loser not in reasons]
    excluded = [
        {**p.to_json(), "excluded_because": reasons[p.loser]} for p in pairs if p.loser in reasons
    ]
    return kept, excluded


def write_excluded(
    wave: str, excluded: Sequence[Mapping[str, Any]], root: Path | None = None
) -> Path:
    """`EXCLUDED.json` beside the wave's `PAIRS.json`: what the waves of this run left out, and why."""
    path = pairs_path(wave, root).with_name(EXCLUDED_FILE)
    body = {"wave": wave, "excluded": list(excluded)}
    path.write_text(
        json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def write_wave(wave: str, pairs: Sequence[WavePair], root: Path | None = None) -> Path:
    """`PAIRS.json` of one wave. A wave that has one is never planned again."""
    path = pairs_path(wave, root)
    if path.exists():
        raise P.PlanError(f"{path} exists: a wave is planned once - take a new label")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"wave": wave, "pairs": [p.to_json() for p in pairs]},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_wave(wave: str, root: Path | None = None) -> list[WavePair]:
    """The pairs of a wave with their decisions (the lane's own view is `lane.load_pairs`)."""
    path = pairs_path(wave, root)
    load_pairs(wave, root)  # the lane's own validation: distinct losers, no chain
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        WavePair(
            loser=p["loser"],
            survivor=p["survivor"],
            loser_name=p["loser_name"],
            survivor_name=p["survivor_name"],
            metres_limit=int(p.get("metres_limit", DUP_RETIRE_METRES)),
            already_retired=bool(p["already_retired"]),
            cluster_id=p["cluster_id"],
            why=p["why"],
            quotes=tuple(p["quotes"]),
            limit_evidence=tuple(p["limit_evidence"]),
        )
        for p in data["pairs"]
    ]


# ------------------------------------------------------------------------------------ the read
def read_parts(pairs: Sequence[WavePair], move: Lane, retire: Lane) -> tuple[tuple[str, str], ...]:
    """What the plans read, each part one query of one read-only snapshot."""
    ids = P.sql_ids([i for p in pairs for i in (p.loser, p.survivor)])
    losers = P.sql_ids([p.loser for p in pairs])
    site = (
        "SELECT u.id::text AS id, u.name, u.source_id, u.scope_status, u.scope_reason, u.lat, "
        f"u.lon, {site_key_sql('u.name')} AS name_key, ({move.premise_sql}) AS move_premise, "
        f"({retire.premise_sql}) AS retire_premise FROM unified_sites u WHERE u.id IN ({ids}) "
        "ORDER BY u.id"
    )
    ext = (
        "SELECT e.site_id::text AS id, e.kind, e.value FROM site_external_ids e "
        f"WHERE e.site_id IN ({ids}) ORDER BY e.site_id, e.kind, e.value"
    )
    images = (
        "SELECT w.id, w.site_id::text AS site_id, w.original_url, w.filename, w.is_hero, "
        f"w.is_excluded, w.sort_order FROM wiki_images w WHERE w.site_id IN ({ids}) ORDER BY w.id"
    )
    links = (
        "SELECT c.id, c.site_id::text AS site_id, c.content_source, c.content_id "
        f"FROM site_content_links c WHERE c.site_id IN ({ids}) ORDER BY c.id"
    )
    names = (
        "SELECT n.id, n.site_id::text AS site_id, n.name, n.name_normalized, n.name_type "
        f"FROM unified_site_names n WHERE n.site_id IN ({ids}) ORDER BY n.id"
    )
    values = ", ".join(f"({sql_literal(p.loser)}, {sql_literal(p.survivor)})" for p in pairs)
    metres = (
        f"SELECT p.loser AS loser, {sphere_metres('l', 's')} AS metres "
        f"FROM (VALUES {values}) AS p(loser, survivor) "
        "JOIN unified_sites l ON l.id::text = p.loser JOIN unified_sites s ON s.id::text = "
        "p.survivor ORDER BY p.loser"
    )
    onto = (
        "SELECT d.id::text AS id, d.name, d.scope_reason FROM unified_sites d "
        f"WHERE d.source_id = 'ancient_nerds' AND d.scope_status = '{RETIRED}' AND "
        f"d.scope_reason IN ({', '.join(sql_literal(DUPLICATE_PREFIX + p.loser) for p in pairs)}) "
        "ORDER BY d.id"
    )
    journal = (
        "SELECT id, row_pk, column_name, run_stamp, coalesce(test_id, '') AS test_id, old_value, "
        "new_value FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND row_pk IN ({losers}) AND column_name IN ('scope_status', 'scope_reason') ORDER BY id"
    )
    stamps = ", ".join(
        sql_literal(s) for lane in (move, retire) for s in (lane.run_stamp, lane.rollback_run_stamp)
    )
    stamp = (
        "SELECT run_stamp, count(*) AS n FROM remediation_change_log WHERE run_stamp IN "
        f"({stamps}) GROUP BY run_stamp ORDER BY run_stamp"
    )
    return (
        ("site", site),
        ("ext", ext),
        ("image", images),
        ("link", links),
        ("name", names),
        ("metres", metres),
        ("onto", onto),
        ("journal", journal),
        ("stamp", stamp),
    )


@dataclass(frozen=True)
class Read:
    """The production read the plans rest on, and the listing of the wave's image folders
    (`files`: folder -> filename -> sha256, `read_folders`)."""

    sites: Mapping[str, Mapping[str, Any]]
    ext: Mapping[str, tuple[tuple[str, str], ...]]
    images: Mapping[str, tuple[Mapping[str, Any], ...]]
    links: Mapping[str, tuple[Mapping[str, Any], ...]]
    names: Mapping[str, tuple[Mapping[str, Any], ...]]
    metres: Mapping[str, float]
    onto: tuple[Mapping[str, Any], ...]
    journal: Mapping[tuple[str, str], tuple[P.JournalLink, ...]]
    stamps: Mapping[str, int]
    read_at: str
    files: Mapping[str, Mapping[str, str]]


def _by_site(
    rows: Sequence[Mapping[str, Any]], key: str = "site_id"
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        out.setdefault(str(r[key]), []).append(r)
    return {site: tuple(v) for site, v in out.items()}


def parse_read(
    text: str,
    pairs: Sequence[WavePair],
    move: Lane,
    retire: Lane,
    files: Mapping[str, Mapping[str, str]],
) -> Read:
    """The tagged read (`plan.parse_tagged_export` refuses a line of another kind and a read
    without its one snapshot line) with the listing of the wave's image folders."""
    kinds = [kind for kind, _sql in read_parts(pairs, move, retire)]
    rows, read_at = P.parse_tagged_export(text, kinds)
    journal: dict[tuple[str, str], list[P.JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault((str(r["row_pk"]), str(r["column_name"])), []).append(
            P.JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    return Read(
        sites={str(r["id"]): r for r in rows["site"]},
        ext={
            k: tuple((str(x["kind"]), str(x["value"])) for x in v)
            for k, v in _by_site(rows["ext"], "id").items()
        },
        images=_by_site(rows["image"]),
        links=_by_site(rows["link"]),
        names=_by_site(rows["name"]),
        metres={str(r["loser"]): float(r["metres"]) for r in rows["metres"]},
        onto=tuple(rows["onto"]),
        journal={cell: tuple(links) for cell, links in journal.items()},
        stamps={str(r["run_stamp"]): int(r["n"]) for r in rows["stamp"]},
        read_at=read_at,
        files=files,
    )


def write_read(path: Path, pairs: Sequence[WavePair], move: Lane, retire: Lane) -> Path:
    """Read production (read-only, one snapshot) and keep the answer as it came."""
    return P.write_tagged_export(P.tagged_export_script(read_parts(pairs, move, retire)), path)


# ------------------------------------------------------------------------- the image folders
def wave_folders(pairs: Sequence[WavePair]) -> list[str]:
    """The image folder of every loser and survivor of the wave."""
    return sorted({site_id_short(site) for p in pairs for site in (p.loser, p.survivor)})


def list_script(folders: Sequence[str]) -> str:
    """Shell, read-only: the sha256 of every file directly in each of `folders` (a folder that does
    not exist has none), then one closing record. NUL-terminated records (`sha256sum -b -z`): a
    filename may hold blanks, quotes and letters of any script (9,499 of the 49,972 stored ones
    hold more than ASCII letters, digits, blanks and `._(),%-`, read 2026-11-10), and `-z` prints
    a name as it is; `-b` makes the record the same on every platform (` *` before the path)."""
    for name in folders:
        if not _FOLDER.match(name):
            raise P.PlanError(f"{name!r} is not an image folder (8 hex): refusing to list it")
    return (
        f"set -u\ncd {shlex.quote(WIKI_TREE)} || exit 9\n"
        f"for d in {' '.join(folders)}; do\n"
        '  if [ -d "$d" ]; then find "$d" -maxdepth 1 -type f -exec sha256sum -b -z {} + || exit 8; fi\n'
        "done\n"
        f"printf '{LISTED} %s\\0' {len(folders)}\n"
    )


def parse_listing(raw: bytes, folders: Sequence[str]) -> dict[str, dict[str, str]]:
    """`list_script`'s answer as folder -> filename -> sha256. A listing without its closing record,
    or with a record that is no `<sha256> *<folder>/<filename>` of a folder asked for, is refused:
    a listing that stopped early would read as folders with fewer files."""
    records = raw.split(b"\0")
    closing = f"{LISTED} {len(folders)}".encode()
    if len(records) < 2 or records[-1] != b"" or records[-2] != closing:
        raise P.PlanError("the folder listing has no closing record: it did not finish")
    listing: dict[str, dict[str, str]] = {name: {} for name in folders}
    for record in records[:-2]:
        digest, _, path = record.decode("utf-8").partition(" *")
        name, _, filename = path.partition("/")
        if not _SHA256.match(digest) or name not in listing or not filename:
            raise P.PlanError(f"the folder listing holds a record it cannot read: {record[:120]!r}")
        listing[name][filename] = digest
    return listing


def run_on_vps(script: str, *, host: str = SSH_HOST, timeout: int = 900) -> bytes:
    """Run a shell script on the VPS (`bash -s`, the script as UTF-8 bytes on stdin, like
    `prod_write.send`) and return what it printed. A non-zero exit and a timeout are refusals: a
    listing changes nothing, and a copy that stopped is finished by running `files --copy` again
    (it never overwrites, and every file is read back by its sha256)."""
    try:
        proc = subprocess.run(
            shlex.split(f"ssh {SSH_OPTIONS} {host} bash -s"),
            input=script.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise P.PlanError(f"the VPS did not answer within {timeout}s") from exc
    if proc.returncode != 0:
        raise P.PlanError(
            f"the script on the VPS exited {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def read_folders(folders: Sequence[str]) -> dict[str, dict[str, str]]:
    """The image folders as they are on the VPS (read-only): folder -> filename -> sha256."""
    return parse_listing(run_on_vps(list_script(folders)), folders)


# -------------------------------------------------------------------------------- the checks
def _listed(held: Sequence[Mapping[str, Any]]) -> str:
    """The pairs held back, one per line, for the refusal of a plan with nothing left."""
    return "".join(f"\n  - {h['name']} ({h['loser']}): {h['reason']}" for h in held)


class Held(Exception):
    """A pair the plan cannot carry; the message is why. It is listed, never written."""


def _ids(read: Read, site_id: str) -> str:
    return ", ".join(f"{kind}={value}" for kind, value in read.ext.get(site_id, ()))


def move_premise(read: Read, loser: Mapping[str, Any], survivor: Mapping[str, Any]) -> str:
    """What `lane.dup_merge_move_lane`'s premise SQL prints for the loser, from the read's rows."""
    status = "NULL" if loser["scope_status"] is None else loser["scope_status"]
    reason = "NULL" if loser["scope_reason"] is None else loser["scope_reason"]
    return (
        f"{loser['name']} | {_ids(read, loser['id'])} | {status} | {reason} | "
        f"survivor {survivor['name']} | {_ids(read, survivor['id'])}"
    )


def live(image: Mapping[str, Any]) -> bool:
    """A picture a visitor can be served: `is_excluded` is false or NULL."""
    return image["is_excluded"] is not True


def retire_premise(read: Read, loser: Mapping[str, Any], survivor: Mapping[str, Any]) -> str:
    """What `lane.dup_merge_retire_lane`'s premise SQL prints for the loser, from the read's rows."""
    held = f"content links {len(read.links.get(loser['id'], ()))}, images {len(read.images.get(loser['id'], ()))}"
    shown = sum(1 for i in read.images.get(survivor["id"], ()) if live(i))
    return (
        f"{loser['name']} | {held} | {_ids(read, loser['id'])} | survivor {survivor['name']} | "
        f"{_ids(read, survivor['id'])} | live images {shown}"
    )


def check_pair(
    read: Read, pair: WavePair, stamps: Sequence[str]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """`(loser, survivor)` as the decision has them - or the `Held` that says why not."""
    written = {s: n for s, n in read.stamps.items() if n and s in stamps}
    if written:
        raise P.PlanError(
            f"{written} journal row(s) exist for this wave: a lane that has written is never "
            "re-planned - its ROLLBACK.sql may be the only undo"
        )
    loser, survivor = read.sites.get(pair.loser), read.sites.get(pair.survivor)
    for role, row, wanted, site in (
        ("loser", loser, pair.loser_name, pair.loser),
        ("survivor", survivor, pair.survivor_name, pair.survivor),
    ):
        if row is None:
            raise Held(f"the {role} ({site}) is not in unified_sites")
        if row["source_id"] != P.CURATED_SOURCE:
            raise Held(f"the {role} is not a curated site: {row['source_id']!r}")
        if row["name"] != wanted:
            raise Held(f"the {role} is named {row['name']!r}; the decision names {wanted!r}")
    assert loser is not None and survivor is not None
    if survivor["scope_status"] == RETIRED:
        raise Held(f"the survivor is retired ({survivor['scope_reason']!r})")
    if loser["scope_status"] == RETIRED:
        if loser["scope_reason"] != f"{DUPLICATE_PREFIX}{pair.survivor}":
            raise Held(f"the loser is retired for another reason: {loser['scope_reason']!r}")
    elif pair.already_retired:
        raise Held("the decision says the loser is already retired; it is shown")
    onto = [
        str(r["id"]) for r in read.onto if r["scope_reason"] == f"{DUPLICATE_PREFIX}{pair.loser}"
    ]
    if onto:
        raise Held(f"{', '.join(onto)} is retired onto the loser already")
    metres = read.metres.get(pair.loser)
    if metres is None:
        raise Held("the read holds no distance of the pair")
    if metres > pair.metres_limit:
        raise Held(
            f"the two rows are {metres:.1f} m apart; the pair's limit is {pair.metres_limit} m"
        )
    return loser, survivor


def _evidence(
    pair: WavePair, read: Read, loser: Mapping[str, Any], survivor: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    def counts(site: Mapping[str, Any]) -> str:
        sid = site["id"]
        return (
            f"{site['name']!r} ({sid}): {len(read.images.get(sid, ()))} image(s), "
            f"{len(read.links.get(sid, ()))} content link(s)"
        )

    return (
        {
            "source": f"identity/dup_judge.py, cluster {pair.cluster_id}",
            "url": None,
            "quote": f"MERGE {pair.loser_name!r} into {pair.survivor_name!r}: {pair.why}",
        },
        *(
            dict(q) | {"url": q["source"]} if "url" not in q else dict(q)
            for q in (*pair.quotes, *pair.limit_evidence)
        ),
        {
            "source": "production:unified_sites",
            "url": None,
            "quote": f"{counts(loser)}; survivor {counts(survivor)}; "
            f"{read.metres[pair.loser]:.1f} m apart (read {read.read_at})",
        },
    )


def name_taken(read: Read, pair: WavePair, image: Mapping[str, Any]) -> bool:
    """The survivor's folder uses this image's filename for another picture: a row of the survivor
    names it (another URL - the same one is a URL collision), or the folder holds a file of that
    name with other bytes than the loser's. The folder is asked and not only the rows: a folder can
    hold a file no row names (an old `hero.webp` in 4 of the 272 folders read on 2026-11-10). The
    listing holds every folder of the wave (`wave_folders`; a folder that does not exist is listed
    empty): a read without a pair's folders is no read of the wave and fails here. A row whose own
    file is not in the loser's folder is none the survivor's folder took the name of."""
    name = image["filename"]
    if any(i["filename"] == name for i in read.images.get(pair.survivor, ())):
        return True
    own = read.files[site_id_short(pair.loser)].get(name)
    there = read.files[site_id_short(pair.survivor)].get(name)
    return own is not None and there is not None and there != own


# -------------------------------------------------------------------------------- the move plan
@dataclass(frozen=True)
class MoveCell:
    """One planned cell of the move, before it is a `plan.Verdict`."""

    site_id: str
    table: str
    row_id: str
    column: str
    old: str
    new: str
    note: str


@dataclass
class Taken:
    """What the pairs of a wave planned before this one already move onto one survivor: a second
    loser of the same survivor meets them as collisions (an image URL, an image filename, a content
    link, a name key) and as a hero the survivor has by then. Only a pair that is planned in full
    adds to it."""

    urls: set[str] = field(default_factory=set)
    filenames: set[str] = field(default_factory=set)
    links: set[tuple[str, str]] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    hero: bool = False


def move_cells(
    read: Read, pair: WavePair, taken: Taken | None = None
) -> tuple[list[MoveCell], dict[str, int]]:
    """The cells that move one loser's rows onto its survivor, and the counts of what they do.

    * an image whose `original_url` the survivor holds stays on the loser (the unique key
      `(site_id, original_url)`); a content link whose `(content_source, content_id)` the survivor
      holds likewise;
    * an image whose filename the survivor's folder uses for another picture stays on the loser
      too (`name_taken`): the row is served from `<folder of its site>/<filename>`, no unique key
      covers the filename, and moved it would show the survivor's picture under its own credit. An
      image whose file is not in the loser's folder is `Held`: there is no picture to carry;
    * a moved live hero is demoted to a plain image when the survivor already has a live hero, and
      all but one when the survivor has none (`is_hero` true -> false, the first by `sort_order`
      and id stays) - at most one live hero per site is the invariant the lane proves;
    * the loser's name row (the row whose key is the key of the loser's name) becomes an alias of
      the survivor, unless the survivor already holds that key. A loser with no such row and a
      survivor without the key is `Held`: the alias needs an INSERT this lane does not make.

    `taken` is what the wave's earlier pairs of the same survivor move: it counts as the survivor's
    own for every check above, and is added to once this pair is planned.
    """
    loser, survivor = pair.loser, pair.survivor
    counts = {
        "images": 0,
        "images_stay": 0,
        "images_stay_filename": 0,
        "heroes_demoted": 0,
        "links": 0,
        "links_stay": 0,
        "names": 0,
    }
    taken = taken if taken is not None else Taken()
    cells: list[MoveCell] = []
    s_urls = {i["original_url"] for i in read.images.get(survivor, ())} | taken.urls
    s_has_hero = taken.hero or any(
        i["is_hero"] is True and live(i) for i in read.images.get(survivor, ())
    )
    moved = []
    for image in sorted(read.images.get(loser, ()), key=lambda i: int(i["id"])):
        if image["original_url"] in s_urls:
            counts["images_stay"] += 1
            continue
        if image["filename"] not in read.files[site_id_short(loser)]:
            raise Held(
                f"image row {image['id']} names the file {image['filename']!r}, which is not in "
                f"the loser's folder {site_id_short(loser)}: there is no picture to carry"
            )
        if image["filename"] in taken.filenames or name_taken(read, pair, image):
            counts["images_stay_filename"] += 1
            continue
        moved.append(image)
        counts["images"] += 1
        cells.append(
            MoveCell(
                loser,
                "wiki_images",
                str(image["id"]),
                "site_id",
                loser,
                survivor,
                "image moves to the survivor",
            )
        )
    heroes = sorted(
        (i for i in moved if i["is_hero"] is True and live(i)),
        key=lambda i: (int(i["sort_order"] or 0), int(i["id"])),
    )
    kept_hero = False
    for index, image in enumerate(heroes):
        kept_hero = kept_hero or not (s_has_hero or index > 0)
        if s_has_hero or index > 0:
            counts["heroes_demoted"] += 1
            cells.append(
                MoveCell(
                    loser,
                    "wiki_images",
                    str(image["id"]),
                    "is_hero",
                    "true",
                    "false",
                    "a second live hero is demoted to a plain image",
                )  # fmt: skip
            )
    s_keys = {(c["content_source"], c["content_id"]) for c in read.links.get(survivor, ())}
    s_keys |= taken.links
    moved_links = set()
    for link in sorted(read.links.get(loser, ()), key=lambda c: int(c["id"])):
        if (link["content_source"], link["content_id"]) in s_keys:
            counts["links_stay"] += 1
            continue
        moved_links.add((link["content_source"], link["content_id"]))
        counts["links"] += 1
        cells.append(
            MoveCell(
                loser,
                "site_content_links",
                str(link["id"]),
                "site_id",
                loser,
                survivor,
                "content link moves to the survivor",
            )
        )
    key = read.sites[loser]["name_key"]
    moves_name = key not in taken.names and not any(
        n["name_normalized"] == key for n in read.names.get(survivor, ())
    )
    if moves_name:
        row = next(
            (
                n
                for n in sorted(read.names.get(loser, ()), key=lambda n: int(n["id"]))
                if n["name_normalized"] == key
            ),
            None,
        )
        if row is None:
            raise Held(
                f"the loser's name {read.sites[loser]['name']!r} is no name row of the loser and "
                "none of the survivor: the alias would need an INSERT"
            )
        if row["name_type"] != ALIAS:
            cells.append(
                MoveCell(
                    loser,
                    "unified_site_names",
                    str(row["id"]),
                    "name_type",
                    str(row["name_type"]) if row["name_type"] is not None else "",
                    ALIAS,
                    "the loser's name becomes an alias",
                )
            )
        cells.append(
            MoveCell(
                loser,
                "unified_site_names",
                str(row["id"]),
                "site_id",
                loser,
                survivor,
                "the loser's name moves to the survivor",
            )
        )
        counts["names"] += 1
    taken.urls |= {i["original_url"] for i in moved}
    taken.filenames |= {i["filename"] for i in moved}
    taken.links |= moved_links
    taken.hero = taken.hero or kept_hero
    if moves_name:
        taken.names.add(key)
    return cells, counts


def build_move(
    read: Read, pairs: Sequence[WavePair], move: Lane, built_at: str
) -> tuple[P.Plan, list[dict[str, Any]], dict[str, int]]:
    """The plan of the wave's moves - a pure function of the read - and the pairs it holds back.

    Every pair that passes `check_pair` and `move_cells` contributes its cells; the others are
    `held` with the reason (never half-planned). The plan is refused when nothing is left."""
    stamps = [move.run_stamp, move.rollback_run_stamp]
    changes: list[P.Verdict] = []
    held: list[dict[str, Any]] = []
    taken: dict[str, Taken] = {}
    totals = dict.fromkeys(
        ("pairs", "images", "images_stay", "images_stay_filename", "heroes_demoted", "links",
         "links_stay", "names"), 0
    )  # fmt: skip
    for pair in pairs:
        try:
            loser, survivor = check_pair(read, pair, stamps)
            expected = move_premise(read, loser, survivor)
            if loser["move_premise"] != expected:
                raise Held(
                    f"the premise the database printed, {loser['move_premise']!r}, is not the one "
                    f"the read's rows give, {expected!r}"
                )
            cells, counts = move_cells(read, pair, taken.setdefault(pair.survivor, Taken()))
        except Held as exc:
            held.append(
                {
                    "loser": pair.loser,
                    "survivor": pair.survivor,
                    "name": pair.loser_name,
                    "reason": str(exc),
                }
            )
            continue
        if not cells:
            held.append({"loser": pair.loser, "survivor": pair.survivor, "name": pair.loser_name,
                         "reason": "nothing to move: the pair goes straight to its retirement"})  # fmt: skip
            continue
        evidence = _evidence(pair, read, loser, survivor)
        for cell in cells:
            changes.append(
                P.Verdict(
                    site_id=cell.site_id,
                    site_name=str(loser["name"]),
                    ok=True,
                    old_value=cell.old or None,
                    new_value=cell.new,
                    rule=RULE_MOVE,
                    reason="",
                    note=f"{cell.table}.{cell.column} of row {cell.row_id}: {cell.note} "
                    f"({loser['name']!r} -> {survivor['name']!r}, D14)",
                    phase3=False,
                    finding_test_id=move.test_id,
                    evidence=evidence,
                    premise=str(loser["move_premise"]),
                    column=cell.column,
                    table=cell.table,
                    row_id=cell.row_id,
                )
            )
        totals["pairs"] += 1
        for k, v in counts.items():
            totals[k] += v
    if not changes:
        raise P.PlanError("no pair of the wave has a row to move: nothing to plan" + _listed(held))
    plan = P.Plan(changes=tuple(changes), skipped=(), built_at=built_at,
                  counters={"sites": totals["pairs"], "cells": len(changes), **totals}, lane=move)  # fmt: skip
    return plan, held, totals


# ------------------------------------------------------------------------------ the retire plan
def build_retire(
    read: Read, pairs: Sequence[WavePair], retire: Lane, built_at: str
) -> tuple[P.Plan, list[dict[str, Any]]]:
    """The plan of the wave's retirements, from a read taken after the move.

    A loser is retired only when its move is complete: every image and content link it still holds
    is a collision (the survivor holds the same URL or content), its name is among the survivor's,
    and - when it shows an image - the survivor shows one too. Losers that are retired already are
    not in this plan."""
    stamps = [retire.run_stamp, retire.rollback_run_stamp]
    changes: list[P.Verdict] = []
    held: list[dict[str, Any]] = []
    for pair in pairs:
        if pair.already_retired:
            continue
        try:
            loser, survivor = check_pair(read, pair, stamps)
            if loser["scope_status"] is not None or loser["scope_reason"] is not None:
                raise Held(
                    f"the loser already has a scope decision: {loser['scope_status']!r}, "
                    f"{loser['scope_reason']!r}"
                )
            for column in ("scope_status", "scope_reason"):
                broken = P.journal_break(read.journal.get((pair.loser, column), ()), loser[column])
                if broken is not None:
                    raise Held(f"{column}: {broken[0]} - {broken[1]}")
            _complete(read, pair, loser, survivor)
            expected = retire_premise(read, loser, survivor)
            if loser["retire_premise"] != expected:
                raise Held(
                    f"the premise the database printed, {loser['retire_premise']!r}, is not the one "
                    f"the read's rows give, {expected!r}"
                )
        except Held as exc:
            held.append(
                {
                    "loser": pair.loser,
                    "survivor": pair.survivor,
                    "name": pair.loser_name,
                    "reason": str(exc),
                }
            )
            continue
        evidence = _evidence(pair, read, loser, survivor)
        for column, value in (
            ("scope_status", RETIRED),
            ("scope_reason", f"{DUPLICATE_PREFIX}{pair.survivor}"),
        ):
            changes.append(
                P.Verdict(
                    site_id=pair.loser,
                    site_name=str(loser["name"]),
                    ok=True,
                    old_value=None,
                    new_value=value,
                    rule=RULE_RETIRE,
                    reason="",
                    note=f"{column} NULL -> {value!r} (D14: {pair.loser_name!r} is the same site as "
                    f"{pair.survivor_name!r})",
                    phase3=False,
                    finding_test_id=retire.test_id,
                    evidence=evidence,
                    premise=str(loser["retire_premise"]),
                    column=column,
                )
            )
    if not changes:
        raise P.PlanError(
            "no loser of the wave can be retired yet: nothing to plan" + _listed(held)
        )
    plan = P.Plan(changes=tuple(changes), skipped=(), built_at=built_at,
                  counters={"sites": len(changes) // 2, "cells": len(changes)}, lane=retire)  # fmt: skip
    return plan, held


def _complete(
    read: Read, pair: WavePair, loser: Mapping[str, Any], survivor: Mapping[str, Any]
) -> None:
    """The move is complete: what the loser still holds, the survivor holds too - or could not take
    (an image whose filename the survivor's folder uses for another picture, `name_taken`)."""
    s_urls = {i["original_url"] for i in read.images.get(pair.survivor, ())}
    left = [
        i
        for i in read.images.get(pair.loser, ())
        if i["original_url"] not in s_urls and not name_taken(read, pair, i)
    ]
    if left:
        raise Held(
            f"{len(left)} image(s) the survivor lacks are still on the loser: run the move first"
        )
    s_keys = {(c["content_source"], c["content_id"]) for c in read.links.get(pair.survivor, ())}
    left_links = [
        c
        for c in read.links.get(pair.loser, ())
        if (c["content_source"], c["content_id"]) not in s_keys
    ]
    if left_links:
        raise Held(f"{len(left_links)} content link(s) the survivor lacks are still on the loser")
    if not any(
        n["name_normalized"] == loser["name_key"] for n in read.names.get(pair.survivor, ())
    ):
        raise Held("the loser's name is not among the survivor's names")
    if any(live(i) for i in read.images.get(pair.loser, ())) and not any(
        live(i) for i in read.images.get(pair.survivor, ())
    ):
        raise Held("the loser shows an image and the survivor shows none")


# ---------------------------------------------------------------------------------- the output
def plan_md(
    plan: P.Plan, held: Sequence[Mapping[str, Any]], read: Read, pairs: Sequence[WavePair]
) -> str:
    lane = plan.lane
    lines = [
        f"# D14 duplicate merge `{lane.name}`: plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/dup_merge.py` from the read-only "
        f"production read of {read.read_at} (`{READ_FILE}`). Lane `{lane.name}`: run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`, premise `{lane.premise_sql}`.",
        "",
        "Counters: " + ", ".join(f"{k} {v}" for k, v in plan.counters.items()),
        "",
        "| loser | survivor | pair limit (m) | already retired |",
        "|---|---|---|---|",
        *[
            f"| {p.loser_name} (`{p.loser}`) | {p.survivor_name} (`{p.survivor}`) | {p.metres_limit} | {p.already_retired} |"
            for p in pairs
        ],
        "",
    ]
    if held:
        lines += [
            "## Held back (not planned, not written)",
            "",
            *[f"* {h['name']} (`{h['loser']}`): {h['reason']}" for h in held],
            "",
        ]
    commands = [
        f"$PY scripts/remediation/mechanical/apply.py --lane {lane.name} {flag}"
        for flag in (
            "--check-primitive",
            "--verify",
            "--interests",
            "--emit",
            "--rehearse",
            "--probe-guards",
            "--apply",
            "--verify",
            "--rehearse-rollback",
        )  # fmt: skip
    ]
    moved = DUP_MERGE_MOVE_LANE.match(lane.name)
    if moved is not None:
        # the pictures go first (the apply refuses without them) and are asked for afterwards
        files = f"$PY scripts/remediation/mechanical/dup_merge.py files --wave {moved.group(1)}"
        commands[6:7] = [f"{files} --copy", commands[6], f"{files} --served"]
    lines += [
        "## Run",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        *commands,
        "```",
        "",
        "The reversal order is retire, then move.",
        "",
        "The loser's name row moves to the survivor as an alias. Lyra's boot (`_run_migrations`, "
        "'Backfill AN Originals') inserts a label row for every site that has none under its own "
        "name key, so after a Lyra restart the retired loser holds a new row with that key and the "
        "rollback of the name row stops at `uq_usn`: roll the move back before the next Lyra "
        "restart, or delete that one new row first.",
        "",
    ]
    return "\n".join(lines)


def write_plan(
    plan: P.Plan,
    held: Sequence[Mapping[str, Any]],
    read: Read,
    pairs: Sequence[WavePair],
    root: Path,
) -> Path:
    """The lane's files in its directory under `root` (`apply.lane_dir` for the default).

    `DISK.json`, the folder listing the plan was built on, is written here with the plan and not
    when the folders are read: a re-plan that is refused (a lane that has written) leaves the
    listing of the applied plan, whose `FILES.jsonl` carries that listing's sha256 values."""
    directory = root / plan.lane.out_dir_name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / DISK_FILE).write_text(
        json.dumps(read.files, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    P.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    (directory / "PLAN.md").write_text(
        plan_md(plan, held, read, pairs), encoding="utf-8", newline="\n"
    )
    (directory / HELD_FILE).write_text(
        "".join(json.dumps(h, ensure_ascii=False, sort_keys=True) + "\n" for h in held),
        encoding="utf-8",
        newline="\n",
    )
    if DUP_MERGE_MOVE_LANE.match(plan.lane.name) is not None:
        (directory / FILES_FILE).write_text(
            "".join(
                json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n"
                for f in move_files(plan, read)
            ),
            encoding="utf-8",
            newline="\n",
        )
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo
    P.write_rollback_sql(plan, directory / "ROLLBACK.sql", plan_path=directory / "PLAN.jsonl")
    return directory


# ---------------------------------------------------------------------------- the moved pictures
#: What `file_state` says of one planned picture. The first is the state a move may be applied in,
#: the second is `files --copy`'s work, the last two mean the folders are no longer as the plan
#: read them.
IN_PLACE = "in place"
TO_COPY = "not copied yet"
SOURCE_CHANGED = "the loser's file is gone or is another file than the plan read"
DEST_TAKEN = "the survivor's folder holds another file under this name"


def move_files(plan: P.Plan, read: Read) -> list[dict[str, str]]:
    """The picture of each image row the plan moves: where its file is (`source`), where the row is
    served from after the move (`dest`), both `<folder>/<filename>`, and the sha256 the loser's
    folder held when the plan was read."""
    rows = {str(i["id"]): i for images in read.images.values() for i in images}
    files = []
    for change in plan.changes:
        if (change.table, change.column) != ("wiki_images", "site_id"):
            continue
        name = rows[str(change.row_id)]["filename"]
        source, dest = site_id_short(change.site_id), site_id_short(str(change.new_value))
        files.append(
            {
                "row_id": str(change.row_id),
                "filename": name,
                "source": f"{source}/{name}",
                "dest": f"{dest}/{name}",
                "sha256": read.files[source][name],
            }
        )
    return files


def load_files(path: Path, plan_path: Path) -> list[dict[str, str]]:
    """`FILES.jsonl` of a move plan, held to its `PLAN.jsonl`: one picture per planned
    `wiki_images.site_id` cell, out of the folder of the cell's old site into the folder of its
    new one. A plan without the file (written before the file list existed) is refused."""
    if not path.exists():
        raise P.PlanError(
            f"{path} does not exist: the move plan was written without its file list - run "
            "plan-move --write again (allowed while the lane's stamp has no journal row)"
        )
    files = [json.loads(line) for line in jsonl_lines(path.read_text("utf-8")) if line.strip()]
    cells = [json.loads(line) for line in jsonl_lines(plan_path.read_text("utf-8")) if line.strip()]
    planned = sorted(
        (str(c["row_id"]), site_id_short(c["old_value"]), site_id_short(c["new_value"]))
        for c in cells
        if (c["row_table"], c["column"]) == ("wiki_images", "site_id")
    )
    listed = sorted(
        (f["row_id"], f["source"].partition("/")[0], f["dest"].partition("/")[0]) for f in files
    )
    if planned != listed:
        raise P.PlanError(
            f"{path} is not the file list of {plan_path}: {len(listed)} picture(s) for "
            f"{len(planned)} planned image row(s), or other folders - run plan-move --write again"
        )
    for f in files:
        names = {f["filename"], f["source"].partition("/")[2], f["dest"].partition("/")[2]}
        if len(names) != 1 or not _SHA256.match(f["sha256"]):
            raise P.PlanError(f"{path}: the entry of row {f['row_id']} is not one file's")
    return files


def file_state(entry: Mapping[str, str], listing: Mapping[str, Mapping[str, str]]) -> str:
    """One planned picture against the folders as they are."""
    source, _, name = entry["source"].partition("/")
    if listing[source].get(name) != entry["sha256"]:
        return SOURCE_CHANGED
    there = listing[entry["dest"].partition("/")[0]].get(name)
    if there is None:
        return TO_COPY
    return IN_PLACE if there == entry["sha256"] else DEST_TAKEN


def file_states(files: Sequence[Mapping[str, str]]) -> list[tuple[Mapping[str, str], str]]:
    """Every planned picture with its state, from one read-only listing of the folders named. A
    plan that moves no image row asks nothing."""
    if not files:
        return []
    folders = sorted({f[end].partition("/")[0] for f in files for end in ("source", "dest")})
    listing = read_folders(folders)
    return [(f, file_state(f, listing)) for f in files]


def _named(states: Sequence[tuple[Mapping[str, str], str]]) -> list[str]:
    return [f"{state}: {f['source']} -> {f['dest']} (row {f['row_id']})" for f, state in states]


def files_not_in_place(directory: Path, plan_path: Path) -> list[str]:
    """One line per picture of the move plan in `directory` that is not in its survivor's folder
    with the planned bytes: empty when the move can be applied. `apply.py --apply` asks it before
    the write (`files --verify` prints the same)."""
    states = file_states(load_files(directory / FILES_FILE, plan_path))
    return _named([(f, state) for f, state in states if state != IN_PLACE])


def copy_script(files: Sequence[Mapping[str, str]]) -> str:
    """Shell: copy each picture to its destination unless something is there - under a partial name
    first and renamed when it is whole (`mv -n` replaces nothing). It never moves a file (the
    rollback and the rows that stay need the loser's) and never overwrites one. A new folder and a
    new file get the modes of the tree (777 and 666 on all 4,197 folders, read 2026-11-10): the
    API container writes there as another user than the one that copies."""
    copies = sorted({(f["source"], f["dest"]) for f in files})
    return (
        f"set -u\ncd {shlex.quote(WIKI_TREE)} || exit 9\n"
        "c() {\n"
        '  if [ -e "$2" ]; then return 0; fi\n'
        '  if [ ! -d "${2%%/*}" ]; then mkdir -m 777 "${2%%/*}" || exit 7; fi\n'
        f'  cp -- "$1" "$2{PARTIAL}" || exit 7\n'
        f'  chmod 666 "$2{PARTIAL}" || exit 7\n'
        f'  mv -n -- "$2{PARTIAL}" "$2" || exit 7\n'
        f'  rm -f -- "$2{PARTIAL}"\n'
        "}\n" + "".join(f"c {shlex.quote(source)} {shlex.quote(dest)}\n" for source, dest in copies)
    )


def copy_files(files: Sequence[Mapping[str, str]]) -> dict[str, int]:
    """Put every planned picture into its survivor's folder, read back by its sha256 - or refuse
    and copy nothing, when a folder is no longer as the plan read it. Running it again is safe: a
    picture that is in place is left alone."""
    before = file_states(files)
    changed = [(f, state) for f, state in before if state in (SOURCE_CHANGED, DEST_TAKEN)]
    if changed:
        raise P.PlanError(
            "the image folders are not as the plan read them, nothing was copied - run plan-move "
            "--write again (allowed while the lane's stamp has no journal row):"
            + "".join(f"\n  - {line}" for line in _named(changed))
        )
    to_copy = [f for f, state in before if state == TO_COPY]
    if to_copy:
        run_on_vps(copy_script(to_copy))
    after = [(f, state) for f, state in file_states(files) if state != IN_PLACE]
    if after:
        raise P.PlanError(
            "after the copy these pictures are not in place:"
            + "".join(f"\n  - {line}" for line in _named(after))
        )
    return {"files": len(files), "copied": len(to_copy), "already_there": len(files) - len(to_copy)}


def served_status(url: str) -> int:
    """The site's answer to a HEAD for one picture. An HTTP error status is an answer and is
    returned; a request that got none (no connection, a timeout) raises."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - SERVED_ROOT is a fixed https URL
            urllib.request.Request(url, method="HEAD"), timeout=60
        ) as answer:
            return int(answer.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def not_served(files: Sequence[Mapping[str, str]]) -> list[str]:
    """One line per moved picture the site does not answer 200 for, under the path its row is
    served from after the move (`/data/images/wiki/<survivor, 8 hex>/<filename>`)."""
    urls = sorted({f"{SERVED_ROOT}/{urllib.parse.quote(f['dest'])}" for f in files})
    return [f"{code} {url}" for url in urls if (code := served_status(url)) != 200]


# ------------------------------------------------------------------------------------------ CLI
def _lanes(wave: str, pairs: Sequence[WavePair]) -> tuple[Lane, Lane]:
    lane_pairs = [p.lane_pair() for p in pairs]
    return dup_merge_move_lane(wave, lane_pairs), dup_merge_retire_lane(wave, lane_pairs)


def cmd_waves(args: argparse.Namespace) -> int:
    from identity import common

    run = common.run_dir(args.root)
    decisions = common.read_jsonl(run / "DUP_DECISIONS.jsonl")
    pairs = decided_pairs(decisions)
    excluded: list[dict[str, Any]] = []
    if args.exclude is not None:
        pairs, excluded = exclude_pairs(pairs, json.loads(args.exclude.read_text(encoding="utf-8")))
    if not pairs:
        raise P.PlanError("DUP_DECISIONS.jsonl holds no decided MERGE")
    waves = split_waves(pairs, args.max_sites)
    labels = wave_labels(args.date, len(waves))
    summary: dict[str, Any] = {}
    for label, group in zip(labels, waves, strict=True):
        path = write_wave(label, group, args.out)
        summary[label] = {"pairs": len(group), "file": str(path)}
        if excluded:
            summary[label]["excluded_file"] = str(write_excluded(label, excluded, args.out))
    summary["excluded"] = [f"{e['loser_name']} ({e['loser']})" for e in excluded]
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def cmd_plan(args: argparse.Namespace, *, kind: str) -> int:
    pairs = load_wave(args.wave, args.out)
    move, retire = _lanes(args.wave, pairs)
    lane = move if kind == "move" else retire
    if not args.write:
        print(
            f"{lane.name}: {len(pairs)} pair(s); add --write to read production and write the plan"
        )
        return 0
    root = args.out or REMEDIATION_ROOT
    read_path = write_read((root / lane.out_dir_name) / READ_FILE, pairs, move, retire)
    files = read_folders(wave_folders(pairs))
    read = parse_read(read_path.read_text(encoding="utf-8"), pairs, move, retire, files)
    if kind == "move":
        plan, held, _totals = build_move(read, pairs, move, P._now())
    else:
        plan, held = build_retire(read, pairs, retire, P._now())
    write_plan(plan, held, read, pairs, root)
    print(json.dumps({"lane": lane.name, **dict(plan.counters), "held": len(held)}, indent=1))
    return 0


def cmd_files(args: argparse.Namespace) -> int:
    """`files --copy | --verify | --served` for the move plan of a wave. Exit 0 when every picture
    is where the command asks it to be, 1 when one is not (each is printed) or on a refusal."""
    pairs = load_wave(args.wave, args.out)
    move, _retire = _lanes(args.wave, pairs)
    directory = (args.out or REMEDIATION_ROOT) / move.out_dir_name
    files = load_files(directory / FILES_FILE, directory / "PLAN.jsonl")
    if args.copy:
        print(json.dumps({"lane": move.name, **copy_files(files)}, indent=1))
        return 0
    if args.served:
        asked, problems = "served with HTTP 200", not_served(files)
    else:
        asked = "in the survivor's folder with the planned sha256"
        problems = _named([(f, s) for f, s in file_states(files) if s != IN_PLACE])
    answer = {"lane": move.name, "files": len(files), "asked": asked, "not": problems}
    print(json.dumps(answer, ensure_ascii=False, indent=1))
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D14: waves, move plan and retire plan of the merges")
    ap.add_argument("--root", type=Path, default=None, help="main checkout of the run data")
    ap.add_argument("--out", type=Path, default=None, help="default: output/remediation")
    sub = ap.add_subparsers(dest="command", required=True)
    waves = sub.add_parser("waves", help="split DUP_DECISIONS.jsonl into waves (PAIRS.json each)")
    waves.add_argument("--date", required=True, help="the first wave's label, e.g. 2026-10-10")
    waves.add_argument("--max-sites", type=int, default=MAX_SITES)
    waves.add_argument(
        "--exclude", type=Path, default=None,
        help='a JSON list of {"loser": id, "reason": why}: decided pairs left out of the waves',
    )  # fmt: skip
    for name in ("plan-move", "plan-retire"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--wave", required=True)
        cmd.add_argument(
            "--write", action="store_true", help="read production (read-only), write the plan"
        )
    files = sub.add_parser(
        "files", help="the pictures of the image rows a wave's move plan moves (FILES.jsonl)"
    )
    files.add_argument("--wave", required=True)
    step = files.add_mutually_exclusive_group(required=True)
    step.add_argument(
        "--copy",
        action="store_true",
        help="copy each picture into its survivor's folder on the VPS (never moves or "
        "overwrites one) and read it back by its sha256",
    )
    step.add_argument(
        "--verify", action="store_true", help="read-only: every picture is in place, byte for byte"
    )
    step.add_argument(
        "--served", action="store_true", help="after the apply: the site answers 200 for each"
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "waves":
            return cmd_waves(args)
        if args.command == "files":
            return cmd_files(args)
        return cmd_plan(args, kind="move" if args.command == "plan-move" else "retire")
    except (P.PlanError, ValueError, FileNotFoundError, urllib.error.URLError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
