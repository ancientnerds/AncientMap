"""Apply the picked gallery to the Shining Ones paper.

Reads C:/tmp/meaningful/gallery.json + the paper's current report from DB,
rebuilds the markdown with the meaningful galleries substituted for the
existing misleading-heavy image blocks, and writes back via the DB tunnel.

Images reference remote Wikimedia/Met URLs directly — no local download step,
since the paper is served by the API which proxies image tags unchanged.

Run:
    python scripts/apply_meaningful_gallery.py              # dry run — writes preview
    python scripts/apply_meaningful_gallery.py --write      # commit to DB

Dry-run writes:
    C:/tmp/meaningful/patched_report.md — new report body for eyeballing
    C:/tmp/meaningful/patched_report.diff — unified diff vs current DB value
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import pathlib
import re
import sys

for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PAPER_ID = "edfff317-5240-42d1-9dec-1ad6a5805d9a"
OUT_DIR = pathlib.Path(r"C:/tmp/meaningful")

# Same regex the assessor uses — matches one full image-caption-source block.
IMAGE_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)\s*\n+"
    r"\*(?P<caption>[^*]+)\*\s*\n+"
    r"\[Source\]\((?P<source_url>[^)]+)\)",
    re.MULTILINE,
)


def _encode_parens(url: str) -> str:
    """Percent-encode literal parens so markdown doesn't truncate URLs at ')'."""
    return url.replace("(", "%28").replace(")", "%29") if url else url


def render_block(pick: dict, gallery_id: str | None = None) -> str:
    """Render one gallery pick as the standard image-caption-source markdown.

    When `gallery_id` is provided, prefixes the alt text with
    `gallery:<id>|` so the frontend TheoCarousel groups adjacent
    gallery-tagged images into a carousel instead of a stacked mosaic.
    """
    alt = (pick.get("alt") or "Research image").replace("]", "").strip()[:140]
    if gallery_id:
        alt = f"gallery:{gallery_id}|{alt}"
    src = _encode_parens(pick["image_url"])
    caption = pick["caption"]
    if not caption.startswith("*"):
        caption = f"*{caption.strip('*')}*"
    source = _encode_parens(pick["source_url"])
    return f"![{alt}]({src})\n\n{caption}\n[Source]({source})"


def split_refs(report: str) -> tuple[str, str]:
    """Split the report at the References heading so we only touch the prose."""
    m = re.search(r"^##\s+References\b", report, re.MULTILINE)
    if not m:
        return report, ""
    return report[: m.start()], report[m.start() :]


def rebuild_report(report: str, gallery: list[dict]) -> str:
    """Replace every paragraph-following image cluster with its gallery picks.

    Strategy:
    1. Split the report at the References heading (we never touch refs).
    2. Walk image blocks in order; for each, find the paragraph immediately
       preceding the FIRST image of a contiguous run.
    3. Match that paragraph against the gallery (by first 100 chars).
    4. Replace the whole run with the gallery's picks (or nothing if empty).
    """
    prose, refs = split_refs(report)

    # Build paragraph -> picks lookup, keyed by first 100 chars.
    def pkey(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()[:100]

    picks_by_para: dict[str, list[dict]] = {}
    for entry in gallery:
        picks_by_para[pkey(entry["paragraph"])] = entry.get("picks") or []

    # Find contiguous runs of image blocks. A run is a cluster of adjacent
    # image-caption-source blocks separated only by whitespace.
    block_spans: list[tuple[int, int]] = []
    for m in IMAGE_BLOCK_RE.finditer(prose):
        block_spans.append(m.span())

    if not block_spans:
        return report

    # Group into runs: spans where the gap between them is only whitespace.
    runs: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    for span in block_spans:
        if not current:
            current = [span]
            continue
        gap = prose[current[-1][1] : span[0]]
        if gap.strip() == "":
            current.append(span)
        else:
            runs.append(current)
            current = [span]
    if current:
        runs.append(current)

    # For each run, identify its anchor paragraph (the prose block immediately
    # before the first image), look up picks, and record a replacement.
    # Apply replacements from END to START so offsets stay valid.
    replacements: list[tuple[int, int, str]] = []
    for run in runs:
        first_start = run[0][0]
        last_end = run[-1][1]
        # Strip any prior image blocks from the lead-up, same as the assessor.
        before = IMAGE_BLOCK_RE.sub("", prose[:first_start]).rstrip()
        blank = before.rfind("\n\n")
        paragraph = (before[blank:] if blank > 0 else before).strip()
        paragraph = re.sub(r"\s+", " ", paragraph)[:1200]

        picks = picks_by_para.get(pkey(paragraph), [])
        if picks:
            # When the paragraph gets 2+ picks, emit a gallery:<hash>| marker
            # so the frontend renders them as a carousel rather than a stack.
            gallery_id = (
                hashlib.sha1(paragraph.encode("utf-8")).hexdigest()[:8]
                if len(picks) > 1
                else None
            )
            new_md = "\n\n".join(render_block(p, gallery_id) for p in picks)
        else:
            new_md = ""  # empty paragraph → drop images entirely
        replacements.append((first_start, last_end, new_md))
        print(
            f"  paragraph: {paragraph[:60]!r}... "
            f"run=[{len(run)} blocks] -> picks={len(picks)}"
        )

    # Apply replacements end-to-start.
    new_prose = prose
    for start, end, repl in sorted(replacements, key=lambda r: -r[0]):
        # Keep a blank line before and after the replacement so mosaic/figure
        # parsing on the frontend treats it as its own block.
        before_text = new_prose[:start].rstrip()
        after_text = new_prose[end:].lstrip("\n")
        sep_before = "\n\n" if before_text else ""
        sep_after = "\n\n" if repl else "\n\n"
        new_prose = before_text + sep_before + repl + sep_after + after_text

    # Collapse any resulting runs of >2 blank lines.
    new_prose = re.sub(r"\n{3,}", "\n\n", new_prose).rstrip() + "\n"
    return new_prose + ("\n" + refs if refs else "")


def fetch_current_report() -> str:
    import psycopg2

    conn = psycopg2.connect(
        host="localhost", port=15432,
        user="ancient_map", password="ancient_map_dev_password",
        dbname="ancient_map",
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT result_json FROM research_requests WHERE id = %s",
            (PAPER_ID,),
        )
        raw = cur.fetchone()[0]
        d = raw if isinstance(raw, dict) else json.loads(raw)
        return d.get("report") or ""
    finally:
        conn.close()


def write_new_report(new_report: str) -> None:
    import psycopg2

    conn = psycopg2.connect(
        host="localhost", port=15432,
        user="ancient_map", password="ancient_map_dev_password",
        dbname="ancient_map",
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT result_json FROM research_requests WHERE id = %s",
            (PAPER_ID,),
        )
        raw = cur.fetchone()[0]
        result = raw if isinstance(raw, dict) else json.loads(raw)
        result["report"] = new_report
        from datetime import UTC, datetime

        result["edited_at"] = datetime.now(UTC).isoformat()
        cur.execute(
            "UPDATE research_requests SET result_json = %s WHERE id = %s",
            (json.dumps(result), PAPER_ID),
        )
        conn.commit()
        print(f"  DB: wrote {len(new_report)} chars to result_json.report")
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="commit to DB (default: dry run)")
    args = ap.parse_args()

    gallery = json.loads((OUT_DIR / "gallery.json").read_text(encoding="utf-8"))
    print(f"Gallery: {len(gallery)} paragraphs, "
          f"{sum(len(r.get('picks', [])) for r in gallery)} total picks")

    current = fetch_current_report()
    print(f"Current report: {len(current)} chars, "
          f"{len(list(IMAGE_BLOCK_RE.finditer(current)))} image blocks")

    new_report = rebuild_report(current, gallery)
    print(
        f"New report: {len(new_report)} chars, "
        f"{len(list(IMAGE_BLOCK_RE.finditer(new_report)))} image blocks"
    )

    (OUT_DIR / "patched_report.md").write_text(new_report, encoding="utf-8")
    diff = "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            new_report.splitlines(),
            fromfile="current",
            tofile="patched",
            lineterm="",
        )
    )
    (OUT_DIR / "patched_report.diff").write_text(diff, encoding="utf-8")
    print(f"-> {OUT_DIR / 'patched_report.md'}")
    print(f"-> {OUT_DIR / 'patched_report.diff'} ({len(diff.splitlines())} diff lines)")

    if args.write:
        print("\nWriting to DB...")
        write_new_report(new_report)
        print("Done. Verify via:")
        print("  curl 'http://localhost:18000/api/theo/public/"
              "the-shining-ones-sky-gods-ancient-astronauts-and-human-genius' | head -c 500")
    else:
        print("\nDry run. Re-run with --write to commit.")


if __name__ == "__main__":
    main()
