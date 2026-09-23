"""Do lanes T and R take exactly one answer shape, tie every restated sentence to a quote code
found in its page, and hold everything else?

Work item WB-B3 (`phase4/translate_stage.py`, `phase4/restricted_stage.py`). The model is a scripted
`ModelRunner`. The silent mistakes: a translation line for a sentence that was never shown, a
missing one read as "nothing to translate", a quote the page does not carry, a url the prompt never
showed, two quotes of one page that overlap (provenance would refuse them later, after the call was
paid), and a page that cannot be cited at all reaching a paid call.
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
from phase4 import restricted_stage as RS  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402
from phase4 import translate_stage as TS  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402

FR_TEXT = (
    "Le temple de pierre fut construit vers 2500 av. J.-C. par des paysans, selon les fouilles. "
    "Il fut fouillé par des archéologues en 1911 et en 1954.\n"
)
FR = X.wiki_doc("T.fr", FR_TEXT, title="Temple de pierre", host="fr.wikipedia.org")


def _t_batch(tmp_path: Path) -> Path:
    setup = X.SiteSetup(site=X.plan_site("site-t"), lane=M.Lane.T, sources={"T.fr": (FR, FR_TEXT)})
    batch_dir = X.make_batch(tmp_path, [setup])
    runner = X.ScriptedRunner({("site-t", "select"): "DESC: T.fr1 -t1\nDESC: T.fr2\nCARD: T.fr2"})
    assert SEL.select_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    return batch_dir


# --------------------------------------------------------------------------------- lane T


def test_the_translator_sees_the_trimmed_sentences_numbered_in_source_order(tmp_path: Path) -> None:
    batch_dir = _t_batch(tmp_path)
    answer = "T1: The stone temple was built around 2500 BC by farmers.\nT2: It was dug in 1911."
    runner = X.ScriptedRunner({("site-t", "translate"): answer})
    assert TS.translate_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    (call,) = runner.calls
    assert (
        "T1: Le temple de pierre fut construit vers 2500 av. J.-C. par des paysans." in call.prompt
    )
    assert "T2: Il fut fouillé par des archéologues en 1911 et en 1954." in call.prompt
    assert ", selon les fouilles" not in call.prompt  # the dropped span is not translated
    assert B.read_translations(batch_dir)["site-t"] == {
        "T.fr1": "The stone temple was built around 2500 BC by farmers.",
        "T.fr2": "It was dug in 1911.",
    }


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        ("T1: One sentence only.", "no translation for ['T2']"),
        ("T1: One.\nT2: Two.\nT3: Three.", "T3 names no shown sentence"),
        ("T1: One.\nT1: Again.\nT2: Two.", "T1 is answered twice"),
        ("T1: One.\nT2: No final stop", "T2 does not end"),
        ("Here you go:\nT1: One.\nT2: Two.", "not `T<i>: <sentence>`"),
    ],
)
def test_a_translation_the_contract_refuses_holds_the_site(
    tmp_path: Path, answer: str, detail: str
) -> None:
    batch_dir = _t_batch(tmp_path)
    runner = X.ScriptedRunner({("site-t", "translate"): answer})
    assert TS.translate_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    (hold,) = X.holds_of(batch_dir)
    assert hold.reason is M.HoldReason.TRANSLATION_REFUSED and detail in hold.detail
    assert B.read_translations(batch_dir) == {}


def test_a_translated_site_assembles_as_generated_text(tmp_path: Path) -> None:
    batch_dir = _t_batch(tmp_path)
    answer = "T1: The stone temple was built around 2500 BC by farmers.\nT2: It was dug in 1911."
    TS.translate_batch(
        batch_dir,
        ledger=tmp_path / "L.jsonl",
        runner=X.ScriptedRunner({("site-t", "translate"): answer}),
    )
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir) == 0
    (assembly,) = M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly)
    assert assembly.description == (
        "The stone temple was built around 2500 BC by farmers [1]. It was dug in 1911 [1]."
    )
    assert assembly.provenance.ai is M.AiMark.GENERATED and assembly.card is None


def test_an_unreadable_translation_stream_holds_and_a_dead_process_stops(tmp_path: Path) -> None:
    batch_dir = _t_batch(tmp_path)
    runner = X.ScriptedRunner({("site-t", "translate"): MS.UnreadableStream("empty")})
    assert TS.translate_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    assert X.holds_of(batch_dir)[0].reason is M.HoldReason.MODEL_STREAM_UNREADABLE
    other = _t_batch(tmp_path / "second")
    dead = X.ScriptedRunner({("site-t", "translate"): MS.ModelCallFailed("timed out")})
    assert TS.translate_batch(other, ledger=tmp_path / "L.jsonl", runner=dead) == 2
    report = json.loads((other / B.TRANSLATE_REPORT).read_text(encoding="utf-8"))
    assert report["error"] == "timed out"


# --------------------------------------------------------------------------------- lane R

PAGE_ONE = (
    "Welcome to the heritage page. The mound was raised in the Bronze Age by local farmers. "
    "It is\nsurrounded by a ditch that is now filled in."
)
PAGE_TWO = "Notes: the stone circle on top of the mound has nine stones, three of them fallen."
URL_ONE = "https://www.example.org/mound"
URL_TWO = "https://example.net/circle"


def _r_setup(one_title: str | None = "The Mound", pages: int = 2) -> X.SiteSetup:
    sources = {"R1": (X.page_doc("R1", PAGE_ONE, url=URL_ONE, title=one_title), PAGE_ONE)}
    if pages == 2:
        sources["R2"] = (X.page_doc("R2", PAGE_TWO, url=URL_TWO, title="Circle notes"), PAGE_TWO)
    return X.SiteSetup(site=X.plan_site("site-r"), lane=M.Lane.R, sources=sources)


RESTATED = (
    f"S1: Farmers built the mound in the Bronze Age.\n"
    f'Q1: {URL_ONE} - "The mound was raised in the Bronze Age by local farmers."\n'
    f"S2: Nine stones stand on it, and three have fallen.\n"
    f'Q2: {URL_TWO} - "the stone circle on top of the mound has nine stones, three of them fallen"\n'
    f"S3: A ditch surrounds it.\n"
    f"Q3: {URL_ONE} - “It is surrounded by a ditch”\n"
)


def test_a_quote_is_located_across_case_spacing_and_quote_marks() -> None:
    assert RS.locate_quote("it is surrounded by a ditch", PAGE_ONE) == (
        PAGE_ONE.index("It is"),
        PAGE_ONE.index("a ditch") + len("a ditch"),
    )
    start, end = RS.locate_quote("the MOUND was  raised", PAGE_ONE)
    assert PAGE_ONE[start:end] == "The mound was raised"
    assert RS.locate_quote("the mound was built", PAGE_ONE) is None


def test_every_restated_sentence_carries_its_quote_range(tmp_path: Path) -> None:
    batch_dir = X.make_batch(tmp_path, [_r_setup()])
    runner = X.ScriptedRunner({("site-r", "restricted"): RESTATED})
    assert RS.restricted_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    (call,) = runner.calls
    assert f'<source id="R1" url="{URL_ONE}" title="The Mound">' in call.prompt
    restated = B.read_restatements(batch_dir)["site-r"]
    texts = {"R1": PAGE_ONE, "R2": PAGE_TWO}
    assert [texts[r.src][r.start : r.end] for r in restated] == [
        "The mound was raised in the Bronze Age by local farmers.",
        "the stone circle on top of the mound has nine stones, three of them fallen",
        "It is\nsurrounded by a ditch",
    ]
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.POOLS_FILE, [])
    B.write_text_atomic(batch_dir / B.SELECTIONS_FILE, "")
    assert A.assemble_batch(batch_dir) == 0
    (assembly,) = M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly)
    assert assembly.description == (
        "Farmers built the mound in the Bronze Age [1]. A ditch surrounds it [1]. "
        "Nine stones stand on it, and three have fallen [2]."
    )


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        ("S1: Only one pair.\nQ1: " + URL_ONE + ' - "The mound was raised"', "2-4 S/Q pairs"),
        (RESTATED.replace("Q2:", "Q9:"), "numbered"),
        (RESTATED.replace(URL_TWO, "https://elsewhere.org/x"), "the prompt did not show"),
        (RESTATED.replace("nine stones", "ten stones"), "does not occur"),
        (RESTATED.replace("S3: A ditch surrounds it.", "S3: A ditch surrounds it"), "does not end"),
        (
            RESTATED.replace("It is surrounded by a ditch", "local farmers. It is surrounded"),
            "overlap",
        ),
        ("Sure! Here they are:\n" + RESTATED.split("S3:")[0], "lines"),
    ],
)
def test_a_restatement_the_contract_refuses_holds_the_site(
    tmp_path: Path, answer: str, detail: str
) -> None:
    batch_dir = X.make_batch(tmp_path, [_r_setup()])
    runner = X.ScriptedRunner({("site-r", "restricted"): answer})
    assert RS.restricted_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    (hold,) = X.holds_of(batch_dir)
    assert hold.reason is M.HoldReason.RESTATEMENT_REFUSED and detail in hold.detail
    assert B.read_restatements(batch_dir) == {}


def test_a_page_that_cannot_be_cited_holds_before_any_call(tmp_path: Path) -> None:
    batch_dir = X.make_batch(tmp_path, [_r_setup(one_title=None)])
    runner = X.ScriptedRunner({})
    assert RS.restricted_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    assert runner.calls == []
    (hold,) = X.holds_of(batch_dir)
    assert "cannot be cited" in hold.detail


def test_pages_over_the_evidence_bound_hold_before_any_call(tmp_path: Path) -> None:
    big = "The mound is old. " * (MS.MAX_EVIDENCE_CHARS // 18 + 10)
    setup = X.SiteSetup(
        site=X.plan_site("site-r"),
        lane=M.Lane.R,
        sources={"R1": (X.page_doc("R1", big, url=URL_ONE), big)},
    )
    batch_dir = X.make_batch(tmp_path, [setup])
    runner = X.ScriptedRunner({})
    assert RS.restricted_batch(batch_dir, ledger=tmp_path / "L.jsonl", runner=runner) == 0
    assert runner.calls == []
    assert "no bounded prompt" in X.holds_of(batch_dir)[0].detail
