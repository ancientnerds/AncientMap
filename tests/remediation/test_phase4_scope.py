"""Is the owner's defect scope derived from data, pinned, and the only set the mass run asks about?

Owner decision 2026-09-23 (Martin, "Nur Defekt-Sites (Recommended)"): after a passing Phase-4 pilot,
Phases 4/5 write only the sites with proven text defects - the Phase-3 cleared defects plus the
ungrounded card texts, in the design's order; every other site's description and card stay exactly
as they are. `phase4/scope4.py` is that sentence as data (`SCOPE4.json`, pinned by its sha256),
`plan4.py scope` writes it, `plan4.py build --defect-scope` builds the mass run's plan from it, and
`mass4.py` asks no model question for a site outside it. The writer's refusal of such a site (P4, L,
P5) is tested beside the writer's other rules (`test_phase4_write.py`, `test_phase4_legacy.py`).

The mistakes worth a test are the quiet ones: a number counted as absent because the input writes it
with a separator, or as present because it hides inside a longer numeral; the generator's input read
from today's description instead of the pre-March snapshot's first 500 characters; a site the
snapshot never had claimed on an empty input; a scope file edited after its pin; a plan that carries
the pilot's or an out-of-scope site into the mass run's model calls. The mutation cases are
`P4_SCOPE_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import mass_run as MR  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase4 import mass4 as M4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import plan4 as P  # noqa: E402
from phase4 import scope4 as S  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402
from tests.remediation.test_phase4_plan import build, row, uuid  # noqa: E402

RUNNER = REPO / "output" / "remediation" / "phase4_runner"
MAIN_OUTPUT = REPO / "output" / "remediation"

#: House of Taga, a canary of plan section 5.1 and the design's pilot set (45ac8925), verbatim from
#: the S0 export: the card's "10,000 BC" is in no numeral of the generator's input ("10th", "1,200").
TAGA_CARD = (
    "Latte stone pillars quarried 1.2 km away, from a site occupied as early as 10,000 BC. Only one "
    "pillar still stands upright after centuries of earthquakes."
)
TAGA_INPUT = (
    "(10th - 4th ml. BC) The House of Taga (Chamoru: Guma Taga) is an archeological site located "
    "near San Jose Village, on the island of Tinian, United States Commonwealth of the Northern "
    "Mariana Islands, in the Marianas Archipelago. The site is the location of a series of "
    "Prehistoric Latte Stone Pillars which were quarried about 1,200 metres (4,000 ft) south of the "
    "site, only one of which is left standing erect due to past earthquakes."
)


# ====================================================================== the ungrounded card


def test_a_number_is_its_value_as_written() -> None:
    """A numeral as written: digits with comma thousands separators and a decimal part, read as its
    value - '10,000' is 10000, '7.10' is 7.1; an ordinal's digits are its number."""
    assert S.numerals("10,000 BC, 7.10 m, 1.2 km, the 3rd century, 50 and 500, AD 79.") == [
        Decimal("10000"),
        Decimal("7.1"),
        Decimal("1.2"),
        Decimal("3"),
        Decimal("50"),
        Decimal("500"),
        Decimal("79"),
    ]
    assert S.numerals("1,20 and 12,5") == [Decimal(1), Decimal(20), Decimal(12), Decimal(5)]
    assert S.numerals("No number here.") == []


def test_house_of_taga_is_ungrounded_as_the_plan_found_it() -> None:
    assert S.ungrounded_card(TAGA_CARD, TAGA_INPUT)


@pytest.mark.parametrize(
    ("card", "given"),
    [
        ("Occupied from 10,000 BC.", "It was occupied from 10000 BC."),
        ("A capstone 7.1 m long.", "The capstone is 7.10 m long."),
        ("Built in the 3rd century.", "Built in 3 phases."),
    ],
    ids=["separator", "decimal", "ordinal"],
)
def test_a_number_the_input_writes_otherwise_is_grounded(card: str, given: str) -> None:
    assert not S.ungrounded_card(card, given)


def test_a_number_inside_a_longer_numeral_never_appeared() -> None:
    """'50' did not appear in '500': the documented cohort counts numbers, not digit runs."""
    assert S.ungrounded_card("A ditch 50 m across.", "The ditch is 500 m long.")


def test_only_the_first_500_characters_were_the_generators_input() -> None:
    """`scripts/export_card_sites.py:36` gave the generator `LEFT(us.description, 500)`."""
    tail = "x" * 490 + " 1066"
    assert len(tail) == 495
    assert not S.ungrounded_card("A battle in 1066.", tail)
    late = "x" * 497 + " 1066"
    assert S.ungrounded_card("A battle in 1066.", late)
    assert S.generator_input(late) == late[:500]


def test_a_card_without_a_number_or_without_a_card_is_not_ungrounded() -> None:
    assert not S.ungrounded_card("A card with no number at all.", "Nothing here either.")
    assert not S.ungrounded_card(None, "Occupied in 3000 BC.")


def test_the_input_is_the_pre_march_snapshots_text_not_todays() -> None:
    """Today's description may carry the card's number (the March chain rewrote it); the generator
    was given the snapshot's."""
    rows = [
        row(1, card="Built in 3000 BC.", description="Built in 3000 BC.",
            snapshot_description="An old text without the year."),
        row(2, card="Built in 3000 BC.", description="A new text.",
            snapshot_description="Built in 3000 BC."),
    ]  # fmt: skip
    claimed, unknown = S.ungrounded_cards(rows)
    assert (claimed, unknown) == ([uuid(1)], [])


def test_a_site_the_snapshot_does_not_have_is_not_claimed() -> None:
    """Temple of Baalshamin (95b33efa) was created after d4526691: its generator input is unknown,
    so nothing proves its card ungrounded. It is listed, never claimed."""
    rows = [row(1, card="Rebuilt in 131 AD.", in_snapshot=False, snapshot_description=None)]
    assert S.ungrounded_cards(rows) == ([], [uuid(1)])


# ================================================================================= the scope


def _cleared() -> dict[str, set[str]]:
    return {uuid(1): {"description"}, uuid(2): {"card_description"}, uuid(3): {"description", "card_description"}}  # fmt: skip


def _rows() -> list[dict[str, Any]]:
    return [
        row(1),
        row(2),
        row(3, card="Built in 2500 BC.", snapshot_description="Built in 2500 BC."),
        row(4, card="Built in 2500 BC.", snapshot_description="An old text."),
        row(5, card="Built in 2500 BC.", snapshot_description="Built in 2500 BC."),
        row(6, card="Rebuilt in 131 AD.", in_snapshot=False),
    ]


INPUTS = {"S0_ROWS.jsonl": "a" * 64, "ALL_REFUSED.jsonl": "b" * 64}


def test_the_scope_is_the_three_lists_and_each_site_names_its_lists() -> None:
    payload = S.scope_payload(_rows(), _cleared(), inputs=INPUTS)
    assert payload["lists"] == {S.CLEARED_DESCRIPTION: 2, S.CLEARED_CARD: 2, S.UNGROUNDED_CARD: 1}
    assert payload["sites"] == [
        {"site_id": uuid(1), "lists": [S.CLEARED_DESCRIPTION]},
        {"site_id": uuid(2), "lists": [S.CLEARED_CARD]},
        {"site_id": uuid(3), "lists": [S.CLEARED_DESCRIPTION, S.CLEARED_CARD]},
        {"site_id": uuid(4), "lists": [S.UNGROUNDED_CARD]},
    ]
    assert payload["unclaimed"] == {S.UNGROUNDED_CARD: {S.NOT_IN_SNAPSHOT: [uuid(6)]}}
    assert payload["inputs"] == INPUTS and payload["version"] == S.SCOPE_VERSION
    assert payload["sites_sha256"] == S.sites_digest(payload["sites"])


def test_a_cleared_defect_of_a_site_that_is_no_curated_row_stops_the_scope() -> None:
    with pytest.raises(S.ScopeError, match="not curated rows"):
        S.scope_payload(_rows(), {uuid(9): {"description"}}, inputs=INPUTS)


def test_a_cleared_defect_of_another_field_stops_the_scope() -> None:
    with pytest.raises(S.ScopeError, match="country"):
        S.scope_payload(_rows(), {uuid(1): {"country"}}, inputs=INPUTS)


def test_the_scope_file_round_trips_and_is_byte_identical_across_builds() -> None:
    first = S.render_scope(S.scope_payload(_rows(), _cleared(), inputs=INPUTS))
    second = S.render_scope(S.scope_payload(list(reversed(_rows())), _cleared(), inputs=INPUTS))
    assert first == second and first.endswith(b"\n")
    scope = S.parse_scope(first)
    assert scope.sha256 == hashlib.sha256(first).hexdigest()
    assert uuid(3) in scope and uuid(5) not in scope and uuid(6) not in scope
    assert scope.sites[uuid(3)] == (S.CLEARED_DESCRIPTION, S.CLEARED_CARD)
    assert scope.label == f"SCOPE4.json v{S.SCOPE_VERSION} {scope.sha256[:16]}"


def _payload() -> dict[str, Any]:
    return S.scope_payload(_rows(), _cleared(), inputs=INPUTS)


def _resealed(payload: dict[str, Any]) -> bytes:
    payload["sites_sha256"] = S.sites_digest(payload["sites"])
    return S.render_scope(payload)


@pytest.mark.parametrize(
    ("tamper", "match"),
    [
        (lambda p: p.update(version=2), "version"),
        (lambda p: p.pop("unclaimed"), "keys"),
        (lambda p: p["sites"].reverse(), "sorted"),
        (lambda p: p["sites"].append(dict(p["sites"][-1])), "sorted"),
        (lambda p: p["sites"][0].update(site_id="Tarxien Temples"), "not a site id"),
        (lambda p: p["sites"][0].update(lists=[]), "no list"),
        (lambda p: p["sites"][0].update(lists=["t03-severe"]), "not a list"),
        (lambda p: p["sites"][2].update(lists=[S.CLEARED_CARD, S.CLEARED_DESCRIPTION]), "order"),
        (lambda p: p["sites"][0].update(note="x"), "keys"),
        (lambda p: p["lists"].update({S.UNGROUNDED_CARD: 2}), "counts"),
    ],
    ids=[
        "version",
        "missing-key",
        "unsorted",
        "twice",
        "id",
        "empty",
        "unknown-list",
        "list-order",
        "site-key",
        "counts",
    ],  # fmt: skip
)
def test_a_malformed_scope_is_refused(tamper, match: str) -> None:
    payload = _payload()
    tamper(payload)
    with pytest.raises(S.ScopeError, match=match):
        S.parse_scope(_resealed(payload))


def test_a_site_list_that_is_not_its_digest_is_refused() -> None:
    payload = _payload()
    payload["sites"].pop()
    payload["lists"][S.UNGROUNDED_CARD] = 0
    with pytest.raises(S.ScopeError, match="sites_sha256"):
        S.parse_scope(S.render_scope(payload))


def _pinned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "SCOPE4.json"
    path.write_bytes(data)
    monkeypatch.setattr(S, "SCOPE_FILE", path)
    monkeypatch.setattr(S, "SCOPE_SHA256", hashlib.sha256(data).hexdigest())
    return path


def test_the_scope_is_read_only_from_the_pinned_file(monkeypatch, tmp_path: Path) -> None:
    """A new scope is a new version and a new pin in code, never an edit of the file."""
    data = S.render_scope(_payload())
    path = _pinned(monkeypatch, tmp_path, data)
    assert set(S.load_scope().sites) == {uuid(1), uuid(2), uuid(3), uuid(4)}
    path.write_bytes(data.replace(b'"version": 1', b'"version":  1'))
    with pytest.raises(S.ScopeError, match="is not the pinned scope"):
        S.load_scope()


# ===================================================================== the committed artefact


def test_the_committed_scope_is_the_pinned_one_with_the_recorded_counts() -> None:
    """`SCOPE4.json` v1: 322 + 709 cleared defects (946 sites) and 876 ungrounded cards, 1,623
    sites; plan section 5.1's three named examples are ungrounded, Baalshamin is not claimed."""
    scope = S.load_scope()
    payload = json.loads(S.SCOPE_FILE.read_text(encoding="utf-8"))
    assert payload["lists"] == {
        S.CLEARED_DESCRIPTION: 322,
        S.CLEARED_CARD: 709,
        S.UNGROUNDED_CARD: 876,
    }
    assert len(scope.sites) == 1623
    assert payload["inputs"] == {
        "S0_ROWS.jsonl": "2c99f96f899447000659ad3ff6b24bc2dc9eddd2f96cdfe73afeabb1829272a8",
        "ALL_REFUSED.jsonl": "7b4026d0e39d6c0c1355442a65cea9a5bae9b8762897b1685a8f44b1d6cd75f9",
    }
    for prefix in ("45ac8925", "2968fd35", "3dd6b568"):  # House of Taga, Hatunmarka, Maray Qalla
        (site,) = [s for s in scope.sites if s.startswith(prefix)]
        assert S.UNGROUNDED_CARD in scope.sites[site]
    assert payload["unclaimed"] == {
        S.UNGROUNDED_CARD: {S.NOT_IN_SNAPSHOT: ["95b33efa-d5eb-4cb8-ab61-746b3822762a"]}
    }


def test_the_audit_log_records_the_pinned_scope() -> None:
    log = (MAIN_OUTPUT / "AUDIT_LOG.md").read_text(encoding="utf-8")
    assert f"`{S.SCOPE_SHA256}`" in log


needs_inputs = pytest.mark.skipif(
    not (RUNNER / "S0_ROWS.jsonl").exists()
    or not (MAIN_OUTPUT / "logs" / "_write_dry" / "ALL_REFUSED.jsonl").exists(),
    reason="the gitignored S0 export or Phase 3's refusals are not in this checkout",
)


@needs_inputs
def test_the_committed_scope_is_rebuilt_byte_for_byte_from_its_inputs(tmp_path: Path) -> None:
    out = tmp_path / "SCOPE4.json"
    assert (
        P.main(
            [
                "scope",
                f"--rows={RUNNER / 'S0_ROWS.jsonl'}",
                f"--refused={MAIN_OUTPUT / 'logs' / '_write_dry' / 'ALL_REFUSED.jsonl'}",
                f"--out={out}",
            ]
        )
        == 0
    )
    assert out.read_bytes() == S.SCOPE_FILE.read_bytes()


# ================================================================== plan4: scope and the plan


def test_plan4_scope_writes_the_scope_file_from_the_rows_and_the_refusals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _rows()
    (tmp_path / "S0_ROWS.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    refused = [
        {"site_id": uuid(1), "field": "description", "rule": "report-only-field"},
        {"site_id": uuid(2), "field": "card_description", "rule": "report-only-field"},
        {"site_id": uuid(5), "field": "description", "rule": "reviewer-did-not-clear"},
    ]
    (tmp_path / "ALL_REFUSED.jsonl").write_text("".join(json.dumps(r) + "\n" for r in refused))
    out = tmp_path / "SCOPE4.json"

    code = P.main(
        [
            "scope",
            f"--rows={tmp_path / 'S0_ROWS.jsonl'}",
            f"--refused={tmp_path / 'ALL_REFUSED.jsonl'}",
            f"--out={out}",
        ]
    )

    printed = capsys.readouterr().out
    assert code == 0 and printed.rstrip().endswith("STAGE_EXIT=0")
    scope = S.parse_scope(out.read_bytes())
    assert set(scope.sites) == {uuid(1), uuid(2), uuid(4)}  # refuted is no defect
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["inputs"] == {
        "S0_ROWS.jsonl": hashlib.sha256((tmp_path / "S0_ROWS.jsonl").read_bytes()).hexdigest(),
        "ALL_REFUSED.jsonl": hashlib.sha256(
            (tmp_path / "ALL_REFUSED.jsonl").read_bytes()
        ).hexdigest(),
    }
    summary = json.loads(printed.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert (summary["sites"], summary["sha256"]) == (3, scope.sha256)


def _scope_of(*site_ids: str) -> S.DefectScope:
    return S.DefectScope(
        version=S.SCOPE_VERSION,
        sha256="c" * 64,
        sites=dict.fromkeys(site_ids, (S.CLEARED_CARD,)),
    )


def test_the_scoped_plan_is_the_scopes_sites_after_the_pilot_in_the_plans_order(
    tmp_path: Path,
) -> None:
    """The design's order (cleared defects, then T03, then the rest) restricted to the scope; the
    pilot's sites are the pilot run's - written or held there - and never asked again."""
    rows = [row(n) for n in range(1, 41)]
    cleared = {uuid(n): {"card_description"} for n in (1, 30, 31)}
    t03 = {uuid(n): {"description": "moderate"} for n in (2, 32)}
    sites = build(rows, cleared=cleared, t03=t03, gold=[uuid(1), uuid(2), uuid(3)])
    scope = _scope_of(uuid(1), uuid(3), uuid(30), uuid(31), uuid(32), uuid(40))
    path = tmp_path / "PLAN4.scope.jsonl"

    tail = P.write_scoped_plan(path, sites, pilot=3, scope=scope)

    assert [site.site_id for site in tail] == [uuid(30), uuid(31), uuid(32), uuid(40)]
    (batch,) = R.read_jsonl(path)
    assert [s["site_id"] for s in batch["sites"]] == [uuid(30), uuid(31), uuid(32), uuid(40)]
    assert [M.PlanSite.from_dict(s) for s in batch["sites"]] == tail


def test_the_scoped_plan_continues_the_numbering_after_the_pilots_batches(tmp_path: Path) -> None:
    """A journal stamp names its batch (`phase4:p4-NNNN:chunk-NNNN`) and the apply root is the
    lane's: a mass batch never reuses one of the pilot's ids."""
    rows = [row(n) for n in range(1, 51)]
    sites = build(rows, gold=[uuid(n) for n in range(1, 18)])
    scope = _scope_of(*[uuid(n) for n in range(18, 51)])
    path = tmp_path / "PLAN4.scope.jsonl"

    P.write_scoped_plan(path, sites, pilot=17, scope=scope)

    batches = R.read_jsonl(path)
    assert [(b["batch_id"], b["ordinal"], len(b["sites"])) for b in batches] == [
        ("p4-0003", 3, 15), ("p4-0004", 4, 15), ("p4-0005", 5, 3)
    ]  # fmt: skip


def test_the_scoped_plan_is_built_only_after_a_pilot(tmp_path: Path) -> None:
    sites = build([row(n) for n in range(1, 4)])
    with pytest.raises(R.InputError, match="pilot"):
        P.write_scoped_plan(tmp_path / "PLAN4.scope.jsonl", sites, pilot=0, scope=_scope_of())
    assert not (tmp_path / "PLAN4.scope.jsonl").exists()


def test_build_with_the_defect_scope_writes_the_mass_runs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.remediation.test_phase4_plan import _build_inputs

    argv = _build_inputs(tmp_path, [row(n) for n in range(1, 6)])
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"site_id": uuid(5)}) + "\n", encoding="utf-8")
    data = S.render_scope(S.scope_payload(_rows(), _cleared(), inputs=INPUTS))
    _pinned(monkeypatch, tmp_path, data)  # uuid 1-4 in scope, uuid 5 the pilot

    assert P.main([*argv, f"--pilot={pilot}", "--defect-scope"]) == 0

    out = capsys.readouterr().out
    (batch,) = R.read_jsonl(tmp_path / "PLAN4.jsonl")
    assert batch["batch_id"] == "p4-0002"
    assert [s["site_id"] for s in batch["sites"]] == [uuid(2), uuid(1), uuid(3), uuid(4)]
    summary = json.loads(out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert (summary["sites"], summary["batches"], summary["first_batch"]) == (4, 1, "p4-0002")
    assert summary["scope"] == S.parse_scope(data).label


def test_build_with_the_defect_scope_needs_the_pilot(tmp_path: Path) -> None:
    argv = _build_inputs_of(tmp_path)
    with pytest.raises(R.InputError, match="--pilot"):
        P.main([*argv, "--defect-scope"])


def _build_inputs_of(tmp_path: Path) -> list[str]:
    from tests.remediation.test_phase4_plan import _build_inputs

    return _build_inputs(tmp_path, [row(n) for n in range(1, 3)])


# ============================================================ mass4: no question outside it


def _mass_plan(tmp_path: Path, *site_ids: str) -> Path:
    (tmp_path / "runs" / "mass").mkdir(parents=True)
    return _plan_file(tmp_path, [X.plan_site(site_id) for site_id in site_ids])


def _plan_file(tmp_path: Path, sites: list[M.PlanSite]) -> Path:
    plan = tmp_path / "PLAN4.jsonl"
    line = {"batch_id": "p4-0010", "ordinal": 10, "sites": [site.to_dict() for site in sites]}
    plan.write_text(json.dumps(line, sort_keys=True) + "\n", encoding="utf-8")
    return plan


def _mass_args(tmp_path: Path, plan: Path, *extra: str):
    return M4.build_parser().parse_args(
        ["--plan", str(plan), "--run-dir", str(tmp_path / "runs" / "mass"),
         "--log-dir", str(tmp_path / "logs"), *extra]
    )  # fmt: skip


MODEL_ROUND = ("--live", "--stages", "prepare,sources,routes,select", "--searches-off")


def _no_run(**kwargs: Any) -> int:
    raise AssertionError("a refused round started the loop")


def test_a_model_round_over_a_site_outside_the_scope_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(S, "load_scope", lambda: _scope_of("site-1"))
    monkeypatch.setattr(MR, "run_mass", _no_run)
    plan = _mass_plan(tmp_path, "site-1", "site-2")
    export = ["--handoff-export", str(tmp_path / "handoff")]
    with pytest.raises(MR.PlanError, match="1 site.* outside the owner's defect scope"):
        M4.drive(_mass_args(tmp_path, plan, *MODEL_ROUND, *export))


def test_a_model_round_over_the_scopes_sites_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(S, "load_scope", lambda: _scope_of("site-1", "site-2"))
    seen: dict[str, Any] = {}
    monkeypatch.setattr(MR, "run_mass", lambda **kw: seen.update(kw) or 0)
    plan = _mass_plan(tmp_path, "site-1", "site-2")
    export = ["--handoff-export", str(tmp_path / "handoff")]
    assert M4.drive(_mass_args(tmp_path, plan, *MODEL_ROUND, *export)) == 0
    assert [b.batch_id for b in seen["batches"]] == ["p4-0010"]
    assert "0 site(s) of the open batches outside it" in capsys.readouterr().out


def test_only_the_rounds_own_batches_are_asked_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--only` runs one batch of the scope's sites; another batch of the plan, never run in this
    round, does not refuse it."""
    monkeypatch.setattr(S, "load_scope", lambda: _scope_of("site-1"))
    seen: dict[str, Any] = {}
    monkeypatch.setattr(MR, "run_mass", lambda **kw: seen.update(kw) or 0)
    (tmp_path / "runs" / "mass").mkdir(parents=True)
    lines = [
        {"batch_id": "p4-0010", "ordinal": 10, "sites": [X.plan_site("site-1").to_dict()]},
        {"batch_id": "p4-0011", "ordinal": 11, "sites": [X.plan_site("site-2").to_dict()]},
    ]
    plan = tmp_path / "PLAN4.jsonl"
    plan.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    export = ["--handoff-export", str(tmp_path / "handoff"), "--only", "p4-0010"]
    assert M4.drive(_mass_args(tmp_path, plan, *MODEL_ROUND, *export)) == 0
    assert [b.batch_id for b in seen["batches"]] == ["p4-0010"]
    assert "0 site(s) of the open batches outside it" in capsys.readouterr().out


def test_a_done_batch_asks_nothing_and_refuses_no_round(tmp_path: Path) -> None:
    """The pilot's batches are done: re-driving its run asks nothing, whatever sites they hold."""
    from tests.remediation.test_phase4_runner import _reviewed

    batch_dir = _reviewed(tmp_path)
    line = M4.PlanLine(batch_id="p4-0001", ordinal=1, sites=(X.plan_site("site-1"),))
    assert M4.outside_scope([line], _scope_of(), run_dir=batch_dir.parent) == []
    assert M4.outside_scope([line], _scope_of(), run_dir=tmp_path / "elsewhere") == ["site-1"]


def test_a_round_without_a_model_stage_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Prepare, sources and routes ask no model question; the refusal is the model round's."""
    monkeypatch.setattr(S, "load_scope", lambda: _scope_of())
    seen: dict[str, Any] = {}
    monkeypatch.setattr(MR, "run_mass", lambda **kw: seen.update(kw) or 0)
    plan = _mass_plan(tmp_path, "site-1")
    live = ("--live", "--stages", "prepare,sources,routes", "--searches-off")
    assert M4.drive(_mass_args(tmp_path, plan, *live)) == 0
    assert "1 site(s) of the open batches outside it" in capsys.readouterr().out
