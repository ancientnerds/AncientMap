"""L5, the journalled link and name pass (HUMAN_ONLY B1-L, B1-N, Nr. 7, decided 2026-09-26).

What is tested, DB-less and without the network:

* the population: its groups from the waves' records and `names.jsonl`, the pinned rename, who is
  not asked and why;
* the question and the answer's exact shape - every rule an answer can break on its own;
* the machine checks (`decide.py`): quotes found in the fetched pages, a replacement item at the
  site's place, the article kept or written resolved as the refresh resolves it;
* the handoff: a round exported, briefed, shape-checked, answered, imported, re-asked;
* the plan: link steps through `qid_repair.render_split(removals=True)`, the name lane, the skips;
* a link step's commands against a fake production, and the probes' shapes;
* the title resolution's transport and the User-Agent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import qid_repair as QR  # noqa: E402
from l5 import decide as D  # noqa: E402
from l5 import handoff as H  # noqa: E402
from l5 import links as LK  # noqa: E402
from l5 import plan as L5P  # noqa: E402
from l5 import population as POP  # noqa: E402
from l5 import questions as QN  # noqa: E402
from l5 import web  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

TIKAL = "11111111-2222-4333-8444-555555555555"
ZOQUE = "ed186ea9-9ed1-415d-828b-97d9f21401d2"
OTHER = "99999999-8888-4777-8666-555555555555"
READ_AT = "2026-09-26T01:32:44+00:00"
NOW = "2026-09-26T02:00:00+00:00"
ENT = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
WP = "https://en.wikipedia.org/wiki/"


def site(sid: str = TIKAL, **over: Any) -> dict[str, Any]:
    row = {
        "site_id": sid,
        "source_id": "ancient_nerds",
        "name": "Tikal",
        "name_normalized": "tikal",
        "country": "Guatemala",
        "lat": "17.2220",
        "lon": "-89.6237",
        "site_type": "Settlement",
        "period_start": -600,
        "period_name": "1000 BC - 1 AD",
        "source_url": WP + "Mundo_Perdido,_Tikal",
        "scope_status": None,
        "description": "Mundo Perdido is the largest ceremonial complex of Tikal.",
        "ext": [
            {"kind": "enwiki_title", "value": "Mundo Perdido, Tikal"},
            {"kind": "wikidata_qid", "value": "Q100"},
        ],
    }
    row.update(over)
    return row


def member(sid: str = TIKAL, *, ask_name: bool = False) -> dict[str, Any]:
    return {
        "site_id": sid,
        "name": "Tikal",
        "groups": ["wave1-unresolved"],
        "why": ["wave1-unresolved: named Tikal, linked as Mundo Perdido"],
        "ask_name": ask_name,
        "excluded": None,
    }


def read_of(*sites: dict[str, Any], sharers: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"read_at": READ_AT, "sites": {s["site_id"]: s for s in sites}, "sharers": sharers or {}}


def cell(verdict: str, value: str | None = None, quotes: list[dict[str, str]] | None = None):
    return {"verdict": verdict, "value": value, "why": "read it", "quotes": quotes or []}


def q(source: str, text: str) -> dict[str, str]:
    return {"source": source, "quote": text}


def answer(sid: str = TIKAL, **cells: Any) -> dict[str, Any]:
    base = {
        "site_id": sid,
        "wikidata_qid": cell("REPLACE", "Q200", [q(ENT.format("Q200"), "Tikal")]),
        "enwiki_title": cell(
            "REPLACE", "Tikal", [q(WP + "Tikal", "Tikal is the ruin of an ancient city")]
        ),
        "source_url": cell("KEEP"),
    }
    base.update(cells)
    return base


def parse(data: dict[str, Any], s: dict[str, Any] | None = None, m: dict[str, Any] | None = None):
    return QN.parse(json.dumps(data), s or site(), m or member())


# ------------------------------------------------------------------------------ the population
class TestThePopulation:
    NAMES = [
        {
            "site_id": OTHER,
            "name": "Dolmens of Sardinia",
            "link_suspect": ["generic"],
            "qid": "Q101659",
            "en_label": "dolmen",
            "p31": ["type of building"],
            "shared_by": 1,
            "p625_km": None,
            "class": "keep",
        },
        {
            "site_id": ZOQUE,
            "name": "Zoque Culture Archaeological Zone",
            "link_suspect": [],
            "qid": "Q4384315",
            "en_label": "Chiapa de Corzo",
            "p31": ["archaeological site"],
            "shared_by": 1,
            "p625_km": 0.55,
            "class": "N7",
            "n7": "anchor-is-a-site",
        },
    ]

    def test_the_groups_come_from_the_waves_and_the_classifier(self) -> None:
        members = {m.site_id: m for m in POP.members(self.NAMES)}
        assert members[OTHER].groups == ("link-suspect",)
        assert "generic" in members[OTHER].why[0] and not members[OTHER].ask_name
        assert members[ZOQUE].groups == ("name-n7",)
        assert not members[ZOQUE].ask_name, "the Nr. 7 rename is decided, not asked"
        tikal = [m for m in members.values() if m.groups == ("wave1-unresolved",)]
        assert [m.name for m in tikal] == ["Tikal"]
        assert tikal[0].ask_name, "a record that contradicts itself is asked its name too"
        contradictory = [m for m in members.values() if m.site_id in POP.SELF_CONTRADICTORY]
        assert len(contradictory) == 3 and all(m.ask_name for m in contradictory)
        wave2 = [m for m in members.values() if "wave2-unresolved" in m.groups]
        assert len(wave2) == sum(1 for s in QR.WAVE2_SITES if s.rule == "unresolved") == 47
        assert "6aa4c8de-3794-42fe-b68e-6b6ab77bd8ed" in members  # Delphinion, found by WE

    def test_a_site_listed_twice_in_one_group_is_refused(self) -> None:
        with pytest.raises(MP.PlanError, match="listed twice"):
            POP.members([self.NAMES[0], self.NAMES[0]])

    @pytest.mark.parametrize(
        ("over", "reason"),
        [
            ({"source_id": "lyra"}, "a lyra row"),
            ({"scope_status": "retired"}, "retired"),
            ({"ext": [{"kind": "wikidata_qid", "value": "Q1"}]}, "links:"),
            ({"site_id": "ce7db300-8777-425d-917a-2f6d9f325b58"}, "duplicate candidate: Caesarea"),
        ],
    )
    def test_who_is_not_asked(self, over: dict[str, Any], reason: str) -> None:
        assert str(POP.excluded(site(**over))).startswith(reason)
        assert POP.excluded(site()) is None

    def test_the_delivered_population_is_the_measured_one(self) -> None:
        path = POP.OUT / "COUNTS.json"
        if not path.exists():
            pytest.skip(f"{path} not built")
        counts = json.loads(path.read_text(encoding="utf-8"))
        assert counts["members"] == sum(counts["by_group"].values())
        assert counts["asked"] + sum(counts["excluded"].values()) == counts["members"]


# ------------------------------------------------------------------------------ the question
class TestTheQuestion:
    def test_the_prompt_is_a_pure_function_of_the_read(self) -> None:
        r = read_of(site())
        one = QN.prompt(site(), member(), r)
        assert one == QN.prompt(site(), member(), r)
        assert "wikidata_qid: Q100" in one and "enwiki_title: Mundo Perdido, Tikal" in one
        assert '"name"' not in one and "6. The name" not in one
        assert "AN EARLIER ANSWER" not in one

    def test_a_name_question_and_a_re_ask_say_so(self) -> None:
        r = read_of(site())
        text = QN.prompt(site(), member(ask_name=True), r, "wikidata_qid: a quote does not count")
        assert "6. The name" in text and '"name": {"verdict": "KEEP | RENAME"' in text
        assert "AN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED" in text
        assert "a quote does not count" in text

    def test_the_sharers_of_the_item_are_shown(self) -> None:
        sharer = {
            "site_id": OTHER,
            "name": "Mundo Perdido",
            "lat": "17.2",
            "lon": "-89.6",
            "scope_status": None,
        }
        text = QN.prompt(site(), member(), read_of(site(), sharers={"Q100": [sharer]}))
        assert f"also carried by the curated site Mundo Perdido ({OTHER}" in text

    def test_a_well_formed_answer_parses(self) -> None:
        got = parse(answer())
        assert (got.qid.verdict, got.qid.value, got.title.value) == ("REPLACE", "Q200", "Tikal")
        assert got.name is None

    @pytest.mark.parametrize(
        ("change", "says"),
        [
            ({"wikidata_qid": cell("MAYBE", None, [q(WP + "X", "x")])}, "is not one of"),
            ({"wikidata_qid": cell("KEEP", "Q100", [q(WP + "X", "x")])}, "goes with REPLACE"),
            ({"wikidata_qid": cell("REPLACE", None, [q(WP + "X", "x")])}, "goes with REPLACE"),
            ({"wikidata_qid": cell("KEEP")}, "needs at least one quote"),
            ({"wikidata_qid": cell("REPLACE", "Q100", [q(ENT.format("Q100"), "x")])}, "that is KEEP"),
            ({"wikidata_qid": cell("REPLACE", "Q300", [q(WP + "Tikal", "x")])}, "cites"),
            ({"wikidata_qid": cell("REPLACE", "item", [q(ENT.format("item"), "x")])}, "not an item id"),
            ({"enwiki_title": cell("REPLACE", "Tikal", [q(WP + "Yaxha", "x")])}, "cites"),
            ({"enwiki_title": cell("REPLACE", "Tikal#History", [q(WP + "Tikal", "x")])}, "not an article"),
            ({"wikidata_qid": cell("REMOVE", None, [q(WP + "X", "x")])}, "has a Wikidata item"),
            ({"source_url": cell("CLEAR", None, [q(WP + "X", "x")])}, "KEEP with value null"),
            ({"wikidata_qid": cell("KEEP", None, [q("https://ancientnerds.com/sites/x", "x")])}, "never fetched"),
            ({"wikidata_qid": cell("KEEP", None, [q("wikidata", "x")])}, "must be the URL"),
        ],
    )  # fmt: skip
    def test_each_shape_rule_refuses(self, change: dict[str, Any], says: str) -> None:
        with pytest.raises(QN.AnswerError, match=says):
            parse(answer(**change))

    def test_the_answer_must_carry_exactly_its_keys(self) -> None:
        with pytest.raises(QN.AnswerError, match="carries"):
            parse({**answer(), "name": cell("KEEP")})
        with pytest.raises(QN.AnswerError, match="carries"):
            parse(answer(), m=member(ask_name=True))
        with pytest.raises(QN.AnswerError, match="not this question"):
            parse(answer(sid=OTHER))

    def test_both_links_removed_on_an_enwiki_source_url_decide_the_url(self) -> None:
        gone = {
            "wikidata_qid": cell("REMOVE", None, [q(ENT.format("Q100"), "Mundo Perdido")]),
            "enwiki_title": cell("REMOVE", None, [q(WP + "Mundo_Perdido,_Tikal", "Mundo Perdido")]),
        }
        with pytest.raises(QN.AnswerError, match="REPLACE or CLEAR it"):
            parse(answer(**gone))
        with pytest.raises(QN.AnswerError, match="English Wikipedia article"):
            parse(answer(**gone, source_url=cell("REPLACE", WP + "Tikal", [q(WP + "Tikal", "x")])))
        page = "https://whc.unesco.org/en/list/64/"
        got = parse(
            answer(**gone, source_url=cell("REPLACE", page, [q(page, "Tikal National Park")]))
        )
        assert got.source_url.value == page
        assert (
            parse(
                answer(**gone, source_url=cell("CLEAR", None, [q(WP + "X", "x")]))
            ).source_url.verdict
            == "CLEAR"
        )

    def test_a_rename_quotes_its_new_name(self) -> None:
        m = member(ask_name=True)
        ok = answer(
            name=cell("RENAME", "Tikal National Park", [q(WP + "Tikal", "Tikal National Park")])
        )
        assert parse(ok, m=m).name is not None
        with pytest.raises(QN.AnswerError, match="with the new name in the quote"):
            parse(answer(name=cell("RENAME", "Yax Mutul", [q(WP + "Tikal", "Tikal")])), m=m)
        with pytest.raises(QN.AnswerError, match="that is KEEP"):
            parse(answer(name=cell("RENAME", "Tikal", [q(WP + "Tikal", "Tikal")])), m=m)
        assert parse(answer(name=cell("KEEP")), m=m).name.verdict == "KEEP"


# ------------------------------------------------------------------------------ the decision
def store(
    pages: Path, url: str, body: bytes, *, content_type: str = "text/html", status: int = 200
) -> None:
    Q.store_page(
        pages, url, status=status, final_url=url, content_type=content_type, body=body, error="",
        fetched_at=NOW,
    )  # fmt: skip


def entity(qid: str, label: str, lat: float | None, lon: float | None) -> bytes:
    claims = {}
    if lat is not None:
        value = {"latitude": lat, "longitude": lon, "precision": 0.0001, "globe": "Q2"}
        claims["P625"] = [{"mainsnak": {"datavalue": {"value": value}}, "rank": "normal"}]
    body = {"entities": {qid: {"id": qid, "labels": {"en": {"value": label}}, "claims": claims}}}
    return json.dumps(body).encode()


TITLES = {
    "Tikal": {"canonical_title": "Tikal", "qid": "Q200", "lat": 17.2221, "lon": -89.6237,
              "disambiguation": False, "redirected": False},
    "Mundo Perdido, Tikal": {"canonical_title": "Mundo Perdido, Tikal", "qid": "Q100", "lat": None,
                             "lon": None, "disambiguation": False, "redirected": False},
}  # fmt: skip


@pytest.fixture
def library(tmp_path: Path) -> Q.Library:
    pages = tmp_path / "pages"
    store(
        pages,
        ENT.format("Q200"),
        entity("Q200", "Tikal", 17.2225, -89.6235),
        content_type="application/json",
    )
    store(
        pages,
        ENT.format("Q300"),
        entity("Q300", "Tikal", 17.40, -89.62),
        content_type="application/json",
    )
    store(
        pages,
        ENT.format("Q400"),
        entity("Q999", "Tikal", 17.2225, -89.6235),
        content_type="application/json",
    )
    store(
        pages,
        WP + "Tikal",
        b"<html><body><p>Tikal is the ruin of an ancient city.</p></body></html>",
    )
    return Q.Library(REPO, pages)  # fmt: skip


def decide(
    data: dict[str, Any], library: Q.Library, titles: dict[str, Any] | None = None
) -> D.Decision:
    return D.decide(
        site(), member(), parse(data), round_name="r1", answered_by="r1-b01", library=library,
        titles=TITLES if titles is None else titles,
    )  # fmt: skip


class TestTheMachineChecks:
    def test_a_sourced_replacement_at_the_site_s_place_is_decided(self, library: Q.Library) -> None:
        got = decide(answer(), library)
        assert got.status == D.DECIDED, got.reason
        assert (
            got.cells["wikidata_qid"]["old"] == "Q100"
            and got.cells["wikidata_qid"]["new"] == "Q200"
        )
        assert "m from the stored point" in got.cells["wikidata_qid"]["note"]
        assert "resolved as the refresh resolves it" in got.cells["enwiki_title"]["note"]
        assert got.cells["enwiki_title"]["quote_outcomes"] == ["found: visible text"]
        assert got.cells["source_url"]["new"] == got.cells["source_url"]["old"]

    def test_a_quote_the_page_does_not_hold_holds_the_site(self, library: Q.Library) -> None:
        bad = cell("REPLACE", "Tikal", [q(WP + "Tikal", "Tikal was founded by aliens")])
        got = decide(answer(enwiki_title=bad), library)
        assert got.status == D.HELD and got.reason.startswith(
            "enwiki_title: a quote does not count"
        )

    def test_a_replacement_item_far_from_the_site_is_held(self, library: Q.Library) -> None:
        far = cell("REPLACE", "Q300", [q(ENT.format("Q300"), "Tikal")])
        got = decide(
            answer(wikidata_qid=far, enwiki_title=cell("REMOVE", None, [q(WP + "Tikal", "Tikal")])),
            library,
        )
        assert got.status == D.HELD and "not proven at the site's place" in got.reason

    def test_an_entity_page_of_another_item_is_a_redirect_and_held(
        self, library: Q.Library
    ) -> None:
        moved = cell("REPLACE", "Q400", [q(ENT.format("Q400"), "Tikal")])
        got = decide(
            answer(
                wikidata_qid=moved, enwiki_title=cell("REMOVE", None, [q(WP + "Tikal", "Tikal")])
            ),
            library,
        )
        assert got.status == D.HELD and "a redirect" in got.reason

    @pytest.mark.parametrize(
        ("resolution", "says"),
        [
            ({"canonical_title": None}, "no English Wikipedia page"),
            ({"disambiguation": True}, "disambiguation"),
            ({"redirected": True, "canonical_title": "Tikal National Park"}, "redirects"),
            ({"qid": "Q777"}, "the daily refresh would write another pair"),
        ],
    )
    def test_the_article_must_be_the_item_s_own(
        self, library: Q.Library, resolution: dict[str, Any], says: str
    ) -> None:
        titles = {**TITLES, "Tikal": {**TITLES["Tikal"], **resolution}}
        got = decide(answer(), library, titles)
        assert got.status == D.HELD and says in got.reason


# ------------------------------------------------------------------------------ the handoff
class FakeClient:
    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def get(self, url: str) -> Any:  # every page of the tests is stored beforehand
        raise AssertionError(f"no page should be fetched: {url}")


def resolver(titles: list[str], client: Any) -> dict[str, dict[str, Any]]:
    return {t: TITLES[t] for t in titles}


@pytest.fixture
def out(tmp_path: Path, library: Q.Library) -> Path:
    directory = tmp_path / "l5"
    (directory / "export").mkdir(parents=True)
    read = read_of(site(), site(OTHER, name="Mundo Perdido", ext=[
        {"kind": "enwiki_title", "value": "Mundo Perdido, Tikal"}, {"kind": "wikidata_qid", "value": "Q100"}]))  # fmt: skip
    (directory / "export" / POP.READ_FILE).write_text(json.dumps(read), encoding="utf-8")
    records = [member(), {**member(OTHER), "name": "Mundo Perdido", "ask_name": True}]
    (directory / "POPULATION.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    (directory / "pages").mkdir()
    for path in library.pages.iterdir():
        (directory / "pages" / path.name).write_bytes(path.read_bytes())
    return directory


def answer_all(root: Path, record: H.Round, texts: dict[str, dict[str, Any]]) -> None:
    for batch_id, sids in record.batches.items():
        for sid in sids:
            OH.write_answer(
                root, batch_id=batch_id, stage=QN.STAGE, label=sid,
                text=json.dumps(texts[sid]), answered_by=batch_id, now=lambda: NOW,
            )  # fmt: skip


class TestTheHandoff:
    def test_a_round_is_exported_briefed_checked_imported_and_re_asked(
        self, out: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(H, "REPO", tmp_path)
        record = H.export_round(
            out, tmp_path / "handoff-r1", H.first_round_sites(out), per_batch=1, now=lambda: NOW
        )
        assert record.name == "r1" and sorted(record.batches) == ["r1-b01", "r1-b02"]
        assert record.handoff == "handoff-r1"
        text = H.brief(out, "r1", "r1-b01")
        assert "handoff-r1/r1-b01/MANIFEST.jsonl" in text and "check-answer --round r1" in text
        assert H.check_answer(out, "r1", "r1-b01", TIKAL, json.dumps(answer())) is None
        assert "carries" in str(
            H.check_answer(out, "r1", "r1-b02", OTHER, json.dumps(answer(OTHER)))
        )
        with pytest.raises(H.HandoffError, match="no question"):
            H.check_answer(out, "r1", "r1-b02", TIKAL, "{}")

        with pytest.raises(H.HandoffError, match="does not validate"):
            H.import_round(out, "r1", http=FakeClient, resolver=resolver, now=lambda: NOW)
        wrong_name = answer(OTHER, name=cell("RENAME", "Lost World", [q(WP + "Tikal", "Tikal")]))
        answer_all(tmp_path / "handoff-r1", record, {TIKAL: answer(), OTHER: wrong_name})
        summary = H.import_round(
            out, "r1", http=FakeClient, resolver=resolver, now=lambda: NOW, pace=0
        )
        assert (summary["decided"], summary["held"]) == (1, 1)
        decisions = {d["site_id"]: d for d in H.load_decisions(out)}
        assert decisions[TIKAL]["status"] == D.DECIDED
        assert decisions[OTHER]["reason"].startswith("shape: name: a RENAME quotes")
        assert set(json.loads((out / H.TITLES_FILE).read_text(encoding="utf-8"))["titles"]) == {
            "Tikal"
        }
        assert {r["url"] for r in H._read_jsonl(out / H.PAGES_FILE)} == {
            ENT.format("Q200"),
            WP + "Tikal",
        }

        again = H.export_round(
            out,
            tmp_path / "handoff-r2",
            sorted(H.held_sites(out)),
            earlier=H.held_sites(out),
            now=lambda: NOW,
        )
        assert again.name == "r2" and again.sites == [OTHER]
        prompt = next((tmp_path / "handoff-r2").glob("*/l5/*.prompt.txt")).read_text(
            encoding="utf-8"
        )
        assert "AN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED" in prompt
        keep = answer(OTHER, wikidata_qid=cell("KEEP", None, [q(ENT.format("Q200"), "Tikal")]),
                      enwiki_title=cell("KEEP", None, [q(WP + "Tikal", "Tikal is the ruin")]),
                      name=cell("KEEP"))  # fmt: skip
        answer_all(tmp_path / "handoff-r2", again, {OTHER: keep})
        H.import_round(out, "r2", http=FakeClient, resolver=resolver, now=lambda: NOW, pace=0)
        merged = {d["site_id"]: d for d in H.load_decisions(out)}
        assert merged[TIKAL]["round"] == "r1"
        assert merged[OTHER]["round"] == "r2" and merged[OTHER]["status"] == D.DECIDED
        assert (
            "Mundo Perdido, Tikal"
            in json.loads((out / H.TITLES_FILE).read_text(encoding="utf-8"))["titles"]
        )
        assert len(H.load_rounds(out)) == 2 and (out / H.ANSWERS_DIR / "r2.jsonl").exists()

    def test_a_round_is_never_exported_into_a_used_directory(
        self, out: Path, tmp_path: Path
    ) -> None:
        used = tmp_path / "used"
        used.mkdir()
        (used / "x").write_text("x", encoding="utf-8")
        with pytest.raises(H.HandoffError, match="not empty"):
            H.export_round(out, used, [TIKAL])
        with pytest.raises(H.HandoffError, match="not asked by L5"):
            H.export_round(out, tmp_path / "new", ["00000000-0000-4000-8000-000000000000"])

    def test_batches_are_in_site_order_and_bounded(self) -> None:
        got = H.batches(["c", "a", "b"], "r1", 2)
        assert got == {"r1-b01": ["a", "b"], "r1-b02": ["c"]}
        with pytest.raises(H.HandoffError):
            H.batches(["a"], "r1", 0)


# ------------------------------------------------------------------------------ the plan
def decided(sid: str = TIKAL, **cells: Any) -> dict[str, Any]:
    base = {
        "wikidata_qid": {"verdict": "REPLACE", "old": "Q100", "new": "Q200", "why": "w", "quotes": [q(ENT.format("Q200"), "Tikal")], "note": "n"},
        "enwiki_title": {"verdict": "REMOVE", "old": "Mundo Perdido, Tikal", "new": None, "why": "w", "quotes": [q(WP + "Tikal", "T")], "note": ""},
        "source_url": {"verdict": "KEEP", "old": WP + "Mundo_Perdido,_Tikal", "new": WP + "Mundo_Perdido,_Tikal", "why": "w", "quotes": [], "note": ""},
    }  # fmt: skip
    base.update(cells)
    return {"site_id": sid, "name": "Tikal", "status": D.DECIDED, "reason": "", "round": "r1",
            "answered_by": "r1-b01", "cells": base}  # fmt: skip


def live(
    *sites: dict[str, Any],
    holders: dict[str, Any] | None = None,
    keys: dict[str, str] | None = None,
) -> L5P.Live:
    return L5P.Live({s["site_id"]: s for s in sites}, holders or {}, keys or {})  # fmt: skip


ZOQUE_ROW = site(
    ZOQUE,
    name="Zoque Culture Archaeological Zone",
    name_normalized="zoque culture archaeological zone",
)


class TestThePlan:
    def test_a_decided_site_becomes_its_link_rows_and_the_pinned_rename(self) -> None:
        built = L5P.build(
            [decided()],
            {TIKAL: site()},
            live(site(), ZOQUE_ROW, keys={"Chiapa de Corzo": "chiapa de corzo"}),
        )
        assert [(c.table, c.kind, c.old_value, c.new_value) for c in built.links] == [
            ("site_external_ids", "wikidata_qid", "Q100", "Q200"),
            ("site_external_ids", "enwiki_title", "Mundo Perdido, Tikal", None),
        ]
        assert all(
            c.test_id.startswith("L5/") and c.confidence == "authoritative" for c in built.links
        )
        names = [(v.column, v.old_value, v.new_value) for v in built.names]
        assert names == [
            ("name", "Zoque Culture Archaeological Zone", "Chiapa de Corzo"),
            ("name_normalized", "zoque culture archaeological zone", "chiapa de corzo"),
        ]
        counts = built.counts()
        assert (
            counts["link:site_external_ids.enwiki_title:remove"] == 1 and counts["name_sites"] == 1
        )

    def test_a_site_changed_since_the_question_is_skipped(self) -> None:
        moved = site(
            ext=[
                {"kind": "enwiki_title", "value": "Tikal"},
                {"kind": "wikidata_qid", "value": "Q100"},
            ]
        )
        built = L5P.build([decided()], {TIKAL: site()}, live(moved), pinned={})
        assert built.links == [] and built.skipped[0]["reason"] == "changed-since-the-question"

    def test_a_replacement_another_curated_site_carries_is_a_duplicate_not_a_link(self) -> None:
        holders = {"Q200": [{"qid": "Q200", "site_id": OTHER, "name": "Tikal (2)"}]}
        built = L5P.build([decided()], {TIKAL: site()}, live(site(), holders=holders), pinned={})
        assert built.links == [] and built.skipped[0]["reason"] == "item-carried-by-another-site"

    def test_a_rename_carries_the_key_postgres_computed(self) -> None:
        rename = {"verdict": "RENAME", "old": "Tikal", "new": "Tikal National Park", "why": "w",
                  "quotes": [q(WP + "Tikal", "Tikal National Park")], "note": ""}  # fmt: skip
        built = L5P.build(
            [decided(name=rename)],
            {TIKAL: site()},
            live(site(), keys={"Tikal National Park": "tikal national park"}),
            pinned={},
        )
        assert [(v.column, v.new_value) for v in built.names] == [
            ("name", "Tikal National Park"),
            ("name_normalized", "tikal national park"),
        ]
        assert "Tikal National Park" in L5P.keys_sql(
            ["Tikal National Park"]
        ) and "unaccent" in L5P.keys_sql(["x"])

    def test_a_held_decision_never_reaches_the_plan(self) -> None:
        with pytest.raises(MP.PlanError, match="not decided"):
            L5P.build([{**decided(), "status": D.HELD}], {TIKAL: site()}, live(site()))

    def test_steps_hold_at_most_a_hundred_whole_sites(self) -> None:
        rows = [
            QR.Change(f"{i:08d}-0000-4000-8000-000000000000", "s", kind, "a", "b", "L5/x", "authoritative", (), f"k{i}{kind}")
            for i in range(150) for kind in ("wikidata_qid", "enwiki_title")
        ]  # fmt: skip
        got = L5P.steps(rows)
        assert [len({c.site_id for c in s}) for s in got] == [100, 50]
        assert sum(len(s) for s in got) == 300

    def test_a_step_renders_the_removal_form_and_is_never_replaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(L5P, "STEPS", tmp_path)
        built = L5P.build([decided()], {TIKAL: site()}, live(site()), pinned={})
        wave = L5P.step_wave(1)
        assert wave.run_stamp == "2026-09-26_l5-links-001" and wave.out == tmp_path / "step-001"
        L5P.write_step(wave, built.links)
        apply_sql = (wave.out / "APPLY.sql").read_text(encoding="utf-8")
        assert (
            "DELETE FROM site_external_ids" in apply_sql
            and "invariant 4: the fixed point" in apply_sql
        )
        undo = (wave.out / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert "planned item(s) are carried by another curated site" not in undo
        assert L5P.load_step(wave) == built.links
        L5P.write_step(wave, built.links)  # the same plan again is a no-op
        with pytest.raises(MP.PlanError, match="holds another plan"):
            L5P.write_step(wave, built.links[:1])


class TestTheNameLane:
    def test_the_statements_refuse_a_key_that_is_not_the_name_s(self) -> None:
        records = [
            A.ChangeRecord(site_id=ZOQUE, site_name="Zoque", old_value=old, new_value=new, rule="l5-name",
                           condition="", reason="r", evidence=({"source": "s", "quote": "q"},), column=col)
            for col, old, new in (("name", "Zoque Culture Archaeological Zone", "Chiapa de Corzo"),
                                  ("name_normalized", "zoque culture archaeological zone", "chiapa de corzo"))
        ]  # fmt: skip
        for sql in (
            A.apply_statement(records, L.NAME_L5),
            A.rollback_statement(records, L.NAME_L5),
        ):
            assert "invariant 3, the lane's own" in sql
            assert "name_normalized IS DISTINCT FROM left(lower(unaccent(name)), 500)" in sql
            assert A.INVARIANT_SAYS in sql
        assert "invariant-lane" in {
            c[0] for c in A.probe_cases(records, L.NAME_L5, {"id": OTHER, "name": "x"})
        }

    def test_only_a_cell_lane_on_the_sites_may_carry_an_invariant(self) -> None:
        from dataclasses import replace

        with pytest.raises(ValueError, match="belongs to a cell lane"):
            replace(L.UK_PARTS, write_invariant=L.NAME_L5.write_invariant)


# ------------------------------------------------------------------------------ a link step
class FakeProduction:
    """Answers the reads of a step's commands from a dict of stored values and a journal."""

    def __init__(
        self, values: dict[tuple[str, str], list[str]], journal: dict[str, list[str]]
    ) -> None:
        self.values, self.journal, self.sent = values, journal, []

    def read(self, sql: str) -> str:
        if "FROM remediation_change_log" in sql:
            stamp = sql.split("run_stamp = '", 1)[1].split("'", 1)[0]
            keys = self.journal.get(stamp, [])
            if "count(*)" in sql:
                return json.dumps({"n": len(keys)}) + "\n"
            return "".join(json.dumps({"change_key": k}) + "\n" for k in keys)
        if "FROM site_external_ids" in sql:
            return "".join(
                json.dumps({"site_id": sid, "kind": kind, "value": v}) + "\n"
                for (sid, kind), vals in self.values.items() if kind != "source_url" for v in vals
            )  # fmt: skip
        raise AssertionError(sql)

    def send(self, sql: str) -> Any:
        self.sent.append(sql)
        import subprocess

        return subprocess.CompletedProcess([], 0, "BEGIN\nDO\nCOMMIT\n", "")


@pytest.fixture
def step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[QR.Change]:
    monkeypatch.setattr(L5P, "STEPS", tmp_path)
    built = L5P.build([decided()], {TIKAL: site()}, live(site()), pinned={})
    L5P.write_step(L5P.step_wave(1), built.links)
    return built.links


class TestALinkStep:
    def test_check_reads_the_old_values_and_refuses_a_deviation(
        self, step: list[QR.Change]
    ) -> None:
        prod = FakeProduction(
            {(TIKAL, "wikidata_qid"): ["Q100"], (TIKAL, "enwiki_title"): ["Mundo Perdido, Tikal"]},
            {},
        )
        assert LK.cmd_check(1, read=prod.read) == A.EXIT_OK
        prod.values[(TIKAL, "wikidata_qid")] = ["Q101"]
        assert LK.cmd_check(1, read=prod.read) == A.EXIT_REFUSED

    def test_an_edited_statement_is_never_sent(self, step: list[QR.Change]) -> None:
        path = L5P.step_wave(1).out / "APPLY.sql"
        path.write_text(path.read_text(encoding="utf-8").replace("Q200", "Q201"), encoding="utf-8")
        with pytest.raises(LK.StepError, match="edited or stale"):
            LK.delivered(1)

    def test_apply_verifies_what_landed(self, step: list[QR.Change]) -> None:
        stamp = L5P.step_wave(1).run_stamp
        prod = FakeProduction(
            {(TIKAL, "wikidata_qid"): ["Q100"], (TIKAL, "enwiki_title"): ["Mundo Perdido, Tikal"]},
            {},
        )

        def landed(sql: str) -> Any:
            prod.values = {(TIKAL, "wikidata_qid"): ["Q200"]}
            prod.journal[stamp] = [c.change_key for c in step]
            return FakeProduction.send(prod, sql)

        assert LK.cmd_apply(1, sender=landed, read=prod.read) == A.EXIT_OK
        assert prod.sent == [(L5P.step_wave(1).out / "APPLY.sql").read_text(encoding="utf-8")]
        assert LK.cmd_verify(1, read=prod.read) == A.EXIT_OK
        with pytest.raises(LK.StepError, match="never apply twice"):
            LK.cmd_apply(1, sender=landed, read=prod.read)

    def test_a_failed_apply_is_settled_from_the_journal(self, step: list[QR.Change]) -> None:
        import subprocess

        prod = FakeProduction(
            {(TIKAL, "wikidata_qid"): ["Q100"], (TIKAL, "enwiki_title"): ["Mundo Perdido, Tikal"]},
            {},
        )
        stopped = lambda sql: subprocess.CompletedProcess([], A.PSQL_SCRIPT_ERROR, "", "ERROR: x")  # noqa: E731
        assert LK.cmd_apply(1, sender=stopped, read=prod.read) == A.EXIT_NOT_COMMITTED

        def timeout(sql: str) -> Any:
            raise LK.OutcomeUnknown("timed out")

        assert LK.cmd_apply(1, sender=timeout, read=prod.read) == A.EXIT_UNKNOWN

    def test_the_probes_corrupt_one_thing_each(self, step: list[QR.Change]) -> None:
        live_state = {
            "foreign": OTHER,
            "shared": "Q555",
            "links": [("enwiki_title", "Mundo Perdido, Tikal"), ("wikidata_qid", "Q100")],
        }
        cases = dict(LK.probe_cases(step, live_state))
        assert sorted(cases) == ["guard1", "guard3", "guard5", "invariant4"]
        assert cases["guard1"][0].site_id == OTHER
        assert cases["guard3"][0].old_value == LK.NEVER_STORED
        assert cases["guard5"][0].new_value == "Q555"
        assert {(c.kind, c.new_value) for c in cases["invariant4"]} == {
            ("enwiki_title", None),
            ("wikidata_qid", None),
        }
        for guard, rows in cases.items():
            sql = QR.render_split(
                rows, reversal=False, rehearsal=True, wave=L5P.step_wave(1), removals=True
            )
            assert sql.rstrip().split("\n")[-4] == "ROLLBACK;" or "ROLLBACK;" in sql
            assert LK.SAYS[guard] in sql
        assert LK.refused_by(
            "guard3",
            "psql:<stdin>:40: ERROR:  source-url split: 1 external-id row(s) no longer hold the planned old value",
        )
        assert not LK.refused_by(
            "guard3", "ERROR:  source-url split: 1 site(s) are not curated sites"
        )


# ------------------------------------------------------------------------------ the web
class TestTheWeb:
    def test_the_user_agent_names_no_person(self) -> None:
        assert web.USER_AGENT.startswith("AncientMapRemediation/1.0 (research")
        assert "@" not in web.USER_AGENT
        with web.client() as client:
            assert client.headers["User-Agent"] == web.USER_AGENT

    def test_titles_are_resolved_with_the_refresh_s_query(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"query": {
                "redirects": [{"from": "Mundo Perdido", "to": "Mundo Perdido, Tikal"}],
                "pages": [{"title": "Mundo Perdido, Tikal", "pageprops": {"wikibase_item": "Q100"},
                           "coordinates": [{"lat": 17.22, "lon": -89.62}]}],
            }})  # fmt: skip

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            got = web.resolve_titles(["Mundo Perdido"], client)
        assert got["Mundo Perdido"] == {
            "canonical_title": "Mundo Perdido, Tikal", "qid": "Q100", "lat": 17.22, "lon": -89.62,
            "disambiguation": False, "redirected": True,
        }  # fmt: skip
        params = dict(seen[0].url.params)
        assert params["prop"] == "coordinates|pageprops" and params["redirects"] == "1"
        assert (
            params["ppprop"] == "wikibase_item|disambiguation"
            and params["titles"] == "Mundo Perdido"
        )
