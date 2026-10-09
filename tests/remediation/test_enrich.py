"""Lane E, the enrichment, on the WC machinery (`wc/cli.py` kind `wn-enrich`): the population, the enrich
round, the import that fetches every page itself, the verification of the new sentences inside the whole
text, the build, the pilot's judge with its hook-invented count, the pilot gate and the roles every
answer must name. Nothing here calls a model, opens a socket or touches a database. The mutation cases
are `ENRICH_MUTATIONS`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from phase3.run import read_jsonl  # noqa: E402 - scripts/remediation is on sys.path by wc_fixtures
from wc import cli  # noqa: E402
from wc import enrich as E  # noqa: E402

from tests.remediation import enrich_fixtures as EF
from tests.remediation import wc_fixtures as FX
from tests.remediation import wn_fixtures as WX
from tests.remediation.wc_fixtures import OH, WC4, M, wiki_cache  # noqa: F401 - autouse


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, Any]:
    return EF.built(tmp_path_factory.mktemp("enrich-cli"))


@pytest.fixture
def calibrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The writer's calibration stands (a sealed, passed verdict) in a calibration root of its own."""
    root = EF.write_writer_calibration(tmp_path / "calibration")
    monkeypatch.setattr(E, "CALIBRATION_ROOT", root)
    return root


def _rows(tmp_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    return EF.standard_rows(tmp_path)


# ------------------------------------------------------------------------------ the export
def test_the_export_asks_the_listed_sites_that_can_be_enriched_each_under_its_marking(
    tmp_path: Path,
) -> None:
    rows, _ = _rows(tmp_path)
    retired = FX.row(EF.SITE_BAD, WX.P4_TEXT, raw_data=WX.p4_site_raw(), scope_status="retired")
    run, handoff = EF.start_enrich_run(tmp_path / "r", [*rows, retired])
    population = json.loads((run / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["kind"] == "wn-enrich" and population["asked"] == 4
    assert population["by_marking"] == {"L": 1, "phase4": 2, "web": 1}
    assert population["listed_counts"] == {"retired": 1}
    entries = {e["site_id"]: e for e in read_jsonl(run / cli.SITES_FILE)}
    entry = entries[EF.SITE_W]
    assert entry["sentences"] == [] and entry["thin"] is True and entry["dispute"] is None
    assert entry["existing"] == list(WC4.checked_sentences(WX.P4_TEXT))
    assert entry["base"] == {"text": WX.P4_TEXT, "citations": WX.p4_site_raw()[M.CITATIONS_KEY]}
    assert entries[EF.SITE_L]["base_check"] is not None and entry["base_check"] is None


def test_the_round_is_the_enrich_round_of_one_question_per_site(tmp_path: Path) -> None:
    rows, _ = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    manifest = OH.manifest(handoff)
    assert {line["stage"] for line in manifest} == {"enrich"}
    assert sorted({line["batch_id"] for line in manifest}) == ["we-0001"]
    assert {line["label"] for line in manifest} == {r["id"] for r in rows}
    prompt = (handoff / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
    assert "You extend the description of one site" in prompt
    assert "THE DESCRIPTION AS IT STANDS" in prompt and "S1: " in prompt
    record = cli.round_of(run, handoff)
    assert record["round"] == 1 and set(record["asked"]) == {r["id"] for r in rows}


def test_the_export_refuses_what_a_lane_e_run_is_not(tmp_path: Path) -> None:
    rows, _ = _rows(tmp_path)
    run = tmp_path / "r" / "runs" / "x"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    listing = tmp_path / "sites.txt"
    listing.write_text(f"{EF.SITE_W}\n", encoding="utf-8")

    def export(handoff: str, **kwargs: Any) -> Any:
        base = {"batch_size": 5, "exclude": None, "after": [], "pilot": None, "seed": None}
        return cli.cmd_export(run, tmp_path / handoff, **{**base, **kwargs})

    with pytest.raises(cli.WcRunError, match="asks the sites of a --sites list"):
        export("a", enrich=True)
    with pytest.raises(cli.WcRunError, match="beside neither --wn nor --defects"):
        export("b", enrich=True, wn=True, sites=listing)
    with pytest.raises(cli.WcRunError, match="goes with --enrich"):
        export("c", sites=listing, disputes=listing)
    three = tmp_path / "three.txt"
    three.write_text("\n".join([EF.SITE_W, EF.SITE_L, EF.SITE_N]) + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="lane-E pilot draws 3 sites"):
        export("d", enrich=True, sites=three, pilot=2, seed=1)
    assert not (run / cli.SITES_FILE).exists()  # nothing half-exported


def test_a_list_names_curated_sites_only(tmp_path: Path) -> None:
    rows, _ = _rows(tmp_path)
    run, _ = EF.start_enrich_run(tmp_path / "r", rows)  # the run works
    other = tmp_path / "other"
    other.mkdir()
    run2 = other / "runs" / "y"
    run2.mkdir(parents=True)
    cli.cmd_read(run2, runner=FX.ReadRunner(rows))
    listing = other / "sites.txt"
    listing.write_text("ffffffff-0000-4000-8000-000000000001\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="no curated row"):
        cli.cmd_export(run2, other / "h", batch_size=5, exclude=None, after=[], pilot=None,
                       seed=None, sites=listing, enrich=True)  # fmt: skip


@pytest.mark.parametrize("site", [EF.SITE_W, EF.SITE_L, EF.SITE_N])
def test_an_enriched_text_is_asked_by_no_check_and_no_list_run(
    built: dict[str, Any], site: str
) -> None:
    """Whatever the marking: the enrichment moved a March or lane-N text's check record into
    `base_check`, so the `checked-before` guard no longer sees it (review of 2026-10-09: a plain WC
    run asked such a text again as March AI text and replaced the enrichment record)."""
    done = built["outcomes"][site]
    row = FX.row(site, done.description, raw_data=done.raw_data)
    for kind, only in ((cli.KIND_WC, None), (cli.KIND_LIST, {site})):
        asked, listed = cli.population([row], excluded=set(), earlier=set(), kind=kind, only=only)
        assert listed == {"enriched-text": [site]}, (site, kind)
    asked, listed = cli.population(
        [row], excluded=set(), earlier=set(), kind=cli.KIND_ENRICH, only={site}
    )
    assert asked == [] and listed == {"enriched-before": [site]}  # and never twice


# ------------------------------------------------------------------------------ the agent's aids
def test_the_brief_records_the_answer_in_the_writers_role(tmp_path: Path) -> None:
    rows, _ = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    text = cli.brief(run, handoff, "we-0001")
    assert "--stage enrich" in text and "--model claude-sonnet-5-5 --role field_researcher" in text
    assert "--answered-by sonnet-enrich-we-0001" in text and "lane E" in text
    with pytest.raises(cli.WcRunError, match="no batch of"):
        cli.brief(run, handoff, "we-0009")


def test_check_answer_reports_the_shape_the_quotes_and_the_text_the_answer_leaves(
    tmp_path: Path,
) -> None:
    rows, _ = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    label = EF.SITE_W
    client = EF.pages_client()
    clean, report = cli.check_answer(
        run, handoff, "we-0001", label, EF.good(label), client=client, pace=0
    )
    assert clean and "S1 KEEP: counts" in report and "S2 KEEP: counts" in report
    assert f"the text this answer leaves: {WX.P4_TEXT} Spiral reliefs decorate" in report
    assert "[2]." in report
    clean, report = cli.check_answer(run, handoff, "we-0001", label, "{}", client=client, pace=0)
    assert not clean and report.startswith("NOT IN SHAPE")
    clean, report = cli.check_answer(
        run, handoff, "we-0001", label, EF.nothing(label), client=client, pace=0
    )
    assert clean and "the site is left as it is" in report
    lost = EF.answer(
        label,
        EF.sentence(
            "fact",
            EF.FACT,
            FX.quote(EF.RESEARCH, "Nothing like this is written on the page at all."),
        ),
    )
    clean, report = cli.check_answer(run, handoff, "we-0001", label, lost, client=client, pace=0)
    assert not clean and "DOES NOT COUNT" in report and "the site is left as it is" in report


# ------------------------------------------------------------------------------ the import
def _import(run: Path, handoff: Path) -> dict[str, Any]:
    return cli.cmd_import(run, handoff, client=EF.pages_client(), pace=0.0)


def _record(handoff: Path, answers: dict[str, str], **kwargs: Any) -> None:
    EF.record_enriched(handoff, answers, **kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"role": "web_verifier"}, "does not name the role 'field_researcher'"),
        ({"model": OH.OPUS_MODEL}, "registered to claude-sonnet-5-5"),
        ({"model": OH.MINIMAX_MODEL}, "registered to claude-sonnet-5-5"),
        ({"model": OH.HAIKU_MODEL}, "registered to claude-sonnet-5-5"),
    ],
)
def test_the_import_refuses_an_answer_that_is_not_the_writers_role(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    rows, answers = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    _record(handoff, answers, **kwargs)
    with pytest.raises(E.EnrichError, match=message):
        _import(run, handoff)
    assert not (run / "round-1" / "ANSWERS.jsonl").exists()


def test_an_answer_recorded_without_a_role_is_refused(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff, model=OH.SONNET_MODEL, batch_id=line["batch_id"], stage=line["stage"],
            label=line["label"], text=answers[line["label"]], answered_by="sonnet-enrich-1",
            now=lambda: "2026-10-09T12:00:00+00:00",
        )  # fmt: skip
    with pytest.raises(E.EnrichError, match="does not name the role"):
        _import(run, handoff)


def test_a_malformed_enrich_answer_refuses_the_import_it_is_not_silently_empty(
    tmp_path: Path,
) -> None:
    rows, answers = _rows(tmp_path)
    answers[EF.SITE_W] = EF.answer(
        EF.SITE_W,
        EF.sentence("open_question", EF.HOOK, EF.Q_HOOK),
        EF.sentence("fact", EF.FACT, EF.Q_FACT),
    )  # the classes are out of order
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    _record(handoff, answers)
    with pytest.raises(cli.WcRunError, match="malformed answer .*not in the order"):
        _import(run, handoff)


def test_the_import_fetches_every_page_itself_and_records_the_sentences_as_keeps(
    tmp_path: Path,
) -> None:
    rows, answers = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    _record(handoff, answers)
    client = EF.pages_client()
    summary = cli.cmd_import(run, handoff, client=client, pace=0.0)
    assert summary["answers"] == 4 and summary["sentences"] == 6 and summary["to_reask"] == 0
    assert summary["sites_without_sentences"] == 1 and summary["verdicts"] == {"KEEP": 6}
    assert client.fetched == [EF.RESEARCH]  # one page, fetched once for all four sites
    drafts = {d["site_id"]: d for d in read_jsonl(run / cli.DRAFTS_FILE)}
    assert drafts[EF.SITE_W]["sentences"] == [EF.FACT, EF.HOOK]
    assert drafts[EF.SITE_W]["classes"] == ["fact", "open_question"]
    assert drafts[EF.SITE_NONE]["sentences"] == []
    sites = cli.read_sites(run)
    assert sites[EF.SITE_W]["sentences"] == [
        EF.FACT,
        EF.HOOK,
    ]  # the NEW ones; the old stay `existing`
    assert sites[EF.SITE_W]["existing"][0].startswith("The Tarxien Temples")
    with pytest.raises(cli.WcRunError, match="was imported; a round is imported once"):
        _import(run, handoff)
    with pytest.raises(cli.WcRunError, match="not re-asked"):
        cli.cmd_export_reask(run, tmp_path / "again", batch_size=5)


def test_a_sentence_whose_quote_is_not_found_is_dropped_not_re_asked(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    lost = FX.quote(
        EF.RESEARCH,
        "The spiral reliefs at Tarxien are carved into volcanic tuff.",
        "Tarxien Research",
    )
    answers[EF.SITE_W] = EF.answer(
        EF.SITE_W,
        EF.sentence("fact", EF.FACT, lost),
        EF.sentence("open_question", EF.HOOK, EF.Q_HOOK),
    )
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    _record(handoff, answers)
    summary = _import(run, handoff)
    assert summary["to_reask"] == 0
    EF.verify_enriched(run, tmp_path / "v")
    cli.cmd_build(run, first_batch=WC4.FIRST_BATCH)
    final = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}[EF.SITE_W]
    assert final["kept"] == 1 and final["of"] == 2
    assert final["description"].endswith(
        "remains undecided [2]."
    )  # the fact was dropped, unverified
    assert [d["reason"] for d in final["decisions"]] == ["unverified", None]


# ------------------------------------------------------------------------------ the verification
def _to_verify(tmp_path: Path, answers: dict[str, str] | None = None):
    rows, standard = _rows(tmp_path)
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows)
    _record(handoff, answers or standard)
    _import(run, handoff)
    return run, rows


def test_the_verifier_is_shown_the_whole_text_with_only_the_new_sentences_marked(
    tmp_path: Path,
) -> None:
    run, _ = _to_verify(tmp_path)
    handoff = tmp_path / "v"
    cli.cmd_verify_export(run, handoff, batch_size=5)
    manifest = [m for m in OH.manifest(handoff) if m["label"] == EF.SITE_W]
    prompt = (handoff / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
    assert "THE OLD SENTENCES (context; not under judgement)" in prompt
    assert "S1: The Tarxien Temples are an archaeological complex" in prompt
    assert f"K1 [fact]: {EF.FACT}" in prompt and f"K2 [open_question]: {EF.HOOK}" in prompt
    assert f'quote: "{EF.Q_FACT["quote"]}"' in prompt
    assert cli.verify_brief(run, handoff, "verify-0001").count("--role web_verifier") == 1
    # a lane-WN verifier question is not this one
    assert "were written from web pages" in prompt and "has been checked" not in prompt


def test_a_new_sentence_the_verifier_does_not_confirm_is_dropped_and_the_rest_is_verified_again(
    tmp_path: Path,
) -> None:
    run, rows = _to_verify(tmp_path)
    first = EF.verify_enriched(
        run, tmp_path / "v1", verdicts={EF.SITE_W: ["SUPPORTED", "UNSUPPORTED"]}
    )
    assert first["to_verify2"] == 1 and first["verdicts"]["UNSUPPORTED"] == 1
    second = EF.verify_enriched(run, tmp_path / "v2", agent="sonnet-wc-verify2")
    assert second["stage"] == "verify2" and second["sites"] == 1
    cli.cmd_build(run, first_batch=WC4.FIRST_BATCH)
    finals = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}
    final = finals[EF.SITE_W]
    assert final["kept"] == 1 and final["verification"]["status"] == "verified"
    assert final["description"].endswith("inside the temples [2].")
    assert "undecided" not in final["description"]
    assert [d["reason"] for d in final["decisions"]] == [None, "verify-unsupported"]
    # the text the second verifier saw is the whole text: its hash is the served text's
    assert final["verification"]["rounds"][-1]["text_sha256"] == M.text_sha256(final["description"])


def test_a_text_the_verifier_calls_incoherent_loses_the_new_sentence_it_names(
    tmp_path: Path,
) -> None:
    run, _ = _to_verify(tmp_path)
    EF.verify_enriched(run, tmp_path / "v1", coherent={EF.SITE_W: (False, [1])})
    EF.verify_enriched(run, tmp_path / "v2", agent="sonnet-wc-verify2")
    cli.cmd_build(run, first_batch=WC4.FIRST_BATCH)
    final = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}[EF.SITE_W]
    assert [d["reason"] for d in final["decisions"]] == ["verify-incoherent", None]


def test_a_verifier_must_be_an_independent_agent_in_the_verifiers_role(tmp_path: Path) -> None:
    run, _ = _to_verify(tmp_path)
    cli.cmd_verify_export(run, tmp_path / "v", batch_size=5)
    record = cli._verify_round_of(run, tmp_path / "v")
    answers = {l: FX.verification(l, ["SUPPORTED"] * len(s)) for l, s in record["shown"].items()}
    for model, role, message in (
        (OH.SONNET_MODEL, "field_researcher", "does not name the role 'web_verifier'"),
        (OH.OPUS_MODEL, "web_verifier", "registered to claude-sonnet-5-5"),
    ):
        handoff = tmp_path / f"v-{role}-{model[:6]}"
        # the same questions, answered in another role: the round's own directory is written once
        import shutil

        shutil.copytree(tmp_path / "v", handoff)
        for line in OH.manifest(handoff):
            path = handoff / OH.answer_relpath(line["batch_id"], line["stage"], line["label"])
            if path.exists():
                path.unlink()
        EF.record_enriched(handoff, answers, role=role, model=model, agent="x-verify")
        # point the round at the copy
        meta = cli._verify_dir(run, 1) / "ROUND.json"
        original = meta.read_text(encoding="utf-8")
        meta.write_text(
            original.replace(cli._shown(tmp_path / "v"), cli._shown(handoff)), encoding="utf-8"
        )
        with pytest.raises(E.EnrichError, match=message):
            cli.cmd_verify_import(run, handoff, client=EF.pages_client(), pace=0.0)
        meta.write_text(original, encoding="utf-8")


# ------------------------------------------------------------------------------ the build
def test_the_build_plans_the_sites_that_got_sentences_and_leaves_the_others_as_they_are(
    built: dict[str, Any],
) -> None:
    summary = json.loads((built["run"] / cli.SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["kind"] == "wn-enrich"
    assert summary["not_planned"] == {"unchanged": [EF.SITE_NONE]}
    assert summary["sites"] == 4 and summary["cleared"] == 0 and summary["sentences_kept"] == 6
    finals = {f["site_id"]: f for f in read_jsonl(built["run"] / cli.FINAL_FILE)}
    assert finals[EF.SITE_NONE]["planned"] is False and finals[EF.SITE_NONE]["description"] is None
    assert finals[EF.SITE_NONE]["cleared"] is False  # a site left as it is is not a clear
    assert all(finals[s]["planned"] for s in (EF.SITE_W, EF.SITE_L, EF.SITE_N))
    plan = read_jsonl(built["plan"])
    assert [b["batch_id"] for b in plan] == ["p4-4001"]
    assert {o["site_id"] for o in plan[0]["outcomes"]} == {EF.SITE_W, EF.SITE_L, EF.SITE_N}


def test_the_text_of_each_site_is_the_stored_text_with_the_new_sentences_appended(
    built: dict[str, Any],
) -> None:
    rows = {r["id"]: r for r in built["rows"]}
    for site_id, outcome in built["outcomes"].items():
        old = rows[site_id]["description"]
        assert outcome.description.startswith(old + " "), site_id
        assert outcome.evidence["checked"] == old
        tail = outcome.description[len(old) + 1 :]
        assert tail.startswith("Spiral reliefs decorate limestone slabs inside the temples [")
        assert tail.count("remains undecided [") == 1
    assert built["outcomes"][EF.SITE_W].description.count("[1]") == 3  # the base's own markers stay
    # the new page is number N+1 in every text: N is 1 for the Phase-4 text, 2 for the others
    assert built["outcomes"][EF.SITE_W].description.endswith("undecided [2].")
    assert built["outcomes"][EF.SITE_L].description.endswith("undecided [3].")


def test_a_build_is_refused_while_a_verification_is_due(tmp_path: Path) -> None:
    run, _ = _to_verify(tmp_path)
    with pytest.raises(cli.WcRunError, match="verification round 1 .* is due"):
        cli.cmd_build(run, first_batch=WC4.FIRST_BATCH)


# ------------------------------------------------------------------------------ the pilot
def test_the_pilot_is_judged_with_the_hook_invented_count_and_passes_at_zero(
    built: dict[str, Any],
) -> None:
    result = json.loads((built["run"] / cli.JUDGE_DIR / "RESULT.json").read_text(encoding="utf-8"))
    assert result["passed"] is True and result["failures"] == []
    assert result["measured"]["hook_invented"] == 0
    assert result["measured"]["kept_sentences"] == 6 and result["measured"]["drawn"] == 4
    assert result["thresholds"] == cli.ENRICH_THRESHOLDS == {
        "wrong": 0, "unsupported_share": 0.05, "incoherent": 0, "hook_invented": 0,
    }  # fmt: skip
    judged = read_jsonl(built["run"] / cli.JUDGE_DIR / "JUDGED.jsonl")
    assert {row["site_id"] for row in judged} == {
        EF.SITE_W,
        EF.SITE_L,
        EF.SITE_N,
    }  # not the unchanged


def test_a_pilot_whose_judge_finds_a_hook_invented_fails(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    run, _ = EF.build_enrich_run(tmp_path / "r", rows, answers, invented=[EF.SITE_L])
    result = json.loads((run / cli.JUDGE_DIR / "RESULT.json").read_text(encoding="utf-8"))
    assert result["passed"] is False and result["measured"]["hook_invented"] == 1
    assert any("INVENTED" in failure for failure in result["failures"])
    with pytest.raises(cli.WcRunError, match="did not pass"):
        cli.pilot_approval([run / cli.PLAN_FILE])


def test_the_judge_must_be_an_opus_agent_in_the_pilot_judges_role(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    run, _ = EF.build_enrich_run(tmp_path / "r", rows, answers, judged=False)
    with pytest.raises(E.EnrichError, match="registered to claude-opus-5-5"):
        EF.judge_enriched(run, tmp_path / "j1", model=OH.SONNET_MODEL)
    run2, _ = EF.build_enrich_run(tmp_path / "s", rows, answers, judged=False, name="second")
    with pytest.raises(E.EnrichError, match="does not name the role 'pilot_judge'"):
        EF.judge_enriched(run2, tmp_path / "j2", role="adversarial")


def test_the_judge_question_shows_the_old_text_and_marks_the_hook(built: dict[str, Any]) -> None:
    final = {f["site_id"]: f for f in read_jsonl(built["run"] / cli.FINAL_FILE)}[EF.SITE_W]
    site = M.PlanSite.from_dict(cli.read_sites(built["run"])[EF.SITE_W]["plan_site"])
    prompt = cli.judge_prompt(final, site, cli.KIND_ENRICH)
    assert "INVENTED" in prompt and "THE OLD SENTENCES (context; not under judgement)" in prompt
    assert f"K2 [open_question]: {EF.HOOK}" in prompt and "NEW SENTENCES REMOVED\n(none)" in prompt
    assert E.judge_counts(final) == (2, 0, [2])
    handoff = built["root"] / "handoff" / "enrich-test-judge"
    assert cli.judge_brief(built["run"], handoff, "judge-0001").count("--role pilot_judge") == 1


def test_each_kind_of_text_has_its_own_pilot_and_an_enrichment_plan_never_rests_on_the_others(
    tmp_path: Path, built: dict[str, Any], calibrated: Path
) -> None:
    # the enrichment's own judged pilot approves its plan once the writer's calibration stands
    (approval,) = cli.pilot_approval([built["plan"]])
    assert approval["calibration_sha256"]
    assert approval["run"].endswith("enrich-test")
    # a chunk of the lane named first is not a pilot
    rows, answers = _rows(tmp_path)
    chunk_plan = EF.build_enrich_run(
        tmp_path / "c", rows, answers, pilot=False, name="chunk", first_batch=4501
    )[1]
    with pytest.raises(cli.WcRunError, match="first ENRICH plan named is the pilot's"):
        cli.pilot_approval([chunk_plan])
    assert len(cli.pilot_approval([built["plan"], chunk_plan])) == 1
    # a judged WN pilot does not approve a lane-E chunk, nor does a judged WC pilot
    wn_plan = WX.build_wn_run(
        tmp_path / "w", [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)}, name="wn-pilot"
    )[1]
    with pytest.raises(cli.WcRunError, match="first ENRICH plan named is the pilot's"):
        cli.pilot_approval([wn_plan, chunk_plan])
    assert len(cli.pilot_approval([wn_plan, built["plan"], chunk_plan])) == 2


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"seal": False}, "does not seal|has no sealed passed verdict"),
        ({"passed": False}, "verdict did not pass"),
        ({"unanswered": ["we-0001"]}, "verdict did not pass"),
        ({"false_sources": 1}, "verdict did not pass"),
        ({"threshold": 0.6}, "sealed below 0.7"),
        ({"role": "web_verifier"}, "does not calibrate the writer role"),
    ],
)
def test_a_lane_e_pilot_is_not_approved_on_a_writer_that_was_not_calibrated(
    tmp_path: Path,
    built: dict[str, Any],
    change: dict[str, Any],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review of 2026-10-09: pilot approval read only the judge's RESULT.json, so a lane could be
    approved and written before its writer was measured (the map: leave-one-out on about 40 sites,
    seal at 70 % or more)."""
    monkeypatch.setattr(E, "CALIBRATION_ROOT", tmp_path / "none")
    with pytest.raises(cli.WcRunError, match="no sealed passed verdict"):
        cli.pilot_approval([built["plan"]])
    monkeypatch.setattr(
        E, "CALIBRATION_ROOT", EF.write_writer_calibration(tmp_path / "calibration", **change)
    )
    with pytest.raises(cli.WcRunError, match=message):
        cli.pilot_approval([built["plan"]])


def test_the_writers_calibration_is_void_once_its_registry_entry_changed(
    built: dict[str, Any], calibrated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli.pilot_approval([built["plan"]])
    monkeypatch.setattr(E.RO, "role_sha256", lambda name: "0" * 64)
    with pytest.raises(cli.WcRunError, match="registry entry changed after the seal"):
        cli.pilot_approval([built["plan"]])


def test_the_other_lanes_pilots_need_no_writer_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(E, "CALIBRATION_ROOT", tmp_path / "none")
    wn_plan = WX.build_wn_run(
        tmp_path / "w", [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)}, name="wn-pilot"
    )[1]
    (approval,) = cli.pilot_approval([wn_plan])
    assert "calibration_sha256" not in approval


def test_the_gate_reads_the_hook_invented_count_again_so_a_forged_pass_does_not_pass(
    tmp_path: Path, built: dict[str, Any]
) -> None:
    rows, answers = _rows(tmp_path)
    run, plan = EF.build_enrich_run(tmp_path / "r", rows, answers, invented=[EF.SITE_L])
    result_path = run / cli.JUDGE_DIR / "RESULT.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(passed=True, failures=[])  # a forged verdict
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="found 1 open question"):
        cli.pilot_approval([plan])
    del result["measured"]["hook_invented"]
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="found None open question"):
        cli.pilot_approval([plan])


def test_a_judged_enrichment_pilot_that_measured_too_little_does_not_pass(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    answers = {s: EF.nothing(s) for s in answers}  # nothing to append anywhere
    answers[EF.SITE_W] = EF.good(EF.SITE_W)
    run, _ = EF.build_enrich_run(tmp_path / "r", rows, answers)
    result = json.loads((run / cli.JUDGE_DIR / "RESULT.json").read_text(encoding="utf-8"))
    assert result["passed"] is False and result["measured"]["minimum"] == 2
    assert any("measured too little" in failure for failure in result["failures"])


# ------------------------------------------------------------------------------ the disputes
def _brief(
    site_id: str, *, asserting: list[dict] | None = None, desc_sha256: str | None = None
) -> dict:
    source = {"url": EF.POSITIONS, "title": "Dating Tarxien", "quote": EF.Q_A["quote"]}
    return {
        "site_id": site_id, "name": "Tarxien Temples", "verdict": "dispute",
        "desc_sha256": desc_sha256 or M.text_sha256(WX.P4_TEXT),
        "position_a": {"claim": "The first phase is near 3600 BC", "holders": "the excavators",
                       "sources": [source]},
        "position_b": {"claim": "The first phase is near 3150 BC", "holders": "radiocarbon dating",
                       "sources": [{**source, "quote": EF.Q_B["quote"]}]},
        "asserting": asserting or [], "note": "a documented controversy",
        "researched_by": "field_researcher:r", "adjudicated_by": "adversarial:a",
    }  # fmt: skip


def test_a_dispute_brief_puts_both_positions_into_the_question_of_its_site(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    briefs = tmp_path / "DISPUTES.jsonl"
    briefs.write_text(json.dumps(_brief(EF.SITE_W)) + "\n", encoding="utf-8")
    run, handoff = EF.start_enrich_run(tmp_path / "r", rows, disputes=briefs)
    entries = {e["site_id"]: e for e in read_jsonl(run / cli.SITES_FILE)}
    assert (
        entries[EF.SITE_W]["dispute"]["verdict"] == "dispute"
        and entries[EF.SITE_L]["dispute"] is None
    )
    prompts = {
        m["label"]: (handoff / m["prompt_path"]).read_text(encoding="utf-8")
        for m in OH.manifest(handoff)
    }
    assert "THIS SITE IS DISPUTED" in prompts[EF.SITE_W] and "DISPUTED" not in prompts[EF.SITE_L]
    population = json.loads((run / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["disputes"]["sites"] == 1
    # a site with a brief must name both positions (or nothing): its fact alone is refused
    clean, report = cli.check_answer(
        run, handoff, "we-0001", EF.SITE_W, EF.good(EF.SITE_W), client=EF.pages_client(), pace=0
    )
    assert not clean and "has a dispute brief" in report


def test_the_dispute_pair_goes_through_the_whole_chain(tmp_path: Path) -> None:
    rows, answers = _rows(tmp_path)
    briefs = tmp_path / "DISPUTES.jsonl"
    briefs.write_text(json.dumps(_brief(EF.SITE_W)) + "\n", encoding="utf-8")
    answers[EF.SITE_W] = EF.answer(
        EF.SITE_W,
        EF.sentence("dispute_a", EF.POSITION_A, EF.Q_A),
        EF.sentence("dispute_b", EF.POSITION_B, EF.Q_B),
    )
    run, plan = EF.build_enrich_run(tmp_path / "r", rows, answers, disputes=briefs)
    final = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}[EF.SITE_W]
    assert final["description"].endswith(f"{EF.POSITION_A[:-1]} [2]. {EF.POSITION_B[:-1]} [2].")
    classes = final["evidence"]["enrichment"]["classes"]
    assert classes == {"1": "dispute_a", "2": "dispute_b"}
    assert final["evidence"]["enrichment"]["dispute"]["verdict"] == "dispute"


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (lambda: {**_brief(EF.SITE_W), "verdict": "settled"}, "verdict"),
        (lambda: _brief("ffffffff-0000-4000-8000-000000000001"), "is no site this run asks"),
        (
            lambda: _brief(
                EF.SITE_W,
                asserting=[
                    {"sentence": 2, "asserts": "a", "text": "They date to approximately 3150 BC."}
                ],
            ),
            "still in the text",
        ),
    ],
)
def test_a_dispute_brief_is_refused_when_it_is_not_one_this_text_can_take(
    tmp_path: Path, record, message: str
) -> None:
    rows, _ = _rows(tmp_path)
    briefs = tmp_path / "DISPUTES.jsonl"
    briefs.write_text(json.dumps(record()) + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match=message):
        EF.start_enrich_run(tmp_path / "r", rows, disputes=briefs)


def test_the_sentences_that_state_a_side_as_fact_must_be_gone_before_both_are_named(
    tmp_path: Path,
) -> None:
    """The repair pass (`defect-sites` over `DISPUTE_DEFECTS.jsonl`, a wc-list run) changes the text:
    a brief made for the earlier text is taken when the sentence it names is no longer in the text,
    and refused while it is."""
    stated = "They date to approximately 3150 BC."
    brief = _brief(EF.SITE_W, asserting=[{"sentence": 2, "asserts": "b", "text": stated}])
    brief["desc_sha256"] = "e" * 64  # made for an earlier text than the one the read holds
    rows, _ = _rows(tmp_path)
    briefs = tmp_path / "DISPUTES.jsonl"
    # the read still holds the sentence: refused
    briefs.write_text(json.dumps(brief) + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match=r"sentence\(s\) \[2\] of .* still in the text"):
        EF.start_enrich_run(tmp_path / "r1", rows, disputes=briefs)
    # the read holds the text after the repair: taken
    after = WX.P4_TEXT.replace(" They date to approximately 3150 BC [1].", "")
    repaired = [EF.p4_row(EF.SITE_W, text=after) if row["id"] == EF.SITE_W else row for row in rows]
    # the provenance of the repaired text is not needed to read the brief: the site is simply not asked
    # by the enrichment (it would be listed), so this test reads the briefs directly
    read = [{**r, "description_sha256": M.text_sha256(r["description"] or "")} for r in repaired]
    asked = [{"site_id": EF.SITE_W}]
    assert cli._read_disputes(read, briefs, asked)[EF.SITE_W]["verdict"] == "dispute"
    # two briefs for one site are refused
    briefs.write_text(json.dumps(brief) + "\n" + json.dumps(brief) + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="has two dispute briefs"):
        cli._read_disputes(read, briefs, asked)
