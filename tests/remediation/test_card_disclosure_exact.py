"""Lane WB's exact-disclosure correction (owner decision D56): one key of the all-Opus v3 cards.

`mechanical/card_disclosure_exact.py` sets `_card_provenance.ai_system` of the version-3 cards whose
every stage Opus answered from the Opus-and-Sonnet string to the Opus-only string of D56. DB-less:
production is a fixture export, the closed teaser steps are fixture files, and the SQL is asserted as
rendered text or evaluated in SQLite where it is portable (`->`, `->>`, `||`, `coalesce`). The later
acceptances that must accept this lane - by its stamp, for its one key - are `teaser.py accept`
(`corrected_cell` over `teaser.CORRECTIONS`) and `verify_writes4 --allow-stamp` (both tested here).
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

import opus_handoff as OH  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import card_disclosure as C  # noqa: E402
from mechanical import card_disclosure_exact as X  # noqa: E402
from mechanical import card_disclosure_exact_list as LIST  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical import teaser as W  # noqa: E402
from phase4 import model4 as M  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation import test_card_disclosure as TC  # noqa: E402
from tests.remediation import test_mechanical_teaser as TT  # noqa: E402
from tests.remediation import test_mechanical_teaser_shorts as TS  # noqa: E402
from tests.remediation import test_phase4_accept as TA  # noqa: E402
from tests.remediation.test_mechanical import FOREIGN, ProbeProduction  # noqa: E402

OLD, NEW = M.AI_SYSTEM_CLAUDE, M.AI_SYSTEM_CLAUDE_OPUS
OPUS, SONNET = OH.OPUS_MODEL, OH.SONNET_MODEL
ALL_OPUS = {"write": OPUS, "rate": OPUS, "check": OPUS, "verify": OPUS}
SITES = (T.SKARA, T.NEWGRANGE, T.STONEHENGE)
PROV = CP.CARD_PROVENANCE_KEY
NOW = "2026-10-24T00:00:00+00:00"


def provenance(ai_system: str = OLD, models: dict[str, str | None] | None = None) -> dict:
    """A version-3 provenance as pilots 2 and 3 wrote it: every stage Opus, the Claude string."""
    return TS.v3(models=ALL_OPUS if models is None else models, ai_system=ai_system)


def raw_of(ai_system: str = OLD, **over: Any) -> dict[str, Any]:
    """A raw_data as production prints it for a card site: Phase 5's key and the teaser's."""
    return {
        "description_citations": [],
        "_description_provenance": {"lane": "W", "card": None},
        PROV: provenance(ai_system, **over),
    }


def live_of(site_id: str, ai_system: str = OLD, **over: Any) -> C.Live:
    base = C.Live(
        site_id=site_id,
        name=T.NAMES[site_id],
        scope_status=None,
        raw_data=C.reprint(raw_of(ai_system)),
        description=T.DESCRIPTIONS[T.SKARA],
        card=TS.NAMELESS,
        premise=C.premise_of(provenance(ai_system)),
    )
    return replace(base, **over)


def listed_of(site_id: str, **over: Any) -> X.Listed:
    base = X.Listed(
        site_id=site_id,
        name=T.NAMES[site_id],
        run="wb-shorts-test",
        step=37,
        provenance=provenance(),
    )
    return replace(base, **over)


@pytest.fixture()
def pinned(monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    """The pinned list of these tests: the lane, the plan and the acceptance read it via `X.LIST`."""
    ids = tuple(sorted(SITES))
    monkeypatch.setattr(X, "LIST", SimpleNamespace(SITE_IDS=ids, LIST_SHA256=C.list_sha256(ids)))
    return ids


def step_records(directory: Path) -> list[A.ChangeRecord]:
    live = {s: live_of(s) for s in SITES}
    plan = X.build_step(1, [listed_of(s) for s in SITES], live, {}, built_at=NOW)
    MP.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    return A.load_records(directory / "PLAN.jsonl")


# ------------------------------------------------------------------------------ the pair
class TestThePair:
    def test_the_lane_owns_the_claude_string_and_the_opus_only_string_of_d56(self) -> None:
        assert (X.OLD, X.NEW) == (M.AI_SYSTEM_CLAUDE, M.AI_SYSTEM_CLAUDE_OPUS)
        assert X.CORRECTION is W.EXACT_CORRECTION and X.CORRECTION in W.CORRECTIONS
        assert X.NEW != M.AI_SYSTEM_OPUS, "the 2026-09 string the first correction replaced"
        assert {X.OLD, X.NEW} <= M.AI_SYSTEMS
        assert M.ai_system_for(ALL_OPUS.values()) == X.NEW

    def test_the_two_corrections_have_their_own_stamps(self) -> None:
        assert W.correction_of("wb-card-exact-s001") is W.EXACT_CORRECTION
        assert W.correction_of("wb-card-disclosure-s001") is W.DISCLOSURE_CORRECTION
        for other in (
            "wb-card-exact-s001-rollback",
            "wb-card-exact-x001",
            "wb-card-exact-s1",
            "wb-teaser-prov-s037",
            "wb-card-disclosure-s001-rollback",
            "%",
        ):
            assert W.correction_of(other) is None, other


# ------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_a_step_is_a_lane_of_its_own(self, pinned: tuple[str, ...]) -> None:
        lane = X.exact_lane(1)
        assert lane.name == "card-exact-s001" and lane.key_prefix == lane.name
        assert lane.run_stamp == "wb-card-exact-s001"
        assert lane.rollback_run_stamp == "wb-card-exact-s001-rollback"
        assert lane.out_dir_name == "mechanical_card_exact/s001"
        assert lane.test_id == "WB/card-disclosure-exact" and lane.target is L.UNIFIED_SITES
        assert lane.premise_sql == C.PREMISE_SQL
        (cell,) = lane.cells
        assert (cell.name, cell.sql_type) == ("raw_data", "jsonb")
        assert not cell.clears and not cell.fills_null
        assert W.EXACT_STAMP.match(lane.run_stamp)
        with pytest.raises(MP.PlanError, match="step 2 has no sites"):
            X.exact_lane(2)

    def test_the_lanes_resolve_by_name_for_apply(self, pinned: tuple[str, ...]) -> None:
        assert L.resolve_lane("card-exact-s001") == X.exact_lane(1)
        assert X.lane_of("card-exact-s001") == X.exact_lane(1)
        for name in ("card-exact-1", "card-exact-s0001", "card-exact"):
            with pytest.raises(KeyError):
                L.resolve_lane(name)
        assert A.readback_for(X.exact_lane(1)) == X.exact_readback(X.exact_lane(1))
        assert A._lane_argument("card-exact-s001") == "card-exact-s001"

    def test_the_invariant_refuses_any_provenance_that_names_neither_disclosure(self) -> None:
        predicate = X._NAMES_NEITHER.predicate
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE unified_sites (id TEXT, raw_data TEXT)")
        rows = {
            "old": C.reprint(raw_of(OLD)),
            "new": C.reprint(raw_of(NEW)),
            "opus-2026-09": C.reprint(raw_of(M.AI_SYSTEM_OPUS)),
            "none": "{}",
            "probe": A.NEVER_STORED["jsonb"],
        }
        for key, text in rows.items():
            db.execute("INSERT INTO unified_sites VALUES (?, ?)", (key, text))
        broken = {
            k for (k,) in db.execute(f"SELECT id FROM unified_sites WHERE ({predicate})").fetchall()
        }
        assert broken == {"opus-2026-09", "none", "probe"}

    def test_the_statements_carry_the_premise_the_old_value_and_the_invariant_both_ways(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        records = step_records(tmp_path)
        lane = X.exact_lane(1)
        write = A.apply_statement(records, lane)
        undo = A.rollback_statement(records, lane)
        for sql in (write, undo):
            assert f"WHERE ({C.PREMISE_SQL}) IS DISTINCT FROM p.premise;" in sql
            assert "invariant 3, the lane's own" in sql
            assert "SET LOCAL lock_timeout = '10s';" in sql
        assert f"'{lane.run_stamp}'" in write and f"'{lane.rollback_run_stamp}'" in undo

    def test_every_guard_has_its_probe_and_each_is_refused_by_its_own_guard(
        self,
        pinned: tuple[str, ...],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        records = step_records(tmp_path)
        lane = X.exact_lane(1)
        cases = {c[0] for c in A.probe_cases(records, lane, FOREIGN)}
        assert cases == {
            "guard1-other-source",
            "guard2-no-op",
            "guard2-foreign-column",
            "guard3-foreign-old-value",
            "guard5-premise",
            "invariant-lane",
        }
        ProbeProduction(lane, records, monkeypatch)
        assert A.cmd_probe_guards(records, tmp_path, lane) == 0
        assert capsys.readouterr().out.count("refused by its own guard=True") == 6

    def test_the_readback_counts_what_the_correction_may_and_may_not_have_moved(
        self, pinned: tuple[str, ...]
    ) -> None:
        sql = X.exact_readback(X.exact_lane(1))
        for metric in (  # a metric is a SQL literal: its apostrophe is doubled
            "journal rows for this run that changed anything but the card provenance''s ai_system",
            "journal rows for this run whose old value did not name the Opus and Sonnet disclosure",
            "listed sites of this step still naming the Opus and Sonnet disclosure",
            "curated version-3 card provenances naming Sonnet that no stage of theirs names",
        ):
            assert metric in sql
        assert "'wb-card-exact-s001'" in sql
        assert not re.search(r"(?i)\b(insert|update|delete|truncate|drop)\b", sql)


# ------------------------------------------------------------------------------ the pinned list
class TestThePinnedList:
    def test_the_delivered_list_is_the_43_cards_of_pilots_2_and_3(self) -> None:
        ids = LIST.SITE_IDS
        assert len(ids) == 43
        assert list(ids) == sorted(set(ids))
        assert all(MP.UUID_RE.match(site_id) for site_id in ids)
        assert C.list_sha256(ids) == LIST.LIST_SHA256
        assert (
            LIST.LIST_SHA256 == "b87daa31d60a33edb86c8c2a11acdecb104266d6244dac75e46b4c8aa03fd1bb"
        )
        assert [len(X.step_sites(1))] == [43]

    def test_the_module_is_what_list_write_renders(self) -> None:
        text = (REPO / "scripts/remediation/mechanical/card_disclosure_exact_list.py").read_text(
            encoding="utf-8"
        )
        assert text.replace("\r\n", "\n") == X.module_text(LIST.SITE_IDS)

    def test_the_committed_list_file_names_every_site_its_run_and_its_all_opus_models(
        self,
    ) -> None:
        path = REPO / "output/remediation/mechanical_card_exact/LIST.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [r["site_id"] for r in rows] == list(LIST.SITE_IDS)
        runs = {r["run"] for r in rows}
        assert runs == {"wb-shorts-pilot2-2026-10-19", "wb-shorts-pilot3-2026-10-20"}
        assert sum(r["run"] == "wb-shorts-pilot2-2026-10-19" for r in rows) == 23
        for row in rows:
            assert (row["ai_system"], row["derived"]) == (OLD, NEW)
            assert {m for m in row["models"].values() if m is not None} == {OPUS}


# ------------------------------------------------------------------------------ the list builder
class Steps:
    """A teaser root with closed steps whose provenance plans carry the given provenances."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "mechanical_teaser"
        self.steps: dict[int, list[dict[str, Any]]] = {}

    def card(self, site_id: str, prov: dict[str, Any] | None, *, step: int = 1) -> None:
        raw = {} if prov is None else {PROV: prov}
        self.steps.setdefault(step, []).append(
            {"site_id": site_id, "site_name": T.NAMES[site_id], "new_value": C.reprint(raw)}
        )

    def build(self, *, accepted: tuple[int, ...] = (1,), reverted: tuple[int, ...] = ()) -> None:
        TC.write_jsonl(
            self.root / "STEPS.jsonl",
            [{"step": s, "run": f"run-{s}", "outcomes": []} for s in sorted(self.steps)],
        )
        for s, rows in self.steps.items():
            TC.write_jsonl(self.root / W.step_name(s) / "prov" / "PLAN.jsonl", rows)
        for kind in (W.ACCEPTED_DIR, W.REVERTED_DIR):
            shutil.rmtree(self.root / kind, ignore_errors=True)
        for n in accepted:
            W._record_closing(W.ACCEPTED_DIR, n, self.root, {})
        for n in reverted:
            W._record_closing(W.REVERTED_DIR, n, self.root, {})

    def list(self) -> list[X.Listed]:
        return X.build_list(root=self.root)


class TestTheListBuilder:
    def test_an_all_opus_card_that_names_sonnet_is_listed(self, tmp_path: Path) -> None:
        fx = Steps(tmp_path)
        fx.card(T.SKARA, provenance())
        fx.build()
        (item,) = fx.list()
        assert (item.site_id, item.name, item.run, item.step) == (
            T.SKARA,
            T.NAMES[T.SKARA],
            "run-1",
            1,
        )
        row = item.row()
        assert (row["ai_system"], row["derived"]) == (OLD, NEW)
        assert row["models"] == ALL_OPUS

    def test_a_card_whose_disclosure_its_models_derive_is_not_listed(self, tmp_path: Path) -> None:
        fx = Steps(tmp_path)
        fx.card(T.SKARA, provenance(models=TS.CLAUDE))  # Opus and Sonnet: AI_SYSTEM_CLAUDE holds
        fx.card(T.NEWGRANGE, provenance(NEW))  # already the exact string
        fx.card(T.STONEHENGE, {**T.teaser(T.STONEHENGE), "ai_system": OLD})  # version 2
        fx.build()
        assert fx.list() == []

    def test_a_rate_stage_nobody_answered_does_not_count(self, tmp_path: Path) -> None:
        fx = Steps(tmp_path)
        unrated = provenance()  # the rewrite after a failed verification: no rater (check-v)
        unrated["models"] = {**ALL_OPUS, "rate": None}
        fx.card(T.SKARA, unrated)
        fx.build()
        assert [item.site_id for item in fx.list()] == [T.SKARA]

    def test_another_pair_is_refused_never_guessed(self, tmp_path: Path) -> None:
        sonnet = dict.fromkeys(ALL_OPUS, SONNET)
        fx = Steps(tmp_path)
        fx.card(T.SKARA, provenance(models=sonnet))  # derives the Sonnet-only string
        fx.build()
        with pytest.raises(MP.PlanError, match="never a guess"):
            fx.list()
        fx = Steps(tmp_path / "b")
        fx.card(T.SKARA, provenance(M.AI_SYSTEM_CLAUDE_HAIKU))
        fx.build()
        with pytest.raises(MP.PlanError, match="never a guess"):
            fx.list()

    def test_only_a_closed_step_that_stands_counts_and_the_latest_wins(
        self, tmp_path: Path
    ) -> None:
        fx = Steps(tmp_path)
        fx.card(T.SKARA, provenance(), step=1)
        fx.card(T.NEWGRANGE, provenance(), step=2)
        fx.card(T.STONEHENGE, provenance(), step=3)
        fx.card(T.SKARA, None, step=4)  # a later step cleared Skara's card
        fx.build(accepted=(1, 2, 4), reverted=(2,))
        assert fx.list() == []
        fx.build(accepted=(1, 2, 3))  # step 4 (Skara's clear) not closed: its card stands
        assert [i.site_id for i in fx.list()] == sorted(SITES)
        fx.build(accepted=(1, 2, 3, 4), reverted=(3,))
        assert [i.site_id for i in fx.list()] == [T.NEWGRANGE]

    def test_list_write_and_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fx = Steps(tmp_path)
        for site in SITES:
            fx.card(site, provenance())
        fx.build()
        module = tmp_path / "card_disclosure_exact_list.py"
        monkeypatch.setattr(X, "LIST_MODULE", module)
        argv = ["--root", str(tmp_path / "out"), "list", "--write", "--teaser-root", str(fx.root)]
        assert X.main(argv) == 0
        rows = [json.loads(x) for x in (tmp_path / "out" / "LIST.jsonl").read_text().splitlines()]
        assert [r["site_id"] for r in rows] == sorted(SITES)
        namespace: dict[str, Any] = {}
        exec(compile(module.read_text(encoding="utf-8"), "module", "exec"), namespace)  # noqa: S102
        assert namespace["SITE_IDS"] == tuple(sorted(SITES))
        monkeypatch.setattr(X, "LIST", SimpleNamespace(**namespace))
        assert X.main(["list", "--check", "--teaser-root", str(fx.root)]) == 0
        fx.card(T.SACSAY, provenance())
        fx.build()
        capsys.readouterr()
        assert X.main(["list", "--check", "--teaser-root", str(fx.root)]) == 1
        assert "is not the pinned one" in capsys.readouterr().err


# ------------------------------------------------------------------------------ the decision
class TestTheDecision:
    def test_exactly_one_key_moves_from_the_claude_string_to_the_opus_only_one(self) -> None:
        verdict = X.classify(listed_of(T.SKARA), live_of(T.SKARA), [])
        assert verdict.ok and verdict.rule == X.RULE and verdict.column == "raw_data"
        before, after = json.loads(verdict.old_value), json.loads(verdict.new_value)
        assert (before[PROV]["ai_system"], after[PROV]["ai_system"]) == (OLD, NEW)
        before[PROV]["ai_system"] = NEW
        assert before == after, "every other key, at every depth, is as it was"
        assert list(json.loads(verdict.new_value)[PROV]) == list(after[PROV])
        assert verdict.premise == C.premise_of(provenance())
        assert W.moves_disclosure_key(verdict.old_value, verdict.new_value, W.EXACT_CORRECTION)
        models, rule = verdict.evidence
        assert "check: anthropic/claude-opus-5-5" in models["quote"]
        assert OLD in rule["quote"] and NEW in rule["quote"] and "D56" in rule["source"]

    @pytest.mark.parametrize(
        ("live", "reason"),
        [
            (lambda: None, C.NOT_CURATED),
            (lambda: live_of(T.SKARA, raw_data=None), C.NO_PROVENANCE),
            (lambda: live_of(T.SKARA, raw_data="[1]"), C.RAW_DATA_NOT_OBJECT),
            (lambda: live_of(T.SKARA, raw_data="{}"), C.NO_PROVENANCE),
            (
                lambda: live_of(T.SKARA, raw_data=json.dumps(raw_of(), indent=1)),
                C.NOT_REPRINTED,
            ),
            (lambda: live_of(T.SKARA, NEW), C.ALREADY_CORRECTED),
            (
                lambda: live_of(T.SKARA, raw_data=C.reprint({**raw_of(), PROV: {"x": 1}})),
                C.PROVENANCE_MOVED,
            ),
        ],
        ids=["gone", "null", "not-object", "no-key", "not-reprinted", "already", "moved"],
    )
    def test_a_site_that_cannot_be_corrected_is_listed_not_written(
        self, live: Any, reason: str
    ) -> None:
        verdict = X.classify(listed_of(T.SKARA), live(), [])
        assert not verdict.ok and verdict.reason == reason and verdict.new_value is None
        assert X.REFUSAL_MEANING[reason]

    def test_a_provenance_whose_models_no_longer_derive_the_opus_only_string_is_listed(
        self,
    ) -> None:
        """The list says the models are all Opus; the planner asks the live provenance again."""
        mixed = provenance(models=TS.CLAUDE)
        item = listed_of(T.SKARA, provenance=mixed)
        live = live_of(T.SKARA, raw_data=C.reprint({**raw_of(), PROV: mixed}))
        verdict = X.classify(item, live, [])
        assert verdict.reason == X.MODELS_MOVED and not verdict.ok

    def test_a_journal_that_does_not_end_at_the_live_value_lists_the_site(self) -> None:
        stale = [MP.JournalLink(7, "x", "t", None, C.canonical(C.reprint({"a": 1})))]
        assert X.classify(listed_of(T.SKARA), live_of(T.SKARA), stale).reason == (
            "journal-disagrees"
        )
        good = [MP.JournalLink(7, "x", "t", None, C.canonical(live_of(T.SKARA).raw_data))]
        assert X.classify(listed_of(T.SKARA), live_of(T.SKARA), good).ok

    def test_an_export_that_is_not_one_snapshot_is_refused(self) -> None:
        with pytest.raises(MP.PlanError, match="not one snapshot"):
            X.classify(listed_of(T.SKARA), live_of(T.SKARA, premise="r|t|d"), [])

    def test_rewrite_disclosure_holds_the_old_value(self) -> None:
        for bad in (raw_of(NEW), raw_of(M.AI_SYSTEM_OPUS), {}, {PROV: "x"}):
            with pytest.raises(MP.PlanError, match="is not"):
                W.rewrite_disclosure(bad, W.EXACT_CORRECTION)

    def test_a_pilot_outcome_cannot_be_planned_again_with_the_claude_string(self) -> None:
        """After D56 the planner of lane WB refuses the old all-Opus outcome of pilots 2 and 3: its
        `ai_system` is no longer the one its models derive."""
        row = TS.shorts_outcome(provenance=provenance())
        with pytest.raises(ValueError, match="is not the one derived from its models"):
            W.new_raw_data({}, row)
        assert W.new_raw_data({}, TS.shorts_outcome(provenance=provenance(NEW)))


# ------------------------------------------------------------------------------ the step
def export_for(lives: list[C.Live], journal: list[dict[str, Any]] | None = None) -> str:
    return TC.export_for(lives, journal)


def a_step(tmp_path: Path, *, lives: list[C.Live] | None = None) -> Path:
    root = tmp_path / "mechanical_card_exact"
    X.plan_step(
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
        A.validate_records(rows, lane=X.exact_lane(1))
        undo = (out / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert undo.startswith("-- plan sha256 ") and "wb-card-exact-s001-rollback" in undo
        page = (out / "PLAN.md").read_text(encoding="utf-8")
        assert "3 site(s) written, 0 listed" in page and T.NAMES[T.SKARA] in page
        assert A.emit(rows, out, X.exact_lane(1), plan_path=out / "PLAN.jsonl") == 3

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

    def test_a_step_is_planned_once_and_the_next_waits(
        self, pinned: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = a_step(tmp_path)
        with pytest.raises(MP.PlanError, match="planned once"):
            X.plan_step(1, read=lambda _s: "", root=root, listed=[listed_of(s) for s in SITES])
        ids = tuple(f"{i:08d}-0000-4000-8000-000000000000" for i in range(101))
        monkeypatch.setattr(X, "LIST", SimpleNamespace(SITE_IDS=ids))
        with pytest.raises(MP.PlanError, match="step 1 has no acceptance"):
            X.plan_step(2, read=lambda _s: "", root=tmp_path / "other", listed=[])

    def test_a_list_that_is_not_the_pinned_one_is_refused(
        self, pinned: tuple[str, ...], tmp_path: Path
    ) -> None:
        live = {s: live_of(s) for s in SITES}
        with pytest.raises(MP.PlanError, match="not the pinned list"):
            X.build_step(1, [listed_of(T.SKARA)], live, {}, built_at=NOW)

    def test_the_read_is_one_read_only_snapshot_of_the_steps_sites(
        self, pinned: Any, tmp_path: Path
    ) -> None:
        seen: list[str] = []

        def read(script: str) -> str:
            seen.append(script)
            return export_for([live_of(s) for s in SITES])

        X.plan_step(1, read=read, root=tmp_path, listed=[listed_of(s) for s in SITES])
        (script,) = seen
        assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script
        for site in SITES:
            assert f"'{site}'" in script
        assert C.PREMISE_SQL in script and "column_name = 'raw_data'" in script
        assert not re.search(r"(?i)\b(insert|update|delete|truncate|drop)\b", script)


# ------------------------------------------------------------------------------ the acceptance
def written_state() -> tuple[list[C.Live], list[dict[str, Any]], list[dict[str, Any]]]:
    """Production after the step's lane ran as planned: live rows, plan rows, the journal."""
    plan = X.build_step(
        1, [listed_of(s) for s in SITES], {s: live_of(s) for s in SITES}, {}, built_at=NOW
    )
    rows = [
        {"site_id": v.site_id, "old_value": v.old_value, "new_value": v.new_value}
        for v in plan.changes
    ]
    lives = [live_of(s, NEW) for s in SITES]
    journal = [
        {"row_pk": r["site_id"], "column_name": "raw_data", "run_stamp": "wb-card-exact-s001",
         "old_value": r["old_value"], "new_value": r["new_value"]}
        for r in rows
    ]  # fmt: skip
    return lives, rows, journal


@pytest.fixture()
def accepting(pinned: tuple[str, ...], tmp_path: Path) -> Any:
    root = a_step(tmp_path)

    def accept(lives: list[C.Live], journal: list[dict[str, Any]]) -> tuple[int, list[str]]:
        return X.accept_step(1, read=lambda _sql: export_for(lives, journal), root=root)

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
        code, found = accepting([live_of(s) for s in SITES], [])
        assert code == 1 and not (accepting.root / "ACCEPTED").exists()
        assert any("does not hold the planned value" in line for line in found)
        assert any("0 journal row(s) for 3 planned" in line for line in found)

    def test_a_rollback_row_is_a_deviation(self, accepting: Any) -> None:
        lives, _rows, journal = written_state()
        undo = {**journal[0], "run_stamp": "wb-card-exact-s001-rollback"}
        code, found = accepting(lives, [*journal, undo])
        assert code == 1 and any("rollback journal row" in line for line in found)

    def test_a_journal_row_that_is_not_the_plans_is_a_deviation(self, accepting: Any) -> None:
        lives, _rows, journal = written_state()
        journal[0] = {**journal[0], "old_value": '{"other": 1}'}
        _code, found = accepting(lives, journal)
        assert any("the journal row is not the plan's" in line for line in found)

    def test_a_provenance_that_no_longer_hashes_the_card_is_a_deviation(
        self, accepting: Any
    ) -> None:
        lives, _rows, journal = written_state()
        lives[0] = replace(lives[0], card="Another card.")
        _code, found = accepting(lives, journal)
        assert any("does not hash the live card" in line for line in found)

    def test_a_correction_that_moved_more_than_one_key_is_a_deviation(self, pinned: Any) -> None:
        lives, rows, journal = written_state()
        wide = json.loads(rows[0]["new_value"])
        wide["description_citations"] = ["x"]
        rows[0] = {**rows[0], "new_value": C.reprint(wide)}
        by_site = {s.site_id: s for s in lives}
        by_site[rows[0]["site_id"]] = replace(by_site[rows[0]["site_id"]], raw_data=C.reprint(wide))
        journal[0] = {**journal[0], "new_value": C.reprint(wide)}
        found = X.deviations(1, rows, by_site, journal)
        assert any("changes more than the one key" in line for line in found)
        assert any("journal row changed more than the one key" in line for line in found)

    def test_a_disclosure_its_models_do_not_derive_is_a_deviation(self, pinned: Any) -> None:
        """Production holds the planned value, but the plan itself paired the Opus-only string with
        a Sonnet stage: the acceptance derives the disclosure again from the models."""
        mixed_old = C.reprint({**raw_of(), PROV: provenance(models=TS.CLAUDE)})
        mixed_new = C.reprint({**raw_of(), PROV: provenance(NEW, models=TS.CLAUDE)})
        rows = [{"site_id": T.SKARA, "old_value": mixed_old, "new_value": mixed_new}]
        live = {T.SKARA: live_of(T.SKARA, raw_data=mixed_new)}
        journal = [{"row_pk": T.SKARA, "column_name": "raw_data", "run_stamp": "wb-card-exact-s001",
                    "old_value": mixed_old, "new_value": mixed_new}]  # fmt: skip
        found = X.deviations(1, rows, live, journal)
        assert any("models do not derive the disclosure it names" in line for line in found)


# ------------------------------------------------------------------------------ lane WB's accept
CLAUDE_PROV = {**T.teaser(T.SKARA), "ai_system": OLD}


def outcome(**over: Any) -> dict[str, Any]:
    return TT.outcome(T.SKARA, provenance=CLAUDE_PROV, **over)


def step_one(tmp_path: Path) -> tuple[Path, list[W.Live], list[dict[str, Any]], str]:
    """Lane WB's step 1 for a card whose provenance names `AI_SYSTEM_CLAUDE`, written as planned."""
    root = tmp_path / "mechanical_teaser"
    W.plan_step(
        TC.RUN, 1, read=lambda _sql: TT.export_for([TT.live()]), root=root, outcomes=[outcome()]
    )
    prov, card = W.classify(outcome(), TT.live(), {}, TC.RUN)
    journal = [
        {"row_pk": T.SKARA, "column_name": v.column, "run_stamp": stamp,
         "old_value": v.old_value, "new_value": v.new_value}
        for v, stamp in ((prov, TT.PROV.run_stamp), (card, TT.CARD.run_stamp))
    ]  # fmt: skip
    return root, [TT.live(raw_data=prov.new_value, card=card.new_value)], journal, prov.new_value


def accept_teaser(
    tmp_path: Path, root: Path, lives: list[W.Live], journal: list[dict[str, Any]]
) -> tuple[int, list[str]]:
    TC.write_jsonl(tmp_path / "runs" / TC.RUN / "OUTCOMES.jsonl", [outcome()])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(W, "RUNS", tmp_path / "runs")
        return W.accept_step(1, read=lambda _sql: TT.export_for(lives, journal), root=root)


def exact(old: str, **over: Any) -> dict[str, Any]:
    new = C.reprint(W.rewrite_disclosure(json.loads(old), W.EXACT_CORRECTION))
    row = {"row_pk": T.SKARA, "column_name": "raw_data", "run_stamp": "wb-card-exact-s001",
           "old_value": old, "new_value": new}  # fmt: skip
    return {**row, **over}


class TestLaneWbAcceptsTheExactCorrectionByNameForItsOneKey:
    def test_the_step_after_its_site_was_corrected_is_still_accepted(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = exact(planned)
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        assert accept_teaser(tmp_path, root, lives, [*journal, entry]) == (0, [])
        assert W.corrected_cell(T.SKARA, planned, [entry]) == C.canonical(entry["new_value"])

    def test_without_the_correction_in_the_journal_the_moved_cell_is_a_deviation(
        self, tmp_path: Path
    ) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        lives[0] = replace(lives[0], raw_data=exact(planned)["new_value"])
        code, found = accept_teaser(tmp_path, root, lives, journal)
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    @pytest.mark.parametrize(
        "change",
        [
            {"run_stamp": "wb-card-exact-x001"},
            {"run_stamp": "wb-card-disclosure-s001"},  # the other lane's pair does not fit
            {"run_stamp": "wb-teaser-prov-s099"},
            {"column_name": "description"},
            {"row_pk": T.NEWGRANGE},
        ],
        ids=["lookalike", "other-correction", "other-wb-stamp", "another-column", "another-site"],
    )
    def test_no_other_lane_is_accepted(self, tmp_path: Path, change: dict[str, Any]) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = exact(planned, **change)
        lives[0] = replace(lives[0], raw_data=exact(planned)["new_value"])
        code, found = accept_teaser(tmp_path, root, lives, [*journal, entry])
        assert code == 1 and any("does not hold the planned value" in line for line in found)

    def test_only_the_one_key_is_accepted(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        wide = {**W.rewrite_disclosure(json.loads(planned), W.EXACT_CORRECTION), "extra": 1}
        entry = exact(planned, new_value=C.reprint(wide))
        lives[0] = replace(lives[0], raw_data=C.reprint(wide))
        code, _found = accept_teaser(tmp_path, root, lives, [*journal, entry])
        assert code == 1

    def test_two_standing_corrections_are_not_the_steps(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = exact(planned)
        again = {**entry, "run_stamp": "wb-card-exact-s002"}
        lives[0] = replace(lives[0], raw_data=entry["new_value"])
        code, _found = accept_teaser(tmp_path, root, lives, [*journal, entry, again])
        assert code == 1
        assert W.corrected_cell(T.SKARA, planned, [entry, again]) is None

    def test_a_correction_that_was_undone_leaves_the_step_as_planned(self, tmp_path: Path) -> None:
        root, lives, journal, planned = step_one(tmp_path)
        entry = exact(planned)
        undo = {**entry, "run_stamp": "wb-card-exact-s001-rollback",
                "old_value": entry["new_value"], "new_value": planned}  # fmt: skip
        assert accept_teaser(tmp_path, root, lives, [*journal, entry, undo]) == (0, [])

    def test_a_cell_that_names_another_value_is_not_corrected_by_this_lane(self) -> None:
        opus_2026_09 = C.reprint(TC.raw_of(T.SKARA))  # names AI_SYSTEM_OPUS
        assert W.corrected_cell(T.SKARA, opus_2026_09, [exact(C.reprint(raw_of()))]) is None

    def test_the_step_s_read_asks_for_both_corrections_rows_of_its_sites_only(
        self, tmp_path: Path
    ) -> None:
        root, lives, journal, _planned = step_one(tmp_path)
        seen: list[str] = []

        def read(script: str) -> str:
            seen.append(script)
            return TT.export_for(lives, journal)

        TC.write_jsonl(tmp_path / "runs" / TC.RUN / "OUTCOMES.jsonl", [outcome()])
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(W, "RUNS", tmp_path / "runs")
            W.accept_step(1, read=read, root=root)
        (script,) = seen
        assert "l.run_stamp LIKE 'wb-card-disclosure-s%'" in script
        assert "l.run_stamp LIKE 'wb-card-exact-s%'" in script
        assert f"l.row_pk IN ('{T.SKARA}')" in script
        assert not re.search(r"(?i)\b(insert|update|delete|truncate|drop)\b", script)


# ------------------------------------------------------------------ verify_writes4 --allow-stamp
def _teaser_site(tmp_path: Path) -> tuple[TA.Written, dict[str, Any]]:
    written = TA.written_p4(tmp_path, card_held=True)
    raw = written.production.sites[TA.SITE_ID]["raw_data"]
    teaser = dict(raw, _card_provenance={"ai_system": OLD, "text_sha256": "e" * 64})
    TA._later(written, old=raw, new=teaser, stamp="wb-teaser-prov-s037")
    return written, teaser


ALLOWED = ("wb-teaser-prov-%", "wb-card-exact-s%")


class TestVerifyWrites4ReadsTheExactCorrectionByNameForItsOneKey:
    def test_the_correction_is_superseding_under_its_own_pattern(self, tmp_path: Path) -> None:
        written, teaser = _teaser_site(tmp_path)
        new = W.rewrite_disclosure(teaser, W.EXACT_CORRECTION)
        TA._later(written, old=teaser, new=new, stamp="wb-card-exact-s001")
        result = TA._accept4(written, allowed=ALLOWED)
        assert (result.deviations, result.superseded) == ([], {"wb-card-exact-s%": 1})

    @pytest.mark.parametrize("pattern", ["wb-card-exact-s%", "wb-%", "%"])
    def test_a_correction_that_moved_a_second_key_is_never_superseding(
        self, tmp_path: Path, pattern: str
    ) -> None:
        written, teaser = _teaser_site(tmp_path)
        wide = {**W.rewrite_disclosure(teaser, W.EXACT_CORRECTION), "extra": 1}
        TA._later(written, old=teaser, new=wide, stamp="wb-card-exact-s001")
        deviations = TA._accept4(written, allowed=("wb-teaser-prov-%", pattern)).deviations
        assert any(d.startswith("CHANGED LATER") for d in deviations)

    def test_a_correction_from_another_value_is_never_superseding(self, tmp_path: Path) -> None:
        """The exact lane's stamp on the first lane's transition (2026-09 Opus -> Claude) does not
        fit its pair."""
        written, teaser = _teaser_site(tmp_path)
        opus = {**teaser, PROV: {**teaser[PROV], "ai_system": M.AI_SYSTEM_OPUS}}
        TA._later(written, old=teaser, new=opus, stamp="wb-card-exact-s001")
        deviations = TA._accept4(written, allowed=ALLOWED).deviations
        assert any(d.startswith("CHANGED LATER") for d in deviations)
