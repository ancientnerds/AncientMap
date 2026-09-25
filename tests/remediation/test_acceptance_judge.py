"""Phase 6 acceptance, sections 6-7: the stages through the Opus handoff (`acceptance/judge.py`).

Export writes the questions into a handoff directory (`scripts/remediation/opus_handoff.py`), an
Opus agent per batch answers them, import validates, parses and quote-checks every answer. A verdict
that does not count goes to a new judge at most twice; every counted stage-1 WRONG goes to a second
judge, every UNDECIDED to a third. Offline: the answers are written by the test and the cited pages
come from an in-memory transport. The mutation cases are `acceptance judge: ...` in
`scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
from acceptance import judge as J  # noqa: E402
from acceptance import questions as QN  # noqa: E402

NOW = "2026-09-26T10:00:00+00:00"
ONE, TWO, GONE = "https://a.example/one", "https://b.example/two", "https://c.example/gone"
PAGES: dict[str, tuple[int, str, bytes]] = {
    ONE: (200, "text/html; charset=utf-8", b"<p>The temple is in <i>Peru</i>.</p>"),
    TWO: (200, "text/plain; charset=utf-8", b"The temple lies in Peru, near Cusco."),
    GONE: (404, "text/plain", b"not here"),
}
CANARY_REASON = "CANARY_KEY_TEXT_never_shown"


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def site(n: int) -> dict[str, Any]:
    return {
        "site_id": _uuid(n),
        "name": f"Temple {n}",
        "name_normalized": f"temple {n}",
        "country": "Peru",
        "lat": -13.5 - n / 10,
        "lon": -71.9,
        "site_type": "Temple",
        "period_start": -500,
        "period_end": None,
        "period_name": "500 BC - 1 AD",
        "description": f"Temple {n} is a temple in Peru.",
        "description_citations": None,
        "description_provenance": None,
        "source_url": f"https://en.wikipedia.org/wiki/Temple_{n}",
        "thumbnail_url": None,
        "scope_status": None,
        "scope_reason": None,
        "card_description": f"Temple {n}, in Peru.",
        "civilization": "Peru",
        "served_image": None,
    }


def canary(n: int, value: str = "Japan") -> dict[str, Any]:
    return {
        "site_id": _uuid(n),
        "field": "country",
        "canary_value": value,
        "true_stored": "Peru",
        "why_wrong": CANARY_REASON,
    }


def _jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def make_run(tmp_path: Path, n_sites: int = 2, canaries: list[dict] | None = None) -> Path:
    run = tmp_path / "draw-2026-10-01"
    run.mkdir(parents=True)
    sample = _jsonl([site(n) for n in range(1, n_sites + 1)])
    key = _jsonl(canaries if canaries is not None else [canary(1)])
    (run / "SAMPLE.jsonl").write_text(sample, encoding="utf-8", newline="\n")
    (run / "CANARIES.jsonl").write_text(key, encoding="utf-8", newline="\n")
    draw = {
        "journal_at_draw": {"max_id": 100, "max_applied_at": "t", "rows": 9},
        "sample_size": n_sites,
        "sha256": {
            "SAMPLE.jsonl": hashlib.sha256(sample.encode()).hexdigest(),
            "CANARIES.jsonl": hashlib.sha256(key.encode()).hexdigest(),
        },
    }
    (run / "DRAW.json").write_text(json.dumps(draw), encoding="utf-8")
    return run


def client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status, ctype, body = PAGES.get(str(request.url), (404, "text/plain", b"no such page"))
        return httpx.Response(status, headers={"Content-Type": ctype}, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def unverifiable() -> str:
    return json.dumps(
        {
            "verdict": "UNVERIFIABLE",
            "quotes": [],
            "right_value": None,
            "severity": None,
            "reasoning": "The sources are silent.",
        }  # fmt: skip
    )


def correct() -> str:
    return json.dumps(
        {
            "verdict": "CORRECT",
            "right_value": None,
            "severity": None,
            "reasoning": "Both agree.",
            "quotes": [
                {"url": ONE, "quote": "The temple is in Peru.", "claim": None},
                {"url": TWO, "quote": "lies in Peru", "claim": None},
            ],
        }  # fmt: skip
    )


def wrong_country(quote: str = "lies in Peru", url: str = TWO) -> str:
    return json.dumps(
        {
            "verdict": "WRONG",
            "right_value": "Peru",
            "severity": "severe",
            "reasoning": "REASONING_S1 the temple is in Peru.",
            "quotes": [{"url": url, "quote": quote, "claim": None}],
        }  # fmt: skip
    )


def s2_answer(verdict: str = "CONFIRMED", reasoning: str = "REASONING_S2") -> str:
    quotes = [{"url": ONE, "quote": "The temple is in Peru."}] if verdict == "CONFIRMED" else []
    return json.dumps(
        {
            "verdict": verdict,
            "quotes": quotes,
            "severity": None,
            "severity_reason": None,
            "pattern": None,
            "reasoning": reasoning,
        }  # fmt: skip
    )


def s3_answer(verdict: str = "CONFIRMED") -> str:
    quotes = [{"url": TWO, "quote": "near Cusco"}] if verdict == "CONFIRMED" else []
    return json.dumps({"verdict": verdict, "quotes": quotes, "reasoning": "REASONING_S3"})


def answer_all(
    handoff: Path,
    text_for: Callable[[dict[str, Any]], str | None],
    who: Callable[[dict[str, Any]], str] = lambda line: str(line["batch_id"]),
) -> None:
    for line in OH.manifest(handoff):
        text = text_for(line)
        if text is not None:
            OH.write_answer(handoff, batch_id=line["batch_id"], stage=line["stage"],
                            label=line["label"], text=text, answered_by=who(line),
                            now=lambda: NOW)  # fmt: skip


def _import(run: Path, stage: str) -> dict[str, Any]:
    return J.import_stage(run, stage, client=client(), pace=0.0)


def _records(run: Path, stage: str) -> dict[str, dict[str, Any]]:
    path = run / "judging" / f"STAGE{stage[1]}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {row["label"]: row for row in rows}


def _canary_label(run: Path) -> str:
    (label,) = [
        q.label
        for q in J.read_questions(run).values()
        if q.field == "country" and q.value == "Japan"
    ]
    return label


def _answers_with(run: Path, special: dict[str, str]) -> Callable[[dict[str, Any]], str]:
    return lambda line: special.get(line["label"], unverifiable())


# ------------------------------------------------------------------------------ export stage 1
def test_export_stage1_writes_every_question_once_and_records_the_round(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    handoff = tmp_path / "h-s1"
    summary = J.export_stage1(run, handoff)
    assert summary["questions"] == 21  # 2 sites x 10 non-empty fields + the canary question
    lines = OH.manifest(handoff)
    assert len(lines) == 21 and {line["stage"] for line in lines} == {"s1"}
    assert len({line["label"] for line in lines}) == 21
    by_batch: dict[str, list[str]] = {}
    questions = J.read_questions(run)
    for line in lines:
        by_batch.setdefault(line["batch_id"], []).append(questions[line["label"]].site_id)
    for batch_id, sites in by_batch.items():
        assert len(sites) == len(set(sites)), batch_id
    assert summary["batches"] == {b: len(s) for b, s in sorted(by_batch.items())}
    rounds = J.read_rounds(run)
    assert [(r["stage"], r["round"]) for r in rounds] == [("s1", 0)]
    assert rounds[0]["handoff"] == handoff.as_posix()


def test_nothing_a_judge_can_read_marks_a_canary(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    handoff = tmp_path / "h-s1"
    J.export_stage1(run, handoff)
    readable = [*handoff.rglob("*"), *(run / "judging").rglob("*")]
    for path in (p for p in readable if p.is_file()):
        text = path.read_text(encoding="utf-8")
        for mark in (CANARY_REASON, "canary", "true_stored", "why_wrong"):
            assert mark not in text, (path.name, mark)
    rows = [
        json.loads(line)
        for line in (run / "judging" / "QUESTIONS.jsonl").read_text("utf-8").splitlines()
    ]
    assert {frozenset(row) for row in rows} == {
        frozenset({"label", "site_id", "field", "value", "name", "country", "point"})
    }
    assert [row["label"] for row in rows] == sorted(row["label"] for row in rows)


def test_export_refuses_a_sample_or_a_key_that_is_not_the_draw_s(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    (run / "CANARIES.jsonl").write_text(_jsonl([canary(1, "Chile")]), encoding="utf-8")
    with pytest.raises(J.JudgeError, match="CANARIES.jsonl"):
        J.export_stage1(run, tmp_path / "h")
    run2 = make_run(tmp_path / "b")
    with (run2 / "SAMPLE.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(site(9)) + "\n")
    with pytest.raises(J.JudgeError, match="SAMPLE.jsonl"):
        J.export_stage1(run2, tmp_path / "h2")


def test_a_crlf_checkout_of_the_draw_is_the_same_draw(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    for name in ("SAMPLE.jsonl", "CANARIES.jsonl"):
        path = run / name
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert J.export_stage1(run, tmp_path / "h")["questions"] == 21


def test_a_round_is_exported_once_into_a_directory_of_its_own(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "h-s1")
    with pytest.raises(J.JudgeError, match="already exported"):
        J.export_stage1(run, tmp_path / "h-other")
    run2 = make_run(tmp_path / "b")
    busy = tmp_path / "busy"
    (busy / "x").mkdir(parents=True)
    with pytest.raises(J.JudgeError, match="not empty"):
        J.export_stage1(run2, busy)


# ------------------------------------------------------------------------------ import stage 1
def test_import_refuses_until_every_answer_is_validated(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    handoff = tmp_path / "h-s1"
    J.export_stage1(run, handoff)
    first = OH.manifest(handoff)[0]["label"]
    answer_all(handoff, lambda line: None if line["label"] == first else unverifiable())
    with pytest.raises(J.JudgeError, match="missing"):
        _import(run, "s1")


def test_a_verdict_counts_only_when_its_quotes_are_found(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    handoff = tmp_path / "h-s1"
    J.export_stage1(run, handoff)
    by_field: dict[str, list[str]] = {}
    for question in J.read_questions(run).values():
        by_field.setdefault(question.field, []).append(question.label)
    good, lost = sorted(by_field["name"])[0], sorted(by_field["site_type"])[0]
    broken = sorted(by_field["period_name"])[0]
    answer_all(handoff, _answers_with(run, {
        good: correct(),
        lost: correct().replace("lies in Peru", "lies in Chile"),
        broken: "VERDICT: CORRECT",
    }))  # fmt: skip
    summary = _import(run, "s1")
    records = _records(run, "s1")
    assert records[good]["final"]["verdict"] == "CORRECT"
    assert records[good]["attempts"][0]["counted"] is True
    assert records[lost]["final"] is None and records[lost]["attempts"][0]["reason"] == "not found"
    assert records[broken]["final"] is None
    assert records[broken]["attempts"][0]["reason"].startswith("malformed")
    reask = json.loads((run / "judging" / "REASK_S1.json").read_text(encoding="utf-8"))
    assert reask == {"stage": "s1", "after_round": 0, "labels": sorted([lost, broken])}
    assert summary["pending"] == 2 and summary["final"]["UNVERIFIABLE"] == 18
    pages = (run / "judging" / "PAGES.jsonl").read_text(encoding="utf-8")
    assert ONE in pages and TWO in pages
    body = run / "judging" / "pages" / f"{hashlib.sha256(ONE.encode()).hexdigest()}.body"
    assert body.read_bytes() == PAGES[ONE][2]


def test_a_question_goes_to_a_new_judge_at_most_twice_then_stands_unverifiable(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "r0")
    lost = sorted(J.read_questions(run))[0]
    failing = {lost: wrong_country("lies in Chile")}
    answer_all(tmp_path / "r0", _answers_with(run, failing))
    _import(run, "s1")
    for n in (1, 2):
        summary = J.export_reask(run, "s1", tmp_path / f"r{n}")
        assert summary["questions"] == 1
        (line,) = OH.manifest(tmp_path / f"r{n}")
        assert line["label"] == lost and line["batch_id"].startswith(f"s1r{n}-")
        answer_all(tmp_path / f"r{n}", _answers_with(run, failing))
        _import(run, "s1")
    record = _records(run, "s1")[lost]
    assert len(record["attempts"]) == 3
    assert record["final"] == {"verdict": "UNVERIFIABLE", "via": "exhausted", "attempt": None}
    reask = json.loads((run / "judging" / "REASK_S1.json").read_text(encoding="utf-8"))
    assert reask["labels"] == [] and reask["after_round"] == 2
    with pytest.raises(J.JudgeError, match="nothing to ask again"):
        J.export_reask(run, "s1", tmp_path / "r3")


def test_the_reask_asks_the_exact_same_prompt(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "r0")
    lost = sorted(J.read_questions(run))[0]
    answer_all(tmp_path / "r0", _answers_with(run, {lost: "not json"}))
    _import(run, "s1")
    J.export_reask(run, "s1", tmp_path / "r1")
    first = {line["label"]: line for line in OH.manifest(tmp_path / "r0")}[lost]
    (again,) = OH.manifest(tmp_path / "r1")
    assert again["prompt_sha256"] == first["prompt_sha256"]


def test_a_reask_waits_for_the_import_of_its_round(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "r0")
    with pytest.raises(J.JudgeError, match="import"):
        J.export_reask(run, "s1", tmp_path / "r1")


def test_an_answer_to_a_prompt_that_is_not_this_question_s_is_refused(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "r0")
    answer_all(tmp_path / "r0", lambda line: unverifiable())
    path = run / "judging" / "QUESTIONS.jsonl"
    path.write_text(path.read_text("utf-8").replace("Temple 2", "Temple 9"), encoding="utf-8")
    with pytest.raises(J.JudgeError, match="exported prompt"):
        _import(run, "s1")


def test_a_judge_who_answered_another_question_of_the_site_does_not_count(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "r0")
    questions = J.read_questions(run)
    site_one = sorted(q.label for q in questions.values() if q.site_id == _uuid(1))
    first, second = site_one[0], site_one[1]
    answer_all(
        tmp_path / "r0",
        lambda line: unverifiable(),
        who=lambda line: "judge-x" if line["label"] in (first, second) else line["batch_id"],
    )
    _import(run, "s1")
    records = _records(run, "s1")
    outcomes = sorted([records[first]["attempts"][0], records[second]["attempts"][0]],
                      key=lambda a: a["counted"])  # fmt: skip
    assert [a["counted"] for a in outcomes] == [False, True]
    assert "independent" in outcomes[0]["reason"]


# ------------------------------------------------------------------------------ stages 2 and 3
def _stage1_done(tmp_path: Path, run: Path, special: dict[str, str]) -> None:
    J.export_stage1(run, tmp_path / "s1")
    answer_all(tmp_path / "s1", _answers_with(run, special))
    _import(run, "s1")


def test_stage2_waits_for_stage1_to_finish(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "s1")
    lost = sorted(J.read_questions(run))[0]
    answer_all(tmp_path / "s1", _answers_with(run, {lost: "not json"}))
    _import(run, "s1")
    with pytest.raises(J.JudgeError, match="stage 1"):
        J.export_stage2(run, tmp_path / "s2")


def test_stage2_asks_every_counted_wrong_and_shows_no_stage1_source_or_reasoning(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "s1")
    label = _canary_label(run)
    quiet = sorted(set(J.read_questions(run)) - {label})[0]
    answer_all(tmp_path / "s1", _answers_with(run, {label: wrong_country(),
                                                   quiet: wrong_country("lies in Mars")}))  # fmt: skip
    _import(run, "s1")
    J.export_reask(run, "s1", tmp_path / "s1r1")
    answer_all(tmp_path / "s1r1", lambda line: unverifiable())
    _import(run, "s1")
    summary = J.export_stage2(run, tmp_path / "s2")
    assert summary["questions"] == 1
    (line,) = OH.manifest(tmp_path / "s2")
    assert line["label"] == label and line["stage"] == "s2"
    prompt = (tmp_path / "s2" / line["prompt_path"]).read_text(encoding="utf-8")
    assert "Japan" in prompt and "Peru" in prompt and "severe" in prompt
    assert "REASONING_S1" not in prompt and TWO not in prompt


def test_stage3_asks_every_undecided_with_both_reasonings(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "s1")
    label = _canary_label(run)
    answer_all(tmp_path / "s1", _answers_with(run, {label: wrong_country()}))
    _import(run, "s1")
    J.export_stage2(run, tmp_path / "s2")
    with pytest.raises(J.JudgeError, match="stage 2"):
        J.export_stage3(run, tmp_path / "s3")
    answer_all(tmp_path / "s2", lambda line: s2_answer("UNDECIDED"))
    summary = _import(run, "s2")
    assert summary["final"] == {"UNDECIDED": 1}
    J.export_stage3(run, tmp_path / "s3")
    (line,) = OH.manifest(tmp_path / "s3")
    prompt = (tmp_path / "s3" / line["prompt_path"]).read_text(encoding="utf-8")
    for shown in ("REASONING_S1", "REASONING_S2", TWO, "lies in Peru", "Japan"):
        assert shown in prompt
    answer_all(tmp_path / "s3", lambda line: s3_answer())
    assert _import(run, "s3")["final"] == {"CONFIRMED": 1}


def test_a_stage2_judge_must_be_new_to_the_site(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "s1")
    label = _canary_label(run)
    answer_all(tmp_path / "s1", _answers_with(run, {label: wrong_country()}))
    _import(run, "s1")
    s1_judge = _records(run, "s1")[label]["attempts"][0]["answered_by"]
    J.export_stage2(run, tmp_path / "s2")
    answer_all(tmp_path / "s2", lambda line: s2_answer(), who=lambda line: s1_judge)
    summary = _import(run, "s2")
    assert summary["pending"] == 1


# ------------------------------------------------------------------------------ the agent's aids
def test_check_answer_names_the_shape_problem_and_fetches_nothing(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "s1")
    line = OH.manifest(tmp_path / "s1")[0]
    args = (run, tmp_path / "s1", line["batch_id"], line["label"])
    assert J.check_answer(*args, unverifiable()) is None
    assert "one JSON object" in (J.check_answer(*args, "```json\n{}\n```") or "")
    assert not (run / "judging" / "pages").exists()


def test_the_brief_names_the_batch_its_directory_and_both_commands(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    J.export_stage1(run, tmp_path / "s1")
    batch = OH.manifest(tmp_path / "s1")[0]["batch_id"]
    brief = J.brief(run, tmp_path / "s1", batch)
    assert batch in brief and (tmp_path / "s1").as_posix() in brief
    assert f"--answered-by {batch}" in brief and "--stage s1" in brief
    assert "opus_handoff.py answer" in brief and "judge.py check-answer" in brief
    assert "CANARIES" not in brief and "canary" not in brief.lower()
