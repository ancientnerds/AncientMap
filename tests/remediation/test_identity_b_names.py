"""D23: the clean-name question, the spoken-name question and their plans.

DB-less and offline (`identity_b_fixtures`). The cases: a Spanish-prefixed dolmen whose item carries
the English name, a name the triage repaired by rule, and a French menhir the rule could not make a
spoken name for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from identity import name_write as NW  # noqa: E402
from identity import names_judge as NJ  # noqa: E402
from identity import rounds as R  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_b_fixtures import ENT, WP, entity, html, store  # noqa: E402
from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402

DOLMEN = "d2300000-0000-4000-8000-000000000001"
ALBANIANA = "d2300000-0000-4000-8000-000000000002"
MENHIR = "d2300000-0000-4000-8000-000000000003"
OTHER = "d2300000-0000-4000-8000-000000000004"
DOLMEN_TEXT = "The Menga Dolmen is a megalithic burial monument near Antequera."
ALBANIANA_TEXT = "Albaniana was a Roman fort at Alphen aan den Rijn."


def q(url: str, text: str) -> dict[str, str]:
    return {"url": url, "quote": text}


def triage(sid: str = DOLMEN, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": sid, "name": "Dolmen de Menga", "country": "Spain", "site_type": "Dolmen",
        "defects": ["foreign_prefix"], "differs_from_label": False, "enwiki": ["Menga Dolmen"],
        "label": "Menga Dolmen", "aliases": ["Dolmen of Menga"], "severity": "hard",
        "suggestion": None, "needs_model": True,
    }  # fmt: skip
    base.update(over)
    return base


def context(sid: str = DOLMEN, **over: Any) -> dict[str, Any]:
    row = site(id=sid, name="Dolmen de Menga", description="Un dolmen near Antequera.")
    ctx = NJ.clean_context(
        triage(sid, **{k: v for k, v in over.items() if k in triage()}),
        row,
        {"wikidata_qid": ["Q300"], "enwiki_title": ["Menga Dolmen"]},
        [{"lang": "en", "title": "Menga Dolmen", "path": "C:/cache/en/m.json"}],
        "2026-10-08 20:35:11+00",
    )
    ctx.update({k: v for k, v in over.items() if k in ctx})
    return ctx


def clean(verdict: str = "RENAME", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": DOLMEN, "verdict": verdict, "why": "Its item's English label is Menga Dolmen.",
        "new_name": "Menga Dolmen" if verdict == "RENAME" else None,
        "attested_as": "label" if verdict == "RENAME" else None,
        "quotes": [q(WP + "Menga_Dolmen", DOLMEN_TEXT)] if verdict == "RENAME" else [],
    }  # fmt: skip
    base.update(over)
    return base


def parse(data: dict[str, Any], ctx: dict[str, Any] | None = None) -> NJ.Clean:
    return NJ.parse_clean(json.dumps(data), ctx or context())


# ------------------------------------------------------------------------------ the question
class TestTheCleanQuestion:
    def test_the_prompt_names_the_defects_the_known_forms_and_the_rules(self) -> None:
        text = NJ.render_clean(context())
        assert "name:         Dolmen de Menga" in text
        assert "it opens with a foreign word for the kind of the thing" in text
        assert "English label: Menga Dolmen" in text and "English aliases: Dolmen of Menga" in text
        assert 'en.wikipedia "Menga Dolmen": C:/cache/en/m.json' in text
        assert "A name that merely differs from the item's label is NOT a defect" in text
        assert '"verdict": "KEEP | RENAME"' in text and "EARLIER ANSWER" not in text
        assert "AN EARLIER ANSWER" in NJ.render_clean(context(), "name: not attested")

    def test_a_differs_from_label_note_is_marked_as_no_defect(self) -> None:
        text = NJ.render_clean(context(differs_from_label=True, defects=["comma_qualifier"]))
        assert "(a note, not a defect) it shares almost no word" in text
        assert "it holds a comma qualifier" in text

    def test_every_triage_defect_has_a_wording(self) -> None:
        from identity import names_triage

        assert set(NJ.DEFECT_WORDS) == set(names_triage.DEFECTS)

    def test_the_questions_are_the_triage_records_that_need_a_model_or_those_it_repaired(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shown = [
            site(id=DOLMEN, name="Dolmen de Menga"),
            site(id=ALBANIANA, name="Albaniana (Roman Fort)"),
        ]
        monkeypatch.setattr(
            NJ.export, "load_export",
            lambda path: export_of(shown, ext_ids=[ext(DOLMEN, "wikidata_qid", "Q300")]),
        )  # fmt: skip
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "INDEX.jsonl").write_text("", encoding="utf-8")
        monkeypatch.setattr(NJ, "wiki_cache_dir", lambda root=None: cache)
        records = [
            triage(),
            triage(ALBANIANA, name="Albaniana (Roman Fort)", defects=["parenthesis"], needs_model=False,
                   suggestion={"kind": "attested_form", "source": "label", "value": "Albaniana"}),
        ]  # fmt: skip
        (tmp_path / NJ.TRIAGE_FILE).write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )
        assert [x.site_id for x in NJ.clean_questions(tmp_path)] == [DOLMEN]
        assert [x.site_id for x in NJ.clean_questions(tmp_path, rule_made=True)] == [ALBANIANA]
        assert NJ.clean_questions(tmp_path, exclude=[DOLMEN]) == []


class TestTheCleanAnswerShape:
    def test_a_rename_and_a_keep_parse(self) -> None:
        assert parse(clean()).new_name == "Menga Dolmen"
        assert parse(clean("KEEP")).verdict == "KEEP"
        assert parse(clean("KEEP", quotes=[q(WP + "x", "y")])).quotes

    @pytest.mark.parametrize(
        ("over", "match"),
        [
            ({"site_id": OTHER}, "is not this question's"),
            ({"verdict": "CHANGE"}, "is not KEEP or RENAME"),
            ({"new_name": "Dolmen de Menga"}, "that is KEEP"),
            ({"new_name": " Menga Dolmen"}, "trimmed, non-empty"),
            ({"new_name": "M" * 501}, "longer than 500"),
            ({"attested_as": "translation"}, "is not one of label, alias, enwiki_title"),
            ({"quotes": []}, "needs at least 1 quote"),
            ({"quotes": [q(WP + "x", "an unrelated sentence")]}, "with the new name in the quote"),
            ({"why": ""}, "trimmed, non-empty"),
        ],
    )
    def test_the_rules_a_rename_can_break_on_its_own(
        self, over: dict[str, Any], match: str
    ) -> None:
        with pytest.raises(R.AnswerError, match=match):
            parse(clean(**over))

    def test_a_keep_carries_no_name(self) -> None:
        with pytest.raises(R.AnswerError, match="null for KEEP"):
            parse(clean("KEEP", new_name="X"))

    def test_a_rename_reads_the_entity_page_of_every_item_cited_or_not(self) -> None:
        ctx = context()
        urls = NJ.cited_clean(parse(clean()), ctx)
        assert urls == {WP + "Menga_Dolmen", ENT.format("Q300")}
        assert NJ.cited_clean(parse(clean("KEEP")), ctx) == set()


@pytest.fixture
def library(tmp_path: Path) -> Q.Library:
    pages = tmp_path / "pages"
    store(
        pages, ENT.format("Q300"),
        entity("Q300", "Menga Dolmen", 37.0, -4.5, {"en": ["Dolmen of Menga"], "es": ["Dolmen de Menga"]}),
        content_type="application/json",
    )  # fmt: skip
    store(pages, WP + "Menga_Dolmen", html(DOLMEN_TEXT))
    store(pages, WP + "Albaniana", html(ALBANIANA_TEXT))
    return Q.Library(REPO, pages)


def decide(
    data: dict[str, Any], library: Q.Library, ctx: dict[str, Any] | None = None
) -> R.Outcome:
    c = ctx or context()
    return NJ.decide_clean(parse(data, c), c, R.Env(library, {}))


class TestTheCleanGates:
    def test_a_name_the_items_entity_page_attests_is_decided(self, library: Q.Library) -> None:
        got = decide(clean(), library)
        assert got.status == R.DECIDED, got.reason
        assert got.data["note"].endswith("is a name of the record's own item or article")

    def test_an_english_alias_is_attested_and_a_spanish_one_is_not(
        self, library: Q.Library
    ) -> None:
        alias = clean(new_name="Dolmen of Menga", attested_as="alias",
                      quotes=[q(ENT.format("Q300"), "Dolmen of Menga")])  # fmt: skip
        assert decide(alias, library).status == R.DECIDED
        spanish = clean(
            new_name="Dolmen de Menga", quotes=[q(ENT.format("Q300"), "Dolmen de Menga")]
        )
        with pytest.raises(R.AnswerError, match="that is KEEP"):
            parse(spanish)

    def test_the_title_of_the_article_attests_a_name_with_and_without_its_qualifier(
        self, library: Q.Library
    ) -> None:
        ctx = context(enwiki=["Albaniana (Roman fort)"], qids=[])
        text = clean(new_name="Albaniana (Roman fort)", attested_as="enwiki_title",
                     quotes=[q(WP + "Albaniana", "Albaniana (Roman fort) was a Roman fort")])  # fmt: skip
        store(
            library.pages,
            WP + "Albaniana",
            html("Albaniana (Roman fort) was a Roman fort at Alphen."),
        )
        assert decide(text, Q.Library(REPO, library.pages), ctx).status == R.DECIDED
        short = clean(
            new_name="Albaniana",
            attested_as="enwiki_title",
            quotes=[q(WP + "Albaniana", "Albaniana (Roman fort)")],
        )
        assert decide(short, Q.Library(REPO, library.pages), ctx).status == R.DECIDED

    def test_a_name_no_form_attests_holds_the_site(self, library: Q.Library) -> None:
        store(
            library.pages,
            WP + "Menga_Dolmen",
            html(DOLMEN_TEXT, "Antequera Dolmens are three monuments."),
        )
        data = clean(
            new_name="Antequera Dolmens", quotes=[q(WP + "Menga_Dolmen", "Antequera Dolmens are")]
        )
        got = decide(data, Q.Library(REPO, library.pages))
        assert (
            got.status == R.HELD
            and "is no English label or alias of the record's item" in got.reason
        )

    def test_a_quote_the_page_does_not_hold_holds_the_site(self, library: Q.Library) -> None:
        got = decide(clean(quotes=[q(WP + "Menga_Dolmen", "Menga Dolmen is in Peru")]), library)
        assert got.status == R.HELD and got.reason.startswith("quotes: a quote does not count")

    def test_a_record_with_neither_item_nor_article_attests_nothing(
        self, library: Q.Library
    ) -> None:
        got = decide(clean(), library, context(qids=[], enwiki=[]))
        assert got.status == R.HELD and "nothing attests a name" in got.reason

    def test_an_entity_page_that_is_a_redirect_holds_the_site(self, tmp_path: Path) -> None:
        pages = tmp_path / "pages"
        store(
            pages,
            ENT.format("Q300"),
            entity("Q999", "Menga Dolmen", 1.0, 1.0),
            content_type="application/json",
        )
        store(pages, WP + "Menga_Dolmen", html(DOLMEN_TEXT))
        got = decide(clean(), Q.Library(REPO, pages))
        assert got.status == R.HELD and "a redirect" in got.reason

    def test_a_keep_is_decided_on_its_quotes_alone(self, library: Q.Library) -> None:
        assert decide(clean("KEEP"), library).status == R.DECIDED


# ------------------------------------------------------------------------------ the re-check
def web_decision(library: Q.Library, **over: Any) -> dict[str, Any]:
    out = decide(clean(**over), library)
    return {"site_id": DOLMEN, "status": out.status, "round": "r1", "answered_by": "web_verifier:r1-b01",
            "reason": out.reason, "data": out.data}  # fmt: skip


def rule_ctx() -> dict[str, Any]:
    return context(
        ALBANIANA, name="Albaniana (Roman Fort)", defects=["parenthesis"], needs_model=False,
        suggestion={"kind": "attested_form", "source": "label", "value": "Albaniana"},
    )  # fmt: skip


class TestTheRecheck:
    def test_every_rename_is_re_checked_the_model_made_and_the_rule_made(
        self, library: Q.Library
    ) -> None:
        web = [R.Question(DOLMEN, context()), R.Question(OTHER, context(OTHER))]
        decisions = {
            DOLMEN: web_decision(library),
            OTHER: {**web_decision(library, verdict="KEEP"), "site_id": OTHER},
        }
        decisions[OTHER] = {**web_decision(library, **clean("KEEP")), "site_id": OTHER}
        rule = [R.Question(ALBANIANA, rule_ctx())]
        got = NJ.recheck_questions(web, decisions, rule)
        assert [x.site_id for x in got] == [DOLMEN, ALBANIANA]
        by = {x.site_id: x.context["proposal"] for x in got}
        assert by[DOLMEN]["source"] == "model" and by[DOLMEN]["new_name"] == "Menga Dolmen"
        assert by[DOLMEN]["quotes"][0]["quote"] == DOLMEN_TEXT
        assert by[ALBANIANA]["source"] == "rule" and by[ALBANIANA]["new_name"] == "Albaniana"
        assert "repaired the name by rule (attested_form)" in by[ALBANIANA]["why"]

    def test_the_prompt_shows_the_proposal_and_asks_for_the_names_page(
        self, library: Q.Library
    ) -> None:
        (ask,) = NJ.recheck_questions(
            [R.Question(DOLMEN, context())], {DOLMEN: web_decision(library)}, []
        )
        text = NJ.render_recheck(ask.context)
        assert 'rename "Dolmen de Menga" -> "Menga Dolmen"   (attested as label)' in text
        assert "made by a web verifier" in text and "Try to REFUTE" in text
        assert "swap of one good name for another" in text
        (rule_ask,) = NJ.recheck_questions([], {}, [R.Question(ALBANIANA, rule_ctx())])
        assert "made by the triage's rule" in NJ.render_recheck(rule_ask.context)

    def test_a_confirmation_quotes_a_page_that_holds_the_new_name(self, library: Q.Library) -> None:
        ctx = {"site_id": DOLMEN, "proposal": {"new_name": "Menga Dolmen"}}
        good = {
            "site_id": DOLMEN,
            "verdict": "CONFIRM",
            "why": "read",
            "quotes": [q(WP + "Menga_Dolmen", DOLMEN_TEXT)],
        }
        review = NJ.parse_recheck(json.dumps(good), ctx)
        assert NJ.decide_recheck(review, ctx, R.Env(library, {})).status == R.DECIDED
        elsewhere = {**good, "quotes": [q(WP + "Menga_Dolmen", "a megalithic burial monument")]}
        with pytest.raises(R.AnswerError, match="holds the new name"):
            NJ.parse_recheck(json.dumps(elsewhere), ctx)
        reject = {**good, "verdict": "REJECT", "quotes": []}
        assert NJ.parse_recheck(json.dumps(reject), ctx).verdict == "REJECT"
        with pytest.raises(R.AnswerError, match="not CONFIRM or REJECT"):
            NJ.parse_recheck(json.dumps({**good, "verdict": "KEEP"}), ctx)
        bad = NJ.Review(DOLMEN, "CONFIRM", "w", (q(WP + "Menga_Dolmen", "not on the page"),))
        assert NJ.decide_recheck(bad, ctx, R.Env(library, {})).status == R.HELD

    def test_the_final_state_of_a_model_made_and_a_rule_made_rename(self) -> None:
        def d(verdict: str, status: str = R.DECIDED) -> dict[str, Any]:
            return {"status": status, "data": {"verdict": verdict}}

        web = {
            "a": d("KEEP"),
            "b": d("RENAME"),
            "c": d("RENAME"),
            "e": d("RENAME", R.HELD),
            "f": d("RENAME"),
        }
        second = {
            "b": d("CONFIRM"),
            "c": d("REJECT"),
            "r1": d("CONFIRM"),
            "r2": d("REJECT"),
            "f": d("CONFIRM", R.HELD),
        }
        got = {
            r["site_id"]: (r["source"], r["state"])
            for r in NJ.final_state(web, second, ["r1", "r2", "r3"])
        }
        assert got == {
            "a": ("model", "keep"), "b": ("model", "confirmed"), "c": ("model", "rejected"),
            "e": ("model", "held"), "f": ("model", "waiting-for-recheck"),
            "r1": ("rule", "confirmed"), "r2": ("rule", "rejected"), "r3": ("rule", "waiting-for-recheck"),
        }  # fmt: skip


# ------------------------------------------------------------------------------ the plan
def renames(library: Q.Library) -> dict[str, dict[str, Any]]:
    web = {DOLMEN: web_decision(library)}
    recheck = {
        DOLMEN: {"site_id": DOLMEN, "status": R.DECIDED, "round": "r1", "answered_by": "adversarial:r1-b01",
                 "data": {"verdict": "CONFIRM", "why": "read the item", "quotes": [
                     {**q(WP + "Menga_Dolmen", DOLMEN_TEXT), "outcome": "found", "detail": "visible text"}]}},
        ALBANIANA: {"site_id": ALBANIANA, "status": R.DECIDED, "round": "r1", "answered_by": "adversarial:r1-b02",
                    "data": {"verdict": "CONFIRM", "why": "read the fort", "quotes": [
                        {**q(WP + "Albaniana", ALBANIANA_TEXT), "outcome": "found", "detail": "visible text"}]}},
    }  # fmt: skip
    return NJ.confirmed_renames({}, web, {ALBANIANA: rule_ctx()}, recheck)


def live_row(
    sid: str = DOLMEN, name: str = "Dolmen de Menga", key: str = "dolmen de menga", **over: Any
) -> dict[str, Any]:
    row = {
        "site_id": sid, "source_id": "ancient_nerds", "name": name, "name_normalized": key,
        "scope_status": None,
        "ext": [{"kind": "enwiki_title", "value": "Menga Dolmen"}, {"kind": "wikidata_qid", "value": "Q300"}],
        "premise": "enwiki_title=Menga Dolmen, wikidata_qid=Q300",
    }  # fmt: skip
    row.update(over)
    return row


class TestThePlan:
    def test_the_confirmed_renames_carry_the_evidence_of_both_stages(
        self, library: Q.Library
    ) -> None:
        got = renames(library)
        assert set(got) == {DOLMEN, ALBANIANA}
        model, rule = got[DOLMEN], got[ALBANIANA]
        assert (model["source"], model["who"], model["new_name"]) == (
            "model",
            "web_verifier:r1-b01",
            "Menga Dolmen",
        )
        assert {x["url"] for x in model["quotes"]} == {
            WP + "Menga_Dolmen"
        } and "adversarial:r1-b01" in model["recheck"]
        assert (rule["source"], rule["who"], rule["new_name"]) == (
            "rule",
            "rule:names_triage",
            "Albaniana",
        )

    def build(self, library: Q.Library, live: dict[str, Any], **kw: Any) -> NW.NamePlan:
        asked = {DOLMEN: context(), ALBANIANA: rule_ctx()}
        rows = {k: v for k, v in renames(library).items() if k in live}
        name_rows = {DOLMEN: [{"id": 5, "site_id": DOLMEN, "name": "Dolmen de Menga",
                               "name_normalized": "dolmen de menga", "name_type": "label"}]}  # fmt: skip
        return NJ.build_clean(
            rows, asked, live, kw.get("keys", {"Menga Dolmen": "menga dolmen", "Albaniana": "albaniana"}),
            kw.get("key_holders", {}), kw.get("name_rows", name_rows), "2026-10-12",
        )  # fmt: skip

    def test_a_confirmed_rename_is_a_name_cell_pair_and_an_alias_change(
        self, library: Q.Library
    ) -> None:
        plan = self.build(library, {DOLMEN: live_row()})
        assert plan.skipped == [] and plan.lane.name == "name-clean-2026-10-12"
        cells = {v.column: v for v in plan.verdicts}
        assert (cells["name"].new_value, cells["name_normalized"].new_value) == (
            "Menga Dolmen",
            "menga dolmen",
        )
        assert (
            cells["name"].rule == "d23-name-clean"
            and cells["name"].finding_test_id == "D23/name-clean"
        )
        assert any(e["url"] == WP + "Menga_Dolmen" for e in cells["name"].evidence)
        (alias,) = plan.aliases
        assert (alias.row_key, alias.old_value, alias.new_value) == ("5", "label", "alias")

    def test_a_rule_made_rename_names_the_rule_in_its_evidence(self, library: Q.Library) -> None:
        live = live_row(ALBANIANA, "Albaniana (Roman Fort)", "albaniana (roman fort)")
        live["ext"] = []
        asked_ctx = rule_ctx()
        asked_ctx.update(qids=[], enwiki=[])
        rows = {ALBANIANA: renames(library)[ALBANIANA]}
        plan = NJ.build_clean(
            rows, {ALBANIANA: asked_ctx}, {ALBANIANA: live}, {"Albaniana": "albaniana"}, {},
            {ALBANIANA: [{"id": 9, "site_id": ALBANIANA, "name": "Albaniana (Roman Fort)",
                          "name_normalized": "albaniana (roman fort)", "name_type": "label"}]},
            "2026-10-12",
        )  # fmt: skip
        name_cell = next(v for v in plan.verdicts if v.column == "name")
        assert any(e["source"] == "rule:names_triage" for e in name_cell.evidence)

    @pytest.mark.parametrize(
        ("live", "reason"),
        [
            (live_row(name="Dolmen de Menga (Antequera)"), "changed-since-the-question"),
            (live_row(ext=[{"kind": "wikidata_qid", "value": "Q999"}, {"kind": "enwiki_title", "value": "Menga Dolmen"}]), "changed-since-the-question"),
            (live_row(scope_status="pending"), "changed-since-the-question"),
            (live_row(scope_status="retired"), "not-live"),
            (live_row(source_id="lyra"), "not-live"),
        ],
    )  # fmt: skip
    def test_a_site_that_moved_is_skipped(
        self, library: Q.Library, live: dict[str, Any], reason: str
    ) -> None:
        plan = self.build(library, {DOLMEN: live})
        assert plan.verdicts == [] and [s["reason"] for s in plan.skipped] == [reason]

    def test_a_site_gone_or_a_name_already_borne_is_skipped(self, library: Q.Library) -> None:
        asked = {DOLMEN: context()}
        rows = {DOLMEN: renames(library)[DOLMEN]}
        gone = NJ.build_clean(rows, asked, {}, {}, {}, {}, "2026-10-12")
        assert gone.skipped[0]["reason"] == "gone"
        taken = self.build(
            library,
            {DOLMEN: live_row()},
            key_holders={"menga dolmen": [{"site_id": OTHER, "name": "Menga Dolmen"}]},
        )
        assert taken.skipped[0]["reason"] == "name-key-taken"


# --------------------------------------------------------------------------------- the spoken name
def spoken_record(**over: Any) -> dict[str, Any]:
    base = {
        "id": MENHIR, "name": "Menhir du Camp de César", "country": "France", "has_description": True,
        "spoken": None, "source": None, "steps": [], "needs_model": True,
        "reasons": ["foreign_prefix"], "attested": ["Menhir du Camp de César", "Camp de César Menhir"],
    }  # fmt: skip
    base.update(over)
    return base


def spoken_ctx(**over: Any) -> dict[str, Any]:
    ctx = NJ.spoken_context(
        spoken_record(), [{"name": "Menhir du Camp de César, Var", "country": "France"}],
        [], "2026-10-08 20:35:11+00", {"site_type": "Menhir", "description": "A standing stone."},
    )  # fmt: skip
    ctx.update(over)
    return ctx


def say(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": MENHIR, "verdict": "SPEAK", "spoken": "Camp de Cesar Menhir",
        "from_form": "Camp de César Menhir", "why": "The item's English form, without the accent.",
    }  # fmt: skip
    base.update(over)
    return base


def parse_spoken(data: dict[str, Any], ctx: dict[str, Any] | None = None) -> NJ.Spoken:
    return NJ.parse_spoken(json.dumps(data), ctx or spoken_ctx())


class TestTheSpokenQuestion:
    def test_the_prompt_lists_the_attested_forms_the_homonyms_and_the_bounds(self) -> None:
        text = NJ.render_spoken(spoken_ctx())
        assert "  - Menhir du Camp de César\n  - Camp de César Menhir" in text
        assert "foreign prefix" in text and "Menhir du Camp de César, Var (France)" in text
        assert "at most 60 characters" in text
        assert "AN EARLIER ANSWER" in NJ.render_spoken(spoken_ctx(), "spoken: not attested")
        assert "OTHER RECORDS" not in NJ.render_spoken(spoken_ctx(homonyms=[]))

    def test_the_questions_are_the_sites_the_rule_could_not_name_with_a_description(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shown = [
            site(id=MENHIR, name="Menhir du Camp de César"),
            site(id=OTHER, name="Menhir du Camp de César, Var"),
        ]
        monkeypatch.setattr(NJ.export, "load_export", lambda path: export_of(shown))
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "INDEX.jsonl").write_text("", encoding="utf-8")
        monkeypatch.setattr(NJ, "wiki_cache_dir", lambda root=None: cache)
        records = [
            spoken_record(),
            spoken_record(id=OTHER, has_description=False),
            spoken_record(id="x", needs_model=False, spoken="X"),
        ]
        (tmp_path / NJ.SPOKEN_FILE).write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )
        (got,) = NJ.spoken_questions(tmp_path)
        assert got.site_id == MENHIR
        assert got.context["homonyms"] == [
            {"name": "Menhir du Camp de César, Var", "country": "Greece"}
        ]

    def test_the_rule_made_names_are_those_that_differ_for_a_site_with_a_description(
        self, tmp_path: Path
    ) -> None:
        records = [
            spoken_record(
                id="a", name="Tiverton, Devon", needs_model=False, spoken="Tiverton", source="name"
            ),
            spoken_record(id="b", name="Same", needs_model=False, spoken="Same", source="name"),
            spoken_record(
                id="c", name="NoText, X", needs_model=False, spoken="NoText", has_description=False
            ),
            spoken_record(id="d"),
        ]
        (tmp_path / NJ.SPOKEN_FILE).write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )
        assert [r["id"] for r in NJ.rule_spoken(tmp_path)] == ["a"]


class TestTheSpokenAnswer:
    def test_a_respelled_attested_form_parses(self) -> None:
        got = parse_spoken(say())
        assert (got.verdict, got.spoken, got.from_form) == (
            "SPEAK",
            "Camp de Cesar Menhir",
            "Camp de César Menhir",
        )
        assert parse_spoken(say(verdict="NONE", spoken=None, from_form=None)).verdict == "NONE"

    def test_a_form_with_only_a_kind_word_left_out_parses(self) -> None:
        ctx = spoken_ctx(attested=["Cave of Ardales"])
        got = parse_spoken(say(spoken="Ardales", from_form="Cave of Ardales"), ctx)
        assert got.spoken == "Ardales"

    @pytest.mark.parametrize(
        ("over", "match"),
        [
            ({"site_id": OTHER}, "is not this question's"),
            ({"verdict": "MAYBE"}, "is not SPEAK or NONE"),
            ({"from_form": "Menhir Camp"}, "none of the attested forms"),
            ({"spoken": "Caesar Camp Menhir"}, "is not the attested form"),
            ({"spoken": "Camp de Cesar Menhir, Var"}, "is not the attested form"),
            ({"spoken": "x" * 61}, "longer than 60"),
            (
                {"spoken": "Menhir du Camp de César", "from_form": "Menhir du Camp de César"},
                "that is NONE",
            ),
            ({"why": ""}, "trimmed, non-empty"),
            ({"spoken": None}, "trimmed, non-empty"),
        ],
    )
    def test_every_rule_an_answer_can_break_on_its_own(
        self, over: dict[str, Any], match: str
    ) -> None:
        with pytest.raises(R.AnswerError, match=match):
            parse_spoken(say(**over))

    def test_none_carries_no_name(self) -> None:
        with pytest.raises(R.AnswerError, match="null for NONE"):
            parse_spoken(say(verdict="NONE"))

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("Qʼumarkaj", "modifier letter"),
            ("Jabal al-ʿHayn", "modifier letter"),
            ("Tumulus 3", "a digit"),
            ("Tiverton (Devon)", "character '('"),
            ("Tiverton, Devon", "character ','"),
            ("Афина", "of another script"),
        ],
    )
    def test_a_spoken_name_a_voice_cannot_read_is_refused(self, text: str, problem: str) -> None:
        assert any(problem in p for p in NJ.tts_problems(text)), NJ.tts_problems(text)

    @pytest.mark.parametrize(
        "text",
        ["Camp de Cesar Menhir", "Qumarkaj", "Jabal al-Hayn", "St. Mary's Well", "Ħal Saflieni"],
    )
    def test_a_tts_safe_name_has_no_problem(self, text: str) -> None:
        assert NJ.tts_problems(text) == []

    def test_the_machine_refuses_a_respelling_a_voice_cannot_read(self) -> None:
        ctx = spoken_ctx(attested=["Qʼumarkaj"])
        with pytest.raises(R.AnswerError, match="not TTS-safe"):
            parse_spoken(say(spoken="Qʼumarkaj", from_form="Qʼumarkaj"), ctx)
        assert parse_spoken(say(spoken="Qumarkaj", from_form="Qʼumarkaj"), ctx).spoken == "Qumarkaj"

    def test_nothing_is_fetched_for_a_spoken_name(self) -> None:
        got = parse_spoken(say())
        assert NJ.spoken_spec().cited(got, {}) == set()
        outcome = NJ.decide_spoken(got, spoken_ctx(), R.Env(None, {}))  # type: ignore[arg-type]
        assert outcome.status == R.DECIDED and outcome.data["spoken"] == "Camp de Cesar Menhir"


def spoken_live(sid: str = MENHIR, **over: Any) -> dict[str, Any]:
    row = {"site_id": sid, "source_id": "ancient_nerds", "name": "Menhir du Camp de César",
           "scope_status": None, "spoken_name": None, "premise": "Menhir du Camp de César"}  # fmt: skip
    row.update(over)
    return row


class TestTheSpokenPlan:
    def rows(self) -> dict[str, dict[str, Any]]:
        rule = [
            spoken_record(
                id="a",
                name="Tiverton, Devon",
                needs_model=False,
                spoken="Tiverton",
                source="name",
                steps=["qualifier"],
            )
        ]
        model = {MENHIR: {"status": R.DECIDED, "answered_by": "web_verifier:r1-b01",
                          "data": {"verdict": "SPEAK", "spoken": "Camp de Cesar Menhir",
                                   "from_form": "Camp de César Menhir", "why": "Respelled."}}}  # fmt: skip
        return NJ.spoken_rows(rule, model, {MENHIR: spoken_ctx()})

    def test_rule_made_and_model_made_names_are_rows(self) -> None:
        rows = self.rows()
        assert rows["a"]["spoken"] == "Tiverton" and rows["a"]["source"] == "rule:name"
        assert rows[MENHIR]["source"] == "model:web_verifier:r1-b01"
        assert rows[MENHIR]["name"] == "Menhir du Camp de César", "the name it was made from"
        none = {MENHIR: {"status": R.DECIDED, "answered_by": "w", "data": {"verdict": "NONE"}}}
        assert NJ.spoken_rows([], none, {MENHIR: spoken_ctx()}) == {}
        held = {MENHIR: {"status": R.HELD, "answered_by": "w", "data": {"verdict": "SPEAK"}}}
        assert NJ.spoken_rows([], held, {MENHIR: spoken_ctx()}) == {}

    def test_a_null_spoken_name_is_filled_on_the_premise_of_the_name(self) -> None:
        live = {
            "a": spoken_live("a", name="Tiverton, Devon", premise="Tiverton, Devon"),
            MENHIR: spoken_live(),
        }
        plan = NJ.build_spoken(self.rows(), live)
        assert plan.skipped == [] and plan.sites == sorted(["a", MENHIR])
        cell = next(c for c in plan.changes if c.site_id == MENHIR)
        assert (cell.old_value, cell.new_value, cell.column) == (
            None,
            "Camp de Cesar Menhir",
            "spoken_name",
        )
        assert cell.premise == "Menhir du Camp de César" and cell.rule == "d23-spoken-name"

    @pytest.mark.parametrize(
        ("live", "reason"),
        [
            (None, "gone"),
            (spoken_live(name="Menhir du Camp"), "name-moved"),
            (spoken_live(spoken_name="Camp Menhir"), "already-set"),
            (spoken_live(scope_status="retired"), "not-live"),
            (spoken_live(source_id="lyra"), "not-live"),
        ],
    )
    def test_a_site_that_moved_or_is_set_is_skipped(
        self, live: dict[str, Any] | None, reason: str
    ) -> None:
        rows = {MENHIR: self.rows()[MENHIR]}
        plan = NJ.build_spoken(rows, {} if live is None else {MENHIR: live})
        assert plan.changes == [] and [s["reason"] for s in plan.skipped] == [reason]

    def test_a_spoken_name_equal_to_the_name_is_not_written(self) -> None:
        rows = {
            MENHIR: {
                "name": "Menhir du Camp de César",
                "spoken": "Menhir du Camp de César",
                "source": "model:x",
                "why": "w",
            }
        }
        plan = NJ.build_spoken(rows, {MENHIR: spoken_live()})
        assert plan.skipped[0]["reason"] == "same-as-name"

    def test_the_plan_is_a_cell_lane_plan_of_at_most_a_hundred_sites(self, tmp_path: Path) -> None:
        plan = NJ.build_spoken(self.rows(), {MENHIR: spoken_live()})
        mech = NJ.spoken_plan(plan, "2026-10-12", "2026-10-09T03:00:00+00:00")
        assert mech.lane.name == "spoken-2026-10-12" and mech.counters["cells"] == 1
        MP.write_plan_jsonl(mech, tmp_path / "PLAN.jsonl")
        MP.write_rollback_sql(mech, tmp_path / "ROLLBACK.sql", plan_path=tmp_path / "PLAN.jsonl")
        assert "spoken-2026-10-12" in (tmp_path / "ROLLBACK.sql").read_text("utf-8")
        big = NJ.SpokenPlan(
            [
                MP.Verdict(
                    f"{i:08d}-0000-4000-8000-000000000000",
                    "n",
                    True,
                    None,
                    "x",
                    "r",
                    "",
                    "",
                    False,
                    "t",
                )
                for i in range(101)
            ],
            [],
        )
        with pytest.raises(MP.PlanError, match="exceed one wave"):
            NJ.spoken_plan(big, "2026-10-12", "t")

    def test_the_live_read_asks_the_name_as_the_premise(self) -> None:
        sql = NJ.spoken_live_sql([MENHIR])
        assert "u.name AS premise" in sql and "u.spoken_name" in sql and f"'{MENHIR}'::uuid" in sql
