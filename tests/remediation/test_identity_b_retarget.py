"""D13: the re-target question, its exact answer shape, the machine gates and the re-check.

DB-less and offline (`identity_b_fixtures`): every cited page is stored beforehand, every article
resolution is a dict. The case is Chania, the Cretan town whose record describes the town while the
ancient site is Kydonia.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from identity import common  # noqa: E402
from identity import retarget as RT  # noqa: E402
from identity import rounds as R  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_b_fixtures import (  # noqa: E402
    ENT,
    NOW,
    WP,
    entity,
    html,
    resolution,
    store,
)
from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402

CHANIA = "c4a1a000-0000-4000-8000-000000000001"
OTHER = "c4a1a000-0000-4000-8000-000000000002"
KYDONIA_TEXT = "Kydonia was an ancient city on the north coast of Crete."
COORD_TEXT = "Its centre lies at 35.519 N, 24.015 E."


def q(url: str, text: str) -> dict[str, str]:
    return {"url": url, "quote": text}


def context(**over: Any) -> dict[str, Any]:
    row = site(
        id=CHANIA,
        name="Chania",
        country="Greece",
        site_type="City/town/settlement",
        lat=35.5135,
        lon=24.0180,
        source_url=WP + "Chania",
        description="Chania is a city on the island of Crete, Greece.",
        description_chars=48,
    )
    funnel = {
        "tier": "A+rx",
        "p31": ["city"],
        "p31_modern": ["city"],
        "sentence1": "Chania is a city on the island of Crete, Greece.",
        "opening_match": "city",
        "shared_with": [],
    }
    cache = [{"lang": "en", "title": "Chania", "path": "C:/cache/en/abc.json"}]
    candidates = [{"id": OTHER, "name": "Kydonia", "why": "70 m away", "metres": 70.0}]
    ctx = RT.site_context(
        row,
        funnel,
        {"wikidata_qid": ["Q100"], "enwiki_title": ["Chania"]},
        candidates,
        cache,
        "2026-10-08 20:35:11+00",
    )
    ctx.update(over)
    return ctx


def target(**over: Any) -> dict[str, Any]:
    base = {
        "name": {"value": "Kydonia", "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)]},
        "qid": {"value": "Q200", "quotes": [q(ENT.format("Q200"), "Kydonia")]},
        "enwiki_title": {"value": "Kydonia", "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)]},
        "source_url": {"value": WP + "Kydonia", "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)]},
        "coordinates": {"lat": 35.519, "lon": 24.015, "quotes": [q(WP + "Kydonia", COORD_TEXT)]},
    }
    base.update(over)
    return base


def answer(verdict: str = "RETARGET", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": CHANIA,
        "verdict": verdict,
        "why": "The record describes the town; the ancient site is Kydonia.",
        "quotes": [q(WP + "Chania", "Chania is a city on the island of Crete")],
        "target": target() if verdict == "RETARGET" else None,
        "merge_with": None,
    }
    base.update(over)
    return base


def parse(data: dict[str, Any], ctx: dict[str, Any] | None = None) -> RT.Answer:
    return RT.parse_web(json.dumps(data), ctx or context())


# ------------------------------------------------------------------------------ the context
class TestTheContext:
    def test_the_context_carries_everything_the_question_is_a_function_of(self) -> None:
        ctx = context()
        assert ctx["qids"] == ["Q100"] and ctx["enwiki"] == ["Chania"]
        assert ctx["why"]["tier"] == "A+rx" and ctx["scope_status"] is None
        assert ctx["merge_candidates"][0]["id"] == OTHER
        json.dumps(ctx)  # JSON-able: it is stored with the round

    def test_merge_candidates_are_the_sharers_and_the_pairs_nearest_first(self) -> None:
        shared = [{"id": "s1", "name": "Shared"}]
        pairs = [
            {"a": "x", "b": "p1", "metres": 250.0, "similarity": 0.6},
            {"a": "p2", "b": "x", "metres": 40.0, "similarity": 0.9},
            {"a": "y", "b": "z", "metres": 1.0, "similarity": 1.0},
            {"a": "x", "b": "s1", "metres": 100.0, "similarity": 0.8},
        ]
        got = RT.merge_candidates("x", shared, pairs, {"p1": "One", "p2": "Two", "s1": "Shared"})
        assert [c["id"] for c in got] == ["p2", "s1", "p1"]
        assert "carries the same Wikidata item" in got[1]["why"] and "100 m away" in got[1]["why"]
        only_shared = RT.merge_candidates("x", shared, [], {})
        assert only_shared[0]["metres"] is None

    def test_the_cache_index_gives_absolute_paths_per_site(self, tmp_path: Path) -> None:
        (tmp_path / "INDEX.jsonl").write_text(
            json.dumps({"site_id": "s", "lang": "en", "title": "T", "file": "en\\abc.json"}) + "\n",
            encoding="utf-8",
        )
        got = RT.cache_entries(tmp_path)
        assert got["s"][0]["path"] == (tmp_path / "en" / "abc.json").as_posix()
        with pytest.raises(common.IdentityError, match="not built"):
            RT.cache_entries(tmp_path / "nowhere")

    def test_the_pilot_is_spread_over_the_funnel_order(self) -> None:
        qs = [R.Question(f"s{i:02d}", {}) for i in range(20)]
        assert RT.pilot_sites(qs, 4) == ["s00", "s05", "s10", "s15"]
        with pytest.raises(common.IdentityError):
            RT.pilot_sites(qs, 0)
        with pytest.raises(common.IdentityError):
            RT.pilot_sites(qs, 21)

    def test_holders_are_who_carries_each_item(self) -> None:
        a, b = site(), site(scope_status="retired")
        exported = export_of(
            [a, b],
            ext_ids=[ext(a["id"], "wikidata_qid", "Q9"), ext(b["id"], "wikidata_qid", "Q9"),
                     ext(a["id"], "enwiki_title", "T")],
        )  # fmt: skip
        held = RT.holders_of(exported)
        assert sorted(h["site_id"] for h in held["Q9"]) == sorted([a["id"], b["id"]])
        assert "T" not in held


class TestTheQuestion:
    def test_the_prompt_states_the_record_the_rules_and_the_answer_shape(self) -> None:
        text = RT.render_web(context())
        assert "id:           " + CHANIA in text and "35.5135, 24.018" in text
        assert "Wikidata:     Q100 (https://www.wikidata.org/wiki/Q100)" in text
        assert f"Chania ({WP}Chania)" in text
        assert "funnel tier A+rx" in text and "reads as a city" in text
        assert "RECORDS A MERGE MAY NAME" in text and f"Kydonia ({OTHER})" in text
        assert 'en.wikipedia "Chania": C:/cache/en/abc.json' in text
        assert "within 25 km of the stored point" in text
        assert '"verdict": "KEEP | RETARGET | RETIRE | MERGE"' in text
        assert "EARLIER ANSWER" not in text

    def test_a_re_ask_shows_why_the_earlier_answer_was_held(self) -> None:
        text = RT.render_web(context(), "target.qid: Q200 is not proven at the coordinates given")
        assert "AN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED" in text
        assert "target.qid: Q200 is not proven" in text

    def test_a_record_without_candidates_or_cache_has_neither_section(self) -> None:
        text = RT.render_web(context(merge_candidates=[], cache=[], qids=[], enwiki=[]))
        assert "RECORDS A MERGE MAY NAME" not in text and "CACHED WIKIPEDIA" not in text
        assert "Wikidata:     none" in text and "Wikipedia:    none" in text

    def test_the_prompt_is_a_pure_function_of_the_context(self) -> None:
        assert RT.render_web(context()) == RT.render_web(copy.deepcopy(context()))


# ------------------------------------------------------------------------------ the answer shape
class TestTheAnswerShape:
    def test_a_complete_retarget_parses(self) -> None:
        got = parse(answer())
        assert got.verdict == "RETARGET" and got.target is not None
        assert (got.target.qid.value, got.target.enwiki_title.value) == ("Q200", "Kydonia")
        assert (got.target.lat, got.target.lon) == (35.519, 24.015)

    def test_keep_retire_and_merge_parse_with_their_own_fields(self) -> None:
        assert parse(answer("KEEP")).verdict == "KEEP"
        assert parse(answer("RETIRE")).target is None
        assert parse(answer("MERGE", merge_with=OTHER)).merge_with == OTHER

    @pytest.mark.parametrize(
        ("over", "match"),
        [
            ({"site_id": OTHER}, "is not this question's"),
            ({"verdict": "MAYBE"}, "is not one of KEEP, RETARGET, RETIRE, MERGE"),
            ({"quotes": []}, "needs at least 1 quote"),
            ({"why": "  "}, "trimmed, non-empty"),
            ({"merge_with": OTHER}, "merge_with is null unless"),
            ({"target": None}, "carries"),
        ],
    )
    def test_the_envelope_rules(self, over: dict[str, Any], match: str) -> None:
        with pytest.raises(R.AnswerError, match=match):
            parse(answer(**over))

    def test_a_missing_or_extra_key_is_refused(self) -> None:
        data = answer()
        del data["why"]
        with pytest.raises(R.AnswerError, match="carries"):
            parse(data)
        with pytest.raises(R.AnswerError, match="not JSON"):
            RT.parse_web("{nope", context())

    @pytest.mark.parametrize("verdict", ["KEEP", "RETIRE", "MERGE"])
    def test_only_a_retarget_carries_a_target(self, verdict: str) -> None:
        data = answer(verdict, target=target(), merge_with=OTHER if verdict == "MERGE" else None)
        with pytest.raises(R.AnswerError, match="target is null unless the verdict is RETARGET"):
            parse(data)

    def test_a_merge_names_one_of_the_candidates(self) -> None:
        with pytest.raises(R.AnswerError, match="none of the candidates"):
            parse(answer("MERGE", merge_with="00000000-0000-4000-8000-00000000dead"))
        with pytest.raises(R.AnswerError, match="none of the candidates"):
            parse(answer("MERGE", merge_with=None))

    @pytest.mark.parametrize(
        ("key", "value", "match"),
        [
            ("qid", {"value": "Q100", "quotes": [q(ENT.format("Q100"), "Chania")]}, "own item"),
            ("qid", {"value": "kydonia", "quotes": [q(ENT.format("Q200"), "K")]}, "not an item id"),
            (
                "qid",
                {"value": "Q200", "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)]},
                "a quote cites",
            ),
            (
                "enwiki_title",
                {"value": "Chania", "quotes": [q(WP + "Chania", "Chania is a city")]},
                "own article",
            ),
            (
                "enwiki_title",
                {"value": "Kydonia#History", "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)]},
                "not an article title",
            ),
            (
                "enwiki_title",
                {"value": "Kydonia", "quotes": [q(WP + "Cydonia", KYDONIA_TEXT)]},
                "a quote cites https://en.wikipedia.org/wiki/Kydonia",
            ),
            (
                "name",
                {"value": "Cydonia", "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)]},
                "holds the name word for word",
            ),
            (
                "source_url",
                {"value": WP + "Chania", "quotes": [q(WP + "Chania", "Chania")]},
                "current source_url",
            ),
            (
                "source_url",
                {"value": WP + "Cydonia", "quotes": [q(WP + "Cydonia", "Cydonia")]},
                "names the article given as enwiki_title",
            ),
            (
                "source_url",
                {
                    "value": "https://ancientnerds.com/x",
                    "quotes": [q("https://ancientnerds.com/x", "x")],
                },
                "never fetched here",
            ),
            (
                "source_url",
                {
                    "value": "https://example.org/kydonia",
                    "quotes": [q(WP + "Kydonia", KYDONIA_TEXT)],
                },
                "a quote cites the page given",
            ),
        ],
    )
    def test_every_cell_rule_an_answer_can_break_on_its_own(
        self, key: str, value: dict[str, Any], match: str
    ) -> None:
        data = answer()
        data["target"][key] = value
        with pytest.raises(R.AnswerError, match=match):
            parse(data)

    @pytest.mark.parametrize(
        "coordinates",
        [
            {"lat": 91, "lon": 24.0, "quotes": [q(WP + "Kydonia", COORD_TEXT)]},
            {"lat": 35.5, "lon": "24", "quotes": [q(WP + "Kydonia", COORD_TEXT)]},
            {"lat": True, "lon": 24.0, "quotes": [q(WP + "Kydonia", COORD_TEXT)]},
            {"lat": 35.5, "lon": 24.0, "quotes": []},
        ],
    )
    def test_the_coordinates_are_numbers_with_a_quote(self, coordinates: dict[str, Any]) -> None:
        data = answer()
        data["target"]["coordinates"] = coordinates
        with pytest.raises(R.AnswerError):
            parse(data)

    def test_a_non_wikipedia_source_url_is_allowed_when_it_quotes_its_own_page(self) -> None:
        data = answer()
        page = "https://example.org/kydonia"
        data["target"]["source_url"] = {"value": page, "quotes": [q(page, "Kydonia")]}
        assert parse(data).target.source_url.value == page  # type: ignore[union-attr]

    def test_the_cited_urls_and_the_titles_to_resolve(self) -> None:
        got = parse(answer())
        assert RT.cited_web(got, {}) == {WP + "Chania", WP + "Kydonia", ENT.format("Q200")}
        assert RT.titles_web(got, {}) == {"Kydonia"}
        assert RT.titles_web(parse(answer("KEEP")), {}) == set()


# ------------------------------------------------------------------------------ the decision
@pytest.fixture
def library(tmp_path: Path) -> Q.Library:
    pages = tmp_path / "pages"
    store(
        pages,
        ENT.format("Q200"),
        entity("Q200", "Kydonia", 35.5190, 24.0150, {"en": ["Cydonia"]}, "ancient city in Crete"),
        content_type="application/json",
    )
    store(pages, WP + "Kydonia", html(KYDONIA_TEXT, COORD_TEXT))
    store(pages, WP + "Chania", html("Chania is a city on the island of Crete, Greece."))
    return Q.Library(REPO, pages)


TITLES = {"Kydonia": resolution("Q200", 35.519, 24.015, canonical_title="Kydonia")}


def decide(
    data: dict[str, Any],
    library: Q.Library,
    *,
    titles: dict[str, Any] | None = None,
    holders: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> R.Outcome:
    c = ctx or context()
    return RT.decide_web(
        parse(data, c), c, R.Env(library, TITLES if titles is None else titles), holders or {}
    )


class TestTheMachineGates:
    def test_a_sourced_target_at_the_site_s_place_is_decided_with_its_facts(
        self, library: Q.Library
    ) -> None:
        got = decide(answer(), library)
        assert got.status == R.DECIDED, got.reason
        cells = got.data["target"]
        assert cells["qid"]["note"].startswith("Q200 ('Kydonia'): P625 ")
        assert "resolved as the refresh resolves it" in cells["enwiki_title"]["note"]
        assert cells["name"]["note"] == "'Kydonia' is a name of Q200"
        assert cells["coordinates"]["note"].endswith("m from the stored point")
        assert got.data["facts"]["label"] == "Kydonia"
        assert got.data["facts"]["description"] == "ancient city in Crete"
        assert 0 < got.data["facts"]["moved_m"] < 2000
        assert all(q["outcome"] == "found" for q in cells["name"]["quotes"])

    def test_keep_retire_and_merge_are_decided_on_their_quotes_alone(
        self, library: Q.Library
    ) -> None:
        for verdict in ("KEEP", "RETIRE"):
            assert decide(answer(verdict), library).status == R.DECIDED
        merged = decide(answer("MERGE", merge_with=OTHER), library)
        assert merged.status == R.DECIDED and merged.data["merge_with"] == OTHER

    def test_a_quote_the_page_does_not_hold_holds_the_site(self, library: Q.Library) -> None:
        data = answer()
        data["target"]["name"]["quotes"] = [q(WP + "Kydonia", "Kydonia was founded by aliens")]
        got = decide(data, library)
        assert got.status == R.HELD and got.reason.startswith("target.name: a quote does not count")
        bad = answer("KEEP", quotes=[q(WP + "Chania", "Chania is a village in Wales")])
        assert decide(bad, library).reason.startswith("quotes: a quote does not count")

    @pytest.mark.parametrize(
        ("titles", "match"),
        [
            ({"Kydonia": resolution("Q200", 35.5, 24.0, canonical_title=None)}, "no English Wikipedia page"),
            ({"Kydonia": resolution("Q200", 35.5, 24.0, canonical_title="Kydonia", disambiguation=True)}, "disambiguation"),
            ({"Kydonia": resolution("Q200", 35.5, 24.0, canonical_title="Kydonia", redirected=True)}, "redirects"),
            ({"Kydonia": resolution("Q999", 35.5, 24.0, canonical_title="Kydonia")}, "the daily refresh would write another pair"),
        ],
    )  # fmt: skip
    def test_the_article_gates_are_l5_s(
        self, library: Q.Library, titles: dict[str, Any], match: str
    ) -> None:
        got = decide(answer(), library, titles=titles)
        assert got.status == R.HELD and match in got.reason

    def test_an_item_not_at_the_coordinates_given_holds_the_site(self, library: Q.Library) -> None:
        data = answer()
        data["target"]["coordinates"]["lat"] = 35.55  # ~3.5 km from the item and the article
        got = decide(data, library)
        assert got.status == R.HELD and "is not proven at the coordinates given" in got.reason
        assert "P625" in got.reason and "the article" in got.reason

    def test_the_article_s_coordinates_prove_an_item_without_a_point(self, tmp_path: Path) -> None:
        pages = tmp_path / "pages"
        store(
            pages,
            ENT.format("Q200"),
            entity("Q200", "Kydonia", None, None),
            content_type="application/json",
        )
        store(pages, WP + "Kydonia", html(KYDONIA_TEXT, COORD_TEXT))
        store(pages, WP + "Chania", html("Chania is a city on the island of Crete, Greece."))
        got = decide(answer(), Q.Library(REPO, pages))
        assert got.status == R.DECIDED
        assert got.data["target"]["qid"]["note"].startswith("Q200 ('Kydonia'): the article ")

    def test_a_name_that_is_no_attested_form_holds_the_site(self, library: Q.Library) -> None:
        data = answer()
        data["target"]["name"] = {
            "value": "Kydonia Ruins",
            "quotes": [
                q(WP + "Kydonia", "Kydonia was an ancient city on the north coast of Crete.")
            ],
        }
        data["target"]["name"]["quotes"][0]["quote"] = "Kydonia Ruins"
        store_pages = library.pages
        store(
            store_pages,
            WP + "Kydonia",
            html(KYDONIA_TEXT, COORD_TEXT, "Kydonia Ruins are visible."),
        )
        library2 = Q.Library(REPO, store_pages)
        got = decide(data, library2)
        assert got.status == R.HELD and "is no English label or alias of Q200" in got.reason

    def test_an_alias_of_the_item_or_the_article_s_title_is_an_attested_name(
        self, library: Q.Library
    ) -> None:
        data = answer()
        data["target"]["name"] = {"value": "Cydonia", "quotes": [q(WP + "Kydonia", "Cydonia")]}
        store(
            library.pages, WP + "Kydonia", html(KYDONIA_TEXT, COORD_TEXT, "Cydonia is a variant.")
        )
        assert decide(data, Q.Library(REPO, library.pages)).status == R.DECIDED

    def test_a_target_far_from_the_stored_point_is_a_coordinate_question(
        self, library: Q.Library
    ) -> None:
        ctx = context(lat=36.5, lon=25.5)
        got = decide(answer(), library, ctx=ctx)
        assert got.status == R.HELD and "more than 25 km" in got.reason
        assert "a coordinate question, not a re-target" in got.reason

    def test_an_item_another_visible_record_carries_is_a_merge_not_a_retarget(
        self, library: Q.Library
    ) -> None:
        holders = {"Q200": [{"site_id": OTHER, "name": "Kydonia", "scope_status": None}]}
        got = decide(answer(), library, holders=holders)
        assert got.status == R.HELD and "that is a MERGE, not a re-target" in got.reason
        retired = {"Q200": [{"site_id": OTHER, "name": "Kydonia", "scope_status": "retired"}]}
        assert decide(answer(), library, holders=retired).status == R.DECIDED
        own = {"Q200": [{"site_id": CHANIA, "name": "Chania", "scope_status": None}]}
        assert decide(answer(), library, holders=own).status == R.DECIDED

    def test_an_entity_page_that_cannot_be_read_holds_the_site(self, tmp_path: Path) -> None:
        pages = tmp_path / "pages"
        store(pages, ENT.format("Q200"), b"", content_type="application/json", status=404)
        store(pages, WP + "Kydonia", html(KYDONIA_TEXT, COORD_TEXT))
        store(pages, WP + "Chania", html("Chania is a city on the island of Crete, Greece."))
        got = decide(answer(), Q.Library(REPO, pages))
        assert got.status == R.HELD and "fetch failed" in got.reason

    def test_a_redirect_entity_page_holds_the_site(self, tmp_path: Path) -> None:
        pages = tmp_path / "pages"
        store(
            pages,
            ENT.format("Q200"),
            entity("Q999", "Kydonia", 35.519, 24.015),
            content_type="application/json",
        )
        store(pages, WP + "Kydonia", html(KYDONIA_TEXT, COORD_TEXT))
        store(pages, WP + "Chania", html("Chania is a city on the island of Crete, Greece."))
        got = decide(answer(), Q.Library(REPO, pages))
        assert got.status == R.HELD and "a redirect" in got.reason


class TestTheSpec:
    def test_the_web_stage_is_the_web_verifier_s(self) -> None:
        spec = RT.web_spec({})
        assert (spec.stage, spec.role, spec.model) == (
            "retarget-web",
            "web_verifier",
            "claude-sonnet-5-5",
        )
        assert RT.recheck_spec().role == "adversarial"
        assert RT.recheck_spec().model == "claude-opus-5-5"

    def test_the_spec_decides_through_the_holders_it_was_built_with(
        self, library: Q.Library
    ) -> None:
        holders = {"Q200": [{"site_id": OTHER, "name": "K", "scope_status": None}]}
        spec = RT.web_spec(holders)
        c = context()
        got = spec.decide(parse(answer(), c), c, R.Env(library, TITLES))
        assert got.status == R.HELD


# ------------------------------------------------------------------------------ the re-check
def web_decision(library: Q.Library, data: dict[str, Any] | None = None) -> dict[str, Any]:
    out = decide(data or answer(), library)
    return {"site_id": CHANIA, "status": out.status, "reason": out.reason, "data": out.data}


class TestTheRecheck:
    def test_it_asks_every_decided_verdict_that_is_not_keep_with_its_proposal(
        self, library: Q.Library
    ) -> None:
        asked = [R.Question(CHANIA, context()), R.Question(OTHER, context(site_id=OTHER))]
        decisions = {CHANIA: web_decision(library)}
        got = RT.recheck_questions(asked, decisions)
        assert [q_.site_id for q_ in got] == [CHANIA]
        proposal = got[0].context["proposal"]
        assert proposal["verdict"] == "RETARGET" and proposal["target"]["qid"]["value"] == "Q200"
        keep = {CHANIA: web_decision(library, answer("KEEP"))}
        assert RT.recheck_questions(asked, keep) == []
        held = {CHANIA: {**web_decision(library), "status": R.HELD}}
        assert RT.recheck_questions(asked, held) == []

    def test_the_prompt_shows_the_proposal_and_asks_to_refute_it(self, library: Q.Library) -> None:
        ctx = RT.recheck_questions(
            [R.Question(CHANIA, context())], {CHANIA: web_decision(library)}
        )[0].context
        text = RT.render_recheck(ctx)
        assert "try to REFUTE" in text and "THE PROPOSAL (verdict RETARGET)" in text
        assert "target.qid: Q200" in text and "target.coordinates: 35.519, 24.015" in text
        assert "the item's own label and description: 'Kydonia', 'ancient city in Crete'" in text
        assert "Is the proposed target exactly the ancient site" in text
        retire = RT.recheck_questions(
            [R.Question(CHANIA, context())], {CHANIA: web_decision(library, answer("RETIRE"))}
        )[0].context
        assert "nothing ancient is designated" in RT.render_recheck(retire)
        merge = RT.recheck_questions(
            [R.Question(CHANIA, context())],
            {CHANIA: web_decision(library, answer("MERGE", merge_with=OTHER))},
        )[0].context
        assert f"merge_with: {OTHER}" in RT.render_recheck(merge)

    def test_the_answer_confirms_with_a_quote_or_rejects_with_a_reason(self) -> None:
        ctx = {"site_id": CHANIA}
        ok = {
            "site_id": CHANIA,
            "verdict": "CONFIRM",
            "why": "read it",
            "quotes": [q(WP + "Kydonia", "Kydonia")],
        }
        assert RT.parse_recheck(json.dumps(ok), ctx).verdict == "CONFIRM"
        no_quote = {**ok, "quotes": []}
        with pytest.raises(R.AnswerError, match="needs at least 1 quote"):
            RT.parse_recheck(json.dumps(no_quote), ctx)
        reject = {**no_quote, "verdict": "REJECT"}
        assert RT.parse_recheck(json.dumps(reject), ctx).verdict == "REJECT"
        with pytest.raises(R.AnswerError, match="not CONFIRM or REJECT"):
            RT.parse_recheck(json.dumps({**ok, "verdict": "KEEP"}), ctx)
        with pytest.raises(R.AnswerError, match="is not this question's"):
            RT.parse_recheck(json.dumps({**ok, "site_id": OTHER}), ctx)

    def test_a_confirmation_whose_quote_is_not_found_is_held(self, library: Q.Library) -> None:
        ctx = {"site_id": CHANIA, "proposal": {"verdict": "RETARGET"}}
        review = RT.Review(CHANIA, "CONFIRM", "w", (q(WP + "Kydonia", "Kydonia was in Peru"),))
        got = RT.decide_recheck(review, ctx, R.Env(library, {}))
        assert got.status == R.HELD and got.reason.startswith("quotes: a quote does not count")
        good = RT.Review(CHANIA, "CONFIRM", "w", (q(WP + "Kydonia", KYDONIA_TEXT),))
        decided = RT.decide_recheck(good, ctx, R.Env(library, {}))
        assert decided.status == R.DECIDED and decided.data["proposed"] == "RETARGET"


class TestTheFinalState:
    def test_a_site_is_final_only_when_both_stages_agree(self) -> None:
        def web(verdict: str, status: str = R.DECIDED) -> dict[str, Any]:
            return {"status": status, "data": {"verdict": verdict}}

        def second(verdict: str, status: str = R.DECIDED) -> dict[str, Any]:
            return {"status": status, "data": {"verdict": verdict}}

        webs = {
            "a": web("KEEP"),
            "b": web("RETARGET"),
            "c": web("RETARGET"),
            "d": web("RETIRE"),
            "e": web("MERGE", R.HELD),
            "f": web("RETARGET"),
        }
        rechecks = {"b": second("CONFIRM"), "c": second("REJECT"), "f": second("CONFIRM", R.HELD)}
        got = {r["site_id"]: (r["verdict"], r["state"]) for r in RT.final_state(webs, rechecks)}
        assert got == {
            "a": ("KEEP", "keep"),
            "b": ("RETARGET", "confirmed"),
            "c": ("RETARGET", "rejected"),
            "d": ("RETIRE", "waiting-for-recheck"),
            "e": (None, "held"),
            "f": ("RETARGET", "waiting-for-recheck"),
        }
        assert NOW  # the fixtures' clock is shared


class TestTheEdges:
    def test_the_questions_are_the_funnel_records_and_an_unknown_site_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = site(id=CHANIA, name="Chania")
        monkeypatch.setattr(RT.export, "load_export", lambda path: export_of([row]))
        monkeypatch.setattr(RT, "cache_entries", lambda cache: {})
        monkeypatch.setattr(RT, "wiki_cache_dir", lambda root=None: tmp_path)
        funnel = {"id": CHANIA, "tier": "A", "p31": ["city"], "p31_modern": ["city"], "sentence1": "Chania is a city.",
                  "opening_match": "city", "shared_with": []}  # fmt: skip
        (tmp_path / "IDENTITY_FUNNEL.jsonl").write_text(json.dumps(funnel) + "\n", encoding="utf-8")
        (got,) = RT.web_questions(tmp_path)
        assert (
            got.site_id == CHANIA
            and got.context["why"]["tier"] == "A"
            and got.context["cache"] == []
        )
        assert RT.web_questions(tmp_path, exclude=[CHANIA]) == []
        assert [q_.site_id for q_ in RT.web_questions(tmp_path, sites=[CHANIA])] == [CHANIA]
        with pytest.raises(common.IdentityError, match="1 site.s. are not in the funnel"):
            RT.web_questions(tmp_path, sites=["00000000-0000-4000-8000-00000000dead"])

    def test_a_name_longer_than_a_name_column_is_refused(self) -> None:
        long_name = "K" * 501
        data = answer()
        data["target"]["name"] = {"value": long_name, "quotes": [q(WP + "Kydonia", long_name)]}
        with pytest.raises(R.AnswerError, match="longer than 500 characters"):
            parse(data)

    @pytest.mark.parametrize(
        "url",
        ["ftp://example.org/kydonia", "http://localhost/kydonia", "https://example.org/a\x01b"],
    )
    def test_a_source_url_that_is_no_public_page_is_refused(self, url: str) -> None:
        data = answer()
        data["target"]["source_url"] = {"value": url, "quotes": [q(url, "Kydonia")]}
        with pytest.raises(R.AnswerError):
            parse(data)

    @pytest.mark.parametrize("verdict", ["KEEP", "RETIRE"])
    def test_only_a_merge_names_a_record_to_merge_with(self, verdict: str) -> None:
        with pytest.raises(R.AnswerError, match="merge_with is null unless the verdict is MERGE"):
            parse(answer(verdict, merge_with=OTHER))
