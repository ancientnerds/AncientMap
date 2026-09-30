from __future__ import annotations

import pytest

from pipeline.studio import remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import pull, workspace
from pipeline.studio.paper.workspace import parse_dossier
from tests.pipeline.studio import fixtures as fx

RUN_ID = "22222222-3333-4444-5555-666666666666"  # a fresh Theo run a rewrite pulls


def test_template_carries_the_house_format_rules():
    text = pull.TEMPLATE_PATH.read_text(encoding="utf-8")
    for needle in (
        "## Connecting the Dots",
        "## The Other Side",
        "## What We Actually Know",
        "5,000 to 7,500 words",
        "almost certain · very likely · likely · roughly even · unlikely · very unlikely",
        "[S:<source_id>]",
        "claims_check/live/<id>.txt",
        "IMPORTANT:",
        "<!-- editorial:begin -->",
        "<!-- editorial:end -->",
        "### Research angles",
    ):
        assert needle in text, needle


def test_render_brief_fills_every_placeholder():
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes()))
    assert "{{" not in brief
    assert "How were the Baalbek megaliths moved?" in brief
    assert f"(high) The Stone of the Pregnant Woman weighs about 1000 tons. [S:{fx.S1}]" in brief
    assert f"- [S:{fx.S4}] T1 · Paywalled monograph · publisher.example · tdm_reserved" in brief
    assert "1 challenges accepted by the defender" in brief
    assert "- engineer accepted: Range adopted." in brief
    assert (
        f'- on "The 2014 block weighs 1650 tons.": Give the range of estimates. '
        f"[S:{fx.S1}] [S:{fx.S2}]" in brief
    )
    assert "would strengthen: a pre-Roman tool mark date" in brief


def test_production_shaped_synthesis_renders_markers_not_dict_reprs():
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes()))
    assert "{'" not in brief
    assert "- Quarry and podium stone match." in brief
    assert f"  - The podium blocks are of the same limestone. [S:{fx.S2}]" in brief
    assert "- same stone" in brief
    assert f"  from: The quarry stone is a local limestone. [S:{fx.S5}]" in brief
    assert f"  to: The podium blocks are of the same limestone. [S:{fx.S2}]" in brief
    assert (
        "- The 2014 block is the heaviest. | for: DAI weight estimate | against: Wikipedia "
        f"gives a higher figure [S:{fx.S1}] [S:{fx.S2}]" in brief
    )
    assert "- contradiction: the weight of the 2014 block (A: 1000 tons / B: 1650 tons)" in brief


def test_sparse_answers_render_without_key_errors():
    data = fx.dossier_dict()
    synthesis = data["synthesis"]
    synthesis["cross_angle_connections"] = [{}, {"from_angle": {"finding": "x"}}]
    synthesis["synthesis"]["contested_claims"] = [{"claim": "Only a claim."}]
    synthesis["synthesis"]["convergent_findings"] = [{"pattern": "p"}]
    synthesis["synthesis"]["contradictions"] = [{"description": "d"}]
    del data["moderated"]["revised_claims"][0]["original"]
    data["debate"]["defenses"] = [{"response": "accept"}]
    data["debate"]["challenges"] = [{"suggestion": "s"}]
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes(data)))
    assert "{'" not in brief
    assert "- Only a claim. | for:  | against:" in brief
    assert f"- Estimates for the 2014 block differ. (sources differ) [S:{fx.S1}]" in brief


def test_brief_lists_the_research_angles():
    data = fx.dossier_dict()
    finding = data["angles"][1]["findings"][0]
    data["angles"][1]["findings"] = [finding] * 31
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes(data)))
    for angle in data["angles"]:
        assert f"#### {angle['topic']}" in brief
    assert f"- (high) The quarry stone is a local limestone. [S:{fx.S1}] [S:{fx.S5}]" in brief
    assert "Quarry workers lived nearby." not in brief  # shares no moderated source
    assert "(first 30 of 31; the rest are in dossier.json.gz under angles)" in brief


def test_citable_ids_are_the_exported_cited_set():
    dossier = parse_dossier(fx.dossier_gz_bytes())
    assert dossier.citable_ids == [fx.S1, fx.S2, fx.S4, fx.S3, fx.S5]
    brief = pull.render_brief(dossier)
    behind = brief.index("Sources of the angle findings behind these claims:")
    assert brief.index(f"- [S:{fx.S5}] T2 · Baalbek geology") > behind
    assert f"[S:{fx.S6}]" not in brief


def test_sources_list_tiers_first_and_names_unknown_ids():
    data = fx.dossier_dict()
    data["moderated"]["final_claims"][0]["source_ids"].append("eeeeeeeeeee5")
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes(data)))
    assert "not in the dossier (never cite): ['eeeeeeeeeee5']" in brief
    assert brief.index(f"[S:{fx.S1}] T1") < brief.index(f"[S:{fx.S2}] T2")


def test_a_legacy_export_renders_a_brief():
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes(fx.legacy_dossier_dict())))
    assert "{{" not in brief
    assert "4 cited: full text 2, abstract only 1, missing 0, TDM-reserved 1" in brief


def test_dossier_text_that_looks_like_a_placeholder_stays_text():
    """Placeholders are filled in one pass over the template: a claim quoting wiki markup
    ({{sfn}}) is not an unfilled placeholder, and a question naming one is not filled."""
    data = fx.dossier_dict()
    data["request"]["question"] = "Why does {{moderated}} appear here?"
    data["moderated"]["final_claims"][0]["claim"] = "A wiki page cites it {{sfn}}."
    brief = pull.render_brief(parse_dossier(fx.dossier_gz_bytes(data)))
    assert "# Writer brief: Why does {{moderated}} appear here?" in brief
    assert "A wiki page cites it {{sfn}}." in brief


def test_a_rewrite_brief_names_the_paper_it_rewrites():
    """`pull TARGET --dossier-from RUN`: every command takes TARGET's workspace."""
    data = fx.dossier_dict()
    data["request"]["id"] = RUN_ID
    dossier = parse_dossier(fx.dossier_gz_bytes(data))
    brief = pull.render_brief(dossier, target=TARGET)
    assert f"Request `{TARGET}`" in brief
    assert (
        f"rewrite of the public paper `{TARGET}` from the dossier of the fresh Theo run `{RUN_ID}`"
        in brief
    )
    assert f"`paper correct {TARGET} --republish`" in brief
    own = pull.render_brief(parse_dossier(fx.dossier_gz_bytes()))
    assert f"Request `{fx.REQ}`" in own and "rewrite of the public paper" not in own


def test_a_brief_that_cannot_be_rendered_leaves_the_workspace_untouched(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(remote, "check_module", lambda *a, **k: fx.dossier_gz_bytes())
    broken = tmp_path / "template.md"
    broken.write_text("{{question}} {{nope}}", encoding="utf-8")
    monkeypatch.setattr(pull, "TEMPLATE_PATH", broken)
    with pytest.raises(StudioError, match="unfilled placeholders"):
        pull.pull(fx.REQ)
    ws = workspace.workspace(fx.REQ)
    assert not ws.dossier_gz.exists() and not ws.texts_dir.exists()


def test_unfilled_placeholders_are_refused():
    with pytest.raises(StudioError, match="unfilled placeholders"):
        pull.render_brief(parse_dossier(fx.dossier_gz_bytes()), "{{question}} {{nope}}")


def test_pull_writes_dossier_texts_and_brief(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seen = {}

    def fake_check(module, args, *, timeout, stdin=None):
        seen["call"] = (module, args, timeout)
        return fx.dossier_gz_bytes()

    monkeypatch.setattr(remote, "check_module", fake_check)
    ws = pull.pull(fx.REQ)
    assert seen["call"] == (
        "pipeline.lyra.theo_dossier",
        ["export", fx.REQ, "--texts", "cited"],
        pull.EXPORT_TIMEOUT_S,
    )
    assert ws.dossier_gz.read_bytes() == fx.dossier_gz_bytes()
    assert sorted(p.name for p in ws.texts_dir.iterdir()) == [
        f"{fx.S1}.txt",
        f"{fx.S2}.txt",
        f"{fx.S3}.txt",
        f"{fx.S5}.txt",
    ]
    assert "Writer brief" in ws.brief.read_text(encoding="utf-8")


def test_pull_refuses_a_bundle_for_another_request(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(remote, "check_module", lambda *a, **k: fx.dossier_gz_bytes())
    with pytest.raises(StudioError, match="exported"):
        pull.pull("11111111-2222-3333-4444-555555555555")


TARGET = "11111111-2222-3333-4444-555555555555"


def test_a_rewrite_pulls_the_fresh_runs_dossier_into_the_public_papers_workspace(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    calls = []

    def fake_check(module, args, *, timeout, stdin=None):
        calls.append(args)
        data = fx.dossier_dict()
        data["request"]["id"] = args[1]  # the export of the id it was asked for
        return fx.dossier_gz_bytes(data)

    monkeypatch.setattr(remote, "check_module", fake_check)
    ws = pull.pull(TARGET, dossier_from=fx.REQ)
    assert calls == [["export", fx.REQ, "--texts", "cited"]]
    assert ws.root == tmp_path / "papers" / TARGET and ws.request_id == TARGET
    assert workspace.read_json(ws.dossier_from, "") == {"request_id": fx.REQ}
    assert workspace.load_dossier(ws).request_id == fx.REQ
    pull.pull(TARGET)  # a pull without --dossier-from takes TARGET's own dossier again
    assert calls[1] == ["export", TARGET, "--texts", "cited"]
    assert not ws.dossier_from.exists()
    assert workspace.load_dossier(ws).request_id == TARGET


def test_a_rewrite_pull_refuses_its_own_id_and_a_published_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(remote, "check_module", lambda *a, **k: fx.dossier_gz_bytes())
    with pytest.raises(StudioError, match="names the paper itself"):
        pull.pull(fx.REQ, dossier_from=fx.REQ)
    with pytest.raises(StudioError, match="is not a research request id"):
        pull.pull(TARGET, dossier_from=fx.REQ.upper())
    ws = workspace.workspace(TARGET)
    ws.root.mkdir(parents=True)
    ws.published_bundle.write_text("{}", encoding="utf-8")
    with pytest.raises(StudioError, match="holds a paper this studio published"):
        pull.pull(TARGET, dossier_from=fx.REQ)


def test_a_rewrite_pull_refuses_a_run_that_is_not_researched(monkeypatch, tmp_path):
    """A legacy `completed` paper or a run another republish already closed (`cancelled`) is
    no fresh run: refused at pull, before the write, the claim check and the images."""
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))

    def fake_check(module, args, *, timeout, stdin=None):
        data = fx.dossier_dict()
        data["request"]["id"] = args[1]
        data["request"]["status"] = "completed"
        return fx.dossier_gz_bytes(data)

    monkeypatch.setattr(remote, "check_module", fake_check)
    with pytest.raises(StudioError, match="is completed, not researched"):
        pull.pull(TARGET, dossier_from=fx.REQ)
    assert not workspace.workspace(TARGET).dossier_gz.exists()
    pull.pull(TARGET)  # the paper's own dossier: any status (a legacy paper is `completed`)
