"""Shared fixtures for lane WN's and the site-list runs' tests (2026-10-01): sites without a
description, answers of the write round as a Sonnet agent writes them, a Phase-4 site, and a whole
run end to end.

Not a test module (no `test_` prefix). Builds on `wc_fixtures` (the fake page server, the read
runner, the verification and judge rounds): nothing here opens a socket, calls a model or touches a
database.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.remediation import wc_fixtures as FX
from tests.remediation.wc_fixtures import OH, WC4, M

#: Sites that have no description: NULL, blank, and one that keeps a raw_data without WC's keys.
SITE_N = "1a000000-0000-4000-8000-00000000000a"
SITE_BLANK = "1b000000-0000-4000-8000-00000000000b"
SITE_EMPTY = "1c000000-0000-4000-8000-00000000000c"  #: the agent finds nothing: no sentence
SITE_BAD = (
    "1d000000-0000-4000-8000-00000000000d"  #: one of its sentences has a quote that is no page
)

#: Three sentences about the Tarxien Temples, each in its own words and standing alone.
W1 = "The Tarxien Temples form an archaeological complex in the town of Tarxien on Malta."
W2 = "Archaeologists date the monuments to approximately 3150 BC."
W3 = "Themistocles Zammit led the excavations at the site in 1915."
Q_W1 = FX.Q_COMPLEX
Q_W2 = FX.Q_DATE
Q_W3 = FX.Q_ZAMMIT

#: A Phase-4 text of three sentences, as lane W wrote it, with its provenance: sentences 1-3 of the
#: pinned page (`phase4_write_fixtures.TEXT`), one source.
P4_TEXT = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
    "They date to approximately 3150 BC [1]. "
    "The site was excavated by Themistocles Zammit in 1915 [1]."
)
P4_SENTENCES = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta.",
    "They date to approximately 3150 BC.",
    "The site was excavated by Themistocles Zammit in 1915.",
)


def wn_row(
    site_id: str, description: str | None = None, *, raw_data: dict | None = None, name: str = ""
) -> dict[str, Any]:
    """A curated site without a description as the read returns it (`description` NULL or blank)."""
    return FX.row(site_id, description, raw_data=raw_data, name=name or "Tarxien Temples")


def sentence(
    text: str, *quotes: dict[str, str], note: str = "each quote supports its claim"
) -> dict:
    return {"text": text, "quotes": list(quotes), "note": note}


def written(site_id: str, *sentences: dict, note: str = "searched the web") -> str:
    """A write answer."""
    return json.dumps({"site_id": site_id, "sentences": list(sentences), "note": note},
                      ensure_ascii=False)  # fmt: skip


def good(site_id: str) -> str:
    """Three sentences, each on its quote."""
    return written(site_id, sentence(W1, Q_W1), sentence(W2, Q_W2), sentence(W3, Q_W3))


def nothing(site_id: str) -> str:
    """The agent finds no reputable page: no sentence, the site stays empty."""
    return written(site_id, note="no page names this site")


def record_written(
    handoff: Path,
    answers: Mapping[str, str],
    *,
    by: str = "sonnet-write",
    model: str = OH.SONNET_MODEL,
) -> None:
    """Write each site's answer where its question was exported, as `opus_handoff.py answer
    --model claude-sonnet-5-5` records it."""
    for line in OH.manifest(handoff):
        if line["label"] in answers:
            OH.write_answer(
                handoff,
                model=model,
                batch_id=line["batch_id"],
                stage=line["stage"],
                label=line["label"],
                text=answers[line["label"]],
                answered_by=f"{by}-{line['batch_id']}",
                now=lambda: "2026-10-01T12:00:00+00:00",
            )


def p4_site_raw(description: str = P4_TEXT, *, card: bool = False) -> dict[str, Any]:
    """`raw_data` of a Phase-4 text: its citation list and its lane-W provenance (three published
    sentences of one pinned source, aligned with the text's three sentences)."""
    from tests.remediation import phase4_write_fixtures as PFX

    base = PFX.assembly(description=description, card=PFX.CARD if card else None)
    third = (PFX.TEXT.index("The site"), len(PFX.TEXT))
    provenance = base.provenance
    sentences = (
        *provenance.sentences,
        M.PublishedSentence(n=1, src="W", start=third[0], end=third[1], drop=()),
    )
    import dataclasses

    provenance = dataclasses.replace(provenance, sentences=sentences)
    return {
        M.CITATIONS_KEY: [c.to_dict() for c in base.citations],
        M.PROVENANCE_KEY: provenance.to_dict(),
    }


def build_wn_run(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    answers: Mapping[str, str],
    *,
    name: str = "wn-test",
    pilot: bool = True,
    judged: bool = True,
    first_batch: int = WC4.FIRST_BATCH,
    after: Sequence[Path] = (),
    writer_model: str = OH.SONNET_MODEL,
    verifier_model: str = OH.OPUS_MODEL,
) -> tuple[Path, Path]:
    """A lane-WN run end to end: read, export (a pilot that draws the whole population, or a chunk),
    write answers, import, verify (every kept sentence SUPPORTED), build; a pilot is judged and passes
    unless `judged` is false. Returns the run directory and its gate plan (`WC4.jsonl`)."""
    from phase3.run import read_jsonl
    from wc import cli

    run, handoff = root / "runs" / name, root / "handoff" / f"{name}-w"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    asked, _ = cli.population(
        read_jsonl(run / cli.ROWS_FILE), excluded=set(), earlier=set(), kind=cli.KIND_WN
    )
    draw = {"pilot": len(asked), "seed": 1} if pilot else {"pilot": None, "seed": None}
    cli.cmd_export(run, handoff, batch_size=5, exclude=None, after=list(after), wn=True, **draw)
    record_written(handoff, answers, model=writer_model)
    cli.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    FX.verify_all(run, root / "handoff" / f"{name}-verify", model=verifier_model)
    cli.cmd_build(run, first_batch=first_batch)
    if pilot and judged:
        FX.judge_all(run, root / "handoff" / f"{name}-judge")
    return run, run / cli.PLAN_FILE


def build_list_run(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    sites: Sequence[str],
    answers: Mapping[str, str],
    *,
    name: str = "wcl-test",
    pilot: bool = False,
    judged: bool = True,
    first_batch: int = WC4.FIRST_BATCH,
    after: Sequence[Path] = (),
    defect_lines: Sequence[Mapping[str, Any]] = (),
) -> tuple[Path, Path]:
    """A site-list run end to end (`export --sites`): read, export the listed sites (a pilot that
    draws every one of them, or a chunk), answer the check (`wc_fixtures.record_answers`), import,
    verify (every kept sentence SUPPORTED), build; a pilot is judged. Returns the run directory and
    its gate plan."""
    from wc import cli

    run, handoff = root / "runs" / name, root / "handoff" / f"{name}-r1"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    listing = root / f"{name}.sites.txt"
    defects = None
    if defect_lines:  # the list is the one `defect-sites` builds, and its report goes to the export
        found = root / f"{name}.defects.jsonl"
        found.write_text(
            "".join(json.dumps(line) + "\n" for line in defect_lines), encoding="utf-8"
        )
        cli.cmd_defect_sites(run, [found], listing)
        defects = listing.with_name(listing.name + ".report.json")
        assert listing.read_text(encoding="utf-8").split() == sorted(sites)
    else:
        listing.write_text("".join(f"{site}\n" for site in sites), encoding="utf-8", newline="\n")
    from phase3.run import read_jsonl

    asked, _ = cli.population(
        read_jsonl(run / cli.ROWS_FILE), excluded=set(), earlier=set(), kind=cli.KIND_LIST,
        only=set(sites),
    )  # fmt: skip
    draw = {"pilot": len(asked), "seed": 1} if pilot else {"pilot": None, "seed": None}
    cli.cmd_export(
        run, handoff, batch_size=5, exclude=None, after=list(after), sites=listing,
        defects=defects, **draw,
    )  # fmt: skip
    FX.record_answers(handoff, answers, by="sonnet-check")
    cli.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    FX.verify_all(run, root / "handoff" / f"{name}-verify")
    cli.cmd_build(run, first_batch=first_batch)
    if pilot and judged:
        FX.judge_all(run, root / "handoff" / f"{name}-judge")
    return run, run / cli.PLAN_FILE
