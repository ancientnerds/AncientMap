"""The two rerun shapes through every stage that reads them: the gap run's and the search lane's.

Two reviewed branches gave one plan-record key two meanings (found in the merged tree, 2026-09-23).
The search lane read `rerun_fields` as "the fields a search plan reruns" and derived its MiniMax
searches from it; the gap plan writes `rerun_fields` on every record to say which fields the run asks
again, with no search intended. A gap run would have been driven as a search run - 802 searches nobody
planned - or refused, and the writer's own test failed on a search file nobody had bought.

The two meanings now have two keys: `rerun_fields` (what a run asks again) and `search_fields` (what it
buys a MiniMax search for, a non-empty subset). This module builds one plan of each shape **with its
own planner** (`gap_plan.site_records`, `search_plan.build_search_plan`), prepares it with `run.py
prepare`, and asks every stage that reads a record what it makes of it: `mass_run`'s kind and stages,
the discover pass's questions, the evidence and the search stage, the reviewer's calls, and the
writer's refusal of a field outside `rerun_fields`. Temporary run directories and fake stores only: no
socket, no model, no database.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import gap_plan as G  # noqa: E402
import lanes  # noqa: E402
from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import hit_stage as HS  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import mass_run as MR  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import review_stage as RS  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import search_plan as SPL  # noqa: E402
from phase3 import search_stage as SS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

from pipeline.lyra import minimax_shared as MX  # noqa: E402

#: The gap: BIG was over the evidence bound (all five fields), SMALL had an empty stream and an
#: answer without a readable verdict (two fields) - the census's three classes.
BIG = "aaaaaaaa-0000-4000-8000-000000000001"
SMALL = "aaaaaaaa-0000-4000-8000-000000000002"
#: The search lane: one site whose country the mass run's finder answered UNVERIFIABLE.
CAVE = "cccccccc-0000-4000-8000-000000000003"
VOCAB = ("Temple", "Cave Structures")
#: The sentence every fetched page carries, and the one the gap finding quotes.
PAGE_SENTENCE = "It stands in Turkey."
#: The one page the scripted search finds, and the sentence the search finding quotes.
HIT_URL = "https://e.org/cave-one"
HIT_SNIPPET = "Cave One lies in Peru."
TUESDAY = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # outside Theo's end-of-week window
PROBE_OK = {
    "ok": True,
    "five_hour_remaining_percent": 98,
    "weekly_remaining_percent": 86,
    "weekly_remains_tokens": 500_000_000,
    "five_hour_remains_tokens": 90_000_000,
}
SHAPES = ("gap", "search")


# ── the two plans, each from its own planner ────────────────────────────────────────────────────


def _row(site_id: str, name: str, **values: object) -> dict[str, Any]:
    """One `unified_sites` row of a production export."""
    return {
        "id": site_id,
        "name": name,
        "description": "a description",
        "period_start": -1500,
        "site_type": "Temple",
        "country": "Greece",
        "source_id": "ancient_nerds",
        **values,
    }


def _enwiki_page(text: str) -> str:
    """An enwiki evidence file the way the fetch stage stores it: the API's JSON."""
    return json.dumps({"query": {"pages": {"1": {"title": "Site", "extract": text}}}})


def _fetched(batch_dir: Path, sites: list[dict[str, Any]]) -> None:
    """What `run.py fetch` leaves: one page per target of every site, and a report with no failure."""
    store = F.EvidenceStore(batch_dir / "evidence")
    for site in sites:
        for target in F.targets_for_site(site):
            page = _enwiki_page(f"{site['name']} is an ancient site. {PAGE_SENTENCE}")
            store.write(site_id=target.site_id, feature=target.feature, body=page.encode("utf-8"))
    report = {"sites": [{"site_id": site["site_id"], "outcomes": []} for site in sites]}
    (batch_dir / "fetch.json").write_text(json.dumps(report), encoding="utf-8")


def _gap_plan(tmp_path: Path) -> Path:
    """`PLAN.gap.jsonl` as `gap_plan.py plan` writes it, from a fabricated census and export."""
    questions = [
        *(
            G.Question(BIG, name, "batch-0007", 0, G.OVER_BOUND, "evidence 70000, bound 64000")
            for name in SP.DISCOVER_FIELDS
        ),
        G.Question(SMALL, "period_start", "batch-0007", 1, G.NO_VERDICT, "no VERDICT line"),
        G.Question(SMALL, "country", "batch-0007", 1, G.EMPTY_STREAM, "no text"),
    ]
    export = tmp_path / "export"
    lanes.write_jsonl(
        export / "unified_sites.jsonl", [_row(BIG, "Big Temple"), _row(SMALL, "Small Temple")]
    )
    lanes.write_jsonl(
        export / "card_stats.jsonl",
        [{"site_id": site_id, "card_description": "a card"} for site_id in (BIG, SMALL)],
    )
    lanes.write_jsonl(export / "site_external_ids.jsonl", [])
    records = G.site_records(questions, export_dir=export, sitelinks={})
    path = tmp_path / "PLAN.gap.jsonl"
    R.write_batches(path, G.batches(records))
    return path


def _search_plan(tmp_path: Path) -> Path:
    """`PLAN.search.jsonl` as `run.py plan-search` writes it, from a fabricated mass run."""
    source = tmp_path / "mass"
    batch_dir = source / "batch-0001"
    batch_dir.mkdir(parents=True)
    site = SP.discover_site_record(
        site=_row(
            CAVE, "Cave One", site_type="Cave Structures", country="Spain", period_start=-3000
        ),
        card={"card_description": "A painted cave."},
        qid=None,
    )
    batch = {"batch_id": "batch-0001", "ordinal": 1, "pass": R.DISCOVER_PASS, "sites": [site]}
    (batch_dir / "input.json").write_text(json.dumps(batch, sort_keys=True) + "\n", "utf-8")
    _fetched(batch_dir, [site])
    answers = F.EvidenceStore(batch_dir / "answers")
    for name in SP.DISCOVER_FIELDS:
        verdict = "UNVERIFIABLE" if name == "country" else "CORRECT"
        body = f"The evidence is silent.\nVERDICT: {verdict}\n".encode()
        answers.write(site_id=CAVE, feature=name, body=body)
    current = {
        CAVE: {
            name: DS.field_finding(site, name)["current_value"] for name in SPL.CURRENT_VALUE_FIELDS
        }
    }
    plan = SPL.build_search_plan(
        source_run_dir=source, scope="writable", prefix="srch", current=current
    )
    path = tmp_path / "PLAN.search.jsonl"
    SPL.write_plan(path, plan)
    return path


@dataclass(frozen=True)
class Lane:
    """One prepared plan of one shape, and what every stage should make of it."""

    plan: Path
    run_dir: Path
    batch_id: str
    kind: str
    stages: tuple[str, ...]
    #: site -> the fields the finder is asked, in `DISCOVER_FIELDS` order
    asked: dict[str, tuple[str, ...]]
    searches: int
    #: (site, rerun field, proposed value, cited url, quote): one finding the run may write
    finding: tuple[str, str, str, str, str]
    #: a field of that site the run does not ask again, which the writer must refuse
    outside: str

    @property
    def batch_dir(self) -> Path:
        return self.run_dir / self.batch_id

    @property
    def store(self) -> F.EvidenceStore:
        return F.EvidenceStore(self.batch_dir / "evidence")

    def sites(self) -> list[dict[str, Any]]:
        return json.loads((self.batch_dir / "input.json").read_text(encoding="utf-8"))["sites"]

    def site(self, site_id: str) -> dict[str, Any]:
        return next(site for site in self.sites() if site["site_id"] == site_id)

    def failures(self, site_id: str) -> dict[str, str] | None:
        return MS.read_fetch_failures(self.batch_dir / "fetch.json").get(site_id)


def _lane(shape: str, tmp_path: Path) -> Lane:
    """Plan, `run.py prepare`, and the evidence the run's own evidence stage would leave.

    The gap run fetches (faked here: `_fetched`); the search lane's `prepare` copies the mass
    batch's evidence byte for byte, and its search is left to the test that means it (`_search`).
    """
    run_dir = tmp_path / "runs"
    plan = _gap_plan(tmp_path) if shape == "gap" else _search_plan(tmp_path)
    assert R.main(["prepare", "--plan", str(plan), "--run-dir", str(run_dir)]) == 0
    if shape == "gap":
        lane = Lane(
            plan=plan,
            run_dir=run_dir,
            batch_id="gap-0001",
            kind=MR.RERUN_PLAN,
            stages=MR.STAGES,
            asked={BIG: SP.DISCOVER_FIELDS, SMALL: ("period_start", "country")},
            searches=0,
            finding=(
                SMALL,
                "country",
                "Turkey",
                F.wikipedia_extract_url("Small Temple"),
                PAGE_SENTENCE,
            ),
            outside="site_type",
        )
        _fetched(lane.batch_dir, lane.sites())
        return lane
    return Lane(
        plan=plan,
        run_dir=run_dir,
        batch_id="srch-0001",
        kind=MR.SEARCH_PLAN,
        stages=MR.SEARCH_STAGES,
        asked={CAVE: ("country",)},
        searches=1,
        finding=(CAVE, "country", "Peru", HIT_URL, HIT_SNIPPET),
        outside="period_start",
    )


class _Searcher:
    """The search seam, scripted: every query finds the one page `HIT_URL`."""

    endpoint = "https://api.minimax.io/v1/coding_plan/search"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str) -> MX.SearchResponse:
        self.queries.append(query)
        hit = MX.WebSearchResult(title="Cave One", url=HIT_URL, snippet=HIT_SNIPPET)
        return MX.SearchResponse(query=query, items=(hit,), http_status=200, body_bytes=123)


def _search(lane: Lane, ledger: Path, searcher: _Searcher | None = None) -> _Searcher:
    """`run.py search` for the lane's batch, through the stage's own function and report."""
    searcher = searcher or _Searcher()
    batch = json.loads((lane.batch_dir / "input.json").read_text(encoding="utf-8"))
    report = SS.search_batch(
        batch=batch,
        searcher=searcher,
        store=lane.store,
        ledger=L.Ledger(ledger),
        probe=lambda: dict(PROBE_OK),
        now=lambda: TUESDAY,
        wait=lambda: None,
        sleep=lambda _seconds: None,
    )
    SS.write_report(lane.batch_dir / MS.SEARCH_REPORT_NAME, report)
    return searcher


def _verified(lane: Lane, ledger: Path) -> None:
    """`run.py verify-hits` for a search lane's batch, once its finder answers are on disk: the page
    behind the cited hit is served by a fake transport and carries the hit's snippet sentence."""
    if lane.kind != MR.SEARCH_PLAN:
        return

    def serve(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == HIT_URL
        return httpx.Response(200, text=f"<html><h1>Cave One</h1><p>{HIT_SNIPPET}</p></html>")

    batch = json.loads((lane.batch_dir / "input.json").read_text(encoding="utf-8"))
    with F.HttpFetcher(transport=httpx.MockTransport(serve)) as fetcher:
        report = HS.verify_batch(
            batch=batch,
            fetcher=fetcher,
            store=lane.store,
            answers=F.EvidenceStore(lane.batch_dir / "answers"),
            ledger=L.Ledger(ledger),
            failures=MS.read_fetch_failures(lane.batch_dir / "fetch.json"),
            sleep=lambda _seconds: None,
        )
    HS.write_report(lane.batch_dir / MS.HIT_REPORT_NAME, report)
    assert [o.stored for o in report.outcomes] == [True]


def _ready(shape: str, tmp_path: Path) -> Lane:
    """The lane with every piece of evidence its judge reads on disk: a search lane has searched."""
    lane = _lane(shape, tmp_path)
    if lane.kind == MR.SEARCH_PLAN:
        _search(lane, tmp_path / "LEDGER.jsonl")
    return lane


def _answer(proposed: str, url: str, quote: str) -> bytes:
    """One complete `WRONG` finder answer, in the shape `discover_stage.parse_answer` reads."""
    return (
        "The page states a value other than the one this site stores.\n"
        "EVIDENCE: the page gives another value\n"
        f"PROPOSED: {proposed}\n"
        f'SOURCE: {url} - "{quote}"\n'
        "VERDICT: WRONG\n"
    ).encode()


def _cleared(site_id: str, field: str, url: str, quote: str) -> dict[str, Any]:
    """One `review.json` verdict that lets the writer act: asked, not refuted, no problem."""
    return {
        "site_id": site_id,
        "field": field,
        "asked": True,
        "applies": True,
        "refuted": False,
        "reason": "checked against the page the finder cited",
        "sources": [{"url": url, "quote": quote}],
        "problems": [],
        "unreviewable": None,
    }


# ── mass_run: the kind of plan, and the stages it runs ──────────────────────────────────────────


@pytest.mark.parametrize("shape", SHAPES)
def test_mass_run_reads_each_plan_as_its_own_kind_and_runs_its_own_stages(
    shape: str, tmp_path: Path
) -> None:
    """A gap plan is a rerun plan (`prepare,fetch,judge`, no search); a search plan is a search plan
    (`prepare,search,judge`). Each is refused under the other's stages, before anything is bought."""
    lane = _lane(shape, tmp_path)
    (batch,) = MR.read_plan(lane.plan)
    assert (batch.batch_id, batch.kind, batch.stages) == (lane.batch_id, lane.kind, lane.stages)
    assert batch.expected_calls == sum(len(fields) for fields in lane.asked.values())
    assert batch.searches == lane.searches
    ledger = tmp_path / "L.jsonl"
    argv = ["--plan", str(lane.plan), "--run-dir", str(lane.run_dir), "--ledger", str(ledger)]
    argv += ["--log-dir", str(tmp_path / "logs")]
    assert MR.main([*argv, "--stages", ",".join(lane.stages)]) == 0  # the dry run buys nothing
    other = MR.SEARCH_STAGES if lane.stages == MR.STAGES else MR.STAGES
    with pytest.raises(MR.PlanError, match="does not fit"):
        MR.main([*argv, "--stages", ",".join(other)])
    assert not ledger.exists()


def test_a_plan_whose_lines_are_of_two_kinds_is_refused(tmp_path: Path) -> None:
    """A plan is one kind: its kind decides the stages every one of its batches runs."""
    gap = _gap_plan(tmp_path / "gap").read_text(encoding="utf-8")
    search = _search_plan(tmp_path / "search").read_text(encoding="utf-8")
    snapshot = {
        "batch_id": "batch-0001",
        "ordinal": 1,
        "pass": R.DISCOVER_PASS,
        "sites": [SP.discover_site_record(site=_row(BIG, "Big Temple"), card=None, qid=None)],
    }
    path = tmp_path / "PLAN.mixed.jsonl"
    for body, kinds in (
        (gap + json.dumps(snapshot) + "\n", [MR.RERUN_PLAN, MR.SNAPSHOT_PLAN]),
        (gap + search, [MR.RERUN_PLAN, MR.SEARCH_PLAN]),
    ):
        path.write_text(body, encoding="utf-8")
        with pytest.raises(MR.PlanError, match=re.escape(f"the plan mixes {kinds}")):
            MR.read_plan(path)


def test_a_search_plan_built_before_search_fields_is_refused_not_run_as_a_rerun(
    tmp_path: Path,
) -> None:
    """The search plans built on 2026-09-22 carry `rerun_fields` and `rerun_why`, and no
    `search_fields` (measured 2026-09-23 on the plans still on disk). Read by key alone they would be
    rerun plans - a run without its searches, and without the held-value guard - so the driver
    refuses them, naming the key that gives them away."""
    lane = _lane("search", tmp_path)
    (line,) = [json.loads(text) for text in lane.plan.read_text(encoding="utf-8").splitlines()]
    for site in line["sites"]:
        for key in (SE.SEARCH_FIELDS_KEY, SE.RERUN_UNWRITTEN_KEY, SE.QUERY_VALUES_KEY):
            del site[key]
    old = tmp_path / "PLAN.search-2026-09-22.jsonl"
    old.write_text(json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(MR.PlanError, match=r":1: .*\['rerun_why'\] but no search_fields"):
        MR.read_plan(old)


# ── the discover pass: which fields the finder is asked ─────────────────────────────────────────


@pytest.mark.parametrize("shape", SHAPES)
def test_the_finder_asks_exactly_the_fields_the_plan_reruns(shape: str, tmp_path: Path) -> None:
    lane = _ready(shape, tmp_path)
    asked = {}
    for site in lane.sites():
        plan = DS.plan_site(
            batch_id=lane.batch_id,
            site=site,
            store=lane.store,
            vocabulary=VOCAB,
            failures=lane.failures(site["site_id"]),
        )
        assert plan.skipped == []
        asked[site["site_id"]] = tuple(call.call.field for call in plan.calls)
    assert asked == lane.asked


# ── the evidence: a search is required exactly where one was bought ────────────────────────────


def test_a_gap_record_is_judged_on_its_fetched_pages_and_buys_no_search(tmp_path: Path) -> None:
    lane = _lane("gap", tmp_path)
    for site in lane.sites():
        assert SE.rerun_fields(site) == lane.asked[site["site_id"]]
        assert SE.search_fields(site) is None and SE.search_slots(site) == ()
        # No search file is on disk and none is recorded as failed: none is asked for.
        excerpts = MS.evidence_excerpts(site_id=site["site_id"], site=site, store=lane.store)
        assert [e.feature for e in excerpts] == [t.feature for t in F.targets_for_site(site)]
        assert all(e.present for e in excerpts)
    searcher = _Searcher()
    with pytest.raises(R.InputError, match="carries no search_fields"):
        _search(lane, tmp_path / "LEDGER.jsonl", searcher)
    assert searcher.queries == [] and not (tmp_path / "LEDGER.jsonl").exists()


def test_a_search_record_is_judged_only_once_its_search_is_on_disk(tmp_path: Path) -> None:
    lane = _lane("search", tmp_path)
    site = lane.site(CAVE)
    assert SE.rerun_fields(site) == SE.search_fields(site) == ("country",)
    assert [slot.feature for slot in SE.search_slots(site)] == ["minimax_search.country"]
    with pytest.raises(MS.EvidenceUnusable, match="search report records no failure"):
        MS.evidence_excerpts(site_id=CAVE, site=site, store=lane.store)
    searcher = _search(lane, tmp_path / "LEDGER.jsonl")
    assert len(searcher.queries) == 1
    excerpts = MS.evidence_excerpts(
        site_id=CAVE, site=site, store=lane.store, failures=lane.failures(CAVE)
    )
    (hit,) = [e for e in excerpts if e.feature.startswith(SE.SEARCH_FEATURE_PREFIX)]
    assert hit.url == HIT_URL and HIT_SNIPPET in str(hit.text)


# ── the reviewer and the writer ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("shape", SHAPES)
def test_the_reviewer_is_asked_about_a_rerun_finding(shape: str, tmp_path: Path) -> None:
    """A gap record names no unwritten proposals - its planner selects none - and is still
    reviewed; a search record names its own (`{}` here) and is reviewed on its search page too."""
    lane = _ready(shape, tmp_path)
    site_id, field, proposed, url, quote = lane.finding
    answers = F.EvidenceStore(lane.batch_dir / "answers")
    answers.write(site_id=site_id, feature=field, body=_answer(proposed, url, quote))
    _verified(lane, tmp_path / "LEDGER.jsonl")
    plan = RS.plan_site(
        batch_id=lane.batch_id,
        site=lane.site(site_id),
        answers=answers,
        store=lane.store,
        failures=lane.failures(site_id),
    )
    (call,) = plan.calls
    assert call.call.field == field and url in call.call.prompt


@pytest.mark.parametrize("shape", SHAPES)
def test_the_writer_writes_a_rerun_field_and_refuses_one_outside_rerun_fields(
    shape: str, tmp_path: Path
) -> None:
    """Both findings are cleared and cite a page the run holds; only the rerun one is planned."""
    lane = _ready(shape, tmp_path)
    site_id, field, proposed, url, quote = lane.finding
    answers = F.EvidenceStore(lane.batch_dir / "answers")
    answers.write(site_id=site_id, feature=field, body=_answer(proposed, url, quote))
    answers.write(site_id=site_id, feature=lane.outside, body=_answer("Tomb", url, quote))
    _verified(lane, tmp_path / "LEDGER.jsonl")
    review = {
        "batch_id": lane.batch_id,
        "stage": "reviewer",
        "verdicts": [_cleared(site_id, name, url, quote) for name in (field, lane.outside)],
    }
    (lane.batch_dir / W.REVIEW_FILE).write_text(json.dumps(review), encoding="utf-8")
    plan = W.load_plan(lane.batch_dir)
    assert [(row.site_id, row.column, row.new_value) for row in plan.rows] == [
        (site_id, field, proposed)
    ]
    refused = {(r.site_id, r.field) for r in plan.refused_fields(W.RULE_NOT_RERUN)}
    assert (site_id, lane.outside) in refused
    assert refused == {
        (site, name)
        for site, fields in lane.asked.items()
        for name in SP.DISCOVER_FIELDS
        if name not in fields
    }
