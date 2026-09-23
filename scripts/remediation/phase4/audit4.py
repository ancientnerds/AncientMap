"""S6b helper: seeded samples for the independent audit, and one audit sheet per site.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, pipeline "S6b
INDEPENDENT AUDIT" and verification "INDEPENDENT AUDIT", pilot_and_thresholds. Work item WB-B4.

The audit is the Claude Code session, a different model family, and not a pipeline module. This
helper only draws the samples (the whole pilot; every lane-T and lane-R site before it may be
written; 10 random written sites after every 500; a final 60, excluding the pilot and the mid-run
samples) and renders what the auditor judges: every published sentence beside its pinned passage
(`SUPPORTED`, `UNSUPPORTED` or `WRONG_SITE`) and the card beside the description (`CONTAINED` or
`NOT_CONTAINED`). **The reviewer's verdicts are never shown**: the sheet is built from the site, its
assembly and the pinned texts, and from nothing under `reviews/`.

The population is what a finished review kept (`reviewed_sites`: a batch `mass4.batch_done` counts
as done, minus the sites a site-scope hold keeps unwritten). A draw is taken from the sites written
to the database, which `--written` lists (the journal's, or `verify_writes4`'s read-back): the
mid-run and final samples are samples of written sites. A draw is seeded and deterministic: the same
ids, seed, count and exclusions give the same sample on every machine. A stratum with fewer sites
than the count is taken whole.

    audit4.py draw  --run-dir R --seed 20260922 --count 10 --written written.txt [--lane W]
                    [--exclude used.txt]
    audit4.py sheet --run-dir R --site-ids drawn.txt --out sheet.md
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3.run import InputError  # noqa: E402

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import mass4 as M4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import review4 as RV  # noqa: E402
from phase4 import run4 as R4  # noqa: E402

SENTENCE_VERDICTS = "SUPPORTED | UNSUPPORTED | WRONG_SITE"
CARD_VERDICTS = "CONTAINED | NOT_CONTAINED"


def draw_sample(site_ids: Sequence[str], *, seed: int, count: int, exclude: set[str]) -> list[str]:
    """`count` ids drawn with `random.Random(seed)` from the sorted, de-duplicated ids that are not
    excluded, returned sorted. Fewer ids than `count` are taken whole."""
    if count < 1:
        raise InputError(f"a sample of {count} is no sample")
    pool = sorted(set(site_ids) - exclude)
    if len(pool) <= count:
        return pool
    return sorted(random.Random(seed).sample(pool, count))  # noqa: S311 - a seeded draw, not a key


def audit_sheet(site: M.PlanSite, assembly: M.Assembly, *, texts: Mapping[str, str]) -> str:
    """One site's sheet: the site, its sources, every sentence beside its passage, and the card."""
    provenance = assembly.provenance
    lines = [
        f"## {site.name} ({site.site_id}) - lane {provenance.lane.value}, {provenance.ai.value}",
        "",
        f"- stored: {site.country or '-'}, {site.site_type or '-'}, {site.lat}, {site.lon}",
        f"- aliases: {'; '.join(site.aliases) or '-'}",
    ]
    lines += [f"- [{c.n}] {c.title} - {c.url} ({c.license.value})" for c in assembly.citations]
    rows = RV.passages(assembly, A.published_sentences(assembly), texts)
    for number, (published, source, before, section) in enumerate(rows, start=1):
        cut = provenance.sentences[number - 1]
        lines += [
            "",
            f"### Sentence {number} - {cut.src} [{cut.start}:{cut.end}], section {section or 'lead'}",
            "",
            f"- published: {published}",
            f"- passage: {source}",
            f"- before it: {before or '-'}",
            f"- verdict: {SENTENCE_VERDICTS}",
        ]
    lines += ["", "### Card", ""]
    if assembly.card is None:
        lines.append("- no card is written for this site")
    else:
        lines += [f"- card: {assembly.card}", f"- verdict: {CARD_VERDICTS}"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------- the run


def reviewed_sites(run_dir: Path) -> dict[str, tuple[Path, M.Assembly]]:
    """Every site a finished review kept, `id -> (batch, row)`: the `assembly.jsonl` of each batch
    `mass4.batch_done` counts as done (the reviewer answered over that very file), minus the sites
    a site-scope hold keeps unwritten (a hold appended after the review counts)."""
    found: dict[str, tuple[Path, M.Assembly]] = {}
    for batch_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if not M4.batch_done(run_dir, batch_dir.name)[0]:
            continue
        held = B.site_held(B.read_holds(batch_dir))
        for assembly in M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly):
            if assembly.site_id in found:
                raise InputError(f"{assembly.site_id} is assembled in two batches")
            if assembly.site_id not in held:
                found[assembly.site_id] = (batch_dir, assembly)
    return found


def _ids(path: str | None) -> set[str]:
    if not path:
        return set()
    return {
        line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()
    }


def cmd_draw(args: argparse.Namespace) -> int:
    """A sample of the sites written to the database (the mid-run 10 after every 500, the final
    60): `--written` lists them (the journal's, or `verify_writes4`'s read-back). Every written id
    that is not excluded must be a reviewed site of this run - a written site this run never
    reviewed is a wrong input, not a smaller population."""
    sites = reviewed_sites(Path(args.run_dir))
    exclude = _ids(args.exclude)
    written = _ids(args.written) - exclude
    unreviewed = sorted(written - set(sites))
    if unreviewed:
        raise InputError(f"written but not reviewed in this run: {unreviewed}")
    ids = [
        site_id
        for site_id in sorted(written)
        if args.lane is None or sites[site_id][1].provenance.lane.value == args.lane
    ]
    for site_id in draw_sample(ids, seed=args.seed, count=args.count, exclude=exclude):
        print(site_id)
    return 0


def cmd_sheet(args: argparse.Namespace) -> int:
    sites = reviewed_sites(Path(args.run_dir))
    wanted = sorted(_ids(args.site_ids))
    unknown = [site_id for site_id in wanted if site_id not in sites]
    if unknown:
        raise InputError(f"not reviewed in this run: {unknown}")
    sheets: list[str] = []
    for site_id in wanted:
        batch_dir, assembly = sites[site_id]
        _, plan_sites = B.read_batch(batch_dir)
        site = next(s for s in plan_sites if s.site_id == site_id)
        texts = {
            source.id: B.read_source(batch_dir, site_id, source.id)[1]
            for source in assembly.provenance.sources
        }
        sheets.append(audit_sheet(site, assembly, texts=texts))
    B.write_text_atomic(Path(args.out), "\n".join(sheets))
    print(f"{len(sheets)} sheet(s) in {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phase4-audit", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    draw = sub.add_parser("draw", help="print a seeded sample of written site ids")
    draw.add_argument("--run-dir", required=True)
    draw.add_argument("--seed", type=int, required=True)
    draw.add_argument("--count", type=int, required=True)
    draw.add_argument("--written", required=True, help="a file of the ids written to the database")
    draw.add_argument("--lane", choices=[lane.value for lane in M.ASSIGNED_LANES], default=None)
    draw.add_argument("--exclude", default=None, help="a file of ids already sampled")
    draw.set_defaults(func=cmd_draw)
    sheet = sub.add_parser("sheet", help="render the audit sheets of the listed sites")
    sheet.add_argument("--run-dir", required=True)
    sheet.add_argument("--site-ids", required=True)
    sheet.add_argument("--out", required=True)
    sheet.set_defaults(func=cmd_sheet)
    return parser


def main(argv: list[str] | None = None) -> int:
    R4.utf8_streams()
    args = build_parser().parse_args(argv)
    code = int(args.func(args))
    print(f"{R4.STAGE_EXIT}{code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
