"""Does the reviewer refute findings without inventing anything, and does it leave alone what it
cannot act on?

Piece 6a of the Phase-3 runner. The discover pass asks the finder's question and nothing else, so its
precision is the pipeline's precision - and the census measured a 60 % false-negative rate. The
reviewer asks the second, differently-worded question, and the pilot measured it refuting 61 % of the
findings it looked at.

The mistakes that matter here are the quiet ones:

* a refutation that cites a page the run never fetched, or quotes a sentence that is not in the page
  we stored - the same fabricated-citation defect as the finder's, and the reason `claim_problems` is
  shared rather than re-written;
* treating `UNRESOLVED` as "not refuted": the three-state value is the stage's whole point, and
  collapsing it would let a finding nobody could confirm be written to the database;
* reviewing a finding that proposes no change, which spends a call to produce an inapplicable verdict
  and hides that the finding was never about a value;
* a field the finder never answered disappearing silently, so an empty reviewer report looks the same
  as a batch that was never judged;
* paying twice for the same question on a second pass.

Each guard below has a test that fails when the guard is removed; the mutation evidence (the
mutation, the failing assertion and the restored file's sha256) is in
`output/remediation/phase3_runner/PIECE6A.md`. Nothing in this file opens a socket or starts a
process: every runner here is scripted.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import review_stage as RS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

NO_EXTENSIONS = Path(__file__).resolve().parent / "fixtures" / "pi_probe_no_extensions.json"
PAGE_TEXT = "Cave text xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#: A URL key for the parse-only tests, which bring their own `pages` mapping. The batch-level tests
#: must not use it: they derive the URL the run really fetched (`_page_url`), because a citation
#: naming a URL nobody asked for is the very defect those tests are about.
CITED_URL = "https://en.wikipedia.org/w/api.php?action=query&titles=Cave%201&format=json"


# ── helpers ──────────────────────────────────────────────────────────────────────────────────


def _usage() -> Any:
    """The captured settled usage, so every scripted call carries real numbers."""
    lines = NO_EXTENSIONS.read_text(encoding="utf-8").splitlines()
    return MS.parse_stream(lines, source=str(NO_EXTENSIONS)).usage


def _site(site_id: str = "site-1", *, name: str = "Cave 1") -> dict[str, Any]:
    actual = dict.fromkeys(SP.DISCOVER_FIELDS, "a value")
    return {
        "findings": [SP.finding_row(field, actual[field]) for field in SP.DISCOVER_FIELDS],
        "name": name,
        "site_id": site_id,
    }


def _batch(*sites: dict[str, Any]) -> dict[str, Any]:
    return {"batch_id": "batch-0001", "ordinal": 1, "sites": list(sites)}


def _evidence_store(root: Path, *sites: str) -> F.EvidenceStore:
    """An evidence store holding exactly the page the finder and the reviewer both read."""
    store = F.EvidenceStore(root)
    for site_id in sites:
        path = store.path_for(site_id, F.FEATURE_ENWIKI)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PAGE_TEXT, encoding="utf-8")
    return store


def _page_url(site: dict[str, Any]) -> str:
    """The enwiki URL the run actually asks for this site's page - derived from the code, never
    guessed: a citation naming a URL nobody asked for is exactly what these tests are about."""
    return next(t.url for t in F.targets_for_site(site) if t.feature == F.FEATURE_ENWIKI)


def _source(site: dict[str, Any], *, quote: str = "Cave text") -> str:
    return f'SOURCE: {_page_url(site)} - "{quote}"'


def _finder_answer(
    site: dict[str, Any],
    *,
    verdict: str = "WRONG",
    proposed: str | None = "Cave",
    with_source: bool = True,
    quote: str = "Cave text",
) -> str:
    """A finder's answer that parses without a single problem - the only kind that is reviewed."""
    lines = ["The page calls it a cave.", f"VERDICT: {verdict}"]
    if proposed is not None:
        lines.append(f"PROPOSED: {proposed}")
    if with_source:
        lines.append(_source(site, quote=quote))
    return "\n".join(lines) + "\n"


def _answer_file(store: F.EvidenceStore, site_id: str, field: str, text: str) -> Path:
    path = store.path_for(site_id, field)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ScriptedRunner:
    """A fake runner: counts calls, answers with a fixed text, never starts a process."""

    def __init__(
        self, text: str = "REFUTED: NO\nWHY: the page says exactly what the record says\n"
    ):
        self.text = text
        self.calls: list[MS.ModelCall] = []
        self.usage = _usage()

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        return MS.ModelAnswer(text=self.text, usage=self.usage)


class ExplodingRunner:
    """A runner that fails the test if anything is bought - the only proof a call was skipped."""

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:  # pragma: no cover - must not run
        raise AssertionError(f"a call was bought for {call.label} although the answer was on disk")


def _by_field(verdicts: list[RS.ReviewVerdict], field: str) -> RS.ReviewVerdict:
    """One field's verdict. Selecting by field keeps these tests independent of report order."""
    hits = [v for v in verdicts if v.field == field]
    assert len(hits) == 1, f"{len(hits)} verdicts for {field!r}"
    return hits[0]


def _ledger(tmp_path: Path) -> L.Ledger:
    return L.Ledger(tmp_path / "LEDGER.jsonl")


# ── the answer's shape ───────────────────────────────────────────────────────────────────────


def test_a_refutation_from_the_reviewers_own_knowledge_needs_no_source() -> None:
    """A refuter with no fetch step cannot cite a page it never fetched.

    This used to be a problem, and that made every knowledge-based refutation unusable: it fell to
    `UNRESOLVED`, the one value that never lets a state change, so the strongest answer the reviewer
    can give was silently turned into the weakest. Phase 3 asks stage 2 to refute "using its own
    research - not by re-reading stage 1's evidence", so the parser has to accept it. The citation
    rules that remain are the ones the plan's method does impose, and the two tests below still
    hold: any `SOURCE:` that is given must be a page this run fetched, with a quote that occurs in
    it.
    """
    answer = RS.parse_review("REFUTED: YES\nWHY: the page is about another cave\n")
    assert answer.refuted is True
    assert answer.problems == (), answer.problems
    assert answer.complete
    assert answer.sources == ()


def test_a_refutation_that_cites_a_page_the_run_never_fetched_is_a_problem() -> None:
    text = (
        "REFUTED: YES\nWHY: the page is about another cave\n"
        'SOURCE: https://example.org/never-fetched - "the other cave"\n'
    )
    answer = RS.parse_review(text)
    pages = {CITED_URL: PAGE_TEXT}
    problems = answer.problems + DS.claim_problems(answer.sources, pages)
    assert any("was not fetched by this run" in p for p in problems), problems


def test_a_refutation_whose_quote_is_not_in_the_page_the_run_stored_is_a_problem() -> None:
    text = (
        "REFUTED: YES\nWHY: the page says otherwise\n"
        f'SOURCE: {CITED_URL} - "a sentence that is not in the stored page"\n'
    )
    answer = RS.parse_review(text)
    problems = answer.problems + DS.claim_problems(answer.sources, {CITED_URL: PAGE_TEXT})
    assert any("quote does not occur" in p for p in problems), problems


def test_an_honest_refutation_has_no_problems() -> None:
    text = f'REFUTED: YES\nWHY: the page is about another cave\nSOURCE: {CITED_URL} - "Cave text"\n'
    answer = RS.parse_review(text)
    assert answer.problems == ()
    assert answer.refuted is True
    assert answer.reason.startswith("the page is about another cave")
    assert DS.claim_problems(answer.sources, {CITED_URL: PAGE_TEXT}) == ()


def test_unresolved_is_neither_refuted_nor_not_refuted() -> None:
    """The three-state value: `UNRESOLVED` must not be readable as `refuted = False`."""
    answer = RS.parse_review("REFUTED: UNRESOLVED\nWHY: the page does not settle it\n")
    assert answer.problems == ()
    assert answer.refuted is None
    verdict = RS.ReviewVerdict(
        site_id="site-1", field="description", refuted=answer.refuted, reason=answer.reason
    )
    assert verdict.asked
    assert verdict.refuted is None
    assert not verdict.applies, "an unresolved finding must not be applied"


def test_a_not_refuted_verdict_that_carries_a_source_is_a_problem() -> None:
    text = (
        "REFUTED: NO\nWHY: the page says exactly what the record says\n"
        f'SOURCE: {CITED_URL} - "Cave text"\n'
    )
    answer = RS.parse_review(text)
    assert any("belongs to `REFUTED: YES`" in p for p in answer.problems), answer.problems


def test_a_review_without_a_refuted_line_is_a_problem() -> None:
    answer = RS.parse_review("WHY: I looked at it\n")
    assert answer.refuted is None
    assert any("0 `REFUTED:` line(s)" in p for p in answer.problems), answer.problems


def test_a_refuted_line_with_a_value_outside_the_vocabulary_is_a_problem() -> None:
    answer = RS.parse_review("REFUTED: MAYBE\nWHY: unclear\n")
    assert answer.refuted is None
    assert any("is not one of YES, NO, UNRESOLVED" in p for p in answer.problems), answer.problems


def test_two_refuted_lines_are_a_problem() -> None:
    answer = RS.parse_review("REFUTED: YES\nREFUTED: NO\nWHY: both\n")
    assert any("2 `REFUTED:` line(s)" in p for p in answer.problems), answer.problems


def test_a_numbered_verdict_line_is_still_a_verdict() -> None:
    """The question numbered its answer steps, and one measured answer numbered the verdict too.

    `a5d9e9a7%2Fcard_description` came back as "1. The first half fails: ... 2. REFUTED: YES". The
    pattern matched nothing, so a refutation that named its reason was read as `UNRESOLVED`, and its
    `SOURCE:` line then tripped the wrong-verdict check - both problems from the numbering, neither
    from the content. The guards are unchanged: exactly one hit, and a value from the vocabulary.
    """
    answer = RS.parse_review(
        "1. The first half fails.\n2. REFUTED: NO\n\nWHY: the proposal stands\n"
    )

    assert answer.problems == ()
    assert answer.refuted is False


def test_the_numbered_tolerance_does_not_swallow_a_second_verdict() -> None:
    """One measured answer wrote `REFUTED: YES`, a `WHY:` line, and then `REFUTED: YES` again.

    That is a real shape error - the model answered its own numbered step and then restated the
    verdict - and reading the first hit would hide it. Two hits must stay a problem.
    """
    answer = RS.parse_review("REFUTED: YES\nWHY: it names a reason\n\nREFUTED: YES\n")

    assert answer.refuted is None
    assert any("2 `REFUTED:` line(s)" in p for p in answer.problems), answer.problems


def test_a_review_without_a_why_line_is_a_problem() -> None:
    answer = RS.parse_review("REFUTED: NO\n")
    assert any("no `WHY:` sentence" in p for p in answer.problems), answer.problems


# ── a WHY line that names a failing half (2026-09-23) ────────────────────────────────────────

#: Real `WHY:` lines of `REFUTED: NO` answers, each naming a failing half, and the phrase that names
#: it. From the search pilot (`runs/search-gold`) and the mass lane's hand-held rows
#: (`logs/_write_apply/HOLDS.jsonl`), quoted as the reviewer wrote them.
FAILING_HALF_WHY: tuple[tuple[str, str], ...] = (
    (  # Lake Mungo period_start, the pilot
        "Both halves fail: the evidence actually supports a value around -500 (the store) rather "
        "than -50000, so neither the reasoning nor the proposed value holds",
        "both halves fail",
    ),
    (  # Lake Mungo site_type, the pilot
        'Neither half holds — the reason (no source states "Geological interest") does not show '
        "the stored value wrong",
        "neither half holds",
    ),
    (  # Odeon Theatre card_description, the pilot
        "no evidence contradicts that clause, and the stored text is not shown wrong.",
        "the stored value is not shown wrong",
    ),
    (  # Huandacareo site_type, the re-review of 2026-09-23 (REFUTED: NO)
        "The stored value is not wrong — the finder's reasons conflict with the evidence, which "
        'describes Huandacareo as a site "about two kilometers from the center of the Huandacareo '
        'town and municipality"',
        "the stored value is not wrong",
    ),
    (  # Cueva de los Murcielagos period_start, the pilot
        "The stored value 1 is not shown wrong: `period_start` is a sort key",
        "the stored value is not shown wrong",
    ),
    (  # Tan Hill site_type, a hold
        'the finder\'s proposal "Natural feature" is not a site-type value and is contradicted by '
        "the documented hill figure, so neither half is established.",
        "neither half is established",
    ),
    (  # Harappa period_start, a mass-lane write
        "The half that fails is the reason — the excavators' chronology gives the site's own "
        "earliest occupation",
        "the half that fails is named",
    ),
    (  # Jarlshof period_start, a mass-lane write
        "The evidence does not show the stored -3000 wrong: the enwiki extract explicitly says the "
        "oldest known remains date from the Bronze Age",
        "does not show the stored value wrong",
    ),
    (  # Ollantaytambo period_start, a hold
        "the site's own Inca founding is stated as mid/late 15th century, so nothing shows the "
        "stored value wrong",
        "nothing shows the stored value wrong",
    ),
    (  # Copan Ruins site_type, a mass-lane write
        'P31 = Q839954 (archaeological site) is a less specific value than the stored "Temple '
        'complex", and a broader Wikidata type does not make the finer stored type wrong.',
        "does not make the stored value wrong",
    ),
    (  # Uruk period_start, a hold
        "the enwiki extract's own founding date of c. 5000 BC supports a value earlier than -3200, "
        "so the evidence does not establish the stored value is wrong.",
        "does not establish that the stored value is wrong",
    ),
    (  # Pagans Hill Roman Temple site_type, a hold
        'The stored "Temple complex" is not contradicted — the enwiki extract itself says the '
        'site "formed a large pilgrimage centre"',
        "the stored value is not contradicted",
    ),
    (  # Alte Burg site_type, a hold
        'Wikidata\'s "castle in Langenenslingen" description does not contradict the stored '
        "`Fortress/citadel`.",
        "does not contradict the stored value",
    ),
    (  # Tulum period_start, a hold
        'The evidence supports the stored value: the enwiki text says Tulum "achieved its greatest '
        'prominence between the 13th and 15th centuries,"',
        "the evidence supports the stored value",
    ),
    (  # Castell Dinas period_start, a hold
        "The proposed -600 is contradicted by the evidence itself, which says the hillfort dates "
        'from "600 BC to 50 AD"',
        "the proposed value is contradicted",
    ),
    (  # Pen Dinas period_start, a mass-lane write
        "The reason fails: the English Wikipedia source dates the hillfort's construction",
        "the reason fails",
    ),
    (  # Amaru Marka Wasi site_type, a mass-lane write
        "The reason does not hold — the evidence's own text describes Amaru Marka Wasi as an "
        '"archaeological site"',
        "the reason does not hold",
    ),
    (  # Roman Emperors Route site_type, a mass-lane write
        "the proposed `Road/avenue/trackway` is not contradicted either, but the reason half fails "
        "because enwiki/Wikidata describe it as a project/route",
        "the reason half fails",
    ),
    (  # a YES answer of the mass run (batch-0007), the value half in the reviewer's own words
        "while -4000 is not contradicted by any dating evidence for this tomb, so the second half "
        "fails.",
        "the value half fails",
    ),
    (  # a NO answer of the mass run (batch-0237)
        'The proposal fails, not the reason: the stored "City/town/settlement" is a project bucket '
        "for an inhabited site",
        "the proposal fails",
    ),
    (  # a hand-held row of the mass lane (batch-0053, 50873aa8 period_start), `REFUTED: NO`: the
        # half's name in quotes. Until 2026-09-23 only the value-half phrase caught it, and by its
        # own misreading ("the proposed year 300 is contradicted neither by ...", the half that holds)
        'The stored value 1 is the period_start year 1 (used as a sort key within the "1 - 500 AD" '
        "bucket), and the finder supplies no evidence that the year 1 is what the project must "
        'store; the "reason" half fails because the evidence shows an occupation beginning at 300 '
        "AD, not a mis-stored 1, and the proposed year 300 is contradicted neither by Wikipedia nor "
        "Wikidata's P580 +300.",
        "the reason half fails",
    ),
    (  # the same quoted name for the value half, which no answer of the mass run uses yet
        "the reason stands, but the `value` half fails because the page dates the site later",
        "the value half fails",
    ),
)


@pytest.mark.parametrize(("why", "phrase"), FAILING_HALF_WHY)
def test_a_why_line_that_names_a_failing_half_is_recognised(why: str, phrase: str) -> None:
    assert RS.failing_half(why) == phrase


#: Real `WHY:` lines that say both halves hold, including the wordings closest to a failing half.
#: A phrase that caught one of these would hold a row the reviewer cleared in so many words.
BOTH_HALVES_HOLD_WHY: tuple[str, ...] = (
    # Aguada Fenix, a mass-lane write
    "The evidence supports the proposed value — the Wikipedia extract states the monumental "
    'structure "is believed to have been built from around 1000 BC to 800 BC," so the stored -1500 '
    "is contradicted and -1000 is not.",
    # Celemantia, a mass-lane write
    "so neither the reason nor the proposed `Fortress/citadel` is contradicted.",
    # Piddington Roman Villa, a mass-lane write
    "so neither the reason (that -3000 is unsupported) nor the proposed -3500 is contradicted; "
    "both halves hold.",
    # Debdieba, a mass-lane write
    "but the proposed -3000 is contradicted by neither source and is supported by both",
    # Dipylon, a mass-lane write
    "however the proposed -478 is contradicted by nothing in the evidence",
    # Maiden Castle, a mass-lane write
    "and the proposed -600 matches that founding value, so neither the reason nor the proposal "
    "fails.",
    # Dos Pilas, a mass-lane write
    "The evidence supports the stored value being wrong - both the enwiki extract (founded AD 629) "
    "and Wikidata P571 (629 CE) date the site's founding to the 7th century",
    # Cadbury Hill, a mass-lane write
    "and nothing in the evidence supports the stored -3000 (3rd millennium BC), so both halves "
    "hold: the reason stands and the proposed -1000 is not contradicted.",
    # Ahu Tongariki period_start, the pilot
    "The cited source explicitly says most image ahu were built circa 1000-1500 AD, so the stored "
    "value 1 (bucket 1-500 AD) is wrong and the proposed 1000 is supported.",
    # Aubrey Holes period_start, the pilot (refused by the bucket gate, not by a phrase)
    "Neither half fails — the cited inventory gives the Aubrey Holes as a Neolithic pit dated "
    "-4000 to -2351, so -4500 does fall outside that range and the proposed -4000 is not "
    "contradicted",
    # Asclepieion of Athens: a conditional, not a verdict on the half
    "the second half fails only if the proposal is contradicted — it is not",
    # Roman Bridge of Cordoba, a mass-lane write: "stored" and "not contradicted" in one sentence,
    # about the two different values
    "so the stored -500 is wrong and the proposed -100 is not contradicted; both halves hold.",
    # ── "the proposed value is contradicted" in a sentence that says the value half holds
    # (2026-09-23, the fixer's review): the mass run's own NO answers
    # batch-0237 34f1acbd card_description: "nor its proposed value"
    'while "oldest military fort in the Timok Valley" is simply the English equivalent of "Valea '
    "Timacului,\" so neither the finding's reason nor its proposed value is contradicted—both "
    "halves hold.",
    # batch-0053 50873aa8 period_start, the value half's clause alone: "contradicted neither by"
    "and the proposed year 300 is contradicted neither by Wikipedia nor Wikidata's P580 +300.",
    # batch-0151 1374c196 card_description: a question the sentence answers "No" to
    "The evidence supports the finder's reason (eight stones survive: five standing, three "
    'recumbent), but the proposed value\'s "sandstone" is contradicted by the evidence? No — the '
    'source says the stones are sandstone boulders of the Bagshot Beds, so "sandstone" is '
    'actually supported; the "eight surviving boulders" and "~26 m" both stand, so the reason '
    "holds and the proposal is not contradicted.",
    # batch-0171 44354857 period_start, the value half's clause alone: a conditional
    "and the proposed -430 is contradicted only if the earlier dedication is ignored",
    # the reviewer's own synthetic check of the same wording
    "The proposed -1000 is contradicted neither by enwiki nor by Wikidata.",
    # the other owners a "neither ... nor <owner> proposed value" sentence can name
    "so neither the reason nor the finding's proposed value is contradicted.",
    "so neither the reason nor the finder's proposed value is contradicted.",
    "so neither the reason nor finding's proposed value is contradicted.",
    "so neither the reason nor finder’s proposed value is contradicted.",
    # ── one sentence per exclusion that had no negative of its own (2026-09-23, the fixer's
    # review): without it, the exclusion could be deleted with every test green
    # `(?<!no )` on "the evidence supports the stored value" - batch-0045 69fb2e9b site_type
    "the enwiki extract and Wikidata description call it an archaeological site, while no "
    'evidence supports the stored "City/town/settlement"',
    # `(?<!nothing in the )` on the same phrase - batch-0114 6b730ea0 site_type (the Cadbury Hill line
    # above names a bare year, which the phrase never reads, so it did not protect this exclusion)
    "the enwiki extract both class the site only as an archaeological site, and nothing in the "
    'evidence supports the stored "City/town/settlement"; the proposed "Archaeological site" '
    "matches the sources.",
    # `(?<!nor )` on the same phrase
    'neither the extract nor evidence supports the stored "Temple complex" as a type',
    # `(?! only if)` on "the reason / first half fails" - batch-0272 6a8bc59c card_description
    'The first half fails only if "1st-century BC" is asserted as a dating',
    # `(?! only if)` on "the reason fails"
    "the reason fails only if the extract is wrong, and it is not",
    # `(?<!nor )` on "the reason fails"
    "so neither the proposal nor the reason fails.",
    # `(?! only if)` on "the proposal fails"
    "the proposal fails only if the page is misread, and it is not",
    # `(?!(?:that )?the propos)` on "does not show ... wrong"
    "the evidence does not show the proposed -1000 wrong",
    # `(?<!if the )` on "the proposed value is contradicted"
    "it would fail if the proposed -700 is contradicted by a dated source, and none is given",
    # `(?<!whether the )` on the same phrase
    "the question is whether the proposal is contradicted, and it is not",
    # `(?<!nor )` on the same phrase: the owner-less "nor proposed"
    "so neither the reason nor proposed -3500 is contradicted.",
)


@pytest.mark.parametrize("why", BOTH_HALVES_HOLD_WHY)
def test_a_why_line_that_says_both_halves_hold_names_no_failing_half(why: str) -> None:
    assert RS.failing_half(why) is None


def test_every_hand_read_phrase_is_a_failing_half_phrase() -> None:
    """The writer looks a hold's phrase up by name: a hand-read key no phrase carries would route
    nothing, silently. Each count is (false holds, written rows held), so false <= held."""
    names = {name for name, _ in RS.FAILING_HALF_PHRASES}
    assert set(RS.HAND_READ_PHRASES) <= names
    assert all(0 < false <= held for false, held in RS.HAND_READ_PHRASES.values())


# ── what gets reviewed at all ────────────────────────────────────────────────────────────────


def test_only_a_complete_wrong_finding_is_asked_about(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    _answer_file(
        answers,
        "site-1",
        "period_start",
        _finder_answer(site, verdict="CORRECT", proposed=None, with_source=False),
    )
    _answer_file(answers, "site-1", "site_type", _finder_answer(site, proposed=None))

    plan = RS.plan_batch(batch=_batch(site), answers=answers, store=store)

    assert [item.call.field for item in plan.calls] == ["description"], plan.calls
    reasons = {v.field: v.unreviewable or "" for v in plan.unreviewable}
    assert len(reasons) == 4, reasons
    assert "proposes no change" in reasons["period_start"], reasons
    assert "not usable as it stands" in reasons["site_type"], reasons
    assert "a `WRONG` verdict with no `PROPOSED:` value" in reasons["site_type"], reasons


def test_a_field_the_finder_never_answered_is_recorded_not_silently_skipped(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")

    plan = RS.plan_batch(batch=_batch(site), answers=answers, store=store)

    assert plan.calls == []
    assert len(plan.unreviewable) == len(SP.DISCOVER_FIELDS)
    for verdict in plan.unreviewable:
        assert not verdict.asked
        assert "is not on disk" in (verdict.unreviewable or ""), verdict
        assert verdict.refuted is None


def test_a_site_whose_findings_all_propose_nothing_buys_no_call(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    for field in SP.DISCOVER_FIELDS:
        _answer_file(
            answers,
            "site-1",
            field,
            _finder_answer(site, verdict="UNVERIFIABLE", proposed=None, with_source=False),
        )
    runner = ScriptedRunner()

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=runner,
        store=store,
        answers=answers,
        reviews=F.EvidenceStore(tmp_path / "reviews"),
        ledger=_ledger(tmp_path),
    )

    assert runner.calls == []
    assert report.calls == 0
    assert report.cost_usd == 0.0
    assert len(report.verdicts) == len(SP.DISCOVER_FIELDS)
    assert all(v.unreviewable for v in report.verdicts)


# ── the prompt ───────────────────────────────────────────────────────────────────────────────


def test_the_prompt_carries_the_finders_answer_verbatim_and_the_same_page(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    finder_text = _finder_answer(site)
    _answer_file(answers, "site-1", "description", finder_text)

    plan = RS.plan_batch(batch=_batch(site), answers=answers, store=store)

    assert len(plan.calls) == 1
    prompt = plan.calls[0].call.prompt
    assert finder_text.strip() in prompt, "the finding must travel verbatim, not re-rendered"
    assert "a value" in prompt, "the stored value the finder judged must be in the prompt too"
    assert PAGE_TEXT in prompt, "the reviewer reads the same page the finder read"
    assert MS.REVIEWER_QUESTION in prompt
    assert plan.calls[0].call.stage.value == "reviewer"
    assert plan.calls[0].call.field == "description"


def test_the_reviewer_question_asks_for_the_verdict_line_the_parser_wants(tmp_path: Path) -> None:
    """The reviewer's question was never measured before it was asked twelve times, and it never
    asked for the line the parser reads.

    In the round-6 gold run every one of the 12 answers came back with no `REFUTED:` line at all -
    the model wrote `**VERDICT: none refuted**` in a shape of its own - so all 12 were read as
    `UNRESOLVED`, `applies` was false everywhere, and the write path would have had nothing to
    apply. The finder's frozen question spells its answer shape out; this one now does too, and the
    shape is taken from the parser's own vocabulary so that a drift on either side fails here.
    """
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert f"REFUTED: {' | '.join(RS.REFUTED_VALUES)}" in prompt
    assert "WHY:" in prompt


def test_the_reviewer_question_lets_its_own_knowledge_refute_a_finding(tmp_path: Path) -> None:
    """Stage 2 refutes with its own research, and `refuted = false` is the only write gate.

    The plan asks the reviewer to "refute every error claim using its own research - not by
    re-reading stage 1's evidence", and the rule this test replaces forbade exactly that: it made
    the reviewer's own knowledge unusable for refutation, which is the one job that stage has. The
    guard that remains is the one that matters - a refutation must name the claim that fails, or it
    is a guess.
    """
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert "your own knowledge of the subject" in prompt, "the plan's own research must be usable"
    assert "may not refute" not in prompt, "the replaced rule forbade what Phase 3 asks for"
    assert "Name which on the `WHY:` line" in prompt, "a refutation of nothing is a guess"


def test_the_reviewer_question_names_both_ways_a_finding_can_fail(tmp_path: Path) -> None:
    """Three measured rounds fixed the question's referent; the record of them is the reason.

    Round 1 forbade refuting from the reviewer's own knowledge: measured over the 13 findings of the
    blinded truth set it refuted 3 and left 4 of 6 suspect findings standing. Round 2 allowed
    knowledge but left "the claim" without a referent, and the reviewer attached it per call: in
    three of the 13 its own `WHY:` sentence names evidence that *supports* the finding while the
    verdict kills it, and in one it names evidence that defeats the finding while the verdict keeps
    it. Round 3 pinned the referent to the proposal alone, and that made the stage nearly inert - 1
    refutation in 13 - so the only write gate in Phase 3 waved everything through.

    What the writer needs is neither half alone: a finding fails when the reason it gives does not
    hold, *or* when the value it would write is contradicted. That is what the question says now.
    """
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert "Refute it if either half fails" in prompt
    assert "the reason it gives does not hold" in prompt
    assert "the proposed value is contradicted by the evidence" in prompt
    assert "is **not** by itself a reason to refute" in prompt, (
        "weak-looking stored text is no proof"
    )


def test_the_reviewer_is_briefed_on_every_false_alarm_the_plan_lists(tmp_path: Path) -> None:
    """Phase 3: the reviewer "must be briefed on the false-alarm patterns in 4.3".

    The briefing is data (`MS.FALSE_ALARMS`), with `MS.FALSE_ALARM_SOURCES` naming the plan item each
    line paraphrases, and this test reads the plan file itself: the question and the plan have to
    agree on which patterns exist. A paraphrased clause inside a prompt string is exactly what drifts
    unnoticed, and this one is the reviewer's only defence against the false alarms patterns 2 and 11
    measured - the deliberate `England`/`Scotland`/`Wales` vocabulary, and the generalised map that
    draws Northern Ireland as `Ireland` and drops Crimea and Northern Cyprus.
    """
    plan_text = (REPO / "docs" / "procedures" / "SITES_DB_REMEDIATION_2026-09.md").read_text(
        encoding="utf-8"
    )
    section = plan_text.split("### 4.3 ", 1)[1].split("\n### ", 1)[0]
    in_plan = re.findall(r"^(\d+)\. \*\*", section, flags=re.MULTILINE)

    assert len(MS.FALSE_ALARMS) == len(MS.FALSE_ALARM_SOURCES)
    covered = {number for group in MS.FALSE_ALARM_SOURCES for number in group}
    assert covered == {f"4.3.{number}" for number in in_plan}, (
        "the briefing and the plan's 4.3 list must cover the same items"
    )

    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert "False alarms that are not errors" in prompt
    for pattern in MS.FALSE_ALARMS:
        assert pattern in prompt


def test_the_question_and_the_parser_agree_that_a_source_belongs_to_yes(tmp_path: Path) -> None:
    """The question states a fact about the parser, so both sides are asserted together.

    The closing paragraph of the question tells the model that a `SOURCE:` line on a verdict that is
    not `YES` is read as a problem. That is a clause about code, written by hand in a string, which
    is how such clauses drift: change the parser and the prompt still promises the old shape. The
    parser's own behaviour and the sentence are therefore pinned in one test - either side moving
    alone fails here.
    """
    answer = RS.parse_review(
        'REFUTED: NO\nWHY: the proposal stands\nSOURCE: https://example.org/x - "y"\n'
    )
    assert any("belongs to `REFUTED: YES`" in p for p in answer.problems), answer.problems

    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert "A `SOURCE:` line on a verdict that is not `YES` is an " in prompt


def test_the_reviewers_prompt_is_bounded_like_the_finders(tmp_path: Path) -> None:
    site = _site()
    store = F.EvidenceStore(tmp_path / "evidence")
    path = store.path_for("site-1", F.FEATURE_ENWIKI)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (MS.MAX_EVIDENCE_CHARS + 10), encoding="utf-8")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    with pytest.raises(MS.EvidenceOverBound):
        RS.plan_batch(batch=_batch(site), answers=answers, store=store)


# ── the judge ────────────────────────────────────────────────────────────────────────────────


def test_a_review_already_on_disk_is_read_and_not_bought_again(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    reviews = F.EvidenceStore(tmp_path / "reviews")
    _answer_file(reviews, "site-1", "description", "REFUTED: NO\nWHY: already answered once\n")

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=ExplodingRunner(),
        store=store,
        answers=answers,
        reviews=reviews,
        ledger=_ledger(tmp_path),
    )

    assert report.calls == 0
    assert report.resumed == 1
    assert report.cost_usd == 0.0
    verdict = _by_field(report.verdicts, "description")
    assert verdict.reason == "already answered once"
    assert verdict.applies


def test_a_live_review_is_bought_once_written_once_and_counted(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    reviews = F.EvidenceStore(tmp_path / "reviews")
    runner = ScriptedRunner()
    ledger = _ledger(tmp_path)
    before = ledger.path.read_text(encoding="utf-8") if ledger.path.exists() else ""

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=runner,
        store=store,
        answers=answers,
        reviews=reviews,
        ledger=ledger,
    )

    assert len(runner.calls) == 1
    assert report.calls == 1
    assert report.resumed == 0
    assert report.cost_usd == pytest.approx(runner.usage.cost_usd)
    assert (
        reviews.path_for("site-1", "description")
        .read_text(encoding="utf-8")
        .startswith("REFUTED: NO")
    )
    after = ledger.path.read_text(encoding="utf-8")
    assert after != before and "reviewer" in after, "the purchased call belongs in the ledger"
    assert _by_field(report.verdicts, "description").applies


def test_the_report_counts_what_the_verdicts_say(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    reviews = F.EvidenceStore(tmp_path / "reviews")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    _answer_file(answers, "site-1", "period_start", _finder_answer(site))
    _answer_file(answers, "site-1", "site_type", _finder_answer(site))
    _answer_file(answers, "site-1", "country", _finder_answer(site))
    _answer_file(
        answers,
        "site-1",
        "card_description",
        _finder_answer(site, verdict="CORRECT", proposed=None, with_source=False),
    )
    _answer_file(reviews, "site-1", "description", "REFUTED: NO\nWHY: it holds\n")
    _answer_file(
        reviews,
        "site-1",
        "period_start",
        "REFUTED: YES\nWHY: another period\n" + _source(site) + "\n",
    )
    _answer_file(
        reviews, "site-1", "site_type", "REFUTED: UNRESOLVED\nWHY: the page does not settle it\n"
    )
    _answer_file(
        reviews,
        "site-1",
        "country",
        "REFUTED: YES\nWHY: cites a page nobody fetched\n"
        + 'SOURCE: https://example.org/x - "a sentence"\n',
    )

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=ExplodingRunner(),
        store=store,
        answers=answers,
        reviews=reviews,
        ledger=_ledger(tmp_path),
    )
    payload = report.to_dict()

    assert payload["calls"] == 0 and payload["resumed"] == 4
    assert payload["applies"] == 1, payload
    # Two reviewers said YES; one of them cited a page nobody fetched, so it does not apply. The
    # counters report what was said, `applies` reports what a writer may act on - keeping those two
    # apart is the reason both exist.
    assert payload["refuted"] == 2, payload
    assert payload["unresolved"] == 1, payload
    assert payload["unreviewable"] == 1, payload
    assert payload["with_problems"] == 1, payload
    assert sum(1 for v in report.verdicts if v.applies) == 1
    assert not _by_field(report.verdicts, "country").applies
    assert _by_field(report.verdicts, "country").refuted is True
    # And the report reads in the plan's field order, not in the order the fields were judged.
    assert [v.field for v in report.verdicts] == list(SP.DISCOVER_FIELDS)


def test_the_reviewer_writes_its_own_report_and_leaves_the_finders_model_json_alone(
    tmp_path: Path,
) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    finder_report = tmp_path / "batch-0001" / "model.json"
    finder_report.parent.mkdir(parents=True, exist_ok=True)
    finder_report.write_text('{"stage": "finder", "totals": {"calls": 5}}\n', encoding="utf-8")
    before = finder_report.read_bytes()

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=ScriptedRunner(),
        store=store,
        answers=answers,
        reviews=F.EvidenceStore(tmp_path / "batch-0001" / "reviews"),
        ledger=_ledger(tmp_path),
    )
    RS.write_report(tmp_path / "batch-0001" / "review.json", report)

    written = json.loads((tmp_path / "batch-0001" / "review.json").read_text(encoding="utf-8"))
    assert written["stage"] == "reviewer"
    assert written["verdicts"][0]["field"] == "description"
    assert finder_report.read_bytes() == before, (
        "the reviewer must not overwrite the finder's record"
    )


def test_an_unreviewable_verdict_never_applies(tmp_path: Path) -> None:
    """A finding nobody was asked about must not reach a writer as if it had been confirmed."""
    verdict = RS.ReviewVerdict(
        site_id="site-1",
        field="description",
        refuted=None,
        reason="the finder's verdict is 'CORRECT'",
        unreviewable="the finder's verdict is 'CORRECT'",
    )
    assert not verdict.asked
    assert not verdict.applies
    assert verdict.to_dict()["applies"] is False
    assert verdict.to_dict()["asked"] is False
