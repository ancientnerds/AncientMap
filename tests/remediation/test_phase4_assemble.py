"""Does S4 build every byte by the closed edit list, number citations itself, and record exactly
the provenance production_write names?

Work item WB-B3 (`phase4/assemble.py`). The expected strings below are written out by hand from the
design's edit list (writer, ASSEMBLY), not computed with the module under test, so a change to the
assembler cannot move the expectation with it. Every assembly is also read back through `model4`,
which refuses a malformed record. Nothing here opens a socket or calls a model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PHASE_PARENT = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(PHASE_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE_PARENT))

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402
from phase4 import sentences as S  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402


def _pool(text: str = X.ARTICLE, lane: M.Lane = M.Lane.W) -> tuple[M.Sentence, ...]:
    return S.candidate_pool(S.split_source("W", text), lane=lane, names=["Stone Temple"], text=text)


def _built(answer: str, *, text: str = X.ARTICLE, lane: M.Lane = M.Lane.W) -> A.Built:
    pool = _pool(text, lane)
    selection = SEL.parse_selection("site-1", answer, pool)
    return A.build_picks(
        X.plan_site(),
        selection.desc,
        selection.card,
        pool,
        lane,
        {"W": X.wiki_doc("W", text)},
        {"W": text},
        run="pilot",
    )


def _span(text: str, sid: str, span_id: str) -> tuple[int, int]:
    sentence = {s.sid: s for s in S.split_source("W", text)}[sid]
    span = {s.id: s for s in sentence.spans}[span_id]
    return span.start, span.end


# ------------------------------------------------------------------------------ the edit list


def test_edit_1_removes_exactly_the_range() -> None:
    text = "A second shrine (the south shrine) was added later."
    assert A.trim(text, 0, len(text), [(15, 34)]) == "A second shrine was added later."


def test_edits_2_and_3_collapse_spaces_and_repair_a_space_before_a_comma() -> None:
    text = "The shrine (south) , now ruined,  stands  here."
    assert A.trim(text, 0, len(text), [(11, 18)]) == "The shrine, now ruined, stands here."


def test_edit_4_restores_the_capital_after_a_dropped_leading_span() -> None:
    text = "In 1900, the site was cleared."
    assert A.trim(text, 0, len(text), [(0, 9)]) == "The site was cleared."
    assert A.trim(text, 0, len(text), []) == text  # no leading drop, no change of case


def test_edit_5_puts_the_marker_before_the_final_punctuation() -> None:
    assert A.with_marker("The temple is old.", 1) == "The temple is old [1]."
    assert A.with_marker("Was it a temple?", 2) == "Was it a temple [2]?"
    with pytest.raises(ValueError, match="no final punctuation"):
        A.with_marker("The temple is old", 1)


def test_a_drop_outside_its_sentence_is_refused() -> None:
    with pytest.raises(ValueError, match="not inside"):
        A.trim("abcdef", 1, 4, [(3, 6)])


def test_the_spoken_edit_reads_circa_and_nothing_else() -> None:
    assert A.spoken("Built c. 2500 BC and ca.300 AD.") == "Built circa 2500 BC and circa 300 AD."
    assert A.spoken("Tools, pots etc. 5 of them.") == "Tools, pots etc. 5 of them."


@pytest.mark.parametrize(
    ("card", "spoken"),
    [
        # {{circa}} renders c. + U+2009 (thin space), the extracts' most common form
        ("Babylon grew c.\u20091770 BC.", "Babylon grew circa 1770 BC."),
        ("It was settled c.\u00a012,500 years ago.", "It was settled circa 12,500 years ago."),
        ("It was built c. AD 79 on the shore.", "It was built circa AD 79 on the shore."),
        ("It was built ca.\u2009BC 500 on the hill.", "It was built circa BC 500 on the hill."),
        ("C. 1200 BC the city was burnt.", "Circa 1200 BC the city was burnt."),
        # `c.` meaning century, and an initial, stay as written
        ("It dates to the 5th c. BCE and later.", "It dates to the 5th c. BCE and later."),
        ("It was dug by B.c. 1990 surveyors.", "It was dug by B.c. 1990 surveyors."),
    ],
)
def test_the_spoken_edit_reads_every_circa_form_and_no_century(card: str, spoken: str) -> None:
    assert A.spoken(card) == spoken


def test_nested_ranges_collapse_to_the_outer_one_and_overlaps_raise() -> None:
    assert A.maximal([(5, 9), (0, 20), (22, 25)]) == ((0, 20), (22, 25))
    assert A.maximal([(0, 5), (5, 9)]) == ((0, 5), (5, 9))
    with pytest.raises(ValueError, match="overlaps"):
        A.maximal([(0, 6), (5, 9)])


# ----------------------------------------------------------------------------- lanes W and S


GOOD = "DESC: W6 -p1\nDESC: W1\nDESC: W2 -t1\nCARD: W2\n"
EXPECTED = (
    "The Stone Temple is a megalithic temple on the island of Gozo [1]. "
    "The temple was built c. 2500 BC by a farming community [1]. "
    "A second shrine was added later [1]."
)


def test_the_description_is_the_edited_sentences_in_source_order() -> None:
    built = _built(GOOD)
    assert built.assembly.description == EXPECTED
    assert " ".join(built.sentences) == EXPECTED


def test_the_citation_is_the_existing_shape_with_the_permalink() -> None:
    (citation,) = _built(GOOD).assembly.citations
    assert citation.to_dict() == {
        "n": 1,
        "url": X.PERMALINK,
        "title": "Wikipedia: Stone Temple",
        "domain": "en.wikipedia.org",
        "license": "CC BY-SA 4.0",
    }


def test_the_provenance_pins_ranges_drops_hashes_and_the_disclosure() -> None:
    assembly = _built(GOOD).assembly
    provenance = assembly.provenance.to_dict()
    starts = {s.sid: (s.start, s.end) for s in S.split_source("W", X.ARTICLE)}
    t1 = _span(X.ARTICLE, "W2", "t1")
    p1 = _span(X.ARTICLE, "W6", "p1")
    assert provenance["sentences"] == [
        {"n": 1, "src": "W", "start": starts["W1"][0], "end": starts["W1"][1], "drop": []},
        {"n": 1, "src": "W", "start": starts["W2"][0], "end": starts["W2"][1], "drop": [list(t1)]},
        {"n": 1, "src": "W", "start": starts["W6"][0], "end": starts["W6"][1], "drop": [list(p1)]},
    ]
    assert provenance["lane"] == "W" and provenance["ai"] == "selected"
    assert provenance["ai_system"] == M.AI_SYSTEM and provenance["run"] == "pilot"
    assert provenance["attribution"] == {
        "title": "Stone Temple",
        "url": X.PERMALINK,
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "changes": "sentences selected and shortened",
    }
    assert provenance["sources"] == [
        {
            "id": "W",
            "url": X.PERMALINK,
            "revid": 1234567,
            "rev_timestamp": "2026-09-01T10:00:00Z",
            "text_sha256": M.text_sha256(X.ARTICLE),
            "licence": "CC BY-SA 4.0",
        }
    ]
    assert provenance["desc_sha256"] == M.text_sha256(EXPECTED)
    assert M.Assembly.from_json(assembly.to_json()) == assembly


def test_the_card_is_its_desc_sentence_with_the_spoken_edit_and_no_marker() -> None:
    assembly = _built(GOOD).assembly
    card = "The temple was built circa 2500 BC by a farming community."
    assert assembly.card == card
    t1 = _span(X.ARTICLE, "W2", "t1")
    assert assembly.provenance.card is not None
    assert assembly.provenance.card.to_dict() == {
        "items": [{"sentence": 1, "drop": [list(t1)]}],
        "text_sha256": M.text_sha256(card),
    }


def test_a_card_drop_on_top_of_the_desc_drop_is_recorded_as_the_maximal_union() -> None:
    text = "The shrine was added later, near the (old) north gate, on the ridge of the hill."
    built = _built("DESC: W1 -p1\nCARD: W1 -a1", text=text)
    a1 = _span(text, "W1", "a1")
    assert built.assembly.description == (
        "The shrine was added later, near the north gate, on the ridge of the hill [1]."
    )
    assert built.assembly.card == "The shrine was added later on the ridge of the hill."
    assert built.assembly.provenance.card is not None
    assert built.assembly.provenance.card.items[0].drop == (a1,)


def test_a_dropped_leading_phrase_gives_a_capital() -> None:
    built = _built("DESC: W3 -l1\nDESC: W1\nCARD: W1")
    assert built.sentences[1] == "The site was cleared of rubble by the island's governor [1]."


def test_every_published_sentence_is_its_slice_with_the_edits(tmp_path: Path) -> None:
    """The invariant V3 re-derives, checked here against the design's own formula."""
    assembly = _built(GOOD).assembly
    for published, cut in zip(
        A.published_sentences(assembly), assembly.provenance.sentences, strict=True
    ):
        body = A.trim(X.ARTICLE, cut.start, cut.end, cut.drop)
        assert published == body[:-1] + f" [{cut.n}]" + body[-1]


def test_lane_s_is_selected_text_with_the_same_change_note() -> None:
    provenance = _built("DESC: W1\nCARD: W1", lane=M.Lane.S).assembly.provenance
    assert (provenance.lane, provenance.ai) == (M.Lane.S, M.AiMark.SELECTED)
    assert provenance.attribution.changes is M.Changes.SELECTED_AND_SHORTENED


def test_no_card_pick_means_no_card() -> None:
    pool = _pool()
    selection = SEL.parse_selection("s", GOOD, pool)
    built = A.build_picks(
        X.plan_site(), selection.desc, (), pool, M.Lane.W,
        {"W": X.wiki_doc("W", X.ARTICLE)}, {"W": X.ARTICLE}, run="pilot",
    )  # fmt: skip
    assert built.assembly.card is None and built.assembly.provenance.card is None


def test_an_abstaining_selection_is_never_assembled() -> None:
    selection = M.Selection(site_id="s", desc=(), card=(), abstain="about the town")
    with pytest.raises(ValueError, match="abstaining"):
        A.assemble(X.plan_site(), selection, _pool(), M.Lane.W, {}, {}, run="pilot")


# -------------------------------------------------------------------------------- lanes T, R

FR_TEXT = (
    "Le temple fut construit vers 2500 av. J.-C. par des paysans. "
    "Il fut fouillé par des archéologues en 1911."
)


def test_lane_t_publishes_the_translation_with_its_marker_and_no_card() -> None:
    pool = S.candidate_pool(
        S.split_source("T.fr", FR_TEXT), lane=M.Lane.T, names=["X"], text=FR_TEXT
    )
    selection = SEL.parse_selection("s", "DESC: T.fr1\nDESC: T.fr2\nCARD: T.fr1", pool)
    doc = X.wiki_doc("T.fr", FR_TEXT, title="Temple de pierre", host="fr.wikipedia.org")
    built = A.build_picks(
        X.plan_site(), selection.desc, selection.card, pool, M.Lane.T,
        {"T.fr": doc}, {"T.fr": FR_TEXT}, run="pilot",
        translations={"T.fr1": "The temple was built around 2500 BC by farmers.",
                      "T.fr2": "It was excavated by archaeologists in 1911."},
    )  # fmt: skip
    assembly = built.assembly
    assert assembly.description == (
        "The temple was built around 2500 BC by farmers [1]. "
        "It was excavated by archaeologists in 1911 [1]."
    )
    assert assembly.card is None
    assert (assembly.provenance.ai, assembly.provenance.attribution.changes) == (
        M.AiMark.GENERATED,
        M.Changes.TRANSLATED,
    )
    assert assembly.citations[0].domain == "fr.wikipedia.org"
    assert assembly.citations[0].title == "Wikipedia: Temple de pierre"


def test_translations_belong_to_lane_t_only() -> None:
    pool = _pool()
    selection = SEL.parse_selection("s", GOOD, pool)
    with pytest.raises(ValueError, match="for lane T and only for it"):
        A.build_picks(
            X.plan_site(), selection.desc, selection.card, pool, M.Lane.W,
            {"W": X.wiki_doc("W", X.ARTICLE)}, {"W": X.ARTICLE}, run="p", translations={},
        )  # fmt: skip


PAGE_ONE = "Intro text. The mound was raised in the Bronze Age by farmers. More text here."
PAGE_TWO = "The mound has a ditch around it and a stone circle on top of it."


def test_lane_r_numbers_pages_by_first_appearance_and_keeps_each_page_in_order() -> None:
    one = X.page_doc("R1", PAGE_ONE, url="https://www.example.org/mound", title="The Mound")
    two = X.page_doc("R2", PAGE_TWO, url="https://example.net/ditch", title="Ditch notes")
    restated = [
        B.Restatement(text="A ditch surrounds the mound.", src="R2", start=0, end=36),
        B.Restatement(text="Farmers built it in the Bronze Age.", src="R1", start=12, end=62),
        B.Restatement(text="It carries a stone circle.", src="R2", start=37, end=64),
    ]
    assembly = A.build_restated(X.plan_site(), restated, {"R1": one, "R2": two}, run="p").assembly
    assert assembly.description == (
        "A ditch surrounds the mound [1]. It carries a stone circle [1]. "
        "Farmers built it in the Bronze Age [2]."
    )
    assert [(c.n, c.title, c.domain, c.license) for c in assembly.citations] == [
        (1, "Ditch notes", "example.net", M.Licence.RESTRICTED),
        (2, "The Mound", "example.org", M.Licence.RESTRICTED),
    ]
    assert assembly.provenance.attribution.url == "https://example.net/ditch"
    assert assembly.provenance.attribution.changes is M.Changes.FACTS_RESTATED
    assert assembly.card is None
    assert A.quotes_of(assembly, {"R1": PAGE_ONE, "R2": PAGE_TWO}) == (
        PAGE_TWO[0:36],
        PAGE_TWO[37:64],
        PAGE_ONE[12:62],
    )
    assert M.Assembly.from_json(assembly.to_json()) == assembly


def test_the_description_cuts_back_into_its_sentences_or_raises() -> None:
    assembly = _built(GOOD).assembly
    assert A.published_sentences(assembly) == _built(GOOD).sentences
    tampered = M.Assembly.from_dict({**assembly.to_dict(), "description": EXPECTED + " Extra [1]."})
    with pytest.raises(ValueError, match="does not cut"):
        A.published_sentences(tampered)


# ------------------------------------------------------------------------------- the batch


def _selected(tmp_path: Path, setups: list[X.SiteSetup], answers: dict[str, str]) -> Path:
    batch_dir = X.make_batch(tmp_path, setups)
    runner = X.ScriptedRunner({(site, "select"): answer for site, answer in answers.items()})
    assert SEL.select_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    return batch_dir


def test_assemble_batch_writes_one_assembly_per_site_that_reached_a_text(tmp_path: Path) -> None:
    batch_dir = _selected(
        tmp_path,
        [X.w_site("site-1"), X.w_site("site-2")],
        {"site-1": GOOD, "site-2": "ABSTAIN: about the town"},
    )
    assert A.assemble_batch(batch_dir) == 0
    rows = M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly)
    assert [row.site_id for row in rows] == ["site-1"]
    assert rows[0].description == EXPECTED
    assert rows[0].provenance.run == "pilot"  # runs/<run>/<batch>


def test_a_site_with_neither_a_selection_nor_a_hold_stops_the_batch(tmp_path: Path) -> None:
    batch_dir = _selected(tmp_path, [X.w_site("site-1")], {"site-1": GOOD})
    (batch_dir / B.SELECTIONS_FILE).write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="neither a selection nor a hold"):
        A.assemble_batch(batch_dir)


def test_a_stage_file_that_was_never_written_is_an_error(tmp_path: Path) -> None:
    batch_dir = _selected(tmp_path, [X.w_site("site-1")], {"site-1": GOOD})
    (batch_dir / B.TRANSLATIONS_FILE).unlink()
    with pytest.raises(FileNotFoundError):
        A.assemble_batch(batch_dir)


def test_the_assembly_file_is_the_model4_jsonl(tmp_path: Path) -> None:
    batch_dir = _selected(tmp_path, [X.w_site("site-1")], {"site-1": GOOD})
    A.assemble_batch(batch_dir)
    line = (batch_dir / M.ASSEMBLY_FILE).read_text(encoding="utf-8")
    assert line == M.dump_jsonl(M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly))
    assert json.loads(line)["citations"][0]["license"] == "CC BY-SA 4.0"
