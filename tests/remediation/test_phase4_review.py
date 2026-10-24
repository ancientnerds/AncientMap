"""Does S6 only ever remove, fail closed on every answer it cannot read, assemble and verify again,
and never buy a review twice?

Work item WB-B3 (`phase4/review4.py`). The reviewer is a scripted `ModelRunner`; the verifier is a
recording stand-in for the `reverify` seam (Track C's `verify4.verify_site`, wired by `run4`). The
silent mistakes: a missing line read as KEEP, a `KEEP because ...` line read as KEEP, a card kept
though the sentence it came from was dropped, a card rebuilt under 80 characters, a site written
without being verified again, a second paid review on a resumed batch, and an unreviewed
`assembly.jsonl` passing for a reviewed one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PHASE_PARENT = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(PHASE_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE_PARENT))

from phase3 import model_stage as MS  # noqa: E402
from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import review4 as RV  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402

#: Four sentences; the card is W2 (84 characters) plus W5 once shortened.
SELECT = "DESC: W1\nDESC: W2\nDESC: W5 -a1\nDESC: W6 -p1\nCARD: W2\nCARD: W5 -a1\n"
#: The same, but W2 loses its last comma segment: alone it is a 58-character card.
SELECT_SHORT = SELECT.replace("DESC: W2\n", "DESC: W2 -t1\n")
W2_CARD = "The temple was built circa 2500 BC by a farming community, whose tombs lie nearby."
ALL_KEEP = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\nCARD: KEEP\n"


class Verifier:
    """The `reverify` seam, recording every assembly it is shown and answering from a script."""

    def __init__(self, answers: list[tuple[M.Hold, ...]] | None = None) -> None:
        self.answers = list(answers or [])
        self.seen: list[M.Assembly] = []

    def __call__(self, site: M.PlanSite, assembly: M.Assembly) -> tuple[M.Hold, ...]:
        assert isinstance(site, M.PlanSite) and isinstance(assembly, M.Assembly)
        self.seen.append(assembly)
        return self.answers.pop(0) if self.answers else ()


def _assembled(tmp_path: Path, sites: tuple[str, ...] = ("site-1",), select: str = SELECT) -> Path:
    batch_dir = X.make_batch(tmp_path, [X.w_site(site) for site in sites])
    runner = X.ScriptedRunner({(site, "select"): select for site in sites})
    assert SEL.select_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir, ledger=tmp_path / "L.jsonl") == 0
    return batch_dir


def _review(
    batch_dir: Path, answer: str | Exception, verifier: Verifier | None = None, site: str = "site-1"
) -> tuple[int, X.ScriptedRunner, Verifier]:
    runner = X.ScriptedRunner({(site, "review"): answer})
    verify = verifier or Verifier()
    code = RV.review_batch(
        batch_dir, ledger=batch_dir.parents[2] / "L.jsonl", runner=runner, reverify=verify
    )
    return code, runner, verify


def _written(batch_dir: Path) -> list[M.Assembly]:
    return M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly)


# ------------------------------------------------------------------------------ the parser


def test_one_keep_line_per_sentence_keeps_everything() -> None:
    verdict = RV.parse_review(ALL_KEEP, sentences=4, card=True)
    assert verdict.kept == (1, 2, 3, 4) and verdict.card_kept is True


@pytest.mark.parametrize(
    ("answer", "kept"),
    [
        ("R1: KEEP\nR2: DROP not about this site\nR3: KEEP\nR4: KEEP\nCARD: KEEP", (1, 3, 4)),
        ("R1: KEEP\nR3: KEEP\nR4: KEEP\nCARD: KEEP", (1, 3, 4)),  # a missing line removes
        ("R1: KEEP\nR2: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP", (1, 3, 4)),  # so does a second one
        ("R1: DROP\nR2: KEEP\nR3: KEEP\nR4: KEEP", (2, 3, 4)),  # a DROP without a reason
    ],
)
def test_anything_but_one_keep_line_removes_the_sentence(
    answer: str, kept: tuple[int, ...]
) -> None:
    assert RV.parse_review(answer, sentences=4, card=True).kept == kept


def test_a_card_that_is_not_kept_exactly_once_is_dropped() -> None:
    assert RV.parse_review("R1: KEEP", sentences=1, card=True).card_kept is False
    assert (
        RV.parse_review("R1: KEEP\nCARD: DROP too vague", sentences=1, card=True).card_kept is False
    )
    assert (
        RV.parse_review("R1: KEEP\nCARD: KEEP\nCARD: KEEP", sentences=1, card=True).card_kept
        is False
    )
    assert RV.parse_review("R1: KEEP", sentences=1, card=False).card_kept is None


@pytest.mark.parametrize(
    ("answer", "card", "detail"),
    [
        ("R1: KEEP\nLooks fine to me.", True, "no contract shape"),
        ("R1: KEEP because it is supported", True, "no contract shape"),
        ("r1: keep", True, "no contract shape"),
        ("R1: KEEP\nR5: KEEP", True, "R5 names no shown sentence"),
        # the numbering starts at 1: R0 and a zero-padded R01 name no shown sentence
        ("R0: KEEP\nR1: KEEP", True, "no contract shape"),
        ("R01: KEEP", True, "no contract shape"),
        ("R1: KEEP\nCARD: KEEP", False, "no card was shown"),
    ],
)
def test_an_answer_in_no_contract_shape_is_unparseable(
    answer: str, card: bool, detail: str
) -> None:
    with pytest.raises(RV.ReviewUnparseable, match=detail):
        RV.parse_review(answer, sentences=4, card=card)


# ------------------------------------------------------------------------------- the stage


def test_the_reviewer_sees_each_sentence_beside_its_untrimmed_source(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    code, runner, _ = _review(batch_dir, ALL_KEEP)
    assert code == 0
    (call,) = runner.calls
    assert call.stage is MS.Stage.REVIEWER and call.answer_key == "review"
    prompt = call.prompt
    assert "published: A second shrine was added later [1]." in prompt
    assert "source sentence: A second shrine (the south shrine) was added later." in prompt
    assert '<source id="R3" section="History">' in prompt
    # W5's two source predecessors are the last two lead sentences, published or not.
    assert (
        "before it: In 1900, the site was cleared of rubble by the island's governor. "
        "It is probably the oldest temple on the island.\n"
    ) in prompt
    assert "card: The temple was built circa 2500 BC" in prompt
    assert "A stored description." not in prompt


def test_the_reviewer_sees_the_whole_passage_the_selector_chose_from(tmp_path: Path) -> None:
    """Pilot 3 (T7): Partiscum's lead was published although the article's own body contradicts
    it; the reviewer was shown each sentence's two source predecessors only - for a lead, nothing -
    so no DROP could see the contradiction. It now sees the selector's pool, every candidate with
    its sid and section, before the numbered sentences; the apparatus stays out, as in the pool."""
    batch_dir = _assembled(tmp_path)
    _, runner, _ = _review(batch_dir, ALL_KEEP)
    prompt = runner.calls[0].prompt
    block = prompt[prompt.index('<source id="PASSAGE" title="Stone Temple">') :]
    block = block[: block.index("</source>")]
    _, sites = B.read_batch(batch_dir)
    lane = B.read_lanes(batch_dir, sites)["site-1"]
    _, _, text, pool = SEL.site_pool(batch_dir, sites[0], lane)
    for sentence in pool:
        section = sentence.section or "lead"
        assert f"\n{sentence.sid} [{section}] {text[sentence.start : sentence.end]}\n" in block
    assert "W7 [History] Excavations in 1911 found pottery, figurines and animal bones." in block
    assert "Smith, J." not in block  # the references section is no passage
    assert prompt.index('<source id="PASSAGE"') < prompt.index('<source id="R1"')


def test_a_lane_r_reviewer_sees_every_page_it_restated() -> None:
    """Lane R selects no pool: its passage is the pages the restatement model read, whole."""
    page = "The mound was raised in the Bronze Age. It was dug in 1901 and found empty."
    doc = X.page_doc("R1", page, url="https://example.org/mound", title="The Mound")
    inputs = A.SiteInputs(
        site=X.plan_site(),
        lane=M.Lane.R,
        sources={"R1": doc},
        texts={"R1": page},
        pool=(),
        selection=None,
        translations=None,
        restatements=(),
    )
    assert RV.passage(inputs) == (
        '<source id="PASSAGE" url="https://example.org/mound" title="The Mound">\n'
        f"{page}\n</source>"
    )


def test_all_kept_writes_the_same_assembly_and_marks_it_reviewed(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    before = _written(batch_dir)
    code, _, verify = _review(batch_dir, ALL_KEEP)
    assert code == 0
    assert _written(batch_dir) == before
    assert verify.seen == before  # verified again, even with nothing dropped
    report = json.loads((batch_dir / B.REVIEW_REPORT).read_text(encoding="utf-8"))
    assert report["error"] is None
    assert report["assembly_sha256"] == B.sha256_file(batch_dir / M.ASSEMBLY_FILE)
    assert report["sites"][0]["card"] == "kept"


def test_a_dropped_sentence_is_assembled_away(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    answer = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: DROP not supported\nCARD: KEEP"
    assert _review(batch_dir, answer)[0] == 0
    (assembly,) = _written(batch_dir)
    assert "A second shrine" not in assembly.description
    assert len(assembly.provenance.sentences) == 3
    assert assembly.provenance.desc_sha256 == M.text_sha256(assembly.description)


#: Pilot 3 (T8, Mersinaki and Diana Fort): the reviewer dropped a sentence whose published successor
#: leans on it, and V6 then held the whole site. W3 opens with a pronoun and leans on W2; W4 carries
#: one after its first comma and leans on W3; W5 stands alone; W7's "that it" leans on W6.
CHAIN = (
    "The Stone Temple is a megalithic temple on the island of Gozo. "
    "The temple was built c. 2500 BC by a farming community on a low ridge. "
    "It was enlarged in the Bronze Age with a second court and an altar. "
    "Standing on the ridge above the sea, it was later made into a small fort. "
    "Excavations in 1911 found pottery, figurines and animal bones in the courts. "
    "The settlement around it may have been founded when farmers came to the island. "
    "Pottery sherds show that it was also occupied in the Iron Age.\n"
)
CHAIN_SELECT = "".join(f"DESC: W{n}\n" for n in range(1, 8)) + "CARD: W5\n"


def _chain(tmp_path: Path, answer: str) -> tuple[Path, dict]:
    setup = X.SiteSetup(
        site=X.plan_site("site-1"), lane=M.Lane.W, sources={"W": (X.wiki_doc("W", CHAIN), CHAIN)}
    )
    batch_dir = X.make_batch(tmp_path, [setup])
    runner = X.ScriptedRunner({("site-1", "select"): CHAIN_SELECT})
    assert SEL.select_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir, ledger=tmp_path / "L.jsonl") == 0
    assert _review(batch_dir, answer)[0] == 0
    report = json.loads((batch_dir / B.REVIEW_REPORT).read_text(encoding="utf-8"))
    return batch_dir, report["sites"][0]


def _answer(*dropped: int) -> str:
    lines = [f"R{n}: DROP x" if n in dropped else f"R{n}: KEEP" for n in range(1, 8)]
    return "\n".join([*lines, "CARD: KEEP"])


def test_a_dropped_sentence_takes_the_pronouns_that_lean_on_it_along(tmp_path: Path) -> None:
    """The import drops a kept sentence that leans on the sentence before it (`sentences.
    leans_on_predecessor`, V6's rule) when that sentence is dropped - transitively, and recorded
    under its own reason - so the site is judged on what remains instead of held by V6."""
    batch_dir, row = _chain(tmp_path, _answer(2, 6))
    assert row["lines"][1] == "R2: DROP x"  # the reviewer's own lines stay as it wrote them
    assert row["kept"] == [1, 5]
    assert row["followed"] == [
        {"sentence": 3, "follows": 2, "reason": RV.FOLLOWS_A_DROP},
        {"sentence": 4, "follows": 3, "reason": RV.FOLLOWS_A_DROP},
        {"sentence": 7, "follows": 6, "reason": RV.FOLLOWS_A_DROP},
    ]
    (assembly,) = _written(batch_dir)
    assert len(assembly.provenance.sentences) == 2
    assert "It was enlarged" not in assembly.description
    assert "Pottery sherds" not in assembly.description


def test_a_pronoun_whose_predecessor_is_kept_stays(tmp_path: Path) -> None:
    _, row = _chain(tmp_path, _answer(5))
    assert row["kept"] == [1, 2, 3, 4, 6, 7] and row["followed"] == []


def test_the_followed_drops_can_leave_too_few_sentences(tmp_path: Path) -> None:
    """V9's floor and the two-sentence minimum still apply to what remains."""
    batch_dir, row = _chain(tmp_path, _answer(2, 5, 6))
    assert row["kept"] == [1] and row["outcome"] == "held"
    (hold,) = X.holds_of(batch_dir)
    assert hold.reason is M.HoldReason.REVIEW_TOO_FEW_SENTENCES


#: The mass run's mid-run audit (2026-09-25, T2: Roman Bath, York): the article's lead is about a
#: later pub that carries the Roman bath house's name, and the next sentence leans on it ("It is
#: built above ..."). W1 names the site; nothing after it does.
NAMESAKE = (
    "The Old Bath is a listed public house on the market square of Eburacum. "
    "It is built above the remains of a Roman bath house. "
    "The bath house served the soldiers of the legionary fortress in the second century. "
    "Roof tiles stamped with the names of two legions were found at the bath house site. "
    "The caldarium and part of the hypocaust can still be seen by visitors today.\n"
)


def test_a_later_namesake_building_is_dropped_with_the_sentence_that_leans_on_it(
    tmp_path: Path,
) -> None:
    """The reviewer's DROP of a sentence about a later building that shares the site's name goes
    through the import's own cascade (`follow_drops`): the pronoun sentence after it goes too, and
    the site is verified again on what is left - whose first sentence no longer names the site, so
    V6 holds it (measured on the real case: `logs/p4_mass/measure_roman_bath_cascade.log`)."""
    setup = X.SiteSetup(
        site=X.plan_site("site-1", name="Old Bath"),
        lane=M.Lane.W,
        sources={"W": (X.wiki_doc("W", NAMESAKE), NAMESAKE)},
    )
    batch_dir = X.make_batch(tmp_path, [setup])
    select = "".join(f"DESC: W{n}\n" for n in range(1, 6)) + "CARD: W4\n"
    runner = X.ScriptedRunner({("site-1", "select"): select})
    assert SEL.select_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir, ledger=tmp_path / "L.jsonl") == 0
    answer = (
        "R1: DROP its subject is the pub, a later building that shares the site's name\n"
        "R2: KEEP\nR3: KEEP\nR4: KEEP\nR5: KEEP\nCARD: KEEP"
    )
    v6 = M.Hold(site_id="site-1", scope=M.HoldScope.SITE, reason=M.HoldReason.V6, detail="d")
    code, _, verifier = _review(batch_dir, answer, Verifier([(v6,)]))
    assert code == 0
    report = json.loads((batch_dir / B.REVIEW_REPORT).read_text(encoding="utf-8"))
    row = report["sites"][0]
    assert row["kept"] == [3, 4, 5]
    assert row["followed"] == [{"sentence": 2, "follows": 1, "reason": RV.FOLLOWS_A_DROP}]
    (shown,) = verifier.seen
    assert shown.description.startswith("The bath house served the soldiers")
    assert "public house" not in shown.description and "It is built" not in shown.description
    assert row["outcome"] == "held" and _written(batch_dir) == []
    assert [hold.reason for hold in X.holds_of(batch_dir)] == [M.HoldReason.V6]


def test_a_dropped_card_sentence_rebuilds_the_card_from_the_rest(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    answer = "R1: KEEP\nR2: KEEP\nR3: DROP changed meaning\nR4: KEEP\nCARD: KEEP"
    assert _review(batch_dir, answer)[0] == 0
    (assembly,) = _written(batch_dir)
    assert assembly.card == W2_CARD and len(W2_CARD) >= RV.MIN_CARD_CHARS
    assert assembly.provenance.card is not None
    assert [item.sentence for item in assembly.provenance.card.items] == [1]
    report = json.loads((batch_dir / B.REVIEW_REPORT).read_text(encoding="utf-8"))
    assert report["sites"][0]["card"] == "rebuilt"
    assert X.holds_of(batch_dir) == []


def test_a_rebuilt_card_under_80_characters_is_held_and_the_description_goes_on(
    tmp_path: Path,
) -> None:
    batch_dir = _assembled(tmp_path, select=SELECT_SHORT)
    answer = "R1: KEEP\nR2: KEEP\nR3: DROP changed meaning\nR4: KEEP\nCARD: KEEP"
    assert _review(batch_dir, answer)[0] == 0
    (assembly,) = _written(batch_dir)
    assert assembly.card is None and assembly.provenance.card is None
    (hold,) = X.holds_of(batch_dir)
    assert (hold.scope, hold.reason) == (M.HoldScope.CARD, M.HoldReason.CARD_TOO_SHORT_AFTER_REVIEW)
    assert "under 80" in hold.detail


def test_card_drop_holds_the_card_only(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    answer = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\nCARD: DROP reads like an advert"
    assert _review(batch_dir, answer)[0] == 0
    (assembly,) = _written(batch_dir)
    assert assembly.card is None and len(assembly.provenance.sentences) == 4
    (hold,) = X.holds_of(batch_dir)
    assert hold.scope is M.HoldScope.CARD and "did not keep the card" in hold.detail


def test_fewer_than_two_sentences_left_holds_the_site(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    answer = "R1: KEEP\nR2: DROP x\nR3: DROP x\nR4: DROP x\nCARD: KEEP"
    code, _, verify = _review(batch_dir, answer)
    assert code == 0 and verify.seen == []
    assert _written(batch_dir) == []
    (hold,) = X.holds_of(batch_dir)
    assert hold.reason is M.HoldReason.REVIEW_TOO_FEW_SENTENCES and hold.scope is M.HoldScope.SITE


def test_an_unparseable_answer_holds_the_site(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    assert _review(batch_dir, "All four sentences look fine.")[0] == 0
    assert _written(batch_dir) == []
    assert X.holds_of(batch_dir)[0].reason is M.HoldReason.REVIEW_UNPARSEABLE


def test_a_site_hold_from_the_second_verification_keeps_the_site_out(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    v9 = M.Hold(site_id="site-1", scope=M.HoldScope.SITE, reason=M.HoldReason.V9, detail="short")
    assert _review(batch_dir, ALL_KEEP, Verifier([(v9,)]))[0] == 0
    assert _written(batch_dir) == []
    assert X.holds_of(batch_dir) == [v9]


def test_a_card_hold_from_the_second_verification_takes_the_card_off_and_verifies_again(
    tmp_path: Path,
) -> None:
    batch_dir = _assembled(tmp_path)
    v10 = M.Hold(site_id="site-1", scope=M.HoldScope.CARD, reason=M.HoldReason.V10, detail="len")
    code, _, verify = _review(batch_dir, ALL_KEEP, Verifier([(v10,), ()]))
    assert code == 0
    assert [a.card is None for a in verify.seen] == [False, True]
    (assembly,) = _written(batch_dir)
    assert assembly.card is None
    assert X.holds_of(batch_dir) == [v10]


def test_a_site_held_before_the_review_buys_no_review(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path, ("site-1", "site-2"))
    v3 = M.Hold(site_id="site-1", scope=M.HoldScope.SITE, reason=M.HoldReason.V3, detail="x")
    B.append_holds(batch_dir, [v3])
    runner = X.ScriptedRunner({("site-2", "review"): ALL_KEEP})
    code = RV.review_batch(
        batch_dir, ledger=tmp_path / "L.jsonl", runner=runner, reverify=Verifier()
    )
    assert code == 0 and [c.site_id for c in runner.calls] == ["site-2"]
    assert [a.site_id for a in _written(batch_dir)] == ["site-2"]


def test_a_resumed_review_buys_nothing_and_writes_the_same_file(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    answer = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: DROP x\nCARD: KEEP"
    _review(batch_dir, answer)
    ledger = batch_dir.parents[2] / "L.jsonl"
    before = (ledger.read_bytes(), (batch_dir / M.ASSEMBLY_FILE).read_bytes())
    code, runner, _ = _review(batch_dir, MS.ModelCallFailed("must not be asked"))
    assert code == 0 and runner.calls == []
    assert (ledger.read_bytes(), (batch_dir / M.ASSEMBLY_FILE).read_bytes()) == before


def test_a_review_that_could_not_be_made_leaves_the_assembly_unreviewed(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    before = (batch_dir / M.ASSEMBLY_FILE).read_bytes()
    code, _, _ = _review(batch_dir, MS.ModelCallFailed("'pi.cmd' could not be started"))
    assert code == 2
    assert (batch_dir / M.ASSEMBLY_FILE).read_bytes() == before
    report = json.loads((batch_dir / B.REVIEW_REPORT).read_text(encoding="utf-8"))
    assert "could not be started" in report["error"] and "assembly_sha256" not in report


def test_an_unreadable_review_stream_holds_the_site(tmp_path: Path) -> None:
    batch_dir = _assembled(tmp_path)
    assert _review(batch_dir, MS.UnreadableStream("no usage"))[0] == 0
    assert X.holds_of(batch_dir)[0].reason is M.HoldReason.MODEL_STREAM_UNREADABLE


# ------------------------------------------------------------------------------ the disclosure (X10)
class _Stamped(X.ScriptedRunner):
    """`ScriptedRunner` answering as another model: its stamp goes into the ledger line."""

    def __init__(self, script, model: str) -> None:
        super().__init__(script)
        self.model = model

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        answer = super().run(call)
        return MS.ModelAnswer(text=answer.text, usage=answer.usage, model=self.model)


def test_the_disclosure_names_the_models_whose_answers_the_text_rests_on(tmp_path: Path) -> None:
    """Orchestrator item X10 (2026-10-24): S4 stamped the Claude-and-MiniMax `model4.AI_SYSTEM` on
    every new Phase-4 provenance. The disclosure is now `model4.ai_system_for` over the stamps of
    the site's calls in the run's ledger: the selector's at S4, the selector's and the reviewer's
    after S6 - and the string itself is `ai_system_for`'s (owner decision D56 makes it exact)."""
    batch_dir = X.make_batch(tmp_path, [X.w_site("site-1")])
    ledger = tmp_path / "L.jsonl"
    selector = _Stamped({("site-1", "select"): SELECT}, X.MS.OH.SONNET_MODEL)
    assert SEL.select_batch(batch_dir, ledger=ledger, runner=selector) == 0
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir, ledger=ledger) == 0
    (assembly,) = M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly)
    assert assembly.provenance.ai_system == M.ai_system_for([X.MS.OH.SONNET_MODEL])
    # a reviewer of another model joins the disclosure (Haiku: a set every version of
    # ai_system_for names apart from Sonnet alone)
    reviewer = _Stamped({("site-1", "review"): ALL_KEEP}, X.MS.OH.HAIKU_MODEL)
    assert RV.review_batch(batch_dir, ledger=ledger, runner=reviewer, reverify=Verifier()) == 0
    (reviewed,) = _written(batch_dir)
    both = M.ai_system_for([X.MS.OH.SONNET_MODEL, X.MS.OH.HAIKU_MODEL])
    assert reviewed.provenance.ai_system == both != assembly.provenance.ai_system
    assert "MiniMax" not in reviewed.provenance.ai_system


def test_a_site_whose_calls_the_ledger_does_not_hold_has_no_disclosure(tmp_path: Path) -> None:
    """No stamp, no disclosure: a site whose calls are not in the ledger it is assembled with, a
    ledger that is missing, and a stamp no handoff answer carries are refused, never guessed."""
    batch_dir = _assembled(tmp_path)
    with pytest.raises(A.InputError, match="no answering model"):
        A.assemble_batch(batch_dir, ledger=_empty_ledger(tmp_path))
    with pytest.raises(A.InputError, match="no ledger"):
        A.assemble_batch(batch_dir, ledger=tmp_path / "missing.jsonl")
    rows = [
        {"kind": "model_call", "batch_id": "p4-0001", "label": "site-1/select", "model": "x/y"},
    ]
    with pytest.raises(A.InputError, match="no stamp of opus_handoff.ANSWER_MODELS"):
        A.site_ai_system(rows, batch_id="p4-0001", site_id="site-1")


def test_the_stamps_are_the_sites_own_calls_in_its_own_batch() -> None:
    rows = [
        {"kind": "model_call", "batch_id": "p4-0001", "label": "site-1/select", "model": "a"},
        {"kind": "model_call", "batch_id": "p4-0001", "label": "site-1/review", "model": "b"},
        {"kind": "model_call", "batch_id": "p4-0002", "label": "site-1/select", "model": "c"},
        {"kind": "model_call", "batch_id": "p4-0001", "label": "site-10/select", "model": "d"},
        {"kind": "fetch", "batch_id": "p4-0001", "label": "site-1/W", "model": None},
    ]
    assert A.answer_stamps(rows, batch_id="p4-0001", site_id="site-1") == {"a", "b"}
    minimax = [{**rows[0], "model": X.MS.OH.MINIMAX_MODEL}]
    assert A.site_ai_system(minimax, batch_id="p4-0001", site_id="site-1") == M.AI_SYSTEM


def test_a_re_asked_call_discloses_only_the_model_whose_answer_is_stored() -> None:
    """The review of 2026-10-24 (D56, exact): deleting a stored answer is how a human asks again
    (`model_stage.judge_site`), and the new call adds a second ledger line for the label. A selector
    answered first by a MiniMax agent and asked again under D6 by Sonnet rests on Sonnet alone."""
    first = {"kind": "model_call", "batch_id": "p4-0001", "label": "site-1/select"}
    rows = [
        {**first, "model": X.MS.OH.MINIMAX_MODEL},
        {**first, "label": "site-1/review", "model": X.MS.OH.OPUS_MODEL},
        {**first, "model": X.MS.OH.SONNET_MODEL},
    ]
    assert A.answer_stamps(rows, batch_id="p4-0001", site_id="site-1") == {
        X.MS.OH.SONNET_MODEL,
        X.MS.OH.OPUS_MODEL,
    }
    assert A.site_ai_system(rows, batch_id="p4-0001", site_id="site-1") == M.AI_SYSTEM_CLAUDE
    asked_back = [*rows, {**first, "model": X.MS.OH.MINIMAX_MODEL}]
    assert A.site_ai_system(asked_back, batch_id="p4-0001", site_id="site-1") == M.AI_SYSTEM


def test_the_review_reads_the_run_ledger_once_per_batch(tmp_path: Path, monkeypatch) -> None:
    """S6 reads the ledger once and adds each bought review call to the rows it read, so the
    disclosure after the review names the reviewer without re-parsing the file per site."""
    batch_dir = X.make_batch(tmp_path, [X.w_site("site-1"), X.w_site("site-2")])
    ledger = tmp_path / "L.jsonl"
    script = {("site-1", "select"): SELECT, ("site-2", "select"): SELECT}
    selector = _Stamped(script, X.MS.OH.SONNET_MODEL)
    assert SEL.select_batch(batch_dir, ledger=ledger, runner=selector) == 0
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir, ledger=ledger) == 0
    reads: list[Path] = []
    real = A.read_ledger
    monkeypatch.setattr(A, "read_ledger", lambda path: reads.append(path) or real(path))
    review = {("site-1", "review"): ALL_KEEP, ("site-2", "review"): ALL_KEEP}
    reviewer = _Stamped(review, X.MS.OH.HAIKU_MODEL)
    assert RV.review_batch(batch_dir, ledger=ledger, runner=reviewer, reverify=Verifier()) == 0
    assert reads == [ledger]
    both = M.ai_system_for([X.MS.OH.SONNET_MODEL, X.MS.OH.HAIKU_MODEL])
    assert {a.provenance.ai_system for a in _written(batch_dir)} == {both}


def _empty_ledger(tmp_path: Path) -> Path:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    return path
