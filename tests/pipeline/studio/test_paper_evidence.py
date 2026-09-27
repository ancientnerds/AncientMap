from __future__ import annotations

import copy

from pipeline.lyra import theo_publishing
from pipeline.studio.paper import evidence, numbering
from pipeline.studio.paper.workspace import parse_dossier
from tests.pipeline.studio import fixtures as fx

TITLE = fx.META["title"]
LIVE_QUOTE = "Roman engineers moved the largest blocks on sledges."


def _setup(tmp_path):
    ws = fx.make_workspace(tmp_path)
    built = numbering.number(ws)
    return built.markdown, parse_dossier(fx.dossier_gz_bytes()), set(built.registry.sources)


def _problems(entries, report, dossier, cited, texts=None, *, after_claim_check=True):
    texts = dossier.texts if texts is None else texts
    return evidence.evidence_problems(
        entries, report, TITLE, dossier, cited, texts, after_claim_check=after_claim_check
    )


def test_quote_matching_ignores_whitespace_only():
    assert evidence.quote_in_text("weighs  about\n1000 tons", "It weighs about 1000 tons.")
    assert not evidence.quote_in_text("weighs about 1,000 t", "It weighs about 1000 tons.")
    assert not evidence.quote_in_text("   ", "anything")


def test_fixture_evidence_is_valid(tmp_path):
    report, dossier, cited = _setup(tmp_path)
    assert _problems(fx.EVIDENCE, report, dossier, cited) == []
    assert _problems(fx.EVIDENCE, report, dossier, cited, after_claim_check=False) == []


def test_the_publish_gates_rule_comes_first_then_the_quotes(tmp_path):
    report, dossier, cited = _setup(tmp_path)
    bad = copy.deepcopy(fx.EVIDENCE)
    bad[0]["quote"] = "The Stone weighs 2000 t."
    bad[1]["quote_source_id"] = fx.S1
    assert _problems(bad, report, dossier, cited) == [
        "ev-02: quote_source_id is not one of source_ids"
    ]
    bad[1]["quote_source_id"] = fx.EVIDENCE[1]["quote_source_id"]
    assert _problems(bad, report, dossier, cited) == [
        "ev-01: quote does not occur verbatim in texts/aaaaaaaaaaa1.txt"
    ]


def test_only_supported_evidence_may_be_published(tmp_path):
    report, dossier, cited = _setup(tmp_path)
    partly = copy.deepcopy(fx.EVIDENCE)
    partly[1]["verdict"] = "partly"
    assert _problems(partly, report, dossier, cited) == [
        "ev-02: verdict is 'partly'; only 'supported' may be published"
    ]


def test_uncited_unknown_and_textless_sources_are_refused(tmp_path):
    report, dossier, cited = _setup(tmp_path)
    bad = copy.deepcopy(fx.EVIDENCE[:1])
    bad[0]["source_ids"] = [fx.S6]
    bad[0]["quote_source_id"] = fx.S6
    assert _problems(bad, report, dossier, cited) == [
        f"ev-01: source ids the paper does not cite: ['{fx.S6}']",
        f"ev-01: {fx.S6} has no text (missing); quote a source that has one",
    ]
    bad[0]["source_ids"] = ["eeeeeeeeeee5"]
    bad[0]["quote_source_id"] = "eeeeeeeeeee5"
    assert _problems(bad, report, dossier, cited) == [
        "ev-01: source ids not in the dossier: ['eeeeeeeeeee5']"
    ]


def test_a_tdm_reserved_quote_is_checked_against_the_live_text(tmp_path):
    report, dossier, cited = _setup(tmp_path)
    entry = copy.deepcopy(fx.EVIDENCE[:1])
    entry[0]["source_ids"] = [fx.S1, fx.S4]
    entry[0]["quote_source_id"] = fx.S4
    entry[0]["quote"] = LIVE_QUOTE
    cited = cited | {fx.S4}
    # claims-export: the quote of a TDM-reserved source is checked after its live read
    assert _problems(entry, report, dossier, cited, after_claim_check=False) == []
    assert _problems(entry, report, dossier, cited) == [
        f"ev-01: {fx.S4} is TDM-reserved and the claim check has not saved its live text "
        f"(claims_check/live/{fx.S4}.txt): run the claim check first"
    ]
    live = {**dossier.texts, fx.S4: f"Chapter 2. {LIVE_QUOTE} More text."}
    assert _problems(entry, report, dossier, cited, live) == []
    live[fx.S4] = "Another page altogether."
    assert _problems(entry, report, dossier, cited, live) == [
        f"ev-01: quote does not occur verbatim in claims_check/live/{fx.S4}.txt"
    ]


def test_a_page_anchor_issue_still_runs_the_quote_checks(tmp_path, monkeypatch):
    report, dossier, cited = _setup(tmp_path)

    def acceptance(report, title, entries):
        return {"ev-01": 1, "ev-02": 2}, ["paper page: ev-02 matches 2 paragraphs"]

    monkeypatch.setattr(theo_publishing, "check_evidence_anchors", acceptance)
    bad = copy.deepcopy(fx.EVIDENCE)
    bad[0]["quote"] = "The Stone weighs 2000 t."
    assert _problems(bad, report, dossier, cited) == [
        "paper page: ev-02 matches 2 paragraphs",
        "ev-01: quote does not occur verbatim in texts/aaaaaaaaaaa1.txt",
    ]


def test_shape_ids_and_anchors(tmp_path):
    report, dossier, cited = _setup(tmp_path)
    assert _problems([], report, dossier, cited) == ["evidence.json must be a non-empty list"]
    extra = copy.deepcopy(fx.EVIDENCE[:1])
    extra[0]["note"] = "x"
    assert _problems(extra, report, dossier, cited) == ["ev-01: unknown keys ['note']"]
    dup = copy.deepcopy([fx.EVIDENCE[0], fx.EVIDENCE[0]])
    assert _problems(dup, report, dossier, cited) == ["ev-01: duplicate id"]
    moved = copy.deepcopy(fx.EVIDENCE[:1])
    moved[0]["anchor_text"] = "the block rests where the workers left it and the stone"
    problems = _problems(moved, report, dossier, cited)
    assert problems and "matches" in problems[0] and "paragraphs (needs exactly 1)" in problems[0]
