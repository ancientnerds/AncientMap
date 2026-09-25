"""The wrong-both correction lane: the Opus re-verification's proposed values, written only where a
machine-verified verbatim quote carries them (`scripts/remediation/mechanical/wrong_both.py`).

RULES.md rule 5: "wrong-both rows carry a proposed value; it is not written by this audit. It goes to
a later correction lane that writes only with a machine-verified verbatim quote." The planner is a
pure function of the audit's files, the live rows and the pages the audit fetched; the readers are
driven by a stand-in for production that answers only the statements they send.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from mechanical import wrong_both as W  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

REV3 = L.REVERSAL_3.run_stamp
ARLES = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
CISS = "1b2c3d4e-5f6a-4b7c-9d8e-0f1a2b3c4d5e"
KEPT = "2c3d4e5f-6a7b-4c8d-8e9f-1a2b3c4d5e6f"
ANNA = "3d4e5f6a-7b8c-4d9e-9f0a-2b3c4d5e6f7a"
ARLES_KEY = "phase3:" + "a" * 64
CISS_KEY = "phase3:" + "b" * 64
KEPT_KEY = "phase3:" + "c" * 64
ANNA_KEY = "phase3:" + "d" * 64
ARLES_FILE = f"output/remediation/phase3_runner/runs/mass/batch-0297/evidence/{ARLES}%2Fenwiki.txt"
CISS_PAGE = "https://example.org/cissbury"


def quote(source: str, text: str) -> dict[str, str]:
    return {"source": source, "quote": text}


def verdict(key: str, name: str, right: str | None, quotes: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "change_key": key,
        "verdict": name,
        "right_value": right,
        "reason": f"{name} because",
        "quotes": quotes,
    }


def decision(
    key: str,
    site: str,
    name: str,
    column: str,
    old: str,
    written: str,
    judged: list[tuple[str, dict[str, Any], list[str]]],
    *,
    decided: str = "revert",
    superseded: bool = False,
    counted: bool = True,
) -> dict[str, Any]:
    """One DECISIONS.jsonl line as `opus_audit.decide.decide_row` and `trace` write it; `judged` is
    (pass, verdict, the quote check's outcome per quote), the verdict filed in VERDICTS_RAW.json."""
    proposals = [
        {"pass": p, "value": v["right_value"]} for p, v, _ in judged if v["verdict"] == "wrong-both"
    ]
    values = {x["value"] for x in proposals}
    return {
        "change_key": key,
        "site_id": site,
        "site_name": name,
        "column": column,
        "old_value": old,
        "written_value": written,
        "current_value": written,
        "superseded": superseded,
        "decision": decided,
        "route_decision": decided,
        "basis": [
            {
                "pass": p,
                "verdict": v["verdict"],
                "counted": counted,
                "from": f"VERDICTS_RAW.json {p}",
            }
            for p, v, _ in judged
        ],
        "rejudge": [],
        "pending": [],
        "proposed_value": values.pop() if decided == "revert" and len(values) == 1 else None,
        "proposals": proposals,
        "reversal": decided == "revert" and not superseded,
        "quote_check": {
            p: {
                "counted": counted,
                "reason": "",
                "quotes": [
                    {"source": q["source"], "outcome": outcome, "detail": "as served"}
                    for q, outcome in zip(v["quotes"], outcomes, strict=True)
                ],
            }
            for p, v, outcomes in judged
        },
        "set_aside": [],
    }


ARLES_P1 = verdict(
    ARLES_KEY,
    "wrong-both",
    "Amphitheatre",
    [quote(ARLES_FILE, "is a Roman amphitheatre in Arles, southern France.")],
)
ARLES_P2 = verdict(
    ARLES_KEY, "wrong-both", "Amphitheatre", [quote(ARLES_FILE, "It has an oval arena")]
)
CISS_P1 = verdict(
    CISS_KEY,
    "wrong-both",
    "-3700",
    [quote(CISS_PAGE, "This individual was recently radiocarbon dated to c. 3700 BC.")],
)
CISS_P2 = verdict(CISS_KEY, "revert", None, [quote(CISS_PAGE, "flint mines")])
KEPT_P1 = verdict(KEPT_KEY, "wrong-both", "Temple complex", [quote(ARLES_FILE, "a temple")])
KEPT_P2 = verdict(KEPT_KEY, "keep", None, [quote(ARLES_FILE, "a settlement")])
KEPT_TIE = verdict(KEPT_KEY, "keep", None, [quote(ARLES_FILE, "a settlement")])
PLAIN_KEY = "phase3:" + "e" * 64
PLAIN_P1 = verdict(PLAIN_KEY, "revert", None, [quote(ARLES_FILE, "x")])
PLAIN_P2 = verdict(PLAIN_KEY, "revert", None, [quote(ARLES_FILE, "y")])


def decisions() -> list[dict[str, Any]]:
    return [
        decision(
            ARLES_KEY,
            ARLES,
            "Arles Amphitheatre",
            "site_type",
            "Megalithic structures",
            "Theatre",
            [("p1", ARLES_P1, ["found"]), ("p2", ARLES_P2, ["found"])],
        ),
        decision(
            CISS_KEY,
            CISS,
            "Cissbury Ring",
            "period_start",
            "-1500",
            "-250",
            [("p1", CISS_P1, ["found"]), ("p2", CISS_P2, ["found"])],
        ),
        decision(
            KEPT_KEY,
            KEPT,
            "Wichqana",
            "site_type",
            "City/town/settlement",
            "Archaeological site",
            [
                ("p1", KEPT_P1, ["found"]),
                ("p2", KEPT_P2, ["found"]),
                ("tie", KEPT_TIE, ["found"]),
            ],
            decided="keep",
        ),
        decision(
            PLAIN_KEY,
            ARLES,
            "Arles Amphitheatre",
            "period_start",
            "90",
            "1",
            [("p1", PLAIN_P1, ["found"]), ("p2", PLAIN_P2, ["found"])],
        ),
    ]


def write_audit(directory: Path, lines: list[dict[str, Any]] | None = None) -> Path:
    """An audit directory: DECISIONS.jsonl and the verdict file its basis names."""
    lines = decisions() if lines is None else lines
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "DECISIONS.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8"
    )
    raw: dict[str, dict[str, Any]] = {"p1": {}, "p2": {}, "tie": {}}
    for v in (ARLES_P1, CISS_P1, KEPT_P1, PLAIN_P1):
        raw["p1"][v["change_key"]] = v
    for v in (ARLES_P2, CISS_P2, KEPT_P2, PLAIN_P2):
        raw["p2"][v["change_key"]] = v
    raw["tie"][KEPT_KEY] = KEPT_TIE
    (directory / "VERDICTS_RAW.json").write_text(json.dumps(raw), encoding="utf-8")
    return directory


def candidates(tmp_path: Path) -> dict[str, W.Candidate]:
    return {c.change_key: c for c in W.load_candidates(write_audit(tmp_path / "audit"))}


# ------------------------------------------------------------------------------ production
def link(i: int, stamp: str, old: str | None, new: str | None) -> P.JournalLink:
    return P.JournalLink(i, stamp, "t", old, new)


def site(sid: str, name: str, **over: Any) -> dict[str, Any]:
    base = {
        "id": sid,
        "name": name,
        "source_id": "ancient_nerds",
        "site_type": "Megalithic structures",
        "period_start": "-1500",
        "period_name": "1500 - 500 BC",
        "country": "France",
    }
    base.update(over)
    return base


def state(**over: Any) -> W.State:
    sites = {
        ARLES: site(ARLES, "Arles Amphitheatre", period_start="90", period_name="1 - 500 AD"),
        CISS: site(CISS, "Cissbury Ring", site_type="Fort", country="England"),
        KEPT: site(KEPT, "Wichqana", site_type="Archaeological site", country="Peru"),
    }
    chains = {
        (ARLES, "site_type"): (
            link(28001, "phase3:batch-0297:chunk-0001", "Megalithic structures", "Theatre"),
            link(36105, REV3, "Theatre", "Megalithic structures"),
        ),
        (CISS, "period_start"): (
            link(28002, "phase3:batch-0025:chunk-0001", "-1500", "-250"),
            link(35641, REV3, "-250", "-1500"),
        ),
        (KEPT, "site_type"): (
            link(
                28340, "phase3:batch-0114:chunk-0004", "City/town/settlement", "Archaeological site"
            ),
        ),
    }
    sites.update(over.pop("sites", {}))
    chains.update(over.pop("chains", {}))
    assert not over
    return W.State(sites=sites, chains=chains)


class Pages:
    """The pages the audit fetched, as `opus_audit.quotes.Library.url` reads them."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts

    def url(self, url: str) -> Q.Source:
        if url not in self.texts:
            return Q.Source(failure=Q.NOT_FETCHED, detail="not collected")
        return Q.Source((("visible text", Q.normalise(self.texts[url])),))


CISS_TEXT = (
    "Cissbury Ring is a hillfort. Long before the hill was fortified, flint mines were being "
    "excavated in the area. This individual was recently radiocarbon dated to c. 3700 BC."
)
PAGES = Pages({CISS_PAGE: CISS_TEXT})
FRONTEND = categorize_period
VOCABULARY = W.country_vocabulary()


def decide(
    c: W.Candidate, st: W.State | None = None, pages: Pages = PAGES
) -> tuple[P.Verdict, ...]:
    return W.classify(
        c, state() if st is None else st, library=pages, vocabulary=VOCABULARY, frontend=FRONTEND
    )


def refused(c: W.Candidate, st: W.State | None = None, pages: Pages = PAGES) -> P.Verdict:
    (v,) = decide(c, st, pages)
    assert not v.ok
    return v


# ------------------------------------------------------------------------------ the candidates
class TestTheCandidates:
    def test_every_row_with_a_wrong_both_on_its_route_is_a_candidate_with_its_judges(
        self, tmp_path: Path
    ) -> None:
        got = candidates(tmp_path)
        assert set(got) == {ARLES_KEY, CISS_KEY, KEPT_KEY}, "a row without a wrong-both is none"
        arles = got[ARLES_KEY]
        assert (arles.site_id, arles.name, arles.column) == (
            ARLES,
            "Arles Amphitheatre",
            "site_type",
        )
        assert (arles.old_value, arles.written_value, arles.decision) == (
            "Megalithic structures",
            "Theatre",
            "revert",
        )
        assert [(j.stage, j.origin, j.verdict, j.right_value, j.counted) for j in arles.judges] == [
            ("p1", "VERDICTS_RAW.json p1", "wrong-both", "Amphitheatre", True),
            ("p2", "VERDICTS_RAW.json p2", "wrong-both", "Amphitheatre", True),
        ]
        assert arles.judges[0].quotes == (
            (ARLES_FILE, "is a Roman amphitheatre in Arles, southern France.", "found"),
        )
        assert got[KEPT_KEY].decision == "keep"
        assert [j.stage for j in got[KEPT_KEY].judges] == ["p1", "p2", "tie"]

    def test_missing_decisions_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="is missing"):
            W.load_candidates(tmp_path)

    def test_a_basis_that_did_not_count_is_read_as_one(self, tmp_path: Path) -> None:
        lines = decisions()
        lines[0]["basis"][1]["counted"] = False
        (arles, *_rest) = W.load_candidates(write_audit(tmp_path, lines))
        assert [j.counted for j in arles.judges] == [True, False]

    def test_a_decision_named_twice_is_refused(self, tmp_path: Path) -> None:
        lines = decisions()
        with pytest.raises(P.PlanError, match="twice"):
            W.load_candidates(write_audit(tmp_path, [*lines, lines[0]]))

    def test_a_basis_whose_verdict_file_holds_another_verdict_is_refused(
        self, tmp_path: Path
    ) -> None:
        lines = decisions()
        lines[0]["basis"][1]["verdict"] = "revert"
        with pytest.raises(P.PlanError, match="holds 'wrong-both'"):
            W.load_candidates(write_audit(tmp_path, lines))

    def test_a_quote_check_that_is_not_the_verdicts_own_is_refused(self, tmp_path: Path) -> None:
        lines = decisions()
        lines[0]["quote_check"]["p1"]["quotes"][0]["source"] = "https://example.org/other"
        with pytest.raises(P.PlanError, match="is not that verdict's"):
            W.load_candidates(write_audit(tmp_path, lines))


# ------------------------------------------------------------------------------ the rules
class TestTheRules:
    def test_a_row_whose_judges_agree_and_whose_quote_states_the_value_is_written(
        self, tmp_path: Path
    ) -> None:
        (v,) = decide(candidates(tmp_path)[ARLES_KEY])
        assert v.ok and (v.column, v.old_value, v.new_value) == (
            "site_type",
            "Megalithic structures",
            "Amphitheatre",
        )
        assert v.journal_id == 36105, "the journal-reversal-3 row the correction follows"
        assert v.rule == W.RULE and v.finding_test_id == f"opus:{ARLES_KEY}" and v.phase3
        sources = [e["source"] for e in v.evidence]
        assert sources[0] == "remediation_change_log:36105"
        assert f"opus:{ARLES_KEY}" in sources and ARLES_FILE in sources
        stated = next(e for e in v.evidence if e["source"] == ARLES_FILE)
        assert stated["quote"] == "is a Roman amphitheatre in Arles, southern France."
        rule = next(e for e in v.evidence if e["source"] == W.RULE_SOURCE)
        assert "'amphitheatre'" in rule["quote"] and "evidence file of the row" in rule["quote"]

    def test_a_row_the_audit_kept_is_listed(self, tmp_path: Path) -> None:
        v = refused(candidates(tmp_path)[KEPT_KEY])
        assert v.reason == "not-reverted"
        assert (v.old_value, v.new_value) == ("Archaeological site", "Temple complex")

    def test_a_site_that_is_not_curated_is_listed(self, tmp_path: Path) -> None:
        st = state(sites={ARLES: site(ARLES, "Arles", source_id="pleiades")})
        assert refused(candidates(tmp_path)[ARLES_KEY], st).reason == "row-not-in-curated-source"
        gone = W.State(sites={}, chains=state().chains)
        assert refused(candidates(tmp_path)[ARLES_KEY], gone).reason == "row-not-in-curated-source"

    def test_a_journal_that_does_not_end_at_the_live_value_is_listed(self, tmp_path: Path) -> None:
        st = state(sites={ARLES: site(ARLES, "Arles", site_type="Theatre")})
        assert refused(candidates(tmp_path)[ARLES_KEY], st).reason == "journal-disagrees"

    @pytest.mark.parametrize(
        "last",
        [
            link(30798, "2026-09-22_mechanical-uk-parts", "Theatre", "Megalithic structures"),
            link(36105, REV3, "Bath", "Megalithic structures"),
            link(36105, REV3 + "-rollback", "Theatre", "Megalithic structures"),
        ],
    )
    def test_a_cell_journal_reversal_3_did_not_restore_from_the_judged_write_is_listed(
        self, tmp_path: Path, last: P.JournalLink
    ) -> None:
        first = link(28001, "phase3:x", "Megalithic structures", last.old_value)
        st = state(chains={(ARLES, "site_type"): (first, last)})
        v = refused(candidates(tmp_path)[ARLES_KEY], st)
        assert v.reason == "not-restored-by-journal-reversal-3"

    def test_a_cell_the_journal_holds_nothing_for_is_listed(self, tmp_path: Path) -> None:
        st = state(chains={(ARLES, "site_type"): ()})
        v = refused(candidates(tmp_path)[ARLES_KEY], st)
        assert v.reason == "not-restored-by-journal-reversal-3"

    def test_judges_that_name_two_values_are_listed(self, tmp_path: Path) -> None:
        """A revert judge that names the old value as right disagrees with a wrong-both judge."""
        c = candidates(tmp_path)[CISS_KEY]
        judges = (c.judges[0], W.Judge("p2", "VERDICTS_RAW.json p2", "revert", "-1500", True, ()))
        v = refused(replace(c, judges=judges))
        assert v.reason == "judges-disagree"
        assert "'-3700' (p1)" in v.note and "'-1500' (p2)" in v.note

    def test_a_keep_judge_that_names_the_written_value_disagrees(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        keep = W.Judge("p2", "VERDICTS_RAW.json p2", "keep", "-250", True, ())
        assert refused(replace(c, judges=(c.judges[0], keep))).reason == "judges-disagree"

    def test_only_a_counted_judge_s_value_counts(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        uncounted = W.Judge("tie", "VERDICTS_RAW.json tie", "wrong-both", "-9000", False, ())
        written = decide(replace(c, judges=(*c.judges, uncounted)))
        assert written[0].ok and written[0].new_value == "-3700"

    @pytest.mark.parametrize(
        ("value", "reason"),
        [("-1500", "not-a-change"), ("-250", "proposes-the-reverted-value")],
    )
    def test_a_proposal_of_the_old_or_the_written_value_is_listed(
        self, tmp_path: Path, value: str, reason: str
    ) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        judge = replace(c.judges[0], right_value=value)
        assert refused(replace(c, judges=(judge, c.judges[1]))).reason == reason

    @pytest.mark.parametrize("value", ["Treasury", "amphitheatre", "Amphitheater"])
    def test_a_site_type_that_is_not_a_canonical_fixed_point_is_listed(
        self, tmp_path: Path, value: str
    ) -> None:
        c = candidates(tmp_path)[ARLES_KEY]
        judges = tuple(replace(j, right_value=value) for j in c.judges)
        assert refused(replace(c, judges=judges)).reason == "not-a-site-type"

    @pytest.mark.parametrize("value", ["-3700 BC", "-03700", "c. -3700", "-3700.0"])
    def test_a_period_start_that_is_not_an_integer_year_is_listed(
        self, tmp_path: Path, value: str
    ) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        judge = replace(c.judges[0], right_value=value)
        assert refused(replace(c, judges=(judge, c.judges[1]))).reason == "not-an-integer-year"

    def test_the_bucket_rules_must_agree(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        (v,) = W.classify(
            c, state(), library=PAGES, vocabulary=VOCABULARY, frontend=lambda _y: "1500+ AD"
        )
        assert not v.ok and v.reason == "bucket-rules-disagree"

    def test_no_quote_that_states_the_value_lists_the_row(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        silent = replace(c.judges[0], quotes=((CISS_PAGE, "flint mines", "found"),))
        v = refused(replace(c, judges=(silent, c.judges[1])))
        assert v.reason == "no-verbatim-evidence" and "no counted quote states" in v.note

    def test_a_quote_the_check_did_not_find_is_no_evidence(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[ARLES_KEY]
        judges = tuple(
            replace(j, quotes=tuple((s, t, "not found") for s, t, _ in j.quotes)) for j in c.judges
        )
        assert refused(replace(c, judges=judges)).reason == "no-verbatim-evidence"

    def test_a_quote_of_a_judge_that_does_not_count_is_no_evidence(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[ARLES_KEY]
        judges = (replace(c.judges[0], counted=False), c.judges[1])
        v = refused(replace(c, judges=judges))
        assert v.reason == "no-verbatim-evidence"

    def test_a_page_quote_that_stands_far_from_the_site_s_name_is_no_evidence(
        self, tmp_path: Path
    ) -> None:
        far = Pages({CISS_PAGE: "Cissbury Ring. " + "x " * 1000 + CISS_TEXT.split(". ", 2)[2]})
        v = refused(candidates(tmp_path)[CISS_KEY], pages=far)
        assert v.reason == "no-verbatim-evidence" and "about the site" in v.note

    def test_a_page_quote_near_the_site_s_name_is_evidence(self, tmp_path: Path) -> None:
        written = decide(candidates(tmp_path)[CISS_KEY])
        start = written[0]
        assert start.ok and start.new_value == "-3700"
        rule = next(e for e in start.evidence if e["source"] == W.RULE_SOURCE)
        assert "'3700 BC'" in rule["quote"] and "'cissbury'" in rule["quote"]

    def test_a_page_the_audit_found_the_quote_on_must_still_hold_it(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="no longer"):
            decide(candidates(tmp_path)[CISS_KEY], pages=Pages({CISS_PAGE: "Cissbury Ring."}))
        with pytest.raises(P.PlanError, match="cannot be read"):
            decide(candidates(tmp_path)[CISS_KEY], pages=Pages({}))

    def test_a_start_that_changes_bucket_writes_its_label_with_it(self, tmp_path: Path) -> None:
        start, label = decide(candidates(tmp_path)[CISS_KEY])
        assert (label.column, label.old_value, label.new_value) == (
            "period_name",
            "1500 - 500 BC",
            "4500 - 3000 BC",
        )
        assert label.ok and label.rule == W.LABEL_RULE and label.journal_id is None
        assert categorize_period(int(str(start.new_value))) == label.new_value
        assert any("categorize_period(-3700)" in e["quote"] for e in label.evidence)

    def test_a_start_within_its_label_s_bucket_writes_no_label(self, tmp_path: Path) -> None:
        c = candidates(tmp_path)[CISS_KEY]
        judge = replace(c.judges[0], right_value="-1400")
        text = CISS_TEXT.replace("c. 3700 BC", "c. 1400 BC")
        got = decide(replace(c, judges=(judge, c.judges[1])), pages=Pages({CISS_PAGE: text}))
        assert [v.column for v in got] == ["period_start"]

    def test_a_label_the_row_holds_none_of_is_listed(self, tmp_path: Path) -> None:
        st = state(sites={CISS: site(CISS, "Cissbury Ring", period_name=None)})
        assert refused(candidates(tmp_path)[CISS_KEY], st).reason == "period-name-empty"

    def test_a_label_whose_journal_does_not_end_at_it_is_listed(self, tmp_path: Path) -> None:
        stray = (link(30336, "2026-09-22_mechanical-period-name", "500 BC - 1 AD", "1 - 500 AD"),)
        st = state(chains={(CISS, "period_name"): stray})
        v = refused(candidates(tmp_path)[CISS_KEY], st)
        assert v.reason == "period-name-journal-disagrees"


class TestTheCountryConvention:
    @pytest.mark.parametrize("value", ["Northern Ireland", "Afghanistan", "Peru"])
    def test_a_country_of_the_convention_passes(self, value: str) -> None:
        assert W.country_problem(value, VOCABULARY) is None

    @pytest.mark.parametrize(
        "value", ["United Kingdom", "UK", "Great Britain", "Atlantis", "Georgia (country)", "Guam"]
    )
    def test_a_country_outside_the_convention_is_named(self, value: str) -> None:
        assert W.country_problem(value, VOCABULARY)

    def test_a_country_row_outside_the_convention_is_listed(self, tmp_path: Path) -> None:
        text = "Annadorn Dolmen is a portal tomb in County Down, United Kingdom."
        p1 = verdict(ANNA_KEY, "wrong-both", "United Kingdom", [quote(CISS_PAGE, text)])
        p2 = verdict(ANNA_KEY, "wrong-both", "United Kingdom", [quote(CISS_PAGE, text)])
        c = W.Candidate(
            change_key=ANNA_KEY,
            site_id=ANNA,
            name="Annadorn Dolmen",
            column="country",
            old_value="Ireland",
            written_value="England",
            decision="revert",
            judges=tuple(
                W.Judge(
                    p,
                    f"VERDICTS_RAW.json {p}",
                    v["verdict"],
                    v["right_value"],
                    True,
                    ((CISS_PAGE, text, "found"),),
                )
                for p, v in (("p1", p1), ("p2", p2))
            ),
        )
        chain = (link(1, "phase3:x", "Ireland", "England"), link(2, REV3, "England", "Ireland"))
        st = state(
            sites={ANNA: site(ANNA, "Annadorn Dolmen", country="Ireland")},
            chains={(ANNA, "country"): chain},
        )
        v = refused(c, st, Pages({CISS_PAGE: text}))
        assert v.reason == "not-the-country-convention"
        # audit 2026-09-25 m10: the last branch took any other column for the country
        named = replace(c, column="name")
        st = state(
            sites={ANNA: site(ANNA, "Ireland")},
            chains={(ANNA, "name"): chain},
        )
        with pytest.raises(P.PlanError, match="not a column"):
            decide(named, st, Pages({CISS_PAGE: text}))


# ------------------------------------------------------------------------------ the statements
class TestWhatAQuoteStates:
    @pytest.mark.parametrize(
        ("value", "text", "term"),
        [
            ("Amphitheatre", "is a Roman amphitheatre in Arles", "amphitheatre"),
            ("Amphitheatre", "the Roman amphitheater of Nimes", "amphitheater"),
            ("Monument", "The statue was made by the sculptor Theopropus", "statue"),
            ("Fort", "formerly a hillfort, in Dorset", "hillfort"),
            ("Fort", "an Iron Age promontory fort.", "fort"),
            ("Religious", "the first religious structure made entirely out of marble", "religious"),
            (
                "Archaeological site",
                "obtained from an archaeological site at",
                "archaeological site",
            ),
            ("Barrow", "had a large barrow with a circle", "barrow"),
            ("Fortress/citadel", "a Fortress/citadel above the river", "Fortress/citadel"),
        ],
    )
    def test_a_term_the_normalizer_resolves_to_the_type_states_it(
        self, value: str, text: str, term: str
    ) -> None:
        assert W.states("site_type", value, text) == term

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            ("Fort", "Long before the hill was fortified"),
            ("Religious", "sacred building at Delphi"),
            ("Monument", "a key memorial of Athens' ancestral valour"),
            ("Archaeological site", "an archaeological area"),
            ("Sacred site", "the seasonal social and religious centre of a tribe"),
        ],
    )
    def test_a_quote_without_such_a_term_does_not(self, value: str, text: str) -> None:
        assert W.states("site_type", value, text) is None

    @pytest.mark.parametrize(
        ("value", "text", "stated"),
        [
            (-3700, "recently radiocarbon dated to c. 3700 BC.", "3700 BC"),
            (-2500, "spanned from c. 2500–2200 BC until c. 800 BC.", "2500–2200 BC"),
            (-1750, "from c. 2000/1750–500 BC.", "1750–500 BC"),
            (-200, "poblado desde el año 200 a.C. y alcanzó", "200 a.C."),
            (-200, "Cronología: 200 a. C. a 1000 d. C.", "200 a. C."),
            (1000, "Cronología: 200 a. C. a 1000 d. C.", "1000 d. C."),
            (-1500, "fishing village (1500–1200 B.C.E.) located", "1500–1200 B.C.E."),
            (-4000, "inhabited between 4000 and 1700 BCE", "4000 and 1700 BCE"),
            (-35000, "an occupation of 35,000 BC", "35,000 BC"),
            (-50, "occupied from about 50 BC, with", "50 BC"),
            (200, "The city existed from 200 to 1000 AD.", "200 to 1000 AD"),
            (900, "rebuilt in AD 900 by", "AD 900"),
            (900, "rebuilt in AD 900.", "AD 900"),
            (1500, "rebuilt in AD 1,500, then", "AD 1,500"),
            (900, "rebuilt in 900 CE by", "900 CE"),
            (-6000, "zwischen dem 6000 v. Chr. und", "6000 v. Chr."),
            (-400, "fondée vers 400 av. J.-C.", "400 av. J.-C."),
        ],
    )
    def test_a_year_with_its_era_states_it(self, value: int, text: str, stated: str) -> None:
        assert W.states("period_start", str(value), text) == stated

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            (900, "pottery and faunal remains dating to 900"),
            (-500, "the oldest from Apollonia Pontica from the 5th century BC"),
            (-33000, "early human occupation (about 35,000 years ago)"),
            (-700, "a hearth of 13700 BC"),
            (-700, "a hearth of 1.700 BC"),
            (-200, "The city existed from 200 to 1000 AD."),
            (50, "occupied from about 50 BC, with"),
            (-3700, "about 3700 years old"),
            (-500, "the middle years of the first millennium BC"),
            (0, "0 BC"),
            (0, "AD 0"),
            (-1500, "1500 CENTURY"),
            (1500, "1500 CENTURY"),
            (900, "BAD 900"),
            (900, "rebuilt in AD 800"),
            (-35, "35,000 BC"),
            # audit 2026-09-25 M7: the prefix form needs a right boundary too
            (5, "founded in the AD 5th century"),
            (90, "abandoned in the AD 90s"),
            (1, "an estimated AD 1.500 inhabitants"),
            (900, "dated AD 900.5"),
            (900, "AD 9001"),
        ],
    )
    def test_a_year_without_its_era_or_in_another_does_not(self, value: int, text: str) -> None:
        assert W.states("period_start", str(value), text) is None

    def test_no_synonym_is_longer_than_the_longest_canonical_type(self) -> None:
        from pipeline.normalizers.site_type import _SYNONYMS, normalize_site_type

        longest = max(len(W._WORD.findall(k.replace("_", " "))) for k in _SYNONYMS)
        assert longest <= W.MAX_TERM_WORDS
        assert all(normalize_site_type(t) == t for t in W.CANONICAL_TYPES)

    def test_a_column_the_lane_does_not_correct_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="not a column"):
            W.states("name", "Stonehenge", "Stonehenge")

    def test_a_country_is_stated_by_its_name_standing_whole(self) -> None:
        assert (
            W.states("country", "Northern Ireland", "in County Down, Northern Ireland.")
            == "Northern Ireland"
        )
        assert W.states("country", "Ireland", "in County Down, Northern Ireland.") is None
        assert W.states("country", "Ireland", "a dolmen in Ireland.") == "Ireland"
        assert W.states("country", "Oman", "the Romans came") is None
        assert W.states("country", "Iran", "the Iranian plateau") is None


# ------------------------------------------------------------------------------ the list and the plan
class Production:
    """Answers the two statements `read_state` sends, and refuses any other."""

    def __init__(self, st: W.State) -> None:
        self.state = st
        self.sent: list[str] = []

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        self.sent.append(sql)
        if sql.startswith("SELECT id::text AS id, name, source_id"):
            assert f"'{ARLES}'" in sql and f"'{CISS}'" in sql and f"'{KEPT}'" in sql
            return list(self.state.sites.values())
        if sql.startswith("SELECT id, row_pk, column_name, run_stamp"):
            assert "column_name IN ('country', 'period_name', 'period_start', 'site_type')" in sql
            assert sql.endswith("ORDER BY id")
            return [
                {
                    "id": x.id,
                    "row_pk": sid,
                    "column_name": column,
                    "run_stamp": x.run_stamp,
                    "test_id": x.test_id,
                    "old_value": x.old_value,
                    "new_value": x.new_value,
                }
                for (sid, column), links in self.state.chains.items()
                for x in links
            ]
        raise AssertionError(f"unexpected statement: {sql[:80]!r}")


def test_the_readers_ask_for_exactly_the_rows_they_need(tmp_path: Path) -> None:
    production = Production(state())
    got = W.read_state(production, list(candidates(tmp_path).values()))
    assert got == state()
    assert len(production.sent) == 2


def test_the_plan_writes_the_corrections_and_lists_the_rest(tmp_path: Path) -> None:
    plan = W.build(
        list(candidates(tmp_path).values()),
        state(),
        library=PAGES,
        vocabulary=VOCABULARY,
        frontend=FRONTEND,
        built_at="2026-09-25T00:00:00+00:00",
    )
    assert plan.lane is L.WRONG_BOTH
    assert [(v.site_id, v.column) for v in plan.changes] == [
        (ARLES, "site_type"),
        (CISS, "period_start"),
        (CISS, "period_name"),
    ]
    assert [(v.site_id, v.reason) for v in plan.skipped] == [(KEPT, "not-reverted")]
    assert W.followed_rows(plan) == (35641, 36105)
    assert plan.counters == {"candidates": 3, "corrections": 2, "labels": 1, "listed": 1}


def test_the_list_module_is_generated_code_that_holds_exactly_the_ids() -> None:
    text = W.render_list_module((35641, 36105), "f" * 64)
    namespace: dict[str, Any] = {}
    exec(compile(ast.parse(text), "wrong_both_list.py", "exec"), namespace)  # noqa: S102
    assert namespace["JOURNAL_IDS"] == (35641, 36105)
    assert "f" * 64 in text and "do not edit by hand" in text
    assert all(len(row) <= 100 for row in text.splitlines())


def run_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str, st: W.State | None = None
) -> int:
    audit = write_audit(tmp_path / "audit")
    monkeypatch.setattr(W, "psql_json_reader", lambda: Production(state() if st is None else st))
    monkeypatch.setattr(W, "open_library", lambda _audit: PAGES)
    argv = [flag, "--audit", str(audit), "--out", str(tmp_path / "out")]
    return W.main([*argv, "--module", str(tmp_path / "wrong_both_list.py")])


def test_list_writes_the_journal_rows_the_corrections_follow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_main(tmp_path, monkeypatch, "--list") == 0
    text = (tmp_path / "wrong_both_list.py").read_text(encoding="utf-8")
    assert "35641, 36105," in text
    digest = W.sha256_file(tmp_path / "audit" / "DECISIONS.jsonl")
    assert digest in text


def test_write_refuses_a_plan_that_is_not_the_lane_s_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(W, "listed_rows", lambda: (35641,))
    assert run_main(tmp_path, monkeypatch, "--write") == 1
    assert "run --list" in capsys.readouterr().err
    assert not (tmp_path / "out" / "PLAN.jsonl").exists()


def test_list_and_write_in_one_run_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse() -> Any:
        raise AssertionError("production was read")

    monkeypatch.setattr(W, "psql_json_reader", refuse)
    with pytest.raises(SystemExit) as info:
        W.main(["--list", "--write", "--out", str(tmp_path)])
    assert info.value.code == 2


def test_no_flag_reads_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> Any:
        raise AssertionError("production was read")

    monkeypatch.setattr(W, "psql_json_reader", refuse)
    assert W.main(["--out", str(tmp_path)]) == 0
    assert not list(tmp_path.iterdir())


def test_write_plans_the_lane_s_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(W, "listed_rows", lambda: (35641, 36105))
    assert run_main(tmp_path, monkeypatch, "--write") == 0
    out = tmp_path / "out"
    records = A.load_records(out / "PLAN.jsonl")
    A.validate_records(records, lane=L.WRONG_BOTH)
    assert [(r.site_id, r.column, r.new_value) for r in records] == [
        (ARLES, "site_type", "Amphitheatre"),
        (CISS, "period_start", "-3700"),
        (CISS, "period_name", "4500 - 3000 BC"),
    ]
    P.verify_pinned(
        out / "ROLLBACK.sql",
        plan_path=out / "PLAN.jsonl",
        expected=A.rollback_statement(records, L.WRONG_BOTH),
    )
    skipped = [json.loads(x) for x in (out / "SKIPPED.jsonl").read_text("utf-8").splitlines()]
    assert [(s["site_name"], s["reason"]) for s in skipped] == [("Wichqana", "not-reverted")]
    md = (out / "PLAN.md").read_text(encoding="utf-8")
    assert "3 cell(s) will be written" in md and "`not-reverted`" in md
    assert W.sha256_file(tmp_path / "audit" / "DECISIONS.jsonl") in md


# ------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_the_lane_owns_four_cells_and_reverses_no_journal_row(self) -> None:
        lane = L.WRONG_BOTH
        assert L.LANES[lane.name] is lane and lane.name in L.LANE_READBACKS
        assert lane.columns == ("site_type", "period_start", "period_name", "country")
        assert lane.cell("site_type").allowed_new_values == tuple(W.CANONICAL_TYPES)
        assert lane.cell("period_name").allowed_new_values == tuple(b[0] for b in PERIOD_BUCKETS)
        assert lane.cell("period_start").sql_type == "integer"
        assert not lane.reverses_journal and lane.premise_sql is None
        assert (lane.run_stamp, lane.test_id, lane.key_prefix) == (
            "2026-09-25_mechanical-wrong-both",
            "P6/wrong-both",
            "wrong-both",
        )
        stamps = [other.run_stamp for other in L.LANES.values()]
        assert stamps.count(lane.run_stamp) == 1

    def test_the_residual_is_the_restored_values_the_list_names(self) -> None:
        residual = L.WRONG_BOTH.post_commit_residual
        assert residual == L.WRONG_BOTH.rehearsal_residual
        listed = ", ".join(str(i) for i in L.WRONG_BOTH_JOURNAL_IDS)
        assert f"l.id IN ({listed})" in residual.predicate
        assert "restored value" in residual.metric
        readback = L.LANE_READBACKS[L.WRONG_BOTH.name]
        assert residual.metric in readback and "a later write superseded" in readback
        assert "period_name is not the bucket" in readback


# ------------------------------------------------------------------------------ the delivered plan
DELIVERED = A.lane_dir(L.WRONG_BOTH)


def test_the_delivered_plan_follows_exactly_the_lane_s_list() -> None:
    records = A.load_records(DELIVERED / "PLAN.jsonl")
    followed = sorted(
        int(e["source"].partition(":")[2])
        for r in records
        if r.column != "period_name"
        for e in r.evidence
        if e["source"].startswith("remediation_change_log:")
    )
    assert tuple(followed) == L.WRONG_BOTH_JOURNAL_IDS
    starts = {r.site_id: r for r in records if r.column == "period_start"}
    for r in records:
        if r.column == "period_name":
            assert r.new_value == categorize_period(int(str(starts[r.site_id].new_value)))


def test_every_delivered_correction_quotes_what_the_audit_found() -> None:
    """Offline: each written value's quote is a found quote of a counted verdict on its row's route,
    and each row is a final revert whose judges named that value and no other."""
    by_key = {c.change_key: c for c in W.load_candidates(W.OPUS_AUDIT)}
    for r in A.load_records(DELIVERED / "PLAN.jsonl"):
        if r.column == "period_name":
            continue
        (key,) = [e["source"][5:] for e in r.evidence if e["source"].startswith("opus:")]
        c = by_key[key]
        assert c.decision == "revert" and c.site_id == r.site_id and c.column == r.column
        named = {j.right_value for j in c.judges if j.counted and j.right_value}
        assert named == {r.new_value}
        found = {(s, t) for j in c.judges if j.counted for s, t, o in j.quotes if o == "found"}
        quoted = [
            (e["source"], e["quote"]) for e in r.evidence if (e["source"], e["quote"]) in found
        ]
        assert quoted, r.site_name
