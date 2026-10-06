"""The candidate judgement (owner decision 2026-10-06): does this picture show this site?

The search hands over candidates; **this is the stage that decides**, one verdict per candidate, and
nothing else does. A candidate becomes a picture of a site only when the verdict is `depicts`; every
other verdict - `region_or_type`, `other_site` - ends that file's candidacy, and a site whose
candidates are all refused simply keeps the picture it has (or none).

**What the pilot measured, so nobody has to guess what this stage yields.** 23 candidates of three
sites, one verdict each: **3 `depicts`, 7 `region_or_type`, 13 `other_site`** - 13 % precision, and one
site in three with at least one picture of itself. The misses are not near misses (three photographs
of Mars for the site *Gonnus*, four bronze coins, graves of a different Cerna in Bucharest, a
barracks in Brno, a ski slope in Slovakia). The expected yield over the class is therefore **one site
in six**, which is the number the owner decides with.

The transport is the handoff the project already uses (`opus_handoff.py`): the code writes the
question, an agent answers one JSON object per site, the code checks the answer's shape and records it
under the name of the model that wrote it. The verdicts are **never** taken from the file name, the
Commons title or the model's prior: the agent is given the bytes and the site's own name and country
and has to look.

Batch shape: `IMAGES_PER_BATCH` candidates, packed by site, so one site never splits across two
agents (its candidates are one judgement). The write side of this stage is `write_targets`: the
`(site_id, commons_file)` pairs the INSERT lane's fetch takes, one per site - the best `depicts`
candidate of that site, the largest, because a bigger file stores a bigger hero at the same licence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
for _path in (_ROOT, _ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

CANDIDATES = "CANDIDATES.jsonl"
VERDICTS = "VERDICTS.jsonl"
PICTURES = "pictures"
REFUSED = "CANDIDATE_VERDICT_REFUSALS.jsonl"
TARGETS = "TARGETS.jsonl"

#: Candidates per agent. 36 is the number the gallery vision lane packs (`vision.REPLACE_IMAGES_PER_BATCH`):
#: enough for one site of an ordinary day, small enough that no agent judges hundreds of images.
IMAGES_PER_BATCH = 36
#: A batch never grows past this many sites, so one agent cannot be handed the whole run.
SITES_PER_BATCH = 6

DEPICTS = "depicts"
REGION = "region_or_type"
OTHER = "other_site"
VERDICTS_THAT_END_CANDIDACY = frozenset({DEPICTS, REGION, OTHER})


def pack(
    sites: Sequence[Mapping[str, Any]],
    *,
    images_per_batch: int = IMAGES_PER_BATCH,
    sites_per_batch: int = SITES_PER_BATCH,
) -> list[dict[str, Any]]:
    """The sites of a run into batches of candidates, a site never split across two batches.

    A site with more candidates than a whole batch is the only case that does not fit; it gets a
    batch of its own and the surplus is **refused by name** rather than quietly dropped, because a
    candidate nobody looks at is a candidate the site could have had.
    """
    batches: list[dict[str, Any]] = []
    current: list[Mapping[str, Any]] = []
    used = 0
    for site in sites:
        count = len(site.get("candidates") or ())
        if count == 0:
            continue
        if count > images_per_batch:
            # the site's first `images_per_batch` candidates go to the judge, the surplus is named
            head = dict(site)
            head["candidates"] = list(site["candidates"])[:images_per_batch]
            batches.append(
                {"sites": [head], "images": images_per_batch, "refused": [count - images_per_batch]}
            )
            continue
        if used + count > images_per_batch or len(current) >= sites_per_batch:
            batches.append({"sites": current, "images": used, "refused": []})
            current, used = [], 0
        current.append(site)
        used += count
    if current:
        batches.append({"sites": current, "images": used, "refused": []})
    for number, batch in enumerate(batches, start=1):
        batch["batch_id"] = f"cand-{number:04d}"
    return batches


def download(
    client: Any, candidate: Mapping[str, Any], pictures: Path
) -> tuple[dict[str, Any], str]:
    """One candidate's bytes, named by the sha256 of their URL, and the candidate with its path.

    A refusal is part of the answer, not an exception: a candidate whose rendering cannot be fetched
    is recorded with the reason, so the site's judgement counts it as judged rather than leaving a
    hole the answer would have to guess at.
    """
    url = str(candidate.get("picture_url") or "")
    if not url:
        return {**candidate, "path": "", "fetched": False}, "the search recorded no rendering"
    target = pictures / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        response = client.get(url)
        if response.status_code != 200 or not response.content:
            return {**candidate, "path": "", "fetched": False}, f"HTTP {response.status_code}"
        target.write_bytes(response.content)
    suffix = ".jpg" if "jpeg" in str(candidate.get("original_url") or "") else ".img"
    named = target.with_suffix(suffix if not target.with_suffix(suffix).exists() else target.suffix)
    named = named if named.exists() else target
    return {**candidate, "path": str(named), "fetched": True}, ""


def export(
    out: Path,
    sites: Sequence[Mapping[str, Any]],
    client: Any,
    *,
    images_per_batch: int = IMAGES_PER_BATCH,
    sites_per_batch: int = SITES_PER_BATCH,
) -> dict[str, Any]:
    """The run's candidates into batches, every image on disk, one prompt file per site.

    The prompts are written where the handoff reads them (`<out>/<batch_id>/<site_id>.prompt.txt`),
    so an agent answers one file per site and the code can record it under the model's own name.
    """
    pictures = out / PICTURES
    prepared: list[dict[str, Any]] = []
    refusals: list[dict[str, str]] = []
    for site in sites:
        rows: list[dict[str, Any]] = []
        for candidate in site.get("candidates") or ():
            row, reason = download(client, candidate, pictures)
            if not row.get("fetched"):
                refusals.append(
                    {
                        "site_id": str(site.get("site_id") or ""),
                        "file": str(candidate.get("file") or ""),
                        "reason": reason,
                    }
                )
                continue
            rows.append(row)
        if rows:
            prepared.append({**site, "candidates": rows})
    batches = pack(prepared, images_per_batch=images_per_batch, sites_per_batch=sites_per_batch)
    written = 0
    for batch in batches:
        folder = out / batch["batch_id"]
        folder.mkdir(parents=True, exist_ok=True)
        for site in batch["sites"]:
            (folder / f"{site['site_id']}.prompt.txt").write_text(
                prompt_for(site), encoding="utf-8", newline="\n"
            )
            written += 1
    return {
        "sites_with_candidates": len(prepared),
        "candidates": sum(len(s["candidates"]) for s in prepared),
        "batches": len(batches),
        "prompt_files": written,
        "images": str(pictures),
        "refused_images": len(refusals),
        "refusals": refusals[:20],
    }


def prompt_for(site: Mapping[str, Any]) -> str:
    """The question one site asks, in the shape the answer's JSON mirrors."""
    lines = [
        f"site_id: {site['site_id']}",
        f"name: {site.get('name') or ''}",
        f"country: {site.get('country') or ''}",
        "",
        "Zeige jedes Bild unter diesem Pfad und entscheide fuer jedes genau eines:",
        "",
        f"- `{DEPICTS}`: das Bild zeigt die Site selbst - ihre Ruinen, Strukturen, Ausgrabungen,",
        "  Felsbilder oder eine Umgebung, in der die Site erkennbar ist; oder ein dort gefundenes",
        "  Objekt.",
        f"- `{REGION}`: das Bild zeigt nur die Region oder den Typ (Landschaft, Dorf, Museum, Karte),",
        "  nicht die Site.",
        f"- `{OTHER}`: das Bild zeigt eine andere Site oder etwas ganz anderes (eine Person, eine",
        "  Muenze, ein anderes Land, eine moderne Szene).",
        "",
        "Trage dein Urteil nicht aus dem Dateinamen oder deinem Vorwissen ab: eine Datei namens",
        '"Cerna, Dunare.JPG" ist nicht die Site Cerna in Kroatien, wenn das Bild etwas anderes zeigt.',
        "Bilde nichts aus: wenn du ein Bild nicht sicher lesen kannst, nimm",
        f"`{REGION}` und schreibe das in die Notiz.",
        "",
    ]
    for candidate in site["candidates"]:
        lines.append(f"- {candidate['file']}  ->  {candidate['path']}")
    lines += [
        "",
        "Antworte mit genau einem JSON-Objekt (UTF-8, keine Codezaeune) auf stdout:",
        "",
        '{"site_id": "...", "verdicts": [{"file": "...", "verdict": "depicts",',
        ' "note": "woran du das im Bild siehst, max 200 Zeichen"}], "note": ""}',
        "",
    ]
    return "\n".join(lines) + "\n"


def check_answer(answer: Mapping[str, Any], site: Mapping[str, Any]) -> list[str]:
    """Why this answer is refused - by name, every reason the code can see."""
    problems: list[str] = []
    wanted = {c["file"] for c in site["candidates"]}
    if answer.get("site_id") != site["site_id"]:
        problems.append(f"site_id: {answer.get('site_id')!r} is not {site['site_id']!r}")
    # The stamp is not decoration: a verdict without the model that made it cannot be audited, and
    # the audit of a wrong picture is exactly what this stage exists for.
    for key in ("answered_by", "model"):
        if not str(answer.get(key) or "").strip():
            problems.append(f"{key}: the answer does not name who judged, or with which model")
    verdicts = answer.get("verdicts")
    if not isinstance(verdicts, list):
        return problems + ["verdicts: no list"]
    seen: set[str] = set()
    for entry in verdicts:
        if not isinstance(entry, Mapping):
            problems.append("verdicts: an entry that is not an object")
            continue
        file = str(entry.get("file") or "")
        verdict = str(entry.get("verdict") or "")
        if file not in wanted:
            problems.append(f"file: {file!r} is not one of the site's candidates")
            continue
        if file in seen:
            problems.append(f"file: {file!r} judged twice")
        seen.add(file)
        if verdict not in VERDICTS_THAT_END_CANDIDACY:
            problems.append(
                f"verdict: {verdict!r} is not one of {sorted(VERDICTS_THAT_END_CANDIDACY)}"
            )
        note = str(entry.get("note") or "")
        if len(note) > 600:
            problems.append(f"note: {len(note)} characters for {file!r}")
    missing = sorted(wanted - seen)
    if missing:
        problems.append(f"not judged: {', '.join(missing)}")
    return problems


def import_answers(
    out: Path, answers: Mapping[str, Mapping[str, Any]], sites: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """The recorded answers, checked and written; the refusals named, the rest kept."""
    rows: list[dict[str, Any]] = []
    refusals: list[dict[str, str]] = []
    for site_id, site in sites.items():
        answer = answers.get(site_id)
        if answer is None:
            refusals.append(
                {"site_id": site_id, "reason": "not_answered", "detail": f"{site_id}: no answer"}
            )
            continue
        problems = check_answer(answer, site)
        if problems:
            refusals.append(
                {
                    "site_id": site_id,
                    "reason": "shape",
                    "detail": f"{site_id}: " + "; ".join(problems),
                }
            )
            continue
        for entry in answer["verdicts"]:
            rows.append(
                {
                    "site_id": site_id,
                    "name": site.get("name") or "",
                    "country": site.get("country") or "",
                    "file": entry["file"],
                    "verdict": entry["verdict"],
                    "width": next(
                        (c["width"] for c in site["candidates"] if c["file"] == entry["file"]), 0
                    ),
                    "height": next(
                        (c["height"] for c in site["candidates"] if c["file"] == entry["file"]), 0
                    ),
                    "note": str(entry.get("note") or ""),
                    "answered_by": str(answer.get("answered_by") or ""),
                    "model": str(answer.get("model") or ""),
                }
            )
    out.mkdir(parents=True, exist_ok=True)
    (out / VERDICTS).write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    (out / REFUSED).write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in refusals),
        encoding="utf-8",
        newline="\n",
    )
    sites_with = sorted({r["site_id"] for r in rows if r["verdict"] == DEPICTS})
    return {
        "sites_answered": len(sites) - len([r for r in refusals if r["reason"] == "not_answered"]),
        "sites_refused": len(refusals),
        "candidates_judged": len(rows),
        "verdicts": {
            verdict: sum(1 for r in rows if r["verdict"] == verdict)
            for verdict in sorted(VERDICTS_THAT_END_CANDIDACY)
        },
        "sites_with_a_picture": len(sites_with),
    }


def write_targets(out: Path, verdicts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One `(site_id, commons_file)` per site that has a `depicts` verdict - the largest of them.

    The fetch takes that pair and records the licence, the author and both URLs by itself; what this
    stage decides is only **which** file each site gets.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in verdicts:
        if row.get("verdict") != DEPICTS:
            continue
        site_id = str(row["site_id"])
        size = (int(row.get("width") or 0), int(row.get("height") or 0))
        current = best.get(site_id)
        if current is None or size > (
            int(current.get("width") or 0),
            int(current.get("height") or 0),
        ):
            best[site_id] = dict(row)
    out.mkdir(parents=True, exist_ok=True)
    (out / TARGETS).write_text(
        "".join(
            json.dumps(
                {
                    "site_id": row["site_id"],
                    "commons_file": row["file"],
                    "width": row["width"],
                    "height": row["height"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for row in sorted(best.values(), key=lambda r: str(r["site_id"]))
        ),
        encoding="utf-8",
        newline="\n",
    )
    return {"sites_to_fetch": len(best), "file": str(out / TARGETS)}
