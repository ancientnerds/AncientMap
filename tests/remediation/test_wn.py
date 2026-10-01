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


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------ the frozen texts
#: Pinned 2026-10-01. A changed text makes every answer exported under it stale: a change is a new
#: pin and a new export, never an edit under a running round.
PINS = {
    "WRITE_QUESTION": "69c6d6a71dbe5c414b64a2421b2d4bb3eac499c5a050e16266409df7ffc88a44",
    "WRITE_BRIEF": "f1dbef439b05efc46220b522bcd05141986cd8e08d2ffd6dc677e1ec806f4aae",
    "VERIFY_QUESTION_WN": "6a1e020d54c09377dcfba34a70b5c317bb9b7ebe2839e09ed716e227e06b5537",
    "JUDGE_QUESTION_WN": "75c58553ed4a650834f9052672b3a93225c2dda73f1d5914870aefb64b4df2e4",
    "CHECK_QUESTION_LISTED": "2d7bc90ca4908ce9f2bdcd5e8d09bef04631200e7273d2559100c730b76719f3",
    "NO_TRIM": "fd0ac89cf5cd7e0cb56da9e52e34f240990d5a2deffadff61021672d4ca39203",
    "CHECK_BRIEF_SONNET": "835f1199223c1f733c689d45f6b28afecebfa9b16b18a6f11987a8c7a7f000eb",
    "VERIFY_BRIEF_SONNET": "29af52e0cf0216f2dd00aa69a567f4e0ace48c405e6cc19ea3ed71147a710866",
    "JUDGE_BRIEF_SONNET": "e3a9b171ea83899ca9b083e0027903d045d5e71908f3959f7d132e5650906670",
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


@pytest.mark.parametrize(
    "brief", [P2.WRITE_BRIEF, P2.CHECK_BRIEF_SONNET, P2.VERIFY_BRIEF_SONNET, P2.JUDGE_BRIEF_SONNET]
)
def test_every_new_brief_tells_the_agent_to_record_with_the_sonnet_model(brief: str) -> None:
    assert "--model claude-sonnet-5-5" in brief
    assert "claude-opus-5-5" not in brief and "<the model id" not in brief
    assert "You are Sonnet" in brief and "You are Opus" not in brief


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
    assert "--answered-by sonnet-write-wn-0001 --model claude-sonnet-5-5" in brief
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
    assert provenance == M.WebProvenance(desc_sha256=M.text_sha256(n.description)).to_dict()
    assert (provenance["lane"], provenance["ai"], provenance["ai_system"]) == (
        "N", "generated", M.AI_SYSTEM,
    )  # fmt: skip
    check = raw[WC4.CHECK_KEY]
    assert check["checker"] == M.AI_SYSTEM and check["checked_sha256"] == _sha("")
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
