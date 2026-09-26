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

    audit4.py written --run-dir R --apply-root logs/_write_apply_p4 > written.out
    audit4.py draw  --run-dir R --seed 20260922 --count 10 --written written.txt [--lane W]
                    [--exclude used.txt]
    audit4.py sheet --run-dir R --site-ids drawn.txt --out sheet.md
    audit4.py hold  --run-dir R --site <site id> --audit MIDRUN_AUDIT_VERDICTS.json

**The written list** (`written`, second review of lane WA, 2026-09-26) is the run's own: every batch
directory of the run whose write batch in the P4 apply root carries a live `APPLIED.json` (a round
revert4 took back keeps its record under `chunks/` once the gate closed or re-opened it), the sites
of that write batch's `PLAN.jsonl` (which stays what was written), less the sites the run holds
since - an audit hold, whose site the runbook takes back with `revert4 --site` before the next
draw. A write batch whose rows name another run is refused: pilots 1-3 took the batch ids pilot 4
wrote. A glob over the apply root would list another run's batches (v3d's p4-25xx beside v3's) and
the taken-back sites, and the draw would refuse them.

**A finding holds its site** (the mass run's mid-run audit, 2026-09-25). `hold` reads the auditor's
verdict file (one record per site: `site_id`, `name`, every sentence's `n`, `verdict` and `note`,
the card's `verdict` and `note` or `null`), records the site's findings as holds of the closed
list's S6b reasons in the batch that carries the site (its latest), and rewrites the run's
`HOLDS4.jsonl`: a WRONG_SITE sentence is `audit-wrong-site` and an UNSUPPORTED one
`audit-unsupported` (site scope), a NOT_CONTAINED card `audit-not-contained` (card scope); the
detail names the file, its sha256 and the finding. A held site is planned by no one again
(`write4.plan_p4` refuses it; `write_gate4` accepts its batch's re-plan once `revert4.py --site`
took its written rows back) and leaves the reviewed population the samples are drawn from. It
refuses a site the file does not judge exactly once, a verdict outside the audit's vocabulary, a
record whose name is not the site's, a site outside the run, and a record without a finding:
nothing is written then. The command is explicit - it names the site and the file - and appends
only what is not there yet, so a second run adds nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3.run import InputError  # noqa: E402

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import mass4 as M4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import review4 as RV  # noqa: E402
from phase4 import run4 as R4  # noqa: E402
from phase4 import write4 as W4  # noqa: E402 - the write batch's plan and its written record

SENTENCE_VERDICTS = "SUPPORTED | UNSUPPORTED | WRONG_SITE"
CARD_VERDICTS = "CONTAINED | NOT_CONTAINED"
#: The findings that hold, by the closed list's S6b reasons: a sentence's hold the site, a card's
#: only the card.
SENTENCE_HOLDS: Mapping[str, M.HoldReason] = {
    "UNSUPPORTED": M.HoldReason.AUDIT_UNSUPPORTED,
    "WRONG_SITE": M.HoldReason.AUDIT_WRONG_SITE,
}
CARD_HOLDS: Mapping[str, M.HoldReason] = {"NOT_CONTAINED": M.HoldReason.AUDIT_NOT_CONTAINED}


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


def written_sites(run_dir: Path, apply_root: Path) -> list[str]:
    """The run's sites the write gate wrote and did not take back, sorted (the module's "written
    list"). A write batch of one of the run's batch ids that another run wrote is refused."""
    found: set[str] = set()
    for batch_dir in sorted(p for p in run_dir.iterdir() if (p / M.INPUT_FILE).exists()):
        out = apply_root / batch_dir.name
        if not (out / W4.APPLIED_FILE).exists():
            continue
        rows = W4.read_plan(out, group=W4.Group.P4)
        runs = sorted({str(row.evidence.get("run")) for row in rows} - {run_dir.name})
        if runs:
            raise InputError(f"{out.name}: written from run(s) {runs}, not {run_dir.name}")
        found |= {row.site_id for row in rows} - B.site_held(B.read_holds(batch_dir))
    return sorted(found)


def cmd_written(args: argparse.Namespace) -> int:
    for site_id in written_sites(Path(args.run_dir), Path(args.apply_root)):
        print(site_id)
    return 0


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


# ---------------------------------------------------------------------------------- the holds


def audit_holds(record: Mapping[str, Any], *, source: str) -> list[M.Hold]:
    """The holds one site's audit record carries (`SENTENCE_HOLDS`, `CARD_HOLDS`), in its order; a
    verdict outside the audit's vocabulary is refused, never read as a pass."""
    site_id = record["site_id"]
    holds: list[M.Hold] = []
    for sentence in record["sentences"]:
        verdict = sentence["verdict"]
        if verdict not in SENTENCE_VERDICTS.split(" | "):
            raise InputError(f"{site_id}: {verdict!r} is not a sentence verdict")
        if verdict in SENTENCE_HOLDS:
            holds.append(
                M.Hold(
                    site_id=site_id,
                    scope=M.HoldScope.SITE,
                    reason=SENTENCE_HOLDS[verdict],
                    detail=f"{source}: sentence {sentence['n']} {verdict}: {sentence['note']}",
                )
            )
    card = record["card"]
    if card is not None:
        verdict = card["verdict"]
        if verdict not in CARD_VERDICTS.split(" | "):
            raise InputError(f"{site_id}: {verdict!r} is not a card verdict")
        if verdict in CARD_HOLDS:
            holds.append(
                M.Hold(
                    site_id=site_id,
                    scope=M.HoldScope.CARD,
                    reason=CARD_HOLDS[verdict],
                    detail=f"{source}: card {verdict}: {card['note']}",
                )
            )
    return holds


def site_batch(run_dir: Path, site_id: str) -> tuple[Path, M.PlanSite]:
    """The batch that carries the site - its latest, where a re-queued site counts
    (`run4.aggregate_holds`) - and its plan record."""
    found = [
        (batch_dir, site)
        for batch_dir in sorted(p for p in run_dir.iterdir() if (p / M.INPUT_FILE).exists())
        for site in B.read_batch(batch_dir)[1]
        if site.site_id == site_id
    ]
    if not found:
        raise InputError(f"{site_id} is not a site of {run_dir}")
    return found[-1]


def cmd_hold(args: argparse.Namespace) -> int:
    """Hold one site for what the audit file found on it (see the module docstring)."""
    run_dir, audit = Path(args.run_dir), Path(args.audit)
    body = audit.read_bytes()
    records = [record for record in json.loads(body) if record["site_id"] == args.site]
    if len(records) != 1:
        raise InputError(f"{audit.name}: {len(records)} verdict record(s) for {args.site}, not one")
    (record,) = records
    batch_dir, site = site_batch(run_dir, args.site)
    if record["name"] != site.name:
        raise InputError(f"{audit.name} judges {record['name']!r}; {args.site} is {site.name!r}")
    source = f"{audit.name} sha256 {hashlib.sha256(body).hexdigest()}"
    holds = audit_holds(record, source=source)
    if not holds:
        raise InputError(
            f"{audit.name} names no UNSUPPORTED, WRONG_SITE or NOT_CONTAINED finding for "
            f"{args.site}: nothing holds it"
        )
    added = B.append_holds(batch_dir, holds)
    total = R4.write_holds4(run_dir)
    reasons = ", ".join(f"{hold.reason.value} ({hold.scope.value})" for hold in holds)
    print(
        f"held {args.site} ({site.name}) in {batch_dir.name}: {reasons}; {added} new line(s) in "
        f"its {M.HOLDS_FILE}, {len(holds) - added} there already; {R4.HOLDS4_FILE}: {len(total)} "
        "hold(s)"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phase4-audit", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    written = sub.add_parser("written", help="print the run's written site ids (the draw's input)")
    written.add_argument("--run-dir", required=True)
    written.add_argument("--apply-root", required=True, help="the P4 apply root")
    written.set_defaults(func=cmd_written)
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
    hold = sub.add_parser("hold", help="hold one site for the findings of an audit verdict file")
    hold.add_argument("--run-dir", required=True)
    hold.add_argument("--site", required=True, help="the site id the audit found on")
    hold.add_argument("--audit", required=True, help="the auditor's verdict file (JSON)")
    hold.set_defaults(func=cmd_hold)
    return parser


def main(argv: list[str] | None = None) -> int:
    R4.utf8_streams()
    args = build_parser().parse_args(argv)
    code = int(args.func(args))
    print(f"{R4.STAGE_EXIT}{code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
