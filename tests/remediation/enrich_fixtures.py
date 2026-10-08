"""Shared fixtures for lane E's tests (the enrichment, 2026-10-09): a Phase-4 text, a checked March
text and a lane-N text as production holds them, the pages the fake server serves for the new
sentences, answers of the enrich round as a Sonnet agent writes them, and a whole run end to end.

Not a test module (no `test_` prefix). Builds on `wc_fixtures` and `wn_fixtures`: nothing here opens a
socket, calls a model or touches a database.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.remediation import wc_fixtures as FX  # first: it puts scripts/remediation on sys.path
from tests.remediation import wn_fixtures as WX
from tests.remediation.wc_fixtures import OH, WC4

#: A Phase-4 text (lane W, three sentences) and a checked March text (lane L, with its check record)
#: and a lane-N text (written from the web), the three kinds of base an enrichment is appended to.
SITE_W = "2a000000-0000-4000-8000-00000000000a"
SITE_L = "2b000000-0000-4000-8000-00000000000b"
SITE_N = "2c000000-0000-4000-8000-00000000000c"
SITE_NONE = "2d000000-0000-4000-8000-00000000000d"  #: the agent finds nothing to append
SITE_BAD = "2f000000-0000-4000-8000-00000000000f"  #: one sentence lost its quote at the import

#: The pages the new sentences quote: a research page (a fact and an open matter) and the permalink
#: of the pinned revision of the Phase-4 text (a page the base already cites).
RESEARCH = "https://www.example.edu/malta/tarxien-research"
PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567"
POSITIONS = "https://www.example.edu/malta/tarxien-dating"
PAGES: dict[str, str] = {
    **FX.PAGES,
    RESEARCH: (
        "<html><body><h1>Tarxien Research</h1><p>The spiral reliefs at Tarxien are carved into "
        "limestone slabs.</p><p>Scholars have not settled whether the alignment of the south temple "
        "served as a calendar.</p></body></html>"
    ),
    PERMALINK: (
        "<html><head><title>Tarxien Temples - Wikipedia</title></head><body><p>The temple complex "
        "has four main structures that stand side by side.</p></body></html>"
    ),
    POSITIONS: (
        "<html><body><h1>Dating Tarxien</h1><p>Excavators place the first phase near 3600 BC.</p>"
        "<p>Radiocarbon specialists argue that the first phase belongs near 3150 BC.</p></body></html>"
    ),
}

#: The new sentences, each in its own words and standing alone.
FACT = "Spiral reliefs decorate limestone slabs inside the temples."
HOOK = "Whether the south temple's alignment served as a calendar remains undecided."
FACT_PERMALINK = "Four main structures of the complex stand side by side."
POSITION_A = "Excavators place the first building phase near 3600 BC."
POSITION_B = "Radiocarbon specialists date the first phase to about 3150 BC."
Q_FACT = FX.quote(RESEARCH, "The spiral reliefs at Tarxien are carved into limestone slabs.",
                  "Tarxien Research")  # fmt: skip
Q_HOOK = FX.quote(
    RESEARCH,
    "Scholars have not settled whether the alignment of the south temple served as a calendar.",
    "Tarxien Research",
)
Q_PERMALINK = FX.quote(
    PERMALINK, "The temple complex has four main structures that stand side by side."
)
Q_A = FX.quote(POSITIONS, "Excavators place the first phase near 3600 BC.", "Dating Tarxien")
Q_B = FX.quote(
    POSITIONS, "Radiocarbon specialists argue that the first phase belongs near 3150 BC.",
    "Dating Tarxien",
)  # fmt: skip


def answered_by(role: str, agent: str) -> str:
    """`answered_by` as `opus_handoff.py answer --role` records it: `<role>:<agent>` (the registry
    is `scripts/remediation/roles.py`; `wc_fixtures` has put its directory on `sys.path`)."""
    import roles

    return roles.answered_by(role, agent)


def pages_client() -> FX.FakeClient:
    return FX.FakeClient(PAGES)


def p4_row(site_id: str = SITE_W, *, text: str = WX.P4_TEXT, name: str = "Tarxien Temples") -> dict:
    """A shown site with a Phase-4 text of lane W (three aligned published sentences)."""
    return FX.row(site_id, text, raw_data=WX.p4_site_raw(text), name=name)


def sentence(
    kind: str, text: str, *quotes: dict[str, str], note: str = "each quote supports its claim"
) -> dict:
    return {"class": kind, "text": text, "quotes": list(quotes), "note": note}


def answer(site_id: str, *sentences: dict, note: str = "searched the web") -> str:
    return json.dumps(
        {"site_id": site_id, "sentences": list(sentences), "note": note}, ensure_ascii=False
    )


def good(site_id: str) -> str:
    """One fact and the open question."""
    return answer(site_id, sentence("fact", FACT, Q_FACT), sentence("open_question", HOOK, Q_HOOK))


def nothing(site_id: str) -> str:
    return answer(site_id, note="no reputable page frames anything about this site as open")


def record_enriched(
    handoff: Path,
    answers: Mapping[str, str],
    *,
    role: str = "field_researcher",
    model: str = OH.SONNET_MODEL,
    agent: str = "sonnet-enrich",
) -> None:
    """Write each site's answer where its question was exported, as `opus_handoff.py answer --role
    field_researcher --model claude-sonnet-5-5` records it."""
    for line in OH.manifest(handoff):
        if line["label"] in answers:
            OH.write_answer(
                handoff,
                model=model,
                batch_id=line["batch_id"],
                stage=line["stage"],
                label=line["label"],
                text=answers[line["label"]],
                answered_by=answered_by(role, f"{agent}-{line['batch_id']}"),
                now=lambda: "2026-10-09T12:00:00+00:00",
            )


def verify_enriched(
    run: Path,
    handoff: Path,
    *,
    verdicts: Mapping[str, Sequence[str]] | None = None,
    role: str = "web_verifier",
    model: str = OH.SONNET_MODEL,
    agent: str = "sonnet-wc-verify",
    coherent: Mapping[str, tuple[bool, Sequence[int]]] | None = None,
) -> dict[str, Any] | None:
    """One verification round, answered by a new Sonnet agent in the role of the web verifier: every
    new sentence SUPPORTED unless `verdicts` says otherwise, every text coherent."""
    from wc import cli

    try:
        cli.cmd_verify_export(run, handoff, batch_size=5)
    except cli.WcRunError as exc:
        if "nothing to verify" not in str(exc):
            raise
        return None
    record = cli._verify_round_of(run, handoff)
    answers = {}
    for label, shown in record["shown"].items():
        flag, broken = (coherent or {}).get(label, (True, ()))
        answers[label] = FX.verification(
            label, (verdicts or {}).get(label, ["SUPPORTED"] * len(shown)),
            coherent=flag, broken=broken,
        )  # fmt: skip
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff,
            model=model,
            batch_id=line["batch_id"],
            stage=line["stage"],
            label=line["label"],
            text=answers[line["label"]],
            answered_by=answered_by(role, f"{agent}-{line['batch_id']}"),
            now=lambda: "2026-10-09T13:00:00+00:00",
        )
    return cli.cmd_verify_import(run, handoff, client=pages_client(), pace=0.0)


def judge_enriched(
    run: Path,
    handoff: Path,
    *,
    invented: Sequence[str] = (),
    role: str = "pilot_judge",
    model: str = OH.OPUS_MODEL,
    agent: str = "opus-wc-judge",
) -> dict[str, Any]:
    """The pilot's judge round, answered by a fresh Opus agent in the role of the pilot judge: every
    kept sentence SUPPORTED (the open questions of the sites in `invented` INVENTED), every removed
    one DROP_OK, every text coherent."""
    from wc import cli
    from wc import enrich as E

    cli.cmd_judge_export(run, handoff, batch_size=5)
    answers = {}
    for site_id, final in cli._finals(run).items():
        kept, dropped, hooks = E.judge_counts(final)
        answers[site_id] = json.dumps({
            "site_id": site_id,
            "kept": [
                {"k": k, "quotes": [], "note": "judged",
                 "verdict": "INVENTED" if site_id in invented and k in hooks else "SUPPORTED"}
                for k in range(1, kept + 1)
            ],
            "dropped": [{"d": d, "verdict": "DROP_OK", "quotes": [], "note": "judged"}
                        for d in range(1, dropped + 1)],
            "coherent": True,
            "note": "judged",
        })  # fmt: skip
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff,
            model=model,
            batch_id=line["batch_id"],
            stage=line["stage"],
            label=line["label"],
            text=answers[line["label"]],
            answered_by=answered_by(role, f"{agent}-{line['batch_id']}"),
            now=lambda: "2026-10-09T14:00:00+00:00",
        )
    return cli.cmd_judge_import(run, handoff, client=pages_client(), pace=0.0)


def start_enrich_run(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    sites: Sequence[str] | None = None,
    name: str = "enrich-test",
    pilot: bool = True,
    after: Sequence[Path] = (),
    disputes: Path | None = None,
) -> tuple[Path, Path]:
    """Read and export a lane-E run: the listed sites (a pilot that draws every asked site, or a
    chunk), round 1 exported. Returns the run directory and the round's handoff."""
    from phase3.run import read_jsonl
    from wc import cli

    listed = list(sites if sites is not None else [row["id"] for row in rows])
    run, handoff = root / "runs" / name, root / "handoff" / f"{name}-e"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    listing = root / f"{name}.sites.txt"
    listing.write_text("".join(f"{site}\n" for site in listed), encoding="utf-8", newline="\n")
    asked, _ = cli.population(
        read_jsonl(run / cli.ROWS_FILE),
        excluded=set(),
        earlier=set(),
        kind=cli.KIND_ENRICH,
        only=set(listed),
    )
    draw = {"pilot": len(asked), "seed": 1} if pilot else {"pilot": None, "seed": None}
    cli.cmd_export(
        run, handoff, batch_size=5, exclude=None, after=list(after), sites=listing, enrich=True,
        disputes=disputes, **draw,
    )  # fmt: skip
    return run, handoff


def build_enrich_run(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    answers: Mapping[str, str],
    *,
    sites: Sequence[str] | None = None,
    name: str = "enrich-test",
    pilot: bool = True,
    judged: bool = True,
    first_batch: int = WC4.FIRST_BATCH,
    after: Sequence[Path] = (),
    disputes: Path | None = None,
    verdicts: Mapping[str, Sequence[str]] | None = None,
    invented: Sequence[str] = (),
) -> tuple[Path, Path]:
    """A lane-E run end to end: read, export the listed sites (a pilot that draws every asked site,
    or a chunk), write answers, import, verify, build; a pilot is judged and passes unless `judged`
    is false. Returns the run directory and its gate plan (`WC4.jsonl`)."""
    from wc import cli

    run, handoff = start_enrich_run(
        root, rows, sites=sites, name=name, pilot=pilot, after=after, disputes=disputes
    )
    record_enriched(handoff, answers)
    cli.cmd_import(run, handoff, client=pages_client(), pace=0.0)
    verify_enriched(run, root / "handoff" / f"{name}-verify", verdicts=verdicts)
    cli.cmd_build(run, first_batch=first_batch)
    if pilot and judged:
        judge_enriched(run, root / "handoff" / f"{name}-judge", invented=invented)
    return run, run / cli.PLAN_FILE


def checked_march_pair(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    """A checked March text as production holds it after lane WC wrote it: the description and
    `raw_data` of the real WC machinery (lane L's provenance, the check record, two citations)."""
    from tests.remediation import test_phase4_wc_write as T

    batch, outcomes = T._loaded(tmp_path)
    outcome = outcomes[batch.batch_id][FX.SITE_A]
    assert outcome.description is not None and outcome.raw_data is not None
    return outcome.description, outcome.raw_data


def web_pair(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    """A lane-N text as production holds it after lane WN wrote it."""
    rows = [WX.wn_row(WX.SITE_N)]
    plan = WX.build_wn_run(tmp_path, rows, {WX.SITE_N: WX.good(WX.SITE_N)}, name="wn-base")[1]
    from phase4 import write4 as W4

    batches, outcomes = W4.load_wc_plan([plan])
    outcome = outcomes[batches[0].batch_id][WX.SITE_N]
    assert outcome.description is not None and outcome.raw_data is not None
    return outcome.description, outcome.raw_data


def standard_rows(tmp_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The four sites every test of the lane starts from: a Phase-4 text (lane W), a checked March
    text (lane L, with its check record), a lane-N text, and a second Phase-4 text for which the agent
    finds nothing to append - with the answers of the enrich round."""
    l_text, l_raw = checked_march_pair(tmp_path / "l")
    n_text, n_raw = web_pair(tmp_path / "n")
    rows = [
        p4_row(SITE_W),
        FX.row(SITE_L, l_text, raw_data=l_raw, name="Tarxien L"),
        FX.row(SITE_N, n_text, raw_data=n_raw, name="Tarxien N"),
        p4_row(SITE_NONE, name="Tarxien none"),
    ]
    answers = {
        SITE_W: good(SITE_W),
        SITE_L: good(SITE_L),
        SITE_N: good(SITE_N),
        SITE_NONE: nothing(SITE_NONE),
    }
    return rows, answers


def built(tmp_path: Path) -> dict[str, Any]:
    """The standard scenario run end to end (a judged pilot): the rows, the run directory, the plan
    and the plan's outcomes by site."""
    from phase4 import write4 as W4

    rows, answers = standard_rows(tmp_path)
    run, plan = build_enrich_run(tmp_path / "run", rows, answers)
    batches, outcomes = W4.load_wc_plan([plan])
    return {
        "root": tmp_path / "run",
        "rows": rows,
        "answers": answers,
        "run": run,
        "plan": plan,
        "batch": batches[0],
        "outcomes": outcomes[batches[0].batch_id],
    }
