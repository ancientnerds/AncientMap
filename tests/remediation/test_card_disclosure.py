"""Lane WB's disclosure correction: does exactly one key of exactly the listed sites move?

`mechanical/card_disclosure.py` corrects `_card_provenance.ai_system` of the cards a Sonnet 5.5
rewrite agent wrote while the provenance names Opus only (owner decision 2026-10-01). DB-less:
production is a fixture export, the census and the run outcomes are fixture files, the SQL is asserted
as rendered text or evaluated in SQLite where it is portable (`->`, `->>`, `||`, `coalesce`). The
delivered list is pinned by its sha256; the later acceptances that must accept this lane - by its
stamp, for its one key - are `teaser.py accept` (tested here) and `verify_writes4 --allow-stamp`
(the runbook names the pattern; `test_the_stamp_pattern_names_this_lane_only`).
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import card_disclosure as C  # noqa: E402
from mechanical import card_disclosure_list as LIST  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical import teaser as W  # noqa: E402
from phase4 import model4 as M  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation import test_mechanical_teaser as TT  # noqa: E402
from tests.remediation import test_phase4_accept as TA  # noqa: E402
from tests.remediation.test_mechanical import FOREIGN, ProbeProduction  # noqa: E402

OLD, NEW = M.AI_SYSTEM_OPUS, M.AI_SYSTEM_CLAUDE  # the lane's own pair, not the new-write alias
OPUS, SONNET = "claude-opus-5-5", "claude-sonnet-5-5"
SITES = (T.SKARA, T.NEWGRANGE, T.STONEHENGE)


def test_the_correction_owns_the_two_disclosures_that_are_in_production() -> None:
    """This lane finished on 2026-10-01 and wrote 185 provenances: from the Opus-only string to the
    Claude string of that day. Its pair is pinned to those two strings, never to the alias
    `AI_SYSTEM` that a new write carries - `AI_SYSTEM` names the combined Claude and MiniMax
    disclosure since 2026-10-03, and following it would make a finished lane plan a second
    correction of 185 sites it already corrected."""
    assert C.OLD == M.AI_SYSTEM_OPUS
    assert C.NEW == M.AI_SYSTEM_CLAUDE
    assert C.NEW in M.AI_SYSTEMS
    assert "MiniMax" not in C.NEW and "MiniMax" not in C.OLD
RUN = "wb-test"
NOW = "2026-10-01T00:00:00+00:00"


def provenance(site_id: str, ai_system: str = OLD) -> dict[str, Any]:
    return {**T.teaser(site_id), "ai_system": ai_system}


def raw_of(site_id: str, ai_system: str = OLD) -> dict[str, Any]:
    """A raw_data as production prints it for a card site: Phase 5's key and the teaser's."""
    return {
        "description_citations": [],
        "_description_provenance": {"lane": "W", "card": None},
        "_card_provenance": provenance(site_id, ai_system),
    }


def live_of(site_id: str, ai_system: str = OLD, **over: Any) -> C.Live:
    prov = provenance(site_id, ai_system)
    base = C.Live(
        site_id=site_id,
        name=T.NAMES[site_id],
        scope_status=None,
        raw_data=C.reprint(raw_of(site_id, ai_system)),
        description=T.DESCRIPTIONS[site_id],
        card=T.GOOD[site_id],
        premise=C.premise_of(prov),
    )
    return replace(base, **over)


def listed_of(site_id: str, **over: Any) -> C.Listed:
    base = C.Listed(
        site_id=site_id,
        name=T.NAMES[site_id],
        run=RUN,
        step=1,
        stage="rewrite1",
        answered_by="teaser-wb-test-rewrite1-001",
        answered_at="2026-09-29T20:17:11+00:00",
        true_model=SONNET,
        census_files=("teaser-wb-test-rewrite1\\rewrite1-001\\rewrite1\\x.answer.json",),
        provenance=provenance(site_id),
        card=T.GOOD[site_id],
    )
    return replace(base, **over)


@pytest.fixture()
def pinned(monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    """The pinned list of these tests: the module's name for it is replaced, as the lane, the plan
    and the acceptance all read it through `C.LIST`."""
    ids = tuple(sorted(SITES))
    monkeypatch.setattr(C, "LIST", SimpleNamespace(SITE_IDS=ids, LIST_SHA256=C.list_sha256(ids)))
    return ids


# ------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_a_step_is_a_lane_of_its_own(self, pinned: tuple[str, ...]) -> None:
        lane = C.disclosure_lane(1)
        assert lane.name == "card-disclosure-s001" and lane.key_prefix == lane.name
        assert lane.run_stamp == "wb-card-disclosure-s001"
        assert lane.rollback_run_stamp == "wb-card-disclosure-s001-rollback"
        assert lane.out_dir_name == "mechanical_card_disclosure/s001"
        assert lane.test_id == "WB/card-disclosure" and lane.target is L.UNIFIED_SITES
        (cell,) = lane.cells
        assert (cell.name, cell.sql_type) == ("raw_data", "jsonb")
        assert not cell.clears and not cell.fills_null
        with pytest.raises(MP.PlanError, match="step 2 has no sites"):
            C.disclosure_lane(2)

    def test_the_stamp_pattern_names_this_lane_only(self) -> None:
        """What `teaser.py accept` and the runbook's `--allow-stamp 'wb-card-disclosure-s%'` match:
        the correction's stamps, their reversals, and no stamp of any other lane."""
        for step in (1, 2, 185):
            stamp = f"{W.CORRECTION_STAMP_PREFIX}{step:03d}"
            assert W.CORRECTION_STAMP.match(stamp)
            assert not W.CORRECTION_STAMP.match(stamp + "-rollback")
            assert stamp.startswith("wb-card-disclosure-s")
        for other in (
            "wb-teaser-prov-s001",
            "wb-teaser-card-s001",
            "wb-card-disclosure-x001",
            "wb-card-disclosure-s1",
            "phase4:batch",
            "%",
        ):
            # the SQL read's LIKE only narrows the rows read; the regex decides what counts
            assert not W.CORRECTION_STAMP.match(other)

    def test_the_lane_s_stamp_is_the_one_the_acceptance_names(self, pinned: Any) -> None:
        assert W.CORRECTION_STAMP.match(C.disclosure_lane(1).run_stamp)

    def test_the_lanes_resolve_by_name_for_apply(self, pinned: tuple[str, ...]) -> None:
        assert L.resolve_lane("card-disclosure-s001") == C.disclosure_lane(1)
        assert C.lane_of("card-disclosure-s001") == C.disclosure_lane(1)
        for name in ("card-disclosure-1", "card-disclosure-s0001", "card-disclosure"):
            with pytest.raises(KeyError):
                L.resolve_lane(name)
        assert A.readback_for(C.disclosure_lane(1)) == C.disclosure_readback(C.disclosure_lane(1))
        assert A._lane_argument("card-disclosure-s001") == "card-disclosure-s001"

    def test_the_premise_is_the_provenance_s_identity_and_python_agrees(self) -> None:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE unified_sites (id TEXT, raw_data TEXT)")
        for site in SITES:
            db.execute("INSERT INTO unified_sites VALUES (?, ?)", (site, C.reprint(raw_of(site))))
        for site in SITES:
            sql = f"SELECT {C.PREMISE_SQL} FROM unified_sites u WHERE u.id = ?"
            (got,) = db.execute(sql, (site,)).fetchone()
            assert got == C.premise_of(provenance(site)), site
            # the correction itself does not move it: guard 5 holds for the write and the reversal
            assert got == C.premise_of(provenance(site, NEW))
        db.execute("INSERT INTO unified_sites VALUES ('none', '{}')")
        assert db.execute(
            f"SELECT {C.PREMISE_SQL} FROM unified_sites u WHERE u.id = 'none'"
        ).fetchone() == ("||",)

    def test_the_invariant_refuses_any_provenance_that_names_neither_disclosure(self) -> None:
        """Run on the rows the write and its reversal leave, and on the probe's array."""
        predicate = C._NAMES_NEITHER.predicate
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE unified_sites (id TEXT, raw_data TEXT)")
        rows = {
            "old": C.reprint(raw_of(T.SKARA, OLD)),
            "new": C.reprint(raw_of(T.SKARA, NEW)),
            "other": C.reprint(raw_of(T.SKARA, "Claude Opus (Anthropic): somebody else")),
            "none": "{}",
            "probe": L_NEVER_STORED,
        }
        for key, text in rows.items():
            db.execute("INSERT INTO unified_sites VALUES (?, ?)", (key, text))
        broken = {
            k for (k,) in db.execute(f"SELECT id FROM unified_sites WHERE ({predicate})").fetchall()
        }
        assert broken == {"other", "none", "probe"}

    def test_the_statements_carry_the_premise_and_the_invariant_both_ways(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        records = step_records(tmp_path)
        lane = C.disclosure_lane(1)
        write = A.apply_statement(records, lane)
        undo = A.rollback_statement(records, lane)
        for sql in (write, undo):
            assert f"WHERE ({C.PREMISE_SQL}) IS DISTINCT FROM p.premise;" in sql
            assert "invariant 3, the lane's own" in sql
            assert "SET LOCAL lock_timeout = '10s';" in sql
        assert f"'{lane.run_stamp}'" in write and f"'{lane.rollback_run_stamp}'" in undo

    def test_every_guard_has_its_probe(self, pinned: tuple[str, ...], tmp_path: Path) -> None:
        cases = {c[0] for c in A.probe_cases(step_records(tmp_path), C.disclosure_lane(1), FOREIGN)}
        assert cases == {
            "guard1-other-source",
            "guard2-no-op",
            "guard2-foreign-column",
            "guard3-foreign-old-value",
            "guard5-premise",
            "invariant-lane",
        }

    def test_the_probes_are_each_refused_by_their_own_guard(
        self,
        pinned: tuple[str, ...],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        records = step_records(tmp_path)
        lane = C.disclosure_lane(1)
        ProbeProduction(lane, records, monkeypatch)
        assert A.cmd_probe_guards(records, tmp_path, lane) == 0
        assert capsys.readouterr().out.count("refused by its own guard=True") == 6

    def test_a_card_provenance_is_the_one_key_the_plan_side_mirror_lets_through(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        records = step_records(tmp_path)
        A.validate_records(records, lane=C.disclosure_lane(1))
        with pytest.raises(MP.PlanError, match="premise"):
            A.validate_records(
                [replace(records[0], premise=None), *records[1:]], lane=C.disclosure_lane(1)
            )


#: What the probe's `invariant-lane` writes into a jsonb cell (`apply.NEVER_STORED["jsonb"]`).
L_NEVER_STORED = A.NEVER_STORED["jsonb"]


def step_records(directory: Path) -> list[A.ChangeRecord]:
    """The records of step 1 over the three fixture sites, written and read as apply.py reads them."""
    live = {s: live_of(s) for s in SITES}
    plan = C.build_step(1, [listed_of(s) for s in SITES], live, {}, built_at=NOW)
    MP.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    return A.load_records(directory / "PLAN.jsonl")


# ------------------------------------------------------------------------------ the pinned list
class TestThePinnedList:
    def test_the_delivered_list_is_pinned_by_its_sha256(self) -> None:
        ids = LIST.SITE_IDS
        assert len(ids) == 185
        assert list(ids) == sorted(set(ids))
        assert all(MP.UUID_RE.match(site_id) for site_id in ids)
        assert C.list_sha256(ids) == LIST.LIST_SHA256
        assert (
            LIST.LIST_SHA256 == "af59f0ffc82f8f7de63878fe80d69128b4adf133e2576920c9960b8d3ad913c1"
        )

    def test_the_module_is_what_list_write_renders(self) -> None:
        text = (REPO / "scripts/remediation/mechanical/card_disclosure_list.py").read_text(
            encoding="utf-8"
        )
        assert text == C.module_text(LIST.SITE_IDS)

    def test_the_list_makes_two_steps_and_every_site_is_in_one(self) -> None:
        assert [len(C.step_sites(step)) for step in (1, 2)] == [100, 85]
        assert C.step_sites(1) + C.step_sites(2) == LIST.SITE_IDS
        for step in (0, 3, -1):
            with pytest.raises(MP.PlanError, match="has no sites"):
                C.step_sites(step)

    def test_every_real_step_resolves_to_a_lane(self) -> None:
        for step in (1, 2):
            lane = C.disclosure_lane(step)
            assert lane.post_commit_residual.predicate.count("'") >= 2 * len(C.step_sites(step))

    def test_a_list_without_sites_is_the_empty_hash(self) -> None:
        assert (
            C.list_sha256(()) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        assert "SITE_IDS: tuple[str, ...] = ()" in C.module_text(())


# ------------------------------------------------------------------------------ the list builder
def census_row(by: str, at: str, model: str, name: str = "x") -> dict[str, Any]:
    return {
        "file": f"{by}\\b\\{name}.answer.json",
        "answered_by": by,
        "answered_at": at,
        "stamp": "anthropic/claude-opus-5-5 (Claude Code agent)",
        "true_model": model,
        "how": "name+window",
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


class Fixture:
    """A teaser root with closed steps, the runs' outcomes and a census, in a temp directory."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "mechanical_teaser"
        self.runs = tmp_path / "runs"
        self.census = tmp_path / "census.jsonl"
        self.steps: list[dict[str, Any]] = []
        self.outcomes: dict[str, list[dict[str, Any]]] = {}
        self.census_rows: list[dict[str, Any]] = []

    def writer(self, n: int, stage: str = "write") -> dict[str, str]:
        return {
            "stage": stage,
            "answered_by": f"teaser-wb-test-{stage}-{n:03d}",
            "answered_at": f"2026-09-29T20:17:{n:02d}+00:00",
        }

    def card(
        self,
        site_id: str,
        *,
        stage: str = "rewrite1",
        model: str | None = SONNET,
        ai_system: str = OLD,
        step: int = 1,
        run: str = RUN,
        n: int = 1,
        status: str = W.ACCEPTED,
    ) -> None:
        writer = self.writer(n, stage)
        prov = provenance(site_id, ai_system)
        self.outcomes.setdefault(run, []).append(
            {
                "site_id": site_id,
                "name": T.NAMES[site_id],
                "status": status,
                "card": T.GOOD[site_id],
                "writer": writer,
                "provenance": prov,
            }
        )
        if model is not None:
            self.census_rows.append(census_row(writer["answered_by"], writer["answered_at"], model))
        step_row = next((s for s in self.steps if s["step"] == step), None)
        if step_row is None:
            step_row = {"step": step, "run": run, "cells": []}
            self.steps.append(step_row)
        step_row["cells"].append({"site_id": site_id, "new_value": C.reprint({PROV: prov})})

    def build(self, *, accepted: tuple[int, ...] = (1,), reverted: tuple[int, ...] = ()) -> None:
        write_jsonl(
            self.root / "STEPS.jsonl",
            [{"step": s["step"], "run": s["run"], "outcomes": []} for s in self.steps],
        )
        for s in self.steps:
            write_jsonl(self.root / W.step_name(s["step"]) / "prov" / "PLAN.jsonl", s["cells"])
        for kind in (W.ACCEPTED_DIR, W.REVERTED_DIR):
            shutil.rmtree(self.root / kind, ignore_errors=True)
        for n in accepted:
            W._record_closing(W.ACCEPTED_DIR, n, self.root, {})
        for n in reverted:
            W._record_closing(W.REVERTED_DIR, n, self.root, {})
        for run, rows in self.outcomes.items():
            write_jsonl(self.runs / run / "OUTCOMES.jsonl", rows)
        write_jsonl(self.census, self.census_rows)

    def list(self) -> list[C.Listed]:
        return C.build_list(root=self.root, runs=self.runs, census=self.census)


PROV = CP.CARD_PROVENANCE_KEY


class TestTheListBuilder:
    def test_a_card_a_sonnet_rewrite_wrote_under_the_opus_only_disclosure_is_listed(
        self, tmp_path: Path
    ) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, stage="rewrite-v")
        fx.build()
        (item,) = fx.list()
        assert (item.site_id, item.run, item.step, item.stage) == (T.SKARA, RUN, 1, "rewrite-v")
        assert item.true_model == SONNET and item.provenance["ai_system"] == OLD
        assert item.card == T.GOOD[T.SKARA] and item.census_files
        assert item.row()["true_model"] == SONNET

    def test_a_card_an_opus_agent_wrote_is_not_listed(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, stage="write", model=OPUS)
        fx.card(T.NEWGRANGE, stage="rewrite1", model=OPUS, n=2)
        fx.build()
        assert fx.list() == []

    def test_a_disclosure_that_already_names_both_models_is_not_listed(
        self, tmp_path: Path
    ) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, ai_system=NEW)
        fx.build()
        assert fx.list() == []

    def test_the_list_is_sorted_by_site_and_deterministic(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        for n, site in enumerate((T.STONEHENGE, T.SKARA, T.NEWGRANGE), start=1):
            fx.card(site, n=n)
        fx.build()
        ids = [item.site_id for item in fx.list()]
        assert ids == sorted(SITES) == [item.site_id for item in fx.list()]
        assert C.summary(fx.list())["sites"] == 3 and C.summary(fx.list())["steps"] == 1

    def test_only_a_closed_step_that_stands_counts(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, step=1)
        fx.card(T.NEWGRANGE, step=2, n=2)
        fx.card(T.STONEHENGE, step=3, n=3)
        fx.build(accepted=(1, 2), reverted=(2,))
        assert [item.site_id for item in fx.list()] == [T.SKARA]

    def test_a_later_step_that_planned_the_site_again_wins(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, step=1, model=SONNET, n=1)
        fx.card(T.SKARA, step=2, model=OPUS, stage="write", n=2)
        fx.build(accepted=(1, 2))
        assert fx.list() == []

    def test_a_cleared_card_leaves_no_provenance_to_correct(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, step=1)
        fx.card(T.SKARA, step=2, n=2)
        fx.build(accepted=(1, 2))
        write_jsonl(
            fx.root / "s002" / "prov" / "PLAN.jsonl", [{"site_id": T.SKARA, "new_value": "{}"}]
        )
        assert fx.list() == []

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"model": None}, "no model"),
            ({"model": "ambiguous:claude-opus-5-5+claude-sonnet-5-5"}, "never a guess"),
            ({"model": "claude-haiku-5"}, "never a guess"),
        ],
        ids=["no-census-row", "ambiguous", "unknown-model"],
    )
    def test_a_writer_the_census_cannot_name_is_refused(
        self, tmp_path: Path, change: dict[str, Any], message: str
    ) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, **change)
        fx.build()
        with pytest.raises(MP.PlanError, match=message):
            fx.list()

    def test_two_different_models_for_one_answer_are_refused(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA)
        fx.census_rows.append(
            census_row(fx.census_rows[0]["answered_by"], fx.census_rows[0]["answered_at"], OPUS)
        )
        fx.build()
        with pytest.raises(MP.PlanError, match="never a guess"):
            fx.list()

    def test_two_files_of_one_model_are_one_answer(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA)
        fx.census_rows.append(
            census_row(
                fx.census_rows[0]["answered_by"], fx.census_rows[0]["answered_at"], SONNET, "y"
            )
        )
        fx.build()
        (item,) = fx.list()
        assert len(item.census_files) == 2

    def test_a_provenance_that_is_not_the_runs_outcome_is_refused(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA)
        fx.build()
        rows = fx.outcomes[RUN]
        rows[0] = {**rows[0], "provenance": provenance(T.SKARA, NEW)}
        write_jsonl(fx.runs / RUN / "OUTCOMES.jsonl", rows)
        with pytest.raises(MP.PlanError, match="is not run .*'s accepted outcome"):
            fx.list()

    def test_a_site_the_outcomes_do_not_know_is_refused(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA)
        fx.build()
        write_jsonl(fx.runs / RUN / "OUTCOMES.jsonl", [])
        with pytest.raises(MP.PlanError, match="accepted outcome"):
            fx.list()

    def test_a_missing_outcomes_file_or_census_is_refused(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA)
        fx.build()
        (fx.runs / RUN / "OUTCOMES.jsonl").unlink()
        with pytest.raises(MP.PlanError, match="does not exist"):
            fx.list()
        fx.census.unlink()
        with pytest.raises(MP.PlanError, match="census is not there"):
            fx.list()

    def test_a_provenance_that_names_a_third_system_is_refused(self, tmp_path: Path) -> None:
        fx = Fixture(tmp_path)
        fx.card(T.SKARA, ai_system="Claude Opus (Anthropic): test")
        fx.build()
        with pytest.raises(MP.PlanError, match="neither disclosure"):
            fx.list()

    def test_the_list_check_compares_with_the_pinned_module(
        self, tmp_path: Path, pinned: tuple[str, ...], capsys: pytest.CaptureFixture[str]
    ) -> None:
        fx = Fixture(tmp_path)
        for n, site in enumerate(SITES, start=1):
            fx.card(site, n=n)
        fx.build()
        argv = ["list", "--check", "--teaser-root", str(fx.root), "--runs", str(fx.runs),
                "--census", str(fx.census)]  # fmt: skip
        assert C.main(argv) == 0
        assert "the pinned list holds: 3 sites" in capsys.readouterr().out
        fx.card(T.SACSAY, n=9)
        fx.build()
        assert C.main(argv) == 1
        assert "is not the pinned one" in capsys.readouterr().err

    def test_list_write_writes_the_file_and_the_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fx = Fixture(tmp_path)
        for n, site in enumerate(SITES, start=1):
            fx.card(site, n=n)
        fx.build()
        module = tmp_path / "card_disclosure_list.py"
        monkeypatch.setattr(C, "LIST_MODULE", module)
        argv = ["--root", str(tmp_path / "out"), "list", "--write", "--teaser-root", str(fx.root),
                "--runs", str(fx.runs), "--census", str(fx.census)]  # fmt: skip
        assert C.main(argv) == 0
        rows = [
            json.loads(x) for x in (tmp_path / "out" / "LIST.jsonl").read_text("utf-8").splitlines()
        ]
        assert [r["site_id"] for r in rows] == sorted(SITES)
        namespace: dict[str, Any] = {}
        exec(compile(module.read_text(encoding="utf-8"), "module", "exec"), namespace)  # noqa: S102
        assert namespace["SITE_IDS"] == tuple(sorted(SITES))
        assert namespace["LIST_SHA256"] == C.list_sha256(sorted(SITES))


# ------------------------------------------------------------------------------ the decision
def classify(
    item: C.Listed, live: C.Live | None, journal: list[MP.JournalLink] | None = None
) -> MP.Verdict:
    return C.classify(item, live, journal or [])


class TestTheDecision:
    def test_the_one_key_is_corrected_and_nothing_else(self) -> None:
        verdict = classify(listed_of(T.SKARA), live_of(T.SKARA))
        assert verdict.ok and verdict.column == "raw_data" and verdict.rule == "card-disclosure"
        before, after = json.loads(verdict.old_value), json.loads(verdict.new_value)
        assert before[PROV]["ai_system"] == OLD and after[PROV]["ai_system"] == NEW
        before[PROV]["ai_system"] = NEW
        assert before == after, "every other key, at every depth, is as it was"
        assert verdict.new_value == C.reprint(after)
        assert verdict.premise == C.premise_of(provenance(T.SKARA))
        assert W.names_opus_only(json.loads(verdict.old_value))
        assert not W.names_opus_only(json.loads(verdict.new_value))

    def test_the_key_order_of_raw_data_is_kept(self) -> None:
        verdict = classify(listed_of(T.SKARA), live_of(T.SKARA))
        assert list(json.loads(verdict.new_value)) == list(json.loads(verdict.old_value))
        assert list(json.loads(verdict.new_value)[PROV]) == list(
            json.loads(verdict.old_value)[PROV]
        )

    def test_the_evidence_is_the_census_the_outcome_and_the_two_disclosures(self) -> None:
        census, written, disclosure = classify(listed_of(T.SKARA), live_of(T.SKARA)).evidence
        assert (
            census["url"] == C.CENSUS_SOURCE and "true_model claude-sonnet-5-5" in census["quote"]
        )
        assert "stage rewrite1" in written["source"] and written["quote"] == T.GOOD[T.SKARA]
        assert OLD in disclosure["quote"] and NEW in disclosure["quote"]

    @pytest.mark.parametrize(
        ("live", "reason"),
        [
            (lambda: None, C.NOT_CURATED),
            (lambda: live_of(T.SKARA, raw_data=None), C.NO_PROVENANCE),
            (lambda: live_of(T.SKARA, raw_data="[1]"), C.RAW_DATA_NOT_OBJECT),
            (lambda: live_of(T.SKARA, raw_data="{}"), C.NO_PROVENANCE),
            (
                lambda: live_of(T.SKARA, raw_data=json.dumps(raw_of(T.SKARA), indent=1)),
                C.NOT_REPRINTED,
            ),
            (lambda: live_of(T.SKARA, NEW), C.ALREADY_CORRECTED),
        ],
        ids=["gone", "null", "not-object", "no-key", "not-reprinted", "already"],
    )
    def test_a_site_that_cannot_be_corrected_is_listed_not_written(
        self, live: Any, reason: str
    ) -> None:
        verdict = classify(listed_of(T.SKARA), live())
        assert not verdict.ok and verdict.reason == reason and verdict.new_value is None

    def test_a_card_written_again_since_is_listed_not_corrected(self) -> None:
        moved = raw_of(T.SKARA)
        moved[PROV] = {**moved[PROV], "run": "another-run"}
        verdict = classify(listed_of(T.SKARA), live_of(T.SKARA, raw_data=C.reprint(moved)))
        assert verdict.reason == C.PROVENANCE_MOVED

    def test_a_raw_data_key_that_moved_is_not_corrected_around(self) -> None:
        """Another key changed: the listed provenance is intact, so the site is written - but only
        its own key moves, and the other key keeps its live value."""
        moved = {**raw_of(T.SKARA), "extra": {"a": 1}}
        verdict = classify(listed_of(T.SKARA), live_of(T.SKARA, raw_data=C.reprint(moved)))
        assert verdict.ok and json.loads(verdict.new_value)["extra"] == {"a": 1}

    def test_a_journal_that_does_not_end_at_the_live_value_lists_the_site(self) -> None:
        stale = [MP.JournalLink(7, "x", "t", None, C.canonical(C.reprint({"a": 1})))]
        verdict = classify(listed_of(T.SKARA), live_of(T.SKARA), stale)
        assert verdict.reason == "journal-disagrees"
        chain = [
            MP.JournalLink(7, "x", "t", None, '{"a": 1}'),
            MP.JournalLink(8, "x", "t", '{"a": 2}', C.canonical(live_of(T.SKARA).raw_data)),
        ]
        assert (
            classify(listed_of(T.SKARA), live_of(T.SKARA), chain).reason == "journal-chain-broken"
        )
        good = [MP.JournalLink(7, "x", "t", None, C.canonical(live_of(T.SKARA).raw_data))]
        assert classify(listed_of(T.SKARA), live_of(T.SKARA), good).ok

    def test_an_export_that_is_not_one_snapshot_is_refused(self) -> None:
        with pytest.raises(MP.PlanError, match="not one snapshot"):
            classify(listed_of(T.SKARA), live_of(T.SKARA, premise="r|t|d"))

    def test_correct_disclosure_changes_only_its_key_and_only_from_the_opus_value(self) -> None:
        raw = raw_of(T.SKARA)
        corrected = W.correct_disclosure(raw)
        assert corrected[PROV]["ai_system"] == NEW and raw[PROV]["ai_system"] == OLD
        assert {k: v for k, v in corrected[PROV].items() if k != "ai_system"} == {
            k: v for k, v in raw[PROV].items() if k != "ai_system"
        }
        for bad in (raw_of(T.SKARA, NEW), {}, {PROV: "x"}, {PROV: {"ai_system": "other"}}):
            with pytest.raises(MP.PlanError, match="is not"):
                W.correct_disclosure(bad)


# ------------------------------------------------------------------------------ the step
def export_for(lives: list[C.Live], journal: list[dict[str, Any]] | None = None) -> str:
    return T.tagged(
        {
            "site": [
                {
                    "site_id": s.site_id,
                    "name": s.name,
                    "scope_status": s.scope_status,
                    "raw_data": s.raw_data,
                    "description": s.description,
                    "card": s.card,
                    "premise": s.premise,
                }
                for s in lives
            ],  # fmt: skip
            "journal": journal or [],
        }
    )


def a_step(tmp_path: Path, *, lives: list[C.Live] | None = None, root: Path | None = None) -> Path:
    root = root or tmp_path / "mechanical_card_disclosure"
    C.plan_step(
        1,
        read=lambda _sql: export_for(lives or [live_of(s) for s in SITES]),
        root=root,
        listed=[listed_of(s) for s in SITES],
    )
    return root


class TestThePlan:
    def test_a_step_writes_its_plan_the_undo_and_the_listing(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        root = a_step(tmp_path)
        out = root / "s001"
        assert sorted(p.name for p in out.iterdir()) == [
            "PLAN.jsonl", "PLAN.md", "ROLLBACK.sql", "SKIPPED.jsonl", "export.jsonl",
        ]  # fmt: skip
        rows = A.load_records(out / "PLAN.jsonl")
        assert len(rows) == 3 and {r.column for r in rows} == {"raw_data"}
        A.validate_records(rows, lane=C.disclosure_lane(1))
        undo = (out / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert undo.startswith("-- plan sha256 ") and "wb-card-disclosure-s001-rollback" in undo
        page = (out / "PLAN.md").read_text(encoding="utf-8")
        assert "3 site(s) written, 0 listed" in page and T.NAMES[T.SKARA] in page
        assert A.emit(rows, out, C.disclosure_lane(1), plan_path=out / "PLAN.jsonl") == 3

    def test_a_listed_site_is_in_skipped_and_not_in_the_plan(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        lives = [live_of(T.SKARA, NEW), live_of(T.NEWGRANGE), live_of(T.STONEHENGE)]
        root = a_step(tmp_path, lives=lives)
        skipped = [
            json.loads(x) for x in (root / "s001" / "SKIPPED.jsonl").read_text("utf-8").splitlines()
        ]
        assert [(s["site_id"], s["reason"]) for s in skipped] == [(T.SKARA, C.ALREADY_CORRECTED)]
        assert len(A.load_records(root / "s001" / "PLAN.jsonl")) == 2
        assert "`already-corrected` | 1 |" in (root / "s001" / "PLAN.md").read_text(
            encoding="utf-8"
        )

    def test_a_step_is_planned_once(self, pinned: tuple[str, ...], tmp_path: Path) -> None:
        root = a_step(tmp_path)
        with pytest.raises(MP.PlanError, match="planned once"):
            C.plan_step(1, read=lambda _s: "", root=root, listed=[listed_of(s) for s in SITES])

    def test_the_next_step_waits_for_the_acceptance_of_the_last(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ids = tuple(f"{i:08d}-0000-4000-8000-000000000000" for i in range(101))
        monkeypatch.setattr(C, "LIST", SimpleNamespace(SITE_IDS=ids))
        with pytest.raises(MP.PlanError, match="step 1 has no acceptance"):
            C.plan_step(2, read=lambda _s: "", root=tmp_path, listed=[])

    def test_a_list_that_is_not_the_pinned_one_is_refused(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        live = {s: live_of(s) for s in SITES}
        with pytest.raises(MP.PlanError, match="not the pinned list"):
            C.build_step(1, [listed_of(T.SKARA)], live, {}, built_at=NOW)
        with pytest.raises(MP.PlanError, match="not the pinned list"):
            C.build_step(1, [listed_of(s) for s in (*SITES, T.SACSAY)], live, {}, built_at=NOW)

    def test_the_read_is_one_read_only_snapshot_of_the_steps_sites(self, pinned: Any) -> None:
        script = MP.tagged_export_script(
            [("site", C.site_sql(C.step_sites(1))), ("journal", C.journal_sql(C.step_sites(1)))]
        )
        assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script
        for site in SITES:
            assert f"'{site}'" in script
        assert C.PREMISE_SQL in script and "column_name = 'raw_data'" in script
        assert not re.search(r"(?i)\b(insert|update|delete|truncate|drop)\b", script)


# ------------------------------------------------------------------------------ the acceptance
def written_state() -> tuple[list[C.Live], list[dict[str, Any]], list[dict[str, Any]]]:
    """Production after the step's lane ran as planned: plan rows, live rows, the journal."""
    plan = C.build_step(
        1, [listed_of(s) for s in SITES], {s: live_of(s) for s in SITES}, {}, built_at=NOW
    )
    rows = [
        {"site_id": v.site_id, "old_value": v.old_value, "new_value": v.new_value}
        for v in plan.changes
    ]
    lives = [live_of(s, NEW) for s in SITES]
    journal = [
        {"row_pk": r["site_id"], "column_name": "raw_data", "run_stamp": "wb-card-disclosure-s001",
         "old_value": r["old_value"], "new_value": r["new_value"]}
        for r in rows
    ]  # fmt: skip
    return lives, rows, journal


@pytest.fixture()
def accepting(pinned: tuple[str, ...], tmp_path: Path) -> Any:
    root = tmp_path / "mechanical_card_disclosure"
    a_step(tmp_path, root=root)

    def accept(lives: list[C.Live], journal: list[dict[str, Any]]) -> tuple[int, list[str]]:
        return C.accept_step(1, read=lambda _sql: export_for(lives, journal), root=root)

    accept.root = root  # type: ignore[attr-defined]
    return accept


class TestTheAcceptance:
    def test_the_written_step_is_accepted_once(self, accepting: Any) -> None:
        lives, _rows, journal = written_state()
        assert accepting(lives, journal) == (0, [])
        record = accepting.root / "ACCEPTED" / "step-001.json"
        assert record.exists() and json.loads(record.read_text("utf-8"))["sites"] == 3
        record.write_text('{"first": true}', encoding="utf-8")
        assert accepting(lives, journal) == (0, [])
        assert json.loads(record.read_text("utf-8")) == {"first": True}

    def test_a_step_that_was_not_written_is_not_accepted(self, accepting: Any) -> None:
        lives = [live_of(s) for s in SITES]
        code, found = accepting(lives, [])
        assert code == 1 and not (accepting.root / "ACCEPTED").exists()
        assert any("does not hold the planned value" in line for line in found)
        assert any("0 journal row(s) for 3 planned" in line for line in found)

    def test_a_rollback_row_is_a_deviation(self, accepting: Any) -> None:
        lives, _rows, journal = written_state()
        undo = {**journal[0], "run_stamp": "wb-card-disclosure-s001-rollback"}
        code, found = accepting(lives, [*journal, undo])
        assert code == 1 and any("rollback journal row" in line for line in found)

    def test_a_journal_row_that_is_not_the_plans_is_a_deviation(self, accepting: Any) -> None:
        lives, _rows, journal = written_state()
        journal[0] = {**journal[0], "old_value": '{"other": 1}'}
        _code, found = accepting(lives, journal)
        assert any("the journal row is not the plan's" in line for line in found)

    def test_a_site_that_moved_after_the_write_is_a_deviation(self, accepting: Any) -> None:
        lives, _rows, journal = written_state()
        other = json.loads(lives[0].raw_data)
        other["extra"] = 1
        lives[0] = replace(lives[0], raw_data=C.reprint(other))
        _code, found = accepting(lives, journal)
        assert any("does not hold the planned value" in line for line in found)

    def test_a_provenance_that_no_longer_hashes_the_card_is_a_deviation(
        self, accepting: Any
    ) -> None:
        lives, _rows, journal = written_state()
        lives[0] = replace(lives[0], card="Another card.")
        _code, found = accepting(lives, journal)
        assert any("does not hash the live card" in line for line in found)

    def test_a_correction_that_moved_more_than_one_key_is_a_deviation(self, accepting: Any) -> None:
        """Plan and journal alike must be the one-key transition: a plan that also drops a key is
        refused even when production holds exactly what it planned."""
        lives, rows, journal = written_state()
        at = next(i for i, row in enumerate(rows) if row["site_id"] == T.SKARA)
        wide = json.loads(rows[at]["new_value"])
        wide["description_citations"] = ["x"]
        rows[at] = {**rows[at], "new_value": C.reprint(wide)}
        by_site = {s.site_id: s for s in lives}
        by_site[T.SKARA] = replace(by_site[T.SKARA], raw_data=C.reprint(wide))
        journal[at] = {**journal[at], "new_value": C.reprint(wide)}
        found = C.deviations(1, rows, by_site, journal)
        assert any("changes more than the one key" in line for line in found)
        assert any("journal row changed more than the one key" in line for line in found)

    def test_moves_one_key_is_exactly_the_correction(self) -> None:
        old = C.reprint(raw_of(T.SKARA))
        new = C.reprint(raw_of(T.SKARA, NEW))
        assert W.moves_one_key(old, new)
        assert not W.moves_one_key(new, old) and not W.moves_one_key(old, old)
        assert not W.moves_one_key(None, new) and not W.moves_one_key(old, None)
        assert not W.moves_one_key(old, C.reprint({**raw_of(T.SKARA, NEW), "extra": 1}))

    @pytest.mark.parametrize(("before", "after"), [(1, True), (0, False), (1, 1.0)])
    def test_moves_one_key_reads_a_value_spelled_otherwise_as_another_key(
        self, before: Any, after: Any
    ) -> None:
        """Python reads 1 == True == 1.0; the journal does not: the second key moved."""
        old = C.reprint({**raw_of(T.SKARA), "flag": before})
        assert W.moves_one_key(old, C.reprint({**raw_of(T.SKARA, NEW), "flag": before}))
        assert not W.moves_one_key(old, C.reprint({**raw_of(T.SKARA, NEW), "flag": after}))

    def test_a_replan_of_a_corrected_site_from_the_opus_only_outcome_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The outcomes of runs 01/04/06 still name `AI_SYSTEM_OPUS`; writing one again would undo
        the correction, so the planner lists the site instead."""
        monkeypatch.setattr(W.CORRECTED, "SITE_IDS", (T.SKARA,))
        refused = W.classify(outcome(), TT.live(), {}, RUN)
        assert isinstance(refused, W.Verdict) and refused.reason == W.DISCLOSURE_CORRECTED
        # the same outcome rebuilt with the current disclosure is planned, a site off the list is untouched
        rebuilt = TT.outcome(T.SKARA, provenance={**OPUS_PROV, "ai_system": NEW})
        assert not isinstance(W.classify(rebuilt, TT.live(), {}, RUN), W.Verdict)
        monkeypatch.setattr(W.CORRECTED, "SITE_IDS", ())
        assert not isinstance(W.classify(outcome(), TT.live(), {}, RUN), W.Verdict)


# ------------------------------------------------------------------------------ lane WB's accept
OPUS_PROV = {**T.teaser(T.SKARA), "ai_system": OLD}


def outcome(**over: Any) -> dict[str, Any]:
    return TT.outcome(T.SKARA, provenance=OPUS_PROV, **over)


def step_one(tmp_path: Path) -> tuple[Path, list[W.Live], list[dict[str, Any]], str]:
    """Lane WB's step 1 planned for the Skara Brae card, written as planned: its root, production's
    sites, the step's journal, and the provenance cell it wrote."""
    root = tmp_path / "mechanical_teaser"
    W.plan_step(
        RUN,
        1,
        read=lambda _sql: TT.export_for([TT.live()]),
        root=root,
        outcomes=[outcome()],
    )
    prov, card = W.classify(outcome(), TT.live(), {}, RUN)
    journal = [
        {"row_pk": T.SKARA, "column_name": v.column, "run_stamp": stamp,
         "old_value": v.old_value, "new_value": v.new_value}
        for v, stamp in ((prov, TT.PROV.run_stamp), (card, TT.CARD.run_stamp))
    ]  # fmt: skip
    return root, [TT.live(raw_data=prov.new_value, card=card.new_value)], journal, prov.new_value


def accept_teaser(
    tmp_path: Path, root: Path, lives: list[W.Live], journal: list[dict[str, Any]]
) -> tuple[int, list[str]]:
    """`teaser.py accept --step 1` against fixture production; the run's outcomes under `W.RUNS`."""
    write_jsonl(tmp_path / "runs" / RUN / "OUTCOMES.jsonl", [outcome()])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(W, "RUNS", tmp_path / "runs")
        return W.accept_step(1, read=lambda _sql: TT.export_for(lives, journal), root=root)


def correction(old: str, **over: Any) -> dict[str, Any]:
    new = C.reprint(W.correct_disclosure(json.loads(old)))
    row = {"row_pk": T.SKARA, "column_name": "raw_data", "run_stamp": "wb-card-disclosure-s001",
           "old_value": old, "new_value": new}  # fmt: skip
    return {**row, **over}


class TestLaneWbAcceptsTheCorrectionByNameForItsOneKey:
    def test_the_step_as_written_is_accepted(self, tmp_path: Path) -> None:
        root, lives, journal, _planned = step_one(tmp_path)
        assert accept_teaser(tmp_path, root, lives, journal) == (0, [])

    def test_the_step_after_its_site_was_corrected_is_still_accepted(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = correction(planned)
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        assert accept_teaser(tmp_path, root, lives, [*journal, entry]) == (0, [])

    def test_without_the_correction_in_the_journal_the_moved_cell_is_a_deviation(
        self, tmp_path: Path
    ) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        lives[0] = replace(lives[0], raw_data=correction(planned)["new_value"])
        code, found = accept_teaser(tmp_path, root, lives, journal)
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    @pytest.mark.parametrize(
        "change",
        [
            {"run_stamp": "wb-teaser-prov-s099"},
            {"run_stamp": "wb-card-disclosure-x001"},
            {"run_stamp": "2026-09-25_mechanical-orphan-citations"},
            {"column_name": "description"},
            {"row_pk": T.NEWGRANGE},
        ],
        ids=["other-wb-stamp", "lookalike", "another-lane", "another-column", "another-site"],
    )
    def test_no_other_lane_is_accepted(self, tmp_path: Path, change: dict[str, Any]) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = correction(planned, **change)
        lives[0] = replace(lives[0], raw_data=correction(planned)["new_value"])
        code, found = accept_teaser(tmp_path, root, lives, [*journal, entry])
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    def test_only_the_one_key_is_accepted(self, tmp_path: Path) -> None:
        """The correction's journal row moved another key too: its stamp is the right one, its value
        is not the one-key transition, so the cell is not the step's."""
        root, lives, journal, planned = step_one(tmp_path)
        wide = {**W.correct_disclosure(json.loads(planned)), "extra": 1}
        entry = correction(planned, new_value=C.reprint(wide))
        lives[0] = replace(lives[0], raw_data=C.reprint(wide))
        code, found = accept_teaser(tmp_path, root, lives, [*journal, entry])
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    def test_a_correction_from_another_value_is_not_the_steps(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        changed = {**json.loads(planned), "extra": 1}
        entry = correction(C.reprint(changed))
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        code, _found = accept_teaser(tmp_path, root, lives, [*journal, entry])
        assert code == 1

    def test_the_journal_row_must_start_at_the_value_the_step_wrote(self, tmp_path: Path) -> None:
        """Production holds the one-key value, but the correction's journal row says it started
        from another raw_data: something moved the cell around the step, which the step's
        acceptance does not explain."""
        root, lives, journal, planned = step_one(tmp_path)
        entry = correction(planned)
        around = correction(
            C.reprint({**json.loads(planned), "extra": 1}), new_value=entry["new_value"]
        )
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        code, found = accept_teaser(tmp_path, root, lives, [*journal, around])
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    def test_the_journal_row_must_end_at_the_value_production_holds(self, tmp_path: Path) -> None:
        """The journal says the correction wrote something else than what the cell holds: the
        one-key value in the cell is not proven to be that lane's."""
        root, lives, journal, planned = step_one(tmp_path)
        entry = correction(planned)
        wide = C.reprint({**json.loads(entry["new_value"]), "extra": 1})
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        code, found = accept_teaser(tmp_path, root, lives, [*journal, {**entry, "new_value": wide}])
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    def test_a_correction_written_twice_is_not_accepted(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = correction(planned)
        again = {**entry, "run_stamp": "wb-card-disclosure-s002"}
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        code, _found = accept_teaser(tmp_path, root, lives, [*journal, entry, again])
        assert code == 1

    def test_a_correction_that_was_undone_leaves_the_step_as_planned(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = correction(planned)
        undo = {**entry, "run_stamp": "wb-card-disclosure-s001-rollback",
                "old_value": entry["new_value"], "new_value": planned}  # fmt: skip
        assert accept_teaser(tmp_path, root, lives, [*journal, entry, undo]) == (0, [])

    def test_a_step_planned_with_the_new_disclosure_has_nothing_to_correct(
        self, tmp_path: Path
    ) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        assert (
            W.corrected_cell(T.SKARA, C.reprint(raw_of(T.SKARA, NEW)), [correction(planned)])
            is None
        )
        assert W.corrected_cell(T.SKARA, None, [correction(planned)]) is None
        assert W.corrected_cell(T.SKARA, planned, []) is None

    def test_the_step_s_read_asks_for_the_correction_rows_of_its_sites_only(
        self, tmp_path: Path
    ) -> None:
        root, lives, journal, _planned = step_one(tmp_path)
        seen: list[str] = []

        def read(script: str) -> str:
            seen.append(script)
            return TT.export_for(lives, journal)

        write_jsonl(tmp_path / "runs" / RUN / "OUTCOMES.jsonl", [outcome()])
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(W, "RUNS", tmp_path / "runs")
            W.accept_step(1, read=read, root=root)
        (script,) = seen
        assert "l.run_stamp LIKE 'wb-card-disclosure-s%'" in script
        assert f"l.row_pk IN ('{T.SKARA}')" in script
        assert "l.column_name = 'raw_data'" in script
        assert "wb-teaser-prov-s001" in script and "wb-teaser-card-s001-rollback" in script
        assert not re.search(r"(?i)\b(insert|update|delete|truncate|drop)\b", script)


# ------------------------------------------------------------------ verify_writes4 --allow-stamp
def _teaser_site(tmp_path: Path) -> tuple[TA.Written, dict[str, Any]]:
    """A P4-written, card-held site that lane WB then stamped with a teaser provenance naming the
    Opus-only disclosure (`wb-teaser-prov-s001`), as in the p4/p4wc acceptances of the sitting."""
    written = TA.written_p4(tmp_path, card_held=True)
    raw = written.production.sites[TA.SITE_ID]["raw_data"]
    teaser = dict(raw, _card_provenance={"ai_system": OLD, "text_sha256": "e" * 64})
    TA._later(written, old=raw, new=teaser, stamp="wb-teaser-prov-s001")
    return written, teaser


ALLOWED = ("wb-teaser-prov-%", "wb-card-disclosure-s%")


class TestVerifyWrites4ReadsTheCorrectionByNameForItsOneKey:
    def test_the_correction_is_superseding_under_its_own_pattern(self, tmp_path: Path) -> None:
        written, teaser = _teaser_site(tmp_path)
        TA._later(
            written,
            old=teaser,
            new=W.correct_disclosure(teaser),
            stamp="wb-card-disclosure-s001",
        )
        result = TA._accept4(written, allowed=ALLOWED)
        assert (result.deviations, result.superseded) == ([], {"wb-card-disclosure-s%": 1})
        assert TA.accept(written, tmp_path, allow_stamp=list(ALLOWED)) == []

    def test_without_its_pattern_the_row_is_changed_later(self, tmp_path: Path) -> None:
        written, teaser = _teaser_site(tmp_path)
        TA._later(
            written,
            old=teaser,
            new=W.correct_disclosure(teaser),
            stamp="wb-card-disclosure-s001",
        )
        deviations = TA._accept4(written, allowed=("wb-teaser-prov-%",)).deviations
        assert any(d.startswith("CHANGED LATER") for d in deviations)

    @pytest.mark.parametrize("pattern", ["wb-card-disclosure-s%", "wb-%", "%"])
    def test_a_correction_that_moved_a_second_key_is_never_superseding(
        self, tmp_path: Path, pattern: str
    ) -> None:
        """The key rule does not depend on how broad the operator's pattern is."""
        written, teaser = _teaser_site(tmp_path)
        wide = {**W.correct_disclosure(teaser), "extra": 1}
        TA._later(written, old=teaser, new=wide, stamp="wb-card-disclosure-s001")
        deviations = TA._accept4(written, allowed=("wb-teaser-prov-%", pattern)).deviations
        assert any(d.startswith("CHANGED LATER") for d in deviations)

    def test_a_correction_that_does_not_start_from_the_opus_value_is_never_superseding(
        self, tmp_path: Path
    ) -> None:
        written, teaser = _teaser_site(tmp_path)
        other = {**teaser, "_card_provenance": {**teaser["_card_provenance"], "ai_system": "x"}}
        TA._later(written, old=teaser, new=other, stamp="wb-card-disclosure-s001")
        deviations = TA._accept4(written, allowed=ALLOWED).deviations
        assert any(d.startswith("CHANGED LATER") for d in deviations)

    def test_another_lane_s_stamp_is_still_read_by_stamp_alone(self, tmp_path: Path) -> None:
        """The key rule belongs to the correction's stamps: a lane the operator names (here lane
        WB's own provenance stamp) moves any keys it likes, as before."""
        written, teaser = _teaser_site(tmp_path)
        TA._later(written, old=teaser, new={**teaser, "extra": 1}, stamp="wb-teaser-prov-s002")
        result = TA._accept4(written, allowed=("wb-teaser-prov-%",))
        assert result.deviations == [] and result.superseded == {"wb-teaser-prov-%": 1}
