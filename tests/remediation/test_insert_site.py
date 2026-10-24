"""D57's insert lane (`scripts/remediation/insert_site/`): candidates, research, plan, the writer.

Offline: the Wikimedia answers are dicts, the quoted pages come from an `httpx.MockTransport`, the
Wikipedia API from a census `Fetcher` over one, and production is a fake reader or a tagged-export
text. What is pinned: the candidate list resolves merges and refuses what it cannot resolve; a
research answer counts only in the fields lanes' format with every quote found; the plan writes the
curated column set with its provenance and refuses every site its rules name; the transaction carries
every guard, journals every write, and its undo retires - never deletes.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from identity.wiki import article_url  # noqa: E402
from insert_site import candidates as C  # noqa: E402
from insert_site import plan as P  # noqa: E402
from insert_site import research as RS  # noqa: E402
from insert_site import run as RUN  # noqa: E402
from insert_site import writer as W  # noqa: E402
from mechanical.field_prov import sha_of  # noqa: E402

COLOSSEUM = "Q10285"
TERRACOTTA = "Q47672"
WIKI = "https://en.wikipedia.org/wiki/Colosseum"
REGISTER = "https://www.example-heritage.it/colosseo"
PAGES = {
    WIKI: "<html><body><p>The Colosseum is an elliptical amphitheatre in the centre of the city "
    "of Rome, Italy. Construction began under the emperor Vespasian in 72 AD and was completed in "
    "80 AD.</p><p>41.8902°N 12.4922°E</p></body></html>",
    REGISTER: "<html><body><p>The Flavian Amphitheatre, known as the Colosseum, held up to 50,000 "
    "spectators.</p></body></html>",
}
VOCABULARY = {"Italy": 223, "China": 9, "USA": 26, "England": 1044, "Pakistan": 83}


# ------------------------------------------------------------------------------------ fixtures
def candidate(
    qid: str = COLOSSEUM,
    label: str = "Colosseum",
    title: str = "Colosseum",
    lat: float = 41.890277777778,
    lon: float = 12.492222222222,
    **extra: Any,
) -> dict[str, Any]:
    line = {
        "qid": qid,
        "origin": f"{C.INSCOPE_CSV} rank 8",
        "wp_title": title,
        "our_names": label,
        "csv_country": "Italy",
        "wp_views_jul_sep_2026": 280448,
        "note": "70-80 n. Chr.",
        "queue_2026_10_08": "new",
        "status": C.CANDIDATE,
        "reason": None,
        "label_en": label,
        "enwiki_title": title,
        "enwiki_url": article_url("en", title),
        "p625": {"lat": lat, "lon": lon, "precision": 0.0001},
        "parent_qid": None,
        "parent_why": None,
        "curated_ids": [],
        "name_twins": [],
        "proposals": [],
        "name_proposals": [],
        "parent": None,
        "read_at": "2026-10-24 08:22:07+00",
    }
    line.update(extra)
    return line


@pytest.fixture
def run(tmp_path: Path) -> Path:
    out = tmp_path / "d57-test"
    out.mkdir()
    C.write_jsonl(out / C.CANDIDATES_FILE, [candidate()])
    C.write_json(out / C.VOCABULARY_FILE, {"read_at": "x", "countries": VOCABULARY})
    return out


def block(decision: str, value: Any, quotes: list[tuple[str, str]], **extra: Any) -> dict:
    return {
        "decision": decision,
        "value": value,
        "quotes": [{"url": u, "quote": q} for u, q in quotes],
        "reasoning": "The source says so.",
        **extra,
    }


def full_answer(**override: Any) -> dict[str, Any]:
    fields = {
        "name": block("keep", "Colosseum", [(WIKI, "The Colosseum is an elliptical amphitheatre")]),
        "coordinates": block("keep", "41.8902, 12.4922", [(WIKI, "41.8902°N 12.4922°E")]),
        "country": block("replace", "Italy", [(WIKI, "in the centre of the city of Rome, Italy")]),
        "site_type": block("replace", "Amphitheatre", [(WIKI, "an elliptical amphitheatre")]),
        "period_start": block(
            "replace", "72", [(WIKI, "Construction began under the emperor Vespasian in 72 AD")]
        ),
        "source_url": block("keep", WIKI, [(WIKI, "The Colosseum is an elliptical amphitheatre")]),
    }
    fields.update(override)
    return {
        "fields": fields,
        RS.SOURCES: [
            {"url": WIKI, "quote": "Construction began under the emperor Vespasian in 72 AD"},
            {"url": REGISTER, "quote": "held up to 50,000 spectators"},
        ],
    }


def pages_client() -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in PAGES:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                content=PAGES[url].encode("utf-8"),
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)


def api(tmp_path: Path) -> Fetcher:
    def handle(request: httpx.Request) -> httpx.Response:
        title = dict(request.url.params)["titles"]
        page = {"title": title, "pageprops": {"wikibase_item": COLOSSEUM}}
        return httpx.Response(200, json={"query": {"pages": [page]}})

    return Fetcher(tmp_path / "api", workers=1, transport=httpx.MockTransport(handle))


def record(handoff: Path, batch: str, label: str, text: str, *, role: bool = True) -> None:
    OH.write_answer(
        handoff,
        batch_id=batch,
        stage=RS.STAGE,
        label=label,
        text=text,
        answered_by=RO.answered_by(RS.ROLE, "agent1") if role else "agent1",
        model=OH.SONNET_MODEL,
    )


def line() -> dict[str, Any]:
    return RS.question_line(candidate())


# ------------------------------------------------------------------------------------ candidates
def _write_csvs(directory: Path, rows: int, *, extra: list[dict[str, str]] | None = None) -> None:
    fields = ["rank", "wp_title", "qid", "our_names", "country", "wp_views_jul_sep_2026"]
    fields += ["manual_verdict", "manual_note"]
    with (directory / C.INSCOPE_CSV).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        pins = [p.qid for p in C.EXCLUSIONS] + [p.qid for p in C.PARENTS]
        for n in range(rows):
            qid = pins[n] if n < len(pins) else f"Q{900000 + n}"
            writer.writerow(
                {
                    "rank": n,
                    "wp_title": f"Site {n}",
                    "qid": qid,
                    "our_names": f"Site {n}",
                    "country": "Italy",
                    "wp_views_jul_sep_2026": "10",
                    "manual_verdict": C.IN_VERDICT,
                    "manual_note": "",
                }
            )
        for row in extra or []:
            writer.writerow(row)
    with (directory / C.PROPOSALS_CSV).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["qid", "status"])
        writer.writeheader()
        writer.writerow({"qid": "Q900010", "status": "new"})


class TestTheCandidateList:
    def test_the_in_rows_and_the_additions_are_the_candidates(self, tmp_path: Path) -> None:
        _write_csvs(tmp_path, C.EXPECTED_IN_ROWS)
        seeds = C.seed_rows(tmp_path)
        assert len(seeds) == C.EXPECTED_IN_ROWS + len(C.ADDITIONS)
        assert seeds[-1]["qid"] == "Q732463"
        assert next(s for s in seeds if s["qid"] == "Q900010")["queue_2026_10_08"] == "new"

    def test_a_csv_with_another_count_is_not_the_list(self, tmp_path: Path) -> None:
        _write_csvs(tmp_path, C.EXPECTED_IN_ROWS - 1)
        with pytest.raises(C.CandidateError, match="'in' rows"):
            C.seed_rows(tmp_path)

    def test_an_item_twice_is_refused(self, tmp_path: Path) -> None:
        _write_csvs(tmp_path, C.EXPECTED_IN_ROWS - 1, extra=[])
        rows = list(csv.DictReader((tmp_path / C.INSCOPE_CSV).open(encoding="utf-8")))
        rows.append(dict(rows[-1]))
        with (tmp_path / C.INSCOPE_CSV).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with pytest.raises(C.CandidateError, match="twice"):
            C.seed_rows(tmp_path)

    def test_a_pin_that_names_no_candidate_is_refused(self, tmp_path: Path) -> None:
        _write_csvs(tmp_path, C.EXPECTED_IN_ROWS)
        rows = list(csv.DictReader((tmp_path / C.INSCOPE_CSV).open(encoding="utf-8")))
        rows[0]["qid"] = "Q1"  # the first pinned exclusion is gone
        with (tmp_path / C.INSCOPE_CSV).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with pytest.raises(C.CandidateError, match="pin names"):
            C.seed_rows(tmp_path)


def entity(qid: str, title: str | None, *, point: bool = True, served_as: str | None = None):
    claims = {}
    if point:
        claims["P625"] = [
            {
                "rank": "normal",
                "mainsnak": {
                    "datavalue": {
                        "value": {
                            "latitude": 41.89,
                            "longitude": 12.49,
                            "precision": 0.0001,
                            "globe": "http://www.wikidata.org/entity/Q2",
                        }
                    }
                },
            }
        ]
    out = {
        "id": served_as or qid,
        "labels": {"en": {"value": "Label " + qid}},
        "claims": claims,
        "sitelinks": {"enwiki": {"title": title}} if title else {},
    }
    if served_as:
        out["redirects"] = {"from": qid, "to": served_as}
    return out


def article(title: str, item: str, **flags: bool) -> dict[str, Any]:
    return {
        "resolved_title": title,
        "missing": flags.get("missing", False),
        "invalid": False,
        "redirected": flags.get("redirected", False),
        "disambiguation": flags.get("disambiguation", False),
        "wikibase_item": item,
    }


def seed(qid: str) -> dict[str, Any]:
    return {"qid": qid, "origin": "test", "note": None}


class TestTheResolution:
    def test_a_merged_item_takes_the_id_it_was_merged_into(self) -> None:
        lines = C.resolve(
            [seed("Q10332176")],
            {"Q10332176": entity("Q10332176", "Sanchi Stupa", served_as="Q181123")},
            {"Sanchi Stupa": article("Sanchi Stupa", "Q181123")},
        )
        assert lines[0]["qid"] == "Q181123" and lines[0]["qid_asked"] == "Q10332176"
        assert lines[0]["status"] == C.CANDIDATE

    @pytest.mark.parametrize(
        ("ent", "page", "reason"),
        [
            (entity("Q5", None), None, "no-enwiki-article"),
            (entity("Q5", "T", point=False), article("T", "Q5"), "no-p625"),
            (entity("Q5", "T"), article("T", "Q5", redirected=True), "enwiki-redirect"),
            (entity("Q5", "T"), article("T", "Q5", disambiguation=True), "enwiki-disambiguation"),
            (entity("Q5", "T"), article("T", "Q5", missing=True), "enwiki-missing"),
            (entity("Q5", "T"), article("T", "Q6"), "enwiki-other-item"),
            ({"id": "Q5", "missing": ""}, None, "qid-missing"),
        ],
    )
    def test_what_does_not_resolve_says_why(self, ent, page, reason) -> None:
        articles = {"T": page} if page else {}
        [line] = C.resolve([seed("Q5")], {"Q5": ent}, articles)
        assert line["status"] == C.UNRESOLVED and line["reason"].startswith(reason)

    def test_a_pinned_exclusion_is_resolved_and_excluded(self) -> None:
        qid = C.EXCLUSIONS[0].qid
        [line] = C.resolve([seed(qid)], {qid: entity(qid, "T")}, {"T": article("T", qid)})
        assert line["status"] == C.EXCLUDED and "D58" in line["reason"]

    def test_a_curated_item_or_article_makes_the_candidate_curated_already(self) -> None:
        lines = [candidate()]
        rows = {kind: [] for kind in C.KINDS}
        rows["ids"] = [{"qid": COLOSSEUM, "kind": "wikidata_qid", "value": COLOSSEUM,
                        "site_id": "s1", "name": "Colosseum", "scope_status": "retired"}]  # fmt: skip
        [out] = C.apply_read(lines, rows)
        assert out["status"] == C.ALREADY and "s1" in out["reason"]

    def test_a_parent_pin_must_name_one_curated_site(self) -> None:
        lines = [candidate(qid=TERRACOTTA, parent_qid="Q910180")]
        rows = {kind: [] for kind in C.KINDS}
        with pytest.raises(C.CandidateError, match="pinned parent"):
            C.apply_read(lines, rows)
        rows["parents"] = [{"parent_qid": "Q910180", "site_id": "p1", "name": "Mausoleum"}]
        assert C.apply_read(lines, rows)[0]["parent"]["site_id"] == "p1"

    def test_the_read_is_read_only(self) -> None:
        script = C.read_script([candidate()])
        assert script.startswith("\\set QUIET on\nSET default_transaction_read_only = on;\n")
        assert "REPEATABLE READ READ ONLY" in script
        for word in ("INSERT", "UPDATE", "DELETE"):
            assert word not in script

    def test_the_report_names_every_candidate(self) -> None:
        text = C.report([candidate(), candidate(qid="Q2", status=C.EXCLUDED, reason="D58")])
        assert "2 candidates: 1 candidate, 1 excluded" in text and "| Q2 |" in text

    def test_the_report_flags_a_radar_backed_proposal(self) -> None:
        backed = {"proposal_id": "p1", "name": "Chaco Canyon", "status": "out_of_scope",
                  "contribution_id": "ec1e99a7"}  # fmt: skip
        plain = {**backed, "proposal_id": "p2", "name": "Chaco", "contribution_id": None}
        text = C.report([candidate(proposals=[backed, plain])])
        assert "2 open proposal(s)" in text and "1 of them mirror a radar contribution" in text
        assert "Chaco Canyon (out_of_scope, radar contribution ec1e99a7)" in text
        assert "Chaco (out_of_scope)" in text


# ------------------------------------------------------------------------------------ research
class TestTheQuestion:
    def test_the_prompt_shows_the_seeds_and_the_fields_asked(self) -> None:
        prompt = RS.render_prompt(candidate(), list(RS.ASKABLE), VOCABULARY)
        assert 'Stored value (the seed): "Colosseum"' in prompt
        assert "41.890277777778, 12.492222222222" in prompt and WIKI in prompt
        assert "### description_sources" in prompt and '"description_sources": [...]' in prompt
        assert RS.render_prompt(candidate(), list(RS.ASKABLE), VOCABULARY) == prompt

    def test_a_reask_asks_only_its_fields(self) -> None:
        prompt = RS.render_prompt(candidate(), ["country"], VOCABULARY, {"country": "no quote"})
        assert "### country" in prompt and "### name" not in prompt
        assert "did not count: no quote" in prompt and "description_sources" not in prompt

    def test_the_country_list_offers_no_flagged_spelling(self) -> None:
        prompt = RS.render_prompt(candidate(), ["country"], VOCABULARY)
        assert "Italy (223)" in prompt and "USA (" not in prompt

    def test_the_prompt_says_what_unresolved_does_here(self) -> None:
        prompt = RS.render_prompt(candidate(), ["coordinates", "period_start"], VOCABULARY)
        assert "A site without a sourced point is not added in this lane" in prompt
        assert 'the new site is added as "Undated"' in prompt
        assert "The stored point stays" not in prompt


class TestTheAnswer:
    def test_a_full_answer_passes_every_page_free_check(self) -> None:
        checked = RS.check_shape(json.dumps(full_answer()), RS.ASKABLE, line())
        problems = {f: v for f, v in checked.items() if isinstance(v, str)}
        assert problems == {}
        assert checked["period_start"].value == "72" and len(checked[RS.SOURCES]) == 2

    def test_a_name_with_a_comma_qualifier_is_refused(self) -> None:
        bad = block("replace", "Colosseum, Rome", [(WIKI, "Colosseum, Rome")])
        checked = RS.check_shape(json.dumps(full_answer(name=bad)), RS.ASKABLE, line())
        assert "comma_qualifier" in checked["name"]

    def test_a_name_no_quote_holds_is_refused(self) -> None:
        bad = block("replace", "Flavian Amphitheatre", [(WIKI, "The Colosseum is")])
        checked = RS.check_shape(json.dumps(full_answer(name=bad)), RS.ASKABLE, line())
        assert "no quote holds" in checked["name"]

    def test_a_name_keep_must_be_the_seed(self) -> None:
        bad = block("keep", "Colosseo", [(WIKI, "Colosseo")])
        checked = RS.check_shape(json.dumps(full_answer(name=bad)), RS.ASKABLE, line())
        assert "keep, but" in checked["name"]

    @pytest.mark.parametrize(
        ("value", "quote", "why"),
        [
            ("USA", "a site in the USA", "census accepts"),
            ("United Kingdom", "in the United Kingdom", "by its part"),
            ("Italy", "in the centre of Rome", "no quote names"),
        ],
    )
    def test_a_country_the_lane_cannot_take_is_refused(self, value, quote, why) -> None:
        bad = block("replace", value, [(WIKI, quote)])
        checked = RS.check_shape(json.dumps(full_answer(country=bad)), RS.ASKABLE, line())
        assert why in checked["country"]

    def test_a_country_has_no_keep(self) -> None:
        bad = block("keep", "Italy", [(WIKI, "Rome, Italy")])
        checked = RS.check_shape(json.dumps(full_answer(country=bad)), RS.ASKABLE, line())
        assert "no stored country" in checked["country"]

    def test_the_shared_fields_keep_the_fields_lanes_checks(self) -> None:
        far = block("keep", "41.95, 12.49", [(WIKI, "41.95°N 12.49°E")])
        checked = RS.check_shape(json.dumps(full_answer(coordinates=far)), RS.ASKABLE, line())
        assert "km from the stored point" in checked["coordinates"]

    def test_the_description_sources_are_bounded_and_never_our_own_site(self) -> None:
        answer = full_answer()
        answer[RS.SOURCES] = answer[RS.SOURCES][:1]
        assert "not 2 to 8" in RS.check_shape(json.dumps(answer), RS.ASKABLE, line())[RS.SOURCES]
        answer[RS.SOURCES] = [
            {"url": "https://ancientnerds.com/sites/italy/colosseum", "quote": "an amphitheatre"},
            {"url": WIKI, "quote": "an elliptical amphitheatre"},
        ]
        assert "no source" in RS.check_shape(json.dumps(answer), RS.ASKABLE, line())[RS.SOURCES]

    def test_unresolved_carries_nothing(self) -> None:
        checked = RS.check_shape(
            json.dumps(full_answer(name=block("unresolved", None, []))), RS.ASKABLE, line()
        )
        assert checked["name"].decision == "unresolved"

    def test_an_answer_with_other_fields_is_malformed(self) -> None:
        with pytest.raises(RS.AnswerError, match="are not"):
            RS.check_shape(json.dumps(full_answer()), ["name"], line())
        fields_only = {"fields": full_answer()["fields"]}
        with pytest.raises(RS.AnswerError, match="not the asked"):
            RS.check_shape(json.dumps(fields_only), ["name"], line())


class TestTheRounds:
    def _export(self, run: Path, tmp_path: Path) -> tuple[Path, str]:
        handoff = tmp_path / "h-r0"
        RS.export(run, handoff)
        batch = next(iter(RS.read_rounds(run)[0]["batches"]))
        return handoff, batch

    def test_round_zero_asks_every_field_of_every_candidate(self, run: Path, tmp_path) -> None:
        handoff, batch = self._export(run, tmp_path)
        [line_] = OH.manifest(handoff)
        assert line_["label"] == COLOSSEUM and line_["field"] == "+".join(RS.ASKABLE)
        with pytest.raises(RS.ResearchError, match="already"):
            RS.export(run, tmp_path / "h-r0b")
        brief = RS.brief(run, handoff, batch)
        assert "--role field_researcher" in brief and "--model claude-sonnet-5-5" in brief

    def test_check_answer_reports_per_field(self, run: Path, tmp_path: Path) -> None:
        handoff, batch = self._export(run, tmp_path)
        ok = RS.check_answer(run, handoff, batch, COLOSSEUM, json.dumps(full_answer()))
        assert ok == {"ok": True, "problems": {}}
        bad = full_answer(country=block("replace", "USA", [(WIKI, "USA")]))
        result = RS.check_answer(run, handoff, batch, COLOSSEUM, json.dumps(bad))
        assert not result["ok"] and set(result["problems"]) == {"country"}

    def test_a_counted_answer_is_a_decision(self, run: Path, tmp_path: Path) -> None:
        handoff, batch = self._export(run, tmp_path)
        record(handoff, batch, COLOSSEUM, json.dumps(full_answer()))
        result = RS.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        assert result["counted"] == len(RS.ASKABLE) and result["waiting_questions"] == 0
        decisions = RS.read_decisions(run)[COLOSSEUM]
        assert {d["status"] for d in decisions.values()} == {RS.COUNTED}
        assert decisions["country"]["value"] == "Italy"
        assert RS.waiting(run) == {}

    def test_a_quote_the_page_does_not_hold_is_asked_again(self, run: Path, tmp_path) -> None:
        handoff, batch = self._export(run, tmp_path)
        bad = full_answer(site_type=block("replace", "Amphitheatre", [(WIKI, "an amphitheatre X")]))
        record(handoff, batch, COLOSSEUM, json.dumps(bad))
        RS.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        assert set(RS.waiting(run)[COLOSSEUM]) == {"site_type"}
        RS.export_reask(run, tmp_path / "h-r1")
        r1 = RS.read_rounds(run)[1]
        assert r1["asked"] == {COLOSSEUM: ["site_type"]} and r1["notes"][COLOSSEUM]["site_type"]

    def test_after_the_last_reask_a_field_is_exhausted(self, run: Path, tmp_path: Path) -> None:
        handoff, batch = self._export(run, tmp_path)
        bad_type = block("replace", "Amphitheatre", [(WIKI, "an amphitheatre X")])
        record(handoff, batch, COLOSSEUM, json.dumps(full_answer(site_type=bad_type)))
        RS.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        for number in range(1, RS.MAX_ROUND + 1):
            target = tmp_path / f"h-r{number}"
            RS.export_reask(run, target)
            batch_n = next(iter(RS.read_rounds(run)[number]["batches"]))
            text = json.dumps({"fields": {"site_type": bad_type}})
            record(target, batch_n, COLOSSEUM, text)
            RS.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)
        decision = RS.read_decisions(run)[COLOSSEUM]["site_type"]
        assert decision["status"] == RS.EXHAUSTED and RS.waiting(run) == {}
        with pytest.raises(RS.ResearchError, match="last re-ask"):
            RS.export_reask(run, tmp_path / "h-r9")

    def test_an_answer_without_the_role_is_refused(self, run: Path, tmp_path: Path) -> None:
        handoff, batch = self._export(run, tmp_path)
        record(handoff, batch, COLOSSEUM, json.dumps(full_answer()), role=False)
        with pytest.raises(RS.ResearchError, match="field_researcher"):
            RS.import_rounds(run, client=pages_client(), net=api(tmp_path), pace=0)


# ------------------------------------------------------------------------------------ the plan
SITE_ID = "a1b2c3d4-0000-4000-8000-000000000001"
PARENT_ID = "07ea80ce-863f-43b9-8f7e-d155a0182f4f"
#: Chaco Canyon's radar contribution (`enriched`, no site, read 2026-10-24)
CONTRIBUTION = "ec1e99a7-f2dd-48ad-bbd4-cb4926ce46a5"


def decided(**override: Any) -> dict[str, dict[str, Any]]:
    """A candidate's DECISIONS, as `research.decide` writes them."""

    def d(field: str, decision: str, value: Any, quotes=None, status=RS.COUNTED, **extra):
        return {
            "qid": COLOSSEUM,
            "field": field,
            "status": status,
            "decision": decision if status == RS.COUNTED else None,
            "value": value if status == RS.COUNTED else None,
            "period_name": None,
            "quotes": quotes if quotes is not None else [[WIKI, "a quote"]],
            "reasoning": "r",
            "reason": None if status == RS.COUNTED else "quote not found",
            "round": 0,
            "batch_id": "ins-r0-b001",
            "answered_by": "field_researcher:agent1",
            "model": OH.SONNET_MODEL,
            "answered_at": "2026-10-24T10:00:00+00:00",
            "value_page": None,
            **extra,
        }

    out = {
        "name": d("name", "keep", "Colosseum"),
        "coordinates": d("coordinates", "keep", "41.8902, 12.4922"),
        "country": d("country", "replace", "Italy"),
        "site_type": d("site_type", "replace", "Amphitheatre"),
        "period_start": d("period_start", "replace", "72"),
        "source_url": d("source_url", "keep", WIKI),
        RS.SOURCES: d(RS.SOURCES, "sources", None, [[WIKI, "s1"], [REGISTER, "s2"]]),
    }
    for field, value in override.items():
        out[field] = d(*value) if isinstance(value, tuple) else value
    return out


def proposal(**extra: Any) -> dict[str, Any]:
    row = {
        "qid": COLOSSEUM,
        "proposal_id": "d2ff8c14-1aff-44de-af63-7fe3574233c3",
        "name": "Colosseum amphitheatre",
        "aliases": ["Flavian Amphitheatre"],
        "status": "new",
        "promoted_site_id": None,
        "contribution_id": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_notes": None,
        "updated_at": "2026-09-15 10:00:00+00",
        "contribution_status": None,
        "contribution_promoted": None,
    }
    row.update(extra)
    return row


def radar_backed(**extra: Any) -> dict[str, Any]:
    """A proposal that mirrors a radar contribution, as 5 of D57's 11 do."""
    return proposal(contribution_id=CONTRIBUTION, contribution_status="enriched", **extra)


def read_rows(**override: Any) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {kind: [] for kind in P.KINDS}
    rows["proposals"] = [proposal()]
    rows["keys"] = [
        {"text": t, "key": t.lower()}
        for t in ("Colosseum", "Colosseum amphitheatre", "Flavian Amphitheatre")
    ]
    rows["probe"] = [
        {"kind": "shown", "site_id": "11111111-1111-4111-8111-111111111111", "name": "Pompeii",
         "name_normalized": "pompeii", "country": "Italy", "lat": 40.75, "lon": 14.48,
         "source_record_id": "7a43d34c", "qid": "Q43332"},
        {"kind": "retired", "site_id": "22222222-2222-4222-8222-222222222222", "name": "Gone",
         "name_normalized": "gone", "country": "Italy", "lat": 1.0, "lon": 1.0,
         "source_record_id": "x", "qid": None},
    ]  # fmt: skip
    rows.update(override)
    return rows


def agrees(country: str, lat: float, lon: float) -> dict[str, Any]:
    return {"agrees": country in ("Italy", "China"), "polygon": ["Italy"], "note": None}


def site(**extra: Any) -> dict[str, Any]:
    out = {
        "qid": COLOSSEUM,
        "title": "Colosseum",
        "name": "Colosseum",
        "lat": 41.8902,
        "lon": 12.4922,
        "site_id": SITE_ID,
        "record": f"d57-{COLOSSEUM}",
    }
    out.update(extra)
    return out


def build(decisions=None, rows=None, line_=None, check=agrees, sites=None) -> P.Step:
    step = P.Step(run="d57-test", number=1, inserts=[])
    step.probe = {str(p["kind"]): p for p in (rows or read_rows())["probe"]}
    by_qid = {COLOSSEUM: line_ or candidate()}
    P.build_inserts(
        step,
        sites or [site()],
        by_qid,
        {COLOSSEUM: decisions or decided()},
        rows or read_rows(),
        check,
    )
    return step


class TestThePlannedRow:
    def test_the_row_carries_the_curated_column_set(self) -> None:
        [row] = build().inserts
        columns = row.site_columns()
        assert columns["source_id"] == "ancient_nerds" and columns["scope_status"] == "in_scope"
        assert columns["period_name"] == "1 - 500 AD" and columns["period_start"] == "72"
        assert columns["geom"] == "SRID=4326;POINT(12.4922 41.8902)"
        assert columns["edited_by"] == P.EDITED_BY and len(P.EDITED_BY) <= 20
        assert columns["source_record_id"] == "d57-Q10285" and "D57" in row.scope_reason

    def test_the_names_are_the_label_and_the_proposals_names(self) -> None:
        [row] = build().inserts
        assert [(n["name"], n["name_type"]) for n in row.names] == [
            ("Colosseum", "label"),
            ("Colosseum amphitheatre", "alias"),
            ("Flavian Amphitheatre", "alias"),
        ]
        assert row.external_ids == [
            {"kind": "wikidata_qid", "value": COLOSSEUM},
            {"kind": "enwiki_title", "value": "Colosseum"},
        ]

    def test_a_proposal_name_with_the_labels_key_adds_no_alias(self) -> None:
        rows = read_rows(proposals=[proposal(name="COLOSSEUM", aliases=[])])
        rows["keys"].append({"text": "COLOSSEUM", "key": "colosseum"})
        [row] = build(rows=rows).inserts
        assert [n["name"] for n in row.names] == ["Colosseum"]

    def test_the_proposal_carries_the_values_it_holds(self) -> None:
        [row] = build().inserts
        [p] = row.proposals
        assert p["old"]["status"] == "new" and p["old"]["updated_at"] == "2026-09-15 10:00:00+00"
        assert set(p["old"]) == set(P.PROPOSAL_COLUMNS)

    def test_the_markers_hash_the_values_they_describe(self) -> None:
        [row] = build().inserts
        assert row.raw_data["_coord_provenance"]["sha"] == sha_of("41.8902|12.4922")
        assert row.raw_data["_period_provenance"] == {
            "kind": "quote",
            "run": "d57-test_insert-site-s001",
            "journal_id": None,
            "sha": sha_of("72|1 - 500 AD"),
        }
        provenance = row.raw_data[P.RAW_KEY]
        assert provenance["decision"] == "D57" and provenance["qid"] == COLOSSEUM
        assert provenance["description_sources"] == [[WIKI, "s1"], [REGISTER, "s2"]]

    def test_a_start_nobody_sourced_is_undated(self) -> None:
        step = build(decided(period_start=("period_start", "unresolved", None, [])))
        [row] = step.inserts
        assert row.period_start is None and row.period_name == "Undated"
        assert row.raw_data["_period_provenance"]["kind"] == "undated"
        assert row.raw_data["_period_provenance"]["sha"] == sha_of("NULL|Undated")
        assert "period_start" in step.notes[COLOSSEUM][0]

    def test_a_type_nobody_sourced_is_written_empty(self) -> None:
        exhausted = {**decided()["site_type"], "status": RS.EXHAUSTED, "decision": None}
        [row] = build(decided(site_type=exhausted)).inserts
        assert row.site_type is None and "site_type" not in row.site_columns()

    def test_the_journal_rows_are_counted_per_write(self) -> None:
        [row] = build().inserts
        assert row.journal_rows == len(row.site_columns()) + 2 + 4 * 3 + 2 + 6

    def test_pg_float_prints_as_postgres_does(self) -> None:
        assert P.pg_float(12.0) == "12" and P.pg_float(41.8902) == "41.8902"
        assert P.pg_float(-0.5) == "-0.5"


class TestTheRefusals:
    def _refused(self, step: P.Step) -> str:
        assert not step.inserts
        [refusal] = step.refusals
        return refusal.reason

    def test_a_curated_item_is_refused(self) -> None:
        rows = read_rows(ids=[{"qid": COLOSSEUM, "kind": "wikidata_qid", "value": COLOSSEUM,
                               "site_id": "s", "scope_status": None}])  # fmt: skip
        assert self._refused(build(rows=rows)) == "already-curated"

    def test_a_point_outside_its_country_is_refused(self) -> None:
        def disagrees(country, lat, lon):
            return {"agrees": False, "polygon": ["Vatican City"], "note": None}

        assert self._refused(build(check=disagrees)) == "country-disagrees"

    def test_a_name_twin_nearby_is_refused_and_a_far_one_is_not(self) -> None:
        twin = {"qid": COLOSSEUM, "site_id": "t", "name": "Colosseum", "country": "Italy"}
        near = read_rows(twins=[{**twin, "metres": 1200}])
        assert self._refused(build(rows=near)) == "name-twin"
        far = read_rows(twins=[{**twin, "metres": P.NAME_TWIN_METRES + 1}])
        assert len(build(rows=far).inserts) == 1

    @pytest.mark.parametrize(
        ("start", "country", "lat", "lon", "reason"),
        [
            ("1600", "Italy", 41.89, 12.49, "scope-after-1500"),
            ("600", "Italy", 41.89, 12.49, "scope-d58-europe"),
            ("600", "Pakistan", 27.3, 68.1, None),
            ("1200", "USA", 37.2, -108.4, None),
            ("400", "Italy", 41.89, 12.49, None),
        ],
    )
    def test_the_scope_rule_d58(self, start, country, lat, lon, reason) -> None:
        assert P.scope_refusal(int(start), country, lat, lon) == reason

    def test_a_dated_site_out_of_scope_is_refused(self) -> None:
        step = build(decided(period_start=("period_start", "replace", "1600")))
        assert self._refused(step) == "scope-after-1500"

    @pytest.mark.parametrize(
        ("parent", "reason"),
        [
            (None, "parent-missing"),
            ({"scope_status": "retired"}, "parent-retired"),
            ({"parent_site_id": "x"}, "parent-depth"),
            ({"lat": 34.0, "lon": 109.0}, "parent-far"),
            ({"country": "Mongolia"}, "parent-far"),
        ],
    )
    def test_a_pinned_parent_must_hold_the_d25_invariants(self, parent, reason) -> None:
        row = {"parent_qid": "Q910180", "site_id": PARENT_ID, "name": "Qin Shi Huang’s Mausoleum",
               "country": "China", "lat": 34.3819, "lon": 109.2539, "scope_status": None,
               "parent_site_id": None}  # fmt: skip
        rows = read_rows(parents=[] if parent is None else [{**row, **parent}])
        line_ = candidate(parent_qid="Q910180")
        dec = decided(country=("country", "replace", "China"))
        step = build(dec, rows, line_, sites=[site(lat=34.385, lon=109.273)])
        assert self._refused(step) == reason

    def test_a_pinned_parent_within_reach_is_written(self) -> None:
        row = {"parent_qid": "Q910180", "site_id": PARENT_ID, "name": "Mausoleum",
               "country": "China", "lat": 34.3819, "lon": 109.2539, "scope_status": None,
               "parent_site_id": None}  # fmt: skip
        dec = decided(country=("country", "replace", "China"))
        step = build(
            dec,
            read_rows(parents=[row]),
            candidate(parent_qid="Q910180"),
            sites=[site(lat=34.385, lon=109.273)],
        )
        assert step.inserts[0].parent_site_id == PARENT_ID

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"status": "approved", "promoted_site_id": "x"}, "proposal-promoted"),
            (
                {"contribution_status": "promoted", "contribution_promoted": "s"},
                "contribution-promoted",
            ),
            ({"contribution_promoted": "s"}, "contribution-promoted"),
            ({"contribution_status": "promoted"}, "contribution-promoted"),
        ],
    )
    def test_a_proposal_the_lane_cannot_close_refuses_the_site(self, change, reason) -> None:
        if reason == "contribution-promoted":
            change = {"contribution_id": CONTRIBUTION, **change}
        assert self._refused(build(rows=read_rows(proposals=[proposal(**change)]))) == reason

    def test_a_radar_backed_proposal_is_closed_and_its_contribution_promoted(self) -> None:
        """The radar row is promoted with the proposal (`_mirror_contribution`), never a refusal:
        Chaco Canyon, Nineveh, KV62, Sanxingdui and Nan Madol all carry one."""
        [row] = build(rows=read_rows(proposals=[radar_backed()])).inserts
        [p] = row.proposals
        assert p["contribution_id"] == CONTRIBUTION
        assert row.contributions == [
            {
                "contribution_id": CONTRIBUTION,
                "old": {"enrichment_status": "enriched", "promoted_site_id": None},
            }
        ]
        assert row.journal_rows == len(row.site_columns()) + 2 + 4 * 3 + 2 + 6 + 2

    def test_a_proposal_without_a_contribution_promotes_none(self) -> None:
        [row] = build().inserts
        assert row.proposals[0]["contribution"] is None and row.contributions == []

    def test_a_curated_alias_twin_nearby_is_refused_and_named(self) -> None:
        twin = {"qid": COLOSSEUM, "site_id": "t", "name": "Flavian Amphitheatre",
                "as_name": "Colosseum", "country": "Italy", "metres": 40}  # fmt: skip
        step = build(rows=read_rows(twins=[twin]))
        assert self._refused(step) == "name-twin"
        assert "as 'Colosseum'" in step.refusals[0].detail

    def test_the_twin_read_and_guard_4_read_the_curated_names_too(self) -> None:
        [(_, sql)] = [part for part in P.read_sql([site()], []) if part[0] == "twins"]
        key = "left(lower(unaccent(k.name)), 500)"
        assert (
            f"(u.name_normalized = {key} OR EXISTS (SELECT 1 FROM unified_site_names tn "
            f"WHERE tn.site_id = u.id AND tn.name_normalized = {key}))"
        ) in sql
        assert (
            "(u.name_normalized = p.name_key OR EXISTS (SELECT 1 FROM unified_site_names tn "
            "WHERE tn.site_id = u.id AND tn.name_normalized = p.name_key))"
        ) in W.apply_guards()[4]

    def test_the_proposal_read_carries_the_radar_row(self) -> None:
        [(_, sql)] = [part for part in P.read_sql([site()], []) if part[0] == "proposals"]
        assert "LEFT JOIN user_contributions c ON c.id = p.contribution_id" in sql
        assert "c.enrichment_status AS contribution_status" in sql


def tagged(rows: dict[str, list[dict[str, Any]]]) -> str:
    lines = [json.dumps({"kind": k, "row": r}) for k, rs in rows.items() for r in rs]
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-10-24 12:00+00"}}))
    return "\n".join(lines) + "\n"


def fake_export(rows: dict[str, list[dict[str, Any]]]):
    def export(script: str, path: Path) -> Path:
        assert script.startswith("\\set QUIET on\nSET default_transaction_read_only = on;\n")
        if "AS key FROM" in script:
            path.write_text(tagged({"keys": rows["keys"]}), encoding="utf-8")
        else:
            path.write_text(
                tagged({k: v for k, v in rows.items() if k != "keys"}), encoding="utf-8"
            )
        return path

    return export


def write_decisions(run: Path, decisions: dict[str, dict[str, Any]]) -> None:
    C.write_jsonl(run / RS.DECISIONS_FILE, list(decisions.values()))
    C.write_json(run / RS.REASK_FILE, {"after_round": 0, "fields": {}})


class TestThePlanStep:
    def test_a_step_is_planned_from_the_decisions_and_one_read(self, run: Path) -> None:
        write_decisions(run, decided())
        step = P.plan_step(
            run, 1, export=fake_export(read_rows()), country_check=agrees, new_id=lambda: SITE_ID
        )
        assert [i.site_id for i in step.inserts] == [SITE_ID]
        target = P.step_dir(run, 1)
        P.write_step(step, target)
        assert P.load_step(target).digest == step.digest
        assert "Colosseum" in (target / P.PLAN_MD).read_text(encoding="utf-8")

    def test_a_proposal_naming_only_the_name_is_listed_never_closed(self, run: Path) -> None:
        write_decisions(run, decided())
        named = {"qid": COLOSSEUM, "proposal_id": "np-1", "name": "Colosseum", "status": "new",
                 "evidence_count": 2}  # fmt: skip
        rows = read_rows(name_proposals=[named])
        step = P.plan_step(run, 1, export=fake_export(rows), country_check=agrees)
        assert step.name_proposals == {COLOSSEUM: [named]}
        assert [p["proposal_id"] for p in step.inserts[0].proposals] == [proposal()["proposal_id"]]
        assert "np-1" in P.render_md(step) and "not closed" in P.render_md(step)

    def test_the_plan_waits_for_the_reasks(self, run: Path) -> None:
        write_decisions(run, decided())
        C.write_json(run / RS.REASK_FILE, {"after_round": 0, "fields": {COLOSSEUM: {"name": "x"}}})
        with pytest.raises(P.InsertPlanError, match="re-ask"):
            P.plan_step(run, 1, export=fake_export(read_rows()), country_check=agrees)

    def test_a_site_without_its_required_fields_is_refused_before_the_read(self, run) -> None:
        exhausted = {**decided()["coordinates"], "status": RS.EXHAUSTED, "decision": None}
        write_decisions(run, decided(coordinates=exhausted))
        with pytest.raises(P.InsertPlanError, match="no candidate"):
            P.plan_step(run, 1, export=fake_export(read_rows()), country_check=agrees)

    def test_a_step_is_planned_once(self, run: Path) -> None:
        write_decisions(run, decided())
        step = P.plan_step(run, 1, export=fake_export(read_rows()), country_check=agrees)
        P.write_step(step, P.step_dir(run, 1))
        with pytest.raises(P.InsertPlanError, match="planned once"):
            P.plan_step(run, 1, export=fake_export(read_rows()), country_check=agrees)

    def test_a_taken_id_means_plan_again(self, run: Path) -> None:
        write_decisions(run, decided())
        rows = read_rows(taken=[{"qid": COLOSSEUM, "site_id": "x", "source_id": "osm",
                                 "source_record_id": "y"}])  # fmt: skip
        with pytest.raises(P.InsertPlanError, match="plan again"):
            P.plan_step(run, 1, export=fake_export(rows), country_check=agrees)


# ------------------------------------------------------------------------------------ the writer
@pytest.fixture
def step() -> P.Step:
    return build()


@pytest.fixture
def radar_step() -> P.Step:
    return build(rows=read_rows(proposals=[radar_backed()]))


def _between(sql: str, start: str, stop: str) -> str:
    """The text of `sql` from `start` up to the next `stop`."""
    at = sql.index(start)
    return sql[at : sql.index(stop, at)]


def landed(step: P.Step) -> Any:
    """A fake read-only reader that answers as production would after the step committed."""
    i = step.inserts[0]
    columns = i.site_columns()
    site_row = {
        "id": i.site_id,
        **{k: v for k, v in columns.items() if k not in ("lat", "lon", "geom", "period_start")},
        "lat": i.lat,
        "lon": i.lon,
        "gx": i.lon,
        "gy": i.lat,
        "srid": 4326,
        "period_start": i.period_start,
        "site_type": i.site_type,
        "raw_data": i.raw_data,
        "parent_site_id": i.parent_site_id,
    }
    journal = [
        {"site_id": i.site_id, "table_name": "unified_sites", "column_name": c, "new_value": v,
         "test_id": P.TEST_ID, "confidence": P.CONFIDENCE}
        for c, v in [*columns.items(), ("raw_data", "{}"), ("updated_at", "now")]
    ]  # fmt: skip
    journal += [
        {"site_id": i.site_id, "table_name": "other", "column_name": "x", "new_value": "x",
         "test_id": P.TEST_ID, "confidence": P.CONFIDENCE}
    ] * (i.journal_rows - len(journal))  # fmt: skip

    def read(sql: str) -> list[dict[str, Any]]:
        if "FROM unified_sites u WHERE u.id IN" in sql:
            return [site_row]
        if "FROM unified_site_names" in sql:
            return [
                {"site_id": i.site_id, "name": n["name"], "name_normalized": n["name_key"],
                 "name_type": n["name_type"], "language_code": None}
                for n in i.names
            ]  # fmt: skip
        if "FROM site_external_ids" in sql:
            return [{"site_id": i.site_id, **x} for x in i.external_ids]
        if "FROM site_proposals" in sql:
            return [
                {"id": p["proposal_id"], "status": "approved", "promoted_site_id": i.site_id,
                 "reviewed_by": P.REVIEWED_BY, "review_notes": W.review_notes(step, i.site_id)}
                for p in i.proposals
            ]  # fmt: skip
        if "FROM user_contributions" in sql:
            return [
                {"id": c["contribution_id"], "enrichment_status": "promoted",
                 "promoted_site_id": i.site_id}
                for c in i.contributions
            ]  # fmt: skip
        if "FROM remediation_change_log" in sql:
            return journal
        raise AssertionError(sql)

    return read


def _lit_uuid(value: str) -> str:
    return f"'{value}'::uuid"


def code(sql: str) -> str:
    """The statement without its comment lines (the lint reads it the same way)."""
    return "\n".join(x for x in sql.splitlines() if not x.strip().startswith("--"))


class TestTheStatements:
    def test_the_apply_carries_every_guard_and_invariant(self, step: P.Step) -> None:
        sql = W.render_apply(step)
        W.lint(sql, "apply")
        for says in [*W.GUARD_SAYS.values(), *W.INVARIANT_SAYS.values()]:
            assert says in sql
        assert sql.count("\nCOMMIT;\n") == 1 and f"-- plan sha256 {step.digest}" in sql
        assert "INSERT INTO unified_sites" in sql and "DELETE" not in code(sql)
        assert "INSERT INTO site_external_ids" in sql and "UPDATE site_proposals" in sql
        assert "SET LOCAL statement_timeout" in sql

    def test_the_undo_retires_through_the_scope_write_path(self, step: P.Step) -> None:
        sql = W.render_rollback(step)
        W.lint(sql, "rollback")
        assert "apply_remediation_change('unified_sites', 'scope_status'" in sql
        assert "'retired'" in sql and "INSERT INTO unified_sites" not in sql
        assert "DELETE" not in code(sql) and step.rollback_stamp in sql
        for says in W.UNDO_SAYS.values():
            assert says in sql

    @pytest.mark.parametrize(
        ("kind", "edit", "why"),
        [
            ("apply", lambda s: s.replace("COMMIT;\n", "COMMIT;\nCOMMIT;\n"), "one transaction"),
            ("apply", lambda s: s + "DELETE FROM unified_sites;\n", "DELETE"),
            (
                "apply",
                lambda s: s.replace("INSERT INTO unified_sites\n", "INSERT INTO x\n"),
                "creates no",
            ),
            ("rollback", lambda s: s.replace("apply_remediation_change(", "f("), "retires"),
        ],
    )
    def test_the_lint_refuses_another_shape(self, step: P.Step, kind, edit, why) -> None:
        sql = W.render_apply(step) if kind == "apply" else W.render_rollback(step)
        with pytest.raises(W.WriterError, match=why):
            W.lint(edit(sql), kind)

    def test_each_guard_reads_what_it_names(self) -> None:
        g = W.apply_guards()
        assert "u.id >= " in g[1] and "-ffff-ffff-ffff-ffffffffffff" in g[1]
        assert "u.source_record_id = p.source_record_id" in g[2]
        assert "e.value = p.qid" in g[3] and "e.value = p.enwiki_title" in g[3]
        assert "u.name_normalized = p.name_key" in g[4]
        assert f"<= {P.NAME_TWIN_METRES}" in g[4]
        assert "n.name_key IS DISTINCT FROM left(lower(unaccent(n.name)), 500)" in g[5]
        assert f"NOT ({W.proposal_held()})" in g[6]
        for column in P.PROPOSAL_COLUMNS:
            assert f"sp.{column}::text IS NOT DISTINCT FROM q.{W._old(column)}" in g[6]
        assert "sp.contribution_id::text IS NOT DISTINCT FROM q.contribution_id" in g[6]
        assert "s.parent_site_id IS NOT NULL" in g[7] and f"> {W.PARENT_METRES}" in g[7]
        assert "uc.enrichment_status IS NOT DISTINCT FROM 'promoted'" in g[8]
        assert f"NOT ({W.contribution_held()})" in g[8]

    def test_each_update_carries_its_old_values_and_counts_its_rows(self, radar_step) -> None:
        """The old-value guard rides on the write itself (`apply_remediation_change`'s pattern): a
        proposal or contribution changed after guard 6/8 is skipped by the UPDATE, and the row count
        then stops the transaction instead of a lost update with a journal that lies."""
        sql = W.render_apply(radar_step)
        proposals = _between(sql, "UPDATE site_proposals sp", "RETURNING")
        assert f"WHERE sp.id = q.proposal_id\n           AND {W.proposal_held()}" in proposals
        contributions = _between(sql, "UPDATE user_contributions uc", "RETURNING")
        assert "SET enrichment_status = 'promoted', promoted_site_id = c.site_id" in contributions
        assert f"AND {W.contribution_held()}" in contributions
        assert sql.count("GET DIAGNOSTICS written = ROW_COUNT;") == 2
        assert "bad := (SELECT count(*) FROM _ins_prop) - written / 6;" in sql
        assert "bad := (SELECT count(*) FROM _ins_contrib) - written / 2;" in sql
        for says in W.WRITE_SAYS.values():
            assert says in sql
        assert sql.index(W.WRITE_SAYS["proposals"]) < sql.index("UPDATE user_contributions")
        assert f"({_lit_uuid(CONTRIBUTION)}, " in sql and "'enriched'" in sql

    def test_the_undo_locks_and_restores_only_what_the_insert_wrote(self, radar_step) -> None:
        sql = W.render_rollback(radar_step)
        W.lint(sql, "rollback")
        assert sql.index("FOR UPDATE OF sp;") < sql.index("-- guard 1")
        assert sql.index("FOR UPDATE OF uc;") < sql.index("-- guard 1")
        proposals = _between(sql, "UPDATE site_proposals sp", "RETURNING")
        assert f"AND {W.proposal_written()}" in proposals
        contributions = _between(sql, "UPDATE user_contributions uc", "RETURNING")
        assert "SET enrichment_status = c.old_enrichment_status" in contributions
        assert f"AND {W.contribution_written()}" in contributions
        for says in [*W.UNDO_SAYS.values(), *W.UNDO_WRITE_SAYS.values()]:
            assert says in sql
        # 2 per site, 6 per proposal, 2 per contribution
        assert "c.n <> 10" in sql

    def test_each_invariant_reads_what_it_names(self, step: P.Step) -> None:
        inv = W.apply_invariants(step.run_stamp)
        assert (
            "NOT ST_Equals(u.geom" in inv["rows"] and "u.raw_data IS DISTINCT FROM" in inv["rows"]
        )
        assert "u.period_name IS DISTINCT FROM (CASE WHEN u.period_start IS NULL" in inv["rows"]
        assert "_coord_provenance" in inv["markers"] and "_period_provenance" in inv["markers"]
        assert "COALESCE(l.n, 0) <> p.journal_rows" in inv["journal"]
        assert "sp.promoted_site_id IS DISTINCT FROM q.site_id" in inv["proposals"]
        assert W.contribution_written() in inv["contributions"]

    def test_the_undo_moves_in_scope_to_retired_and_nothing_else(self, step: P.Step) -> None:
        sql = W.render_rollback(step)
        assert "'in_scope', 'retired', 'D57/insert-site'" in sql
        assert "r.scope_reason, r.retire_reason" in sql
        checks = W.undo_checks(step.rollback_stamp, 8)
        assert "u.scope_reason IS DISTINCT FROM p.scope_reason" in checks[1]
        assert "c.n <> 8" in checks["journal"]

    def test_a_refusal_text_that_would_break_its_literal_is_refused(self) -> None:
        with pytest.raises(W.WriterError, match="RAISE literal"):
            W._raise("s", "the undo's reason")
        with pytest.raises(W.WriterError, match="RAISE literal"):
            W._raise("s", "100% sure")

    def test_an_empty_step_renders_nothing(self, step: P.Step) -> None:
        empty = P.Step(run="d57-test", number=1, inserts=[])
        with pytest.raises(W.WriterError):
            W.render_apply(empty)
        with pytest.raises(W.WriterError):
            W.render_rollback(empty)

    def test_a_rehearsal_swaps_the_one_commit(self, step: P.Step) -> None:
        sql = W.rehearsal_of(W.render_apply(step), "APPLY.sql")
        assert sql.endswith("\nROLLBACK;\n") and "\nCOMMIT;\n" not in sql

    def test_the_lint_reads_code_and_not_literals_or_comments(self, step: P.Step) -> None:
        """A web quote in `raw_data` may say anything; a plan must not fail on it after its files
        exist. A comment with an apostrophe opens no literal, `--` in a literal opens no comment."""
        [row] = step.inserts
        quoted = P.Insert(**{**row.__dict__, "raw_data": {**row.raw_data, "q": (
            "They DELETE nothing; ALTER TABLE x; DROP TABLE y; TRUNCATE z; -- not a comment\n"
            "COMMIT;\nBEGIN;\nINSERT INTO unified_sites")}})  # fmt: skip
        bare = P.Step(run="d57-test", number=1, inserts=[quoted])
        bare.probe = step.probe
        W.render_checked(bare)
        assert W.code_of("-- the lane's 'x\nSELECT 'a--b', 'it''s';") == "\nSELECT '', '';"
        with pytest.raises(W.WriterError, match="unterminated"):
            W.code_of("SELECT 'open")

    @pytest.mark.parametrize("word", ["DELETE FROM x", "delete from x", "ALTER  TABLE x"])
    def test_the_lint_still_refuses_the_word_in_code(self, step: P.Step, word: str) -> None:
        sql = W.render_apply(step).replace("\nCOMMIT;\n", f"\n{word};\nCOMMIT;\n")
        with pytest.raises(W.WriterError, match="not a statement"):
            W.lint(sql, "apply")

    def test_a_step_without_proposals_renders(self, step: P.Step) -> None:
        bare = P.Step(run="d57-test", number=1, inserts=[
            P.Insert(**{**step.inserts[0].__dict__, "proposals": []})])  # fmt: skip
        W.lint(W.render_apply(bare), "apply")
        assert "INSERT INTO _ins_prop VALUES" not in W.render_apply(bare)
        assert "INSERT INTO _ins_contrib VALUES" not in W.render_apply(bare)


class TestTheFiles:
    def _planned(self, run: Path, step: P.Step) -> Path:
        target = P.step_dir(run, 1)
        P.write_step(step, target)
        return target

    def test_emit_needs_the_undo_first(self, run: Path, step: P.Step) -> None:
        target = self._planned(run, step)
        with pytest.raises(W.WriterError, match="undo is written before"):
            W.emit(target)
        W.write_rollback(step, target)
        assert W.emit(target)["digest"] == step.digest
        assert W.check_delivered(target).digest == step.digest

    def test_an_edited_statement_is_never_sent(self, run: Path, step: P.Step) -> None:
        target = self._planned(run, step)
        W.write_rollback(step, target)
        W.emit(target)
        apply_sql = target / W.APPLY_FILE
        apply_sql.write_text(apply_sql.read_text(encoding="utf-8") + "-- x\n", encoding="utf-8")
        with pytest.raises(W.WriterError, match="not the statement"):
            W.check_delivered(target)

    def test_a_changed_plan_voids_its_files(self, run: Path, step: P.Step) -> None:
        target = self._planned(run, step)
        W.write_rollback(step, target)
        W.emit(target)
        rows = C.read_jsonl(target / P.PLAN_FILE)
        rows[0]["name"] = "Colosseo"
        C.write_jsonl(target / P.PLAN_FILE, rows)
        with pytest.raises(P.InsertPlanError, match="names digest"):
            W.check_delivered(target)


class TestThePlanCommand:
    def test_a_statement_the_lint_refuses_leaves_no_plan_behind(self, run, step, monkeypatch):
        monkeypatch.setattr(RUN, "_country_check", lambda: agrees)
        monkeypatch.setattr(RUN.P, "plan_step", lambda *a, **k: step)

        def refuse(sql: str, kind: str) -> None:
            raise W.WriterError(f"{kind} refused")

        monkeypatch.setattr(W, "lint", refuse)
        with pytest.raises(W.WriterError, match="refused"):
            RUN.plan(run, 1)
        target = P.step_dir(run, 1)
        assert not (target / P.PLAN_FILE).exists() and not (target / P.STEP_FILE).exists()

    def test_a_clean_plan_writes_the_plan_and_its_undo(self, run, radar_step, monkeypatch):
        monkeypatch.setattr(RUN, "_country_check", lambda: agrees)
        monkeypatch.setattr(RUN.P, "plan_step", lambda *a, **k: radar_step)
        out = RUN.plan(run, 1)
        target = P.step_dir(run, 1)
        assert (target / P.PLAN_FILE).exists() and (target / W.ROLLBACK_FILE).exists()
        assert out["proposals_closed"] == 1 and out["contributions_promoted"] == 1
        assert "(radar " + CONTRIBUTION + ")" in (target / P.PLAN_MD).read_text(encoding="utf-8")


class TestTheReadback:
    def test_the_landed_write_reads_back_clean(self, step: P.Step) -> None:
        assert W.readback(step, read=landed(step)) == []

    def test_a_differing_column_is_a_deviation(self, step: P.Step) -> None:
        read = landed(step)

        def moved(sql: str):
            rows = read(sql)
            if "FROM unified_sites u WHERE u.id IN" in sql:
                rows = [{**rows[0], "country": "Vatican City"}]
            return rows

        assert any("country" in p for p in W.readback(step, read=moved))

    def test_a_missing_journal_row_is_a_deviation(self, step: P.Step) -> None:
        read = landed(step)

        def short(sql: str):
            rows = read(sql)
            return rows[:-1] if "remediation_change_log" in sql else rows

        assert any("journal holds" in p for p in W.readback(step, read=short))

    def test_a_radar_contribution_reads_back(self, radar_step: P.Step) -> None:
        read = landed(radar_step)
        assert W.readback(radar_step, read=read) == []

        def unpromoted(sql: str):
            rows = read(sql)
            if "FROM user_contributions" in sql:
                rows = [{**rows[0], "enrichment_status": "enriched"}]
            return rows

        assert any("radar contribution" in p for p in W.readback(radar_step, read=unpromoted))

    def test_the_undo_reads_back_the_restored_proposal_and_contribution(self, radar_step) -> None:
        [i] = radar_step.inserts
        [p] = i.proposals

        def undone(restored: bool):
            def read(sql: str):
                if "FROM unified_sites" in sql:
                    return [{"id": i.site_id, "scope_status": "retired",
                             "scope_reason": W.retire_reason(radar_step)}]  # fmt: skip
                if "FROM site_proposals" in sql:
                    old = p["old"] if restored else {**p["old"], "status": "approved"}
                    return [{"id": p["proposal_id"], **old}]
                if "FROM user_contributions" in sql:
                    old = p["contribution"]["old"]
                    if not restored:
                        old = {**old, "promoted_site_id": i.site_id}
                    return [{"id": CONTRIBUTION, **old}]
                raise AssertionError(sql)

            return read

        assert W.rollback_readback(radar_step, read=undone(True)) == []
        problems = W.rollback_readback(radar_step, read=undone(False))
        assert any("proposal" in x for x in problems)
        assert any("radar contribution" in x for x in problems)

    def test_accept_records_once_and_lists_the_sites(self, run, step: P.Step) -> None:
        target = P.step_dir(run, 1)
        P.write_step(step, target)
        W.write_rollback(step, target)
        W.emit(target)
        result = W.accept(target, read=landed(step))
        assert result["accepted"] and result["deviations"] == 0
        assert (target / W.INSERTED_FILE).read_text(encoding="utf-8") == f"{SITE_ID}\n"
        with pytest.raises(W.WriterError, match="accepted once"):
            W.accept(target, read=landed(step))


class TestTheProbes:
    def test_every_guard_gets_a_probe_that_corrupts_only_its_input(self, step: P.Step) -> None:
        cases = dict(W.probe_cases(step))
        assert sorted(cases) == [1, 2, 3, 4, 5, 6, 7]
        first = step.inserts[0]
        assert cases[1].inserts[0].site_id == step.probe["shown"]["site_id"]
        assert cases[2].inserts[0].source_record_id == step.probe["shown"]["source_record_id"]
        assert cases[3].inserts[0].qid == step.probe["shown"]["qid"]
        assert cases[4].inserts[0].name_key == step.probe["shown"]["name_normalized"]
        assert cases[5].inserts[0].name_key != first.name_key
        assert cases[6].inserts[0].proposals[0]["old"]["status"] == "rejected"
        assert cases[7].inserts[0].parent_site_id == step.probe["retired"]["site_id"]
        for case in cases.values():
            W.lint(W.render_apply(case), "apply")

    def test_a_radar_backed_step_probes_guard_8(self, radar_step: P.Step) -> None:
        cases = dict(W.probe_cases(radar_step))
        assert sorted(cases) == [1, 2, 3, 4, 5, 6, 7, 8]
        [p] = cases[8].inserts[0].proposals
        assert p["old"] == radar_step.inserts[0].proposals[0]["old"]
        assert p["contribution"]["old"] == {
            "enrichment_status": "enriched",
            "promoted_site_id": radar_step.probe["shown"]["site_id"],
        }
        for case in cases.values():
            W.lint(W.render_apply(case), "apply")

    def test_probes_need_their_rows(self, step: P.Step) -> None:
        step.probe = {}
        with pytest.raises(W.WriterError, match="probe rows"):
            W.probe_cases(step)


class TestTheTransport:
    def _target(self, run: Path, step: P.Step) -> Path:
        target = P.step_dir(run, 1)
        P.write_step(step, target)
        W.write_rollback(step, target)
        W.emit(target)
        return target

    def test_a_stamp_that_journals_already_is_never_applied_again(self, run, step, monkeypatch):
        target = self._target(run, step)
        monkeypatch.setattr(W, "journal_count", lambda stamp: 3)
        with pytest.raises(W.WriterError, match="never apply twice"):
            W.command_apply(target)

    def test_a_stopped_script_with_an_empty_journal_did_not_commit(self, step, monkeypatch):
        monkeypatch.setattr(W, "journal_count", lambda stamp: 0)
        assert W.settle(step, "psql exited 3", session_ended=True) == W.MA.EXIT_NOT_COMMITTED
        with pytest.raises(W.OutcomeUnknown):
            W.settle(step, "timeout", session_ended=False)

    def test_the_undo_is_rehearsed_only_on_the_landed_write(self, run, step, monkeypatch):
        target = self._target(run, step)
        monkeypatch.setattr(W, "journal_count", lambda stamp: 0)
        with pytest.raises(W.WriterError, match="has not landed"):
            W.command_rehearse_rollback(target)


class TestTheCommandLine:
    def test_a_refusal_exits_1_and_says_why(self, tmp_path: Path, capsys) -> None:
        code = RUN.main(["status", "--run", str(tmp_path / "nothing")])
        assert code == 0
        code = RUN.main(["plan", "--run", str(tmp_path / "nothing"), "--step", "1"])
        assert code == 1 and "REFUSED" in capsys.readouterr().err

    def test_a_run_name_lives_under_the_lane_root(self) -> None:
        assert RUN.run_dir("d57-2026-10-24") == C.ROOT / "d57-2026-10-24"
