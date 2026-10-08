"""D20: the scope window question, its answer shape, the gates, the re-check and the plan.

DB-less and offline (`identity_b_fixtures`). The entries are the kinds the window holds: a fort dated
1837 by a withdrawn field wave, a museum, a pending site in the Americas and a footpath opened in 2003.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from identity import common  # noqa: E402
from identity import rounds as R  # noqa: E402
from identity import scope_judge as SJ  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_b_fixtures import html, store  # noqa: E402

FORT = "a1000000-0000-4000-8000-000000000001"
MUSEUM = "a1000000-0000-4000-8000-000000000002"
PENDING = "a1000000-0000-4000-8000-000000000003"
PATH_ = "a1000000-0000-4000-8000-000000000004"
FORT_PAGE = "https://example.org/ali-masjid"
FORT_TEXT = "Ali Masjid fort was built by the British in 1837."
OTHER_PAGE = "https://example.net/khyber"
OTHER_TEXT = "The Khyber fort dates from the nineteenth century."
WIKI = "https://en.wikipedia.org/wiki/Ali_Masjid"
WIKIDATA = "https://www.wikidata.org/wiki/Q42"
WIKI_TEXT = "Ali Masjid is a fort in the Khyber Pass."
WD_TEXT = "Ali Masjid fort in Pakistan"


def q(url: str, text: str) -> dict[str, str]:
    return {"url": url, "quote": text}


def record(sid: str = FORT, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": sid,
        "name": "Ali Masjid Fort",
        "country": "Pakistan",
        "site_type": "Fortress/citadel",
        "lat": 34.0,
        "lon": 71.2,
        "groups": ["outside_window"],
        "museum_question": False,
        "scope_status": None,
        "scope_reason": None,
        "period_start": 1837,
        "period_end": None,
        "period_name": "> 500 AD",
        "date_used": 1837,
        "origin": "fields-wd3",
        "recheck_d10": True,
        "period_writes": {
            "period_start": {
                "run_stamp": "2026-10-04_fields-wd3-s022",
                "family": "fields-wd3",
                "confidence": "one_source",
                "old": None,
                "new": "1837",
                "models": "minimax/MiniMax",
                "reverted": False,
                "applied_at": "t",
            }
        },
        "description": "Ali Masjid is a fort in the Khyber Pass.",
        "source_url": WIKI,
        "images": 3,
    }
    base.update(over)
    return base


def context(sid: str = FORT, **over: Any) -> dict[str, Any]:
    rec = record(sid, **{k: v for k, v in over.items() if k in record()})
    ctx = SJ.site_context(
        rec,
        {"wikidata_qid": ["Q42"], "enwiki_title": ["Ali Masjid"]},
        [{"lang": "en", "title": "Ali Masjid", "path": "C:/cache/en/x.json"}],
        "2026-10-08 20:35:11+00",
    )
    ctx.update({k: v for k, v in over.items() if k not in record()})
    return ctx


def answer(verdict: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": FORT,
        "verdict": verdict,
        "why": "The sources date it.",
        "period_start": None,
        "found_start": None,
        "kind": None,
        "quotes": [q(FORT_PAGE, FORT_TEXT)],
    }
    base.update(
        {
            "PERIOD_WRONG": {"period_start": 300},
            "OUT_OF_WINDOW": {"found_start": 1837},
            "MUSEUM_KEEP": {},
            "NOT_A_SITE": {
                "kind": "modern",
                "quotes": [q(FORT_PAGE, FORT_TEXT), q(OTHER_PAGE, OTHER_TEXT)],
            },
        }[verdict]
    )
    base.update(over)
    return base


def parse(data: dict[str, Any], ctx: dict[str, Any] | None = None) -> SJ.Answer:
    return SJ.parse_web(json.dumps(data), ctx or context())


# ------------------------------------------------------------------------------ the context
class TestTheContext:
    def test_the_context_holds_the_region_the_cutoff_and_the_provenance(self) -> None:
        ctx = context()
        assert (ctx["region"], ctx["cutoff"]) == ("rest of world", 500)
        assert ctx["recheck_d10"] and ctx["period_writes"]["period_start"]["family"] == "fields-wd3"
        assert ctx["qids"] == ["Q42"] and ctx["cache"][0]["title"] == "Ali Masjid"
        json.dumps(ctx)

    @pytest.mark.parametrize(
        ("lon", "country", "region", "cutoff"),
        [(-70.0, "Peru", "Americas", 1500), (143.0, "Australia", "Oceania", 1500), (71.2, "Pakistan", "rest of world", 500)],
    )  # fmt: skip
    def test_the_cutoff_follows_the_dates_module_s_region_rule(
        self, lon: float, country: str, region: str, cutoff: int
    ) -> None:
        assert SJ.cutoff_of(record(lon=lon, country=country, lat=-20.0)) == (region, cutoff)

    def test_a_record_without_a_longitude_has_no_window(self) -> None:
        with pytest.raises(common.IdentityError, match="no longitude"):
            SJ.cutoff_of(record(lon=None))


class TestTheQuestion:
    def test_the_prompt_says_the_window_the_provenance_and_the_verdicts(self) -> None:
        text = SJ.render_web(context())
        assert "prompt scope-window-v1" in text
        assert (
            "The map covers the rest of world through 500 AD (the rest of the world: 500 AD)"
            in text
        )
        assert "here 1837" in text and "do NOT trust it" in text
        assert "withdrawn by owner decision D10" in text
        assert (
            "period_start: None -> '1837' by fields-wd3 (one_source, models minimax/MiniMax)"
            in text
        )
        assert 'en.wikipedia "Ali Masjid": C:/cache/en/x.json' in text
        assert "its date 1837 lies past the cutoff 500 AD" in text
        assert "never answer it" in text, "an entry that is no museum never gets MUSEUM_KEEP"
        assert "at least 2 different websites" in text
        assert '"verdict": "PERIOD_WRONG | OUT_OF_WINDOW | MUSEUM_KEEP | NOT_A_SITE"' in text

    def test_a_museum_may_be_kept_and_an_americas_entry_has_the_later_cutoff(self) -> None:
        museum = context(MUSEUM, museum_question=True, groups=["outside_window"])
        text = SJ.render_web(museum)
        assert "the entry is a Museum that exhibits ancient material" in text
        assert "it is a Museum: the museum rule" in text
        americas = SJ.render_web(context(PENDING, lon=-70.0, country="Peru", lat=-12.0))
        assert "Americas and Oceania: 1500 AD" in americas

    def test_a_pending_entry_and_the_footpath_say_why_they_are_asked(self) -> None:
        pending = context(
            PENDING,
            groups=["pending"],
            scope_status="pending",
            scope_reason="Natural or man-made is disputed",
        )
        assert "left it pending: Natural or man-made is disputed" in SJ.render_web(pending)
        path = context(PATH_, groups=["outside_window", "hadrians_wall_path"])
        assert "a footpath opened in 2003" in SJ.render_web(path)

    def test_a_re_ask_shows_why_and_the_prompt_is_a_pure_function_of_the_context(self) -> None:
        text = SJ.render_web(context(), "quotes: a quote does not count")
        assert "AN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED" in text
        assert SJ.render_web(context()) == SJ.render_web(json.loads(json.dumps(context())))

    def test_the_questions_come_from_the_discovery_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.remediation.identity_fixtures import export_of, ext, site

        shown = site(id=FORT)
        monkeypatch.setattr(
            SJ.export, "load_export",
            lambda path: export_of([shown], ext_ids=[ext(FORT, "wikidata_qid", "Q42")]),
        )  # fmt: skip
        (tmp_path / "SCOPE_WINDOW.jsonl").write_text(json.dumps(record()) + "\n", encoding="utf-8")
        cache = tmp_path / "wiki_cache"
        cache.mkdir()
        (cache / "INDEX.jsonl").write_text(
            json.dumps({"site_id": FORT, "lang": "en", "title": "Ali Masjid", "file": "en\\a.json"})
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(SJ, "wiki_cache_dir", lambda root=None: cache)
        (got,) = SJ.questions(tmp_path)
        assert got.site_id == FORT and got.context["qids"] == ["Q42"]
        assert got.context["cache"][0]["path"] == (cache / "en" / "a.json").as_posix()


# ------------------------------------------------------------------------------ the answer shape
class TestTheAnswerShape:
    @pytest.mark.parametrize("verdict", SJ.VERDICTS)
    def test_each_verdict_parses_with_its_own_field(self, verdict: str) -> None:
        ctx = context(museum_question=verdict == "MUSEUM_KEEP")
        got = parse(answer(verdict), ctx)
        assert got.verdict == verdict
        assert (got.period_start, got.found_start, got.kind) == {
            "PERIOD_WRONG": (300, None, None),
            "OUT_OF_WINDOW": (None, 1837, None),
            "MUSEUM_KEEP": (None, None, None),
            "NOT_A_SITE": (None, None, "modern"),
        }[verdict]

    @pytest.mark.parametrize(
        ("verdict", "over", "match"),
        [
            ("PERIOD_WRONG", {"period_start": None}, "period_start must be set for PERIOD_WRONG"),
            ("PERIOD_WRONG", {"found_start": 1900}, "found_start must be null"),
            ("PERIOD_WRONG", {"period_start": 501}, "is past the cutoff 500"),
            ("PERIOD_WRONG", {"period_start": "300"}, "is not a year"),
            ("PERIOD_WRONG", {"period_start": True}, "is not a year"),
            ("PERIOD_WRONG", {"period_start": 5000}, "is not a year"),
            ("OUT_OF_WINDOW", {"found_start": 500}, "is not past the cutoff 500"),
            ("OUT_OF_WINDOW", {"found_start": None}, "found_start must be set for OUT_OF_WINDOW"),
            ("OUT_OF_WINDOW", {"kind": "modern"}, "kind must be null"),
            ("MUSEUM_KEEP", {}, "is for an entry of type Museum"),
            ("MUSEUM_KEEP", {"period_start": 1}, "all three are null"),
            ("NOT_A_SITE", {"kind": "hoax"}, "is not one of"),
            ("NOT_A_SITE", {"kind": None}, "kind must be set for NOT_A_SITE"),
            ("NOT_A_SITE", {"quotes": [q(FORT_PAGE, FORT_TEXT)]}, "at least 2 websites"),
            (
                "NOT_A_SITE",
                {"quotes": [q(WIKI, WIKI_TEXT), q(WIKIDATA, WD_TEXT)]},
                "at least 2 websites",
            ),
            ("OUT_OF_WINDOW", {"quotes": []}, "needs at least 1 quote"),
            ("OUT_OF_WINDOW", {"verdict": "KEEP"}, "verdict .KEEP. is not one of"),
            ("OUT_OF_WINDOW", {"site_id": MUSEUM}, "is not this question's"),
            ("OUT_OF_WINDOW", {"why": ""}, "trimmed, non-empty"),
            ("OUT_OF_WINDOW", {"why": "x" * 601}, "longer than 600"),
        ],
    )  # fmt: skip
    def test_every_rule_an_answer_can_break_on_its_own(
        self, verdict: str, over: dict[str, Any], match: str
    ) -> None:
        data = answer(verdict)
        data.update(over)
        with pytest.raises(R.AnswerError, match=match):
            parse(data)

    def test_the_americas_cutoff_applies_to_an_americas_entry(self) -> None:
        ctx = context(PENDING, lon=-70.0, country="Peru", lat=-12.0)
        assert (
            parse(answer("PERIOD_WRONG", site_id=PENDING, period_start=1400), ctx).period_start
            == 1400
        )
        with pytest.raises(R.AnswerError, match="past the cutoff 1500"):
            parse(answer("PERIOD_WRONG", site_id=PENDING, period_start=1501), ctx)

    def test_a_museum_keep_for_a_museum_parses(self) -> None:
        assert parse(answer("MUSEUM_KEEP"), context(museum_question=True)).verdict == "MUSEUM_KEEP"

    def test_the_cited_urls(self) -> None:
        got = parse(answer("NOT_A_SITE"))
        assert SJ.cited(got, {}) == {FORT_PAGE, OTHER_PAGE}


# ------------------------------------------------------------------------------ the gates
@pytest.fixture
def library(tmp_path: Path) -> Q.Library:
    pages = tmp_path / "pages"
    store(pages, FORT_PAGE, html(FORT_TEXT))
    store(pages, OTHER_PAGE, html(OTHER_TEXT))
    store(pages, WIKI, html(WIKI_TEXT))
    store(pages, WIKIDATA, html(WD_TEXT))
    return Q.Library(REPO, pages)


def decide(
    data: dict[str, Any], library: Q.Library, ctx: dict[str, Any] | None = None
) -> R.Outcome:
    c = ctx or context(museum_question=data["verdict"] == "MUSEUM_KEEP")
    return SJ.decide_web(parse(data, c), c, R.Env(library, {}))


class TestTheGates:
    @pytest.mark.parametrize("verdict", SJ.VERDICTS)
    def test_a_verdict_whose_quotes_are_found_is_decided(
        self, verdict: str, library: Q.Library
    ) -> None:
        got = decide(answer(verdict), library)
        assert got.status == R.DECIDED, got.reason
        assert all(x["outcome"] == "found" for x in got.data["quotes"])
        assert got.data["verdict"] == verdict

    def test_a_quote_the_page_does_not_hold_holds_the_site(self, library: Q.Library) -> None:
        got = decide(
            answer("OUT_OF_WINDOW", quotes=[q(FORT_PAGE, "Ali Masjid was built in 900.")]), library
        )
        assert got.status == R.HELD and got.reason.startswith("quotes: a quote does not count")

    def test_a_not_a_site_stands_on_two_websites_that_are_found(self, library: Q.Library) -> None:
        bad = answer(
            "NOT_A_SITE", quotes=[q(FORT_PAGE, FORT_TEXT), q(OTHER_PAGE, "nothing of the kind")]
        )
        got = decide(bad, library)
        assert got.status == R.HELD and "a quote does not count" in got.reason

    def test_two_pages_of_one_website_are_one_website(self, library: Q.Library) -> None:
        store(library.pages, FORT_PAGE + "2", html(FORT_TEXT))
        data = answer("NOT_A_SITE", quotes=[q(FORT_PAGE, FORT_TEXT), q(FORT_PAGE + "2", FORT_TEXT)])
        with pytest.raises(R.AnswerError, match="at least 2 websites"):
            parse(data)


# ------------------------------------------------------------------------------ the re-check
def web_decision(
    library: Q.Library, verdict: str, sid: str = FORT, **ctx_over: Any
) -> dict[str, Any]:
    out = decide(
        answer(verdict, site_id=sid),
        library,
        context(sid, museum_question=verdict == "MUSEUM_KEEP", **ctx_over),
    )
    return {"site_id": sid, "status": out.status, "reason": out.reason, "round": "r1",
            "answered_by": "web_verifier:r1-b01", "data": out.data}  # fmt: skip


class TestTheRecheck:
    def test_it_asks_every_decided_retirement_and_nothing_else(self, library: Q.Library) -> None:
        asked = [R.Question(s, context(s)) for s in (FORT, MUSEUM, PENDING, PATH_)]
        decisions = {
            FORT: web_decision(library, "OUT_OF_WINDOW"),
            MUSEUM: web_decision(library, "MUSEUM_KEEP", MUSEUM),
            PENDING: web_decision(library, "NOT_A_SITE", PENDING),
            PATH_: {**web_decision(library, "OUT_OF_WINDOW", PATH_), "status": R.HELD},
        }
        got = SJ.recheck_questions(asked, decisions)
        assert [x.site_id for x in got] == [FORT, PENDING]
        assert got[0].context["proposal"]["found_start"] == 1837
        assert got[1].context["proposal"]["kind"] == "modern"
        period = {FORT: web_decision(library, "PERIOD_WRONG")}
        assert SJ.recheck_questions(asked[:1], period) == []

    def test_the_prompt_asks_to_refute_a_retirement_and_says_what_a_410_is(
        self, library: Q.Library
    ) -> None:
        ask = SJ.recheck_questions(
            [R.Question(FORT, context())], {FORT: web_decision(library, "OUT_OF_WINDOW")}
        )
        text = SJ.render_recheck(ask[0].context)
        assert "try to REFUTE" in text and "becomes a 410" in text
        assert "found_start: 1837" in text and FORT_TEXT in text
        assert "no source dates any part of it at or before the cutoff" in text
        assert "do not trust it: it was written by a withdrawn field wave" in text
        ask2 = SJ.recheck_questions(
            [R.Question(FORT, context())], {FORT: web_decision(library, "NOT_A_SITE")}
        )
        text2 = SJ.render_recheck(ask2[0].context)
        assert "kind: modern" in text2 and "this entry is no archaeological site" in text2

    def test_a_confirmation_needs_a_found_quote_a_rejection_needs_a_reason(
        self, library: Q.Library
    ) -> None:
        ctx = {"site_id": FORT, "proposal": {"verdict": "OUT_OF_WINDOW"}}
        raw = {
            "site_id": FORT,
            "verdict": "CONFIRM",
            "why": "read",
            "quotes": [q(FORT_PAGE, FORT_TEXT)],
        }
        review = SJ.parse_recheck(json.dumps(raw), ctx)
        assert SJ.decide_recheck(review, ctx, R.Env(library, {})).status == R.DECIDED
        bad = SJ.Review(FORT, "CONFIRM", "w", (q(FORT_PAGE, "no such text"),))
        assert SJ.decide_recheck(bad, ctx, R.Env(library, {})).status == R.HELD
        with pytest.raises(R.AnswerError, match="needs at least 1 quote"):
            SJ.parse_recheck(json.dumps({**raw, "quotes": []}), ctx)
        assert (
            SJ.parse_recheck(json.dumps({**raw, "verdict": "REJECT", "quotes": []}), ctx).verdict
            == "REJECT"
        )
        with pytest.raises(R.AnswerError, match="not CONFIRM or REJECT"):
            SJ.parse_recheck(json.dumps({**raw, "verdict": "KEEP"}), ctx)

    def test_the_final_state_of_each_kind_of_verdict(self) -> None:
        def d(verdict: str, status: str = R.DECIDED) -> dict[str, Any]:
            return {"status": status, "data": {"verdict": verdict}}

        web = {"a": d("PERIOD_WRONG"), "b": d("OUT_OF_WINDOW"), "c": d("NOT_A_SITE"),
               "e": d("MUSEUM_KEEP"), "f": d("OUT_OF_WINDOW", R.HELD), "g": d("NOT_A_SITE")}  # fmt: skip
        second = {"b": d("CONFIRM"), "c": d("REJECT"), "g": d("CONFIRM", R.HELD)}
        got = {r["site_id"]: r["state"] for r in SJ.final_state(web, second)}
        assert got == {
            "a": "kept",
            "b": "confirmed",
            "c": "rejected",
            "e": "kept",
            "f": "held",
            "g": "waiting-for-recheck",
        }


# ------------------------------------------------------------------------------ the plan
def decision_for(verdict: str, sid: str = FORT, **over: Any) -> dict[str, Any]:
    quotes = [{**q(FORT_PAGE, FORT_TEXT), "outcome": "found", "detail": "visible text"}]
    if verdict == "NOT_A_SITE":
        quotes.append({**q(OTHER_PAGE, OTHER_TEXT), "outcome": "found", "detail": "visible text"})
    data = {
        "verdict": verdict, "why": "The sources date it.", "quotes": quotes, "kind": None,
        "period_start": 300 if verdict == "PERIOD_WRONG" else None,
        "found_start": 1837 if verdict == "OUT_OF_WINDOW" else None,
    }  # fmt: skip
    if verdict == "NOT_A_SITE":
        data["kind"] = "modern"
    data.update(over)
    return {
        "site_id": sid,
        "status": R.DECIDED,
        "round": "r1",
        "answered_by": "web_verifier:r1-b01",
        "data": data,
    }


def confirm(sid: str = FORT) -> dict[str, Any]:
    return {"site_id": sid, "status": R.DECIDED, "round": "r1", "answered_by": "adversarial:r1-b01",
            "data": {"verdict": "CONFIRM", "why": "read the pages", "quotes": []}}  # fmt: skip


def live_row(sid: str = FORT, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "site_id": sid, "source_id": "ancient_nerds", "name": "Ali Masjid Fort",
        "site_type": "Fortress/citadel", "country": "Pakistan", "lat": 34.0, "lon": 71.2,
        "period_start": 1837, "period_end": None, "scope_status": None, "scope_reason": None,
        "premise": "Ali Masjid Fort | Fortress/citadel | 34.0 | 71.2 | Pakistan | 1837 | NULL",
    }  # fmt: skip
    row.update(over)
    return row


ASKED = {FORT: context(FORT), MUSEUM: context(MUSEUM, museum_question=True, name="Museum")}


def build(
    final: dict[str, Any], live: dict[str, Any], asked: dict[str, Any] | None = None, **kw: Any
) -> SJ.ScopePlan:
    return SJ.build(
        final, kw.get("rechecks", {FORT: confirm()}), asked or ASKED, live, "2026-10-12"
    )


class TestThePlan:
    def test_an_out_of_window_site_is_retired_with_the_documented_reason(self) -> None:
        plan = build({FORT: decision_for("OUT_OF_WINDOW")}, {FORT: live_row()})
        cells = {c.column: c for c in plan.changes}
        assert (cells["scope_status"].old_value, cells["scope_status"].new_value) == (
            None,
            "retired",
        )
        assert (
            cells["scope_reason"].new_value
            == f"E3: period_start 1837 is past the cutoff; {FORT_TEXT}"
        )
        assert cells["scope_status"].premise == live_row()["premise"]
        sources = [e["source"] for e in cells["scope_reason"].evidence]
        assert sources == [FORT_PAGE, "web_verifier:r1-b01", "adversarial:r1-b01"]
        assert plan.skipped == [] and plan.sites == [FORT]

    def test_a_not_a_site_is_retired_with_the_scope_review_s_reason(self) -> None:
        asked = {FORT: context(FORT, scope_status="pending", scope_reason="disputed")}
        live = live_row(scope_status="pending", scope_reason="disputed")
        plan = build({FORT: decision_for("NOT_A_SITE")}, {FORT: live}, asked)
        cells = {c.column: c for c in plan.changes}
        assert (cells["scope_status"].old_value, cells["scope_status"].new_value) == (
            "pending",
            "retired",
        )
        assert (
            cells["scope_reason"].new_value
            == "E3: not an archaeological site (modern): The sources date it."
        )
        assert cells["scope_reason"].old_value == "disputed"

    def test_an_in_scope_museum_can_be_retired_and_a_kept_one_is_not_written_twice(self) -> None:
        asked = {FORT: context(FORT, scope_status="in_scope", scope_reason="kept")}
        live = live_row(scope_status="in_scope", scope_reason="kept")
        retired = build({FORT: decision_for("NOT_A_SITE")}, {FORT: live}, asked)
        assert {
            (c.old_value, c.new_value) for c in retired.changes if c.column == "scope_status"
        } == {("in_scope", "retired")}
        asked_museum = {
            MUSEUM: context(
                MUSEUM,
                museum_question=True,
                name="Museum",
                scope_status="in_scope",
                scope_reason="x",
            )
        }
        same = SJ.build(
            {MUSEUM: decision_for("MUSEUM_KEEP", MUSEUM)}, {}, asked_museum,
            {MUSEUM: live_row(MUSEUM, name="Museum", scope_status="in_scope", scope_reason="x")}, "2026-10-12",
        )  # fmt: skip
        assert same.changes == [] and same.skipped[0]["reason"] == "already-decided"

    def test_a_museum_keep_fills_the_status_from_null(self) -> None:
        plan = SJ.build(
            {MUSEUM: decision_for("MUSEUM_KEEP", MUSEUM)}, {}, {MUSEUM: ASKED[MUSEUM]},
            {MUSEUM: live_row(MUSEUM, name="Museum")}, "2026-10-12",
        )  # fmt: skip
        cells = {c.column: c for c in plan.changes}
        assert cells["scope_status"].new_value == "in_scope"
        assert cells["scope_reason"].new_value.startswith(
            "E3 museum rule: the museum exhibits ancient material;"
        )

    def test_a_wrong_period_keeps_the_entry_and_hands_the_year_to_the_fields_lane(self) -> None:
        plan = build({FORT: decision_for("PERIOD_WRONG")}, {FORT: live_row()})
        cells = {c.column: c for c in plan.changes}
        assert cells["scope_status"].new_value == "in_scope"
        assert cells["scope_reason"].new_value.startswith(
            "E3: period_start 1837 is past the cutoff, but a source dates the start at 300;"
        )
        (hand,) = plan.period_wrong
        assert (hand["period_start"], hand["stored_period_start"], hand["recheck_d10"]) == (
            300,
            1837,
            True,
        )
        assert hand["quotes"][0]["url"] == FORT_PAGE and "WD4" in hand["ask"]

    def test_a_year_that_is_already_right_is_kept_without_a_hand_off(self) -> None:
        asked = {
            FORT: context(
                FORT,
                period_start=300,
                date_used=300,
                groups=["pending"],
                scope_status="pending",
                scope_reason="no date",
            )
        }
        live = live_row(period_start=300, scope_status="pending", scope_reason="no date")
        plan = build({FORT: decision_for("PERIOD_WRONG")}, {FORT: live}, asked)
        assert plan.period_wrong == []
        reason = next(c for c in plan.changes if c.column == "scope_reason").new_value
        assert reason.startswith("E3: kept in scope, a source dates the start at 300;")

    @pytest.mark.parametrize(
        ("live", "reason"),
        [
            (None, "gone"),
            (live_row(source_id="lyra"), "not-curated"),
            (live_row(name="Ali Masjid"), "entry-moved"),
            (live_row(period_start=1900), "entry-moved"),
            (live_row(lat=34.5), "entry-moved"),
            (live_row(scope_status="pending"), "entry-moved"),
            (live_row(scope_reason="x"), "entry-moved"),
        ],
    )
    def test_an_entry_that_moved_since_the_question_is_skipped_and_asked_again(
        self, live: dict[str, Any] | None, reason: str
    ) -> None:
        plan = build({FORT: decision_for("OUT_OF_WINDOW")}, {} if live is None else {FORT: live})
        assert plan.changes == [] and [s["reason"] for s in plan.skipped] == [reason]

    def test_a_retired_site_is_left_alone(self) -> None:
        asked = {FORT: context(FORT, scope_status="retired")}
        live = live_row(scope_status="retired")
        plan = build({FORT: decision_for("OUT_OF_WINDOW")}, {FORT: live}, asked)
        assert plan.changes == [] and plan.skipped[0]["reason"] == "already-retired"

    def test_a_retirement_without_a_confirmation_is_refused(self) -> None:
        with pytest.raises(MP.PlanError, match="only after a CONFIRM"):
            build({FORT: decision_for("OUT_OF_WINDOW")}, {FORT: live_row()}, rechecks={})
        reject = {FORT: {**confirm(), "data": {**confirm()["data"], "verdict": "REJECT"}}}
        with pytest.raises(MP.PlanError, match="only after a CONFIRM"):
            build({FORT: decision_for("OUT_OF_WINDOW")}, {FORT: live_row()}, rechecks=reject)

    def test_the_plan_counts_the_transitions_and_writes_its_files_and_rollback(
        self, tmp_path: Path
    ) -> None:
        final = {FORT: decision_for("OUT_OF_WINDOW"), MUSEUM: decision_for("MUSEUM_KEEP", MUSEUM)}
        live = {
            FORT: live_row(),
            MUSEUM: live_row(MUSEUM, name="Museum", scope_status="pending", scope_reason="d"),
        }
        asked = {
            **ASKED,
            MUSEUM: context(
                MUSEUM,
                museum_question=True,
                name="Museum",
                scope_status="pending",
                scope_reason="d",
            ),
        }
        plan = SJ.build(final, {FORT: confirm()}, asked, live, "2026-10-12")
        mech = SJ.to_plan(plan, "2026-10-09T03:00:00+00:00")
        assert mech.counters == {
            "sites": 2, "cells": 4, "NULL->retired": 1, "pending->in_scope": 1,
            "skipped": 0, "period_wrong_handoffs": 0,
        }  # fmt: skip
        MP.write_plan_jsonl(mech, tmp_path / "PLAN.jsonl")
        MP.write_rollback_sql(mech, tmp_path / "ROLLBACK.sql", plan_path=tmp_path / "PLAN.jsonl")
        rollback = (tmp_path / "ROLLBACK.sql").read_text("utf-8")
        assert "2026-10-12_mechanical-scope-window-rollback" in rollback
        records = A.load_records(tmp_path / "PLAN.jsonl")
        A.validate_records(records, lane=plan.lane)

    def test_a_wave_is_at_most_a_hundred_sites(self) -> None:
        plan = SJ.ScopePlan(SJ.scope_window_lane("2026-10-12"))
        for i in range(101):
            plan.changes.append(
                MP.Verdict(
                    f"{i:08d}-0000-4000-8000-000000000000",
                    "n",
                    True,
                    None,
                    "retired",
                    "r",
                    "",
                    "",
                    False,
                    "t",
                )
            )
        with pytest.raises(MP.PlanError, match="exceed one wave"):
            SJ.to_plan(plan, "t")

    def test_the_live_read_asks_the_lane_s_premise(self) -> None:
        sql = SJ.live_sql([FORT])
        assert "concat_ws(' | ', u.name" in sql and f"'{FORT}'::uuid" in sql
        assert sql.lstrip().upper().startswith("SELECT")
