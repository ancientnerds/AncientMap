"""Phase 6 acceptance, sections 5-7 of the sealed protocol: the fields, the values, the questions.

`scripts/remediation/acceptance/questions.py` builds every question a judge is shown. The protocol
(`output/remediation/acceptance/PROTOCOL.md`) fixes what a prompt may carry - the site's identity,
the field's served value, the field's row of section 5 and the plan's false-alarm patterns - and
that no judge answers two questions of one site. Offline: nothing here reads production.
The mutation cases are `acceptance judge: ...` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from acceptance import draw as D  # noqa: E402
from acceptance import questions as QN  # noqa: E402

from pipeline.normalizers.site_type import CANONICAL_TYPES  # noqa: E402

SAMPLE = REPO / "output" / "remediation" / "acceptance" / "draw-2026-09-25" / "SAMPLE.jsonl"


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def site(n: int = 1, **over: Any) -> dict[str, Any]:
    """A drawn site as SAMPLE.jsonl carries it: every column the draw's value read returns."""
    row: dict[str, Any] = {
        "site_id": _uuid(n),
        "name": f"Temple of Nowhere {n}",
        "name_normalized": f"temple of nowhere {n}",
        "country": "Peru",
        "lat": -13.51588021866,
        "lon": -71.97633563130212,
        "site_type": "Temple",
        "period_start": -500,
        "period_end": None,
        "period_name": "500 BC - 1 AD",
        "description": "The temple stands on a hill.[1] It was built c. 400 BC by the Inca.[1]",
        "description_citations": [
            {"n": 1, "url": "https://en.wikipedia.org/wiki/SECRET_CITATION", "title": "t"}
        ],
        "description_provenance": {"desc_sha256": "PROVENANCE_DIGEST", "lane": "W"},
        "source_url": "https://en.wikipedia.org/wiki/Temple_of_Nowhere",
        "thumbnail_url": "/data/images/wiki/x/hero.webp",
        "scope_status": None,
        "scope_reason": None,
        "card_description": "A hilltop temple built by the Inca.",
        "civilization": "Peru",
        "served_image": {
            "id": 7,
            "filename": "hero.webp",
            "title": "Temple of Nowhere, east face",
            "commons_page_url": "https://commons.wikimedia.org/wiki/File:Nowhere.jpg",
            "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Nowhere.jpg",
            "author": "SECRET_AUTHOR",
            "license": "CC BY-SA 4.0",
        },
    }
    row.update(over)
    return row


def _by(questions: list[QN.Question], field: str) -> list[QN.Question]:
    return [q for q in questions if q.field == field]


# ------------------------------------------------------------------------------ the sealed texts
def test_the_protocol_rows_are_the_sealed_table_of_eleven_fields() -> None:
    seal = json.loads((QN.ACCEPTANCE / "SEAL.json").read_text(encoding="utf-8"))
    assert seal["sha256"]["output/remediation/acceptance/PROTOCOL.md"] == QN.PROTOCOL_SHA256
    rows = QN.read_protocol()
    assert list(rows) == [f.number for f in QN.FIELDS] == [f"F{i}" for i in range(1, 12)]
    for field in QN.FIELDS:
        assert rows[field.number].title == field.title
    assert rows["F3"].right.startswith("the point lies on the site, within 1 km")
    assert rows["F11"].wrong == "moderate"


def test_a_protocol_that_is_not_the_sealed_one_is_refused(tmp_path: Path) -> None:
    changed = QN.PROTOCOL.read_text(encoding="utf-8").replace("0 confirmed severe", "1 confirmed")
    path = tmp_path / "PROTOCOL.md"
    path.write_text(changed, encoding="utf-8")
    with pytest.raises(QN.QuestionError, match="sealed"):
        QN.read_protocol(path)


def test_each_field_s_severities_are_the_ones_its_row_names() -> None:
    rows = QN.read_protocol()
    for field in QN.FIELDS:
        named = {s for s in QN.SEVERITIES if s in rows[field.number].wrong}
        assert named == set(field.severities), field.number


def test_the_false_alarm_patterns_are_the_plan_s_eleven_verbatim() -> None:
    patterns = QN.read_patterns()
    plan = QN.PLAN.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert patterns in plan
    assert re.findall(r"^(\d+)\. ", patterns, re.M) == [str(i) for i in range(1, 12)]
    assert patterns.startswith("1. **Bucket boundary values.**")
    assert "11. **Natural Earth draws de-facto borders" in patterns


def test_patterns_that_changed_are_refused(tmp_path: Path) -> None:
    plan = QN.PLAN.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    path = tmp_path / "plan.md"
    path.write_text(plan.replace("is deliberate project design", "is fine"), encoding="utf-8")
    with pytest.raises(QN.QuestionError, match="false-alarm"):
        QN.read_patterns(path)


# --------------------------------------------------------------------------------- the values
def test_a_point_is_six_decimals_without_trailing_zeros() -> None:
    assert QN.coord(51.17888234) == "51.178882"
    assert QN.coord(10.0) == "10"
    assert QN.coord(-0.0000001) == "0"
    assert QN.coord(-71.97633563130212) == "-71.976336"
    assert QN.point(-13.51588021866, -71.97633563130212) == "-13.51588, -71.976336"


def test_a_coordinate_canary_looks_exactly_like_a_real_point() -> None:
    """The draw's canary value is `round(lat +- 5, 6),lon`: formatted, its form is a real point's."""
    lat, lon = 51.17888234567, -1.826215432109
    moved = D.shifted_point(lat, lon)
    value = QN.canary_point(f"{moved[0]},{moved[1]}")
    real = QN.point(lat, lon)
    shape = re.compile(r"-?\d+(\.\d{1,6})?, -?\d+(\.\d{1,6})?")
    assert shape.fullmatch(value) and shape.fullmatch(real)
    assert value == "56.178882, -1.826215" and real == "51.178882, -1.826215"


def test_empty_fields_are_not_asked_and_scope_always_is() -> None:
    bare = site(card_description=None, served_image=None, lat=None, source_url="  ")
    asked = {q.field for q in QN.stage1_questions([bare], [])}
    assert asked == {
        "name", "country", "site_type", "period_start", "period_name", "description", "scope",
    }  # fmt: skip
    assert QN.served_value("scope", bare).startswith("shown on the public map")


def test_the_served_values_are_the_frozen_ones() -> None:
    row = site()
    assert QN.served_value("coordinates", row) == "-13.51588, -71.976336"
    assert QN.served_value("period_start", row) == "-500"
    assert QN.served_value("period_name", row) == "500 BC - 1 AD"
    image = QN.served_value("served_image", row)
    assert "Temple of Nowhere, east face" in image
    assert "https://commons.wikimedia.org/wiki/File:Nowhere.jpg" in image
    assert "SECRET_AUTHOR" not in image


def test_a_retired_site_or_a_non_integer_year_is_refused() -> None:
    with pytest.raises(QN.QuestionError, match="retired"):
        QN.served_value("scope", site(scope_status="retired"))
    with pytest.raises(QN.QuestionError, match="integer"):
        QN.served_value("period_start", site(period_start=-500.5))


def test_every_non_empty_field_is_one_question_under_an_opaque_label() -> None:
    questions = QN.stage1_questions([site(1), site(2)], [])
    assert len(questions) == 22
    labels = [q.label for q in questions]
    assert len(set(labels)) == 22
    for q in questions:
        assert re.fullmatch(r"q[0-9a-f]{16}", q.label)
        assert q.label == QN.label_of(q.site_id, q.field, q.value)
    assert labels == sorted(labels)  # the file order says nothing about site or field


def test_a_canary_replaces_its_value_and_the_real_value_is_asked_in_an_extra_question() -> None:
    target, other = site(1), site(2)
    canaries = [
        {"site_id": target["site_id"], "field": "country", "canary_value": "Japan",
         "true_stored": "Peru", "why_wrong": "far away"},
        {"site_id": other["site_id"], "field": "coordinates", "canary_value": "-8.515880,-71.97633563130212",
         "true_stored": f"{other['lat']},{other['lon']}", "why_wrong": "moved"},
    ]  # fmt: skip
    questions = QN.stage1_questions([target, other], canaries)
    assert len(questions) == 24
    countries = [q for q in _by(questions, "country") if q.site_id == target["site_id"]]
    assert sorted(q.value for q in countries) == ["Japan", "Peru"]
    for q in countries:
        assert q.country == q.value  # the identity carries the question's own value
    points = [q for q in _by(questions, "coordinates") if q.site_id == other["site_id"]]
    assert sorted(q.value for q in points) == ["-13.51588, -71.976336", "-8.51588, -71.976336"]
    for q in points:
        assert q.point == q.value
    assert {q.country for q in questions if q.field != "country"} == {"Peru"}
    fields = {f.name for f in QN.Question.__dataclass_fields__.values()}
    assert fields == {"label", "site_id", "field", "value", "name", "country", "point"}


def test_a_canary_that_does_not_fit_the_sample_is_refused() -> None:
    row = site(1)
    wrong_stored = {"site_id": row["site_id"], "field": "country", "canary_value": "Japan",
                    "true_stored": "Chile", "why_wrong": "x"}  # fmt: skip
    with pytest.raises(QN.QuestionError, match="stored"):
        QN.stage1_questions([row], [wrong_stored])
    stranger = dict(wrong_stored, site_id=_uuid(99), true_stored="Peru")
    with pytest.raises(QN.QuestionError, match="not a drawn site"):
        QN.stage1_questions([row], [stranger])
    other_field = dict(wrong_stored, field="name", true_stored="Peru")
    with pytest.raises(QN.QuestionError, match="field"):
        QN.stage1_questions([row], [other_field])


def test_the_frozen_draw_asks_643_real_questions() -> None:
    """660 minus the empty fields: 3 sites without a card text, 14 without a served image."""
    sample = [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines()]
    questions = QN.stage1_questions(sample, [])
    assert len(questions) == 643
    counts = {f.key: len(_by(questions, f.key)) for f in QN.FIELDS}
    assert counts["card_description"] == 57 and counts["served_image"] == 46
    assert {k: v for k, v in counts.items() if v != 60} == {
        "card_description": 57, "served_image": 46,
    }  # fmt: skip


# -------------------------------------------------------------------------------- the batches
def _twins() -> list[QN.Question]:
    sample = [site(n, lat=-13.0 - n / 10) for n in range(1, 41)]
    canaries = [
        {"site_id": sample[n]["site_id"], "field": "country", "canary_value": "Japan",
         "true_stored": "Peru", "why_wrong": "x"}
        for n in (0, 1, 2, 39)
    ]  # fmt: skip
    return QN.stage1_questions(sample, canaries)


def test_no_batch_holds_two_questions_of_one_site() -> None:
    questions = _twins()
    batches = QN.batches(questions, "s1r0")
    seen: list[str] = []
    for batch_id, group in batches:
        assert len({q.site_id for q in group}) == len(group), batch_id
        assert len({q.field for q in group}) == 1, batch_id
        field = QN.FIELD_BY_KEY[group[0].field]
        assert len(group) <= field.batch_size, batch_id
        seen += [q.label for q in group]
    assert sorted(seen) == sorted(q.label for q in questions)  # each question once


def test_a_field_with_twins_gets_as_many_batches_as_its_most_asked_site() -> None:
    row = site(1)
    canary = {"site_id": row["site_id"], "field": "country", "canary_value": "Japan",
              "true_stored": "Peru", "why_wrong": "x"}  # fmt: skip
    batches = QN.batches(QN.stage1_questions([row], [canary]), "s1r0")
    country = [group for batch_id, group in batches if "-country-" in batch_id]
    assert [len(group) for group in country] == [1, 1]


def test_twins_are_split_whatever_their_labels() -> None:
    """Round-robin over the site order: a site's two questions are neighbours, never one batch
    apart - here their labels are two apart, which a label order would put into one batch."""
    twin = [QN.Question(f"q{n:016x}", _uuid(0), "country", v, "T", v, "1, 2")
            for n, v in ((0, "Peru"), (2, "Japan"))]  # fmt: skip
    others = [QN.Question(f"q{n:016x}", _uuid(n), "country", "Peru", "T", "Peru", "1, 2")
              for n in (1, *range(3, 17))]  # fmt: skip
    groups = [group for _, group in QN.batches(twin + others, "s1r0")]
    assert len(groups) == 2
    for group in groups:
        assert len({q.site_id for q in group}) == len(group)


def test_batch_ids_are_plain_names_of_stage_round_field_and_number() -> None:
    batches = QN.batches(_twins(), "s1r0")
    ids = [batch_id for batch_id, _ in batches]
    assert "s1r0-country-01" in ids and "s1r0-description-01" in ids
    for batch_id in ids:
        assert re.fullmatch(r"s1r0-[a-z_]+-\d\d", batch_id)
    sizes = {f.key: f.batch_size for f in QN.FIELDS}
    assert sizes["description"] < sizes["name"] and sizes["card_description"] < sizes["name"]


# -------------------------------------------------------------------------------- the prompts
def _prompt(field: str, row: dict[str, Any] | None = None) -> tuple[QN.Question, str]:
    (question,) = _by(QN.stage1_questions([row or site()], []), field)
    return question, QN.stage1_prompt(question, QN.read_protocol(), QN.read_patterns())


def test_the_stage1_prompt_shows_the_identity_the_value_the_row_and_the_patterns() -> None:
    question, prompt = _prompt("coordinates")
    rows = QN.read_protocol()
    for shown in ("Temple of Nowhere 1", "Peru", "-13.51588, -71.976336", rows["F3"].right,
                  rows["F3"].wrong, QN.read_patterns(), "F3 coordinates"):  # fmt: skip
        assert shown in prompt, shown
    assert '"verdict"' in prompt and "UNVERIFIABLE" in prompt


def test_the_stage1_prompt_shows_nothing_else() -> None:
    """Never shown: the journal, remediation evidence, provenance, citations, another field."""
    row = site(site_type="Pyramid complex", period_start=-1234, period_name="1500 - 500 BC")
    for field in ("name", "country", "coordinates", "scope", "source_url"):
        _, prompt = _prompt(field, row)
        for hidden in ("SECRET_CITATION", "PROVENANCE_DIGEST", "SECRET_AUTHOR", _uuid(1),
                       "It was built c. 400 BC", "A hilltop temple", "hero.webp", "Nowhere.jpg",
                       "Pyramid complex", "-1234", "1500 - 500 BC", "journal", "canary",
                       "remediation"):  # fmt: skip
            assert hidden not in prompt, (field, hidden)


def test_the_research_rules_name_the_source_families_and_the_machine_quote_check() -> None:
    _, prompt = _prompt("name")
    assert "Wikidata item" in prompt and "ONE source family" in prompt
    assert "verbatim" in prompt and "does not count" in prompt
    assert "web" in prompt.lower()


def test_the_text_fields_ask_for_every_claim_with_its_quote() -> None:
    _, text = _prompt("description")
    assert "every sentence" in text and "copied exactly from the served text" in text
    _, card = _prompt("card_description")
    assert "every sentence" in card
    _, name = _prompt("name")
    assert '"claim": null' in name and "every sentence" not in name


def test_the_typed_fields_show_their_vocabulary() -> None:
    _, types = _prompt("site_type")
    assert all(t in types for t in CANONICAL_TYPES)
    _, start = _prompt("period_start")
    assert "`1 - 500 AD`" in start and "negative" in start
    _, bucket = _prompt("period_name")
    assert "`< 4500 BC`" in bucket and "`1500+ AD`" in bucket
    _, name = _prompt("name")
    assert "`1 - 500 AD`" not in name and "Megalithic stones" not in name


def test_each_field_names_only_its_own_severities() -> None:
    for field in QN.FIELDS:
        row = site()
        (question,) = _by(QN.stage1_questions([row], []), field.key)
        prompt = QN.stage1_prompt(question, QN.read_protocol(), QN.read_patterns())
        allowed = re.search(r'"severity": one of ([^.]+)\.', prompt)
        assert allowed is not None, field.key
        assert set(re.findall(r'"(\w+)"', allowed.group(1))) == set(field.severities)


# ------------------------------------------------------------------------ stages 2 and 3
def _claim() -> QN.Claim:
    return QN.Claim(right_value="Bolivia", severity="severe", disputed=())


def test_the_stage2_prompt_shows_the_claim_and_not_stage_1_s_sources_or_reasoning() -> None:
    question, _ = _prompt("country")
    prompt = QN.stage2_prompt(question, _claim(), QN.read_protocol(), QN.read_patterns())
    for shown in ("Temple of Nowhere 1", "Peru", "Bolivia", "severe", QN.read_patterns()):
        assert shown in prompt
    assert "CONFIRMED" in prompt and "REFUTED" in prompt and "UNDECIDED" in prompt
    assert "stage-1" not in prompt.lower() and "first judge" not in prompt.lower()


def test_the_stage2_prompt_of_a_text_field_names_the_disputed_part() -> None:
    question, _ = _prompt("description")
    claim = QN.Claim(right_value="built by the Wari", severity="severe",
                     disputed=("It was built c. 400 BC by the Inca.",))  # fmt: skip
    prompt = QN.stage2_prompt(question, claim, QN.read_protocol(), QN.read_patterns())
    assert "It was built c. 400 BC by the Inca." in prompt and "built by the Wari" in prompt


def test_the_stage3_prompt_shows_both_reasonings() -> None:
    question, _ = _prompt("country")
    first = QN.Reasoning("FIRST_REASONING", (("https://a.example/1", "FIRST_QUOTE"),))
    second = QN.Reasoning("SECOND_REASONING", ())
    prompt = QN.stage3_prompt(
        question, _claim(), first, second, QN.read_protocol(), QN.read_patterns()
    )
    for shown in ("FIRST_REASONING", "FIRST_QUOTE", "https://a.example/1", "SECOND_REASONING"):
        assert shown in prompt
    assert "UNDECIDED" not in prompt.split("## Your answer")[1]
    lonely = QN.stage3_prompt(
        question, _claim(), first, None, QN.read_protocol(), QN.read_patterns()
    )
    assert "gave no counted answer" in lonely


def test_the_prompt_digest_is_stable() -> None:
    question, prompt = _prompt("name")
    again = QN.stage1_prompt(question, QN.read_protocol(), QN.read_patterns())
    assert hashlib.sha256(prompt.encode()).digest() == hashlib.sha256(again.encode()).digest()
