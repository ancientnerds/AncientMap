"""Try to turn the 30 kind-labelled `rejected` entries into `wiki_images` rows.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        scripts/remediation/vlm_pilot/rejected_kinds.py

Out: `output/remediation/vlm_pilot/REJECTED_KINDS.jsonl` (one record per entry)
and `REJECTED_KINDS.md`.

`video-assets/shorts/<slug>/selection.json` keeps two lists: `stills`, whose
entries carry `id` + `verdict.kind`, and `rejected`, whose entries carry only
`filename` + `reason`. 30 of the 175 rejected entries name a kind verbatim in
the reason ("kind=artifact" and friends), and those 30 have no id, so they cannot
be written the way the stills were.

The way back is the short's own `images.json` - the candidate pool the selector
ran on: `video-assets/shorts/<slug>/images.json` is written by
`pipeline/video/shorts_export.py` from `wiki_images` and carries `id`, `filename`
**and** `original_url` for every candidate of that site, in the same order the
selector saw them. A rejected filename that matches exactly one `images.json`
entry therefore names exactly one row, and the snapshot confirms the id from the
other side.

Three outcomes, and no fourth:

* **PROVEN** - exactly one candidate, and the snapshot's row with that id has the
  same site and the same filename (two independent records agree), and/or the
  snapshot itself holds exactly one row for (site, filename).
* **AMBIGUOUS** - more than one candidate matches, or the only match needs a
  filename transformation (case, sanitised characters), or the candidate pool is
  missing so only one of the two records can speak.
* **UNPROVABLE** - nothing matches.

A guess is never promoted to PROVEN. The report is in `REJECTED_KINDS.md` and the
machine-readable form in `REJECTED_KINDS.jsonl`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    OFFSITE_CASE_COLLISIONS,
    OFFSITE_IMAGES,
    OUT_DIR,
    REPO_ROOT,
    WIKI_IMAGES_SNAPSHOT,
    build_tree,
    is_webp,
    locate,
    read_jsonl_gz,
)

SHORTS_DIR = REPO_ROOT / "video-assets" / "shorts"
KIND_MARKER = "kind="


def rejected_with_kind() -> list[dict]:
    """Every `rejected` entry whose reason names a kind, in file order."""
    out: list[dict] = []
    for selection in sorted(SHORTS_DIR.glob("*/selection.json")):
        slug = selection.parent.name
        data = json.loads(selection.read_text(encoding="utf-8"))
        for entry in data.get("rejected", []):
            reason = entry.get("reason") or ""
            if KIND_MARKER not in reason:
                continue
            out.append(
                {
                    "slug": slug,
                    "filename": entry.get("filename"),
                    "reason": reason,
                    "kind_stated": reason.split(KIND_MARKER, 1)[1].split()[0].rstrip(",;)"),
                }
            )
    return out


def main() -> int:
    by_site: dict[str, list[dict]] = {}
    for row in read_jsonl_gz(WIKI_IMAGES_SNAPSHOT):
        by_site.setdefault(row["site_id"], []).append(row)
    # Built up front: a missing image tree fails here, loudly, instead of every record quietly
    # getting `resolved_path: None`.
    trees = (
        (OFFSITE_IMAGES, build_tree(OFFSITE_IMAGES)),
        (OFFSITE_CASE_COLLISIONS, build_tree(OFFSITE_CASE_COLLISIONS)),
    )

    records: list[dict] = []
    for entry in rejected_with_kind():
        slug = entry["slug"]
        short_dir = SHORTS_DIR / slug
        filename = entry["filename"]
        site_file = short_dir / "site.json"
        site_id = json.loads(site_file.read_text(encoding="utf-8")).get("id") if site_file.is_file() else None
        pool_file = short_dir / "images.json"
        pool = json.loads(pool_file.read_text(encoding="utf-8")) if pool_file.is_file() else None

        record: dict = dict(entry)
        record["site_id"] = site_id
        record["candidate_pool_file"] = str(pool_file.relative_to(REPO_ROOT)) if pool is not None else None
        record["candidate_pool_size"] = len(pool) if pool is not None else None

        exact = [c for c in (pool or []) if c.get("filename") == filename]
        folded = [c for c in (pool or []) if (c.get("filename") or "").casefold() == (filename or "").casefold()]
        snap_site = by_site.get(site_id or "", [])
        snap_exact = [r for r in snap_site if r["filename"] == filename]
        snap_folded = [r for r in snap_site if r["filename"].casefold() == (filename or "").casefold()]

        record["candidates_in_images_json_exact"] = [
            {"id": c["id"], "filename": c["filename"], "original_url": c.get("original_url")} for c in exact
        ]
        record["candidates_in_snapshot_exact"] = [
            {"image_id": r["id"], "filename": r["filename"], "original_url": r["original_url"]} for r in snap_exact
        ]
        record["case_only_matches"] = {
            "images_json": [c["id"] for c in folded if c not in exact],
            "snapshot": [r["id"] for r in snap_folded if r not in snap_exact],
        }

        verdict = "UNPROVABLE"
        image_id = None
        evidence: list[str] = []
        if len(exact) == 1 and len(snap_exact) == 1 and exact[0]["id"] == snap_exact[0]["id"]:
            verdict = "PROVEN"
            image_id = exact[0]["id"]
            evidence.append(
                f"images.json of the short has exactly one entry named {filename!r} (id {image_id}); "
                f"the snapshot has exactly one wiki_images row with that id, site and filename"
            )
        elif len(exact) == 1 and not snap_exact:
            # images.json knows it, the snapshot does not: the row was deleted or renamed
            # after the short was rendered. One record cannot be confirmed by a second.
            verdict = "AMBIGUOUS"
            image_id = exact[0]["id"]
            evidence.append(
                f"images.json names id {image_id}, but the 2026-09-20 snapshot has no row "
                f"with that id for this site and filename - not confirmable"
            )
        elif len(exact) == 0 and len(snap_exact) == 1 and pool is None:
            verdict = "PROVEN"
            image_id = snap_exact[0]["id"]
            evidence.append("no images.json for this short; the snapshot has exactly one such row")
        elif len(snap_exact) == 1 and len(exact) == 0:
            verdict = "AMBIGUOUS"
            image_id = snap_exact[0]["id"]
            evidence.append(
                "the snapshot has exactly one such row, but this short's candidate pool does not "
                "contain the filename, so the two records do not agree"
            )
        elif len(exact) > 1 or len(snap_exact) > 1:
            evidence.append(
                f"several rows match: images.json {len(exact)}, snapshot {len(snap_exact)}"
            )
        elif folded or snap_folded:
            evidence.append("only a case-insensitive match; the exact filename does not occur")
            image_id = (folded or snap_folded)[0]["id"]
        else:
            evidence.append("no images.json entry and no snapshot row carries this filename")

        record["verdict"] = verdict
        record["image_id"] = image_id
        record["evidence"] = evidence

        if image_id is not None:
            row = next((r for r in by_site.get(site_id or "", []) if r["id"] == image_id), None)
            if row is not None:
                # Exact case against the directory listing: `Path.is_file()` would accept a
                # case-only sibling on this NTFS checkout (common.py's module docstring).
                hit = locate(trees, site_id, row["filename"])
                if hit is not None:
                    record["resolved_path"] = str(hit[0])
                    record["is_riff_webp"] = is_webp(hit[0])[0]
                    record["disk_file_size"] = hit[1]
                else:
                    record["resolved_path"] = None
        records.append(record)

    out = OUT_DIR / "REJECTED_KINDS.jsonl"
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    counts: dict[str, int] = {}
    for record in records:
        counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
    print(f"{len(records)} rejected entries name a kind in their reason; verdicts {counts}")
    for record in records:
        print(
            f"  {record['verdict']:10} {record['kind_stated']:20} {record['slug']:34} "
            f"{record['filename'][:52]:52} id={record['image_id']}"
        )

    lines = [
        "# The 30 kind-labelled rejections: filename -> wiki_images row",
        "",
        f"Source: `video-assets/shorts/*/selection.json`, the `rejected` list. 175 rejected entries "
        f"exist in total; **{len(records)}** name a kind verbatim in their `reason` "
        f"(`{KIND_MARKER}<kind>`). Verdicts: {counts}.",
        "",
        "Method and the three outcomes: see the module docstring of "
        "`scripts/remediation/vlm_pilot/rejected_kinds.py`.",
        "",
        "| verdict | kind stated | slug | filename | image_id | evidence |",
        "|---|---|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            f"| {record['verdict']} | {record['kind_stated']} | {record['slug']} | "
            f"`{record['filename']}` | {record['image_id'] or '-'} | {'; '.join(record['evidence'])} |"
        )
    lines.append("")
    report = OUT_DIR / "REJECTED_KINDS.md"
    report.write_text("\n".join(lines), "utf-8")
    print(f"\nwrote {out}\nwrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
