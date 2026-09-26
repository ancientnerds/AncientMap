"""Scope version 3 and its run: Phase 4 over the curated sites it never saw (lane WA, 2026-09-26).

Owner decisions of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`, O1-O11) and the
design `output/remediation/REPAIR_TEXTS_2026-09-26.md`: every curated site that still carries
2026-03 text joins the defect scope (`march-description`, `march-card`, one read-only production
read), and its description gets a sourced Phase-4 text through the unchanged pipeline, or stays held
with a closed-list reason. The owner's changes to the design: **no Phase 5** for these plans - lane
WB rewrites every card (O2, O3), so P4 writes their descriptions with `card: null` and P5 plans none
of their sites; no clearing group (lanes WC and WB take the held texts); the mass run's
`revision-too-fresh` sites are taken over by a follow-up plan of version 3 (v3d) once their 48 h
have passed.

The quiet mistakes worth a test: a retired site, a live Phase-5 card or a P5 clear on a March list;
a March read of other sites than S0's; a version-3 plan that loses its descriptions-only mark (in a
re-queue, too) and so writes a provenance naming a card that is never served, or lets P5 plan an
extractive card; a plan numbered into lane L's block; an excluded site planned anyway; a deferred
site taken over while the run could still re-queue it, re-queued by a plan without the pass
although a descriptions-only list names it, or refused by the acceptance as "in two runs"; an
agent's answer checked against another pool or prompt than its question's; a group of batches kept
waiting by a batch that asked nothing. The mutation cases are `P4_V3_MUTATIONS` in
`scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
import write_gate4 as G  # noqa: E402
from phase3 import mass_run as MR  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import handoff4 as H  # noqa: E402
from phase4 import mass4 as M4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import plan4 as P  # noqa: E402
from phase4 import revert4 as RV  # noqa: E402
from phase4 import run4 as R4  # noqa: E402
from phase4 import scope4 as S  # noqa: E402
from phase4 import write4 as W4  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402
from tests.remediation import phase4_write_fixtures as FX  # noqa: E402
from tests.remediation.test_phase4_plan import _build_inputs, build, row, uuid  # noqa: E402
from tests.remediation.test_phase4_runner import (  # noqa: E402
    SELECT,
    _deferring_run,
    _fresh_hold,
    _selected_batch,
)
from tests.remediation.test_phase4_scope import (  # noqa: E402
    INPUTS_V2,
    INPUTS_V3,
    RUNNER,
    _cleared,
    _march_rows,
    _marker_rows,
    _pinned,
    _rows,
    _v3_payload,
    march_row,
    needs_inputs,
)

MD, MC = S.MARCH_DESCRIPTION, S.MARCH_CARD
MARK = S.DESCRIPTIONS_ONLY_MARK


# ============================================================================ scope version 3


def test_version_3_is_version_2_and_the_two_march_lists() -> None:
    """Every version-2 site keeps its lists, the March lists are appended: version 3 refuses
    nothing version 2 allowed, and its decision records the owner's decisions of 2026-09-26."""
    two = S.scope_payload(_rows(), _cleared(), inputs=INPUTS_V2, version=2)
    three = _v3_payload()
    assert three["version"] == 3
    assert three["lists"] == {
        S.CLEARED_DESCRIPTION: 2,
        S.CLEARED_CARD: 2,
        S.UNGROUNDED_CARD: 1,
        S.D1_MARKER_WITHOUT_ENTRY: 0,
        MD: 2,
        MC: 2,
    }
    assert three["sites"] == [
        {"site_id": uuid(1), "lists": [S.CLEARED_DESCRIPTION, MD, MC]},
        {"site_id": uuid(2), "lists": [S.CLEARED_CARD]},
        {"site_id": uuid(3), "lists": [S.CLEARED_DESCRIPTION, S.CLEARED_CARD, MC]},
        {"site_id": uuid(4), "lists": [S.UNGROUNDED_CARD, MD]},
    ]
    earlier = {site["site_id"]: site["lists"] for site in two["sites"]}
    later = {site["site_id"]: site["lists"] for site in three["sites"]}
    assert all(later[site][: len(lists)] == lists for site, lists in earlier.items())
    assert three["decision"] == f"{S.DECISION} {S.ORDER_2026_09_25} {S.ORDER_2026_09_26}"
    assert set(three["methods"]) == set(S.LISTS) and three["inputs"] == INPUTS_V3
    assert S.parse_scope(S.render_scope(three)).sites[uuid(4)] == (S.UNGROUNDED_CARD, MD)


def test_the_march_lists_are_the_live_marking_and_the_card_no_live_p5_write_put_there() -> None:
    """`march-description`: lane L's marking in the live provenance. `march-card`: a non-empty card
    no live Phase-5 write put there. A retired site is in neither; a Phase-5 card and a Phase-5
    clear (no card left) are not March cards; a W description with a March card is one."""
    rows = [
        march_row(1, lane="L", card=True),
        march_row(2, lane="W", card=True, live_p5=True),
        march_row(3, lane="W", card=True),
        march_row(4, lane="L", card=False, live_p5=True),
        march_row(5, lane="L", card=True, scope_status="retired"),
        march_row(6, card=True, scope_status="pending"),
        march_row(7, lane="S"),
    ]
    assert S.march_lists(rows) == ([uuid(1), uuid(4)], [uuid(1), uuid(3), uuid(6)])


@pytest.mark.parametrize(
    ("tamper", "match"),
    [
        (lambda r: r.pop("live_p5"), "keys"),
        (lambda r: r.update(extra=1), "keys"),
        (lambda r: r.update(id="Tarxien Temples"), "not a site id"),
        (lambda r: r.update(card="yes"), "not a boolean"),
        (lambda r: r.update(live_p5=1), "not a boolean"),
        (lambda r: r.update(lane=7), "not text or null"),
        (lambda r: r.update(scope_status=["retired"]), "not text or null"),
    ],
    ids=["missing-key", "extra-key", "id", "card", "live-p5", "lane", "scope-status"],
)
def test_a_march_row_of_another_shape_is_refused(tamper, match: str) -> None:
    broken = march_row(1, lane="L")
    tamper(broken)
    with pytest.raises(S.ScopeError, match=match):
        S.march_lists([march_row(2), broken])


def test_a_site_read_twice_is_refused() -> None:
    with pytest.raises(S.ScopeError, match="read twice"):
        S.march_lists([march_row(1, lane="L"), march_row(1, lane="L")])


def test_the_march_read_names_exactly_the_s0_rows_sites() -> None:
    """The lists are joined to S0's sites: a site only one of the two reads has is refused, never
    listed or dropped quietly."""
    march = _march_rows(_rows())
    for rows in (march[:-1], [*march, march_row(9)]):
        with pytest.raises(S.ScopeError, match="name other sites"):
            S.scope_payload(_rows(), _cleared(), inputs=INPUTS_V3, version=3, march_rows=rows)


def test_version_3_needs_the_march_read_and_no_earlier_version_takes_it() -> None:
    with pytest.raises(S.ScopeError, match="carries March lists, and 0 March row"):
        S.scope_payload(_rows(), _cleared(), inputs=INPUTS_V3, version=3)
    with pytest.raises(S.ScopeError, match="carries no March lists"):
        S.scope_payload(
            _rows(), _cleared(), inputs=INPUTS_V2, version=2, march_rows=_march_rows(_rows())
        )


def test_the_descriptions_only_lists_are_the_lists_version_3_added() -> None:
    assert set(S.DESCRIPTIONS_ONLY_LISTS) == set(S.VERSION_LISTS[3]) - set(S.VERSION_LISTS[2])


# ------------------------------------------------------------------ the committed artefact


#: The March read of 2026-09-26 (`plan4.py read-march`, read-only, 00:13 UTC; journal high-water
#: mark 73911): 3,923 March descriptions, 3,822 March cards, 4,063 sites - the design's figures.
MARCH_ROWS_SHA256 = "5a2949fb826fabb920ac3b8976afe21fcc8d13cf3e98c7a5197c274b03a6774b"


def test_the_committed_version_3_is_the_pinned_one_with_the_recorded_counts() -> None:
    scope = S.load_scope()
    payload = json.loads(S.SCOPE_FILE.read_text(encoding="utf-8"))
    assert (scope.version, S.SCOPE_FILE.name, len(scope.sites)) == (3, "SCOPE4.v3.json", 4954)
    assert scope.sha256 == "fb775d0e5563d9d441c7b7a33bd6e96016a5ac2f9db9524c566f10aeb84ad0ef"
    assert payload["lists"] == {
        S.CLEARED_DESCRIPTION: 322,
        S.CLEARED_CARD: 709,
        S.UNGROUNDED_CARD: 876,
        S.D1_MARKER_WITHOUT_ENTRY: 9,
        MD: 3923,
        MC: 3822,
    }
    assert payload["inputs"]["MARCH4_ROWS.jsonl"] == MARCH_ROWS_SHA256
    march = {site for site, lists in scope.sites.items() if set(lists) & {MD, MC}}
    assert len(march) == 4063
    assert sum(1 for lists in scope.sites.values() if set(lists) <= {MD, MC}) == 3323
    two = S.load_scope(2)
    for site_id, lists in two.sites.items():
        assert scope.sites[site_id][: len(lists)] == lists


def test_the_committed_march_read_is_the_one_the_scope_names() -> None:
    path = RUNNER / "MARCH4_ROWS.jsonl"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == MARCH_ROWS_SHA256
    descriptions, cards = S.march_lists(R.read_jsonl(path))
    assert (len(descriptions), len(cards), len(set(descriptions) | set(cards))) == (
        3923,
        3822,
        4063,
    )


@needs_inputs
def test_the_committed_version_3_rebuilds_from_the_committed_march_read(tmp_path: Path) -> None:
    out = tmp_path / "SCOPE4.v3.json"
    argv = [
        "scope",
        "--version=3",
        f"--rows={RUNNER / 'S0_ROWS.jsonl'}",
        f"--refused={REPO / 'output' / 'remediation' / 'logs' / '_write_dry' / 'ALL_REFUSED.jsonl'}",
        f"--march={RUNNER / 'MARCH4_ROWS.jsonl'}",
        f"--out={out}",
    ]
    assert P.main(argv) == 0
    assert out.read_bytes() == S.SCOPE_FILE.read_bytes()


# ============================================================================ plan4: the read


def test_the_march_read_is_one_select_that_reads_reversals_as_revert4_does() -> None:
    sql = P.MARCH_SQL
    assert sql.startswith("SELECT to_jsonb(t)::text FROM (SELECT ")
    assert sql.count(";") == 1 and sql.endswith(";")
    for verb in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE", "COMMIT"):
        assert not re.search(rf"\b{verb}\b", sql, re.IGNORECASE), verb
    assert "WHERE u.source_id = 'ancient_nerds'" in sql
    assert "j.run_stamp LIKE 'phase5:%'" in sql
    assert RV._reversed("j") in sql  # key and stamp plus -rollback: revert4's own reading
    assert "->> 'lane' AS lane" in sql and "btrim(c.card_description) <> ''" in sql
    for key in S.MARCH_ROW_KEYS:
        assert f"AS {key}" in sql or f"{key}," in sql


def test_read_march_writes_the_rows_and_counts_the_lists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def runner(sql: str, *, host: str) -> str:
        seen.append(sql)
        return "".join(json.dumps(r) + "\n" for r in _march_rows(_rows()))

    args = argparse.Namespace(out=str(tmp_path / "MARCH4_ROWS.jsonl"), host="vps")
    assert P.cmd_read_march(args, runner=runner) == 0
    assert seen == [P.MARCH_SQL]
    summary = json.loads(capsys.readouterr().out)
    assert (summary[MD], summary[MC], summary["union"], summary["rows"]) == (2, 2, 3, 6)
    assert R.read_jsonl(tmp_path / "MARCH4_ROWS.jsonl") == _march_rows(_rows())


def test_plan4_scope_writes_version_3_with_the_march_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.remediation.test_phase4_scope import _scope_inputs

    argv = _scope_inputs(tmp_path, _marker_rows())
    listing = tmp_path / "SKIPPED.jsonl"
    listing.write_text(json.dumps({"site_id": uuid(7), "reason": S.D1_REASON}) + "\n")
    march = tmp_path / "MARCH4_ROWS.jsonl"
    march.write_text("".join(json.dumps(r) + "\n" for r in _march_rows(_marker_rows())))
    out = tmp_path / "SCOPE4.v3.json"

    assert P.main([*argv, f"--markers={listing}", f"--march={march}", f"--out={out}"]) == 0

    scope = S.parse_scope(out.read_bytes())
    assert scope.version == 3
    assert scope.sites[uuid(1)] == (S.CLEARED_DESCRIPTION, MD, MC)
    assert scope.sites[uuid(7)] == (S.D1_MARKER_WITHOUT_ENTRY,)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["inputs"]["MARCH4_ROWS.jsonl"] == hashlib.sha256(march.read_bytes()).hexdigest()


# ============================================================================ plan4: the plan


def _v3_scope(sites: dict[str, tuple[str, ...]]) -> S.DefectScope:
    return S.DefectScope(version=3, sha256="c" * 64, sites=sites)


V3 = {"scope_lists": [MD, MC], "first_batch": 2001, "excluded": set()}


def test_the_plan_of_two_lists_is_their_union_in_the_plans_order_each_site_once(
    tmp_path: Path,
) -> None:
    sites = build(
        [row(n) for n in range(1, 12)], cleared={uuid(9): {"description"}}, gold=[uuid(1)]
    )
    scope = _v3_scope(
        {
            uuid(2): (MD, MC),
            uuid(3): (MC,),
            uuid(4): (MD,),
            uuid(5): (S.CLEARED_CARD,),
            uuid(9): (S.CLEARED_DESCRIPTION, MD),
        }
    )
    path = tmp_path / "PLAN4.v3.jsonl"

    tail = P.write_list_plan(path, sites, pilot=1, scope=scope, earlier=set(), taken=901, **V3)

    assert [site.site_id for site in tail] == [uuid(9), uuid(2), uuid(3), uuid(4)]
    (batch,) = R.read_jsonl(path)
    assert (batch["batch_id"], batch["ordinal"]) == ("p4-2001", 2001)


def test_a_plan_of_a_version_3_list_writes_descriptions_only(tmp_path: Path) -> None:
    """Owner decisions 2026-09-26 (O2, O3): the plan's batches carry the mark the writer reads; a
    plan of an older list (D9's) carries none, so its bytes are the ones it was run from."""
    sites = build([row(n) for n in range(1, 6)], gold=[uuid(1)])
    scope = _v3_scope({uuid(2): (S.D1_MARKER_WITHOUT_ENTRY,), uuid(3): (MD,)})
    v3, d9 = tmp_path / "v3.jsonl", tmp_path / "d9.jsonl"
    P.write_list_plan(v3, sites, pilot=1, scope=scope, earlier=set(), taken=901, **V3)
    P.write_list_plan(
        d9,
        sites,
        pilot=1,
        scope=scope,
        earlier=set(),
        taken=115,
        scope_lists=[S.D1_MARKER_WITHOUT_ENTRY],
        first_batch=901,
        excluded=set(),
    )
    assert [b.get("pass") for b in R.read_jsonl(v3)] == [MARK]
    assert [b.get("pass") for b in R.read_jsonl(d9)] == [None]
    assert b'"pass"' not in d9.read_bytes()
    mixed = tmp_path / "mixed.jsonl"
    lists = {"scope_lists": [S.D1_MARKER_WITHOUT_ENTRY, MC], "first_batch": 2001}
    P.write_list_plan(
        mixed, sites, pilot=1, scope=scope, earlier=set(), taken=901, excluded=set(), **lists
    )
    assert [b.get("pass") for b in R.read_jsonl(mixed)] == [MARK]


def test_an_excluded_site_is_left_out_and_accounted_for(tmp_path: Path) -> None:
    sites = build([row(n) for n in range(1, 6)], gold=[uuid(1)])
    scope = _v3_scope({uuid(2): (MD,), uuid(3): (MD,), uuid(4): (MC,)})
    path = tmp_path / "PLAN4.v3.jsonl"
    tail = P.write_list_plan(
        path,
        sites,
        pilot=1,
        scope=scope,
        earlier=set(),
        taken=901,
        scope_lists=[MD, MC],
        first_batch=2001,
        excluded={uuid(3), uuid(5)},
    )
    assert [site.site_id for site in tail] == [uuid(2), uuid(4)]
    with pytest.raises(R.InputError, match="no curated row"):
        P.write_list_plan(
            path,
            sites,
            pilot=1,
            scope=scope,
            earlier=set(),
            taken=901,
            scope_lists=[MD],
            first_batch=2001,
            excluded={uuid(99)},
        )


def test_an_exclude_file_is_read_strictly(tmp_path: Path) -> None:
    path = tmp_path / "exclude.txt"
    path.write_text(f"{uuid(2)}\n\n  {uuid(3)}  \n", encoding="utf-8")
    assert P.read_excluded(path) == [uuid(2), uuid(3)]
    path.write_text(f"{uuid(2)}\nTarxien\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="not a site id"):
        P.read_excluded(path)
    path.write_text(f"{uuid(2)}\n{uuid(2)}\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="twice"):
        P.read_excluded(path)


def test_the_first_batch_lies_past_every_earlier_plan_and_outside_lane_ls_block(
    tmp_path: Path,
) -> None:
    """20 curated rows: lane L's plan numbers p4-1001 .. p4-1002 (`legacy_block`). A plan of 16
    sites takes two batches: from 999 it would end in L's block, from 1002 start in it; from 1003
    and below at 900 it lies outside; and never at or before an earlier plan's last ordinal."""
    sites = build([row(n) for n in range(1, 21)], gold=[uuid(1)])
    assert P.legacy_block(len(sites)) == range(1001, 1003)
    scope = _v3_scope(dict.fromkeys([uuid(n) for n in range(2, 18)], (MD,)))
    path = tmp_path / "PLAN4.v3.jsonl"

    def plan(first: int, taken: int = 115) -> list[str]:
        P.write_list_plan(
            path,
            sites,
            pilot=1,
            scope=scope,
            earlier=set(),
            taken=taken,
            scope_lists=[MD],
            first_batch=first,
            excluded=set(),
        )
        return [b["batch_id"] for b in R.read_jsonl(path)]

    assert plan(1003) == ["p4-1003", "p4-1004"]
    assert plan(900) == ["p4-0900", "p4-0901"]
    for first in (1000, 1001, 1002):
        with pytest.raises(R.InputError, match="inside lane L's block"):
            plan(first)
    with pytest.raises(R.InputError, match="an earlier plan numbers up to p4-0901"):
        plan(901, taken=901)


def test_build_with_two_lists_prints_the_exclusion_as_a_count_and_a_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The acceptance's drawn ids never reach the output: `--exclude` prints how many and the file's
    sha256 only."""
    rows = _marker_rows()
    argv = _build_inputs(tmp_path, rows)
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"site_id": uuid(5)}) + "\n", encoding="utf-8")
    earlier = tmp_path / "PLAN4.scope.jsonl"
    line = {"batch_id": "p4-0010", "ordinal": 10, "sites": [X.plan_site(uuid(2)).to_dict()]}
    earlier.write_text(json.dumps(line) + "\n", encoding="utf-8")
    data = S.render_scope(
        S.scope_payload(rows, _cleared(), inputs=INPUTS_V3, version=3, march_rows=_march_rows(rows))
    )
    _pinned(monkeypatch, tmp_path, data)
    exclude = tmp_path / "drawn.txt"
    exclude.write_text(f"{uuid(4)}\n", encoding="utf-8")

    argv = [
        *argv,
        f"--pilot={pilot}",
        f"--scope-list={MD}",
        f"--scope-list={MC}",
        f"--after={earlier}",
        "--first-batch=2001",
        f"--exclude={exclude}",
    ]
    assert P.main(argv) == 0

    out = capsys.readouterr().out
    (batch,) = R.read_jsonl(tmp_path / "PLAN4.jsonl")
    assert [s["site_id"] for s in batch["sites"]] == [uuid(1), uuid(3)]
    assert (batch["batch_id"], batch["pass"]) == ("p4-2001", MARK)
    summary = json.loads(out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert summary["excluded"] == {
        "file_sha256": hashlib.sha256(exclude.read_bytes()).hexdigest(),
        "sites": 1,
        "listed": 1,
    }
    assert uuid(4) not in out
    assert summary["lists"] == [MD, MC] and summary["pass"] == MARK
    assert (summary["listed"], summary["sites"], summary["last_batch"]) == (3, 2, "p4-2001")
    assert summary["lane_l_block"] == [1001, 1001]


# ------------------------------------------------------------------- the deferred sites


READY = datetime(2026, 9, 27, tzinfo=UTC)


def test_a_run_hands_over_its_deferred_sites_once_every_one_is_ready(tmp_path: Path) -> None:
    """`mass4.ready_to_hand_over` reads the batches the run prepared (their input.json), not a plan
    file: the latest batch that lists a site decides."""
    _, run_dir = _deferring_run(tmp_path)  # site-1 ready 2026-09-25 08:00, site-2 09-26 08:00
    handed = M4.ready_to_hand_over(run_dir, now=READY)
    assert [(d.site.site_id, d.held_in) for d in handed] == [
        ("site-1", "p4-0001"),
        ("site-2", "p4-0001"),
    ]
    with pytest.raises(
        MR.PlanError, match="1 of its 2 deferred site.* not ready.*2026-09-26T08:00"
    ):
        M4.ready_to_hand_over(run_dir, now=datetime(2026, 9, 25, 9, 0, tzinfo=UTC))


def test_a_run_that_re_queued_a_deferred_site_itself_keeps_it(tmp_path: Path) -> None:
    plan, run_dir = _deferring_run(tmp_path)
    lines = M4.read_plan4_lines(plan)
    new = M4.requeue_lines(lines, M4.deferred_sites(run_dir, lines), now=READY)
    M4.append_requeue(run_dir, new)
    with pytest.raises(MR.PlanError, match="re-queued 2 of its deferred sites itself"):
        M4.ready_to_hand_over(run_dir, now=READY)


def test_the_prepared_lines_are_the_runs_input_files_in_ordinal_order(tmp_path: Path) -> None:
    plan, run_dir = _deferring_run(tmp_path)
    assert M4.prepared_lines(run_dir) == M4.read_plan4_lines(plan)


def test_build_takes_over_the_deferred_sites_an_earlier_plan_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """HOLDS4 of the mass run: 19 sites held `revision-too-fresh`, due from 2026-09-26T21:30Z. They
    were held, not written, so the v3 plan takes them over from the plan that carries them."""
    rows = _marker_rows()
    argv = _build_inputs(tmp_path, rows)
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"site_id": uuid(5)}) + "\n", encoding="utf-8")
    earlier = tmp_path / "PLAN4.scope.jsonl"
    carried = [X.plan_site(uuid(1)).to_dict(), X.plan_site(uuid(4)).to_dict()]
    earlier.write_text(
        json.dumps({"batch_id": "p4-0010", "ordinal": 10, "sites": carried}) + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "runs" / "mass"
    R4.main(["prepare", "--run-dir", str(run_dir), "--batch-id", "p4-0010", "--plan", str(earlier)])
    B.append_holds(
        run_dir / "p4-0010",
        [
            _fresh_hold(uuid(1), "2020-01-01T08:00:00Z"),
            _fresh_hold(uuid(4), "2020-01-01T09:00:00Z"),
        ],
    )
    data = S.render_scope(
        S.scope_payload(rows, _cleared(), inputs=INPUTS_V3, version=3, march_rows=_march_rows(rows))
    )
    _pinned(monkeypatch, tmp_path, data)
    capsys.readouterr()
    base = [*argv, f"--pilot={pilot}", f"--after={earlier}", "--first-batch=2001"]

    assert (
        P.main([*base, f"--scope-list={MD}", f"--scope-list={MC}", f"--take-deferred={run_dir}"])
        == 0
    )

    (batch,) = R.read_jsonl(tmp_path / "PLAN4.jsonl")
    assert [s["site_id"] for s in batch["sites"]] == [uuid(1), uuid(3), uuid(4)]
    summary = json.loads(capsys.readouterr().out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert summary["taken_over"] == {str(run_dir): {"deferred": 2, "planned": 2}}
    assert summary["carried_by_earlier_plans"] == []
    with pytest.raises(R.InputError, match="no list of this plan names"):
        P.main([*base, f"--scope-list={MC}", f"--take-deferred={run_dir}"])
    # The deferring run's plan must be among --after: its other sites are that run's.
    other = tmp_path / "PLAN4.other.jsonl"
    line = {"batch_id": "p4-0020", "ordinal": 20, "sites": [X.plan_site(uuid(2)).to_dict()]}
    other.write_text(json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="no --after plan carries"):
        P.main(
            [*argv, f"--pilot={pilot}", f"--after={other}", "--first-batch=2001",
             f"--scope-list={MD}", f"--scope-list={MC}", f"--take-deferred={run_dir}"]
        )  # fmt: skip


def _mark_plan(plan: Path) -> Path:
    """The plan file, every line given the descriptions-only pass (the plan of a v3 list)."""
    lines = [{**line, "pass": MARK} for line in R.read_jsonl(plan)]
    plan.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return plan


def test_a_plan_without_the_pass_re_queues_no_site_a_descriptions_only_list_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mass run's 19 (review finding 2026-09-26): a live round of the mass run after their 48 h
    would re-queue them into its own plan - S0's old values, and P5 would plan their extractive card
    although lane WB writes every card (O2, O3) - and v3d's `--take-deferred` would then refuse, or
    both runs would assemble them. So a plan without the descriptions-only pass re-queues no site a
    descriptions-only list names: the live round is refused before REQUEUE4 is written, the dry run
    says so, and a descriptions-only plan re-queues its own sites as before."""
    from tests.remediation.test_phase4_runner import LIVE_ROUND, _args

    def no_run(**kwargs: Any) -> int:
        raise AssertionError("a refused round started the loop")

    plan, run_dir = _deferring_run(tmp_path, ("2020-01-01T08:00:00Z", "2020-01-02T08:00:00Z"))
    scope = _v3_scope({"site-1": (MD,), "site-2": (S.CLEARED_CARD,)})
    monkeypatch.setattr(S, "load_scope", lambda *args, **kwargs: scope)
    monkeypatch.setattr(MR, "run_mass", no_run)
    assert M4.descriptions_only_claims(M4.read_plan4_lines(plan), scope) == ["site-1"]
    capsys.readouterr()

    assert M4.drive(_args(tmp_path, plan)) == 0  # dry: names what a live round refuses
    assert "hand over     1 ready site(s) a descriptions-only list names" in capsys.readouterr().out
    with pytest.raises(MR.PlanError, match="1 ready deferred site.*first site-1.*take-deferred"):
        M4.drive(_args(tmp_path, plan, *LIVE_ROUND))
    assert not (run_dir / M4.REQUEUE_FILE).exists()

    # the same sites deferred by a descriptions-only plan: its own re-queue, as before
    seen: dict[str, Any] = {}
    monkeypatch.setattr(MR, "run_mass", lambda **kw: seen.update(kw) or 0)
    _mark_plan(plan)
    assert M4.descriptions_only_claims(M4.read_plan4_lines(plan), scope) == []
    assert M4.drive(_args(tmp_path, plan, *LIVE_ROUND)) == 0
    assert [b.batch_id for b in seen["batches"]] == ["p4-0001", "p4-0002", "p4-0003"]
    (line,) = M4.read_requeue(run_dir, M4.read_plan4_lines(plan))
    assert ([s.site_id for s in line.sites], line.pass_name) == (["site-1", "site-2"], MARK)


# ============================================================================ mass4: the pass


def _plan_lines(tmp_path: Path, *marks: str | None) -> Path:
    plan = tmp_path / "PLAN4.jsonl"
    rows = []
    for number, mark in enumerate(marks, start=1):
        line: dict[str, Any] = {
            "batch_id": f"p4-{2000 + number:04d}",
            "ordinal": 2000 + number,
            "sites": [X.plan_site(f"site-{number}").to_dict()],
        }
        if mark is not None:
            line["pass"] = mark
        rows.append(line)
    plan.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return plan


def test_a_plans_pass_is_carried_into_its_lines_and_its_re_queue(tmp_path: Path) -> None:
    lines = M4.read_plan4_lines(_plan_lines(tmp_path, MARK, MARK))
    assert {line.pass_name for line in lines} == {MARK}
    deferred = [M4.Deferred(site=lines[0].sites[0], held_in="p4-2001", ready_at=READY)]
    (new,) = M4.requeue_lines(lines, deferred, now=READY)
    assert (new.batch_id, new.pass_name) == ("p4-2003", MARK)
    assert json.loads(new.to_json())["pass"] == MARK
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    M4.append_requeue(run_dir, [new])
    assert M4.read_requeue(run_dir, lines) == [new]
    (tmp_path / "plain").mkdir()
    plain = M4.read_plan4_lines(_plan_lines(tmp_path / "plain", None))
    assert "pass" not in json.loads(plain[0].to_json())  # a v1/v2 line's bytes are unchanged


def test_a_plan_of_lane_l_or_of_two_passes_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MR.PlanError, match="no Phase-4 plan's"):
        M4.read_plan4_lines(_plan_lines(tmp_path, "phase4-legacy"))
    with pytest.raises(MR.PlanError, match="different passes"):
        M4.read_plan4_lines(_plan_lines(tmp_path, MARK, None))


def test_a_re_queue_line_without_its_plans_pass_is_refused(tmp_path: Path) -> None:
    lines = M4.read_plan4_lines(_plan_lines(tmp_path, MARK))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    stray = {"batch_id": "p4-2002", "ordinal": 2002, "sites": [X.plan_site("site-1").to_dict()]}
    (run_dir / M4.REQUEUE_FILE).write_text(json.dumps(stray) + "\n", encoding="utf-8")
    with pytest.raises(MR.PlanError, match="another pass than its plan"):
        M4.read_requeue(run_dir, lines)


def test_the_dry_run_names_the_done_batches_the_write_gate_may_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate plans a batch once its review is imported (`write4.load_batch` refuses a hole): the
    dry run lists exactly the done batches, in plan order, as `--only` takes them."""
    from tests.remediation.test_phase4_runner import _reviewed

    batch_dir = _reviewed(tmp_path)
    plan = tmp_path / "PLAN4.jsonl"
    rows = [
        {"batch_id": "p4-0001", "ordinal": 1, "sites": [X.plan_site("site-1").to_dict()]},
        {"batch_id": "p4-0002", "ordinal": 2, "sites": [X.plan_site("site-2").to_dict()]},
    ]
    plan.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    argv = ["--plan", str(plan), "--run-dir", str(batch_dir.parent), "--log-dir", str(tmp_path)]
    assert M4.drive(M4.build_parser().parse_args(argv)) == 0
    out = capsys.readouterr().out
    assert "\ndone          p4-0001\n" in out
    empty = ["--plan", str(plan), "--run-dir", str(tmp_path / "none"), "--log-dir", str(tmp_path)]
    (tmp_path / "none").mkdir()
    assert M4.drive(M4.build_parser().parse_args(empty)) == 0
    assert "\ndone          -\n" in capsys.readouterr().out


def test_prepare_copies_the_pass_into_input_json(tmp_path: Path) -> None:
    plan = _plan_lines(tmp_path, MARK)
    run_dir = tmp_path / "runs" / "v3"
    R4.main(["prepare", "--run-dir", str(run_dir), "--batch-id", "p4-2001", "--plan", str(plan)])
    stored = json.loads((run_dir / "p4-2001" / M.INPUT_FILE).read_text(encoding="utf-8"))
    assert stored["pass"] == MARK


# ============================================================================ write4


def _marked(batch_dir: Path, mark: str | None = MARK) -> Path:
    raw = json.loads((batch_dir / M.INPUT_FILE).read_text(encoding="utf-8"))
    raw["pass"] = mark
    (batch_dir / M.INPUT_FILE).write_text(json.dumps(raw), encoding="utf-8")
    return batch_dir


def _p4(batch: W4.BatchInputs, verify: FX.Verify) -> W4.WritePlan4:
    return W4.plan_p4(
        batch,
        scope=FX.EVERY_SITE,
        open_lanes=frozenset({M.Lane.W, M.Lane.S}),
        audited=frozenset(),
        verify=verify,
        ledger=FX.ledger_rows(FX.SITE_A, FX.SITE_B),
    )


def test_load_batch_reads_the_descriptions_only_mark(tmp_path: Path) -> None:
    one = {"sites": [FX.plan_site()], "assemblies": [FX.assembly()]}
    plain = W4.load_batch(FX.write_batch(tmp_path / "a", **one))
    marked = W4.load_batch(_marked(FX.write_batch(tmp_path / "b", **one)))
    assert (plain.descriptions_only, marked.descriptions_only) == (False, True)
    other = _marked(FX.write_batch(tmp_path / "c", **one), "phase4-legacy")
    with pytest.raises(W4.PlanInputError, match="carries pass 'phase4-legacy'"):
        W4.load_batch(other)


def test_a_descriptions_only_site_is_written_with_card_null(tmp_path: Path) -> None:
    """No provenance claims a card that is never served (acceptance D4): the description and its
    provenance are written, `card: null`, and the verifier judged exactly that."""
    batch_dir = _marked(
        FX.write_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    )
    verify = FX.Verify()
    plan = _p4(W4.load_batch(batch_dir), verify)
    description, raw = plan.rows
    assert description.new_value == FX.DESCRIPTION
    assert json.loads(raw.new_value)[M.PROVENANCE_KEY]["card"] is None
    assert verify.calls[0]["assembly"].card is None
    assert description.evidence["card"] is None
    assert MARK in description.evidence["card_withheld"]
    unmarked = _p4(
        W4.load_batch(
            FX.write_batch(tmp_path / "x", sites=[FX.plan_site()], assemblies=[FX.assembly()])
        ),
        FX.Verify(),
    )
    assert json.loads(unmarked.rows[1].new_value)[M.PROVENANCE_KEY]["card"] is not None
    assert "card_withheld" not in unmarked.rows[0].evidence


def test_p5_plans_no_card_and_no_clear_for_a_descriptions_only_batch(tmp_path: Path) -> None:
    """Nothing re-plans an extractive card from a v3 run: a written card, a card clear of a
    cleared defect - every site is refused `descriptions-only-plan`, after the scope."""
    flagged = FX.plan_site(FX.SITE_B, flags=[M.SiteFlag.CLEARED_CARD_DEFECT])
    batch_dir = _marked(
        FX.write_batch(
            tmp_path,
            sites=[FX.plan_site(), flagged, FX.plan_site(FX.SITE_C)],
            assemblies=[FX.assembly(), FX.assembly(FX.SITE_B), FX.assembly(FX.SITE_C)],
        )
    )
    batch = W4.load_batch(batch_dir)
    written = {FX.SITE_A: M.text_sha256(FX.CARD)}
    plan = W4.plan_cards(
        batch,
        scope=FX.scope(FX.SITE_A, FX.SITE_B),
        written=written,
        card_findings={FX.SITE_B: [{"finding": "x"}]},
        card_rows=FX.EVERY_CARD_ROW,
    )
    assert plan.rows == []
    assert [(r.site_id, r.rule) for r in plan.refusals] == [
        (FX.SITE_A, W4.RULE_DESCRIPTIONS_ONLY),
        (FX.SITE_B, W4.RULE_DESCRIPTIONS_ONLY),
        (FX.SITE_C, W4.RULE_OUT_OF_SCOPE),
    ]


def test_the_gate_names_the_descriptions_only_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.remediation.test_phase4_write import _db, _gate_args, _gate_run

    monkeypatch.setattr(G, "_defect_scope", lambda: FX.EVERY_SITE)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    _gate_run(tmp_path, 2)
    _marked(tmp_path / "runs" / "pilot" / "p4-0002")
    ids = [f"{n:08x}-0000-4000-8000-00000000000{n}" for n in (1, 2)]
    assert G.main(_gate_args(tmp_path), runner=_db(*ids)) == 0
    out = capsys.readouterr().out
    assert f"descriptions-only batches ({MARK}): 1 of 2" in out
    plan = (tmp_path / "apply" / "p4-0002" / W4.PLAN_FILE).read_text(encoding="utf-8")
    raw = [json.loads(line) for line in plan.splitlines() if '"raw_data"' in line][0]
    assert json.loads(raw["new_value"])[M.PROVENANCE_KEY]["card"] is None


# ============================================================================ handoff4


def _select_export(tmp_path: Path) -> tuple[Path, Path]:
    batch_dir = X.make_batch(tmp_path, [X.w_site("site-1")], run="v3", batch="p4-2001")
    handoff = tmp_path / "handoff" / "p4-v3-select"
    code = R4.main(
        ["select", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-2001",
         "--handoff-export", str(handoff)]
    )  # fmt: skip
    assert code == 0
    return batch_dir, handoff


def test_the_brief_names_the_batch_its_files_its_scratch_and_its_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir, handoff = _select_export(tmp_path)
    capsys.readouterr()
    text = H.brief(batch_dir.parent, handoff, "p4-2001")
    agent = "opus-p4-v3-select-p4-2001"
    assert H.agent_name(handoff, "p4-2001") == agent
    assert f"You are Opus agent {agent}, the selector (S3) of the Phase-4 run v3" in text
    assert "the 1 question(s) of batch p4-2001" in text
    assert f"{handoff.resolve().as_posix()}/p4-2001/MANIFEST.jsonl" in text
    scratch = (tmp_path / "handoff" / "p4-v3-select-scratch" / "p4-2001").resolve().as_posix()
    assert f"{scratch}/<site id>.txt" in text
    assert f"--stage finder --label <label> --answered-by {agent}" in text
    assert "check-answer --run-dir" in text and "no web page" in text
    assert H.main(["brief", "--run-dir", str(batch_dir.parent), "--handoff", str(handoff),
                   "--batch-id", "p4-2001"]) == 0  # fmt: skip
    assert capsys.readouterr().out.strip() == text.strip()


def test_a_brief_for_a_batch_the_directory_does_not_ask_is_refused(tmp_path: Path) -> None:
    batch_dir, handoff = _select_export(tmp_path)
    with pytest.raises(H.HandoffCheckError, match="no question"):
        H.brief(batch_dir.parent, handoff, "p4-2002")
    assert H.main(["brief", "--run-dir", str(batch_dir.parent), "--handoff", str(handoff),
                   "--batch-id", "p4-2002"]) == 2  # fmt: skip


def test_check_answer_reads_the_selection_through_the_stages_own_parser(tmp_path: Path) -> None:
    batch_dir, handoff = _select_export(tmp_path)
    run = batch_dir.parent
    assert H.check_answer(run, handoff, "p4-2001", "site-1/select", SELECT) is None
    assert H.check_answer(run, handoff, "p4-2001", "site-1/select", "ABSTAIN: no text") is None
    problem = H.check_answer(run, handoff, "p4-2001", "site-1/select", "DESC: W99\n")
    assert problem is not None and problem.startswith("selection-refused") and "W99" in problem
    problem = H.check_answer(
        run, handoff, "p4-2001", "site-1/select", "Here is my answer:\nDESC: W1"
    )
    assert problem is not None and "unknown-line" in problem
    with pytest.raises(H.HandoffCheckError, match="no question"):
        H.check_answer(run, handoff, "p4-2001", "site-9/select", SELECT)


def test_check_answer_refuses_a_question_the_batch_no_longer_builds(tmp_path: Path) -> None:
    """The pool the answer is read against must be the one the question showed."""
    batch_dir, handoff = _select_export(tmp_path)
    store = B.evidence_store(batch_dir)
    path = store.path_for("site-1", M.source_feature("W", "txt"))
    path.write_bytes(path.read_bytes() + b" A later edit of the article.")
    with pytest.raises(H.HandoffCheckError, match="no longer builds the exported prompt"):
        H.check_answer(batch_dir.parent, handoff, "p4-2001", "site-1/select", SELECT)


def _review_export(tmp_path: Path) -> tuple[Path, Path]:
    batch_dir = _selected_batch(tmp_path)
    handoff = tmp_path / "handoff" / "p4-v3-review"
    code = R4.main(
        ["review", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001",
         "--handoff-export", str(handoff)]
    )  # fmt: skip
    assert code == 0
    return batch_dir, handoff


def test_check_answer_reads_the_review_whole(tmp_path: Path) -> None:
    """Every shown sentence once and the card once: the import reads a missing line as a DROP."""
    batch_dir, handoff = _review_export(tmp_path)
    run = batch_dir.parent
    full = "R1: KEEP\nR2: DROP later building\nR3: KEEP\nR4: KEEP\nCARD: KEEP\n"
    assert H.check_answer(run, handoff, "p4-0001", "site-1/review", full) is None
    for text, match in (
        ("R1: KEEP\nR2: KEEP\nR3: KEEP\nCARD: KEEP\n", "R1 .. R4, each once"),
        ("R1: KEEP\nR1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\nCARD: KEEP\n", "each once"),
        ("R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\n", "0 CARD line"),
        ("R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\nCARD: KEEP\nCARD: KEEP\n", "2 CARD line"),
        ("R1: KEEP\nR5: KEEP\n", "review-unparseable"),
        ("R1: KEEP because\n", "review-unparseable"),
    ):
        problem = H.check_answer(run, handoff, "p4-0001", "site-1/review", text)
        assert problem is not None and match in problem, (text, problem)


def _answer_select(handoff: Path) -> None:
    OH.write_answer(
        handoff,
        batch_id="p4-2001",
        stage="finder",
        label="site-1/select",
        text=SELECT,
        answered_by=H.agent_name(handoff, "p4-2001"),
        now=lambda: "2026-09-26T12:00:00+00:00",
    )


def test_ready_names_the_batches_whose_every_question_is_answered(tmp_path: Path) -> None:
    batch_dir, handoff = _select_export(tmp_path)
    run = batch_dir.parent
    result = H.ready(handoff, run, ["p4-2001"])
    assert not result["ok"] and result["ready"] == [] and result["named_not_ready"] == ["p4-2001"]
    assert result["not_ready"] == {
        "p4-2001": {"answered": 0, "missing": 1, "stale": 0, "malformed": 0}
    }
    _answer_select(handoff)
    result = H.ready(handoff, run, ["p4-2001"])
    assert result["ok"] and result["ready"] == ["p4-2001"]
    ready = ["ready", "--run-dir", str(run), "--handoff", str(handoff)]
    assert H.main([*ready, "--batch", "p4-2001"]) == 0
    orphan = handoff / "p4-2001" / "finder" / "x%2Fselect.answer.json"
    orphan.write_text("{}", encoding="utf-8")
    assert not H.ready(handoff, run)["ok"]


def test_a_named_batch_that_asked_nothing_is_ready_and_a_stray_name_is_refused(
    tmp_path: Path,
) -> None:
    """Review finding 2026-09-26: a batch whose every site was held before the stage has no folder
    in the directory, so `ok` stayed false for a whole group, forever. It is a batch of the run that
    asked nothing: named apart and importable with the rest (had its export not run, its import
    stops at the first question: no answer file). A name that is no batch of the run is refused,
    so a typo can never pass as a batch without questions."""
    batch_dir, handoff = _select_export(tmp_path)
    run = batch_dir.parent
    X.make_batch(tmp_path, [X.w_site("site-2")], run="v3", batch="p4-2002")
    result = H.ready(handoff, run, ["p4-2001", "p4-2002"])
    assert not result["ok"] and result["named_not_ready"] == ["p4-2001"]
    assert result["named_without_questions"] == ["p4-2002"]
    _answer_select(handoff)
    result = H.ready(handoff, run, ["p4-2001", "p4-2002"])
    assert result["ok"] and result["ready"] == ["p4-2001"]
    assert (result["named_not_ready"], result["named_without_questions"]) == ([], ["p4-2002"])
    with pytest.raises(H.HandoffCheckError, match=r"no batch of the run: \['p4-2009'\]"):
        H.ready(handoff, run, ["p4-2001", "p4-2009"])
    ready = ["ready", "--run-dir", str(run), "--handoff", str(handoff)]
    assert H.main([*ready, "--batch", "p4-2001", "--batch", "p4-2002"]) == 0
    assert H.main([*ready, "--batch", "p4-2009"]) == 2
