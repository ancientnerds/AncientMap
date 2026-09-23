"""Does a search hit count only through the page behind it, fetched after the finder and before the
reviewer?

The search pilot of 2026-09-23 (`output/remediation/phase3_runner/SEARCH_PILOT_RESULT_1.txt`) showed
that a snippet is not a page: Las Labradas' `1000 B.C. - 300 A.D.` was a travel page's snippet about
another site (Toro Muerto), and the Font dels Coms quote was not in the Zenodo snippet at all. So
`phase3/hit_stage.py` (`run.py verify-hits`) fetches the page behind every hit a finder answer cites,
the reviewer is shown it, and the writer accepts a hit's citation only when its quote occurs in that
page - a hit whose page could not be fetched or read is refused, never accepted on the snippet.

Every page here is served by `httpx.MockTransport`; no socket is opened, no model is asked, no
database is touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
TOOLS = REPO / "output" / "remediation" / "tools"
for _path in (TOOLS, PHASE3_PARENT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import score_search_pilot  # noqa: E402
from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import hit_stage as HS  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import review_stage as RS  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import search_stage as SS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

SITE = "33333333-3333-4333-8333-333333333333"
BATCH = "srgd-0081"
#: The pilot's own case: the hit a finder cited for Las Labradas, and the snippet it quoted.
HIT = "https://pathere.org/archaeological-complex-of-toro-muerto/"
OTHER_HIT = "https://kids.kiddle.co/List_of_World_Heritage_Sites_in_Mexico"
QUOTE = "The antiquity of Las Labradas sites (1000 B.C. - 300 A.D.) is earlier than Toro Muerto."
#: The page behind the hit as it really reads: about Toro Muerto, and without the quoted sentence.
TORO_MUERTO = "<html><head><title>Archaeological Complex of Toro Muerto</title></head>" + (
    "<body><p>Toro Muerto is a petroglyph site in Peru.</p></body></html>"
)
CARRYING = f"<html><body><p>Some context.</p><p>{QUOTE}</p></body></html>"


# ── helpers ──────────────────────────────────────────────────────────────────────────────────


def _site(*, rerun: tuple[str, ...] = ("period_start",), search: bool = True) -> dict[str, Any]:
    """A search-plan record: Las Labradas stores `period_start` 500 and asks it again."""
    stored = {
        "description": "Petroglyphs on the shore.",
        "period_start": 500,
        "site_type": "Rock art",
        "country": "Mexico",
        "card_description": "Petroglyphs.",
    }
    record: dict[str, Any] = {
        "findings": [SP.finding_row(name, stored[name]) for name in SP.DISCOVER_FIELDS],
        "name": "Las Labradas",
        "site_id": SITE,
        "rerun_fields": list(rerun),
    }
    if search:
        record["search_fields"] = list(rerun)
        record["rerun_unwritten"] = {}
        record["query_values"] = {slot: stored[slot] for slot in SS.SLOT_FIELDS}
    return record


def _answer(*, url: str = HIT, quote: str = QUOTE, proposed: str = "-1000") -> str:
    return (
        "The evidence gives 1000 BC as the start.\nVERDICT: WRONG\n"
        f'PROPOSED: {proposed}\nSOURCE: {url} - "{quote}"\n'
    )


def _batch_dir(
    tmp_path: Path,
    *,
    hits: tuple[tuple[str, str], ...] = ((HIT, QUOTE), (OTHER_HIT, "100 B.C. to A.D. 1300")),
    answers: dict[str, str] | None = None,
    rerun: tuple[str, ...] = ("period_start",),
    reason: str = "checked against the page the finder cited",
) -> Path:
    """A search batch after `prepare`, `search` and `judge`: input, evidence, reports, answers, and
    a review that clears every answered field."""
    root = tmp_path / BATCH
    site = _site(rerun=rerun)
    batch = {"batch_id": BATCH, "ordinal": 81, "pass": R.DISCOVER_PASS, "sites": [site]}
    (root / "input.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "input.json").write_text(json.dumps(batch), encoding="utf-8")
    store = F.EvidenceStore(root / "evidence")
    for target in F.targets_for_site(site):
        store.write(site_id=SITE, feature=target.feature, body=b'{"query": {"pages": {}}}')
    records = {
        slot.feature: SE.SearchRecord(
            query="q",
            hits=tuple(
                SE.StoredHit(rank=rank, title="T", url=url, snippet=snippet, date="")
                for rank, (url, snippet) in enumerate(hits, start=1)
            ),
            linkless=0,
        )
        for slot in SE.search_slots(site)
    }
    for feature, record in records.items():
        store.write(site_id=SITE, feature=feature, body=record.to_bytes())
    (root / "fetch.json").write_text(json.dumps({"sites": []}), encoding="utf-8")
    (root / "search.json").write_text(json.dumps({"sites": []}), encoding="utf-8")
    texts = answers if answers is not None else {"period_start": _answer()}
    answer_store = F.EvidenceStore(root / "answers")
    for name, text in texts.items():
        answer_store.write(site_id=SITE, feature=name, body=text.encode("utf-8"))
    verdicts = [
        {
            "site_id": SITE,
            "field": name,
            "asked": name in texts,
            "applies": name in texts,
            "refuted": False if name in texts else None,
            "reason": reason,
            "sources": [],
            "problems": [],
            "unreviewable": None if name in texts else "not asked",
        }
        for name in SP.DISCOVER_FIELDS
    ]
    review = {"batch_id": BATCH, "stage": "reviewer", "verdicts": verdicts}
    (root / W.REVIEW_FILE).write_text(json.dumps(review), encoding="utf-8")
    return root


class Pages:
    """The fake web: one response per url, and every request it was asked."""

    def __init__(self, pages: dict[str, httpx.Response]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(str(request.url))
        return self.pages[str(request.url)]

    def fetcher(self) -> F.HttpFetcher:
        return F.HttpFetcher(transport=httpx.MockTransport(self))


def _verify(root: Path, pages: Pages, *, ledger: Path | None = None) -> HS.HitReport:
    """`run.py verify-hits` for the batch, through the stage's own function and report."""
    batch = json.loads((root / "input.json").read_text(encoding="utf-8"))
    with pages.fetcher() as fetcher:
        report = HS.verify_batch(
            batch=batch,
            fetcher=fetcher,
            store=F.EvidenceStore(root / "evidence"),
            answers=F.EvidenceStore(root / "answers"),
            ledger=L.Ledger(ledger or root.parent / "LEDGER.jsonl"),
            failures=MS.read_fetch_failures(root / "fetch.json"),
            sleep=lambda _seconds: None,
        )
    HS.write_report(root / MS.HIT_REPORT_NAME, report)
    return report


def _excerpts(root: Path) -> list[MS.EvidenceExcerpt]:
    site = json.loads((root / "input.json").read_text(encoding="utf-8"))["sites"][0]
    return MS.evidence_excerpts(
        site_id=SITE,
        site=site,
        store=F.EvidenceStore(root / "evidence"),
        failures=MS.read_fetch_failures(root / "fetch.json").get(SITE),
    )


def _ledger_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── what the stage fetches ───────────────────────────────────────────────────────────────────


def test_the_stage_fetches_the_cited_hits_and_no_other(tmp_path: Path) -> None:
    """Two hits were found, one is cited: one request, one ledger line, one page on disk."""
    root = _batch_dir(tmp_path)
    pages = Pages({HIT: httpx.Response(200, text=CARRYING)})
    report = _verify(root, pages)
    assert pages.asked == [HIT]
    (outcome,) = report.outcomes
    assert (outcome.url, outcome.fields, outcome.stored, outcome.failure) == (
        HIT,
        ("period_start",),
        True,
        None,
    )
    stored = F.EvidenceStore(root / "evidence").path_for(SITE, SE.hit_page_feature(HIT))
    assert stored.read_bytes() == CARRYING.encode("utf-8")
    (line,) = _ledger_lines(tmp_path / "LEDGER.jsonl")
    assert (line["kind"], line["label"], line["url"], line["stage"]) == (
        "fetch",
        f"{SITE}/{SE.hit_page_feature(HIT)}",
        HIT,
        "reviewer",
    )
    written = json.loads((root / MS.HIT_REPORT_NAME).read_text(encoding="utf-8"))
    assert written["totals"]["stored"] == 1 and written["totals"]["requests"] == 1


def test_a_cited_fetched_target_is_not_a_hit_and_is_not_fetched_again(tmp_path: Path) -> None:
    """The fetch stage already fetched the site's targets; a citation of one is checked against that
    stored page, so the hit stage leaves it alone."""
    target = F.targets_for_site(_site())[0]
    root = _batch_dir(tmp_path, answers={"period_start": _answer(url=target.url)})
    pages = Pages({})
    report = _verify(root, pages)
    assert pages.asked == [] and report.outcomes == []


def test_a_page_already_on_disk_is_not_fetched_again(tmp_path: Path) -> None:
    root = _batch_dir(tmp_path)
    _verify(root, Pages({HIT: httpx.Response(200, text=CARRYING)}))
    again = Pages({})
    report = _verify(root, again)
    assert again.asked == []
    assert [(o.existing, o.stored, o.failure) for o in report.outcomes] == [(True, False, None)]


def test_a_cited_hit_past_the_cap_is_recorded_not_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(HS, "MAX_HIT_PAGES_PER_SITE", 1)
    both = (
        "It is dated.\nVERDICT: WRONG\nPROPOSED: -1000\n"
        f'SOURCE: {HIT} - "{QUOTE}"\nSOURCE: {OTHER_HIT} - "100 B.C. to A.D. 1300"\n'
    )
    root = _batch_dir(tmp_path, answers={"period_start": both})
    pages = Pages({HIT: httpx.Response(200, text=CARRYING)})
    report = _verify(root, pages)
    assert pages.asked == [HIT]
    first, second = report.outcomes
    assert first.stored and second.failure is not None and "cite 2 search hits" in second.failure
    assert second.attempts == []
    # The record is read back as that hit's failure, so its citation stays unverified.
    failures = MS.read_fetch_failures(root / "fetch.json")[SITE]
    assert failures == {SE.hit_page_feature(OTHER_HIT): second.failure}


def test_a_hit_url_asking_for_raw_geometry_is_recorded_not_fetched(tmp_path: Path) -> None:
    dump = "https://api.openstreetmap.org/api/0.6/map?bbox=1,2,3,4"
    root = _batch_dir(
        tmp_path, hits=((dump, "a dump"),), answers={"period_start": _answer(url=dump)}
    )
    pages = Pages({})
    (outcome,) = _verify(root, pages).outcomes
    assert pages.asked == []
    assert outcome.failure is not None and outcome.failure.startswith("not fetched:")


def test_a_batch_that_bought_no_search_is_refused(tmp_path: Path) -> None:
    root = _batch_dir(tmp_path)
    batch = json.loads((root / "input.json").read_text(encoding="utf-8"))
    batch["sites"] = [_site(search=False)]
    with pytest.raises(R.InputError, match="carries no search_fields"):
        HS.verify_batch(
            batch=batch,
            fetcher=Pages({}).fetcher(),
            store=F.EvidenceStore(root / "evidence"),
            answers=F.EvidenceStore(root / "answers"),
            ledger=L.Ledger(tmp_path / "L.jsonl"),
        )


def test_two_cited_urls_under_one_feature_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    both = (
        "It is dated.\nVERDICT: WRONG\nPROPOSED: -1000\n"
        f'SOURCE: {HIT} - "{QUOTE}"\nSOURCE: {OTHER_HIT} - "100 B.C. to A.D. 1300"\n'
    )
    root = _batch_dir(tmp_path, answers={"period_start": both})
    monkeypatch.setattr(SE, "hit_page_feature", lambda url: "hitpage.000000000000")
    with pytest.raises(R.InputError, match="share the feature"):
        _verify(root, Pages({}))


def test_the_hit_page_feature_is_a_digest_of_the_url() -> None:
    digest = hashlib.sha1(HIT.encode("utf-8"), usedforsecurity=False).hexdigest()
    assert SE.hit_page_feature(HIT) == f"hitpage.{digest[:12]}"
    assert SE.hit_page_feature(HIT) != SE.hit_page_feature(OTHER_HIT)


# ── the page as text ─────────────────────────────────────────────────────────────────────────


def test_a_hit_page_is_read_as_its_text_with_the_entities_undone() -> None:
    page = (
        "<html><head><style>p { color: red }</style><script>var x = 'Toro';</script></head>"
        "<body><p>Petroglyphs &amp; engravings, dated to 1000&#8211;300 BC.</p></body></html>"
    )
    text = SE.hit_page_text(page.encode("utf-8"))
    assert text == "Petroglyphs & engravings, dated to 1000–300 BC."
    # the quote a finder copies from the rendered page is found by the pipeline's own rule
    assert DS.quote_occurs("Petroglyphs & engravings, dated to 1000-300 BC.", text)


def test_the_page_reader_is_the_one_lyra_uses() -> None:
    """One spelling of "a page as text": the Lyra handler's reader, moved to `pipeline.utils.text`."""
    from pipeline.lyra.handlers import content_fetch
    from pipeline.utils import text as pipeline_text

    assert content_fetch.extract_text_from_html is pipeline_text.extract_text_from_html
    assert SE.extract_text_from_html is pipeline_text.extract_text_from_html


def test_a_page_that_is_not_utf8_text_is_unreadable() -> None:
    with pytest.raises(SE.UnreadablePage, match="not UTF-8 text"):
        SE.hit_page_text(b"%PDF-1.7\n\xe2\xe3\xcf\xd3 stream")


# ── the reviewer ─────────────────────────────────────────────────────────────────────────────


def _review_plan(root: Path) -> RS.ReviewPlan:
    site = json.loads((root / "input.json").read_text(encoding="utf-8"))["sites"][0]
    return RS.plan_site(
        batch_id=BATCH,
        site=site,
        answers=F.EvidenceStore(root / "answers"),
        store=F.EvidenceStore(root / "evidence"),
        failures=MS.read_fetch_failures(root / "fetch.json").get(SITE),
    )


def test_the_reviewer_is_not_asked_about_a_cited_hit_nobody_tried_to_verify(
    tmp_path: Path,
) -> None:
    root = _batch_dir(tmp_path)
    with pytest.raises(MS.EvidenceUnusable, match="run `phase3-run verify-hits`"):
        _review_plan(root)


def test_the_reviewer_is_shown_the_page_behind_the_hit(tmp_path: Path) -> None:
    root = _batch_dir(tmp_path)
    _verify(root, Pages({HIT: httpx.Response(200, text=TORO_MUERTO)}))
    (call,) = _review_plan(root).calls
    assert f'feature="{SE.hit_page_feature(HIT)}" status="present" url="{HIT}"' in call.call.prompt
    assert "Toro Muerto is a petroglyph site in Peru." in call.call.prompt
    # The question is the frozen one: the page is added evidence, not a changed question.
    assert call.call.prompt.startswith(f"<question>\n{MS.REVIEWER_QUESTION}\n</question>")


def test_a_long_hit_page_is_cut_for_the_prompt_and_read_whole_by_the_citation_check(
    tmp_path: Path,
) -> None:
    filler = " ".join(["The site lies on the coast."] * 600)  # ~17,000 characters
    page = f"<p>{filler}</p><p>{QUOTE}</p>"
    root = _batch_dir(tmp_path)
    _verify(root, Pages({HIT: httpx.Response(200, text=page)}))
    (excerpt,) = [e for e in _excerpts(root) if e.kind == MS.KIND_HIT_PAGE]
    assert excerpt.text is not None and excerpt.page_text is not None
    assert len(excerpt.text) == MS.HIT_PAGE_PROMPT_CHARS
    assert excerpt.text.endswith(MS.HIT_PAGE_CUT_MARKER)
    assert QUOTE not in excerpt.text and QUOTE in excerpt.page_text
    claim = DS.SourceClaim(HIT, QUOTE)
    assert DS.claim_problems([claim], DS.pages_from_excerpts(_excerpts(root))) == ()


def test_the_hit_pages_share_the_room_the_evidence_bound_leaves(tmp_path: Path) -> None:
    """A site whose other evidence nearly fills the bound shows its pages in what is left, so the
    reviewer's prompt stays inside the bound the finder's was built under."""
    root = _batch_dir(tmp_path)
    store = F.EvidenceStore(root / "evidence")
    enwiki = store.path_for(SITE, F.FEATURE_ENWIKI)
    enwiki.write_text("x" * (MS.MAX_EVIDENCE_CHARS - 2_000), encoding="utf-8")
    long_page = "<p>" + " ".join(["Toro Muerto lies in Peru."] * 1_000) + "</p>"
    _verify(root, Pages({HIT: httpx.Response(200, text=long_page)}))
    excerpts = _excerpts(root)
    (page,) = [e for e in excerpts if e.kind == MS.KIND_HIT_PAGE]
    assert page.chars < MS.HIT_PAGE_PROMPT_CHARS and page.text.endswith(MS.HIT_PAGE_CUT_MARKER)
    MS.check_evidence_bound(SITE, excerpts)  # does not raise
    assert sum(e.chars for e in excerpts) <= MS.MAX_EVIDENCE_CHARS


# ── the writer ───────────────────────────────────────────────────────────────────────────────


def test_a_hit_quote_the_fetched_page_does_not_carry_is_refused(tmp_path: Path) -> None:
    """Las Labradas, the pilot: the snippet carried the sentence, the page (about Toro Muerto) does
    not - the citation fails in the page, and the snippet does not rescue it."""
    root = _batch_dir(tmp_path)
    _verify(root, Pages({HIT: httpx.Response(200, text=TORO_MUERTO)}))
    plan = W.load_plan(root)
    assert plan.rows == []
    (refusal,) = plan.refused_fields(W.RULE_CITATION)
    assert f"quote does not occur in {HIT}" in refusal.detail


def test_a_hit_quote_the_fetched_page_carries_is_planned(tmp_path: Path) -> None:
    root = _batch_dir(tmp_path)
    _verify(root, Pages({HIT: httpx.Response(200, text=CARRYING)}))
    plan = W.load_plan(root)
    assert [(row.column, row.old_value, row.new_value) for row in plan.rows] == [
        ("period_start", "500", "-1000")
    ]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(403, text="Just a moment... Enable JavaScript"), "HTTP 403"),
        (httpx.Response(200, content=b"%PDF-1.7\n\xe2\xe3\xcf\xd3 stream"), "not UTF-8 text"),
    ],
)
def test_a_hit_page_that_could_not_be_fetched_or_read_leaves_the_citation_unverified(
    tmp_path: Path, response: httpx.Response, reason: str
) -> None:
    """A Cloudflare 403 and a PDF, the two ways the pilot's cited pages failed: the row is refused
    under its own rule, and the snippet is not read in the page's place."""
    root = _batch_dir(tmp_path)
    report = _verify(root, Pages({HIT: response}))
    (outcome,) = report.outcomes
    assert reason in str(outcome.failure or outcome.unreadable)
    (page,) = [e for e in _excerpts(root) if e.kind == MS.KIND_HIT_PAGE]
    assert page.text is None and page.citable is None and reason in str(page.failure)
    plan = W.load_plan(root)
    assert plan.rows == []
    (refusal,) = plan.refused_fields(W.RULE_HIT_UNVERIFIED)
    assert HIT in refusal.detail and reason in refusal.detail
    assert plan.refused_fields(W.RULE_CITATION) == []


def test_the_writer_raises_when_nobody_tried_to_verify_a_cited_hit(tmp_path: Path) -> None:
    """No page and no record: `verify-hits` never ran, a hole in the record, not a row's refusal."""
    root = _batch_dir(tmp_path)
    with pytest.raises(MS.EvidenceUnusable, match="no page was fetched for it"):
        W.load_plan(root)


def test_a_citation_of_a_fetched_target_is_checked_as_it_always_was(tmp_path: Path) -> None:
    """The hit-page rule touches hits only: a target's citation needs no hit page at all."""
    site = _site()
    target = F.targets_for_site(site)[0]
    root = _batch_dir(
        tmp_path, answers={"period_start": _answer(url=target.url, quote="query pages")}
    )
    F.EvidenceStore(root / "evidence").path_for(SITE, target.feature).write_text(
        '{"query": {"pages": {}}} The query pages say 1000 BC.', encoding="utf-8"
    )
    plan = W.load_plan(root)
    assert [row.new_value for row in plan.rows] == ["-1000"]


# ── what the finder was shown, for the sealed pilot threshold ────────────────────────────────


def test_the_finders_pages_keep_the_snippet_and_leave_the_hit_page_out(tmp_path: Path) -> None:
    root = _batch_dir(tmp_path)
    _verify(root, Pages({HIT: httpx.Response(200, text=TORO_MUERTO)}))
    excerpts = _excerpts(root)
    shown = DS.finder_pages(excerpts)
    cited = DS.pages_from_excerpts(excerpts)
    assert QUOTE in shown[HIT] and "Toro Muerto is a petroglyph site" not in shown[HIT]
    assert "Toro Muerto is a petroglyph site" in cited[HIT] and QUOTE not in cited[HIT]


# ── the command ──────────────────────────────────────────────────────────────────────────────


def test_verify_hits_without_live_lists_the_cited_hits_and_asks_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _batch_dir(tmp_path)
    argv = ["verify-hits", "--run-dir", str(tmp_path), "--batch-id", BATCH]
    argv += ["--ledger", str(tmp_path / "L.jsonl"), "--pacing-dir", str(tmp_path / "pace")]
    assert R.main(argv) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["live"] is False
    assert [(h["url"], h["on_disk"]) for h in printed["hits"]] == [(HIT, False)]
    assert not (tmp_path / "L.jsonl").exists()
    assert not (tmp_path / BATCH / MS.HIT_REPORT_NAME).exists()


def test_verify_hits_live_writes_its_report_through_the_real_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pages = Pages({HIT: httpx.Response(200, text=CARRYING)})
    real = F.HttpFetcher
    monkeypatch.setattr(
        F,
        "HttpFetcher",
        lambda timeout: real(transport=httpx.MockTransport(pages), timeout=timeout),
    )
    root = _batch_dir(tmp_path)
    argv = ["verify-hits", "--live", "--run-dir", str(tmp_path), "--batch-id", BATCH]
    argv += ["--ledger", str(tmp_path / "L.jsonl"), "--pacing-dir", str(tmp_path / "pace")]
    assert R.main(argv) == 0
    assert pages.asked == [HIT]
    written = json.loads((root / MS.HIT_REPORT_NAME).read_text(encoding="utf-8"))
    assert written["totals"]["stored"] == 1
    assert json.loads(capsys.readouterr().out)["live"] is True
    assert (tmp_path / "pace" / "pathere.org.stamp").exists()  # the request was paced
    assert len(_ledger_lines(tmp_path / "L.jsonl")) == 1


# ── the pilot's scorer: the sealed thresholds, and the writer's decision beside them ─────────


def _pilot(tmp_path: Path, page: str, human: str) -> list[str]:
    """One pilot batch for `score_search_pilot.main`, the human verdict `human` on its field."""
    run = tmp_path / "runs"
    root = _batch_dir(run)
    _verify(root, Pages({HIT: httpx.Response(200, text=page)}))
    gold = tmp_path / "sites.json"
    verdicts = [{"field": "period_start", "verdict": human}]
    records = {"records": [{"site_id": SITE, "verdicts": verdicts}]}
    gold.write_text(json.dumps(records), encoding="utf-8")
    progress = tmp_path / "progress.json"
    progress.write_text(json.dumps({"stopped": None, "failed": {}}), encoding="utf-8")
    argv = ["--run-dir", str(run), "--prefix", "srgd", "--gold", str(gold)]
    return [*argv, "--progress", str(progress)]


def test_the_scorer_reports_what_the_writer_would_write_beside_the_sealed_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The quote is on the fetched page and the human says CORRECT: the sealed block counts one
    harmful decision, and the writer block shows the one row that would reach production."""
    assert score_search_pilot.main(_pilot(tmp_path, CARRYING, "CORRECT")) == 1
    out = capsys.readouterr().out
    assert "FAIL  2 no harmful decision: 1 field(s)" in out
    assert "rows the writer would write: 1" in out and "harmful writes (human CORRECT): 1" in out
    assert "WRITER RESULT: 1 row(s), 1 harmful" in out


def test_the_scorer_keeps_the_sealed_citation_definition_and_the_writer_refuses_the_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Las Labradas: the quote is in the snippet the finder was shown (sealed threshold 1 passes,
    as sealed), but not in the page behind it - the writer refuses the row by its citation rule."""
    score_search_pilot.main(_pilot(tmp_path, TORO_MUERTO, "CORRECT"))
    out = capsys.readouterr().out
    assert "PASS  1 no fabricated citation: 0 answer(s)" in out
    assert "rows the writer would write: 0" in out
    assert f"'rule': '{W.RULE_CITATION}'" in out
    assert "WRITER RESULT: 0 row(s), 0 harmful" in out


def test_the_scorer_names_a_batch_the_writer_cannot_plan_yet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _pilot(tmp_path, CARRYING, "WRONG")
    (tmp_path / "runs" / BATCH / MS.HIT_REPORT_NAME).unlink()
    score_search_pilot.main(argv)
    out = capsys.readouterr().out
    assert f"NOT PLANNED: {BATCH}: no {MS.HIT_REPORT_NAME}" in out
    assert "WRITER RESULT: NOT AVAILABLE" in out
