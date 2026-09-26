"""The served-image decisions as planned rows for the shared image writer, and their acceptance.

One rule per outcome (O6: "Belegt ersetzen, sonst leeren"), each site decided on its own:

* **confirmed** - the vision check called the served image `depicts` (or, with `--population
  unconfirmed`, the pre-check confirmed it): the page keeps it. `wd2-align`: the site's
  `thumbnail_url` becomes the served row's local file when it names anything else, so the globe
  shows the confirmed image too (`gallery_audit/decide.py` rule T1). A served thumbnail that was
  checked through its file because its own address serves no picture (`vision.file_behind`) gets
  the file's own URL (`wd2-thumb`).
* **replaced** - the replacement stage picked a gallery row (`G`) it called `depicts`: `wd2-hero`
  moves the hero flag onto it (and off the row that held it), `wd2-align` points the thumbnail at it.
* **cleared** - nothing the lane can serve depicts the site: `wd2-exclude` excludes every live row
  (each was called not `depicts` - the served one by the check, every other one by the replacement
  stage) and takes the hero flag off it; `wd2-thumb` sets `thumbnail_url` to the confirmed Commons
  file the replacement stage picked (`W`), else to NULL. The site then serves no image on its page.

A site that serves nothing is left as it is. Every change carries the verdicts it rests on.

The writer is `gallery_audit/chunk_writer.py` (chunks of at most 100 sites, one transaction each,
the conditional old value, the journal row, `ROLLBACK.sql` written first). Its read-back proves the
rows; `accept` proves the outcome - every site of a chunk serves exactly what this plan says, on
the page and on the globe - read-only, and exits 0 only with 0 deviations.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gallery_audit import chunk_writer as CW  # noqa: E402
from hero_repair.thumbnail import local_path  # noqa: E402

from served_image import precheck as PC  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402

LANE_NAME = "served-image"
TEST_ID = "WD2/served-image"
LABEL = "served image"
RUN_RE = re.compile(r"served-image-(\d{4}-\d{2}-\d{2}[a-z]?)")

RULE_ALIGN = "wd2-align"
RULE_HERO = "wd2-hero"
RULE_EXCLUDE = "wd2-exclude"
RULE_THUMB = "wd2-thumb"

CHUNKS = "chunks"
EXPECTED = "EXPECTED.jsonl"
SUMMARY = "PLAN_SUMMARY.json"

CONFIRMED, REPLACED, CLEARED, NOTHING = "confirmed", "replaced", "cleared", "no image"


def lane_for(run: Path) -> CW.Lane:
    """The journal identity of a run: lane `served-image`, stamped with the run directory's date."""
    match = RUN_RE.fullmatch(run.name)
    if match is None:
        raise ST.StateError(f"{run} is not a run directory (served-image-YYYY-MM-DD[a-z])")
    return CW.Lane(LANE_NAME, TEST_ID, f"{LANE_NAME}-{match.group(1)}", "authoritative", LABEL)


def _bool(value: Any) -> str:
    return "true" if value else "false"


@dataclass
class SitePlan:
    """One site's outcome: what it will serve, and the changes that make it so."""

    site_id: str
    outcome: str
    served_image_id: int | None
    thumbnail_url: str | None
    changes: list[CW.Change] = field(default_factory=list)
    may_empty: bool = False

    def expected(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "outcome": self.outcome,
            "served_image_id": self.served_image_id,
            "thumbnail_url": self.thumbnail_url,
        }


def _evidence_check(check: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": "served_image/CHECK.jsonl",
        "stage": V.STAGE_CHECK,
        "image_id": check["served"].get("image_id"),
        "file": check["served"].get("file"),
        "verdict": check["verdict"],
        "shows": check["shows"],
        "basis": check["basis"],
        "answered_by": check["answered_by"],
        "prompt_sha256": check["prompt_sha256"],
    }


def _evidence_precheck(pre: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": "served_image/PRECHECK.jsonl",
        "status": pre["status"],
        "reason": pre["reason"],
        "qid": pre["qid"],
        "file": pre["served"].get("file"),
    }


def _evidence_replace(rep: Mapping[str, Any], label: str | None) -> dict[str, Any]:
    shown = {c["label"]: c for c in rep["candidates_shown"]}
    out = {
        "source": "served_image/REPLACE.jsonl",
        "stage": V.STAGE_REPLACE,
        "pick": rep["pick"],
        "basis": rep["basis"],
        "answered_by": rep["answered_by"],
        "prompt_sha256": rep["prompt_sha256"],
    }
    if label is not None:
        out |= {
            "label": label,
            "verdict": rep["candidates"][label],
            "image_id": shown[label]["image_id"],
            "file": shown[label]["file"],
        }
    return out


def _thumb(
    site: Mapping[str, Any], new: str | None, rule: str, reason: str, evidence: list[dict[str, Any]]
) -> list[CW.Change]:
    old = site.get("thumbnail_url") or None
    if old == new:
        return []
    sid = str(site["id"])
    return [CW.Change("unified_sites", "thumbnail_url", sid, sid, old, new, rule, reason, evidence)]


def decide_site(
    site: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    pre: Mapping[str, Any],
    check: Mapping[str, Any] | None,
    rep: Mapping[str, Any] | None,
    *,
    population: str,
) -> SitePlan:
    sid = str(site["id"])
    served = pre["served"]
    thumb = site.get("thumbnail_url") or None
    if pre["status"] == PC.NO_IMAGE:
        return SitePlan(sid, NOTHING, None, thumb)
    live = ST.live_rows(rows)
    if check is None:
        if population != V.UNCONFIRMED_ONLY or pre["status"] not in PC.CONFIRMED:
            raise ST.StateError(f"{sid}: the served image has no check answer")
        evidence = [_evidence_precheck(pre)]
    elif check["verdict"] == V.DEPICTS:
        evidence = [_evidence_precheck(pre), _evidence_check(check)]
    else:
        return _not_depicting(site, live, pre, check, rep)
    if served["kind"] != ST.GALLERY:
        repair = check["repair"] if check is not None else None
        if repair is None:
            return SitePlan(sid, CONFIRMED, None, thumb)
        reason = (
            f"the served thumbnail's file depicts the site, but its address serves no picture "
            f"({repair['error']}): the thumbnail becomes the file's own URL"
        )
        evidence = [*evidence, {"source": "served_image/CHECK.jsonl", "repair": dict(repair)}]
        new = repair["file_url"]
        return SitePlan(sid, CONFIRMED, None, new, _thumb(site, new, RULE_THUMB, reason, evidence))
    row = next(r for r in live if int(r["id"]) == served["image_id"])
    target = local_path(sid, str(row["filename"]))
    reason = f"the served image {row['id']} depicts the site; the globe shows it too"
    changes = _thumb(site, target, RULE_ALIGN, reason, evidence)
    return SitePlan(sid, CONFIRMED, int(row["id"]), target, changes)


def _not_depicting(
    site: Mapping[str, Any],
    live: Sequence[Mapping[str, Any]],
    pre: Mapping[str, Any],
    check: Mapping[str, Any],
    rep: Mapping[str, Any] | None,
) -> SitePlan:
    """A served image the check did not call `depicts`: replaced by a gallery row, or cleared."""
    sid = str(site["id"])
    served = pre["served"]
    base = [_evidence_check(check)]
    pick = rep["pick"] if rep is not None else None
    shown = {c["label"]: c for c in rep["candidates_shown"]} if rep is not None else {}
    if pick is not None and shown[pick]["kind"] == V.GALLERY_CANDIDATE:
        new_id = int(shown[pick]["image_id"])
        new = next(r for r in live if int(r["id"]) == new_id)
        evidence = [*base, _evidence_replace(rep or {}, pick)]
        changes: list[CW.Change] = []
        for row in live:
            if row.get("is_hero") and int(row["id"]) != new_id:
                changes.append(
                    CW.Change(
                        "wiki_images",
                        "is_hero",
                        str(row["id"]),
                        sid,
                        "true",
                        "false",
                        RULE_HERO,
                        f"the hero {row['id']} does not depict the site; {new_id} replaces it",
                        evidence,
                    )
                )
        changes.append(
            CW.Change(
                "wiki_images",
                "is_hero",
                str(new_id),
                sid,
                _bool(new.get("is_hero")),
                "true",
                RULE_HERO,
                f"{new_id} depicts the site and replaces the served image",
                evidence,
            )
        )
        target = local_path(sid, str(new["filename"]))
        changes += _thumb(site, target, RULE_ALIGN, "the globe shows the replacement too", evidence)
        return SitePlan(sid, REPLACED, new_id, target, changes)
    # cleared: no gallery row depicts the site
    changes = []
    labels = {c["image_id"]: c["label"] for c in shown.values() if c["image_id"] is not None}
    for row in live:
        rid = int(row["id"])
        if rid == served.get("image_id"):
            evidence = base
        elif rid in labels and rep is not None:
            evidence = [*base, _evidence_replace(rep, labels[rid])]
        else:
            raise ST.StateError(
                f"{sid}: live row {rid} was neither checked nor shown as a candidate"
            )
        reason = f"row {rid} does not depict the site, and no gallery row does"
        if row.get("is_hero"):
            changes.append(
                CW.Change(
                    "wiki_images",
                    "is_hero",
                    str(rid),
                    sid,
                    "true",
                    "false",
                    RULE_EXCLUDE,
                    reason,
                    evidence,
                )
            )
        changes.append(
            CW.Change(
                "wiki_images",
                "is_excluded",
                str(rid),
                sid,
                "false",
                "true",
                RULE_EXCLUDE,
                reason,
                evidence,
            )
        )
    if pick is not None:
        chosen = shown[pick]
        new_thumb: str | None = str(chosen["url"])
        reason = f"no gallery row depicts the site; the Commons file {chosen['file']!r} does"
        evidence = [*base, _evidence_replace(rep or {}, pick)]
    else:
        new_thumb = None
        reason = "nothing the lane can serve depicts the site (O6: else no image)"
        evidence = [*base] + ([_evidence_replace(rep, None)] if rep is not None else [])
    changes += _thumb(site, new_thumb, RULE_THUMB, reason, evidence)
    return SitePlan(sid, CLEARED, None, new_thumb, changes, may_empty=bool(live))


# ------------------------------------------------------------------------------ the plan
def _by_site(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if row["site_id"] in out:
            raise ST.StateError(f"{row['site_id']} is answered twice")
        out[row["site_id"]] = row
    return out


def build(run: Path) -> tuple[list[SitePlan], dict[str, Any]]:
    state = ST.load_read(run / "READ.json")
    prechecks = PC.load_prechecks(run / "PRECHECK.jsonl")
    record = json.loads((run / V.EXPORT_CHECK).read_text(encoding="utf-8"))
    if record["read_sha256"] != state.sha256:
        raise ST.StateError("CHECK was exported from another READ.json - re-run the lane")
    population = record["population"]
    checks = _by_site(V.read_jsonl(run / V.CHECK))
    failed = [c for c in checks.values() if c["verdict"] != V.DEPICTS]
    replaces: dict[str, Mapping[str, Any]] = {}
    if failed:
        replace_record = json.loads((run / V.EXPORT_REPLACE).read_text(encoding="utf-8"))
        if replace_record["check_sha256"] != ST.file_sha256(run / V.CHECK):
            raise ST.StateError("REPLACE was exported from another CHECK.jsonl")
        without = {w["site_id"] for w in replace_record["without_candidates"]}
        replaces = (
            dict(_by_site(V.read_jsonl(run / V.REPLACE))) if replace_record["questions"] else {}
        )
        missing = {c["site_id"] for c in failed} - without - set(replaces)
        if missing:
            raise ST.StateError(f"{len(missing)} failed image(s) have no replacement answer")
    plans = [
        decide_site(
            state.sites[sid],
            state.rows.get(sid, ()),
            prechecks[sid],
            checks.get(sid),
            replaces.get(sid),
            population=population,
        )
        for sid in state.site_ids()
        if sid in prechecks
    ]
    counts: dict[str, int] = {}
    for p in plans:
        counts[p.outcome] = counts.get(p.outcome, 0) + 1
    counts["sites with a change"] = sum(1 for p in plans if p.changes)
    counts["rows"] = sum(len(p.changes) for p in plans)
    return plans, {"population": population, "counts": counts}


def write_plan(run: Path) -> dict[str, Any]:
    plans, summary = build(run)
    changes = [c for p in plans for c in p.changes]
    out = run / CHUNKS
    if (out / EXPECTED).exists():
        raise ST.StateError(f"{out} holds a plan already - a delivered plan is never replaced")
    chunks = (
        CW.chunk_changes(
            lane_for(run),
            changes,
            may_empty=[p.site_id for p in plans if p.may_empty and p.changes],
        )
        if changes
        else []
    )
    CW.emit_chunks(out, chunks)
    chunk_of = {sid: chunk.number for chunk in chunks for sid in chunk.sites}
    out.mkdir(parents=True, exist_ok=True)
    (out / EXPECTED).write_text(
        "".join(
            json.dumps(p.expected() | {"chunk": chunk_of.get(p.site_id)}, sort_keys=True) + "\n"
            for p in plans
        ),
        encoding="utf-8",
        newline="\n",
    )
    summary |= {"chunks": len(chunks), "lane": asdict(lane_for(run))}
    (out / SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


# ------------------------------------------------------------------------------ acceptance
ACCEPT_SITES_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.thumbnail_url, u.source_id FROM unified_sites u
   WHERE u.id IN ({ids}) ORDER BY u.id
) t;"""
ACCEPT_IMAGES_SQL = """SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.filename, w.is_hero, w.is_lead, w.is_excluded,
         w.sort_order FROM wiki_images w WHERE w.site_id IN ({ids}) ORDER BY w.site_id, w.id
) t;"""


def deviations(
    expected: Sequence[Mapping[str, Any]],
    sites: Sequence[Mapping[str, Any]],
    images: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production serves against what the plan says, per site - each difference named."""
    by_site = {str(s["id"]): s for s in sites}
    rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in images:
        rows.setdefault(str(row["site_id"]), []).append(row)
    out: list[str] = []
    for want in expected:
        sid = want["site_id"]
        site = by_site.get(sid)
        if site is None or site["source_id"] != ST.CURATED_SOURCE:
            out.append(f"{sid}: not a curated site in production")
            continue
        head = ST.served_row(rows.get(sid, ()))
        served = None if head is None else int(head["id"])
        if served != want["served_image_id"]:
            out.append(f"{sid}: serves image {served}, the plan says {want['served_image_id']}")
        if (site["thumbnail_url"] or None) != want["thumbnail_url"]:
            out.append(
                f"{sid}: thumbnail_url {site['thumbnail_url']!r}, the plan says "
                f"{want['thumbnail_url']!r}"
            )
        heroes = [r for r in rows.get(sid, ()) if r["is_hero"]]
        if len(heroes) > 1 or any(r["is_excluded"] for r in heroes):
            out.append(f"{sid}: {len(heroes)} hero row(s), an excluded one among them or two")
    return out


def accept(run: Path, chunk: Path) -> dict[str, Any]:
    """Read-only: every site of `chunk` serves what the plan says. 0 deviations or exit 1."""
    delivered = CW.check_delivered(chunk)
    expected = [
        json.loads(line)
        for line in (run / CHUNKS / EXPECTED).read_text(encoding="utf-8").splitlines()
        if line
    ]
    mine = [e for e in expected if e["chunk"] == delivered.number]
    if {e["site_id"] for e in mine} != set(delivered.sites):
        raise ST.StateError(f"{chunk}: EXPECTED.jsonl and the chunk name different sites")
    ids = ", ".join(f"'{e['site_id']}'::uuid" for e in mine)
    found = deviations(
        mine,
        CW.pv.read_rows(ACCEPT_SITES_SQL.replace("{ids}", ids)),
        CW.pv.read_rows(ACCEPT_IMAGES_SQL.replace("{ids}", ids)),
    )
    return {"chunk": delivered.number, "sites": len(mine), "deviations": found}
