"""The E3 scope review (WD2, O7): the funnel, the rounds, the quote check, the waves.

DB-less and offline: production's export is a fixture in the tagged-export form, WD1's harvest a
fixture in its fixed layout, every Opus answer is written through `opus_handoff.write_answer` into
a temporary handoff, and the cited pages are stored with `quotes.store_page` as a fetch would have
kept them. Site ids and names are production's where the case was read there (2026-09-26).
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

import opus_handoff as OH  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import scope_review as R  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from served_image.precheck import load_harvest  # noqa: E402

BALTIC = "c8d2c13e-fd9a-466c-9fdc-fc26ee798ded"  # Baltic Sea Anomaly, Underwater structures
BOSNIA = "3c466fde-b751-4065-8de2-bd5c9280afe5"  # Bosnian Pyramid of the Sun, pending
KHORTYTSIA = "e2030e0e-b33e-410c-b8df-8ccd76b8af03"  # an island: Wikidata P31 island
NOITEM = "0b8f2a44-2c1e-4d7a-9a51-6c1f0e8d9a10"  # no Wikidata item
STONEHENGE = "1d6f2d2a-8f4e-4b1c-9d0a-3e7f5a2b6c11"  # no signal
RETIRED_ONE = "97b3cd09-f833-48ca-8273-8b76767fc245"  # retired by scope-e4
MUNGO = "4f7c9e21-6a3b-4d5e-8f1a-2b3c4d5e6f70"  # Oceania, retired by rule (a) in the fixture

WIKI = "https://en.wikipedia.org/wiki/Baltic_Sea_anomaly"
WIKIDATA = "https://www.wikidata.org/wiki/Q123"
NEWS = "https://www.livescience.com/baltic-sea-anomaly.html"
WIKI_TEXT = "The Baltic Sea anomaly is a natural geological formation on the seabed."
NEWS_TEXT = "Geologists concluded that the object is a glacial deposit, a rock formation."


def premise(s: dict[str, Any]) -> str:
    return " | ".join(
        str(x if x is not None else "NULL")
        for x in (
            s["name"],
            s["site_type"],
            s["lat"],
            s["lon"],
            s["country"],
            s["period_start"],
            s["period_end"],
        )
    )


def site(
    sid: str,
    name: str,
    site_type: str,
    *,
    status: str | None = None,
    reason: str | None = None,
    country: str = "Sweden",
    lat: float = 61.37,
    lon: float = 18.45,
    start: int | None = -1000,
) -> dict[str, Any]:
    row = {
        "id": sid,
        "name": name,
        "country": country,
        "site_type": site_type,
        "lat": lat,
        "lon": lon,
        "period_start": start,
        "period_end": None,
        "excerpt": f"{name} is described here.",
        "source_url": f"https://example.org/{sid[:8]}",
        "scope_status": status,
        "scope_reason": reason,
    }
    row["premise"] = premise(row)
    return row


def sites() -> list[dict[str, Any]]:
    return [
        site(BALTIC, "Baltic Sea Anomaly", "Underwater structures"),
        site(BOSNIA, "Bosnian Pyramid of the Sun", "Geological interest", status="pending"),
        site(KHORTYTSIA, "Khortytsia", "Archaeological site", country="Ukraine"),
        site(NOITEM, "Nameless mound", "Mound/tumulus"),
        site(STONEHENGE, "Stonehenge", "Stone circle", country="England"),
        site(
            RETIRED_ONE,
            "Mount Livadiyskaya",
            "Natural feature",
            status="retired",
            reason="E3: period_start 698 is past the cutoff",
        ),
        site(
            MUNGO,
            "Lake Mungo",
            "Archaeological site",
            status="retired",
            reason="E3: period_start 1200 is 700 years past the rest-of-world cutoff",
            country="Australia",
            lat=-33.75,
            lon=143.08,
            start=1200,
        ),
    ]


def journal() -> list[dict[str, Any]]:
    stamp = L.SCOPE.run_stamp
    return [
        {"id": 900, "row_pk": RETIRED_ONE, "column_name": "scope_status", "old_value": None,
         "new_value": "retired", "run_stamp": stamp},
        {"id": 901, "row_pk": MUNGO, "column_name": "scope_status", "old_value": None,
         "new_value": "retired", "run_stamp": stamp},
    ]  # fmt: skip


def export_text(rows: list[dict[str, Any]], at: str = "2026-09-26 03:00:00+00") -> str:
    lines = [{"kind": "site", "row": r} for r in rows]
    lines += [{"kind": "journal", "row": j} for j in journal()]
    lines.append({"kind": "snapshot", "row": {"exported_at": at}})
    return "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)


def write_export(out: Path, rows: list[dict[str, Any]] | None = None, at: str = "t0") -> None:
    R.export_path(out).parent.mkdir(parents=True, exist_ok=True)
    R.export_path(out).write_text(export_text(rows or sites(), at), encoding="utf-8")


def claim(value: Any, rank: str = "normal") -> dict[str, Any]:
    return {"mainsnak": {"datavalue": {"value": value}}, "rank": rank}


def write_harvest(root: Path, qids: dict[str, str | None] | None = None) -> None:
    qids = qids or {
        BALTIC: "Q123",
        BOSNIA: "Q124",
        KHORTYTSIA: "Q125",
        NOITEM: None,
        STONEHENGE: "Q39671",
        RETIRED_ONE: "Q126",
        MUNGO: "Q127",
    }
    entities = {
        "Q123": [claim({"id": "Q631305"})],  # rock formation
        "Q124": [claim({"id": "Q12518"})],  # a building class: no natural signal
        "Q125": [claim({"id": "Q23442"}), claim({"id": "Q839954"})],  # island, archaeological site
        "Q39671": [claim({"id": "Q839954"}), claim({"id": "Q8502"}, "deprecated")],
        "Q126": [claim({"id": "Q8502"})],
        "Q127": [claim({"id": "Q23397"})],
    }
    (root / "entities").mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {"site_id": sid, "name": "x", "country": "y", "lat": 0.0, "lon": 0.0, "qid": qid,
             "enwiki_title": None, "source_url": None}
        )
        for sid, qid in qids.items()
    ]  # fmt: skip
    (root / "SITES.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for qid, p31 in entities.items():
        (root / "entities" / f"{qid}.json").write_text(
            json.dumps({"id": qid, "claims": {"P31": p31}}), encoding="utf-8"
        )


def not_a_site(quotes: list[tuple[str, str]], kind: str = "natural_formation") -> str:
    return json.dumps(
        {
            "decision": "not_a_site",
            "kind": kind,
            "reason": "A natural rock formation on the seabed, not a structure.",
            "quotes": [{"url": u, "quote": q} for u, q in quotes],
        }
    )


SITE_ANSWER = json.dumps({"decision": "site", "kind": None, "reason": "Ruins.", "quotes": []})
#: A site answer that cites a page: the reviewer's case of 2026-09-26 (Khortytsia, one quote).
SITE_WITH_QUOTE = json.dumps(
    {"decision": "site", "kind": None, "reason": "An island with Scythian burials.",
     "quotes": [{"url": "https://en.wikipedia.org/wiki/Khortytsia", "quote": "burials"}]}
)  # fmt: skip


def pages_for(pages: Path, bodies: dict[str, str]) -> Any:
    """A `collect` that keeps each cited page as a fetch would have (unknown URLs: HTTP 404)."""

    def collect(urls: list[str]) -> None:
        for url in urls:
            body = bodies.get(url)
            Q.store_page(
                pages,
                url,
                status=200 if body is not None else 404,
                final_url=url,
                content_type="text/html; charset=utf-8",
                body=f"<html><body><p>{body or 'gone'}</p></body></html>".encode(),
                error="",
                fetched_at="2026-09-26T03:00:00Z",
            )

    return collect


@pytest.fixture
def review(tmp_path: Path) -> dict[str, Path]:
    out, harvest, handoff = tmp_path / "out", tmp_path / "harvest", tmp_path / "handoff-r0"
    write_export(out)
    write_harvest(harvest)
    return {"out": out, "harvest": harvest, "handoff": handoff}


def answer_round(handoff: Path, out: Path, round_no: int, texts: dict[str, str]) -> None:
    for q in read_jsonl(R.round_files(out, round_no).questions):
        OH.write_answer(
            handoff,
            batch_id=q["batch_id"],
            stage=R.STAGE,
            label=q["site_id"],
            text=texts.get(q["site_id"], SITE_ANSWER),
            answered_by=q["batch_id"],
        )


def run_round(
    review: dict[str, Path], round_no: int, texts: dict[str, str], bodies: dict[str, str]
) -> dict:
    """One round end to end: exported into its own handoff, answered, imported."""
    out = review["out"]
    handoff = out.parent / f"handoff-r{round_no}"
    R.export_round(out, handoff, round_no, load_harvest(review["harvest"]))
    answer_round(handoff, out, round_no, texts)
    pages = out / "pages"
    return R.import_round(out, round_no, Q.Library(REPO, pages), pages_for(pages, bodies))


def run_round0(review: dict[str, Path], texts: dict[str, str], bodies: dict[str, str]) -> dict:
    return run_round(review, 0, texts, bodies)


def move_baltic(review: dict[str, Path]) -> dict[str, Any]:
    """A fresh export in which WD1 has moved the Baltic Sea Anomaly's point."""
    rows = sites()
    rows[0]["lat"] = 55.0
    rows[0]["premise"] = premise(rows[0])
    write_export(review["out"], rows, at="t1")
    return rows[0]


# ------------------------------------------------------------------------------ the funnel
class TestTheFunnel:
    def test_every_signal_puts_a_site_in_and_nothing_else_does(self, review) -> None:
        export = R.read_export(R.export_path(review["out"]))
        got = {c.site_id: c.signals for c in R.candidates(export, load_harvest(review["harvest"]))}
        assert got == {
            BALTIC: ("type", "wikidata:Q631305"),
            BOSNIA: ("type", "pending"),
            KHORTYTSIA: ("wikidata:Q23442",),
            NOITEM: ("no-item",),
        }

    def test_a_retired_site_is_never_asked(self, review) -> None:
        export = R.read_export(R.export_path(review["out"]))
        asked = {c.site_id for c in R.candidates(export, load_harvest(review["harvest"]))}
        assert RETIRED_ONE not in asked and MUNGO not in asked

    def test_a_deprecated_class_is_no_signal(self, review) -> None:
        """Stonehenge's fixture item carries `mountain` deprecated: not a signal."""
        export = R.read_export(R.export_path(review["out"]))
        asked = {c.site_id for c in R.candidates(export, load_harvest(review["harvest"]))}
        assert STONEHENGE not in asked

    def test_a_shown_site_the_harvest_lacks_stops_the_funnel(self, tmp_path: Path) -> None:
        write_harvest(tmp_path / "h", {BALTIC: "Q123"})
        write_export(tmp_path / "out")
        export = R.read_export(R.export_path(tmp_path / "out"))
        with pytest.raises(R.ScopeReviewError, match="not in the harvest"):
            R.candidates(export, load_harvest(tmp_path / "h"))

    def test_the_non_site_types_are_canonical_types(self) -> None:
        from pipeline.normalizers.site_type import CANONICAL_TYPES

        assert {"Natural feature", "Geological interest", "Underwater structures"} <= set(
            CANONICAL_TYPES
        )
        assert set(R.NON_SITE_TYPES) - set(CANONICAL_TYPES) <= {"Impact crater", "Unknown"}


# ------------------------------------------------------------------------------ the answers
class TestTheAnswers:
    def test_a_site_needs_no_quote(self) -> None:
        assert R.parse_answer(SITE_ANSWER).decision == R.SITE

    def test_a_not_a_site_from_two_websites(self) -> None:
        answer = R.parse_answer(not_a_site([(WIKI, WIKI_TEXT), (NEWS, NEWS_TEXT)]))
        assert answer.decision == R.NOT_A_SITE and answer.kind == "natural_formation"

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("no json here", "no JSON"),
            (json.dumps({"decision": "site", "kind": None, "reason": "x"}), "carries"),
            (json.dumps({"decision": "maybe", "kind": None, "reason": "x", "quotes": []}),
             "neither"),
            (json.dumps({"decision": "site", "kind": "modern", "reason": "x", "quotes": []}),
             "has no kind"),
            (not_a_site([(WIKI, "a"), (NEWS, "b")], kind="myth"), "is not one of"),
            (json.dumps({"decision": "site", "kind": None, "reason": "x" * 401, "quotes": []}),
             "400"),
            (not_a_site([(WIKI, "a"), ("ftp://x.org/a", "b")]), "http"),
            (not_a_site([(WIKI, "a")]), "2 websites"),
            (not_a_site([(WIKI, "a"), (WIKI, "b")]), "2 websites"),
            (not_a_site([(WIKI, "a"), (WIKIDATA, "b")]), "Wikimedia"),
            (not_a_site([(WIKI, "a"), ("https://www.wikiwand.com/en/X", "b")]), "Wikimedia"),
            (SITE_WITH_QUOTE, "a site answer carries no quotes"),
        ],
    )  # fmt: skip
    def test_an_answer_out_of_shape(self, text: str, problem: str) -> None:
        with pytest.raises(R.ScopeReviewError, match=problem):
            R.parse_answer(text)

    @pytest.mark.parametrize(
        ("url", "site"),
        [
            ("https://en.wikipedia.org/wiki/X", R.WIKIMEDIA),
            ("https://de.wikipedia.org/wiki/X", R.WIKIMEDIA),
            ("https://www.wikidata.org/wiki/Q1", R.WIKIMEDIA),
            ("https://commons.wikimedia.org/wiki/File:X.jpg", R.WIKIMEDIA),
            ("https://www.bbc.co.uk/news/x", "bbc.co.uk"),
            ("https://www.abc.net.au/news/x", "abc.net.au"),
            ("https://www.britannica.com/place/x", "britannica.com"),
            ("https://whc.unesco.org/en/list/1", "unesco.org"),
            # copies of Wikipedia: its text, so no second website
            ("https://www.wikiwand.com/en/articles/Baltic_Sea_anomaly", R.WIKIMEDIA),
            ("https://dbpedia.org/page/Baltic_Sea_anomaly", R.WIKIMEDIA),
            ("https://www.wikizero.com/en/Baltic_Sea_anomaly", R.WIKIMEDIA),
            ("https://alchetron.com/Baltic-Sea-anomaly", R.WIKIMEDIA),
            ("https://en-academic.com/dic.nsf/enwiki/123", R.WIKIMEDIA),
            ("https://wikimili.com/en/Baltic_Sea_anomaly", R.WIKIMEDIA),
        ],
    )
    def test_the_website_of_a_url(self, url: str, site: str) -> None:
        assert R.website(url) == site

    def test_the_prompt_says_what_a_site_answer_and_a_mirror_are(self) -> None:
        prompt = R.prompt_for(sites()[0], "Q123")
        assert '"quotes" is []' in prompt and "Wikiwand" in prompt
        assert R.PROMPT_ID == "scope-nonsite-v2"


# ------------------------------------------------------------------------------ the rounds
class TestTheRounds:
    def test_round0_asks_every_candidate_twelve_per_batch(self, review) -> None:
        record = R.export_round(
            review["out"], review["handoff"], 0, load_harvest(review["harvest"])
        )
        assert record["questions"] == 4 and record["batches"] == 1
        assert record["signals"] == {"type": 2, "wikidata": 2, "no-item": 1, "pending": 1}
        manifest = OH.manifest(review["handoff"])
        assert {m["label"] for m in manifest} == {BALTIC, BOSNIA, KHORTYTSIA, NOITEM}
        assert {m["batch_id"] for m in manifest} == {"r0-001"}
        prompt = (review["handoff"] / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
        assert "NOT the question" in prompt and "word for word" in prompt

    def test_a_batch_holds_twelve(self, tmp_path: Path) -> None:
        rows = [
            site(f"{n:08d}-0000-4000-8000-000000000000", f"Rock {n}", "Natural feature")
            for n in range(13)
        ]
        write_export(tmp_path / "out", rows)
        write_harvest(tmp_path / "h", {r["id"]: None for r in rows})
        R.export_round(tmp_path / "out", tmp_path / "ho", 0, load_harvest(tmp_path / "h"))
        batches = [m["batch_id"] for m in OH.manifest(tmp_path / "ho")]
        assert batches.count("r0-001") == 12 and batches.count("r0-002") == 1

    def test_a_round_is_exported_once(self, review) -> None:
        harvest = load_harvest(review["harvest"])
        R.export_round(review["out"], review["handoff"], 0, harvest)
        with pytest.raises(R.ScopeReviewError, match="exported already"):
            R.export_round(review["out"], review["out"].parent / "other", 0, harvest)

    def test_rounds_run_in_order(self, review) -> None:
        harvest = load_harvest(review["harvest"])
        with pytest.raises(R.ScopeReviewError, match="count from 0"):
            R.export_round(review["out"], review["handoff"], -1, harvest)
        run_round0(review, {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, "no")])}, {})
        with pytest.raises(R.ScopeReviewError, match="round 1 was never exported"):
            R.export_round(review["out"], review["out"].parent / "handoff-r2", 2, harvest)

    def test_a_funnel_that_asks_nothing_is_refused(self, tmp_path: Path) -> None:
        write_export(tmp_path / "out", [r for r in sites() if r["id"] in (STONEHENGE, MUNGO)])
        write_harvest(tmp_path / "h")
        with pytest.raises(R.ScopeReviewError, match="asks nothing"):
            R.export_round(tmp_path / "out", tmp_path / "ho", 0, load_harvest(tmp_path / "h"))
        assert not list((tmp_path / "out").glob("*_R0.*")) and not (tmp_path / "ho").exists()

    def test_a_round_that_asks_nothing_is_refused_before_it_writes(self, review) -> None:
        """Round 0 answered `site` throughout: round 1 has nothing to re-ask. It writes no file, so
        the plan is not stopped by a round that was exported but never imported."""
        run_round0(review, {}, {})
        handoff = review["out"].parent / "handoff-r1"
        with pytest.raises(R.ScopeReviewError, match="asks nothing"):
            R.export_round(review["out"], handoff, 1, load_harvest(review["harvest"]))
        files = R.round_files(review["out"], 1)
        assert not any(p.exists() for p in (files.questions, files.snapshot, files.record))
        assert not handoff.exists()
        assert R.decisions(review["out"]) == {}
        assert R.write_wave(review["out"], WAVE, built_at="x")["o7_reinstated"] == 1

    def test_an_uncounted_answer_is_asked_three_times_at_most(self, review) -> None:
        """The first ask and two re-asks at one premise, as the acceptance judges re-ask."""
        uncounted = {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, "not on the page")])}
        bodies = {WIKI: WIKI_TEXT, NEWS: NEWS_TEXT}
        assert R.MAX_ASKS == 3
        for round_no in range(R.MAX_ASKS):
            result = run_round(review, round_no, uncounted, bodies)
            assert result["tally"]["not_a_site (not counted)"] == 1
        with pytest.raises(R.ScopeReviewError, match="asks nothing"):
            R.export_round(
                review["out"],
                review["out"].parent / "handoff-r3",
                3,
                load_harvest(review["harvest"]),
            )

    def test_a_counted_answer_whose_entry_moved_is_asked_again(self, review) -> None:
        """WD1 moves points in parallel: an answer about the old entry is none about the new."""
        counted_baltic(review)
        move_baltic(review)
        handoff = review["out"].parent / "handoff-r1"
        record = R.export_round(review["out"], handoff, 1, load_harvest(review["harvest"]))
        assert record["questions"] == 1 and record["signals"] == {"reask-moved": 1}
        [line] = OH.manifest(handoff)
        assert line["label"] == BALTIC
        assert "latitude 55.0" in (handoff / line["prompt_path"]).read_text(encoding="utf-8")

    def test_a_site_the_harvest_no_longer_lists_stops_the_re_ask(self, review) -> None:
        run_round0(review, {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, "no")])}, {})
        write_harvest(review["harvest"], {STONEHENGE: "Q39671"})
        with pytest.raises(R.ScopeReviewError, match="not in the harvest"):
            R.export_round(
                review["out"],
                review["out"].parent / "handoff-r1",
                1,
                load_harvest(review["harvest"]),
            )

    def test_a_retired_site_is_not_asked_again(self, review) -> None:
        run_round0(review, {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, "no")])}, {})
        rows = sites()
        rows[0]["scope_status"] = "retired"
        write_export(review["out"], rows, at="t1")
        with pytest.raises(R.ScopeReviewError, match="asks nothing"):
            R.export_round(
                review["out"],
                review["out"].parent / "handoff-r1",
                1,
                load_harvest(review["harvest"]),
            )

    def test_the_brief_names_the_batch_s_files_and_the_shape_check(self, review) -> None:
        R.export_round(review["out"], review["handoff"], 0, load_harvest(review["harvest"]))
        text = R.brief(review["out"], 0, "r0-001")
        assert "4 question(s)" in text
        assert f"{review['handoff'].resolve().as_posix()}-scratch/r0-001" in text
        assert "scope_review.py check-answer" in text and "opus_handoff.py answer" in text
        with pytest.raises(R.ScopeReviewError, match="no batch"):
            R.brief(review["out"], 0, "r0-009")

    def test_check_answer_prints_the_shape_problem(self, review) -> None:
        R.export_round(review["out"], review["handoff"], 0, load_harvest(review["harvest"]))
        assert R.check_answer(review["out"], 0, "r0-001", BALTIC, SITE_ANSWER) is None
        problem = R.check_answer(review["out"], 0, "r0-001", BALTIC, not_a_site([(WIKI, "a")]))
        assert problem is not None and "quotes" in problem
        with pytest.raises(R.ScopeReviewError, match="no question"):
            R.check_answer(review["out"], 0, "r0-001", STONEHENGE, SITE_ANSWER)

    def test_a_not_a_site_counts_with_two_found_quotes_from_two_websites(self, review) -> None:
        result = run_round0(
            review,
            {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, NEWS_TEXT)])},
            {WIKI: WIKI_TEXT, NEWS: NEWS_TEXT},
        )
        assert result["tally"] == {"not_a_site": 1, "site": 3}
        rows = {r["site_id"]: r for r in read_jsonl(R.round_files(review["out"], 0).answers)}
        assert rows[BALTIC]["counted"] and [q["outcome"] for q in rows[BALTIC]["quotes"]] == [
            Q.FOUND,
            Q.FOUND,
        ]
        assert rows[BALTIC]["premise"] == premise(sites()[0])

    def test_a_quote_the_page_does_not_hold_does_not_count(self, review) -> None:
        run_round0(
            review,
            {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, "a paraphrase of the page")])},
            {WIKI: WIKI_TEXT, NEWS: NEWS_TEXT},
        )
        rows = {r["site_id"]: r for r in read_jsonl(R.round_files(review["out"], 0).answers)}
        assert not rows[BALTIC]["counted"]
        assert [q["outcome"] for q in rows[BALTIC]["quotes"]] == [Q.FOUND, Q.NOT_FOUND]

    def test_a_page_that_cannot_be_fetched_does_not_count(self, review) -> None:
        run_round0(
            review,
            {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, NEWS_TEXT)])},
            {WIKI: WIKI_TEXT},
        )
        rows = {r["site_id"]: r for r in read_jsonl(R.round_files(review["out"], 0).answers)}
        assert not rows[BALTIC]["counted"]
        assert rows[BALTIC]["quotes"][1]["outcome"] == Q.FETCH_FAILED

    def test_two_found_quotes_of_one_website_do_not_count(self, review) -> None:
        """The shape check sees two websites; what is found decides - here only Wikipedia."""
        other = "https://de.wikipedia.org/wiki/Ostsee-Anomalie"
        run_round0(
            review,
            {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (other, WIKI_TEXT), (NEWS, "not there")])},
            {WIKI: WIKI_TEXT, other: WIKI_TEXT, NEWS: NEWS_TEXT},
        )
        rows = {r["site_id"]: r for r in read_jsonl(R.round_files(review["out"], 0).answers)}
        assert not rows[BALTIC]["counted"]

    def test_the_import_renders_from_the_round_s_snapshot(self, review) -> None:
        """WA rewrites descriptions in parallel: a refreshed export must not stale the round."""
        out = review["out"]
        R.export_round(out, review["handoff"], 0, load_harvest(review["harvest"]))
        rows = sites()
        rows[0]["excerpt"] = "A new description written since."
        write_export(out, rows, at="t1")
        answer_round(review["handoff"], out, 0, {})
        result = R.import_round(out, 0, Q.Library(REPO, out / "pages"), pages_for(out / "p", {}))
        assert result["answers"] == 4

    def test_a_changed_snapshot_is_refused(self, review) -> None:
        out = review["out"]
        R.export_round(out, review["handoff"], 0, load_harvest(review["harvest"]))
        answer_round(review["handoff"], out, 0, {})
        snapshot = R.round_files(out, 0).snapshot
        snapshot.write_text(snapshot.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with pytest.raises(R.ScopeReviewError, match="not the snapshot"):
            R.import_round(out, 0, Q.Library(REPO, out / "pages"), pages_for(out / "p", {}))

    def test_an_unanswered_round_is_refused(self, review) -> None:
        out = review["out"]
        R.export_round(out, review["handoff"], 0, load_harvest(review["harvest"]))
        with pytest.raises(R.ScopeReviewError, match="does not validate"):
            R.import_round(out, 0, Q.Library(REPO, out / "pages"), pages_for(out / "p", {}))

    def test_a_site_answer_with_a_quote_is_refused_by_the_shape_check(self, review) -> None:
        R.export_round(review["out"], review["handoff"], 0, load_harvest(review["harvest"]))
        problem = R.check_answer(review["out"], 0, "r0-001", KHORTYTSIA, SITE_WITH_QUOTE)
        assert problem is not None and "no quotes" in problem

    def test_an_answer_out_of_shape_stops_the_import_and_names_the_remedy(self, review) -> None:
        """An answer recorded past `check-answer`: named with the way out, never an AuditError
        about a page nobody collected."""
        out = review["out"]
        R.export_round(out, review["handoff"], 0, load_harvest(review["harvest"]))
        answer_round(review["handoff"], out, 0, {KHORTYTSIA: SITE_WITH_QUOTE})
        with pytest.raises(R.ScopeReviewError, match=rf"1 answer\(s\).*delete.*{KHORTYTSIA}"):
            R.import_round(out, 0, Q.Library(REPO, out / "pages"), pages_for(out / "pages", {}))
        assert not R.round_files(out, 0).answers.exists()

    def test_round1_asks_only_what_round0_left_uncounted(self, review) -> None:
        run_round0(
            review,
            {
                BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, "not on the page")]),
                BOSNIA: not_a_site([(WIKI, WIKI_TEXT), (NEWS, NEWS_TEXT)], "legend_or_hoax"),
            },
            {WIKI: WIKI_TEXT, NEWS: NEWS_TEXT},
        )
        handoff = review["out"].parent / "handoff-r1"
        record = R.export_round(review["out"], handoff, 1, load_harvest(review["harvest"]))
        assert record["questions"] == 1 and record["signals"] == {"reask-uncounted": 1}
        assert [m["label"] for m in OH.manifest(handoff)] == [BALTIC]

    def test_a_round_exported_but_not_imported_stops_the_plan(self, review) -> None:
        R.export_round(review["out"], review["handoff"], 0, load_harvest(review["harvest"]))
        with pytest.raises(R.ScopeReviewError, match="not imported"):
            R.decisions(review["out"])


# ------------------------------------------------------------------------------ the plan
def counted_baltic(review: dict[str, Path]) -> None:
    run_round0(
        review,
        {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, NEWS_TEXT), (NEWS, "not there")])},
        {WIKI: WIKI_TEXT, NEWS: NEWS_TEXT},
    )


WAVE = "2026-09-26"


class TestThePlan:
    def test_a_counted_not_a_site_is_retired_with_its_reason_and_found_quotes(self, review) -> None:
        counted_baltic(review)
        export = R.read_export(R.export_path(review["out"]))
        plan = R.build_plan(
            export, R.decisions(review["out"]), built_at="x", lane=L.scope_review_lane(WAVE)
        )
        cells = {(c.site_id, c.column): c for c in plan.changes}
        status, reason = cells[(BALTIC, "scope_status")], cells[(BALTIC, "scope_reason")]
        assert (status.old_value, status.new_value) == (None, "retired")
        assert reason.new_value == (
            "E3: not an archaeological site (natural_formation): A natural rock formation on the "
            "seabed, not a structure."
        )
        assert reason.new_value.startswith(L.NOT_A_SITE_PREFIX)
        sources = [e["source"] for e in reason.evidence]
        assert sources == [WIKI, NEWS, "opus:r0-001"]  # the unfound third quote is no evidence
        assert status.premise == premise(sites()[0])

    def test_o7_takes_back_an_oceania_retirement_for_the_date(self, review) -> None:
        export = R.read_export(R.export_path(review["out"]))
        plan = R.build_plan(export, {}, built_at="x", lane=L.scope_review_lane(WAVE))
        cells = {(c.site_id, c.column): c for c in plan.changes}
        assert set(cells) == {(MUNGO, "scope_status"), (MUNGO, "scope_reason")}
        assert (
            cells[(MUNGO, "scope_status")].old_value,
            cells[(MUNGO, "scope_status")].new_value,
        ) == (
            "retired",
            "in_scope",
        )
        assert "O7" in cells[(MUNGO, "scope_reason")].new_value
        assert plan.counters["o7_reinstated"] == 1

    @pytest.mark.parametrize(
        ("country", "lon", "start", "reason"),
        [
            ("Russia", 132.68, 1200, "E3: period_start 1200 is past"),  # not Oceania
            ("Australia", 143.08, 1600, "E3: period_start 1600 is past"),  # past 1500 too
            ("Australia", 143.08, 1200, "duplicate_of:0000"),  # retired for another reason
        ],
    )
    def test_nothing_else_is_taken_back(
        self, tmp_path: Path, country: str, lon: float, start: int, reason: str
    ) -> None:
        rows = [r for r in sites() if r["id"] != MUNGO]
        rows.append(
            site(MUNGO, "Lake Mungo", "Archaeological site", status="retired", reason=reason,
                 country=country, lat=-33.75, lon=lon, start=start)
        )  # fmt: skip
        write_export(tmp_path / "out", rows)
        export = R.read_export(R.export_path(tmp_path / "out"))
        assert R.reinstatements(export) == []

    def test_a_site_retired_since_the_question_is_skipped(self, review) -> None:
        counted_baltic(review)
        rows = sites()
        rows[0]["scope_status"] = "retired"
        write_export(review["out"], rows, at="t1")
        export = R.read_export(R.export_path(review["out"]))
        plan = R.build_plan(
            export, R.decisions(review["out"]), built_at="x", lane=L.scope_review_lane(WAVE)
        )
        assert BALTIC not in plan.sites
        assert [(v.site_id, v.reason) for v in plan.skipped] == [(BALTIC, "already-retired")]

    def test_an_entry_that_moved_since_the_answer_is_skipped(self, review) -> None:
        """The answer judged the entry at its name, type, point, country and dates: another
        entry by now (WD1 moved its point) is asked again, never written on the old answer."""
        counted_baltic(review)
        rows = sites()
        rows[0]["lat"] = 55.0
        rows[0]["premise"] = premise(rows[0])
        write_export(review["out"], rows, at="t1")
        export = R.read_export(R.export_path(review["out"]))
        plan = R.build_plan(
            export, R.decisions(review["out"]), built_at="x", lane=L.scope_review_lane(WAVE)
        )
        assert BALTIC not in plan.sites
        assert [(v.site_id, v.reason) for v in plan.skipped] == [(BALTIC, "premise-moved")]
        assert "export-round" in plan.skipped[0].note

    def test_the_latest_answer_decides(self, review) -> None:
        """Counted on the old entry, asked again on the moved one and answered `site`: the new
        answer decides, so the site is not retired."""
        counted_baltic(review)
        move_baltic(review)
        run_round(review, 1, {}, {})
        assert BALTIC not in R.decisions(review["out"])
        export = R.read_export(R.export_path(review["out"]))
        plan = R.build_plan(
            export, R.decisions(review["out"]), built_at="x", lane=L.scope_review_lane(WAVE)
        )
        assert BALTIC not in plan.sites and plan.skipped == ()

    def test_a_moved_entry_counted_again_is_written_on_the_new_answer(self, review) -> None:
        counted_baltic(review)
        moved = move_baltic(review)
        run_round(
            review,
            1,
            {BALTIC: not_a_site([(WIKI, WIKI_TEXT), (NEWS, NEWS_TEXT)])},
            {WIKI: WIKI_TEXT, NEWS: NEWS_TEXT},
        )
        decided = R.decisions(review["out"])
        assert decided[BALTIC]["round"] == 1
        export = R.read_export(R.export_path(review["out"]))
        plan = R.build_plan(export, decided, built_at="x", lane=L.scope_review_lane(WAVE))
        status = {(c.site_id, c.column): c for c in plan.changes}[(BALTIC, "scope_status")]
        assert status.new_value == "retired" and status.premise == moved["premise"]
        assert plan.skipped == ()

    def test_a_wave_is_its_first_hundred_sites(self, tmp_path: Path) -> None:
        rows = [
            site(f"{n:08d}-0000-4000-8000-000000000000", f"Rock {n}", "Natural feature")
            for n in range(101)
        ]
        write_export(tmp_path / "out", rows)
        export = R.read_export(R.export_path(tmp_path / "out"))
        decided = {
            r["id"]: {"premise": r["premise"], "kind": "natural_formation", "reason": "rock",
                      "quotes": [], "answered_by": "r0-001"}
            for r in rows
        }  # fmt: skip
        plan = R.build_plan(export, decided, built_at="x", lane=L.scope_review_lane(WAVE))
        wave = R.first_wave(plan)
        assert len(plan.sites) == 101 and len(wave.sites) == R.MAX_SITES == 100
        assert wave.sites == plan.sites[:100]
        assert wave.counters["left_for_later_waves"] == 1


class TestTheWave:
    def test_the_default_directory_is_the_wave_lane_s(self) -> None:
        lane = L.scope_review_lane(WAVE)
        assert A.lane_dir(lane) == R.DEFAULT_OUT / WAVE
        assert L.resolve_lane(f"scope-review-{WAVE}") == lane

    def test_a_wave_writes_its_plan_rollback_and_source(self, review) -> None:
        counted_baltic(review)
        result = R.write_wave(review["out"], WAVE, built_at="2026-09-26T04:00:00+00:00")
        target = review["out"] / WAVE
        assert result["sites"] == 2 and result["lane"] == f"scope-review-{WAVE}"
        for name in ("PLAN.jsonl", "SKIPPED.jsonl", "PLAN.md", "ROLLBACK.sql", "SOURCE.json"):
            assert (target / name).is_file(), name
        lane = L.scope_review_lane(WAVE)
        records = A.load_records(target / "PLAN.jsonl")
        A.validate_records(records, lane=lane)
        assert {r.site_id for r in records} == {BALTIC, MUNGO}
        assert f"'{lane.run_stamp}'" in A.apply_statement(records, lane)
        assert "E3: not an archaeological site" in (target / "PLAN.md").read_text(encoding="utf-8")

    def test_a_second_wave_from_the_same_export_is_refused(self, review) -> None:
        counted_baltic(review)
        R.write_wave(review["out"], WAVE, built_at="x")
        with pytest.raises(R.ScopeReviewError, match="run `export` again"):
            R.write_wave(review["out"], WAVE + "b", built_at="x")

    def test_the_next_wave_from_a_new_export_plans_what_is_left(self, review) -> None:
        counted_baltic(review)
        R.write_wave(review["out"], WAVE, built_at="x")
        rows = sites()
        rows[0]["scope_status"] = "retired"
        write_export(review["out"], rows, at="t1")
        result = R.write_wave(review["out"], WAVE + "b", built_at="x")
        assert result["sites"] == 1 and result["o7_reinstated"] == 1

    def test_a_delivered_wave_is_never_replaced(self, review) -> None:
        counted_baltic(review)
        R.write_wave(review["out"], WAVE, built_at="x")
        write_export(review["out"], at="t1")
        with pytest.raises(R.ScopeReviewError, match="never replaced"):
            R.write_wave(review["out"], WAVE, built_at="x")

    def test_a_wave_with_nothing_to_write_is_refused(self, tmp_path: Path) -> None:
        write_export(tmp_path / "out", [r for r in sites() if r["id"] != MUNGO])
        with pytest.raises(R.ScopeReviewError, match="nothing to write"):
            R.write_wave(tmp_path / "out", WAVE, built_at="x")

    def test_the_cli_refuses_a_wave_label_apply_could_not_resolve(self, review, capsys) -> None:
        with pytest.raises(SystemExit):
            R.main(["write", "--out", str(review["out"]), "--wave", "wave-1"])
        assert "not a wave label" in capsys.readouterr().err


class TestTheWaveLane:
    def test_a_wave_label_resolves_and_nothing_else_does(self) -> None:
        lane = L.resolve_lane("scope-review-2026-09-26b")
        assert lane.run_stamp == "2026-09-26b_mechanical-scope-review"
        assert lane.out_dir_name == "mechanical_scope_review/2026-09-26b"
        for bad in ("scope-review-", "scope-review-w1", "scope-review-2026-09-26; x"):
            with pytest.raises(KeyError):
                L.resolve_lane(bad)
        with pytest.raises(ValueError, match="not a wave label"):
            L.scope_review_lane("latest")

    def test_the_premise_is_what_the_decision_rests_on_and_not_the_description(self) -> None:
        sql = L.SCOPE_REVIEW_PREMISE_SQL
        for column in ("name", "site_type", "lat", "lon", "country", "period_start", "period_end"):
            assert f"u.{column}" in sql
        assert "description" not in sql

    def test_the_readback_counts_the_review_s_own_rows(self) -> None:
        lane = L.scope_review_lane(WAVE)
        sql = A.readback_for(lane)
        assert sql is L.scope_review_readback(lane)
        assert "curated rows retired as no archaeological site" in sql
        assert "LIKE 'E3: not an archaeological site%'" in sql
        assert "curated Oceania rows retired for their date" in sql
        assert L.in_oceania_sql() in sql
        assert f"'{lane.run_stamp}'" in sql

    def test_the_residual_is_the_o7_window(self) -> None:
        lane = L.scope_review_lane(WAVE)
        assert lane.post_commit_residual.predicate == (
            f"{L.outside_e3_window()} AND scope_status IS NULL"
        )
        assert "country" in lane.post_commit_residual.predicate
