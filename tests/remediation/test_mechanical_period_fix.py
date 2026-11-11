"""The period correction lane (`scripts/remediation/mechanical/period_fix.py`, D121/D122/D124).

DB-less: production is a fixture export, each rule and each refusal asserted by what it produces.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import period_fix as M  # noqa: E402
from mechanical.plan import SNAPSHOT_KIND, JournalLink, PlanError  # noqa: E402

from pipeline import periods as P  # noqa: E402
from pipeline.utils.text import UNDATED, categorize_period  # noqa: E402

RULE_SITE = "0020c4e1-21fd-4174-94ae-912703cb7ec6"
WORD_SITE = "fac97fda-c33c-46eb-9c3c-e0afd48a2eab"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
WAVE = "2026-11-07"

DERIVED = {
    "source": "WD3 decision (derived, round 0, rule:derived_rule.json)",
    "status": "RULE",
    "reasoning": "site_type 'Hillfort' lies in 'Iron Age'; the rule writes the epoch's beginning.",
}
COUNTED = {"source": "WD5 decision (counted, round 0, field_researcher:x)", "status": "MISSING"}


def live(site_id: str, start: int | None, **over: Any) -> M.Live:
    base = {
        "site_id": site_id,
        "name": "Site",
        "country": "Algeria",
        "source_id": "ancient_nerds",
        "scope_status": "in_scope",
        "lat": 36.6,
        "lon": 2.2,
        "period_start": start,
        "period_end": None,
        "period_name": UNDATED if start is None else categorize_period(start),
    }
    base.update(over)
    return M.Live(**base)


def link(jid: int, old: str | None, new: str | None, *evidence: dict[str, Any]) -> M.Link:
    return M.Link(JournalLink(jid, f"run-{jid}", "WD3/structured-fields", old, new), tuple(evidence))


def entry(site_id: str, current: int, word: str, new: int | None, jid: int) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "current": current,
        "period_word": word,
        "new_regional_start": new,
        "journal_id": jid,
        "origin": "WD5 period-word answer",
        "run_stamp": f"run-{jid}",
    }


ALGERIA_ROMAN = P.start_year("Roman", country="Algeria")


class TestRules:
    def test_the_site_type_rule_s_live_start_becomes_undated(self) -> None:
        site = live(RULE_SITE, -800, country="England")
        d = M.decide_d122(site, [link(1, None, "-800", DERIVED)])
        assert d is not None and d.rule == "d122-unsourced" and d.new_start is None
        assert d.journal_id == 1 and "D122" in d.evidence[0]["source"]

    def test_a_researched_start_is_not_d122_s(self) -> None:
        assert M.decide_d122(live(RULE_SITE, -800), [link(1, None, "-800", COUNTED)]) is None

    def test_a_rule_start_that_a_later_write_replaced_is_not_d122_s(self) -> None:
        links = [link(1, None, "-800", DERIVED), link(2, "-800", "-500", COUNTED)]
        assert M.decide_d122(live(RULE_SITE, -500), links) is None

    def test_a_listed_word_gets_its_regional_year(self) -> None:
        site = live(WORD_SITE, 43)
        out = M.decide_d121(site, [link(5, None, "43", COUNTED)], entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5), list_sha="x")
        assert isinstance(out, M.Decision)
        assert out.rule == "d121-regional" and out.new_start == ALGERIA_ROMAN

    def test_a_coarse_word_gives_no_year(self) -> None:
        site = live(WORD_SITE, -2500, country="England")
        out = M.decide_d121(site, [link(5, None, "-2500", COUNTED)], entry(WORD_SITE, -2500, "Bronze Age", None, 5), list_sha="x")
        assert isinstance(out, M.Decision) and out.rule == "d121-no-year" and out.new_start is None

    def test_a_value_moved_since_the_list_is_refused(self) -> None:
        site = live(WORD_SITE, 50)
        out = M.decide_d121(site, [link(5, None, "50", COUNTED)], entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5), list_sha="x")
        assert isinstance(out, M.Refusal) and out.reason == "moved-since-list"

    def test_a_journal_moved_since_the_list_is_refused(self) -> None:
        site = live(WORD_SITE, 43)
        links = [link(5, None, "40", COUNTED), link(6, "40", "43", COUNTED)]
        out = M.decide_d121(site, links, entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5), list_sha="x")
        assert isinstance(out, M.Refusal) and out.reason == "journal-moved-since-list"

    def test_a_table_that_moved_since_the_list_is_refused(self) -> None:
        site = live(WORD_SITE, 43)
        out = M.decide_d121(site, [link(5, None, "43", COUNTED)], entry(WORD_SITE, 43, "Roman", -999, 5), list_sha="x")
        assert isinstance(out, M.Refusal) and out.reason == "table-moved-since-list"


class TestWave:
    def test_a_listed_rule_row_is_d122_s_and_counted_once(self) -> None:
        sites = {RULE_SITE: live(RULE_SITE, 43), WORD_SITE: live(WORD_SITE, 43)}
        journal = {RULE_SITE: [link(1, None, "43", DERIVED)], WORD_SITE: [link(5, None, "43", COUNTED)]}
        d113 = [entry(RULE_SITE, 43, "Roman", ALGERIA_ROMAN, 1), entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5)]
        decisions, refused, counters = M.build_decisions(sites, journal, d113, list_sha="x")
        assert {d.site_id: d.rule for d in decisions} == {RULE_SITE: "d122-unsourced", WORD_SITE: "d121-regional"}
        assert counters["d121-covered-by-d122"] == 1 and not refused

    def test_a_journal_that_does_not_end_at_the_live_value_is_refused(self) -> None:
        sites = {WORD_SITE: live(WORD_SITE, 43)}
        journal = {WORD_SITE: [link(5, None, "40", COUNTED)]}
        d113 = [entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5)]
        decisions, refused, _ = M.build_decisions(sites, journal, d113, list_sha="x")
        assert not decisions and refused[0].reason == "journal-disagrees"

    def test_a_site_named_twice_is_refused(self) -> None:
        e = entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5)
        with pytest.raises(PlanError):
            M.build_decisions({WORD_SITE: live(WORD_SITE, 43)}, {}, [e, e], list_sha="x")

    def test_a_cited_start_fills_an_undated_site(self) -> None:
        cited = {
            "site_id": OTHER,
            "start": -1150,
            "url": "https://example.org/p",
            "quote": "dated to the 12th century BC",
            "answered_by": "field_researcher:d124-b0001",
            "model": "anthropic/claude-sonnet-5-5 (Claude Code agent)",
            "reason": "radiocarbon",
        }
        sites = {OTHER: live(OTHER, None, country="England", lat=53.2, lon=-2.7)}
        decisions, refused, _ = M.build_decisions(sites, {}, [], list_sha="", cited=[cited])
        assert not refused and decisions[0].rule == "d124-cited" and decisions[0].new_start == -1150


class TestStep:
    def decision(self, new: int | None) -> M.Decision:
        return M.Decision(WORD_SITE, "Site", "d121-regional", 43, 5, new, "n", ({"source": "s"},))

    def test_a_year_writes_its_start_and_its_bucket(self) -> None:
        cells = M.step_verdicts(self.decision(-1500), live(WORD_SITE, 43), [link(5, None, "43")])
        assert {(c.column, c.new_value) for c in cells} == {
            ("period_start", "-1500"),
            ("period_name", categorize_period(-1500)),
        }
        assert all(c.ok and c.finding_test_id.startswith("D121/") for c in cells)

    def test_undated_clears_the_start_and_writes_the_residue_label(self) -> None:
        cells = M.step_verdicts(self.decision(None), live(WORD_SITE, 43), [link(5, None, "43")])
        assert {(c.column, c.new_value) for c in cells} == {("period_start", None), ("period_name", UNDATED)}

    def test_an_unchanged_label_is_not_written(self) -> None:
        cells = M.step_verdicts(self.decision(40), live(WORD_SITE, 43), [link(5, None, "43")])
        assert [c.column for c in cells] == ["period_start"]

    def test_a_site_moved_since_the_wave_is_refused(self) -> None:
        cells = M.step_verdicts(self.decision(-1500), live(WORD_SITE, 50), [link(5, None, "43"), link(6, "43", "50")])
        assert len(cells) == 1 and not cells[0].ok and cells[0].reason == "moved-since-wave"


class TestLane:
    def test_the_name_resolves_with_the_period_pair_and_the_label_invariant(self) -> None:
        lane = L.resolve_lane(f"period-fix-{WAVE}-s002")
        assert lane.columns == ("period_start", "period_name")
        assert UNDATED in lane.cell("period_name").allowed_new_values
        assert lane.cell("period_start").clears and lane.cell("period_start").fills_null
        assert lane.run_stamp == f"{WAVE}_mechanical-period-fix-s002"
        assert "period_start IS NULL" in A.readback_for(lane)

    @pytest.mark.parametrize("name", ["period-fix-2026-11-07", "period-fix-x-s001", "period-fix-2026-11-07-s1"])
    def test_a_malformed_name_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            M.lane_of(name)


class TestAccept:
    def rows(self) -> list[dict[str, Any]]:
        return [
            {"site_id": WORD_SITE, "column": "period_start", "old_value": "43", "new_value": None},
            {"site_id": WORD_SITE, "column": "period_name", "old_value": "1 - 500 AD", "new_value": UNDATED},
        ]

    def journal(self, stamp: str) -> list[dict[str, Any]]:
        return [
            {"row_pk": WORD_SITE, "column_name": r["column"], "run_stamp": stamp, "old_value": r["old_value"], "new_value": r["new_value"]}
            for r in self.rows()
        ]

    def test_a_written_step_has_no_deviation(self) -> None:
        lane = M.fix_lane(WAVE, 1)
        assert M.deviations(lane, self.rows(), {WORD_SITE: live(WORD_SITE, None)}, self.journal(lane.run_stamp)) == []

    def test_a_missing_write_and_a_rollback_are_deviations(self) -> None:
        lane = M.fix_lane(WAVE, 1)
        found = M.deviations(lane, self.rows(), {WORD_SITE: live(WORD_SITE, 43)}, self.journal(lane.rollback_run_stamp))
        assert any("rollback" in f for f in found) and any("does not hold" in f for f in found)

    def test_the_export_parser_reads_sites_and_journal_rows(self) -> None:
        text = "\n".join(
            json.dumps(x)
            for x in (
                {"kind": "site", "row": {"site_id": WORD_SITE, "name": "S", "country": "Algeria", "source_id": "ancient_nerds", "scope_status": None, "lat": 1.0, "lon": 2.0, "period_start": 43, "period_end": None, "period_name": "1 - 500 AD"}},
                {"kind": "journal", "row": {"id": 5, "row_pk": WORD_SITE, "run_stamp": "r", "test_id": "t", "old_value": None, "new_value": "43", "evidence": [DERIVED]}},
                {"kind": SNAPSHOT_KIND, "row": {"exported_at": "now"}},
            )
        )
        sites, journal, at = M.parse_export(text)
        assert sites[WORD_SITE].period_start == 43 and M.is_site_type_rule(journal[WORD_SITE][0]) and at == "now"


# ------------------------------------------------------------------------------ D136/D137 bands
def band_row(site_id: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": site_id,
        "name": "Yarrowbury",
        "status": "band",
        "band": "1500 - 500 BC",
        "edge": -1500,
        "epoch": "iron age",
        "band_from": "epoch",
        "source_kind": "lane-quote",
        "quote": "Yarrowbury is an Iron Age hill fort situated close to Bigbury in Devon, England.",
        "url": "https://en.wikipedia.org/wiki/Yarrowbury",
        "country": "England",
    }
    base.update(over)
    return base


YEAR_ROW = {
    "band_from": "year",
    "band": "500 BC - 1 AD",
    "edge": -500,
    "year": -500,
    "year_quote": "dating to the 5th century BC",
    "year_url": "unified_sites.description",
    "epoch_band": "1500 - 500 BC",
}


class TestBands:
    def test_an_epoch_band_fills_an_undated_site_with_its_edge_and_label(self) -> None:
        site = live(RULE_SITE, None, country="England", lat=50.3, lon=-3.9)
        d = M.decide_band(site, [link(1, "-800", None)], band_row(RULE_SITE))
        assert isinstance(d, M.Decision)
        assert d.rule == "d136-band" and d.new_start == -1500 and d.journal_id == 1
        quotes = " ".join(f"{e.get('source')} {e.get('quote')}" for e in d.evidence)
        assert "D136" in d.evidence[0]["source"] and "D137" in d.evidence[0]["source"]
        assert "Iron Age hill fort" in quotes and "iron age" in quotes and "lane-quote" in quotes
        cells = M.step_verdicts(d, site, [link(1, "-800", None)])
        assert {(c.column, c.new_value) for c in cells} == {("period_start", "-1500"), ("period_name", "1500 - 500 BC")}
        assert all(c.finding_test_id.startswith("D136/") for c in cells)

    def test_a_stated_year_writes_its_own_band_edge(self) -> None:
        site = live(RULE_SITE, None, country="Switzerland", lat=47.35, lon=8.49)
        d = M.decide_band(site, [], band_row(RULE_SITE, **YEAR_ROW))
        assert isinstance(d, M.Decision) and d.rule == "d137-year" and d.new_start == -500
        assert any("5th century BC" in str(e.get("quote")) for e in d.evidence)

    def test_a_site_dated_since_the_candidates_is_refused(self) -> None:
        out = M.decide_band(live(RULE_SITE, -800), [link(1, None, "-800")], band_row(RULE_SITE))
        assert isinstance(out, M.Refusal) and out.reason == "dated-since-candidates"

    def test_a_band_outside_the_d58_window_is_listed_not_written(self) -> None:
        row = band_row(RULE_SITE, status="scope-hold", band="1000 - 1500 AD", edge=1000, epoch="medieval")
        sites = {RULE_SITE: live(RULE_SITE, None, country="England", lat=52.6, lon=-3.0)}
        decisions, refused, counters = M.build_decisions(sites, {}, [], list_sha="", bands=[row])
        assert not decisions and refused[0].reason == "d58-window" and counters["skip:d58-window"] == 1

    def test_the_wave_counts_bands_by_rule(self) -> None:
        sites = {
            RULE_SITE: live(RULE_SITE, None, country="England", lat=50.3, lon=-3.9),
            OTHER: live(OTHER, None, country="Switzerland", lat=47.35, lon=8.49),
        }
        bands = [band_row(RULE_SITE), band_row(OTHER, **YEAR_ROW)]
        decisions, refused, counters = M.build_decisions(sites, {}, [], list_sha="", bands=bands)
        assert not refused and counters["rule:d136-band"] == 1 and counters["rule:d137-year"] == 1


class TestLoadBands:
    def write(self, tmp_path: Path, *rows: dict[str, Any]) -> Path:
        path = tmp_path / "CANDIDATES.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_only_band_and_scope_hold_rows_are_loaded(self, tmp_path: Path) -> None:
        path = self.write(
            tmp_path,
            band_row(RULE_SITE),
            {"site_id": OTHER, "name": "x", "status": "undated"},
            {"site_id": WORD_SITE, "name": "y", "status": "year-stated-only", "year_band": "1 - 500 AD"},
        )
        assert [r["site_id"] for r in M.load_bands(path)] == [RULE_SITE]

    def test_an_edge_that_is_not_its_band_s_edge_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError):
            M.load_bands(self.write(tmp_path, band_row(RULE_SITE, edge=-800)))

    def test_a_year_row_whose_year_lies_outside_its_band_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError):
            M.load_bands(self.write(tmp_path, band_row(RULE_SITE, **{**YEAR_ROW, "year": 100})))

    def test_a_band_without_a_quote_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError):
            M.load_bands(self.write(tmp_path, band_row(RULE_SITE, quote="")))


# ------------------------------------------------------------------------------ D138 stated years
def year_only_row(site_id: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": site_id,
        "name": "Kvitky",
        "status": "year-stated-only",
        "country": "Ukraine",
        "year_band": "4500 - 3000 BC",
        "year_sentences": [
            {
                "epochs": [],
                "file": "unified_sites",
                "mode": "single",
                "sentence": "Kvitky is a Cucuteni-Trypillia culture mega-settlement, dating to 3600-3200 BC.",
                "url": "unified_sites.description",
                "years": [-3600],
            },
            {
                "epochs": [],
                "file": "wiki_cache",
                "mode": "single",
                "quoted_by": None,
                "sentence": "The settlement was abandoned around 3200 BC.",
                "url": "https://en.wikipedia.org/wiki/Kvitky",
                "years": [-3200],
            },
        ],
    }
    base.update(over)
    return base


class TestStatedYears:
    def write(self, tmp_path: Path, *rows: dict[str, Any]) -> Path:
        path = tmp_path / "CANDIDATES.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_a_stated_year_fills_an_undated_site_with_its_band_edge(self) -> None:
        site = live(RULE_SITE, None, country="Ukraine", lat=49.3, lon=31.4)
        d = M.decide_year(site, [link(1, "-10000", None)], year_only_row(RULE_SITE))
        assert isinstance(d, M.Decision)
        assert d.rule == "d138-year" and d.new_start == -4500 and d.journal_id == 1
        assert "D138" in d.evidence[0]["source"] and "die 60 sites ja" in d.evidence[0]["quote"]
        assert any("3600-3200 BC" in str(e.get("quote")) for e in d.evidence)
        cells = M.step_verdicts(d, site, [link(1, "-10000", None)])
        assert {(c.column, c.new_value) for c in cells} == {
            ("period_start", "-4500"),
            ("period_name", "4500 - 3000 BC"),
        }
        assert all(c.finding_test_id.startswith("D138/") for c in cells)

    def test_a_site_dated_since_the_candidates_is_refused(self) -> None:
        out = M.decide_year(live(RULE_SITE, -800), [link(1, None, "-800")], year_only_row(RULE_SITE))
        assert isinstance(out, M.Refusal) and out.reason == "dated-since-candidates"

    def test_a_reading_error_is_listed_not_written(self) -> None:
        sid = next(iter(M.D138_READING_ERRORS))
        sites = {sid: live(sid, None, country="Spain", lat=43.3, lon=-4.4)}
        decisions, refused, counters = M.build_decisions(
            sites, {}, [], list_sha="", years=[year_only_row(sid)]
        )
        assert not decisions and refused[0].reason == "d137-reading-error"
        assert counters["skip:d137-reading-error"] == 1

    def test_a_year_outside_the_d58_window_is_listed_not_written(self) -> None:
        row = year_only_row(
            RULE_SITE,
            year_band="1000 - 1500 AD",
            year_sentences=[{**year_only_row(RULE_SITE)["year_sentences"][0], "years": [1200]}],
        )
        sites = {RULE_SITE: live(RULE_SITE, None, country="England", lat=52.6, lon=-3.0)}
        decisions, refused, _ = M.build_decisions(sites, {}, [], list_sha="", years=[row])
        assert not decisions and refused[0].reason == "d58-window"

    def test_only_year_stated_only_rows_are_loaded(self, tmp_path: Path) -> None:
        path = self.write(tmp_path, band_row(OTHER), year_only_row(RULE_SITE))
        assert [r["site_id"] for r in M.load_years(path)] == [RULE_SITE]

    def test_a_band_that_is_not_the_earliest_year_s_band_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError):
            M.load_years(self.write(tmp_path, year_only_row(RULE_SITE, year_band="3000 - 1500 BC")))

    def test_a_year_without_a_quote_is_refused(self, tmp_path: Path) -> None:
        row = year_only_row(RULE_SITE)
        row["year_sentences"][0]["sentence"] = ""
        with pytest.raises(PlanError):
            M.load_years(self.write(tmp_path, row))


# ------------------------------------------------------------------------------ D20 sourced starts
SYRIA = {"country": "Syria", "lat": 33.25, "lon": 35.71}
FABLE = "anthropic/claude-fable-5-2 (Claude Code agent)"
AYYUBID = "The fortress was begun around 1200 by the Ayyubids."


def found(url: str, quote: str) -> dict[str, str]:
    return {"url": url, "quote": quote, "outcome": "found", "detail": "visible text"}


def d20_row(site_id: str, **over: Any) -> dict[str, Any]:
    """A row of a scope-window wave's PERIOD_WRONG.jsonl, as `scope_judge.build` writes it
    (`test_identity_b_scope.py` pins the two to each other)."""
    base: dict[str, Any] = {
        "site_id": site_id,
        "wave": "2026-11-12",
        "name": "Ali Masjid Fort",
        "stored_period_start": 1837,
        "stored_period_name": "1500+ AD",
        "period_start": 300,
        "origin": "fields-wd3",
        "recheck_d10": True,
        "label_borderline": False,
        "why": "The fort stands on a Kushan stronghold of the 3rd century.",
        "answered_by": "web_verifier:r1-b01",
        "model": FABLE,
        "answered_at": "2026-11-11T02:00:00+00:00",
        "quotes": [
            found("https://example.org/ali-masjid", "The pass is guarded by the fort of Ali Masjid."),
            found("https://example.net/khyber", "The first stronghold here was built in the 3rd century AD."),
        ],
        "ask": "mechanical/period_fix.py wave --no-d113 --d20 writes the corrected start (rule d20-sourced)",
    }
    base.update(over)
    return base


def kept(start: int | None = 1837, **over: Any) -> M.Live:
    """A site the scope wave kept in scope, in Pakistan (the window runs through 1500 AD there)."""
    return live(OTHER, start, **{"country": "Pakistan", "lat": 34.0, "lon": 71.2, **over})


class TestD20:
    def test_a_sourced_start_replaces_the_stored_one_with_the_answer_as_evidence(self) -> None:
        site, links = kept(), [link(7, None, "1837", COUNTED)]
        d = M.decide_d20(site, links, d20_row(OTHER))
        assert isinstance(d, M.Decision)
        assert (d.rule, d.live_start, d.new_start, d.journal_id) == ("d20-sourced", 1837, 300, 7)
        decision, *quotes, answer = d.evidence
        assert "D20" in decision["source"] and decision["quote"] == M.D20_QUOTE
        assert M.D20_QUOTE in (REPO / M.DECISIONS).read_text(encoding="utf-8")
        assert [e["url"] for e in quotes] == ["https://example.org/ali-masjid", "https://example.net/khyber"]
        assert "3rd century AD" in quotes[1]["quote"]
        assert "web_verifier:r1-b01" in answer["source"] and answer["model"] == FABLE
        assert answer["reasoning"].startswith("The fort stands on a Kushan stronghold")
        assert not any("D124" in str(e.get("source")) for e in d.evidence)
        cells = M.step_verdicts(d, site, links)
        assert {(c.column, c.old_value, c.new_value) for c in cells} == {
            ("period_start", "1837", "300"),
            ("period_name", "1500+ AD", "1 - 500 AD"),
        }
        assert all(c.ok and c.finding_test_id.startswith("D20/") and c.evidence == d.evidence for c in cells)

    def test_a_year_no_found_quote_states_is_listed_not_written(self) -> None:
        row = d20_row(OTHER, quotes=[found("https://example.org/ali-masjid", "An old fort of the Kushan kings.")])
        out = M.decide_d20(kept(), [], row)
        assert isinstance(out, M.Refusal) and out.reason == "d20-no-quote-states-year"
        decisions, _, counters = M.build_decisions({OTHER: kept()}, {}, [], list_sha="", d20=[row])
        assert not decisions and counters["skip:d20-no-quote-states-year"] == 1

    def test_a_start_that_moved_since_the_answer_is_refused(self) -> None:
        out = M.decide_d20(kept(1500), [], d20_row(OTHER))
        assert isinstance(out, M.Refusal) and out.reason == "moved-since-answer"
        assert "1837" in out.note and "1500" in out.note

    @pytest.mark.parametrize("status", [None, "pending", "retired"])
    def test_a_site_the_scope_wave_has_not_written_in_scope_is_refused(self, status: str | None) -> None:
        out = M.decide_d20(kept(scope_status=status), [], d20_row(OTHER))
        assert isinstance(out, M.Refusal) and out.reason == "d20-scope-not-written"

    def test_a_borderline_start_is_written_where_the_answer_was_asked_the_label(self) -> None:
        row = d20_row(
            OTHER,
            stored_period_start=1227,
            period_start=1200,
            label_borderline=True,
            quotes=[found("https://example.org/nimrod", AYYUBID)],
        )
        sites = {OTHER: live(OTHER, 1227, **SYRIA)}
        decisions, refused, _ = M.build_decisions(sites, {}, [], list_sha="", d20=[row])
        assert not refused and (decisions[0].rule, decisions[0].new_start) == ("d20-sourced", 1200)

    def test_a_start_that_makes_a_site_borderline_unasked_is_listed_not_written(self) -> None:
        row = d20_row(
            OTHER, stored_period_start=1600, period_start=1200, quotes=[found("https://example.org/nimrod", AYYUBID)]
        )
        sites = {OTHER: live(OTHER, 1600, **SYRIA)}
        decisions, refused, counters = M.build_decisions(sites, {}, [], list_sha="", d20=[row])
        assert not decisions and refused[0].reason == "d58-window" and "borderline" in refused[0].note
        assert counters["skip:d58-window"] == 1

    def test_a_start_outside_the_window_is_listed_even_where_the_label_was_asked(self) -> None:
        row = d20_row(
            OTHER,
            period_start=900,
            label_borderline=True,
            quotes=[found("https://example.org/x", "The hall was raised in 900 AD.")],
        )
        sites = {OTHER: live(OTHER, 1837, country="England", lat=52.6, lon=-3.0)}
        decisions, refused, _ = M.build_decisions(sites, {}, [], list_sha="", d20=[row])
        assert not decisions and refused[0].reason == "d58-window" and "outside" in refused[0].note

    def test_a_journal_that_does_not_end_at_the_stored_start_is_refused(self) -> None:
        journal = {OTHER: [link(7, None, "1800", COUNTED)]}
        decisions, refused, _ = M.build_decisions({OTHER: kept()}, journal, [], list_sha="", d20=[d20_row(OTHER)])
        assert not decisions and refused[0].reason == "journal-disagrees"

    def test_a_site_named_twice_is_refused(self) -> None:
        with pytest.raises(PlanError, match="another rule already decides"):
            M.build_decisions({OTHER: kept()}, {}, [], list_sha="", d20=[d20_row(OTHER), d20_row(OTHER)])


class TestLoadD20:
    def write(self, tmp_path: Path, *rows: dict[str, Any]) -> Path:
        path = tmp_path / "PERIOD_WRONG.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_the_rows_load_as_written(self, tmp_path: Path) -> None:
        rows = [d20_row(OTHER), d20_row(RULE_SITE, stored_period_start=None)]
        assert M.load_d20(self.write(tmp_path, *rows)) == rows

    def test_a_row_without_the_answer_s_stamp_is_refused(self, tmp_path: Path) -> None:
        stamp = ("answered_by", "model", "answered_at", "why", "label_borderline")
        old = {k: v for k, v in d20_row(OTHER).items() if k not in stamp}
        with pytest.raises(PlanError, match="exactly the keys"):
            M.load_d20(self.write(tmp_path, old))

    @pytest.mark.parametrize(
        ("over", "says"),
        [
            ({"period_start": "300"}, "is not a year"),
            ({"period_start": True}, "is not a year"),
            ({"quotes": []}, "has no quote"),
            ({"quotes": [{**found("https://example.org/p", "built in 300 AD"), "outcome": "not-found"}]}, "not found on"),
            ({"quotes": [found("example.org/p", "built in 300 AD")]}, "not found on"),
            ({"model": "minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)"}, "not answered by a Claude model"),
            ({"answered_by": " "}, "not answered by a Claude model"),
        ],
    )
    def test_a_row_that_is_no_found_claude_answer_is_refused(
        self, tmp_path: Path, over: dict[str, Any], says: str
    ) -> None:
        with pytest.raises(PlanError, match=says):
            M.load_d20(self.write(tmp_path, d20_row(OTHER, **over)))


class TestD20Wave:
    """The wave and its step under a temp root, production a fixture export."""

    WAVE = "2026-11-12"

    def export(self, start: int) -> str:
        site = {
            "site_id": OTHER,
            "name": "Ali Masjid Fort",
            "country": "Pakistan",
            "source_id": "ancient_nerds",
            "scope_status": "in_scope",
            "lat": 34.0,
            "lon": 71.2,
            "period_start": start,
            "period_end": None,
            "period_name": categorize_period(start),
        }
        entry = {
            "id": 7,
            "row_pk": OTHER,
            "run_stamp": "2026-10-04_fields-wd3-s022",
            "test_id": "WD3/structured-fields",
            "old_value": None,
            "new_value": str(start),
            "evidence": [COUNTED],
        }
        rows = [
            {"kind": "site", "row": site},
            {"kind": "journal", "row": entry},
            {"kind": SNAPSHOT_KIND, "row": {"exported_at": "2026-11-12 08:00:00+00"}},
        ]
        return "\n".join(json.dumps(r) for r in rows)

    def wave(self, tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
        hand = tmp_path / "PERIOD_WRONG.jsonl"
        hand.write_text(json.dumps(d20_row(OTHER)) + "\n", encoding="utf-8")
        root = tmp_path / "mechanical_period_fix"
        summary = M.build_wave(
            self.WAVE, d113_path=None, d20_path=hand, read=lambda _sql: self.export(1837), root=root
        )
        return hand, root, summary

    def test_the_wave_plans_the_start_its_label_and_a_rollback(self, tmp_path: Path) -> None:
        hand, root, summary = self.wave(tmp_path)
        assert (summary["sites"], summary["rule:d20-sourced"], summary["steps"]) == (1, 1, 1)
        record = M.read_wave(self.WAVE, root)
        assert record["d20_sha256"] == M.sha256_file(hand) and record["refused"] == []
        step = M.plan_step(self.WAVE, 1, read=lambda _sql: self.export(1837), root=root)
        assert (step["lane"], step["sites"], step["cells"]) == (f"period-fix-{self.WAVE}-s001", 1, 2)
        out = root / self.WAVE / "s001"
        cells = [json.loads(line) for line in (out / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()]
        assert {(c["column"], c["old_value"], c["new_value"]) for c in cells} == {
            ("period_start", "1837", "300"),
            ("period_name", "1500+ AD", "1 - 500 AD"),
        }
        assert all(c["rule"].startswith("d20-sourced") for c in cells)
        assert all(any(e.get("model") == FABLE for e in c["evidence"]) for c in cells)
        assert "d20-sourced" in (out / "PLAN.md").read_text(encoding="utf-8")
        # the apply machinery takes the plan as it is: its validation, the pinned rollback, APPLY.sql
        lane = M.fix_lane(self.WAVE, 1)
        assert A.emit(A.load_records(out / "PLAN.jsonl"), out, lane, plan_path=out / "PLAN.jsonl") == 2
        apply_sql = (out / "APPLY.sql").read_text(encoding="utf-8")
        assert lane.run_stamp in apply_sql and "example.net/khyber" in apply_sql

    def test_a_start_written_between_the_wave_and_its_step_is_refused(self, tmp_path: Path) -> None:
        _, root, _ = self.wave(tmp_path)
        step = M.plan_step(self.WAVE, 1, read=lambda _sql: self.export(1700), root=root)
        assert step["cells"] == 0 and step["skip:moved-since-wave"] == 1
        assert not (root / self.WAVE / "s001" / "PLAN.jsonl").exists()
