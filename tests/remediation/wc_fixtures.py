"""Shared fixtures for lane WC's tests (the sentence check): production rows as the read returns
them, a fake page server, and answers as the Opus agents write them.

Not a test module (no `test_` prefix). Nothing here opens a socket, calls a model or touches a
database: the pages are served from a dict, the database is a scripted runner.
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
from phase4 import legacy4 as L4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402

SITE_A = "0a000000-0000-4000-8000-00000000000a"
SITE_B = "0b000000-0000-4000-8000-00000000000b"
SITE_C = "0c000000-0000-4000-8000-00000000000c"
SITE_D = "0d000000-0000-4000-8000-00000000000d"

WIKI = "https://en.wikipedia.org/wiki/Tarxien_Temples"
MUSEUM = "https://heritagemalta.mt/explore/tarxien-temples/"
OTHER = "https://www.example.edu/malta/tarxien"
COPY = "https://www.copycat.example/tarxien"

#: The March text of site A: three sentences, one plain marker form after a full stop.
TEXT_A = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
    "They date to approximately 3150 BC, and they were built by giants. "
    "The site was excavated by Themistocles Zammit in 1915.[1][2]"
)
SENTENCES_A = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta.",
    "They date to approximately 3150 BC, and they were built by giants.",
    "The site was excavated by Themistocles Zammit in 1915.",
)

#: The pages the fake server holds: each carries the quotes the answers below give.
PAGES: dict[str, str] = {
    WIKI: (
        "<html><head><title>Tarxien Temples - Wikipedia</title></head><body><p>The Tarxien "
        "Temples are an archaeological complex in Tarxien, Malta. They date to approximately "
        "3150 BC.</p><p>The site was excavated by Themistocles Zammit between 1915 and 1919."
        "</p></body></html>"
    ),
    MUSEUM: (
        "<html><body><h1>Tarxien Temples</h1><p>Excavations at Tarxien were carried out by "
        "Sir Themistocles Zammit in 1915.</p></body></html>"
    ),
    OTHER: "<html><body><p>Nothing about the temples here at all.</p></body></html>",
    COPY: (
        "<html><body><p>" + WC4.strip_markers(TEXT_A) + " A copied page of our own text, word "
        "for word, as scrapers keep it.</p></body></html>"
    ),
}


def row(
    site_id: str,
    description: str | None,
    *,
    raw_data: dict[str, Any] | None = None,
    scope_status: str | None = None,
    snapshot: str | None = "The pre-March text.",
    in_snapshot: bool = True,
    name: str = "Tarxien Temples",
) -> dict[str, Any]:
    """One row of lane WC's read (`cli.WC_SQL`): Phase 4's plan-read columns and the scope."""
    raw_text = None if raw_data is None else json.dumps(raw_data)
    return {
        "id": site_id,
        "scope_status": scope_status,
        "name": name,
        "country": "Malta",
        "site_type": "Temple complex",
        "period_start": -3150,
        "period_end": -2500,
        "lat": 35.8692,
        "lon": 14.5122,
        "description": description,
        "description_sha256": None if description is None else M.text_sha256(description),
        "raw_data": copy.deepcopy(raw_data),
        "raw_data_sha256": None if raw_text is None else M.text_sha256(raw_text),
        "source_url": WIKI,
        "card": "An old card.",
        "card_sha256": M.text_sha256("An old card."),
        "wikidata_qid": "Q1195938",
        "enwiki_title": "Tarxien Temples",
        "names": [name, "Templi ta' Hal Tarxien"],
        "in_snapshot": in_snapshot,
        "snapshot_description": snapshot if in_snapshot else None,
    }


def legacy_raw(description: str, **extra: Any) -> dict[str, Any]:
    """`raw_data` of a March text lane L marked, with its old citations."""
    return {
        M.CITATIONS_KEY: [
            {"n": 1, "url": WIKI, "title": "Tarxien Temples", "domain": "en.wikipedia.org",
             "claim": "an old claim"},
            {"n": 2, "url": MUSEUM, "title": "Tarxien", "domain": "heritagemalta.mt",
             "claim": "another"},
        ],
        M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256=M.text_sha256(description)).to_dict(),
        **extra,
    }  # fmt: skip


def plan_site(site_row: Mapping[str, Any]) -> M.PlanSite:
    from phase4 import plan4

    return plan4.plan_site(
        {k: v for k, v in site_row.items() if k != "scope_status"}, flags=frozenset()
    )


# ------------------------------------------------------------------------------------ pages
@dataclass
class _Response:
    status_code: int
    url: str
    headers: dict[str, str]
    content: bytes


class FakeClient:
    """`wc/answers.Client`'s seam over a dict of pages: a known URL answers 200 with its HTML, a
    URL in `status` answers that status, any other refuses the connection like a dead host."""

    def __init__(self, pages: Mapping[str, str] = PAGES, status: Mapping[str, int] | None = None):
        self.pages = dict(pages)
        self.status = dict(status or {})
        self.fetched: list[str] = []

    def get(self, url: str) -> _Response:
        self.fetched.append(url)
        if url in self.status:
            return _Response(self.status[url], url, {"Content-Type": "text/html"}, b"refused")
        if url not in self.pages:
            raise requests.ConnectionError(f"no route to {url}")
        body = self.pages[url].encode("utf-8")
        return _Response(200, url, {"Content-Type": "text/html; charset=utf-8"}, body)

    def close(self) -> None:
        pass


# ------------------------------------------------------------------------------------ answers
def quote(url: str, text: str, title: str = "Tarxien Temples") -> dict[str, str]:
    return {"url": url, "title": title, "quote": text}


def keep(n: int, *quotes: dict[str, str], note: str = "supported") -> dict[str, Any]:
    return {"n": n, "verdict": "KEEP", "remove": None, "reason": None, "quotes": list(quotes),
            "note": note}  # fmt: skip


def trimmed(n: int, remove: str, *quotes: dict[str, str]) -> dict[str, Any]:
    return {"n": n, "verdict": "KEEP_TRIMMED", "remove": remove, "reason": None,
            "quotes": list(quotes), "note": "the piece is unsupported"}  # fmt: skip


def drop(n: int, reason: str = "unsupported", *quotes: dict[str, str]) -> dict[str, Any]:
    return {"n": n, "verdict": "DROP", "remove": None, "reason": reason, "quotes": list(quotes),
            "note": "no source supports it"}  # fmt: skip


def answer(site_id: str, sentences: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps({"site_id": site_id, "sentences": list(sentences)}, ensure_ascii=False)


#: The quotes the pages above carry, one per claim.
Q_COMPLEX = quote(WIKI, "The Tarxien Temples are an archaeological complex in Tarxien, Malta.")
Q_DATE = quote(WIKI, "They date to approximately 3150 BC.")
Q_ZAMMIT = quote(
    MUSEUM, "Excavations at Tarxien were carried out by Sir Themistocles Zammit in 1915"
)
Q_ZAMMIT_WIKI = quote(WIKI, "excavated by Themistocles Zammit between 1915 and 1919")


def record_answers(handoff: Path, answers: Mapping[str, str], *, by: str = "opus-check") -> None:
    """Write each site's answer where its question was exported, as `opus_handoff.py answer`."""
    for line in OH.manifest(handoff):
        if line["label"] in answers:
            OH.write_answer(
                handoff,
                batch_id=line["batch_id"],
                stage=line["stage"],
                label=line["label"],
                text=answers[line["label"]],
                answered_by=f"{by}-{line['batch_id']}",
                now=lambda: "2026-09-26T12:00:00+00:00",
            )


__all__ = ["L4"]


# ------------------------------------------------------------------------------------ a whole run
class ReadRunner:
    """The read-only production seam of `wc/cli.py read`: answers exactly `cli.WC_SQL`."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]):
        self.rows = [dict(r) for r in rows]

    def __call__(self, sql: str, *, host: str) -> str:
        from wc import cli

        assert sql == cli.WC_SQL
        return "".join(json.dumps(r) + "\n" for r in self.rows)


def build_run(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    answers: Mapping[str, str],
    *,
    first_batch: int = WC4.FIRST_BATCH,
    name: str = "wc-test",
) -> tuple[Path, Path]:
    """A WC run end to end with every answer counted in round 1: read, export, answer, import,
    build. Returns the run directory and its gate plan (`WC4.jsonl`)."""
    from wc import cli

    run, handoff = root / "runs" / name, root / "handoff" / f"{name}-r1"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=ReadRunner(rows))
    cli.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None)
    record_answers(handoff, answers)
    cli.cmd_import(run, handoff, client=FakeClient(), pace=0.0)
    cli.cmd_build(run, first_batch=first_batch)
    return run, run / cli.PLAN_FILE
