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
import re
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
from phase4 import batch4 as B  # noqa: E402 - only for the V6 names parity test
from phase4 import model4 as M  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402 - only for the V6 names parity test
from phase4 import sentences as S  # noqa: E402 - only for the D3 parity test
from phase4 import verify4 as V  # noqa: E402

from pipeline.video import shorts_audit, shorts_brand  # noqa: E402
from tests.remediation import p4_fixtures as X  # noqa: E402
from tests.remediation.p4_garble_cases import GARBLE_CASES  # noqa: E402
from tests.remediation.p4_span_cases import SPAN_CASES  # noqa: E402
from tests.remediation.phase4_cases import (  # noqa: E402
    A1,
    CARD,
    EN1,
    EN2,
    FR2,
    FR_TEXT,
    HELD_SITE,
    L4,
    P2,
    PAGE,
    PERMALINK,
    PUB2,
    Q1,
    R1,
    R_URL,
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
    retitle,
    sha,
    with_marker,
    witness,
    witness_answer,
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


def _offered(sentence: str, source_id: str = "W") -> list[str]:
    return [sentence[a:b] for a, b in V.offered_spans(source_id, sentence, 0, len(sentence))]


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


def test_a_correction_or_contrast_marker_is_protected() -> None:
    """Pilot 2, T3: House of the Faun published its statue as 'a dancing faun' after a `p` drop
    removed '(actually a satyr, since the lower body is that of a man)', the passage's own
    correction. V4 now refuses that drop like a hedge's."""
    faun = (
        "The bronze statue of a dancing faun (actually a satyr, since the lower body is that of a "
        "man) is what the House of the Faun is named after."
    )
    correction = " (actually a satyr, since the lower body is that of a man)"
    assert (faun.index(correction), faun.index(correction) + len(correction)) in (
        V.candidate_spans("W", faun, 0, len(faun))
    )
    assert _offered(faun) == []
    assert V.protected_in(correction) == ("actually",)
    assert V.protected_in("In fact, ") == ("in fact",)
    assert V.protected_in(", rather than in the town") == ("rather",)
    assert V.protected_in(", instead of a temple,") == ("instead",)
    assert V.protected_in(" (wrongly so named)") == ("wrongly",)
    assert V.protected_in(" (sometimes erroneously written Bara)") == ("erroneous*",)


def test_a_number_comma_and_a_bracketed_comma_are_no_delimiters() -> None:
    sentence = "The hoard of 2,500 coins (found in 1920, near the gate) lies in the museum store."
    assert _offered(sentence) == [" (found in 1920, near the gate)"]


def test_an_unspaced_dash_pair_is_not_offered() -> None:
    assert _offered("The fort—built by the Romans—was abandoned in the 5th century AD.") == []
    # spaced after but not before: the range would start one character early and eat the 't'
    assert _offered("The fort— built by the Romans— was abandoned in the 5th century AD.") == []
    # spaced before but not after: removing the pair would glue 'fort' to 'was' ('The fortwas')
    assert _offered("The fort —built by the Romans —was abandoned in the 5th century AD.") == []


def test_a_dash_pair_inside_a_parenthesis_is_no_insertion() -> None:
    """Rule 3: only a top-level dash delimits; the parenthesis around the pair is the span."""
    sentence = "The fort (built – by the Romans – in stone) was abandoned in the 5th century AD."
    assert _offered(sentence) == [" (built – by the Romans – in stone)"]


def test_a_range_dash_on_either_side_of_the_pair_refuses_it() -> None:
    """Rule 6 judges both dashes: here only the second has a digit beside it."""
    assert _offered("The wall – of local stone laid in 1200 – ran along the ridge above.") == []


def test_an_empty_pair_and_an_empty_last_segment_are_no_spans() -> None:
    assert _offered("The wall – – ran along the ridge above.") == []
    assert _offered("The wall, , ran along the ridge above.") == [
        "The wall, ",
        ", ran along the ridge above",
    ]
    assert _offered("The wall was built in 1900, .") == ["The wall was built in 1900, "]


def test_a_leading_phrase_is_at_most_six_tokens() -> None:
    seven = "In the very late summer of 1920, the site was excavated by a team."
    assert "In the very late summer of 1920, " not in _offered(seven)
    six = "In the late summer of 1920, the site was excavated by a team."
    assert "In the late summer of 1920, " in _offered(six)


@pytest.mark.parametrize(("source_id", "text", "spans"), SPAN_CASES)
def test_the_span_cases_verify4_offers_exactly(source_id: str, text: str, spans: dict) -> None:
    """D3: verify4's own finder offers exactly the ranges `SPAN_CASES` pins (section 7), the
    fixture S2's finder is held to as well."""
    offered = V.offered_spans(source_id, text, 0, len(text))
    assert sorted(text[a:b] for a, b in offered) == sorted(spans.values())


#: The verifier's own span texts above, run through both finders as well.
VERIFIER_SPAN_TEXTS = (
    "The temple was built c. 2500 BC by Khufu, whose tomb lies nearby.",
    S1,
    S2,
    S4,
    "The fort – built by the Romans – was abandoned in the 5th century.",
    "The wall, which was not finished, stands (possibly) on older footings, suggesting reuse.",
    "The hoard of 2,500 coins (found in 1920, near the gate) lies in the museum store.",
    "The fort—built by the Romans—was abandoned in the 5th century AD.",
    "The fort— built by the Romans— was abandoned in the 5th century AD.",
    "The fort —built by the Romans —was abandoned in the 5th century AD.",
    "The fort (built – by the Romans – in stone) was abandoned in the 5th century AD.",
    "In the very late summer of 1920, the site was excavated by a team.",
    "In the late summer of 1920, the site was excavated by a team.",
    "The wall – of local stone laid in 1200 – ran along the ridge above.",
    "The wall – – ran along the ridge above.",
    "The wall, , ran along the ridge above.",
    "The wall was built in 1900, .",
)


@pytest.mark.parametrize(
    ("source_id", "text"),
    [(source_id, text) for source_id, text, _ in SPAN_CASES]
    + [("W", text) for text in VERIFIER_SPAN_TEXTS],
)
def test_both_finders_offer_the_same_ranges(source_id: str, text: str) -> None:
    """D3 parity: S2's finder (`sentences.split_source`) and verify4's own offer the same ranges
    over the shared fixture and the verifier's texts. Neither module imports the other; this test
    imports both."""
    (sentence,) = S.split_source(source_id, text)
    s2 = sorted((span.start, span.end) for span in sentence.spans)
    assert sorted(V.offered_spans(source_id, text, sentence.start, sentence.end)) == s2


#: V6's names on both sides (pilot 1, T8): the gate over the article, `src.D` as stored, and which
#: of the two extra names count - the pinned title, and the pinned item's English label.
NAME_PARITY_CASES = [
    ("strong", {}, X.witness_answer(label="Stone Temple"), {}, True, True),
    ("no-distance", {"km": None}, X.witness_answer(), {}, False, False),
    ("qid-mismatch", {"qid_match": False}, X.witness_answer(), {}, False, False),
    ("place-item", {"place_item": True}, X.witness_answer(), {}, False, False),
    ("shared", {"verdict": "shared", "shared": True}, X.witness_answer(), {}, False, False),
    ("no-witness", {}, None, {}, True, False),
    ("another-item", {}, X.witness_answer(qid="Q2"), {}, True, False),
    ("unpinned", {}, X.witness_answer(), {"sha256_raw": "0" * 64}, True, False),
    ("no-english-label", {}, X.witness_answer(label=None), {}, True, False),
    ("not-d", {}, X.witness_answer(), {"id": "W"}, True, False),
]
#: The stored name without its disambiguator (pilot 2, T8): `X (Y)` -> X, `X, Y` -> X, else none.
NAME_BASE_CASES = [
    ("Partiscum (Castra)", "Partiscum"),
    ("Clare, Suffolk", "Clare"),
    ("Beacon Hill, Burghclere, Hampshire", "Beacon Hill"),
    ("Quirigua (Parque Arqueológico y Ruinas de Quiriguá)", "Quirigua"),
    ("Justinianopolis (Epirus)", "Justinianopolis"),
    ("Tarxien Temples, Paola (Malta)", "Tarxien Temples, Paola"),
    ("Stonehenge", None),
    ("Altar Stone - Stonehenge", None),
    ("House (of the Faun) Pompeii", None),
    ("Temple (of Bel (Palmyra))", None),
    ("(Castra)", None),
    (", Suffolk", None),
]


@pytest.mark.parametrize(
    ("gate_over", "raw", "d_over", "title_counts", "label_counts"),
    [case[1:] for case in NAME_PARITY_CASES],
    ids=[case[0] for case in NAME_PARITY_CASES],
)
def test_s3_and_v6_accept_the_same_names(
    tmp_path: Path,
    gate_over: dict,
    raw: bytes | None,
    d_over: dict,
    title_counts: bool,
    label_counts: bool,
) -> None:
    """The D3 idea for V6's names (pilot 1, T8, 2026-09-24): S3 (`select_stage.v6_names`, what the
    selector is shown as `also_named`) and V6 (`verify4.v6_names`) read the same rule - the stored
    names, and for a strong 'own' verdict the pinned title and the pinned item's English label - in
    their own code, from the same store. Neither imports the other; this test imports both."""
    gate_dict = {**X.STRONG_OWN.to_dict(), **gate_over}
    article = X.wiki_doc("W", X.ARTICLE, title="Stone Temple of Gozo").to_dict()
    doc = M.SourceDoc.from_dict({**article, "subject_gate": gate_dict})
    site = X.plan_site("site-1", name="Ggantija South", aliases=("Ta' Ġgantija",))
    setup = X.SiteSetup(site=site, lane=M.Lane.W, sources={"W": (doc, X.ARTICLE)})
    batch_dir = X.make_batch(tmp_path, [setup])
    if raw is not None:
        X.pin_witness(batch_dir, "site-1", raw, **d_over)
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    meta, _ = B.read_source(batch_dir, "site-1", "W")
    s3 = SEL.v6_names(site, meta, SEL.site_witness(batch_dir, "site-1"))
    v6 = V.v6_names(site, B.read_meta(batch_dir, "site-1", "W"), V.read_witness(store, "site-1"))
    expected = ["Ggantija South", "Ta' Ġgantija"]
    expected += ["Stone Temple of Gozo"] if title_counts else []
    expected += ["Stone Temple"] if label_counts else []
    assert list(s3) == v6 == expected


@pytest.mark.parametrize(
    ("gate_over", "raw", "d_over", "title_counts", "label_counts"),
    [case[1:] for case in NAME_PARITY_CASES],
    ids=[case[0] for case in NAME_PARITY_CASES],
)
@pytest.mark.parametrize(("name", "base"), NAME_BASE_CASES)
def test_s3_and_v6_accept_the_same_base_name(
    tmp_path: Path,
    gate_over: dict,
    raw: bytes | None,
    d_over: dict,
    title_counts: bool,
    label_counts: bool,
    name: str,
    base: str | None,
) -> None:
    """Pilot 2's T8 fix on both sides: the stored name's base (`X (Y)` -> X, `X, Y` -> X) counts
    exactly where the title does - a strong 'own' verdict of the source - in S3's code and in
    V6's, over the same store and names."""
    gate_dict = {**X.STRONG_OWN.to_dict(), **gate_over}
    article = X.wiki_doc("W", X.ARTICLE, title="Stone Temple of Gozo").to_dict()
    doc = M.SourceDoc.from_dict({**article, "subject_gate": gate_dict})
    site = X.plan_site("site-1", name=name, aliases=())
    setup = X.SiteSetup(site=site, lane=M.Lane.W, sources={"W": (doc, X.ARTICLE)})
    batch_dir = X.make_batch(tmp_path, [setup])
    if raw is not None:
        X.pin_witness(batch_dir, "site-1", raw, **d_over)
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    meta, _ = B.read_source(batch_dir, "site-1", "W")
    s3 = SEL.v6_names(site, meta, SEL.site_witness(batch_dir, "site-1"))
    v6 = V.v6_names(site, B.read_meta(batch_dir, "site-1", "W"), V.read_witness(store, "site-1"))
    assert list(s3) == v6
    assert (base in v6) is (base is not None and title_counts), (name, v6)


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
    # D2: the era-first date and the {{circa}} thin space read as S4 reads them (model4's pattern)
    assert (
        V.spoken("It was built c. AD 79 on the shore.") == "It was built circa AD 79 on the shore."
    )
    assert (
        V.spoken("It was built ca. BC 500 by farmers.") == "It was built circa BC 500 by farmers."
    )
    assert V.spoken("It was built c.\u2009300 BC.") == "It was built circa 300 BC."
    assert V.spoken("A 5th c. BCE wall.") == "A 5th c. BCE wall."


def test_the_card_speaks_through_the_one_circa_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    """D2: V10 reads `model4.CIRCA_PATTERN`, the one definition S4 imports too; a pattern of the
    verifier's own would not follow it."""
    monkeypatch.setattr(M, "CIRCA_PATTERN", re.compile(r"(?P<c>[Cc])irca-(?=\d)"))
    assert V.spoken("Built circa-300 and Circa-400.") == "Built circa 300 and Circa 400."


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
            witness=V.Witness(meta=None, raw=None),
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
        "https://en.wikipedia.org/wiki/index.php?title=Tarxien_Temples&oldid=1234567",
        "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567#History",
        "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&title=Paola&oldid=1234567",
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


def _with_ref(case: Case, **over: Any) -> Case:
    """The case whose (one) provenance source reference differs in `over`; the attribution follows
    a changed URL (model4 wants it to be a cited source's)."""
    provenance = case.assembly.provenance
    ref = dataclasses.replace(provenance.sources[0], **over)
    attribution = dataclasses.replace(provenance.attribution, url=ref.url)
    return reprovenance(case, sources=(ref,), attribution=attribution)


def test_v1_the_provenance_links_the_pinned_permalink() -> None:
    """Another article's oldid permalink of the same revision number is a permalink, but not the
    pinned one: only V1 compares the provenance's URL with the meta."""
    other = "https://en.wikipedia.org/w/index.php?title=Hal_Tarxien&oldid=1234567"
    held = _with_ref(make_case(), url=other)
    assert "not the pinned permalink" in held.detail("V1")


def test_v1_the_provenance_pins_the_metas_text_hash() -> None:
    held = _with_ref(make_case(), text_sha256="0" * 64)
    assert "provenance pins 0000000000000000, the meta another" in held.detail("V1")


@pytest.mark.parametrize(
    "over", [{"revid": 1234568}, {"rev_timestamp": "2026-09-02T10:00:00Z"}], ids=str
)
def test_v1_the_provenance_pins_the_metas_revision(over: dict[str, Any]) -> None:
    assert "another revision than the meta" in _with_ref(make_case(), **over).detail("V1")


def test_v1_the_meta_names_its_own_source() -> None:
    case = make_case()
    case.metas["W"]["id"] = "T.fr"
    assert "the meta names source 'T.fr'" in case.detail("V1")


def test_v1_the_provenance_licence_is_the_metas() -> None:
    held = _with_ref(make_case(), licence=M.Licence.CC0)
    assert "provenance says CC0, the meta otherwise" in held.detail("V1")


def test_v1_a_lane_r_page_is_restricted(licences: None) -> None:
    case = make_generated_case("R")
    case.metas["R1"]["licence"] = M.Licence.CC_BY_SA_4.value
    held = _with_ref(case, licence=M.Licence.CC_BY_SA_4)
    assert "lane R pages are restricted" in held.detail("V1")


def test_v1_a_lane_r_provenance_links_the_page_the_fetch_ended_at(licences: None) -> None:
    case = make_generated_case("R")
    case.metas["R1"]["final_url"] = R_URL + "visit/"
    assert "the page ended at" in case.detail("V1")


def test_v1_a_restricted_page_pins_no_revision(licences: None) -> None:
    held = _with_ref(make_generated_case("R"), revid=5)
    assert "a restricted page has no revision" in held.detail("V1")


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


HEDGED = "According to Zammit, Phoenician settlers raised the temples in 2500 BC."
UNHEDGED = "Phoenician settlers raised the temples in 2500 BC."


def test_v2_a_range_that_is_not_one_whole_sentence_is_held() -> None:
    """C2: a range starting after 'According to Zammit, ' drops the attribution without a drop
    V4 could see (`according` is protected, so no offered span carries it). The range must be
    exactly one sentence of the pinned text's split (contract section 3)."""
    text = f"{S1} {S2} {HEDGED}"
    case = make_case(text=text, picks=(*W_PICKS[:2], Pick(UNHEDGED, (), UNHEDGED)))
    assert "is not one whole sentence of W" in case.detail("V2")
    # the whole sentence, hedge and all, passes the same check
    whole = make_case(text=text, picks=(*W_PICKS[:2], Pick(HEDGED, (), HEDGED)))
    assert "V2" not in whole.reasons()


def test_v2_the_split_counts_every_line_and_finds_a_repeated_sentence_in_order() -> None:
    """A sentence after a heading line keeps its offsets, and the second of two equal sentences
    in one line is found where it stands, not at the first."""
    text = f"{S1} {S3} {S3} \n\n\n== History ==\n{S5}"  # a space ends line 1
    case = make_case(text=text, picks=(W_PICKS[0], W_PICKS[2], Pick(S5, (), S5)))
    second = text.index(S3, text.index(S3) + 1)
    sentences = case.assembly.provenance.sentences
    moved = dataclasses.replace(sentences[1], start=second, end=second + len(S3))
    held = reprovenance(case, sentences=(sentences[0], moved, sentences[2]))
    held.quotes[1] = S3
    assert "V2" not in held.reasons()
    assert (second, second + len(S3)) in V.sentence_ranges(text)
    assert (text.index(S5), len(text)) in V.sentence_ranges(text)


def test_v2_a_range_over_two_sentences_is_held() -> None:
    joined = f"{S2} {S3}"
    case = make_case(picks=(W_PICKS[0], Pick(joined, (), joined)))
    assert "sentence 2: [" in case.detail("V2") and "not one whole sentence" in case.detail("V2")


def test_v2_a_translated_range_is_one_whole_sentence_too() -> None:
    case = make_generated_case("T")
    first = case.assembly.provenance.sentences[0]
    cut = dataclasses.replace(first, start=first.start + len("Le "))
    held = reprovenance(case, sentences=(cut, *case.assembly.provenance.sentences[1:]))
    held.quotes[0] = FR_TEXT[cut.start : cut.end]
    assert "is not one whole sentence of T.fr" in held.detail("V2")


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


@pytest.mark.parametrize("tail", [" ", "  ", "\n"], ids=repr)
def test_v3_a_description_that_ends_in_whitespace_is_held(tail: str) -> None:
    """C5: every byte is re-derived, the space after the last marker too."""
    case = make_case()
    held = republish(case, case.assembly.description + tail)
    assert "marker-terminated sentence(s)" in held.detail("V3")


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


def test_v5_a_sentence_that_ends_on_an_abbreviation_is_held() -> None:
    """The splitter keeps `Mt.` inside a sentence; a published sentence ending on it is a
    fragment, and its marker must not hide that (`... Mt [1].`)."""
    cut = "The temples stand on a low ridge above the harbour, facing Mt."
    text = f"{S1} {cut}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(cut, (), cut)))
    assert "not a complete sentence" in case.detail("V5")


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


@pytest.mark.parametrize(
    "bad",
    [
        "The temple was called “the House of the Goddess by the villagers.",
        "The temple was called «the House of the Goddess by the villagers.",
    ],
)
def test_v5_an_unclosed_curly_or_guillemet_quote_is_held(bad: str) -> None:
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert "unbalanced" in case.detail("V5")
    assert V.balanced("He said “yes” and «no» [1].")


@pytest.mark.parametrize(
    ("label", "bad"),
    [
        ("'=='", "The temple was restored == History == after the storm of 1956."),
        ("an empty '()'", "The temple () was restored after the storm damage of 1956."),
        ("'( ;'", "The temple (; restored) was repaired after the storm of 1956."),
        ("'displaystyle'", "The temple displaystyle was restored after the storm of 1956."),
        ("doubled punctuation", "The temple, , was restored after the storm damage of 1956."),
    ],
)
def test_v5_every_extract_artefact_is_held(label: str, bad: str) -> None:
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert f"artefact {label}" in case.detail("V5")


@pytest.mark.parametrize(
    ("label", "bad"),
    [
        (
            "a full stop inside the sentence before a lowercase word",
            "The temple lies on the slopes of Cotylion Mountain. near the village of Skliros.",
        ),
        (
            "a preposition directly before a comma",
            "The temple was a Roman shrine, and in the hamlet of, Rudchester, Northumberland.",
        ),
    ],
)
def test_v5_a_garbled_sentence_is_held(label: str, bad: str) -> None:
    """Pilot 2 (T5): Bassae and Vindobala published their sources' garbles word for word; V5 now
    holds either shape of a published sentence."""
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert f"sentence 2: {label}" in case.detail("V5")


@pytest.mark.parametrize(("text", "garbled"), GARBLE_CASES)
def test_the_garble_cases_v5_judges_exactly(text: str, garbled: bool) -> None:
    assert bool(V.ill_formed(text)) is garbled


@pytest.mark.parametrize(("text", "garbled"), GARBLE_CASES)
def test_s2_and_v5_judge_the_same_sentences_garbled(text: str, garbled: bool) -> None:
    """D3 parity for T5: S2's pool (`sentences.garbled`) and V5 (`verify4.ill_formed`) judge the
    shared fixture alike; neither module imports the other."""
    assert S.garbled(text) is bool(V.ill_formed(text)) is garbled


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
    # the name is never the haystack: a sentence shorter than the name cannot carry it
    assert not V.name_in("Kilmartin Glen standing stones", "Kilmartin Glen.")


def test_v6_the_name_match_is_bounded_by_tokens() -> None:
    """C6: the name's tokens stand as whole tokens in the sentence; a short name inside a longer
    word ('Ur' in 'during', 'Pod' in 'tripod') is no mention of the site."""
    for name, sentence in (
        ("Ur", "The ziggurat was restored during the 1930s."),
        ("Ur", "The structure stands on a mound."),
        ("Pod", "The tripod vessels were found in the pit."),
        ("Vani", "Vanished walls were traced in the field."),
        ("Nether Largie North Cairn", "Nether Largie South Cairn lies to the south."),
    ):
        assert not V.name_in(name, sentence), (name, sentence)
    for name, sentence in (
        ("Ur", "Ur was a city of Sumer."),
        ("Tarxien Temples", "The Tarxien temples lie in Paola."),
        ("Tarxien Temple", "The Tarxien Temples lie in Paola."),  # one letter off a long token
        ("Chichén-Itzá", "The ruins of Chichen Itza lie in Yucatan."),
    ):
        assert V.name_in(name, sentence), (name, sentence)
    # a name the fold empties (an alias of punctuation only) names nothing
    assert not V.name_in("", "The Tarxien temples lie in Paola.")
    assert not V.name_in("–", "The Tarxien temples lie in Paola.")
    ur = make_case(site=plan_site(name="Ur", aliases=()), card=None, subject_gate=gate(km=None))
    assert "sentence 1 names none of ['Ur']" in ur.detail("V6")


def test_v6_the_article_title_counts_only_for_a_strong_own_verdict() -> None:
    site = plan_site(name="Ħal Tarxien megaliths", aliases=())
    strong = make_case(site=site, card=None)
    assert "V6" not in strong.reasons()  # 'Tarxien Temples', the title, is in sentence 1
    weak = make_case(site=site, card=None, subject_gate=gate(km=None))
    assert "sentence 1 names none" in weak.detail("V6")


@pytest.mark.parametrize("over", [{"qid_match": False}, {"place_item": True}], ids=str)
def test_v6_a_title_without_its_qid_or_of_a_place_item_is_no_strong_own(over: dict) -> None:
    site = plan_site(name="Ħal Tarxien megaliths", aliases=())
    weak = make_case(site=site, card=None, subject_gate=gate(**over))
    assert "sentence 1 names none" in weak.detail("V6")


def _label_only(subject_gate: M.SubjectGate | None = None) -> Case:
    """Pilot 1's T8 case (Beacon Hill, Burghclere, Hampshire): neither the stored name nor the
    article title stands in sentence 1, but the pinned item's English label does."""
    site = plan_site(name="Ħal Tarxien megaliths", aliases=())
    case = retitle(make_case(site=site, subject_gate=subject_gate), "Ħal Tarxien (Paola)")
    return dataclasses.replace(case, witness=witness())


def test_v6_the_pinned_items_english_label_counts_for_a_strong_own_verdict() -> None:
    assert _label_only().run() == ()
    bare = dataclasses.replace(_label_only(), witness=V.Witness(meta=None, raw=None))
    assert "sentence 1 names none of ['Ħal Tarxien megaliths', 'Ħal Tarxien (Paola)']" in (
        bare.detail("V6")
    )
    assert "the Wikidata witness adds no name: no src.D is pinned" in bare.detail("V6")


@pytest.mark.parametrize(
    "over", [{"qid_match": False}, {"place_item": True}, {"km": None}], ids=str
)
def test_v6_the_label_counts_only_for_a_strong_own_verdict(over: dict) -> None:
    """The design: 'The article title and Wikidata labels count only for a strong own verdict
    (QID + coordinates + not place-level)' - a town's label ('Clare') names no site in it."""
    case = _label_only(subject_gate=gate(**over))
    assert "sentence 1 names none of ['Ħal Tarxien megaliths']" in case.detail("V6")


@pytest.mark.parametrize(
    ("raw", "over", "why"),
    [
        (
            witness_answer(),
            {"sha256_raw": "0" * 64},
            "the stored src.D answer is not its pinned sha256_raw",
        ),
        (witness_answer(qid="Q2"), {}, "src.D is not the stored item Q1353330"),
        (witness_answer(label=None), {}, "the item Q1353330 carries no English label"),
        (witness_answer(), {"id": "W"}, "src.D.meta names 'W'"),
    ],
    ids=["unpinned", "another-item", "no-english-label", "not-d"],
)
def test_v6_a_witness_that_is_not_the_pinned_stored_item_adds_no_label(
    raw: bytes, over: dict, why: str
) -> None:
    case = dataclasses.replace(_label_only(), witness=witness(raw, **over))
    assert "sentence 1 names none" in case.detail("V6")
    assert f"the Wikidata witness adds no name: {why}" in case.detail("V6")


@pytest.mark.parametrize(("name", "base"), NAME_BASE_CASES)
def test_v6_the_base_of_a_stored_name(name: str, base: str | None) -> None:
    assert V.name_base(name) == base


def _base_only(name: str, subject_gate: M.SubjectGate | None = None) -> Case:
    """Pilot 2's T8 case (Partiscum (Castra), Clare, Suffolk): neither the stored name, nor the
    article title, nor an item label stands in sentence 1 - only the stored name's base."""
    site = plan_site(name=name, aliases=())
    return retitle(make_case(site=site, subject_gate=subject_gate), "Ħal Tarxien (Paola)")


@pytest.mark.parametrize("name", ["Tarxien Temples (Paola)", "Tarxien Temples, Paola, Malta"])
def test_v6_the_stored_names_base_counts_for_a_strong_own_verdict(name: str) -> None:
    """The subject gate tied the article to the site (QID, coordinates, no place item), so the
    stored name without its disambiguator names the verified site."""
    assert _base_only(name).run() == ()


@pytest.mark.parametrize(
    "over", [{"qid_match": False}, {"place_item": True}, {"km": None}], ids=str
)
def test_v6_the_base_counts_only_for_a_strong_own_verdict(over: dict) -> None:
    """The Orolik/Clare trap: a town's article ('Clare' for 'Clare, Suffolk') is a place-level item,
    and its bare name then names the town, not the site."""
    case = _base_only("Tarxien Temples (Paola)", subject_gate=gate(**over))
    assert "sentence 1 names none of ['Tarxien Temples (Paola)']" in case.detail("V6")


def test_v6_reads_the_witness_the_store_pins(tmp_path: Path, write4: None) -> None:
    """S5 over a batch reads the site's `src.D` from the evidence store, as S1 left it."""
    batch_dir = write_batch(tmp_path, _label_only())
    assert V.verify_batch(batch_dir) == 0
    holds = M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)
    assert not [h for h in holds if h.reason is M.HoldReason.V6]
    assert V.read_witness(F.EvidenceStore(batch_dir / M.EVIDENCE_DIR), HELD_SITE) == V.Witness(
        meta=None, raw=None
    )


def test_v7_a_verdict_that_does_not_allow_the_lane_is_held() -> None:
    case = make_case(subject_gate=gate("shared"))
    assert "lane W needs 'own'" in case.detail("V7")


def test_v7_lane_s_publishes_only_name_bearing_or_matching_section_sentences() -> None:
    case = make_case(lane="S", picks=(W_PICKS[0], W_PICKS[1]), card=None)
    assert "sentence 2: lane S" in case.detail("V7")
    # a heading that carries a stored name: the section is the site's
    text = TEXT.replace("== History ==", "== History of Tarxien ==")
    under_own = make_case(lane="S", text=text, picks=(W_PICKS[0], Pick(S5, (), S5)), card=None)
    assert "V7" not in under_own.reasons()
    assert V.heading_before(TEXT, TEXT.index(S5)) == "History"


def _lane_s(name: str, heading: str, first: str, second: str) -> Case:
    text = f"{first}\n\n\n== {heading} ==\n{second}"
    site = plan_site(name=name, aliases=())
    picks = (Pick(first, (), first), Pick(second, (), second))
    return make_case(lane="S", text=text, picks=picks, card=None, site=site)


@pytest.mark.parametrize(
    ("name", "heading", "first", "second"),
    [
        # a sibling: the reverse direction read 'Nether Largie South Cairn' inside the stored name
        (
            "Nether Largie North Cairn, Kilmartin Glen",
            "Nether Largie South Cairn",
            "Nether Largie North Cairn, Kilmartin Glen, is a Bronze Age burial cairn in the "
            "Kilmartin valley of Argyll.",
            "The cairn was opened in 1864 and held a stone cist with a crouched burial and "
            "sherds of a beaker of the early Bronze Age.",
        ),
        # a generic heading inside the stored name
        (
            "Pyramid of Neferhetepes",
            "Pyramid",
            "The Pyramid of Neferhetepes is a ruined pyramid built for a queen of the Fifth "
            "Dynasty at Saqqara.",
            "The core was built of local limestone blocks and cased with fine white limestone "
            "from the Tura quarries across the river.",
        ),
        # a stored name that only carries the heading: 'History' in 'Tarxien history'
        (
            "Tarxien history",
            "History",
            "Tarxien history is the story of four megalithic structures near the village of "
            "Tarxien in Malta.",
            S5,
        ),
    ],
)
def test_v7_a_heading_counts_only_when_it_carries_the_stored_name(
    name: str, heading: str, first: str, second: str
) -> None:
    """C1: one direction only, token by token - the stored name (or an alias) inside the heading,
    as S2's pool reads it; never the heading inside the name."""
    assert "sentence 2: lane S, no stored name and no matching section" in _lane_s(
        name, heading, first, second
    ).detail("V7")


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


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"title": "Wikipedia: Paola"}, "is titled 'Wikipedia: Paola', not 'Wikipedia: <title>'"),
        ({"domain": "evil.example"}, "names the domain 'evil.example' of another URL"),
        ({"license": M.Licence.CC0}, "[1] carries licence CC0, its source another"),
    ],
    ids=["title", "domain", "licence"],
)
def test_v8_a_citation_names_its_article_host_and_licence(over: dict, message: str) -> None:
    case = make_case()
    citations = (dataclasses.replace(case.assembly.citations[0], **over),)
    assert message in case.replace(citations=citations).detail("V8")


def test_v8_the_citation_domain_is_the_host_without_www(licences: None) -> None:
    """The production form (`api/main.py`'s seeded citations; S4's `assemble.domain_of`):
    `https://www.heritagemalta.mt/...` is cited as `heritagemalta.mt`."""
    case = make_generated_case("R")
    assert R_URL.startswith("https://www.") and case.assembly.citations[0].domain == (
        "heritagemalta.mt"
    )
    assert "V8" not in case.reasons()
    www = (dataclasses.replace(case.assembly.citations[0], domain="www.heritagemalta.mt"),)
    assert "names the domain 'www.heritagemalta.mt'" in case.replace(citations=www).detail("V8")


def test_v8_a_citation_no_marker_cites_is_held() -> None:
    case = make_case()
    extra = dataclasses.replace(case.assembly.citations[0], n=2)
    held = case.replace(citations=(*case.assembly.citations, extra))
    assert "citations [2] are cited by no marker" in held.detail("V8")


def test_v8_the_citations_are_numbered_from_one() -> None:
    case = make_case()
    citations = (dataclasses.replace(case.assembly.citations[0], n=2),)
    assert "the citations are numbered [2], not 1..1" in case.replace(citations=citations).detail(
        "V8"
    )


def test_v8_a_sentence_carries_exactly_one_marker() -> None:
    """Lane T: V3 does not rebuild a translation, so only V8 counts the markers of a sentence."""
    case = make_generated_case("T")
    case = _regenerate(case, 1, EN2.replace("statues,", "statues [1],"))
    assert "sentence 2 carries 2 markers" in case.detail("V8")


def test_v8_a_sentence_is_marked_with_its_provenance_number() -> None:
    """Lane T: sentence 2 marked [2] while its provenance says [1], with a citation [2] that
    exists, so no other marker check notices."""
    case = make_generated_case("T")
    second = dataclasses.replace(case.assembly.citations[0], n=2)
    marked = case.assembly.description.replace("spirals [1].", "spirals [2].")
    held = republish(case, marked).replace(citations=(*case.assembly.citations, second))
    assert "sentence 2 is marked [2], provenance says [1]" in held.detail("V8")


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


def test_v10_a_card_with_parentheses_or_a_marker_is_held() -> None:
    card = "The site was excavated in 1915 by Themistocles Zammit (the director of the museum)."
    case = make_case(card=card, card_items=((1, (T2,)),))
    assert "the card carries parentheses" in case.detail("V10")
    sentence = "The Tarxien Temples [3] are a complex of four megalithic structures near Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "the card carries a citation marker" in case.detail("V10")


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


def test_v10_a_card_that_names_a_nationality_is_held() -> None:
    """Pilot 2 (T4/T6): 'a Danish hill' (Agri Bavnehøj) and 'the first Greek site' (Bassae) passed
    V10, which knew country names only. The design's card rule is 'no country value, alias or
    demonym (country_lookup vocabulary plus a demonym table)'; the table is
    `country_lookup.ISO_TO_DEMONYMS`, any country's, and an ancient culture's use of a modern
    country's adjective ('Greek temple') is held too - the safe reading."""
    sentence = "The Tarxien Temples are a complex of four Maltese megalithic structures near Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "names a nationality: ['Maltese']" in case.detail("V10")
    assert [h.scope for h in case.run() if h.reason is M.HoldReason.V10] == [M.HoldScope.CARD]
    bavnehoj = (
        "Agri Bavnehøj is a Danish hill, located in the Mols Bjerge National Park on Djursland."
    )
    assert V.card_demonyms(bavnehoj) == ["Danish"]
    bassae = "Bassae was the first Greek site to be inscribed on the World Heritage List."
    assert V.card_demonyms(bassae) == ["Greek"]
    assert V.card_demonyms("A Greek temple built by the Greeks and an Englishman's map.") == [
        "Greek",
        "Greeks",
        "Englishman",
    ]
    assert V.card_demonyms("The Egyptian and Roman builders of the Etruscan wall.") == ["Egyptian"]
    # a demonym is a proper noun, whole word: no hit inside a word or in lower case
    assert V.card_demonyms("The danish pastry and the Greekness of the old town.") == []
    assert V.card_demonyms("A Hellenistic stoa of the Mesoamerican ball court.") == []
    assert V.card_demonyms("THE MESOAMERICAN BALL COURT OF THE GREEKS") == ["GREEKS"]


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


@pytest.mark.parametrize(
    ("lane", "card", "index"),
    [
        ("R", Q1, 0),  # the restricted page's own wording, verbatim
        ("T", FR2, 1),  # the French source sentence
        ("T", EN2, 1),  # the English translation: still no card in lane T
    ],
)
def test_v10_lanes_t_and_r_build_no_card(licences: None, lane: str, card: str, index: int) -> None:
    """C3: lanes T and R publish text that is not the source's, so no offered span applies and no
    card is built (the design's 'extractive condensation'); a card there is held, whatever it
    says - before, V10 passed exactly the verbatim restricted or French one."""
    case = make_generated_case(lane)
    record = M.Card(items=(M.CardItem(sentence=index, drop=()),), text_sha256=sha(card))
    held = reprovenance(case, card=record).replace(card=card)
    holds = [h for h in held.run() if h.reason is M.HoldReason.V10]
    assert [h.scope for h in holds] == [M.HoldScope.CARD]
    assert f"lane {lane} builds no card" in holds[0].detail


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


def test_v11_lane_t_may_state_only_what_its_trimmed_sentence_says() -> None:
    """A translation restoring the year a drop took out of its source sentence is held by V11
    (V4 holds the drop itself: a lane-T sentence offers no span)."""
    case = make_generated_case("T")
    first = case.assembly.provenance.sentences[0]
    low = FR_TEXT.index(" et fouillé en 1915")
    trimmed = dataclasses.replace(first, drop=((low, low + len(" et fouillé en 1915")),))
    held = reprovenance(case, sentences=(trimmed, *case.assembly.provenance.sentences[1:]))
    assert "the numbers ['1915'] are not in its quote" in held.detail("V11")


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


def test_v12_the_citations_written_are_the_assemblys() -> None:
    case = make_case()
    written = [dict(case.new_raw_data[M.CITATIONS_KEY][0], title="Wikipedia: Paola")]
    case.new_raw_data[M.CITATIONS_KEY] = written
    assert "description_citations is not the assembly's citations" in case.detail("V12")


def test_v13_a_card_without_its_provenance_card_is_held() -> None:
    """The run's card published while the provenance says there is none, and the reverse."""
    case = make_case()
    no_card = case.replace(card=None)
    holds = [h for h in no_card.run() if h.reason is M.HoldReason.V13]
    assert [(h.scope, h.detail) for h in holds] == [
        (M.HoldScope.CARD, "the card and provenance.card disagree on whether there is one")
    ]


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


def test_v14_a_stored_country_of_comma_parts_is_read_part_by_part() -> None:
    """C7: the 8 Rapa Nui sites store 'Chile, Easter Island', which is no single NAME_TO_ISO name;
    a location sentence naming Easter Island or Chile agrees with it, Italy does not."""
    site = plan_site(country="Chile, Easter Island")
    sentence = (
        "The Tarxien Temples lie on Easter Island, a Polynesian island in the Pacific Ocean that "
        "belongs to Chile."
    )
    text = f"{sentence} {S2} {S3}"
    picks = (Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2])
    assert "V14" not in make_case(text=text, picks=picks, card=None, site=site).reasons()
    italy = sentence.replace("Easter Island", "Sicily").replace("Chile", "Italy")
    text = f"{italy} {S2} {S3}"
    picks = (Pick(italy, (), italy), W_PICKS[1], W_PICKS[2])
    held = make_case(text=text, picks=picks, card=None, site=site)
    assert "places the site in Italy, the stored country is 'Chile, Easter Island'" in (
        held.detail("V14")
    )


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


def test_the_batch_holds_a_site_that_cites_outside_its_lanes_sources(
    tmp_path: Path, write4: None
) -> None:
    """S1b assigned the German article; the assembly translated the French one."""
    batch_dir = write_batch(tmp_path, make_generated_case("T"), lane="T", sources=("T.de",))
    assert V.verify_batch(batch_dir) == 0
    holds = M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)
    assert [h.detail for h in holds] == ["cites ['T.fr'], outside the lane's sources ['T.de']"]


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
