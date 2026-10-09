"""Contract shorts-v1 and the Claude re-check, end to end through the handoff.

The production export is a fixture built from the pilot sites (`shorts_cases`), every answer is
written through `opus_handoff.write_answer` in the role of its stage, the web is an
`httpx.MockTransport`. The v1 chain keeps its own tests (`test_teaser.py`); here the tests are the
ones the new contracts add: the roles, the variants and the rating, the canary, keep-on-fail
(owner decision D5), the version-3 provenance and the re-check run (owner decision D10).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from teaser import answers as A  # noqa: E402
from teaser import answers_shorts as AS  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import run as R  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import shorts_cases as S  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402

MP, HUACA, GLAPH, TREG, DENBURY = (
    "Machu Picchu",
    "Huaca del Sol",
    "Glaphyrae",
    "Tregiffian Burial Chamber",
    "Denbury Hill",
)
PAGE = "https://example.org/skara-brae"
PAGE_TEXT = b"<html><body><p>The site was occupied from roughly 3180 BC to around 2500 BC.</p></body></html>"
OPUS = OH.OPUS_MODEL
SONNET = OH.SONNET_MODEL


def sid(name: str) -> str:
    return str(S.BY_NAME[name]["site_id"])


def production_row(name: str, **over: Any) -> dict[str, Any]:
    """One `run.SHORTS_SITES_SQL` row: lane W, the provenance hashing the description, the live card
    of the day the pilot sites were read, the alternative names and the usable images."""
    sample = S.BY_NAME[name]
    row = {
        "site_id": sample["site_id"],
        "name": name,
        "country": sample["country"],
        "description": sample["description"],
        "scope_status": None,
        "lane": "W",
        "provenance_desc_sha256": T.sha(sample["description"]),
        "check_desc_sha256": None,
        "card_provenance": None,
        "has_card_row": True,
        "card": sample["live_card"],
        "alt_names": [name, *sample["aliases"]],
        "pool_images": sample["pool_images"],
        "image_titles": ["File A", "File B"],
    }
    return {**row, **over}


def make_run(
    tmp_path: Path,
    names: list[str],
    *,
    rows: list[dict[str, Any]] | None = None,
    exclude: list[Path] | None = None,
    contract: str = R.SHORTS,
) -> Path:
    run = tmp_path / "runs" / "wb-shorts-test"
    export = T.tagged({"site": rows if rows is not None else [production_row(n) for n in names]})

    def read(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export, encoding="utf-8", newline="\n")

    R.select(run, read=read, sites_file=None, pilot=None, exclude=exclude or [], contract=contract)
    return run


# ------------------------------------------------------------------------------ the answers
def variants_json(name: str) -> str:
    sample = S.BY_NAME[name]
    first = {k: sample[k] for k in ("card", "basis", "anchors", "reserve", "hook_type")}
    return json.dumps({"variants": [first, *S.EXTRA_VARIANTS[name]]}, ensure_ascii=False)


def cards_of(name: str) -> list[str]:
    sample = S.BY_NAME[name]
    return [
        C.final_card(sample["card"]),
        *(C.final_card(v["card"]) for v in S.EXTRA_VARIANTS[name]),
    ]


def rate_json(shown: list[tuple[int, str]], hooks: list[int]) -> str:
    ratings = [
        {"variant": number, "first5": AS.first_five(card), "hook": hook}
        for (number, card), hook in zip(shown, hooks, strict=True)
    ]
    best = max(ratings, key=lambda r: (r["hook"], -r["variant"]))["variant"]
    return json.dumps({"ratings": ratings, "best": best})


def check_json(verdict: str = "PASS", **over: Any) -> str:
    fields: dict[str, Any] = {
        "claims": [{"claim": "the site's main facts", "support": ["S1"]}],
        "name_leak": False,
        "this_site": True,
        "hook_ok": True,
        "s1_no_place": True,
        "payoff_ok": True,
        "generic_ok": True,
        "loop_ok": True,
        "tone_ok": True,
        "anchors_ok": True,
        "verdict": verdict,
        "reasons": [],
    }
    if verdict == "FAIL":
        fields.update(reasons=["No sentence says it."], claims=[{"claim": "x", "support": []}])
    return json.dumps({**fields, **over})


CANARY_CAUGHT = check_json("FAIL", name_leak=True, reasons=["The seeded flaw."])
VERIFIED_ANSWER = T.judge_answer()


def judge_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == PAGE:
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=PAGE_TEXT)
        return httpx.Response(404, content=b"no")

    return httpx.Client(transport=httpx.MockTransport(handler))


def put(
    handoff: Path,
    stage: str,
    batch_id: str,
    label: str,
    text: str,
    role: str,
    model: str | None = None,
) -> None:
    OH.write_answer(
        handoff,
        batch_id=batch_id,
        stage=stage,
        label=label,
        text=text,
        answered_by=RO.answered_by(role, R.agent_name(batch_id)),
        model=OH.ANSWER_MODELS[model or RO.role(role).model],
    )


def answer_round(
    run: Path,
    stage: str,
    handoff: Path,
    answers: dict[str, str],
    *,
    canary: str = CANARY_CAUGHT,
    role: str | None = None,
    canary_role: str | None = None,
    model: str | None = None,
) -> None:
    record = R._round(run, stage)
    assert record is not None
    chosen = role or R.SHORTS_SPEC.roles[stage]
    for batch_id, members in record["batches"].items():
        for site_id in members:
            put(handoff, stage, batch_id, site_id, answers[site_id], chosen, model)
        if batch_id in record.get("canaries", {}):
            put(
                handoff,
                stage,
                batch_id,
                record["canaries"][batch_id]["label"],
                canary,
                canary_role or chosen,
                model,
            )


def step(
    run: Path,
    tmp_path: Path,
    stage: str,
    answers: dict[str, str],
    **kw: Any,
) -> dict[str, Any]:
    handoff = tmp_path / f"handoff-{stage}"
    exported = R.export_stage(run, stage, handoff)
    if not exported["questions"]:
        return exported
    answer_round(run, stage, handoff, answers, **kw)
    if stage in R.SHORTS_SPEC.verifiers:
        return R.import_stage(run, stage, fit=T.fit, client=judge_client(), pace=0)
    return R.import_stage(run, stage, fit=T.fit)


def writes(names: list[str]) -> dict[str, str]:
    return {sid(n): variants_json(n) for n in names}


def rates(
    run: Path, names: list[str], stage: str = "write", hooks: tuple[int, ...] = (4, 3, 2)
) -> dict[str, str]:
    records = R.stage_records(run)[stage]
    return {sid(n): rate_json(R.shown_variants(records[sid(n)]), list(hooks)) for n in names}


def passes(names: list[str], **over: Any) -> dict[str, str]:
    return {sid(n): check_json(**over) for n in names}


def verifies(names: list[str]) -> dict[str, str]:
    return {sid(n): VERIFIED_ANSWER for n in names}


def chain(run: Path, tmp_path: Path, names: list[str]) -> None:
    """The first round of every stage, every answer good."""
    step(run, tmp_path, "write", writes(names))
    step(run, tmp_path, "rate", rates(run, names))
    step(run, tmp_path, "check", passes(names))
    step(run, tmp_path, "verify", verifies(names))
    for stage in ("rewrite1", "rewrite2", "rewrite-v"):
        step(run, tmp_path, stage, {})


NAMES = [MP, HUACA, GLAPH, TREG]


def outcome(run: Path, name: str) -> dict[str, Any]:
    return next(r for r in R.read_outcomes(run) if r["site_id"] == sid(name))


# ------------------------------------------------------------------------------ select
class TestSelect:
    def test_the_run_records_its_contract_the_limits_and_the_roles(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        assert record["contract"] == "shorts-v1" and R.contract_of(run) == R.SHORTS
        assert record["limits"]["hook_floor"] == 3 and record["limits"]["sentence_1_chars"] == [
            40,
            85,
        ]
        assert record["roles"]["card_writer"] == {"model": "claude-opus-5-5", "effort": "high"}
        assert record["roles"]["hook_rater"] == {"model": "claude-opus-5-5", "effort": "medium"}
        assert record["roles"]["fact_checker"] == {"model": "claude-sonnet-5-5", "effort": "high"}
        assert record["roles"]["web_verifier"] == {"model": "claude-sonnet-5-5", "effort": "high"}
        assert record["roles"]["pilot_judge"] == {"model": "claude-opus-5-5", "effort": "xhigh"}
        assert R.spec_of(run) is R.SHORTS_SPEC

    def test_a_v1_run_holds_its_limits_as_an_object_and_is_contract_v1(
        self, tmp_path: Path
    ) -> None:
        run = tmp_path / "runs" / "wb-v1"
        export = T.tagged({"site": T.production_rows()})

        def read(path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(export, encoding="utf-8", newline="\n")

        R.select(run, read=read, sites_file=None, pilot=None, exclude=[])
        assert isinstance(json.loads((run / "RUN.json").read_text("utf-8"))["contract"], dict)
        assert R.contract_of(run) == "v1" and R.spec_of(run) is R.V1_SPEC
        assert "roles" not in json.loads((run / "RUN.json").read_text("utf-8"))

    def test_a_role_bound_run_records_its_roles(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        record = json.loads((run / "RUN.json").read_text("utf-8"))
        del record["roles"]
        (run / "RUN.json").write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(R.RunError, match="records no roles"):
            R.run_roles(run)

    def test_an_unknown_contract_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        record = json.loads((run / "RUN.json").read_text("utf-8"))
        record["contract"] = "shorts-v9"
        (run / "RUN.json").write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(R.RunError, match="names the contract 'shorts-v9'"):
            R.contract_of(run)

    def test_the_candidates_carry_their_images_and_the_bases_their_names(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP, TREG])
        rows = {r["site_id"]: r for r in R.read_jsonl(run / "SITES.jsonl")}
        assert rows[sid(MP)]["pool_images"] == 14 and rows[sid(MP)]["image_titles"] == [
            "File A",
            "File B",
        ]
        bases = R.bases(run)
        assert isinstance(bases[sid(MP)], SV.ShortsBasis) and bases[sid(MP)].shorts_eligible
        assert bases[sid(MP)].aliases == ("Machu Picchu", "Machu Pichu")
        assert bases[sid(TREG)].thin and not bases[sid(TREG)].shorts_eligible

    def test_a_recheck_run_is_seeded_never_selected(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="it is seeded"):
            make_run(tmp_path, [MP], contract=R.RECHECK)

    def test_the_shorts_sql_reads_the_usable_images_and_their_titles(self) -> None:
        sql = R.SHORTS_SITES_SQL
        assert (
            "least(w.width, w.height) >= 900" in sql and "<= 2.0 * least(w.width, w.height)" in sql
        )
        assert "AS pool_images" in sql and "AS image_titles" in sql and "LIMIT 12" in sql
        assert "pool_images" not in R.SITES_SQL

    def test_a_v1_run_is_not_asked_again_as_asked_before_by_a_shorts_run(
        self, tmp_path: Path
    ) -> None:
        v1 = tmp_path / "runs" / "wb-v1"
        export = T.tagged({"site": [production_row(MP)]})
        v1.mkdir(parents=True)

        def read(path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(export, encoding="utf-8", newline="\n")

        R.select(v1, read=read, sites_file=None, pilot=None, exclude=[])
        assert R.earlier_sites([v1]) == {sid(MP): T.sha(S.BY_NAME[MP]["description"])}
        assert R.earlier_sites([v1], R.SHORTS) == {}
        run = make_run(tmp_path / "second", [MP], exclude=[v1])
        assert len(R.read_jsonl(run / "SITES.jsonl")) == 1

    def test_only_a_version_3_card_of_the_contract_is_current(self) -> None:
        live = production_row(MP)
        stamp = OPUS
        v2 = CP.build(
            run="wb-old", ai_system=M.AI_SYSTEM_CLAUDE, card=live["card"], description=live["description"],
            stage="check", checker="teaser-check-001", checked_at="2026-09-26T12:00:00+00:00",
            claims=[{"claim": "c", "support": ["S1"]}],
            verify={"verdict": "VERIFIED", "stage": "verify", "by": "teaser-verify-001", "at": "2026-09-26T13:00:00+00:00",
                    "claims": 1, "unproven": 0, "text_sha256": CP.text_sha256(live["card"])},
            web_facts=[],
        )  # fmt: skip
        v3 = CP.build_v3(
            run="wb-new", ai_system=M.AI_SYSTEM_CLAUDE, card=live["card"], description=live["description"],
            stage="check", checker="fact_checker:t-1", checked_at="2026-10-09T12:00:00+00:00",
            claims=[{"claim": "c", "support": ["S1"]}],
            verify={"verdict": "VERIFIED", "stage": "verify", "by": "web_verifier:t-2", "at": "2026-10-09T13:00:00+00:00",
                    "claims": 1, "unproven": 0, "text_sha256": CP.text_sha256(live["card"])},
            web_facts=[], models={"write": stamp, "rate": stamp, "check": stamp, "verify": stamp},
            hook={"type": "object", "rating": 4, "variant": 1}, anchors=["x"], reserve=["S2"], shorts_ready=True,
        )  # fmt: skip
        assert R.classify({**live, "card_provenance": v2}, R.SHORTS) == (None, "")
        assert R.classify({**live, "card_provenance": v2}, R.V1)[0] == R.CURRENT
        assert R.classify({**live, "card_provenance": v3}, R.SHORTS)[0] == R.CURRENT
        assert R.current_for(v3, R.V1) and not R.current_for(v2, R.SHORTS)
        other = {**v3, "contract": "shorts-v2"}
        assert not R.current_for(other, R.SHORTS)


# ------------------------------------------------------------------------------ the chain
class TestTheFirstRound:
    def test_every_stage_in_order_to_a_version_3_provenance(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        assert step(run, tmp_path, "write", writes(NAMES))["mechanical_failures"] == 0
        assert R.status(run)["states"] == {"due rate": 4}
        assert step(run, tmp_path, "rate", rates(run, NAMES))["best_below_floor"] == 0
        assert R.status(run)["states"] == {"due check": 4}
        assert step(run, tmp_path, "check", passes(NAMES))["verdicts"] == {"PASS": 4}
        assert R.status(run)["states"] == {"due verify": 4}
        assert step(run, tmp_path, "verify", verifies(NAMES))["verdicts"] == {"VERIFIED": 4}
        assert R.status(run)["states"] == {"accepted": 4}
        R.outcomes(run)
        rows = {r["site_id"]: r for r in R.read_outcomes(run)}
        assert {r["status"] for r in rows.values()} == {R.ACCEPTED}
        mp = rows[sid(MP)]
        prov = CP.validate(mp["provenance"])
        assert (
            prov["v"] == 3 and prov["contract"] == "shorts-v1" and prov["run"] == "wb-shorts-test"
        )
        assert prov["models"] == {"write": OPUS, "rate": OPUS, "check": SONNET, "verify": SONNET}
        assert prov["ai_system"] == M.AI_SYSTEM_CLAUDE
        assert prov["hook"] == {"type": "object", "rating": 4, "variant": 1}
        assert prov["anchors"] == S.BY_NAME[MP]["anchors"] and prov["reserve"] == ["S3"]
        assert prov["shorts_ready"] is True and CP.describes(prov, mp["card"])
        assert mp["card"] == C.final_card(S.BY_NAME[MP]["card"])
        assert prov["check"]["by"] == "fact_checker:teaser-check-001"
        assert prov["verify"]["by"] == "web_verifier:teaser-verify-001"
        assert CP.shorts_pin(prov, S.BY_NAME[MP]["description"]) == CP.text_sha256(mp["card"])

    def test_shorts_ready_needs_an_eligible_site_a_reserve_and_an_anchor(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, NAMES)
        chain(run, tmp_path, NAMES)
        R.outcomes(run)
        ready = {n: outcome(run, n)["provenance"]["shorts_ready"] for n in NAMES}
        assert ready == {MP: True, HUACA: True, GLAPH: False, TREG: False}
        assert outcome(run, GLAPH)["provenance"]["reserve"] == ["reveal"]
        assert outcome(run, TREG)["provenance"]["reserve"] is None
        assert outcome(run, GLAPH)["provenance"]["anchors"] == []
        assert (
            CP.shorts_pin(outcome(run, GLAPH)["provenance"], S.BY_NAME[GLAPH]["description"])
            is None
        )

    def test_the_rater_chooses_the_best_variant(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP], hooks=(3, 5, 4)))
        step(run, tmp_path, "check", passes([MP]))
        step(run, tmp_path, "verify", verifies([MP]))
        R.outcomes(run)
        row = outcome(run, MP)
        assert row["card"] == cards_of(MP)[1]
        assert row["provenance"]["hook"] == {"type": "object", "rating": 5, "variant": 2}
        assert row["provenance"]["anchors"] == S.EXTRA_VARIANTS[MP][0]["anchors"]

    def test_a_variant_with_a_mechanical_problem_is_not_rated(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        bad = json.loads(variants_json(MP))
        bad["variants"][0]["card"] = (
            "Machu Picchu is a 15th-century Inca citadel high in the Andes of Peru, where bones show that most people living there were immigrants."
        )
        text = json.dumps(bad, ensure_ascii=False)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        checked = R.check_answer(run, handoff, "write-001", sid(MP), text, fit=T.fit)
        assert checked["ok"] is False and checked["problems"][0].startswith("variant 1: ")
        answer_round(run, "write", handoff, {sid(MP): text})
        R.import_stage(run, "write", fit=T.fit)
        record = R.stage_records(run)["write"][sid(MP)]
        assert [bool(v["problems"]) for v in record["variants"]] == [True, False, False]
        assert [n for n, _ in R.shown_variants(record)] == [2, 3]
        handoff_rate = tmp_path / "handoff-rate"
        R.export_stage(run, "rate", handoff_rate)
        prompt = (handoff_rate / OH.manifest(handoff_rate)[0]["prompt_path"]).read_text("utf-8")
        assert "Variant 2: " in prompt and "Variant 3: " in prompt and "Variant 1: " not in prompt

    def test_every_variant_failing_goes_to_a_rewrite_with_its_problems(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP])
        named = json.loads(variants_json(MP))
        for v in named["variants"]:
            v["card"] = "Machu Picchu: " + v["card"]
        step(run, tmp_path, "write", {sid(MP): json.dumps(named, ensure_ascii=False)})
        assert R.status(run)["states"] == {"due rewrite1": 1}
        state = R.states(run)[sid(MP)]
        assert len(state.findings) == 3
        assert any(
            r.startswith("name: the card holds the site's name") for r in state.findings[0].reasons
        )
        handoff = tmp_path / "handoff-rewrite1"
        R.export_stage(run, "rewrite1", handoff)
        prompt = (handoff / OH.manifest(handoff)[0]["prompt_path"]).read_text("utf-8")
        assert "EARLIER CARDS" in prompt and "Why it was not accepted" in prompt

    def test_a_best_opening_below_the_floor_sends_the_site_to_a_rewrite(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        result = step(run, tmp_path, "rate", rates(run, [MP], hooks=(2, 1, 2)))
        assert result["best_below_floor"] == 1
        assert R.status(run)["states"] == {"due rewrite1": 1}
        findings = R.states(run)[sid(MP)].findings
        assert len(findings) == 3
        assert (
            "rated its opening 2/5" in findings[0].reasons[0]
            and "needs at least 3" in findings[0].reasons[0]
        )
        step(run, tmp_path, "rewrite1", writes([MP]))
        assert R.status(run)["states"] == {"due rate1": 1}

    def test_a_best_opening_at_the_floor_passes(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP], hooks=(3, 2, 2)))
        assert R.status(run)["states"] == {"due check": 1}

    def test_a_stage_imported_again_after_it_was_rated_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP]))
        path = run / "STAGE-write.jsonl"
        rows = R.read_jsonl(path)
        rows[0]["variants"][0]["card"] = "Another card, written after the rating."
        R.write_jsonl(path, rows)
        with pytest.raises(
            R.RunError, match="STAGE-rate rated another card than STAGE-write holds"
        ):
            R.states(run)

    def test_a_repeated_opening_between_two_sites_fails_the_second_rating(
        self, tmp_path: Path
    ) -> None:
        twin = production_row(MP, site_id="0b000000-0000-4000-8000-000000000009")
        run = make_run(tmp_path, [], rows=[production_row(MP), twin])
        both = {sid(MP): variants_json(MP), twin["site_id"]: variants_json(MP)}
        step(run, tmp_path, "write", both)
        shown = R.shown_variants(R.stage_records(run)["write"][sid(MP)])
        result = step(run, tmp_path, "rate", dict.fromkeys(both, rate_json(shown, [4, 3, 2])))
        assert result["diversity_failures"] == 1
        rows = {r["site_id"]: r for r in R.read_jsonl(run / "STAGE-rate.jsonl")}
        first, second = sorted(rows)
        assert rows[first]["problems"] == []
        assert rows[second]["problems"][0].startswith(
            "diversity: another card of the run opens with"
        )
        assert R.status(run)["states"] == {"due check": 1, "due rewrite1": 1}

    def test_check_answer_takes_a_rating(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        handoff = tmp_path / "handoff-rate"
        R.export_stage(run, "rate", handoff)
        shown = R.shown_variants(R.stage_records(run)["write"][sid(MP)])
        checked = R.check_answer(
            run, handoff, "rate-001", sid(MP), rate_json(shown, [2, 5, 4]), fit=T.fit
        )
        assert checked == {"ok": True, "problems": [], "best": 2, "hook": 5}
        assert R.check_answer(run, handoff, "rate-001", sid(MP), "{}", fit=T.fit)["ok"] is False

    def test_a_shorts_site_without_a_description_keeps_its_card(self, tmp_path: Path) -> None:
        empty = production_row(
            HUACA, description=None, lane=None, provenance_desc_sha256=None, pool_images=0
        )
        run = make_run(tmp_path, [], rows=[production_row(MP), empty])
        chain(run, tmp_path, [MP])
        R.outcomes(run)
        row = outcome(run, HUACA)
        assert (row["status"], row["reason"], row["card"]) == (R.KEPT, "no-description", None)

    def test_a_thin_decline_keeps_the_card_and_asks_no_more(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [TREG, MP])
        decline = json.dumps({"card": None, "thin": True, "reason": "two sentences"})
        result = step(run, tmp_path, "write", {sid(TREG): decline, sid(MP): variants_json(MP)})
        assert result["thin"] == 1
        assert R.status(run)["states"] == {"cleared": 1, "due rate": 1}
        step(run, tmp_path, "rate", rates(run, [MP]))
        step(run, tmp_path, "check", passes([MP]))
        step(run, tmp_path, "verify", verifies([MP]))
        assert step(run, tmp_path, "rewrite1", {})["questions"] == 0
        R.outcomes(run)
        row = outcome(run, TREG)
        assert (row["status"], row["reason"], row["card"], row["provenance"]) == (
            R.KEPT,
            R.THIN_DECLINED,
            None,
            None,
        )

    def test_a_decline_of_a_description_with_enough_in_it_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        decline = json.dumps({"card": None, "thin": True, "reason": "too hard"})
        checked = R.check_answer(run, handoff, "write-001", sid(MP), decline, fit=T.fit)
        assert checked["ok"] is False and "a card can be written" in checked["problems"][0]

    def test_a_site_whose_chain_fails_keeps_its_card_it_is_never_cleared(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP, HUACA])
        step(run, tmp_path, "write", writes([MP, HUACA]))
        step(run, tmp_path, "rate", rates(run, [MP, HUACA]))
        step(run, tmp_path, "check", {sid(MP): check_json("FAIL"), sid(HUACA): check_json()})
        assert R.status(run)["states"] == {"due rewrite1": 1, "due verify": 1}
        step(run, tmp_path, "rewrite1", {sid(MP): variants_json(MP)})
        step(run, tmp_path, "rate1", rates(run, [MP], "rewrite1"))
        step(run, tmp_path, "check1", {sid(MP): check_json("FAIL")})
        step(run, tmp_path, "rewrite2", {sid(MP): variants_json(MP)})
        step(run, tmp_path, "rate2", rates(run, [MP], "rewrite2"))
        step(run, tmp_path, "check2", {sid(MP): check_json("FAIL")})
        step(run, tmp_path, "verify", verifies([HUACA]))
        step(run, tmp_path, "rewrite-v", {})
        R.outcomes(run)
        row = outcome(run, MP)
        assert (row["status"], row["reason"], row["card"], row["provenance"]) == (
            R.KEPT,
            R.FAILED_REWRITES,
            None,
            None,
        )
        assert len(row["findings"]) == 3
        assert outcome(run, HUACA)["status"] == R.ACCEPTED
        md = (run / "OUTCOMES.md").read_text(encoding="utf-8")
        assert "kept 1" in md and "cleared" not in md.split("## Every contradiction")[0]

    def test_a_contradicted_card_is_rewritten_and_carries_no_rating(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP]))
        step(run, tmp_path, "check", passes([MP]))
        contradicted = T.judge_answer(
            T.judged_claim(),
            T.judged_claim(
                "CONTRADICTED",
                "occupied from roughly 3180 BC to around 2500 BC",
                PAGE,
                "built by the Inca",
            ),
        )
        step(run, tmp_path, "verify", {sid(MP): contradicted})
        assert R.status(run)["states"] == {"due rewrite-v": 1}
        handoff = tmp_path / "handoff-rewrite-v"
        R.export_stage(run, "rewrite-v", handoff)
        prompt = (handoff / OH.manifest(handoff)[0]["prompt_path"]).read_text("utf-8")
        assert (
            prompt
            == PS.verify_rewrite_prompt(
                R.bases(run)[sid(MP)].with_web(R.web_facts(R.states(run)[sid(MP)].verified[0])),
                cards_of(MP)[0],
                [R.contradicted_claims(R.states(run)[sid(MP)].verified[0])[0]],
                [],
            )
            or "THE CARD THE WEB CHECK DID NOT VERIFY" in prompt
        )
        rewrite = json.dumps(
            {
                **{
                    k: S.BY_NAME[MP][k]
                    for k in ("card", "basis", "anchors", "reserve", "hook_type")
                },
                "repeats": [None],
            }
        )
        answer_round(run, "rewrite-v", handoff, {sid(MP): rewrite})
        R.import_stage(run, "rewrite-v", fit=T.fit)
        step(run, tmp_path, "check-v", passes([MP]))
        step(run, tmp_path, "verify2", verifies([MP]))
        R.outcomes(run)
        prov = outcome(run, MP)["provenance"]
        assert prov["check"]["stage"] == "check-v" and prov["verify"]["stage"] == "verify2"
        assert prov["models"] == {"write": OPUS, "rate": None, "check": SONNET, "verify": SONNET}
        assert prov["hook"] == {"type": "object", "rating": None, "variant": None}
        assert [d["claim"] for d in R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl")] == []

    def test_a_card_still_contradicted_after_its_rewrite_is_kept_not_cleared(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP]))
        step(run, tmp_path, "check", passes([MP]))
        wrong = T.judge_answer(
            T.judged_claim(),
            T.judged_claim(
                "CONTRADICTED",
                "occupied from roughly 3180 BC to around 2500 BC",
                PAGE,
                "built by the Inca",
            ),
        )
        step(run, tmp_path, "verify", {sid(MP): wrong})
        rewrite = json.dumps(
            {
                **{
                    k: S.BY_NAME[MP][k]
                    for k in ("card", "basis", "anchors", "reserve", "hook_type")
                },
                "repeats": ["S5"],
            }
        )
        step(run, tmp_path, "rewrite-v", {sid(MP): rewrite})
        step(run, tmp_path, "check-v", passes([MP]))
        step(run, tmp_path, "verify2", {sid(MP): wrong})
        R.outcomes(run)
        row = outcome(run, MP)
        assert (row["status"], row["reason"]) == (R.KEPT, R.CONTRADICTED_AFTER_VERIFY)
        # the first verifier's claim is mapped by the rewrite to sentence 5; the second verifier's
        # contradiction rests on the sentences its check cited, which no writer mapped (sentence null)
        defects = R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl")
        assert [(d["stage"], d["sentence"]) for d in defects] == [("verify", 5), ("verify2", None)]


# ------------------------------------------------------------------------------ the roles
class TestTheRoles:
    def test_an_answer_not_given_in_a_role_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        OH.write_answer(
            handoff, batch_id="write-001", stage="write", label=sid(MP), text=variants_json(MP),
            answered_by="teaser-write-001", model=OPUS,
        )  # fmt: skip
        with pytest.raises(R.RunError, match="did not answer as role card_writer"):
            R.import_stage(run, "write", fit=T.fit)
        assert not (run / "STAGE-write.jsonl").exists()

    def test_an_answer_in_another_role_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        put(handoff, "write", "write-001", sid(MP), variants_json(MP), "hook_rater")
        with pytest.raises(
            R.RunError, match="'hook_rater:teaser-write-001' did not answer as role card_writer"
        ):
            R.import_stage(run, "write", fit=T.fit)

    def test_a_stamp_that_is_not_the_roles_model_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        put(
            handoff,
            "write",
            "write-001",
            sid(MP),
            variants_json(MP),
            "card_writer",
            model="claude-sonnet-5-5",
        )
        with pytest.raises(R.RunError, match="role card_writer is recorded as claude-opus-5-5"):
            R.import_stage(run, "write", fit=T.fit)

    def test_a_rater_that_rated_the_site_before_is_refused(self, tmp_path: Path) -> None:
        """The roles make the names of different roles differ; the rule still catches one agent name
        used for the same role in two rounds."""
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP], hooks=(1, 1, 1)))
        step(run, tmp_path, "rewrite1", writes([MP]))
        handoff = tmp_path / "handoff-rate1"
        R.export_stage(run, "rate1", handoff)
        shown = R.shown_variants(R.stage_records(run)["rewrite1"][sid(MP)])
        OH.write_answer(
            handoff, batch_id="rate1-001", stage="rate1", label=sid(MP), text=rate_json(shown, [4, 3, 2]),
            answered_by="hook_rater:teaser-rate-001", model=OPUS,
        )  # fmt: skip
        with pytest.raises(R.RunError, match="wrote or checked this site before"):
            R.import_stage(run, "rate1", fit=T.fit)

    def test_the_run_fixes_its_models_at_its_start(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        record = json.loads((run / "RUN.json").read_text("utf-8"))
        assert record["roles"]["fact_checker"]["model"] == RO.role("fact_checker").model
        assert set(record["roles"]) == {
            "card_writer",
            "hook_rater",
            "fact_checker",
            "web_verifier",
            "pilot_judge",
        }

    def test_a_failed_calibration_moves_a_role_up_one_tier_before_its_first_round(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP])
        verdict = tmp_path / "verdict.json"
        move = RO.escalation("fact_checker", calibration_id="c-1", reason="agreement 0.8")
        verdict.write_text(
            json.dumps({"role": "fact_checker", "passed": False, "tier_move": move}),
            encoding="utf-8",
        )
        result = R.escalate_role(run, "fact_checker", verdict)
        assert result == {
            "role": "fact_checker",
            "model": "claude-opus-5-5",
            "from": "claude-sonnet-5-5",
        }
        record = json.loads((run / "RUN.json").read_text("utf-8"))
        assert record["roles"]["fact_checker"] == {"model": "claude-opus-5-5", "effort": "high"}
        assert record["escalations"][0]["calibration_id"] == "c-1"
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP]))
        # the checker is Opus now: a Sonnet answer is refused at import, an Opus one stands
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        answer_round(run, "check", handoff, passes([MP]), model="claude-sonnet-5-5")
        with pytest.raises(R.RunError, match="role fact_checker is recorded as claude-opus-5-5"):
            R.import_stage(run, "check", fit=T.fit)
        other = make_run(tmp_path / "other", [MP])
        step(other, tmp_path / "other", "write", writes([MP]))
        step(other, tmp_path / "other", "rate", rates(other, [MP]))
        R.export_stage(other, "check", tmp_path / "other" / "handoff-check")
        with pytest.raises(R.RunError, match="has answered rounds already"):
            R.escalate_role(other, "fact_checker", verdict)

    def test_a_role_the_run_does_not_use_is_not_moved(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        move = {
            "role": "adversarial", "from": "claude-sonnet-5-5", "to": "claude-opus-5-5",
            "calibration_id": "c", "reason": "r",
        }  # fmt: skip
        verdict = tmp_path / "adversarial.json"
        verdict.write_text(
            json.dumps({"role": "adversarial", "passed": False, "tier_move": move}),
            encoding="utf-8",
        )
        with pytest.raises(R.RunError, match="answers no stage of this run"):
            R.escalate_role(run, "adversarial", verdict)

    def test_an_escalation_needs_a_failed_verdict_of_that_role_one_tier_up(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, [MP])
        good = tmp_path / "good.json"
        good.write_text(
            json.dumps({"role": "fact_checker", "passed": True, "tier_move": None}), "utf-8"
        )
        with pytest.raises(R.RunError, match="not a failed calibration"):
            R.escalate_role(run, "fact_checker", good)
        wrong = tmp_path / "wrong.json"
        move = {
            "role": "fact_checker",
            "from": "claude-haiku-5-5",
            "to": "claude-sonnet-5-5",
            "calibration_id": "c",
            "reason": "r",
        }
        wrong.write_text(
            json.dumps({"role": "fact_checker", "passed": False, "tier_move": move}), "utf-8"
        )
        with pytest.raises(R.RunError, match="does not follow the model recorded"):
            R.escalate_role(run, "fact_checker", wrong)
        with pytest.raises(R.RunError, match="not a failed calibration"):
            R.escalate_role(run, "hook_rater", wrong)


# ------------------------------------------------------------------------------ the canary
class TestTheCanary:
    def test_every_check_batch_carries_one_seeded_defect_beside_its_questions(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        handoff = tmp_path / "handoff-check"
        exported = R.export_stage(run, "check", handoff)
        assert exported["canaries"] == 1 and exported["questions"] == 4
        record = R._round(run, "check")
        assert record is not None
        canary = record["canaries"]["check-001"]
        assert (
            canary["label"] == f"canary-{canary['site_id']}" and canary["kind"] in SV.DEFECT_KINDS
        )
        assert canary["site_id"] == record["batches"]["check-001"][0]
        labels = {line["label"] for line in OH.manifest(handoff)}
        assert canary["label"] in labels and len(labels) == 5
        real = (
            handoff
            / next(l for l in OH.manifest(handoff) if l["label"] == canary["site_id"])[
                "prompt_path"
            ]
        )
        flawed = (
            handoff
            / next(l for l in OH.manifest(handoff) if l["label"] == canary["label"])["prompt_path"]
        )
        assert real.read_text("utf-8") != flawed.read_text("utf-8")
        assert canary["card"] in flawed.read_text("utf-8") and canary["card"] not in real.read_text(
            "utf-8"
        )

    def test_a_checker_that_catches_its_canary_is_imported_without_it(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        result = step(run, tmp_path, "check", passes(NAMES))
        assert result["verdicts"] == {"PASS": 4} and result["canaries"] == 1
        assert len(R.stage_records(run)["check"]) == 4

    def test_a_checker_that_passes_its_canary_voids_the_batch_and_nothing_is_written(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        answer_round(run, "check", handoff, passes(NAMES), canary=check_json())
        with pytest.raises(
            R.CanaryPassed, match=r"batch\(es\) check-001 passed the seeded-defect card"
        ) as caught:
            R.import_stage(run, "check", fit=T.fit)
        assert caught.value.batches == ("check-001",)
        assert not (run / "STAGE-check.jsonl").exists()

    def test_a_voided_batch_is_answered_again_by_a_new_agent(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        answer_round(run, "check", handoff, passes(NAMES), canary=check_json())
        moved = R.void_batch(run, handoff, "check-001", fit=T.fit)
        assert moved["voided"] == "check-001" and moved["answers_moved"] == 5
        assert OH.validate(handoff).missing and not list(handoff.glob("*/*/*.answer.json"))
        voided = tmp_path / "handoff-check-void" / "check-001-1"
        assert len(list(voided.rglob("*.answer.json"))) == 5
        record = R._round(run, "check")
        assert record is not None
        for batch_id, members in record["batches"].items():
            for site_id in members:
                put(handoff, "check", batch_id, site_id, check_json(), "fact_checker")
            put(
                handoff,
                "check",
                batch_id,
                record["canaries"][batch_id]["label"],
                CANARY_CAUGHT,
                "fact_checker",
            )
        assert R.import_stage(run, "check", fit=T.fit)["verdicts"] == {"PASS": 4}

    def test_a_batch_whose_canary_was_caught_is_not_voided(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        answer_round(run, "check", handoff, passes(NAMES))
        with pytest.raises(R.RunError, match="caught its canary: the batch stands"):
            R.void_batch(run, handoff, "check-001", fit=T.fit)
        with pytest.raises(R.RunError, match="carries no canary"):
            R.void_batch(run, handoff, "check-009", fit=T.fit)

    def test_the_canary_answer_must_be_in_the_role_too(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        answer_round(run, "check", handoff, passes(NAMES), canary_role="hook_rater")
        with pytest.raises(
            R.RunError, match=r"canary-.*hook_rater:teaser-check-001.*role fact_checker"
        ):
            R.import_stage(run, "check", fit=T.fit)

    def test_check_answer_takes_a_canary_label_as_any_check(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        record = R._round(run, "check")
        assert record is not None
        label = record["canaries"]["check-001"]["label"]
        assert R.check_answer(run, handoff, "check-001", label, CANARY_CAUGHT, fit=T.fit) == {
            "ok": True, "problems": [], "verdict": "FAIL",
        }  # fmt: skip
        bad = R.check_answer(run, handoff, "check-001", label, "{}", fit=T.fit)
        assert bad["ok"] is False
        with pytest.raises(R.RunError, match="is no question"):
            R.check_answer(run, handoff, "check-001", "canary-nobody", CANARY_CAUGHT, fit=T.fit)


# ------------------------------------------------------------------------------ diversity at import
class TestDiversityAtImport:
    def rows(self, cards: dict[str, str]) -> list[dict[str, Any]]:
        return [{"site_id": site, "card": card, "problems": []} for site, card in cards.items()]

    def test_a_repeated_opening_is_the_ratings_finding_and_sends_the_site_to_a_rewrite(
        self,
    ) -> None:
        rows = self.rows(
            {"a": "A bronze mirror lay deep. Words.", "b": "A bronze mirror lay deep. Others."}
        )
        R.rate_diversity(rows, {stage: {} for stage in R.SHORTS_SPEC.stages}, R.SHORTS_SPEC, 200)
        assert rows[0]["problems"] == []
        assert rows[1]["problems"][0].startswith("diversity: another card of the run opens with")

    def test_the_cards_of_the_earlier_rounds_of_other_sites_count(self) -> None:
        records = {stage: {} for stage in R.SHORTS_SPEC.stages}
        records["rate"] = {"x": {"card": "A bronze mirror lay deep. Words."}}
        rows = self.rows({"y": "A bronze mirror lay deep. Others."})
        R.rate_diversity(rows, records, R.SHORTS_SPEC, 200)
        assert rows[0]["problems"] != []
        # but the site's own earlier card does not: it is being replaced
        same = self.rows({"x": "A bronze mirror lay deep. Others."})
        R.rate_diversity(same, records, R.SHORTS_SPEC, 200)
        assert same[0]["problems"] == []

    def test_a_rating_that_fails_diversity_is_a_failed_round(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        # the rating record is imported, then marked: a repeated opening fails the round
        step(run, tmp_path, "rate", rates(run, [MP]))
        path = run / "STAGE-rate.jsonl"
        rows = R.read_jsonl(path)
        rows[0]["problems"] = ["diversity: another card of the run opens with 'x'"]
        R.write_jsonl(path, rows)
        assert R.status(run)["states"] == {"due rewrite1": 1}
        assert R.states(run)[sid(MP)].findings[-1].reasons[-1].startswith("diversity:")


# ------------------------------------------------------------------------------ the briefs
class TestTheBriefs:
    def exported(self, tmp_path: Path, stage: str, names: list[str] = NAMES) -> tuple[Path, Path]:
        run = make_run(tmp_path, names)
        order = ["write", "rate", "check", "verify"]
        answers = {
            "write": writes(names),
            "rate": None,
            "check": passes(names),
        }
        for earlier in order[: order.index(stage)]:
            step(
                run,
                tmp_path,
                earlier,
                answers[earlier] if answers[earlier] is not None else rates(run, names),
            )
        handoff = tmp_path / f"handoff-{stage}"
        R.export_stage(run, stage, handoff)
        return run, handoff

    def test_a_writer_brief_names_the_role_the_fixed_model_and_the_flags(
        self, tmp_path: Path
    ) -> None:
        run, handoff = self.exported(tmp_path, "write")
        text = R.brief(run, handoff, "write-001")
        assert "You are writer write-001 of lane WB, contract shorts-v1" in text
        assert "**card_writer**: your model is **claude-opus-5-5**, effort high" in text
        assert "--role card_writer" in text and "--model claude-opus-5-5" in text
        assert "--answered-by teaser-write-001" in text and "--stage write" in text
        assert "an answer stamped with any other model is refused" in text
        assert "accepts the decline the prompt offers" in text
        assert "Wikipedia cache" not in text

    @pytest.mark.parametrize(
        ("stage", "role", "model", "effort"),
        [
            ("rate", "hook_rater", "claude-opus-5-5", "medium"),
            ("check", "fact_checker", "claude-sonnet-5-5", "high"),
            ("verify", "web_verifier", "claude-sonnet-5-5", "high"),
        ],
    )
    def test_each_stage_names_the_role_the_registry_fixed(
        self, tmp_path: Path, stage: str, role: str, model: str, effort: str
    ) -> None:
        run, handoff = self.exported(tmp_path, stage)
        batch = f"{stage}-001"
        text = R.brief(run, handoff, batch)
        assert f"**{role}**: your model is **{model}**, effort {effort}" in text
        assert f"--role {role}" in text and f"--model {model}" in text

    def test_a_verifier_is_told_where_the_wikipedia_text_is_and_that_a_403_is_no_finding(
        self, tmp_path: Path
    ) -> None:
        run, handoff = self.exported(tmp_path, "verify")
        text = R.brief(run, handoff, "verify-001")
        assert "output/remediation/final-2026-10-08/wiki_cache/INDEX.jsonl" in text
        assert "site_id, lang, title, file" in text and "resolved_title, revid and text" in text
        assert (
            "A 403 or 429 is NEVER a finding" in text and "at most a few requests per site" in text
        )

    def test_the_rater_is_told_it_does_not_know_the_facts(self, tmp_path: Path) -> None:
        run, handoff = self.exported(tmp_path, "rate")
        text = R.brief(run, handoff, "rate-001")
        assert "you do not know and must not look up whether anything is true" in text

    def test_the_agents_of_a_round_are_workflow_ready_jobs(self, tmp_path: Path) -> None:
        run, handoff = self.exported(tmp_path, "verify")
        jobs = R.agent_jobs(run, handoff)
        assert [j["batch_id"] for j in jobs] == ["verify-001"]
        job = jobs[0]
        assert (job["role"], job["model"], job["effort"], job["stage"]) == (
            "web_verifier",
            "claude-sonnet-5-5",
            "high",
            "verify",
        )
        assert job["questions"] == 4 and job["max_parallel"] == 3
        assert job["brief"] == R.brief(run, handoff, "verify-001")
        json.dumps(jobs)
        run2, handoff2 = self.exported(tmp_path / "other", "write")
        assert R.agent_jobs(run2, handoff2)[0]["max_parallel"] is None

    def test_a_v1_run_has_no_roles_and_no_agent_jobs(self, tmp_path: Path) -> None:
        run = tmp_path / "runs" / "wb-v1"
        export = T.tagged({"site": T.production_rows()})

        def read(path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(export, encoding="utf-8", newline="\n")

        R.select(run, read=read, sites_file=None, pilot=None, exclude=[])
        handoff = tmp_path / "h"
        R.export_stage(run, "write", handoff)
        with pytest.raises(R.RunError, match="has no roles"):
            R.agent_jobs(run, handoff)
        assert "--role" not in R.brief(run, handoff, "write-001")

    def test_the_pilots_judge_answers_in_its_role(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        chain(run, tmp_path, [MP])
        R.outcomes(run)
        handoff = tmp_path / "handoff-judge"
        R.export_judge(run, handoff)
        put(handoff, "judge", "judge-001", sid(MP), VERIFIED_ANSWER, "web_verifier")
        with pytest.raises(R.RunError, match="did not answer as role pilot_judge"):
            R.import_judge(run, client=judge_client(), pace=0)
        (handoff / OH.manifest(handoff)[0]["answer_path"]).unlink()
        put(handoff, "judge", "judge-001", sid(MP), VERIFIED_ANSWER, "pilot_judge")
        assert R.import_judge(run, client=judge_client(), pace=0)["pilot"] == "PASS"

    def test_the_pilot_judge_is_the_pilot_judge_role(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        chain(run, tmp_path, [MP])
        R.outcomes(run)
        handoff = tmp_path / "handoff-judge"
        R.export_judge(run, handoff)
        line = OH.manifest(handoff)[0]
        prompt = (handoff / line["prompt_path"]).read_text("utf-8")
        assert prompt == PS.judge_prompt(MP, "Peru", cards_of(MP)[0])
        text = R.brief(run, handoff, "judge-001")
        assert "**pilot_judge**: your model is **claude-opus-5-5**, effort xhigh" in text
        assert "Wikipedia cache" in text


# ------------------------------------------------------------------------------ the re-check run
GAP_RUN = "wb-cardgap-2026-10-07"


#: Cards in the v1 shape, as the MiniMax gap run wrote them: 160-190 characters, naming their site.
GAP_CARDS = {
    MP: "Machu Picchu is a 15th-century Inca citadel on a mountain ridge at 2,430 meters, where studies of skeletal remains show most of its people were immigrants from diverse backgrounds.",
    DENBURY: "Denbury Hill is an Iron Age hill fort in Devon whose entire hilltop, 160 metres above sea level, holds high embankments on the south and east sides and two large burial mounds.",
    HUACA: "The Huaca del Sol is an adobe brick pyramid built by the Moche on the northern coast, estimated at over 130 million adobe bricks, the largest pre-Columbian adobe structure in the Americas.",
}


def gap_row(name: str, **over: Any) -> dict[str, Any]:
    """A live card written by the MiniMax gap run: v1 shape, naming its site."""
    sample = S.BY_NAME[name]
    card = GAP_CARDS[name]
    row = production_row(name, card=card)
    row["card_provenance"] = CP.build(
        run=GAP_RUN,
        ai_system=M.AI_SYSTEM,
        card=card,
        description=sample["description"],
        stage="check",
        checker="teaser-check-001",
        checked_at="2026-10-07T12:00:00+00:00",
        claims=[{"claim": "the site", "support": ["S1", "S2"]}],
        verify={
            "verdict": "VERIFIED",
            "stage": "verify",
            "by": "teaser-verify-001",
            "at": "2026-10-07T13:00:00+00:00",
            "claims": 2,
            "unproven": 0,
            "text_sha256": CP.text_sha256(card),
        },  # fmt: skip
        web_facts=[],
    )
    return {**row, **over}


def seed(tmp_path: Path, names: list[str], extra: list[dict[str, Any]] | None = None) -> Path:
    run = tmp_path / "runs" / "wb-recheck-test"
    export = T.tagged({"site": [gap_row(n) for n in names] + (extra or [])})

    def read(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export, encoding="utf-8", newline="\n")

    R.seed_live(run, read=read, provenance_run=GAP_RUN, fit=T.fit)
    return run


def recheck_step(
    run: Path, tmp_path: Path, stage: str, answers: dict[str, str], **kw: Any
) -> dict[str, Any]:
    handoff = tmp_path / f"handoff-{stage}"
    exported = R.export_stage(run, stage, handoff)
    if not exported["questions"]:
        return exported
    record = R._round(run, stage)
    assert record is not None
    role = R.RECHECK_SPEC.roles[stage]
    for batch_id, members in record["batches"].items():
        for site_id in members:
            put(handoff, stage, batch_id, site_id, answers[site_id], role, kw.get("model"))
        if batch_id in record.get("canaries", {}):
            put(
                handoff,
                stage,
                batch_id,
                record["canaries"][batch_id]["label"],
                CANARY_CAUGHT_V1,
                role,
            )
    if stage in R.RECHECK_SPEC.verifiers:
        return R.import_stage(run, stage, fit=T.fit, client=judge_client(), pace=0)
    return R.import_stage(run, stage, fit=T.fit)


CANARY_CAUGHT_V1 = T.checker_answer("FAIL", [("x", [])], ["The seeded flaw."])


class TestTheRecheckRun:
    def test_the_live_cards_of_the_run_are_seeded_as_the_write_stage(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP, DENBURY], extra=[production_row(HUACA)])
        record = json.loads((run / "RUN.json").read_text("utf-8"))
        assert record["contract"] == "recheck-v1" and record["provenance_run"] == GAP_RUN
        assert record["sites"] == 2 and record["listed"] == {"not-of-run": 1}
        assert set(record["roles"]) == {
            "fact_checker",
            "web_verifier",
            "adversarial",
            "pilot_judge",
        }
        write = R.stage_records(run)["write"]
        assert set(write) == {sid(MP), sid(DENBURY)}
        row = write[sid(MP)]
        assert row["batch_id"] == "seed-live" and row["answered_by"] == f"seed-live:{GAP_RUN}"
        assert row["model"] == OH.MINIMAX_MODEL and row["seeded"] is True
        assert row["card"] == GAP_CARDS[MP] and row["basis"] == ["S1", "S2"]
        assert row["problems"] == C.problems(row["card"], R.bases(run)[sid(MP)], fit=T.fit)
        assert R.status(run)["states"] == {"due check": 2}

    def test_the_seed_lists_the_sites_it_does_not_re_check(self, tmp_path: Path) -> None:
        moved = gap_row(HUACA, card="Another card than the one its provenance hashes. Words here.")
        empty = {
            **gap_row(DENBURY),
            "site_id": "0e000000-0000-4000-8000-000000000001",
            "name": "Empty",
            "description": None,
        }
        retired = {
            **gap_row(DENBURY),
            "site_id": "0e000000-0000-4000-8000-000000000002",
            "name": "Retired",
            "scope_status": "retired",
        }
        no_card = {
            **gap_row(DENBURY),
            "site_id": "0e000000-0000-4000-8000-000000000003",
            "name": "No card",
            "card": None,
        }
        run = seed(
            tmp_path,
            [MP],
            extra=[moved, empty, retired, no_card, production_row(S.SAMPLES[-1]["name"])],
        )
        listed = {r["name"]: r["reason"] for r in R.read_jsonl(run / "LISTED.jsonl")}
        assert listed[HUACA] == "card-changed" and listed["Empty"] == "no-description"
        assert listed["Retired"] == "retired" and listed["No card"] == "no-card-row"
        assert listed[S.SAMPLES[-1]["name"]] == "not-of-run"

    def test_a_run_with_no_card_of_the_run_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="nothing to re-check"):
            seed(tmp_path, [], extra=[production_row(MP)])

    def test_a_recheck_run_is_seeded_once(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP])
        export = T.tagged({"site": [gap_row(MP)]})

        def read(path: Path) -> None:
            path.write_text(export, encoding="utf-8", newline="\n")

        with pytest.raises(R.RunError, match="selected already"):
            R.seed_live(run, read=read, provenance_run=GAP_RUN, fit=T.fit)

    def test_the_write_stage_is_seeded_never_asked(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP])
        with pytest.raises(R.RunError, match="is seeded"):
            R.export_stage(run, "write", tmp_path / "h")
        with pytest.raises(R.RunError, match="is no stage of lane WB contract recheck-v1"):
            R.export_stage(run, "rate", tmp_path / "h")

    def test_a_recheck_run_without_its_seeded_card_is_refused(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP])
        R.write_jsonl(run / "STAGE-write.jsonl", [])
        with pytest.raises(R.RunError, match="no seeded card"):
            R.status(run)

    def test_a_card_that_passes_check_verify_and_adversary_is_confirmed(
        self, tmp_path: Path
    ) -> None:
        run = seed(tmp_path, [MP, DENBURY])
        ok = {sid(n): T.checker_answer() for n in (MP, DENBURY)}
        assert recheck_step(run, tmp_path, "check", ok)["verdicts"] == {"PASS": 2}
        assert recheck_step(run, tmp_path, "verify", verifies([MP, DENBURY]))["verdicts"] == {
            "VERIFIED": 2
        }
        assert recheck_step(run, tmp_path, "adversarial", ok)["verdicts"] == {"PASS": 2}
        handoff = tmp_path / "handoff-adversarial"
        prompt = (handoff / OH.manifest(handoff)[0]["prompt_path"]).read_text("utf-8")
        assert (
            "find the reason it must NOT stay public" in prompt
            and "THE WEB VERIFIER'S EVIDENCE" in prompt
        )
        assert R.status(run)["states"] == {"accepted": 2}
        R.outcomes(run)
        rows = R.read_outcomes(run)
        assert {(r["status"], r["reason"], r["provenance"]) for r in rows} == {
            (R.CONFIRMED, None, None)
        }
        assert (run / "DESCRIPTION_DEFECTS.jsonl").read_text("utf-8") == ""
        assert "confirmed 2" in (run / "OUTCOMES.md").read_text("utf-8")

    @pytest.mark.parametrize(
        ("failing", "reason"),
        [
            ("check", R.RECHECK_CHECK_FAILED),
            ("verify", R.RECHECK_CONTRADICTED),
            ("unproven", R.RECHECK_UNPROVEN),
            ("adversarial", R.RECHECK_ADVERSARIAL_FAILED),
        ],
    )
    def test_any_failure_clears_the_card_with_its_reason(
        self, tmp_path: Path, failing: str, reason: str
    ) -> None:
        run = seed(tmp_path, [MP])
        fail = T.checker_answer("FAIL", [("x", [])], ["Nothing says it."])
        recheck_step(
            run, tmp_path, "check", {sid(MP): fail if failing == "check" else T.checker_answer()}
        )
        if failing != "check":
            if failing == "verify":
                bad = T.judge_answer(
                    T.judged_claim(
                        "CONTRADICTED", "occupied from roughly 3180 BC to around 2500 BC", PAGE
                    )
                )
            elif failing == "unproven":
                bad = T.judge_answer(T.judged_claim("UNVERIFIABLE", None, None))
            else:
                bad = VERIFIED_ANSWER
            recheck_step(run, tmp_path, "verify", {sid(MP): bad})
        if failing == "adversarial":
            recheck_step(run, tmp_path, "adversarial", {sid(MP): fail})
        R.outcomes(run)
        row = outcome(run, MP)
        assert (row["status"], row["reason"], row["card"]) == (R.CLEARED, reason, None)
        assert row["findings"] and "card-clear-" + reason == f"card-clear-{row['reason']}"

    def test_a_re_checked_card_with_a_mechanical_problem_is_cleared_without_a_question(
        self, tmp_path: Path
    ) -> None:
        run = seed(tmp_path, [MP])
        records = R.read_jsonl(run / "STAGE-write.jsonl")
        records[0]["problems"] = ["length: 12"]
        R.write_jsonl(run / "STAGE-write.jsonl", records)
        assert R.status(run)["states"] == {"cleared": 1}
        R.outcomes(run)
        assert outcome(run, MP)["reason"] == R.RECHECK_MECHANICAL

    def test_the_recheck_roles_answer_each_stage(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP])
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        put(handoff, "check", "check-001", sid(MP), T.checker_answer(), "web_verifier")
        record = R._round(run, "check")
        assert record is not None
        put(
            handoff,
            "check",
            "check-001",
            record["canaries"]["check-001"]["label"],
            CANARY_CAUGHT_V1,
            "web_verifier",
        )
        with pytest.raises(R.RunError, match="did not answer as role fact_checker"):
            R.import_stage(run, "check", fit=T.fit)
        text = R.brief(run, handoff, "check-001")
        assert "**fact_checker**" in text and "--model claude-sonnet-5-5" in text
        assert R.agent_jobs(run, handoff)[0]["role"] == "fact_checker"

    def test_a_pilot_judge_is_refused_for_a_recheck_run(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP])
        with pytest.raises(R.RunError, match="no pilot judge"):
            R.export_judge(run, tmp_path / "h")

    def test_the_recheck_check_uses_the_v1_checker_prompt(self, tmp_path: Path) -> None:
        run = seed(tmp_path, [MP])
        handoff = tmp_path / "handoff-check"
        R.export_stage(run, "check", handoff)
        line = next(l for l in OH.manifest(handoff) if l["label"] == sid(MP))
        prompt = (handoff / line["prompt_path"]).read_text("utf-8")
        card = R.stage_records(run)["write"][sid(MP)]["card"]
        assert prompt == P.checker_prompt(R.bases(run)[sid(MP)], card)


# ------------------------------------------------------------------------------ the CLI
class TestTheCommandLine:
    def test_the_new_commands_and_the_contract_option_exist(self) -> None:
        import subprocess

        out = subprocess.run(
            [sys.executable, str(REPO / "scripts/remediation/teaser/run.py"), "--help"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout  # fmt: skip
        for command in ("agents", "void-batch", "seed-live", "escalate"):
            assert command in out
        select = subprocess.run(
            [sys.executable, str(REPO / "scripts/remediation/teaser/run.py"), "select", "--help"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout  # fmt: skip
        assert "--contract" in select and "shorts-v1" in select

    def test_every_stage_of_every_contract_is_a_command_line_choice(self) -> None:
        assert set(R.ALL_STAGES) == {*R.STAGES, *R.SHORTS_SPEC.stages, *R.RECHECK_SPEC.stages}
        assert R.ALL_STAGES.count("verify") == 1
