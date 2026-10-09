"""Lane WN (owner decision "Neu aus Webquellen", 2026-10-01): a site left without a description gets a
short one an agent wrote only from sentences it supports with verbatim quotes from reputable pages,
verified exactly as lane WC verifies a kept sentence, AI-marked (lane N).

The frozen texts (`wc/prompts_sonnet.py`), the write answer's parser (`wc/answers.py`), the run's
commands (`wc/cli.py export --wn`, `check-answer`, `import`, `build`, the judge, `pilot_approval`) and
the data the writer reads (`phase4/wc4.py`, `model4.WebProvenance`). Nothing here opens a socket,
calls a model or touches a database: the pages are served from a dict (`wc_fixtures.FakeClient`).
The writer's side is in `test_wn_write.py`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402
from wc import answers as A  # noqa: E402
from wc import cli  # noqa: E402
from wc import prompts as P  # noqa: E402
from wc import prompts_sonnet as P2  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.wc_fixtures import wiki_cache  # noqa: E402,F401 - the autouse fixture


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------ the frozen texts
#: Pinned 2026-10-01 (CHECK_QUESTION_LISTED re-pinned the same day, before any list run was exported:
#: it gained the `{defects}` slot, and the three DEFECT texts are new). A changed text makes every answer exported under it stale: a change is a new
#: pin and a new export, never an edit under a running round.
PINS = {
    "WRITE_QUESTION": "69c6d6a71dbe5c414b64a2421b2d4bb3eac499c5a050e16266409df7ffc88a44",
    "WRITE_BRIEF": "d4759eeca19bf0c9e722c751d268784090f403c0091be1f3c73a6d890e3ea3b9",
    "VERIFY_QUESTION_WN": "6a1e020d54c09377dcfba34a70b5c317bb9b7ebe2839e09ed716e227e06b5537",
    "JUDGE_QUESTION_WN": "75c58553ed4a650834f9052672b3a93225c2dda73f1d5914870aefb64b4df2e4",
    "CHECK_QUESTION_LISTED": "2bcf9adf92932f5538e8a02ebe85403efb56670d8f852b7f5fef97706cb16fdf",
    "DEFECTS_HEAD": "b77770cfe817644be5fd3461a2e95a9a4d490662fd6daf2b9dc60453fe7e3ae1",
    "DEFECTS_TAIL": "abeb2651235a2fc721231a033ca0f180aefb83b0ce52077129be72460614e3a3",
    "DEFECT_LINE": "b02547a1450c20f6f607365700a1c389b2b8a4d3460af27add1d7608e6a7c7ff",
    "NO_TRIM": "fd0ac89cf5cd7e0cb56da9e52e34f240990d5a2deffadff61021672d4ca39203",
    "ADVERSARIAL_OPENING": "975eb4b55583d1abebd9a6832b733198ea968552ebd440ae264712f8fd2c7009",
    "CHECK_QUESTION_ADVERSARIAL": "fe49e8eb98deebb69e62cb3783bc9637c4f0b42bef8f04a13a0d0a123e7c90c8",
    "ORIGINS": "ec130df29b532f3afcf28291a207a08e9fd9f404e9be198f6db29509ace36c3e",
}


def _measured() -> dict[str, str]:
    measured = {name: _sha(getattr(P2, name)) for name in PINS if name != "ORIGINS"}
    return {**measured, "ORIGINS": _sha(json.dumps(P2.ORIGINS, sort_keys=True))}


def test_the_new_templates_are_pinned() -> None:
    assert _measured() == PINS


def test_the_old_templates_are_the_ones_the_runs_in_flight_were_exported_under() -> None:
    """`prompts.py` is not touched: the exported rounds of the runs in flight rebuild their prompts
    from it byte for byte (`prompt_sha256`). The old pins are `test_wc.py`'s; this holds the new
    texts apart from them."""
    assert P.VERIFY_QUESTION != P2.VERIFY_QUESTION_WN and P.JUDGE_QUESTION != P2.JUDGE_QUESTION_WN
    assert P.CHECK_QUESTION != P2.CHECK_QUESTION_LISTED
    assert "{origin}" in P2.CHECK_QUESTION_LISTED and "{origin}" not in P.CHECK_QUESTION
    assert "March 2026 by an AI enrichment chain and is shown" in P.CHECK_QUESTION
    assert "March 2026 by an AI enrichment chain and is shown" not in P2.CHECK_QUESTION_LISTED


def test_a_derived_text_refuses_an_old_template_that_changed_under_it() -> None:
    with pytest.raises(ImportError, match="re-derive"):
        P2._derive("a text", ("not in the text", "x"))
    assert P2._derive("a text", ("text", "word")) == "a word"


def test_the_write_brief_takes_model_role_and_family_from_the_role_registry() -> None:
    """2026-10-09 (owner decision D6): no brief names a model of its own - the printed
    `opus_handoff.py answer` command carries the role's (`cli.brief`, `test_wc_roles.py`)."""
    assert "--model {model} --role {role}" in P2.WRITE_BRIEF
    assert "You are {family} writer" in P2.WRITE_BRIEF
    assert "claude-" not in P2.WRITE_BRIEF and "Sonnet" not in P2.WRITE_BRIEF


# ------------------------------------------------------------------------------ the write answer
def test_a_good_write_answer_parses_into_sentences_that_a_check_answer_could_be() -> None:
    parsed = A.parse_write(WX.good(WX.SITE_N), site_id=WX.SITE_N)
    assert [s.text for s in parsed.sentences] == [WX.W1, WX.W2, WX.W3]
    check = parsed.as_check()
    assert [(a.n, a.verdict, a.remove, a.reason) for a in check] == [
        (1, WC4.Verdict.KEEP, None, None),
        (2, WC4.Verdict.KEEP, None, None),
        (3, WC4.Verdict.KEEP, None, None),
    ]
    assert check[0].quotes == parsed.sentences[0].quotes


def test_a_write_answer_may_give_no_sentence_and_the_site_stays_empty() -> None:
    parsed = A.parse_write(WX.nothing(WX.SITE_N), site_id=WX.SITE_N)
    assert parsed.sentences == () and parsed.as_check() == () and parsed.note


def _answer(*sentences: dict, site: str = WX.SITE_N, **extra) -> str:
    return json.dumps({"site_id": site, "sentences": list(sentences), "note": "n", **extra})


def _sentence(text: str = WX.W1, *quotes: dict, note: str = "n") -> dict:
    return WX.sentence(text, *(quotes or (WX.Q_W1,)), note=note)


def _two(first: dict, second: dict | None = None) -> str:
    return _answer(first, second or _sentence(WX.W2, WX.Q_W2))


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (_answer(_sentence()), "1 sentences; write 2 to 6"),
        (
            _answer(
                *[
                    _sentence(f"Sentence number {n} about the Tarxien Temples of Malta.")
                    for n in range(7)
                ]
            ),
            "7 sentences; write 2 to 6",
        ),
        (_two(_sentence("The Tarxien Temples are in Malta [1].")), "citation marker"),
        (_two(_sentence("Too short.")), "characters; a sentence has 25-400"),
        (_two(_sentence("x" * 401 + ".")), "characters; a sentence has 25-400"),
        (
            _two(_sentence("the Tarxien Temples lie in the town of Tarxien on Malta.")),
            "does not open with a capital",
        ),
        (
            _two(_sentence("The Tarxien Temples lie in the town of Tarxien on Malta")),
            "does not end with",
        ),
        (
            _two(_sentence("It lies in the town of Tarxien on the island of Malta.")),
            "opens with a pronoun",
        ),
        (
            _two(_sentence("These are in the town of Tarxien on the island of Malta.")),
            "opens with a pronoun",
        ),
        (
            _two(_sentence("The temples lie in Tarxien. They are old and large.")),
            "it is 2 sentences",
        ),
        (
            _two(
                _sentence(WX.W1, WX.Q_W1),
                _sentence(WX.W1.upper().replace("TARXIEN", "Tarxien"), WX.Q_W1),
            ),
            "written twice",
        ),
        (_two(WX.sentence(WX.W1)), "at least one quote"),
        (_two({"text": WX.W1, "quotes": [WX.Q_W1]}), "carries"),
        (
            _two(_sentence(WX.W1, FX.quote("https://www.ancientnerds.com/x", "x" * 30))),
            "never a source",
        ),
        (_two(_sentence(WX.W1, FX.quote(FX.WIKI, "too short"))), "a quote of 9 characters"),
        (_answer(_sentence(), _sentence(WX.W2, WX.Q_W2), site="0" * 36), "names site"),
        (_answer(_sentence(), _sentence(WX.W2, WX.Q_W2), extra="x"), "are not"),
        (_two(_sentence(WX.W1, WX.Q_W1, note="")), "note is not a non-empty string"),
    ],
)
def test_every_rule_of_the_write_answer_refuses_a_broken_one(answer: str, message: str) -> None:
    with pytest.raises(A.AnswerError, match=message):
        A.parse_write(answer, site_id=WX.SITE_N)


def test_a_sentence_may_not_paste_its_quote() -> None:
    """A sentence is its own words: 12 words or more shared with one of its quotes is a paste (an
    uncredited copy of a CC BY-SA sentence). Eleven shared words and a paraphrase pass."""
    long_quote = FX.quote(
        FX.WIKI,
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta. They date to "
        "approximately 3150 BC.",
    )
    pasted = (
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta; they date to "
        "approximately 3150 BC, say archaeologists."
    )
    with pytest.raises(A.AnswerError, match="shares a run of 12 words"):
        A.parse_write(_two(_sentence(pasted, long_quote)), site_id=WX.SITE_N)
    assert A.shared_run(pasted, long_quote["quote"]) and not A.shared_run(pasted, WX.Q_W1["quote"])
    assert A.shared_run(pasted, WX.Q_W1["quote"], 8)
    assert not A.shared_run(pasted, long_quote["quote"], 17)
    assert not A.shared_run("A short text.", "A short text.")  # fewer words than the window
    A.parse_write(_two(_sentence(WX.W1, long_quote)), site_id=WX.SITE_N)


def test_the_sentences_must_split_back_into_themselves_as_one_text(monkeypatch) -> None:
    """Each sentence is one sentence alone, but the description they compose must split into exactly
    them: a splitter that runs two of them together (it does not know the abbreviation one ends on)
    would leave the verifier and the writer with other sentences than the page shows."""
    real = WC4.checked_sentences

    def merging(text: str) -> tuple[str, ...]:
        return (text,) if WX.W1 in text and WX.W2 in text else real(text)

    monkeypatch.setattr(WC4, "checked_sentences", merging)
    with pytest.raises(A.AnswerError, match="do not split back into themselves"):
        A.parse_write(_two(_sentence(WX.W1, WX.Q_W1), _sentence(WX.W2, WX.Q_W2)), site_id=WX.SITE_N)
    monkeypatch.undo()
    A.parse_write(_two(_sentence(WX.W1, WX.Q_W1), _sentence(WX.W2, WX.Q_W2)), site_id=WX.SITE_N)


# ------------------------------------------------------------------------------ the population
def _pop(rows, **kw):
    return cli.population(rows, excluded=set(), earlier=set(), kind=cli.KIND_WN, **kw)


def test_the_population_of_lane_wn_is_the_curated_sites_without_a_description() -> None:
    other = {"title_es": "x"}
    rows = [
        WX.wn_row(WX.SITE_N),
        WX.wn_row(WX.SITE_BLANK, "  \n "),
        WX.wn_row(WX.SITE_EMPTY, raw_data=other),
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)),
        FX.row(FX.SITE_B, None, scope_status="retired"),
        FX.row(FX.SITE_C, None, raw_data={WC4.CHECK_KEY: {}}),
    ]
    asked, listed = _pop(rows)
    assert [(e["site_id"], e["marking"], e["sentences"]) for e in asked] == [
        (WX.SITE_N, "none", []),
        (WX.SITE_BLANK, "none", []),
        (WX.SITE_EMPTY, "none", []),
    ]
    assert listed == {
        "has-description": [FX.SITE_A],
        "retired": [FX.SITE_B],
        "stale-keys": [FX.SITE_C],
    }
    assert asked[2]["plan_site"]["raw_data"] == other


def test_a_wn_chunk_leaves_the_sites_of_an_earlier_unwritten_chunk_and_the_excluded_ones() -> None:
    rows = [WX.wn_row(WX.SITE_N), WX.wn_row(WX.SITE_BLANK), WX.wn_row(WX.SITE_EMPTY)]
    asked, listed = cli.population(
        rows, excluded={WX.SITE_N}, earlier={WX.SITE_BLANK}, kind=cli.KIND_WN
    )
    assert [e["site_id"] for e in asked] == [WX.SITE_EMPTY]
    assert listed == {"excluded": [WX.SITE_N], "earlier-run": [WX.SITE_BLANK]}


# ------------------------------------------------------------------------------ a whole run
def _rows():
    return [
        WX.wn_row(WX.SITE_N),
        WX.wn_row(WX.SITE_BLANK, "   "),
        WX.wn_row(WX.SITE_EMPTY),
        WX.wn_row(WX.SITE_BAD),
    ]


Q_NOWHERE = FX.quote(FX.WIKI, "The temples were raised by a lost people in a later age of giants.")


def _answers():
    return {
        WX.SITE_N: WX.good(WX.SITE_N),
        WX.SITE_BLANK: WX.good(WX.SITE_BLANK),
        WX.SITE_EMPTY: WX.nothing(WX.SITE_EMPTY),
        WX.SITE_BAD: WX.written(
            WX.SITE_BAD,
            WX.sentence(WX.W1, WX.Q_W1),
            WX.sentence(WX.W2, WX.Q_W2),
            WX.sentence("The monuments were raised by a lost people in a later age.", Q_NOWHERE),
        ),
    }


@pytest.fixture(scope="module")
def run_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("wn")
    run, plan = WX.build_wn_run(root, _rows(), _answers())
    return root, run, plan


def test_a_wn_run_exports_the_write_round_and_records_its_kind(run_dirs) -> None:
    _, run, _ = run_dirs
    population = json.loads((run / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["kind"] == "wn" and population["list"] is None
    assert population["by_marking"] == {"none": 4} and population["asked"] == 4
    sites = read_jsonl(run / cli.SITES_FILE)
    assert all(e["sentences"] == [] and e["marking"] == "none" for e in sites)
    (record,) = cli.read_rounds(run)
    assert record["asked"] == dict.fromkeys(record["asked"], [])
    assert sorted(record["batches"]) == ["wn-0001"]
    exported = (
        Path(REPO / record["handoff"])
        if not Path(record["handoff"]).is_absolute()
        else Path(record["handoff"])
    )
    manifest = OH.manifest(exported)
    assert {line["stage"] for line in manifest} == {"write"} and len(manifest) == 4


def test_the_write_prompt_is_the_one_frozen_question_with_the_parsers_numbers(run_dirs) -> None:
    _, run, _ = run_dirs
    entry = cli.read_sites(run)[WX.SITE_N]
    prompt = cli.write_prompt(entry)
    assert f'"site_id": "{WX.SITE_N}"' in prompt and "name: Tarxien Temples" in prompt
    assert "WRITE 2 to 6 sentences" in prompt and "12 words or more" in prompt
    assert "25 to 400 characters" in prompt and "{" not in prompt.replace('{"', "").replace(
        "{{", ""
    )
    assert cli.check_prompt(entry, [], {}, cli.KIND_WN) == prompt


def test_the_brief_names_a_sonnet_writer_and_the_sonnet_model(run_dirs) -> None:
    _, run, _ = run_dirs
    (record,) = cli.read_rounds(run)
    brief = cli.brief(run, Path(record["handoff"]), "wn-0001")
    assert "Sonnet writer wn-0001" in brief and "--stage write" in brief
    assert (
        "--answered-by sonnet-write-wn-0001 --model claude-sonnet-5-5 --role fact_checker" in brief
    )
    assert "check-answer --run-dir" in brief and "answer with no sentences" in brief


def test_the_import_records_every_written_sentence_as_a_keep_in_the_check_rounds_format(
    run_dirs,
) -> None:
    _, run, _ = run_dirs
    rows = {r["label"]: r for r in read_jsonl(run / "round-1" / "ANSWERS.jsonl")}
    assert set(rows) == {WX.SITE_N, WX.SITE_BLANK, WX.SITE_EMPTY, WX.SITE_BAD}
    assert (
        rows[WX.SITE_N]["answered_by"] == "sonnet-write-wn-0001"
        and rows[WX.SITE_N]["problem"] is None
    )
    results = rows[WX.SITE_N]["results"]
    assert sorted(results) == ["1", "2", "3"] and all(r["counted"] for r in results.values())
    assert results["1"]["answer"]["verdict"] == "KEEP" and results["1"]["answer"]["remove"] is None
    assert rows[WX.SITE_EMPTY]["results"] == {}
    bad = rows[WX.SITE_BAD]["results"]
    assert [bad[n]["counted"] for n in ("1", "2", "3")] == [True, True, False]
    assert "not usable (not found" in bad["3"]["why"]
    # no re-ask: the sentence is dropped, whatever was not found
    assert json.loads((run / "round-1" / "REASK.json").read_text(encoding="utf-8")) == {}
    drafts = {d["site_id"]: d for d in read_jsonl(run / cli.DRAFTS_FILE)}
    assert drafts[WX.SITE_N]["sentences"] == [WX.W1, WX.W2, WX.W3]
    assert drafts[WX.SITE_EMPTY]["sentences"] == [] and drafts[WX.SITE_EMPTY]["note"]
    # the written sentences are the sites' sentences from the import on
    assert cli.read_sites(run)[WX.SITE_N]["sentences"] == [WX.W1, WX.W2, WX.W3]
    assert read_jsonl(run / cli.SITES_FILE)[0]["sentences"] == []  # the export's file is untouched


def test_a_written_description_is_never_re_asked(run_dirs, tmp_path) -> None:
    _, run, _ = run_dirs
    with pytest.raises(cli.WcRunError, match="a written description is not re-asked"):
        cli.cmd_export_reask(run, tmp_path / "r2", batch_size=5)


def test_the_build_plans_the_sites_that_got_a_text_and_leaves_the_others_empty(run_dirs) -> None:
    _, run, plan = run_dirs
    summary = json.loads((run / cli.SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["kind"] == "wn" and summary["not_planned"] == {"empty": [WX.SITE_EMPTY]}
    assert summary["sites"] == 4 and summary["cleared"] == 1
    finals = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}
    assert [finals[s]["planned"] for s in (WX.SITE_N, WX.SITE_BLANK, WX.SITE_EMPTY, WX.SITE_BAD)] == [
        True, True, False, True,
    ]  # fmt: skip
    assert finals[WX.SITE_EMPTY]["description"] is None and finals[WX.SITE_EMPTY]["of"] == 0
    (batch,) = read_jsonl(plan)
    assert [s["site_id"] for s in batch["sites"]] == [WX.SITE_N, WX.SITE_BLANK, WX.SITE_BAD]
    assert [o["site_id"] for o in batch["outcomes"]] == [WX.SITE_N, WX.SITE_BLANK, WX.SITE_BAD]


def test_the_text_cites_the_pages_of_its_verified_quotes_and_carries_lane_ns_provenance(
    run_dirs,
) -> None:
    _, run, plan = run_dirs
    outcomes = {o["site_id"]: WC4.WcOutcome.from_dict(o) for o in read_jsonl(plan)[0]["outcomes"]}
    n = outcomes[WX.SITE_N]
    assert n.description == (f"{WX.W1[:-1]} [1]. {WX.W2[:-1]} [1]. {WX.W3[:-1]} [2].").replace(
        "Malta [1]", "Malta [1]"
    )
    raw = n.raw_data
    assert raw is not None and set(raw) == {M.CITATIONS_KEY, WC4.CHECK_KEY, M.PROVENANCE_KEY}
    assert [(c["n"], c["url"]) for c in raw[M.CITATIONS_KEY]] == [(1, FX.WIKI), (2, FX.MUSEUM)]
    provenance = raw[M.PROVENANCE_KEY]
    claude_only = M.AI_SYSTEM_CLAUDE  # the writer is Sonnet, the verifier Opus (D6, 2026-10-08)
    assert (
        provenance
        == M.WebProvenance(
            desc_sha256=M.text_sha256(n.description), ai_system=claude_only
        ).to_dict()
    )
    assert (provenance["lane"], provenance["ai"], provenance["ai_system"]) == (
        "N", "generated", claude_only,
    )  # fmt: skip
    check = raw[WC4.CHECK_KEY]
    assert check["checker"] == claude_only and check["checked_sha256"] == _sha("")
    assert check["verifiers"] == ["opus-verify-verify-0001"] and check["kept"] == 3
    assert WC4.wc_problems(n.description, raw, marking="none") == []
    assert WC4.wc_problems(n.description, raw)  # lane L's reading refuses a lane-N provenance
    assert WC4.evidence_problems(n.evidence, n.description, raw) == []
    evidence = n.evidence
    assert evidence["decision"] == WC4.EVIDENCE_DECISION_WN and evidence["checked"] is None
    assert evidence["marking"]["old"] == "none"


def test_a_blank_old_text_is_recorded_as_it_was_read(run_dirs) -> None:
    _, run, plan = run_dirs
    outcomes = {o["site_id"]: WC4.WcOutcome.from_dict(o) for o in read_jsonl(plan)[0]["outcomes"]}
    blank = outcomes[WX.SITE_BLANK]
    assert blank.evidence["checked"] == "   " and blank.evidence["marking"]["old"] == "none"
    assert blank.raw_data[WC4.CHECK_KEY]["checked_sha256"] == _sha("   ")  # the stored value
    assert WC4.old_marking_problems(blank.evidence["marking"], "   ", None) == []
    assert WC4.old_marking_problems(blank.evidence["marking"], None, None) == []


def test_a_sentence_whose_quote_was_not_found_is_dropped_the_rest_is_published(run_dirs) -> None:
    _, run, plan = run_dirs
    outcomes = {o["site_id"]: WC4.WcOutcome.from_dict(o) for o in read_jsonl(plan)[0]["outcomes"]}
    bad = outcomes[WX.SITE_BAD]
    assert bad.description == f"{WX.W1[:-1]} [1]. {WX.W2[:-1]} [1]."
    sentences = bad.evidence["sentences"]
    assert [s["verdict"] for s in sentences] == ["KEEP", "KEEP", "DROP"]
    assert sentences[2]["reason"] == "unverified"
    assert [x["n"] for x in bad.raw_data[M.CITATIONS_KEY]] == [1]


def test_the_judge_asks_only_the_sites_that_have_sentences(run_dirs) -> None:
    root, run, _ = run_dirs
    ask = json.loads((run / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    judged = [label for labels in ask["batches"].values() for label in labels]
    assert WX.SITE_EMPTY not in judged and len(judged) == 3
    result = json.loads((run / "judge" / "RESULT.json").read_text(encoding="utf-8"))
    assert result["passed"] is True and result["thresholds"] == {
        "wrong": 0, "unsupported_share": 0.05, "incoherent": 0,
    }  # fmt: skip
    prompt = root / "handoff" / "wn-test-judge" / "judge-0001" / "judge"
    first = sorted(prompt.glob("*.prompt.txt"))[0].read_text(encoding="utf-8")
    assert "Another agent wrote it from web pages" in first and "checker" not in first


def test_the_verifier_is_told_the_text_was_written_not_checked(run_dirs) -> None:
    root, run, _ = run_dirs
    prompt = next(
        (root / "handoff" / "wn-test-verify" / "verify-0001" / "verify").glob("*.prompt.txt")
    )
    text = prompt.read_text(encoding="utf-8")
    assert "Another agent wrote this new description from web pages" in text
    assert "the writer's quotes" in text and "checked the old description" not in text
    assert text.count("K1: ") == 1 and "trimmed from" not in text


def test_a_verifier_that_wrote_the_site_is_refused(tmp_path: Path) -> None:
    rows = [WX.wn_row(WX.SITE_N)]
    run, handoff = tmp_path / "runs" / "wn", tmp_path / "handoff" / "wn-w"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    cli.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=1, seed=1, wn=True)
    WX.record_written(handoff, {WX.SITE_N: WX.good(WX.SITE_N)})
    cli.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    verify = tmp_path / "handoff" / "wn-verify"
    cli.cmd_verify_export(run, verify, batch_size=5)
    (line,) = OH.manifest(verify)
    OH.write_answer(
        verify, model=OH.SONNET_MODEL, batch_id=line["batch_id"], stage=line["stage"],
        label=line["label"], text=FX.verification(WX.SITE_N, ["SUPPORTED"] * 3),
        answered_by="sonnet-write-wn-0001", now=lambda: "2026-10-01T12:00:00+00:00",
    )  # fmt: skip
    with pytest.raises(cli.WcRunError, match="checked or verified this site before"):
        cli.cmd_verify_import(run, verify, client=FX.FakeClient(), pace=0.0)


def test_a_malformed_write_answer_refuses_the_import_it_is_not_silently_empty(
    tmp_path: Path,
) -> None:
    rows = [WX.wn_row(WX.SITE_N)]
    run, handoff = tmp_path / "runs" / "wn", tmp_path / "handoff" / "wn-w"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    cli.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=1, seed=1, wn=True)
    WX.record_written(handoff, {WX.SITE_N: _answer(_sentence())})  # one sentence: out of shape
    with pytest.raises(cli.WcRunError, match="malformed answer.*delete the answer file"):
        cli.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not (run / cli.DRAFTS_FILE).exists() and not (run / "round-1").exists()


def test_the_agents_check_answer_reports_each_sentence_and_the_text_it_leaves(
    run_dirs, tmp_path
) -> None:
    _, run, _ = run_dirs
    (record,) = cli.read_rounds(run)
    handoff = Path(record["handoff"])
    path = tmp_path / "a.json"
    path.write_text(_answer(_sentence(WX.W1, WX.Q_W1), _sentence(WX.W2, WX.Q_W2), site=WX.SITE_N),
                    encoding="utf-8")  # fmt: skip
    text = path.read_text(encoding="utf-8")
    clean, report = cli.check_answer(
        run, handoff, "wn-0001", WX.SITE_N, text, client=FX.FakeClient(), pace=0.0
    )
    assert clean and "S1 KEEP: counts" in report and "S2 KEEP: counts" in report
    assert f"the text this answer leaves: {WX.W1[:-1]} [1]. {WX.W2[:-1]} [1]." in report
    clean, report = cli.check_answer(
        run, handoff, "wn-0001", WX.SITE_N,
        _answer(_sentence(WX.W1, WX.Q_W1), _sentence(WX.W2, Q_NOWHERE), site=WX.SITE_N),
        client=FX.FakeClient(), pace=0.0,
    )  # fmt: skip
    assert not clean and "S2 KEEP: DOES NOT COUNT" in report and "NOT CLEAN" in report
    assert cli.check_answer(run, handoff, "wn-0001", WX.SITE_N, _answer(_sentence()))[1].startswith(
        "NOT IN SHAPE"
    )
    clean, report = cli.check_answer(
        run, handoff, "wn-0001", WX.SITE_EMPTY, WX.nothing(WX.SITE_EMPTY)
    )
    assert clean and report.startswith("no sentence: the site stays without a description")
    assert cli.check_answer(run, handoff, "wn-0001", WX.SITE_N, text, fetch_pages=False)[1] == (
        "in shape (no page fetched)"
    )


# ------------------------------------------------------------------------------ the pilot's gate
def _pilot_approval_setup(tmp_path: Path):
    wn_pilot = WX.build_wn_run(tmp_path / "a", [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)},
                               name="wn-pilot")  # fmt: skip
    wn_chunk = WX.build_wn_run(tmp_path / "b", [WX.wn_row(WX.SITE_BAD)], {WX.SITE_BAD: WX.good(WX.SITE_BAD)},
                               name="wn-chunk", pilot=False, first_batch=4002)  # fmt: skip
    wc_pilot = FX.build_run(tmp_path / "c", [FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A))],
                            {FX.SITE_A: FX.answer(FX.SITE_A, [FX.keep(1, FX.Q_COMPLEX), FX.drop(2), FX.drop(3)])},
                            name="wc-pilot")  # fmt: skip
    wc_chunk = FX.build_run(tmp_path / "d", [FX.row(FX.SITE_B, "The Tarxien Temples are an archaeological complex in Tarxien, Malta.", raw_data=None)],
                            {FX.SITE_B: FX.answer(FX.SITE_B, [FX.keep(1, FX.Q_COMPLEX)])},
                            name="wc-chunk", pilot=False, first_batch=4003)  # fmt: skip
    return wn_pilot[1], wn_chunk[1], wc_pilot[1], wc_chunk[1]


def test_each_kind_of_text_has_its_own_pilot_and_a_mass_plan_never_rests_on_the_others(
    tmp_path: Path,
) -> None:
    wn_pilot, wn_chunk, wc_pilot, wc_chunk = _pilot_approval_setup(tmp_path)
    ok = cli.pilot_approval([wc_pilot, wn_pilot, wn_chunk, wc_chunk])
    assert [a["run"].rsplit("/", 1)[-1] for a in ok] == ["wc-pilot", "wn-pilot"]
    assert len(cli.pilot_approval([wn_pilot, wn_chunk])) == 1
    for plans, message in (
        ([wn_chunk], "the first WN plan named is the pilot's"),
        ([wc_pilot, wn_chunk], "the first WN plan named is the pilot's"),  # a WC pilot is not WN's
        ([wn_pilot, wc_chunk], "the first WC plan named is the pilot's"),  # nor a WN pilot WC's
        ([wc_chunk, wn_pilot], "the first WC plan named is the pilot's"),
    ):
        with pytest.raises(cli.WcRunError, match=message) as refused:
            cli.pilot_approval(plans)
        assert "is not a pilot" in str(refused.value)


def test_a_wn_pilot_that_failed_or_was_planned_again_after_its_judge_writes_nothing(
    tmp_path: Path,
) -> None:
    wn_pilot, wn_chunk, *_ = _pilot_approval_setup(tmp_path)
    result = wn_pilot.parent / "judge" / "RESULT.json"
    good = result.read_text(encoding="utf-8")
    result.write_text(json.dumps({**json.loads(good), "passed": False, "failures": ["x"]}),
                      encoding="utf-8")  # fmt: skip
    with pytest.raises(cli.WcRunError, match="did not pass"):
        cli.pilot_approval([wn_pilot, wn_chunk])
    result.write_text(good, encoding="utf-8")
    wn_pilot.write_text(wn_pilot.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="not the plan the pilot's judge judged"):
        cli.pilot_approval([wn_pilot, wn_chunk])


def test_the_pilot_of_a_wn_run_is_judged_on_the_unchanged_thresholds(run_dirs) -> None:
    """J_THRESHOLDS is WC's, unchanged for WN (stated in the runbook, section 12): no WRONG kept
    sentence with a found quote, at most 5 % UNSUPPORTED, no incoherent text."""
    assert cli.J_THRESHOLDS == {"wrong": 0, "unsupported_share": 0.05, "incoherent": 0}


# ------------------------------------------------------------------------------ the pilot's sample
def _sites(count: int) -> list[str]:
    return [f"2{n:07x}-0000-4000-8000-{n:012x}" for n in range(1, count + 1)]


def _pilot(tmp_path: Path, count: int, with_text: int):
    """A WN pilot over `count` sites without a description, of which the agents wrote a text for the
    first `with_text`; the rest found no page. Judged by a judge that finds nothing to fault."""
    ids = _sites(count)
    rows = [WX.wn_row(site_id) for site_id in ids]
    answers = {
        site_id: WX.good(site_id) if n < with_text else WX.nothing(site_id)
        for n, site_id in enumerate(ids)
    }
    return WX.build_wn_run(tmp_path, rows, answers, name="wn-pilot")


def test_a_wn_pilot_in_which_most_sites_ended_empty_measured_too_little_and_approves_nothing(
    tmp_path: Path,
) -> None:
    """19 of the 20 drawn sites end empty: the one judged text is clean, yet the pilot did not
    measure the write round - the judge's verdict is a failure and so is the gate's, even with the
    verdict forged to `passed`."""
    run, plan = _pilot(tmp_path, 20, with_text=1)
    result_path = run / "judge" / "RESULT.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["passed"] is False
    assert (result["measured"]["drawn"], result["measured"]["minimum"]) == (20, 10)
    assert result["measured"]["independent"] == 1
    assert any("1 of the 20 drawn site(s)" in failure for failure in result["failures"])
    with pytest.raises(cli.WcRunError, match="did not pass"):
        cli.pilot_approval([plan])
    result_path.write_text(json.dumps({**result, "passed": True, "failures": []}), encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="the WN pilot measured too little"):
        cli.pilot_approval([plan])


def test_a_wn_pilot_passes_from_half_of_its_drawn_sites_with_a_judged_text(tmp_path: Path) -> None:
    short, _ = _pilot(tmp_path / "short", 20, with_text=9)
    assert (
        json.loads((short / "judge" / "RESULT.json").read_text(encoding="utf-8"))["passed"] is False
    )
    enough, plan = _pilot(tmp_path / "enough", 20, with_text=10)
    result = json.loads((enough / "judge" / "RESULT.json").read_text(encoding="utf-8"))
    assert result["passed"] is True and result["measured"]["kept_sentences"] == 30
    assert len(cli.pilot_approval([plan])) == 1


def test_a_wn_pilot_draws_twenty_sites_or_the_whole_smaller_population(tmp_path: Path) -> None:
    assert [cli.wn_pilot_size(n) for n in (1, 19, 20, 21, 175)] == [1, 19, 20, 20, 20]
    run = tmp_path / "runs" / "wn"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner([WX.wn_row(site_id) for site_id in _sites(25)]))
    with pytest.raises(cli.WcRunError, match="a WN pilot draws 20 sites"):
        cli.cmd_export(
            run, tmp_path / "h", batch_size=5, exclude=None, after=[], wn=True, pilot=5, seed=1
        )
    assert not (run / cli.SITES_FILE).exists()
    # a plan whose population record names a smaller pilot than the one the gate requires
    pilot_run, plan = _pilot(tmp_path / "ok", 20, with_text=20)
    record_path = pilot_run / cli.POPULATION_FILE
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["population"] = 40  # a population of 40 asks for a pilot of 20: this one drew 20, fine
    record_path.write_text(json.dumps(record), encoding="utf-8")
    assert len(cli.pilot_approval([plan])) == 1
    record["pilot"] = {"sites": 5, "seed": 1}
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="a WN pilot of 5 sites from a population of 40"):
        cli.pilot_approval([plan])


def test_judge_result_holds_a_wn_pilot_to_its_minimum_and_a_wc_pilot_to_none() -> None:
    kept = {"kind": "kept", "verdict": "SUPPORTED", "quotes_found": True}
    row = {"independent": True, "coherent": True, "items": [kept, kept]}
    assert cli.judge_result([row, row])["passed"] is True  # WC: the thresholds alone, as before
    assert cli.judge_result([row, row], drawn=4)["passed"] is True  # 2 of 4 texts, 4 sentences
    failed = cli.judge_result([row], drawn=4)
    assert failed["passed"] is False and len(failed["failures"]) == 1
    assert cli.judge_result([], drawn=1)["passed"] is False  # nothing judged is not a pass
