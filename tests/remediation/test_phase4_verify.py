"""Does the Phase-4 verifier (WB-C2) hold every site that breaks one of V1-V15, and only those?

`scripts/remediation/phase4/verify4.py` is the last deterministic line before a description is
written: it must pass a site whose every byte re-derives from its pinned source, and hold - under
the rule's own id - a site that breaks one property. The cases here build one clean site per lane
(W, T and R) and break exactly one thing each: a text, a hash, a marker, a span, a card word. They
break the *world*, not the record shape `model4` already refuses (PHASE4_CONTRACTS.md section 2).

The expected published strings are written out by hand below, never computed with the module's own
edit list, so a wrong edit list cannot move the expectation with it. Nothing here opens a socket,
reads the gitignored fonts, calls a model or touches a database: the card's font measurement goes
through a fake that measures with a real FreeType face (Pillow's own) and refuses the glyphs a
Latin font lacks, and the real brand fonts are tried only where they already are on disk.

The mutation cases are `p4 verify4: ...` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3.run import Batch  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import verify4 as V  # noqa: E402

from pipeline.video import shorts_audit, shorts_brand  # noqa: E402
from tests.remediation.phase4_cases import (  # noqa: E402
    A1,
    CARD,
    EN1,
    EN2,
    HELD_SITE,
    L4,
    P2,
    PERMALINK,
    PUB2,
    R1,
    S1,
    S2,
    S3,
    S4,
    S5,
    SITE_ID,
    STORED,
    T2,
    T4,
    TEXT,
    W_PICKS,
    Case,
    Pick,
    fake_card_fit,
    gate,
    licences_stand_in,
    locate,
    make_case,
    make_generated_case,
    other_track,
    piece_range,
    plan_site,
    reprovenance,
    republish,
    sha,
    with_marker,
    write4_stand_in,
    write_batch,
)

VERIFY4 = PHASE4_PARENT / "phase4" / "verify4.py"

#: The one test that measures with the real brand fonts, where they are on disk.
REAL_FONTS_TEST = "test_v10_measures_through_the_shorts_own_helpers_with_the_brand_fonts"


@pytest.fixture(autouse=True)
def _card_fit_without_brand_fonts(request: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name != REAL_FONTS_TEST:
        monkeypatch.setattr(V, "card_fit", fake_card_fit)


@pytest.fixture
def licences(monkeypatch: pytest.MonkeyPatch) -> None:
    other_track(monkeypatch, "licences", licences_stand_in())


@pytest.fixture
def write4(monkeypatch: pytest.MonkeyPatch) -> None:
    other_track(monkeypatch, "write4", write4_stand_in())


# ------------------------------------------------------------------------------------------------
# Independence
# ------------------------------------------------------------------------------------------------


def test_the_verifier_never_imports_the_assembler() -> None:
    """WB-C2: an AST scan of every import, at any depth, including a dynamic one."""
    tree = ast.parse(VERIFY4.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            assert name not in {"import_module", "__import__"}, "a dynamic import in verify4"
    assert imported, "the scan found no import at all - it is not scanning the module"
    assert not [name for name in imported if name.split(".")[-1] == "assemble"], imported


def test_the_ast_scan_would_see_an_import_of_the_assembler() -> None:
    """The scan above is not vacuous: the same walk finds each spelling of the import."""
    for source in (
        "from phase4 import assemble",
        "from phase4.assemble import assemble",
        "import phase4.assemble as A",
        "def f():\n    from phase4 import assemble\n",
    ):
        names = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
                names.extend(f"{node.module}.{alias.name}" for alias in node.names)
        assert [n for n in names if n.split(".")[-1] == "assemble"], source


# ------------------------------------------------------------------------------------------------
# The span finder and the edit list (the verifier's own reading)
# ------------------------------------------------------------------------------------------------


def _offered(sentence: str) -> list[str]:
    return [sentence[a:b] for a, b in V.offered_spans(sentence, 0, len(sentence))]


def test_the_designs_own_example_is_offered_with_its_delimiter() -> None:
    """writer, User block: `a1=", whose tomb lies nearby"`; `c.` keeps the date out of reach."""
    sentence = "The temple was built c. 2500 BC by Khufu, whose tomb lies nearby."
    assert _offered(sentence) == [", whose tomb lies nearby"]


def test_every_span_kind_is_offered_as_the_range_it_removes() -> None:
    assert _offered(S1) == [A1, ", near the village of Tarxien"]
    assert _offered(S2) == [P2, T2]
    assert _offered(S4) == [L4]  # T4 carries 'part of'
    dashed = "The fort – built by the Romans – was abandoned in the 5th century."
    assert _offered(dashed) == [" – built by the Romans –"]


def test_a_span_with_a_protected_token_is_never_offered() -> None:
    sentence = (
        "The wall, which was not finished, stands (possibly) on older footings, suggesting reuse."
    )
    assert _offered(sentence) == ["The wall, "]  # the one span without a protected token
    assert V.protected_in(", which was not finished,") == ("not",)
    assert V.protected_in(", suggesting reuse") == ("suggest*",)
    assert V.protected_in("part  of the") == ("part of",)
    assert V.protected_in("dated c. 2500 BC") == ("c.",)
    assert V.protected_in("the etc. list") == ()


def test_a_number_comma_and_a_bracketed_comma_are_no_delimiters() -> None:
    sentence = "The hoard of 2,500 coins (found in 1920, near the gate) lies in the museum store."
    assert _offered(sentence) == [" (found in 1920, near the gate)"]


def test_an_unspaced_dash_pair_is_not_offered() -> None:
    assert _offered("The fort—built by the Romans—was abandoned in the 5th century AD.") == []


def test_a_leading_phrase_is_at_most_six_tokens() -> None:
    seven = "In the very late summer of 1920, the site was excavated by a team."
    assert "In the very late summer of 1920, " not in _offered(seven)
    six = "In the late summer of 1920, the site was excavated by a team."
    assert "In the late summer of 1920, " in _offered(six)


def test_the_edit_list_removes_repairs_restores_and_marks() -> None:
    start, end = locate(TEXT, S4)
    low, high = piece_range(TEXT, S4, L4)
    assert V.edited(TEXT, start, end, [(low, high)]).startswith("The temples were declared")
    text = "The pit (x) , a hearth  and a wall (y) were found."
    assert (
        V.edited(text, 0, len(text), [(8, 11), (35, 39)])
        == "The pit, a hearth and a wall were found."
    )
    assert V.marked("He called it the old fort.", 2) == "He called it the old fort [2]."
    assert V.marked('It is called "the fort."', 1) == 'It is called "the fort [1]."'
    assert V.marked("No final stop", 1) is None


def test_the_card_speaks_circa_and_nothing_else() -> None:
    assert V.spoken("Built c. 2500 BC and ca.300 AD, etc. in B.C. times.") == (
        "Built circa 2500 BC and circa 300 AD, etc. in B.C. times."
    )
    assert V.spoken("C. 2500 BC it was built.") == "Circa 2500 BC it was built."


# ------------------------------------------------------------------------------------------------
# The clean sites
# ------------------------------------------------------------------------------------------------


def test_a_clean_lane_w_site_passes_every_rule() -> None:
    case = make_case()
    assert len(V.without_markers(case.assembly.description)) >= V.DESCRIPTION_MIN
    assert V.CARD_MIN <= len(CARD) <= V.CARD_MAX
    assert case.run() == ()


def test_a_clean_lane_t_site_passes_every_rule() -> None:
    assert make_generated_case("T").run() == ()


def test_a_clean_lane_r_site_passes_every_rule(licences: None) -> None:
    assert make_generated_case("R").run() == ()


def test_a_hold_names_its_rule_its_site_and_what_broke() -> None:
    case = make_case()
    broken = dataclasses.replace(case, texts={"W": TEXT.replace("Tarxien.", "Tarxien!")})
    holds = broken.run()
    assert {h.site_id for h in holds} == {SITE_ID}
    assert all(h.detail for h in holds)
    assert "V1" in {h.reason.value for h in holds}


def test_an_assembly_of_another_site_is_refused() -> None:
    case = make_case()
    other = dataclasses.replace(case.assembly, site_id="another-site")
    with pytest.raises(ValueError, match="is not the site"):
        V.verify_site(
            case.site,
            other,
            metas=case.metas,
            texts=case.texts,
            quotes=case.quotes,
            new_raw_data={},
        )


# ------------------------------------------------------------------------------------------------
# V1 pin
# ------------------------------------------------------------------------------------------------


def test_v1_a_text_that_is_not_the_pinned_one_is_held() -> None:
    case = make_case()
    case.metas["W"]["sha256_text"] = sha(TEXT + " ")
    assert "V1" in case.reasons()
    assert "the stored text hashes to" in case.detail("V1")


def test_v1_a_revision_that_is_not_an_integer_is_held() -> None:
    """Read from the raw meta: `model4.SourceDoc` would refuse a bool first (contract section 2)."""
    case = make_case()
    case.metas["W"]["revid"] = True
    case.metas["W"]["lastrevid"] = True
    assert "is not an integer" in case.detail("V1")


def test_v1_a_revision_that_moved_is_held() -> None:
    case = make_case()
    case.metas["W"]["lastrevid"] = 1234568
    assert "is not lastrevid" in case.detail("V1")


def test_v1_a_url_that_is_not_an_oldid_permalink_is_held() -> None:
    assert V.is_permalink(PERMALINK, lang="en", revid=1234567)
    for url in (
        "https://en.wikipedia.org/wiki/Tarxien_Temples",
        "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234568",
        "https://fr.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567",
        "http://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567",
        "https://en.wikipedia.org/w/index.php?title=&oldid=1234567",
        "https://en.wikipedia.org/w/index.php?title=X&oldid=1234567&action=raw",
    ):
        assert not V.is_permalink(url, lang="en", revid=1234567), url
    case = make_case()
    case.metas["W"]["permalink"] = "https://en.wikipedia.org/wiki/Tarxien_Temples"
    assert "is not the oldid permalink" in case.detail("V1")


def test_v1_lanes_w_s_and_t_publish_only_from_cc_by_sa_wikipedia() -> None:
    case = make_case()
    case.metas["W"]["licence"] = "CC BY 4.0"
    assert "publish from CC BY-SA 4.0 Wikipedia only" in case.detail("V1")


def test_v1_a_lane_that_cites_a_source_of_another_kind_is_held(licences: None) -> None:
    case = make_generated_case("R")
    provenance = case.assembly.provenance
    provenance = dataclasses.replace(
        provenance,
        lane=M.Lane.T,
        attribution=dataclasses.replace(provenance.attribution, changes=M.Changes.TRANSLATED),
    )
    assert "publishes from" in case.replace(provenance=provenance).detail("V1")


def test_v1_a_restricted_page_on_the_deny_list_is_held(licences: None) -> None:
    case = make_generated_case("R")
    denied = "https://grokipedia.com/page/Tarxien_Temples"
    case.metas["R1"]["url"] = denied
    assert "is on the deny list" in case.detail("V1")


def test_v1_the_attribution_names_the_article_it_links() -> None:
    case = make_case()
    attribution = dataclasses.replace(case.assembly.provenance.attribution, title="Ħal Tarxien")
    assert "attribution names" in reprovenance(case, attribution=attribution).detail("V1")


# ------------------------------------------------------------------------------------------------
# V2 quote, V3 assembly, V4 drop legality
# ------------------------------------------------------------------------------------------------


def test_v2_a_quote_that_is_not_the_source_slice_is_held() -> None:
    case = make_case()
    case.quotes[1] = case.quotes[1].replace("1915", "1916")
    assert "is not the quote" in case.detail("V2")


def test_v2_a_quote_that_does_not_occur_in_the_text_is_held() -> None:
    """The text carries a decomposed 'é' (NFD): the NFC slice equals the quote, the page does not
    carry it, and only `discover_stage.quote_occurs` notices."""
    sentence = "The Café Tarxien tomb was opened in 1915 by Themistocles Zammit and his team."
    text = unicodedata.normalize("NFD", sentence) + " " + S3
    nfd_sentence = unicodedata.normalize("NFD", sentence)
    case = make_case(
        text=text,
        picks=(Pick(nfd_sentence, (), nfd_sentence), Pick(S3, (), S3)),
        card=None,
    )
    case.quotes[0] = unicodedata.normalize("NFC", case.quotes[0])
    assert "does not occur" in case.detail("V2")


def test_v2_every_published_sentence_needs_its_quote() -> None:
    case = make_case()
    case.quotes.pop()
    assert "2 quote(s) for 3 published sentence(s)" in case.detail("V2")


def test_v3_a_published_sentence_the_edit_list_does_not_rebuild_is_held() -> None:
    case = make_case()
    changed = case.assembly.description.replace("four megalithic", "five megalithic")
    assert "rebuilt" in republish(case, changed).detail("V3")


def test_v3_a_description_that_does_not_split_into_its_sentences_is_held() -> None:
    case = make_case()
    glued = case.assembly.description.replace(" [1]. The site", ". The site", 1)
    held = republish(case, glued)
    assert "marker-terminated sentence(s)" in held.detail("V3")
    assert "V8" in held.reasons()


def test_v3_lane_r_drops_nothing_from_a_quote(licences: None) -> None:
    case = make_generated_case("R")
    first = case.assembly.provenance.sentences[0]
    cut = dataclasses.replace(first, drop=((first.start + 3, first.start + 11),))
    sentences = (cut, *case.assembly.provenance.sentences[1:])
    assert "drops nothing" in reprovenance(case, sentences=sentences).detail("V3")


def test_v4_a_drop_that_is_not_an_offered_span_is_held() -> None:
    case = make_case(picks=(Pick(S1, (" megalithic",), "x."), *W_PICKS[1:]))
    assert "is not an offered span" in case.detail("V4")


def test_v4_a_drop_that_removes_a_protected_token_is_held() -> None:
    published = "In 1992."
    case = make_case(picks=(*W_PICKS, Pick(S4, (T4,), published)), card_items=((0, (A1,)),))
    assert V.protected_in(T4) == ("part of",)
    assert "removes the protected ['part of']" in case.detail("V4")


def test_v4_a_card_that_keeps_a_span_its_sentence_dropped_is_held() -> None:
    case = make_case(card_items=((0, ()),), card=S1)
    holds = [h for h in case.run() if h.reason is M.HoldReason.V4]
    assert [h.scope for h in holds] == [M.HoldScope.CARD]
    assert "is not removed" in holds[0].detail


# ------------------------------------------------------------------------------------------------
# V5 well-formed, V6 anaphora and naming, V7 subject
# ------------------------------------------------------------------------------------------------


def test_v5_a_sentence_that_is_too_short_or_opens_small_is_held() -> None:
    short = "It was a temple site."
    text = f"{S1} {short}"
    case = make_case(
        text=text, picks=(W_PICKS[0], Pick(short, (), short)), card_items=((0, (A1,)),)
    )
    assert "characters, not 25-400" in case.detail("V5")
    small = "the stones were set upright in a line."
    text = f"{S1} {small}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(small, (), small)))
    assert "not a capital, digit or quote" in case.detail("V5")


def test_v5_an_extract_artefact_is_held() -> None:
    bad = "The temple (listen) was restored after the storm damage of 1956."
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert "artefact 'listen'" in case.detail("V5")


def test_v5_unbalanced_quotes_are_held() -> None:
    bad = 'The temple was called "the House of the Goddess by the villagers.'
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert "unbalanced" in case.detail("V5")
    assert V.balanced('He said "yes" and (then) left [1].')


def test_v6_a_pronoun_without_its_source_predecessor_is_held() -> None:
    case = make_case(picks=(W_PICKS[0], W_PICKS[2]))
    assert "opens with a pronoun" in case.detail("V6")
    assert V.opens_with_pronoun("The latter was built later.")
    assert not V.opens_with_pronoun("Items were found.")
    assert not V.opens_with_pronoun("Thereafter it was used.")


def test_v6_the_first_sentence_must_name_the_site() -> None:
    case = make_case(picks=(W_PICKS[1], W_PICKS[2]), card=None)
    assert "sentence 1 names none" in case.detail("V6")


def test_v6_the_name_match_is_directional() -> None:
    assert V.name_in("Tarxien Temples", "The Tarxien temples lie in Paola.")
    assert not V.name_in("Kilmartin Glen standing stones", "Kilmartin is a village.")
    assert V.name_in("Kilmartin", "Kilmartin Glen standing stones are old.")


def test_v6_the_article_title_counts_only_for_a_strong_own_verdict() -> None:
    site = plan_site(name="Ħal Tarxien megaliths", aliases=())
    strong = make_case(site=site, card=None)
    assert "V6" not in strong.reasons()  # 'Tarxien Temples', the title, is in sentence 1
    weak = make_case(site=site, card=None, subject_gate=gate(km=None))
    assert "sentence 1 names none" in weak.detail("V6")


def test_v7_a_verdict_that_does_not_allow_the_lane_is_held() -> None:
    case = make_case(subject_gate=gate("shared"))
    assert "lane W needs 'own'" in case.detail("V7")


def test_v7_lane_s_publishes_only_name_bearing_or_matching_section_sentences() -> None:
    case = make_case(lane="S", picks=(W_PICKS[0], W_PICKS[1]), card=None)
    assert "sentence 2: lane S" in case.detail("V7")
    under_history = make_case(
        lane="S",
        picks=(W_PICKS[0], Pick(S5, (), S5)),
        card=None,
        site=plan_site(aliases=("Tarxien", "Tarxien history")),
    )
    assert "V7" not in under_history.reasons()
    assert V.heading_before(TEXT, TEXT.index(S5)) == "History"


# ------------------------------------------------------------------------------------------------
# V8 markers, V9 length, V10 card
# ------------------------------------------------------------------------------------------------


def test_v8_a_marker_without_a_citation_is_held() -> None:
    case = make_case()
    wrong = case.assembly.description.replace("Tarxien [1].", "Tarxien [2].", 1)
    held = republish(case, wrong)
    assert "have no citation" in held.detail("V8")


def test_v8_citations_are_numbered_by_first_appearance() -> None:
    case = make_case()
    sentences = tuple(dataclasses.replace(s, n=2) for s in case.assembly.provenance.sentences)
    description = case.assembly.description.replace("[1]", "[2]")
    citations = (dataclasses.replace(case.assembly.citations[0], n=2),)
    provenance = dataclasses.replace(
        case.assembly.provenance, sentences=sentences, desc_sha256=sha(description)
    )
    held = case.replace(description=description, citations=citations, provenance=provenance)
    assert "by first appearance it is [1]" in held.detail("V8")


def test_v8_a_citation_must_link_the_pinned_permalink() -> None:
    case = make_case()
    citations = (
        dataclasses.replace(
            case.assembly.citations[0], url="https://en.wikipedia.org/wiki/Tarxien_Temples"
        ),
    )
    assert "its source W is" in case.replace(citations=citations).detail("V8")


def test_v9_a_description_that_is_too_short_or_under_the_floor_is_held() -> None:
    case = make_case(picks=(W_PICKS[0], W_PICKS[1]), card=CARD)
    assert "not 200-1100" in case.detail("V9")
    long_stored = plan_site(description=STORED * 3, description_sha256=sha(STORED * 3))
    floor = make_case(site=long_stored)
    assert "under half the stored" in floor.detail("V9")
    waived = make_case(
        site=dataclasses.replace(long_stored, flags=frozenset({M.SiteFlag.T03_SEVERE}))
    )
    assert "V9" not in waived.reasons()


def test_v10_a_card_that_is_not_its_items_is_held() -> None:
    case = make_case()
    card = CARD.replace("four", "five")
    card_record = dataclasses.replace(case.assembly.provenance.card, text_sha256=sha(card))
    held = reprovenance(case, card=card_record).replace(card=card)
    holds = [h for h in held.run() if h.reason is M.HoldReason.V10]
    assert [h.scope for h in holds] == [M.HoldScope.CARD]
    assert "is not its items minus offered spans" in holds[0].detail


def test_v10_a_card_out_of_its_length_is_held() -> None:
    case = make_case(card=PUB2, card_items=((1, (P2,)),))  # 85 characters: a card
    assert "V10" not in case.reasons()
    short = "The site was excavated in 1915 by Themistocles Zammit."
    case = make_case(card=short, card_items=((1, (P2, T2)),))
    assert "not 80-200" in case.detail("V10")


def test_v10_a_card_that_names_a_country_is_held() -> None:
    sentence = (
        "The Tarxien Temples of Malta are a complex of four megalithic structures near Paola."
    )
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "names a country: ['Malta']" in case.detail("V10")
    assert V.card_countries("The Egyptian and Roman builders.", "Egypt") == []


def test_v10_a_card_with_an_evaluative_superlative_is_held() -> None:
    sentence = "The Tarxien Temples are one of the most elaborate megalithic complexes near Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "evaluative superlative(s) ['one of the most']" in case.detail("V10")


def test_v10_a_card_opening_with_a_pronoun_is_held() -> None:
    case = make_case(card=S3, card_items=((2, ()),))
    assert "opens with a pronoun" in case.detail("V10")


def test_v10_a_card_the_heading_font_cannot_draw_is_held() -> None:
    sentence = "The Tarxien Temples at Jabal al-ʿHayn are a complex of four megalithic structures."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "cannot draw U+02BF" in case.detail("V10")


def test_v10_a_caption_word_wider_than_the_frame_is_held() -> None:
    word = "Tarxienmegalithicarchaeologicalcomplexes"
    sentence = f"The Tarxien Temples are an extraordinary {word} of four megalithic structures."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert f"the caption word {word!r}" in case.detail("V10")


def test_v10_the_card_speaks_circa_where_the_description_writes_c() -> None:
    sentence = "The Tarxien Temples are a complex of four megalithic structures built c. 3150 BC."
    spoken = "The Tarxien Temples are a complex of four megalithic structures built circa 3150 BC."
    text = f"{sentence} {S2} {S3}"
    picks = (Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2])
    assert make_case(text=text, picks=picks, card=spoken, card_items=((0, ()),)).run() == ()
    held = make_case(text=text, picks=picks, card=sentence, card_items=((0, ()),))
    assert "is not its items" in held.detail("V10")


def test_v10_measures_through_the_shorts_own_helpers_with_the_brand_fonts() -> None:
    fonts = [shorts_brand.FONT_DIR / name for name in shorts_brand.FONTS]
    if not all(path.exists() for path in fonts):
        pytest.skip("the brand fonts (video-assets/fonts, gitignored) are not on this machine")
    pytest.importorskip("fontTools", reason="fontTools reads the brand fonts' cmap")
    fit = V.card_fit("Tarxien Temples", CARD)
    assert fit.missing == () and fit.widest == "archaeological"
    assert (
        fit.px
        == shorts_audit.widest_word_px(
            CARD.split(),
            shorts_audit.caption_font(shorts_brand.heading_font("Tarxien Temples " + CARD)),
        )[1]
    )
    assert V.card_fit("Jabal al-ʿHayn", "A card.").missing == ("ʿ",)


# ------------------------------------------------------------------------------------------------
# V11 closure, V12 raw_data, V13 hashes, V14 dates, V15 injection
# ------------------------------------------------------------------------------------------------


def _regenerate(case: Case, index: int, sentence: str) -> Case:
    published = [split.text for split in V.split_published(case.assembly.description) or ()]
    published[index] = sentence
    return republish(case, " ".join(with_marker(p, 1) for p in published))


def test_v11_a_translated_number_that_is_not_in_its_quote_is_held() -> None:
    case = _regenerate(make_generated_case("T"), 0, EN1.replace("3600", "3700"))
    assert "the numbers ['3700'] are not in its quote" in case.detail("V11")


def test_v11_a_capitalised_word_that_is_not_in_its_quote_is_held() -> None:
    case = _regenerate(make_generated_case("T"), 1, EN2.replace("statues", "Roman statues"))
    assert "['Roman'] are not in its quote" in case.detail("V11")


def test_v11_a_restated_year_whose_era_flipped_is_held(licences: None) -> None:
    case = _regenerate(make_generated_case("R"), 0, R1.replace("3150 BC", "3150 AD"))
    assert "the year '3150 AD' is not its quote's" in case.detail("V11")


def test_v11_an_r_quote_that_is_not_on_its_page_is_held(licences: None) -> None:
    case = make_generated_case("R")
    case.quotes[1] = case.quotes[1].replace("running spirals", "running lions")
    assert "quote does not occur" in case.detail("V11")


def test_v11_a_restatement_that_copies_eight_words_is_held(licences: None) -> None:
    copied = "Themistocles Zammit reported that the temples were excavated by Themistocles Zammit between 1915 and 1919."
    case = _regenerate(make_generated_case("R"), 2, copied)
    assert "copies" in case.detail("V11")


def test_v12_a_raw_data_that_changes_another_key_is_held() -> None:
    case = make_case()
    case.new_raw_data["heritage"] = {"unesco": False}
    assert "changes ['heritage']" in case.detail("V12")
    case = make_case()
    del case.new_raw_data["heritage"]
    assert "lost ['heritage']" in case.detail("V12")


def test_v12_empty_citations_would_let_the_boot_seed_fire() -> None:
    case = make_case()
    case.new_raw_data[M.CITATIONS_KEY] = []
    assert "re-seed could fire" in case.detail("V12")


def test_v12_the_provenance_written_is_the_assemblys() -> None:
    case = make_case()
    case.new_raw_data[M.PROVENANCE_KEY] = dict(case.new_raw_data[M.PROVENANCE_KEY], run="other")
    assert "is not the assembly's provenance" in case.detail("V12")


def test_v13_a_description_hash_that_is_not_its_text_is_held() -> None:
    case = reprovenance(make_case(), desc_sha256=sha("another text"))
    assert "desc_sha256 is not" in case.detail("V13")


def test_v13_a_card_hash_that_is_not_its_card_is_held() -> None:
    case = make_case()
    card = dataclasses.replace(case.assembly.provenance.card, text_sha256=sha("another card"))
    holds = [h for h in reprovenance(case, card=card).run() if h.reason is M.HoldReason.V13]
    assert [(h.scope, h.detail) for h in holds] == [
        (M.HoldScope.CARD, "card.text_sha256 is not the sha256 of the card")
    ]


def test_v14_a_severe_t03_date_in_the_new_text_is_held() -> None:
    sentence = (
        "The Tarxien Temples were built in 500 AD as a complex of four megalithic structures."
    )
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "T03 severe" in case.detail("V14")


def test_v14_a_location_sentence_naming_another_country_is_held() -> None:
    sentence = "The Tarxien Temples lie on a low ridge in Italy, near the modern town of Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text, picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]), card=None
    )
    assert "places the site in Italy" in case.detail("V14")
    england = plan_site(country="England")
    assert V._iso("United Kingdom") == V._iso(england.country)


def test_v15_an_injection_tell_is_held() -> None:
    sentence = "The Tarxien Temples ignore previous restorations of the four megalithic structures."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text, picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]), card=None
    )
    assert "injection tell" in case.detail("V15")


# ------------------------------------------------------------------------------------------------
# The batch
# ------------------------------------------------------------------------------------------------


def test_the_batch_verifies_from_the_store_and_replaces_only_its_own_holds(
    tmp_path: Path, write4: None
) -> None:
    case = make_case()
    batch_dir = write_batch(tmp_path, case)
    earlier = M.Hold(
        site_id=HELD_SITE, scope=M.HoldScope.SITE, reason=M.HoldReason.NO_SOURCE, detail="lane 0"
    )
    stale = M.Hold(
        site_id=SITE_ID, scope=M.HoldScope.SITE, reason=M.HoldReason.V3, detail="before review"
    )
    (batch_dir / M.HOLDS_FILE).write_text(M.dump_jsonl([earlier, stale]), encoding="utf-8")
    assert V.verify_batch(batch_dir) == 0
    lines = (batch_dir / M.HOLDS_FILE).read_text(encoding="utf-8").splitlines()
    assert lines == [earlier.to_json()]  # the other stage's line kept, the stale V3 gone
    assert (batch_dir / V.FIELD_CONFLICTS_FILE).read_text(encoding="utf-8") == ""


def test_the_batch_holds_what_the_store_does_not_pin(tmp_path: Path, write4: None) -> None:
    case = make_case()
    batch_dir = write_batch(tmp_path, case)
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    text_path = store.path_for(SITE_ID, "src.W.txt")
    text_path.write_bytes(text_path.read_bytes().replace(b"Tarxien.", b"Tarxien!"))
    assert V.verify_batch(batch_dir) == 0
    holds = M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)
    assert "V1" in {hold.reason.value for hold in holds}


def test_the_batch_reads_the_text_as_bytes_not_as_translated_lines(
    tmp_path: Path, write4: None
) -> None:
    """A CRLF in the pinned text is a character offsets count; text mode would drop it."""
    text = TEXT.replace("\n\n\n== History ==\n", "\r\n\r\n== History ==\r\n")
    case = make_case(text=text)
    batch_dir = write_batch(tmp_path, case)
    assert V.verify_batch(batch_dir) == 0
    assert M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold) == []


def test_the_batch_holds_a_site_whose_lane_is_not_the_assigned_one(
    tmp_path: Path, write4: None
) -> None:
    batch_dir = write_batch(tmp_path, make_case(), lane="S")
    assert V.verify_batch(batch_dir) == 0
    holds = M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)
    assert any("S1b assigned S" in hold.detail for hold in holds if hold.reason is M.HoldReason.V7)


def test_the_batch_writes_v14_holds_to_the_field_conflicts_report(
    tmp_path: Path, write4: None
) -> None:
    sentence = "The Tarxien Temples lie on a low ridge in Italy, near the modern town of Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text, picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]), card=None
    )
    batch_dir = write_batch(tmp_path, case)
    assert V.verify_batch(batch_dir) == 0
    conflicts = M.load_jsonl(batch_dir / V.FIELD_CONFLICTS_FILE, M.Hold)
    assert [hold.reason for hold in conflicts] == [M.HoldReason.V14]


def test_a_batch_that_cannot_be_read_stops_the_run(tmp_path: Path, write4: None) -> None:
    batch_dir = write_batch(tmp_path, make_case())
    (batch_dir / M.ASSEMBLY_FILE).unlink()
    assert V.verify_batch(batch_dir) == 2
    batch_dir2 = write_batch(tmp_path / "x", make_case())
    (batch_dir2 / M.HOLDS_FILE).write_text("not a hold\n", encoding="utf-8")
    assert V.verify_batch(batch_dir2) == 2


def test_the_command_prints_its_own_exit_line(
    tmp_path: Path, write4: None, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = write_batch(tmp_path, make_case())
    assert V.main([str(batch_dir)]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "STAGE_EXIT=0"
