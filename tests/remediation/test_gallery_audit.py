"""Tests for the G0 persister (`scripts/remediation/gallery_audit/persist_verdicts.py`).

Everything here is offline: no network, no database. The pure functions under test are the ones
that decide *whether* a row may be written and *what* SQL is emitted, which is where the damage
would be done. Every test is written to be capable of failing - the assertions that matter are the
messages and the literal SQL, not bare truthiness.

Two specific traps these tests exist to pin, both of which have bitten this project already:

* `NULL` must render as the SQL keyword `NULL`, never the string `'NULL'`. In migration 0019's
  self-test the opposite mistake produced a test that could not fail.
* The comparison against the old value must be `IS NOT DISTINCT FROM`. The old value here *is*
  NULL, and `image_kind = NULL` is NULL - not true - so it would match no rows at all.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "remediation" / "gallery_audit" / "persist_verdicts.py"
#: Tracked fixture with the shape of the real (gitignored) `video-assets/shorts/*/selection.json`.
FIXTURE_SELECTION = Path(__file__).resolve().parent / "fixtures" / "gallery_shorts_shape"


def _load_module():
    spec = importlib.util.spec_from_file_location("persist_verdicts", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["persist_verdicts"] = module
    spec.loader.exec_module(module)
    return module


pv = _load_module()


# --------------------------------------------------------------------------------------
# reading the input
# --------------------------------------------------------------------------------------


def _write_selection(
    base: Path, slug: str, stills: list[dict], rejected: list[dict] | None = None
) -> Path:
    d = base / slug
    d.mkdir(parents=True, exist_ok=True)
    path = d / "selection.json"
    path.write_text(json.dumps({"stills": stills, "rejected": rejected or []}), encoding="utf-8")
    return path


def _still(image_id: int, kind: str = "site_photo", filename: str = "a.webp") -> dict:
    return {
        "id": image_id,
        "filename": filename,
        "original_url": "https://example.invalid/a.jpg",
        "is_hero": False,
        "width": 1600,
        "height": 1200,
        "verdict": {"kind": kind, "quality": 4, "relevance": 5},
    }


def test_load_verdicts_reads_stills_and_ignores_rejected(tmp_path):
    _write_selection(
        tmp_path,
        "stonehenge",
        [_still(1), _still(2)],
        [{"filename": "b.webp", "reason": "too small (100x100)"}],
    )
    verdicts = pv.load_verdicts(tmp_path)
    assert [v.image_id for v in verdicts] == [1, 2]
    assert all(v.slug == "stonehenge" for v in verdicts)


def test_load_verdicts_raises_when_a_still_has_no_id(tmp_path):
    entry = _still(1)
    del entry["id"]
    _write_selection(tmp_path, "s", [entry])
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "has no id" in str(exc.value)


def test_load_verdicts_raises_on_a_non_integer_id(tmp_path):
    _write_selection(tmp_path, "s", [_still(1) | {"id": "1"}])
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "expected an integer" in str(exc.value)


def test_load_verdicts_raises_on_a_boolean_id(tmp_path):
    """`True` is an `int` in Python, so this needs an explicit exclusion."""
    _write_selection(tmp_path, "s", [_still(1) | {"id": True}])
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "expected an integer" in str(exc.value)


def test_load_verdicts_raises_on_a_kind_outside_the_vocabulary(tmp_path):
    _write_selection(tmp_path, "s", [_still(1, kind="site_photos")])
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "not one of" in str(exc.value)
    assert "CHECK constraint" in str(exc.value)


def test_load_verdicts_raises_when_a_still_has_no_verdict(tmp_path):
    entry = _still(1)
    del entry["verdict"]
    _write_selection(tmp_path, "s", [entry])
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "no verdict object" in str(exc.value)


def test_load_verdicts_raises_when_two_files_disagree_about_one_image(tmp_path):
    _write_selection(tmp_path, "a", [_still(7, kind="site_photo")])
    _write_selection(tmp_path, "b", [_still(7, kind="artifact")])
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "two files disagree about one image" in str(exc.value)


def test_load_verdicts_raises_on_malformed_json(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "selection.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "cannot be read as JSON" in str(exc.value)


def test_load_verdicts_raises_when_there_is_nothing_to_read(tmp_path):
    with pytest.raises(pv.PersistError) as exc:
        pv.load_verdicts(tmp_path)
    assert "no selection.json" in str(exc.value)


def test_load_verdicts_reads_the_shape_the_pipeline_writes():
    """The shape of the real `selection.json` files, as a tracked fixture.

    The 16 input files live under `video-assets/shorts/`, which is gitignored working data, so a
    clean checkout and CI have none of them. This fixture keeps the *shape* of those files - the
    stills list, the verdict object, the keys `load_verdicts` reads - under version control, so the
    reader is exercised everywhere. It deliberately does not pin the 105-row number: see below.
    """
    verdicts = pv.load_verdicts(FIXTURE_SELECTION)
    assert [v.image_id for v in verdicts] == [900001, 900002, 900003]
    assert [v.slug for v in verdicts] == ["arena-site", "arena-site", "dolmen-site"]
    assert {v.kind for v in verdicts} == {"site_photo"}
    # The verdict is kept verbatim - it is the evidence the journal will carry.
    assert verdicts[0].verdict["focus"] == "the site itself"
    assert verdicts[0].entry["filename"] == "Arena_01.webp"


#: `video-assets/shorts` is gitignored working data: present on the workstation that ran the
#: write, absent in a clean checkout and in CI. `load_verdicts` raises when the directory is
#: missing, so this test used to *error* - and turn the tests job red - wherever the dataset is
#: not checked out, exactly like `test_mechanical.py`'s dataset tests before they were guarded.
needs_dataset = pytest.mark.skipif(
    not pv.SELECTION.is_dir(),
    reason=f"{pv.SELECTION} is not present (gitignored video-assets); local measurement only",
)


@needs_dataset
def test_load_verdicts_on_the_real_input_finds_105_rows():
    """LOCAL ONLY. The measured shape of one workstation's artifact, pinned as a number.

    Skipped, not failed, where the directory is absent: 105 is a property of the working data, not
    of the repository. The reader itself is pinned everywhere by the fixture test above.
    """
    verdicts = pv.load_verdicts()
    assert len(verdicts) == 105
    assert len({v.image_id for v in verdicts}) == 105
    assert {v.kind for v in verdicts} == {"site_photo"}


# --------------------------------------------------------------------------------------
# the plan: what may be written
# --------------------------------------------------------------------------------------


def _state(image_id: int, kind: str | None = None, source: str = "ancient_nerds") -> dict:
    return {
        "id": image_id,
        "site_id": "00000000-0000-0000-0000-000000000001",
        "source_id": source,
        "image_kind": kind,
        "filename": "a.webp",
        "is_hero": False,
        "original_url": "https://example.invalid/a.jpg",
    }


def _verdict(image_id: int, kind: str = "site_photo") -> object:
    return pv.Verdict(
        image_id=image_id,
        kind=kind,
        slug="s",
        file=Path("video-assets/shorts/s/selection.json"),
        verdict={"kind": kind},
        entry={"filename": "a.webp"},
    )


def test_build_plan_writes_a_row_whose_kind_is_null():
    write, skipped = pv.build_plan([_verdict(1)], {1: _state(1, None)})
    assert [v.image_id for v in write] == [1]
    assert skipped == []


def test_build_plan_skips_a_row_that_already_carries_the_same_kind():
    write, skipped = pv.build_plan([_verdict(1)], {1: _state(1, "site_photo")})
    assert write == []
    assert [s.reason for s in skipped] == ["already-recorded"]
    assert "nothing to write" in skipped[0].detail


def test_build_plan_refuses_to_overwrite_a_different_verdict():
    """The rule that matters most: one judgement is never replaced by another silently."""
    write, skipped = pv.build_plan([_verdict(1, "site_photo")], {1: _state(1, "artifact")})
    assert write == []
    assert [s.reason for s in skipped] == ["different-verdict-already-recorded"]
    assert "never overwrites one judgement with another" in skipped[0].detail


def test_build_plan_refuses_a_row_whose_site_is_not_curated():
    write, skipped = pv.build_plan([_verdict(1)], {1: _state(1, None, source="lyra")})
    assert write == []
    assert [s.reason for s in skipped] == ["row-not-in-curated-source"]
    assert "source_id='lyra'" in skipped[0].detail


def test_build_plan_refuses_a_row_that_is_not_in_the_database():
    write, skipped = pv.build_plan([_verdict(1)], {})
    assert write == []
    assert [s.reason for s in skipped] == ["id-not-in-database"]


def test_build_plan_accounts_for_every_input_row():
    """No verdict may be dropped silently: write + skipped must equal the input."""
    verdicts = [_verdict(1), _verdict(2), _verdict(3), _verdict(4)]
    state = {1: _state(1, None), 2: _state(2, "artifact"), 3: _state(3, "site_photo")}
    write, skipped = pv.build_plan(verdicts, state)
    assert len(write) + len(skipped) == len(verdicts)


# --------------------------------------------------------------------------------------
# the emitted SQL
# --------------------------------------------------------------------------------------


def test_render_plan_table_emits_the_keyword_null_not_the_string(tmp_path, monkeypatch):
    """Migration 0019's self-test failed exactly here once: a text 'NULL' is not a NULL."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_plan_table([_verdict(1)], {1: _state(1, None)})
    assert ", NULL, 'site_photo'" in sql
    assert "'NULL'" not in sql


def test_render_apply_compares_null_safely(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1)], {1: _state(1, None)})
    # The file *explains* why `= NULL` is wrong, so every check here must ignore comments -
    # otherwise it fires on its own documentation and proves nothing about the SQL. The first two
    # assertions used not to: "IS NOT DISTINCT FROM" and "image_kind = NULL" both occur in prose
    # in this file, so they were satisfied by a comment whatever the generated SQL said.
    code = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    assert any("w.image_kind IS DISTINCT FROM p.old_value" in line for line in code), code
    offenders = [line for line in code if "image_kind = NULL" in line]
    assert offenders == [], offenders
    # ... and the operator really is the NULL-safe one, on the guard's own line and on the
    # invariant that re-reads it: this fails if either is written as `=`.
    comparisons = [line.strip() for line in code if "DISTINCT FROM p." in line]
    assert comparisons == [
        "WHERE w.image_kind IS DISTINCT FROM p.old_value;",
        "WHERE w.image_kind IS DISTINCT FROM p.new_value;",
        "OR l.new_value IS DISTINCT FROM p.new_value",
        "OR l.old_value IS DISTINCT FROM p.old_value;",
    ], comparisons


def test_render_apply_ends_in_exactly_one_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1)], {1: _state(1, None)})
    assert sql.count("COMMIT;") == 1
    assert sql.rstrip().endswith("COMMIT;")


def test_render_apply_counts_the_rows_it_will_move(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1), _verdict(2)], {1: _state(1), 2: _state(2)})
    assert "expected integer := 2;" in sql
    assert sql.startswith("-- Generated by scripts/remediation/gallery_audit/persist_verdicts.py")


def test_render_apply_never_deletes(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1)], {1: _state(1)})
    assert "DELETE" not in sql.upper()


def test_render_apply_scopes_to_the_curated_source(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1)], {1: _state(1)})
    assert "s.source_id <> 'ancient_nerds'" in sql


def test_render_apply_escapes_quotes_in_evidence(tmp_path, monkeypatch):
    """The reason embeds a filename in single quotes; unescaped it would break the statement."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    v = _verdict(1)
    object.__setattr__(v, "entry", {"filename": "O'Brien.webp"})
    sql = pv.render_apply([v], {1: _state(1)})
    assert "O''Brien.webp" in sql
    assert "O'Brien.webp" not in sql


def test_guards_never_embed_the_source_name_in_a_quoted_message(tmp_path, monkeypatch):
    """A literal 'ancient_nerds' inside a single-quoted RAISE message terminates the string; the
    rehearsal caught exactly that (psql: syntax error at or near "ancient_nerds"). The guards are
    therefore checked on the emitted text, not just on the template."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1)], {1: _state(1)})
    guards = sql[sql.index("-- scope guard 1") : sql.index("-- the only writer")]
    # Comments explain the bug and therefore quote the offending form; only code is judged.
    code = "\n".join(line for line in guards.splitlines() if not line.strip().startswith("--"))
    assert "''" not in code, "a doubled quote inside the guards means a literal was embedded"
    # The name may (and must) appear as a RAISE *argument*; it must not appear inside a quoted
    # message, which is what terminates the string. Judging the message text is the precise form.
    messages = re.findall(r"RAISE EXCEPTION '((?:[^']|'')*)'", code)
    assert messages, "no RAISE EXCEPTION was found in the guards at all"
    for message in messages:
        assert "ancient_nerds" not in message, message
    assert "source_id %', bad, 'ancient_nerds'" in code


def test_render_rollback_returns_the_column_to_null(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_rollback([_verdict(1)], {1: _state(1, "site_photo")})
    assert ", NULL, 'g0-vlm-kind-rollback:1'" in sql
    assert "are still not NULL" in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_render_rollback_guards_against_rolling_back_a_row_that_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_rollback([_verdict(1)], {1: _state(1, "site_photo")})
    assert "IS DISTINCT FROM p.old_value" in sql
    assert "no longer hold the planned old value" in sql


def test_render_rollback_carries_every_guard_the_apply_carries(tmp_path, monkeypatch):
    """The undo used to carry three guards fewer than the write, and was never parsed by psql.

    Rolling back is the one operation that runs when something has already gone wrong, so it is the
    last place to accept a guard that was hand-shortened out.
    """
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_rollback([_verdict(1)], {1: _state(1, "site_photo")})
    code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    # guard 1: the row exists.
    assert "LEFT JOIN wiki_images w ON w.id = p.image_id WHERE w.id IS NULL" in code
    # guard 2: the row belongs to a curated site - the source_id test the undo never had.
    assert "JOIN unified_sites s ON s.id = w.site_id" in code
    assert "s.source_id <> 'ancient_nerds'" in code
    # guard 3: the row still holds the value being undone.
    assert "w.image_kind IS DISTINCT FROM p.old_value" in code
    # and the journal reconciliation, in the transaction rather than after the COMMIT.
    assert "disagree with the reversal journal" in code
    assert "this run stamp journalled % row(s) outside wiki_images.image_kind" in code


def test_render_rollback_writes_one_row_per_line(tmp_path, monkeypatch):
    """One 86.7 KB line cannot be read by a line-oriented tool, diffed, or checked pairwise.

    Both files are generated from the same record set, so they are formatted the same way: `,\n`
    between tuples. The mechanical lane's ROLLBACK.sql is the model.
    """
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    ids = [11, 22, 33]
    state = {i: _state(i, "site_photo") for i in ids}
    sql = pv.render_rollback([_verdict(i) for i in ids], state)
    block = sql.split("VALUES\n", 1)[1].split(";\n", 1)[0]
    rows = block.splitlines()
    assert len(rows) == 3, rows
    assert all(row.startswith("    (") for row in rows), rows
    assert [row.split(",")[0] for row in rows] == ["    (11", "    (22", "    (33"]


# --------------------------------------------------------------------------------------
# emission order: the undo must exist before the do
# --------------------------------------------------------------------------------------


def test_emit_writes_the_rollback_before_the_apply(tmp_path, monkeypatch):
    """If the process dies between the two writes, the safe direction is a rollback with no apply."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    order: list[str] = []
    real_write_text = Path.write_text

    def recording_write_text(self, *args, **kwargs):
        order.append(self.name)
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording_write_text)
    pv.emit([_verdict(1)], [], {1: _state(1)})

    assert "ROLLBACK.sql" in order and "APPLY.sql" in order
    assert order.index("ROLLBACK.sql") < order.index("APPLY.sql")


def test_emit_writes_every_deliverable(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    paths = pv.emit([_verdict(1)], [], {1: _state(1)})
    for name in ("plan_md", "plan_jsonl", "skipped", "rollback", "apply"):
        assert Path(paths[name]).is_file(), name
    record = json.loads((tmp_path / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["table"] == "wiki_images"
    assert record["column"] == "image_kind"
    assert record["key_column"] == "id"
    assert record["new_value"] == "site_photo"
    assert record["old_value"] is None
    assert "IS NOT DISTINCT FROM NULL" in record["condition"]


# --------------------------------------------------------------------------------------
# the rehearsal transform
# --------------------------------------------------------------------------------------


def test_rehearsal_swaps_only_the_final_commit(tmp_path):
    """The rehearsal must run the real file, not a hand-written approximation of it.

    The earlier version of this test re-implemented the substitution inline - and never used its
    `tmp_path`, the tell - so it asserted on its own arithmetic. The module's transform is called
    here instead, which is what `--rehearse` actually runs.
    """
    apply_sql = "BEGIN;\nSELECT 1;\nCOMMIT;\n"
    rehearsal = pv.rehearsal_of(apply_sql)
    assert rehearsal == "BEGIN;\nSELECT 1;\nROLLBACK;\n"
    assert rehearsal.count("ROLLBACK;") == 1
    assert "COMMIT;" not in rehearsal
    assert tmp_path.is_dir()


def test_rehearsal_refuses_a_file_that_does_not_end_in_one_commit():
    """The refusal guard, not a repetition of its condition: if it let a two-COMMIT file through,
    `--rehearse` would run the real statement against production and report REHEARSAL OK."""
    for bad in ("BEGIN;\nCOMMIT;\nCOMMIT;\n", "BEGIN;\nSELECT 1;\n"):
        with pytest.raises(pv.PersistError) as exc:
            pv.rehearsal_of(bad)
        assert "exactly one COMMIT;" in str(exc.value)
    # A COMMENT mentioning COMMIT; inside the body is what the emitted files contain: exactly one
    # terminator, at the end. The good case must pass, so the guard cannot be satisfied by refusing
    # everything.
    assert pv.rehearsal_of("BEGIN;\nSELECT 1;\nCOMMIT;\n").endswith("ROLLBACK;\n")


def _psql_result(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["psql"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_command_rehearse_sends_a_rollback_and_never_the_apply(tmp_path, monkeypatch, capsys):
    """`--rehearse` must send the transformed script, and must reject a session that committed."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1)], [], {1: _state(1)})
    sent: list[str] = []

    def fake_run_psql(sql, **kwargs):
        sent.append(sql)
        if "context only: curated rows holding site_photo" in sql:
            return _psql_result("context only: curated rows holding site_photo|1")
        return _psql_result("BEGIN\nDO\nplanned rows written|1\nROLLBACK\n")

    monkeypatch.setattr(pv, "run_psql", fake_run_psql)
    assert pv.command_rehearse() == pv.EXIT_OK
    assert "COMMIT;" not in sent[0], sent[0]
    assert sent[0].rstrip().endswith("ROLLBACK;")
    assert "REHEARSAL OK" in capsys.readouterr().out

    # And the same command must not report OK for a session whose tag says COMMIT: that is the
    # rehearsal having applied the rows for real.
    monkeypatch.setattr(
        pv, "run_psql", lambda sql, **kw: _psql_result("planned rows written|1\nCOMMIT\n")
    )
    assert pv.command_rehearse() == pv.EXIT_INCONSISTENT
    assert "INCONCLUSIVE" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# the checked conversion
# --------------------------------------------------------------------------------------


def test_as_int_accepts_an_integer():
    assert pv._as_int(5, what="x") == 5


@pytest.mark.parametrize("value", ["5", 5.0, None, True, False, [5]])
def test_as_int_rejects_anything_else(value):
    with pytest.raises(pv.PersistError) as exc:
        pv._as_int(value, what="wiki_images.id")
    assert "wiki_images.id" in str(exc.value)
    assert "expected an integer" in str(exc.value)


def test_the_module_has_no_bare_type_ignore():
    """A wrong ignore code is not a fix. The project sets warn_unused_ignores=false, so mypy
    would not have caught the one this file originally carried - this pins the removal."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "type: ignore" not in source


# --------------------------------------------------------------------------------------
# the empty plan may not destroy the undo (B1)
# --------------------------------------------------------------------------------------


def test_render_apply_and_rollback_refuse_an_empty_plan(tmp_path, monkeypatch):
    """An empty plan still renders a *plausible* file: header, transaction, guard block.

    It would replace the real one and, for ROLLBACK.sql, that is the only undo of a write that has
    already landed.
    """
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    for fn in (pv.render_apply, pv.render_rollback):
        with pytest.raises(pv.PersistError) as exc:
            fn([], {})
        assert "empty plan" in str(exc.value), fn.__name__


def test_emit_refuses_an_empty_plan_and_leaves_the_delivered_files_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1)], [], {1: _state(1)})
    before = {
        name: (tmp_path / name).read_bytes()
        for name in ("APPLY.sql", "ROLLBACK.sql", "PLAN.jsonl", "PLAN.md")
    }
    with pytest.raises(pv.PersistError) as exc:
        pv.emit([], [], {})
    assert "empty plan" in str(exc.value)
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content, name


def test_command_plan_on_a_landed_write_does_not_touch_the_undo(tmp_path, monkeypatch, capsys):
    """The documented trigger: `--plan` is the first of the post-write verification commands.

    On a landed write its write list is empty, and the old order (`emit` at the top, the emptiness
    check at the bottom) wrote the deliverables first and asked afterwards.
    """
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1)], [], {1: _state(1)})
    before = {
        name: (tmp_path / name).read_bytes()
        for name in ("APPLY.sql", "ROLLBACK.sql", "PLAN.jsonl", "PLAN.md")
    }
    monkeypatch.setattr(pv, "load_verdicts", lambda base=pv.SELECTION: [_verdict(1)])
    monkeypatch.setattr(pv, "read_state", lambda ids: {1: _state(1, "site_photo")})

    assert pv.command_plan() == pv.EXIT_NOTHING
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content, name
    out = capsys.readouterr().out
    assert "rows to write          : 0" in out
    assert "nothing to write" in out
    assert "left exactly as they are" in out


# --------------------------------------------------------------------------------------
# identity, not cardinality (SQL 1 / B2)
# --------------------------------------------------------------------------------------


def test_verify_sql_compares_nothing_table_wide():
    """The metric set is pinned, so the table-wide count cannot be re-wired into a comparison."""
    sql = pv.verify_sql()
    labels = re.findall(r"^SELECT '([^']+)',", sql, re.MULTILINE)
    assert labels == [
        "journal rows for this run",
        "rows with image_kind = site_photo and no journal row for this run",
        "journal rows for this run outside wiki_images.image_kind",
        "journal rows for this run with no evidence",
        "table-wide context: rows with image_kind = site_photo (never compared to the journal)",
        "context only: curated rows still without a kind",
        "rows with a kind outside the vocabulary",
        "curated images",
        "distinct curated sites now carrying a kind",
    ]
    # The tie to the plan is the *journal's row set*, which is read by `journalled_ids` - one row
    # per line, so a set can be built from it rather than a count.
    assert "string_agg(l.row_pk, ',')" in pv.journalled_ids_sql(
        "2026-09-21_gallery-verdicts-persist"
    )
    assert "_kind_plan" not in sql, "the post-hoc query must not read the ON COMMIT DROP table"


def _metrics(**overrides: int) -> str:
    base = {
        "journal rows for this run": 2,
        "rows with image_kind = site_photo and no journal row for this run": 0,
        "journal rows for this run outside wiki_images.image_kind": 0,
        "journal rows for this run with no evidence": 0,
        "table-wide context: rows with image_kind = site_photo (never compared to the journal)": 105,
        "context only: curated rows still without a kind": 0,
        "rows with a kind outside the vocabulary": 0,
        "curated images": 300,
        "distinct curated sites now carrying a kind": 16,
    }
    base.update(overrides)
    return "".join(f"{name}|{value}\n" for name, value in base.items())


def _delivered_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1), _verdict(2)], [], {1: _state(1), 2: _state(2)})
    return pv.load_plan_records(tmp_path / "PLAN.jsonl")


def test_command_verify_accepts_a_run_count_that_differs_from_the_table_wide_one(
    tmp_path, monkeypatch, capsys
):
    """The false alarm this finding is about: 2 journalled rows, 105 site_photo rows in the table.

    Those two numbers are allowed to differ - they agreed on the day of the write only because G0
    was the first writer of `site_photo`. Comparing them made `--verify` fail on a healthy write.
    """
    _delivered_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(pv, "run_psql", lambda sql, **kw: _psql_result(_metrics()))
    monkeypatch.setattr(pv, "read_rows", lambda sql: [{"row_pks": "1,2", "disagreeing": 0}])
    assert pv.command_verify() == pv.EXIT_OK
    assert "VERIFY OK" in capsys.readouterr().out


def test_command_verify_fails_when_the_journal_names_a_row_the_plan_does_not(
    tmp_path, monkeypatch, capsys
):
    _delivered_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(pv, "run_psql", lambda sql, **kw: _psql_result(_metrics()))
    monkeypatch.setattr(pv, "read_rows", lambda sql: [{"row_pks": "1,3", "disagreeing": 0}])
    assert pv.command_verify() == pv.EXIT_VERIFY_FAILED
    out = capsys.readouterr().out
    assert "journal for" in out and "not in the plan" in out


def test_command_verify_fails_when_a_journalled_row_no_longer_holds_its_value(
    tmp_path, monkeypatch, capsys
):
    """A complete journal whose data has moved on: the count is right, the state is not."""
    _delivered_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(pv, "run_psql", lambda sql, **kw: _psql_result(_metrics()))
    monkeypatch.setattr(pv, "read_rows", lambda sql: [{"row_pks": "1,2", "disagreeing": 1}])
    assert pv.command_verify() == pv.EXIT_VERIFY_FAILED
    assert "no longer hold the value" in capsys.readouterr().out


def test_run_stamp_for_keeps_the_landed_stamp_and_derives_any_other(tmp_path, monkeypatch):
    """A module-wide constant would let a second batch journal under the first batch's name."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    landed = [_verdict(1), _verdict(2)]
    pv.emit(landed, [], {1: _state(1), 2: _state(2)})

    assert pv.run_stamp_for(landed) == pv.RUN_STAMP
    wider = [*landed, _verdict(3)]
    derived = pv.run_stamp_for(wider)
    assert derived.startswith(pv.BATCH_STAMP_PREFIX)
    assert derived != pv.RUN_STAMP
    # Stable across order (it is a digest of the identity set) and distinct per batch.
    assert pv.run_stamp_for(list(reversed(wider))) == derived
    assert pv.run_stamp_for([_verdict(3)]) != derived


def test_emit_derives_the_stamp_of_a_batch_that_is_not_the_landed_one(tmp_path, monkeypatch):
    """And the derived stamp reaches every file, not just the header of one."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    # The batch whose record is on disk: writing it again keeps the landed stamp.
    pv.emit([_verdict(1), _verdict(2)], [], {1: _state(1), 2: _state(2)})
    assert pv.run_stamp_for([_verdict(1), _verdict(2)]) == pv.RUN_STAMP

    # A different batch may not journal under that name.
    stamp = pv.run_stamp_for([_verdict(3)])
    assert stamp != pv.RUN_STAMP
    pv.emit([_verdict(3)], [], {3: _state(3)})
    record = json.loads((tmp_path / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["run_stamp"] == stamp
    assert stamp in (tmp_path / "APPLY.sql").read_text(encoding="utf-8")
    assert f"{stamp}-rollback" in (tmp_path / "ROLLBACK.sql").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# the vocabulary has one source (B6)
# --------------------------------------------------------------------------------------


def test_the_vocabulary_is_the_one_the_migration_enforces():
    """Both directions, against the file that actually enforces it."""
    migration = (REPO / "migrations" / "0019_wiki_images_image_kind.sql").read_text(
        encoding="utf-8"
    )
    match = re.search(r"image_kind\s+IN\s*\(([^)]*)\)", migration)
    assert match is not None, "the migration no longer has an image_kind IN (...) constraint"
    enforced = {token.strip().strip("'") for token in match.group(1).split(",") if token.strip()}
    assert enforced == set(pv.VOCAB)
    # And the rendered query is built from VOCAB, so it cannot drift from the check above.
    rendered = re.search(r"image_kind NOT IN \(([^)]*)\)", pv.verify_sql())
    assert rendered is not None, "the verify query no longer states the vocabulary"
    assert {t.strip().strip("'") for t in rendered.group(1).split(",")} == set(pv.VOCAB)


# --------------------------------------------------------------------------------------
# the SQL literal refuses control characters (SECURITY 1)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["a\nb", "a\rb", "a\tb", "a\x00b", "a\x1bb", "a\x7fb"])
def test_sql_literal_refuses_control_characters(value):
    """Fail closed. Doubling apostrophes is not escaping: a newline can start a line with `\\`."""
    with pytest.raises(pv.PersistError) as exc:
        pv._sql_literal(value)
    assert "U+" in str(exc.value)


def test_sql_literal_still_doubles_apostrophes():
    assert pv._sql_literal("O'Brien") == "'O''Brien'"


def test_a_slug_with_a_newline_cannot_put_a_backslash_at_the_start_of_a_line(tmp_path, monkeypatch):
    """`slug` comes from a directory name and was the one external value passed un-repr-ed."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    v = _verdict(1)
    object.__setattr__(v, "slug", "evil\n\\! ls")
    sql = pv.render_apply([v], {1: _state(1)})
    # repr-ed like its neighbours: escaped inside one line ...
    assert "'evil\\n\\\\! ls'" in sql
    # ... so no line of the script begins with a backslash, which psql reads as a meta-command.
    assert [line for line in sql.splitlines() if line.lstrip().startswith("\\")] == [
        "\\set ON_ERROR_STOP on"
    ]


# --------------------------------------------------------------------------------------
# the delivered scripts are tied to the plan (SECURITY 3 / B7)
# --------------------------------------------------------------------------------------


def test_plan_digest_notices_a_changed_value_and_ignores_row_order():
    a = pv.plan_records([_verdict(1), _verdict(2)], {1: _state(1), 2: _state(2)})
    assert pv.plan_digest(a) == pv.plan_digest(list(reversed(a)))
    other_kind = pv.plan_records(
        [_verdict(1), _verdict(2, "artifact")], {1: _state(1), 2: _state(2)}
    )
    assert pv.plan_digest(a) != pv.plan_digest(other_kind)
    # The 105-right-values-on-105-wrong-rows case: same ids, same count, different records.
    swapped = pv.plan_records([_verdict(1), _verdict(2)], {1: _state(1, "unknown"), 2: _state(2)})
    assert pv.plan_digest(a) != pv.plan_digest(swapped)


def test_both_delivered_scripts_carry_the_plan_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1), _verdict(2)], [], {1: _state(1), 2: _state(2)})
    records = pv.load_plan_records(tmp_path / "PLAN.jsonl")
    expected = pv.plan_digest(records)
    for name in ("APPLY.sql", "ROLLBACK.sql"):
        path = tmp_path / name
        assert f"-- plan sha256 {expected}" in path.read_text(encoding="utf-8"), name
    assert pv.verify_delivered(tmp_path / "APPLY.sql", records) == expected
    assert pv.verify_delivered(tmp_path / "ROLLBACK.sql", records, invert=True) == expected


def test_script_records_reads_back_the_record_set_the_script_carries(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1), _verdict(2)], [], {1: _state(1), 2: _state(2)})
    records = pv.load_plan_records(tmp_path / "PLAN.jsonl")
    assert pv.plan_digest(pv.script_records(tmp_path / "APPLY.sql")) == pv.plan_digest(records)
    assert pv.plan_digest(pv.script_records(tmp_path / "ROLLBACK.sql")) == pv.plan_digest(
        pv.inverted_records(records)
    )


def test_verify_delivered_refuses_a_script_that_drifted_from_the_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1)], [], {1: _state(1)})
    records = pv.load_plan_records(tmp_path / "PLAN.jsonl")
    text = (tmp_path / "APPLY.sql").read_text(encoding="utf-8")

    tampered = tmp_path / "TAMPERED.sql"
    tampered.write_text(text.replace("'site_photo'", "'unknown'", 1), encoding="utf-8")
    with pytest.raises(pv.PersistError) as exc:
        pv.verify_delivered(tampered, records)
    assert "is not what this file would apply" in str(exc.value)

    headerless = tmp_path / "HEADERLESS.sql"
    headerless.write_text(
        "\n".join(line for line in text.splitlines() if "-- plan sha256" not in line),
        encoding="utf-8",
    )
    with pytest.raises(pv.PersistError) as exc:
        pv.verify_delivered(headerless, records)
    assert "no '-- plan sha256' header" in str(exc.value)

    # A foreign script - this file with a digest that names another plan - is refused too.
    foreign = tmp_path / "FOREIGN.sql"
    foreign.write_text(
        re.sub(r"(-- plan sha256 )[0-9a-f]{64}", r"\g<1>" + "0" * 64, text), encoding="utf-8"
    )
    with pytest.raises(pv.PersistError) as exc:
        pv.verify_delivered(foreign, records)
    assert "have drifted apart" in str(exc.value)


def test_command_apply_refuses_a_script_whose_records_are_not_the_plan(tmp_path, monkeypatch):
    """The check runs *before* anything is sent, so the refusal proves nothing was sent."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1)], [], {1: _state(1)})
    path = tmp_path / "APPLY.sql"
    path.write_text(
        path.read_text(encoding="utf-8").replace("'site_photo'", "'unknown'", 1), encoding="utf-8"
    )
    sent: list[str] = []

    def record_and_succeed(sql: str, **kw: object) -> subprocess.CompletedProcess:
        sent.append(sql)
        return _psql_result("")

    monkeypatch.setattr(pv, "run_psql", record_and_succeed)
    with pytest.raises(pv.PersistError) as exc:
        pv.command_apply()
    assert "not what this file would apply" in str(exc.value)
    assert sent == []


def test_command_apply_reports_a_retry_of_a_landed_write_as_not_needed(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1), _verdict(2)], [], {1: _state(1), 2: _state(2)})
    # guard 3 trips on a retry: the rows no longer hold the planned old value (NULL).
    monkeypatch.setattr(
        pv, "run_psql", lambda sql, **kw: _psql_result("", returncode=3, stderr="guard 3\n")
    )
    monkeypatch.setattr(pv, "read_rows", lambda sql: [{"row_pks": "1,2", "disagreeing": 0}])
    assert pv.command_apply() == pv.EXIT_NOTHING
    out = capsys.readouterr().out
    assert "APPLY NOT NEEDED" in out
    assert "APPLY FAILED" not in out

    # A journal that does not hold the plan is not a retry, and stays a failure.
    monkeypatch.setattr(pv, "read_rows", lambda sql: [{"row_pks": "1", "disagreeing": 0}])
    assert pv.command_apply() == pv.EXIT_INCONSISTENT
    assert "APPLY FAILED: psql exit=3" in capsys.readouterr().out


def test_run_psql_reports_a_timeout_as_an_unknown_outcome(monkeypatch):
    """A timeout is not a failure like any other: the COMMIT may or may not have landed."""

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=900)

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    with pytest.raises(pv.OutcomeUnknown) as exc:
        pv.run_psql("SELECT 1;")
    assert "UNKNOWN" in str(exc.value)


def test_main_reports_an_unknown_outcome_with_its_own_exit_code(monkeypatch, capsys):
    def boom(output):
        assert output == pv.OUTPUT  # the default source is G0's own directory
        raise pv.OutcomeUnknown("psql did not answer within 900s")

    monkeypatch.setattr(pv, "command_apply", boom)
    assert pv.main(["--apply"]) == pv.EXIT_UNKNOWN
    err = capsys.readouterr().err
    assert "OUTCOME UNKNOWN" in err
    assert "REFUSED" not in err


def test_run_psql_cannot_hang_on_a_dead_ssh_channel(monkeypatch):
    """Without a connect timeout a hung channel sits for the full 900 s."""
    argv: list[list[str]] = []

    def fake_run(args, **kwargs):
        argv.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    pv.run_psql("SELECT 1;")
    joined = " ".join(argv[0])
    assert "-o ConnectTimeout=" in joined
    assert "ServerAliveInterval=" in joined
    assert "ancientnerds" in joined


# --------------------------------------------------------------------------------------
# the rollback guards fail closed, in the transaction (SQL 2 / SQL 9)
# --------------------------------------------------------------------------------------


def test_the_guard_block_raises_with_the_scope_it_was_called_under():
    apply_guards = pv.guards_sql("G0")
    rollback_guards = pv.guards_sql("G0 rollback")
    assert "RAISE EXCEPTION 'G0 image_kind: % planned row(s) do not exist'" in apply_guards
    assert (
        "RAISE EXCEPTION 'G0 rollback image_kind: % planned row(s) do not exist'" in rollback_guards
    )
    # The scope is carried by all three guards, not just the first.
    assert rollback_guards.count("'G0 rollback image_kind:") == 3
    assert "{scope}" not in rollback_guards


def test_the_journal_scope_violation_raises_inside_the_transaction(tmp_path, monkeypatch):
    """G0 used to print the same number after the COMMIT: fail-late instead of fail-closed."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    sql = pv.render_apply([_verdict(1)], {1: _state(1)})
    do_block = sql.split("DO $$", 1)[1].split("END $$;", 1)[0]
    # Comments inside the block explain the old defect and quote it; only code is judged.
    code = "\n".join(line for line in do_block.splitlines() if not line.strip().startswith("--"))
    assert "this run stamp journalled % row(s) outside wiki_images.image_kind" in code
    assert "RAISE EXCEPTION" in code
    assert "COMMIT" not in code


# --------------------------------------------------------------------------------------
# the delivered record, pairwise (SQL 3)
# --------------------------------------------------------------------------------------


DELIVERED = REPO / "output" / "remediation" / "gallery_audit"
needs_deliverable = pytest.mark.skipif(
    not (DELIVERED / "PLAN.jsonl").is_file(),
    reason=f"{DELIVERED}/PLAN.jsonl is not checked out; the delivered-record checks are local",
)


@needs_deliverable
def test_the_delivered_rollback_inverts_the_delivered_plan_pairwise():
    """105 tuples on one 86.7 KB line could not be read, diffed or checked row by row."""
    records = pv.load_plan_records(DELIVERED / "PLAN.jsonl")
    text = (DELIVERED / "ROLLBACK.sql").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith("    (")]
    assert len(lines) == len(records) == 105
    by_id = {int(line.split(",")[0].strip().lstrip("(")): line for line in lines}
    assert set(by_id) == {int(r["image_id"]) for r in records}
    for record in records:
        image_id = int(record["image_id"])
        expected = (
            f"({image_id}, '{record['site_id']}'::uuid, "
            f"{pv._sql_literal(str(record['new_value']))}, NULL, "
            f"{pv._sql_literal(pv.rollback_change_key_of(image_id))},"
        )
        assert expected in by_id[image_id], image_id
    # Both delivered scripts are the ones the plan renders, by hash: the apply as the plan, the
    # undo as its inversion.
    assert pv.verify_delivered(DELIVERED / "APPLY.sql", records) == pv.plan_digest(records)
    assert pv.verify_delivered(DELIVERED / "ROLLBACK.sql", records, invert=True) == pv.plan_digest(
        records
    )


@needs_deliverable
def test_the_delivered_plan_carries_the_landed_run_stamp():
    """The stamp of the landed write is a fact about production; the plan records it."""
    records = pv.load_plan_records(DELIVERED / "PLAN.jsonl")
    assert pv.load_plan_stamp(records, path=DELIVERED / "PLAN.jsonl") == pv.RUN_STAMP


# --------------------------------------------------------------------------------------
# G0b: the kinds the pipeline stated in its rejections (--source rejected-kinds)
# --------------------------------------------------------------------------------------

G0B_SITE = "eff62515-9b70-43cc-afe6-c803dd4b5bc3"


def _rejected_record(image_id: int, kind: str = "artifact", **over: object) -> dict:
    record = {
        "slug": "giza-necropolis",
        "filename": f"Stele_{image_id}.webp",
        "reason": f"kind={kind}",
        "kind_stated": kind,
        "site_id": G0B_SITE,
        "verdict": "PROVEN",
        "image_id": image_id,
        "evidence": [f"images.json of the short has exactly one entry (id {image_id})"],
    }
    record.update(over)
    return record


def _rejected_file(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "REJECTED_KINDS.jsonl"
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    return path


def _g0b_state(verdicts, *, kind=None, site=G0B_SITE, filename=None) -> dict:
    return {
        v.image_id: {
            "id": v.image_id,
            "site_id": site,
            "source_id": "ancient_nerds",
            "image_kind": kind,
            "filename": filename or v.entry["filename"],
            "is_hero": False,
            "original_url": "https://upload.wikimedia.org/x.jpg",
        }
        for v in verdicts
    }


def test_the_versioned_mapping_yields_the_30_proven_rejections():
    """`REJECTED_KINDS.jsonl` is tracked, so this runs everywhere: 30 PROVEN of 30, 8 sites."""
    verdicts, refused = pv.load_rejected_kinds()
    assert refused == []
    assert len(verdicts) == len({v.image_id for v in verdicts}) == 30
    assert len({v.site_id for v in verdicts}) == 8
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v.kind] = counts.get(v.kind, 0) + 1
    assert counts == {"artifact": 17, "map_or_document": 9, "painting_or_artwork": 3, "other": 1}
    assert {v.source for v in verdicts} == {"rejected-kinds"}
    assert all(v.verdict["reason"] == f"kind={v.kind}" for v in verdicts)


def test_a_mapping_that_is_not_proven_is_a_named_refusal(tmp_path):
    path = _rejected_file(
        tmp_path,
        _rejected_record(1),
        _rejected_record(2, verdict="AMBIGUOUS", evidence=["only a case-insensitive match"]),
    )
    verdicts, refused = pv.load_rejected_kinds(path)
    assert [v.image_id for v in verdicts] == [1]
    assert [(s.image_id, s.reason) for s in refused] == [(2, "mapping-not-proven")]
    assert "AMBIGUOUS: only a case-insensitive match" in refused[0].detail


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"kind_stated": "map_or_document"}, "is not the kind the reason names"),
        ({"kind_stated": "photo", "reason": "kind=photo"}, "is not one of"),
        ({"site_id": "Giza"}, "is not a UUID"),
        ({"image_id": "1"}, "expected an integer"),
        ({"verdict": "LIKELY"}, "is none of"),
    ],
)
def test_a_malformed_mapping_record_stops_the_lane(tmp_path, override, says):
    path = _rejected_file(tmp_path, _rejected_record(1) | override)
    with pytest.raises(pv.PersistError) as exc:
        pv.load_rejected_kinds(path)
    assert says in str(exc.value)


def test_one_image_with_two_stated_kinds_stops_the_lane(tmp_path):
    path = _rejected_file(tmp_path, _rejected_record(1), _rejected_record(1, "other"))
    with pytest.raises(pv.PersistError, match="already stated"):
        pv.load_rejected_kinds(path)


def test_a_mapping_without_a_proven_record_writes_nothing(tmp_path):
    path = _rejected_file(tmp_path, _rejected_record(1, verdict="UNPROVABLE"))
    with pytest.raises(pv.PersistError, match="no PROVEN record"):
        pv.load_rejected_kinds(path)


@pytest.mark.parametrize(
    ("state_over", "why"),
    [
        ({"site": "00000000-0000-4000-8000-000000000009"}, "site"),
        ({"filename": "Renamed.webp"}, "filename"),
    ],
)
def test_a_row_that_no_longer_matches_the_proof_is_refused(tmp_path, state_over, why):
    verdicts, _ = pv.load_rejected_kinds(_rejected_file(tmp_path, _rejected_record(1)))
    write, skipped = pv.build_plan(verdicts, _g0b_state(verdicts, **state_over))
    assert write == []
    assert [s.reason for s in skipped] == ["row-no-longer-matches-the-proof"]
    assert why in skipped[0].detail


def test_g0b_never_journals_under_the_landed_g0_stamp(tmp_path, monkeypatch):
    """Not even after its own plan is on disk: the stamp is decided against G0's landed plan."""
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1), _verdict(2)], [], {1: _state(1), 2: _state(2)})  # the landed G0 batch
    verdicts, _ = pv.load_rejected_kinds(
        _rejected_file(tmp_path, _rejected_record(3), _rejected_record(4, "other"))
    )
    state = _g0b_state(verdicts)
    stamps = []
    for _ in range(2):  # the second emit finds its own PLAN.jsonl already delivered
        pv.emit(verdicts, [], state)
        records = pv.load_plan_records(tmp_path / "rejected_kinds" / "PLAN.jsonl")
        stamps.append(pv.load_plan_stamp(records, path=tmp_path))
    assert stamps[0] == stamps[1] == pv.run_stamp_for(verdicts)
    assert stamps[0].startswith(pv.BATCH_STAMP_PREFIX + "-") and stamps[0] != pv.RUN_STAMP


def test_g0b_lives_in_its_own_directory_and_leaves_g0s_files_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    pv.emit([_verdict(1)], [], {1: _state(1)})
    g0 = {name: (tmp_path / name).read_bytes() for name in ("APPLY.sql", "ROLLBACK.sql")}
    verdicts, _ = pv.load_rejected_kinds(_rejected_file(tmp_path, _rejected_record(5)))
    paths = pv.emit(verdicts, [], _g0b_state(verdicts))
    assert Path(paths["apply"]).parent == tmp_path / "rejected_kinds"
    assert {name: (tmp_path / name).read_bytes() for name in g0} == g0


def test_the_g0b_statement_raises_under_its_own_scope_and_writes_its_own_kinds(tmp_path):
    verdicts, _ = pv.load_rejected_kinds(
        _rejected_file(tmp_path, _rejected_record(3), _rejected_record(4, "map_or_document"))
    )
    state = _g0b_state(verdicts)
    stamp = pv.run_stamp_for(verdicts, output=tmp_path)
    sql = pv.render_apply(verdicts, state, run_stamp=stamp)
    assert "RAISE EXCEPTION 'G0b image_kind: % planned row(s) do not exist'" in sql
    assert "'G0 image_kind" not in sql
    assert "WHERE image_kind IN ('artifact', 'map_or_document') AND id IN" in sql
    assert ", NULL, 'artifact', 'g0-vlm-kind:3'" in sql
    rollback = pv.render_rollback(verdicts, state, run_stamp=stamp)
    assert "'G0b rollback: % row(s) are still not NULL'" in rollback
    assert "rollback of G0b: image_kind on 3 returned to NULL (was ''artifact'')" in rollback
    literal = re.search(r"'(\[\{\"source\": \"shorts selection.*?)'::jsonb", sql).group(1)
    evidence = json.loads(literal.replace("''", "'"))
    assert evidence[0]["quote"] == "rejected[] entry filename='Stele_3.webp' reason='kind=artifact'"
    assert evidence[1]["sha256"] == pv.record_sha256(_rejected_record(3))


def test_a_batch_that_mixes_the_two_sources_is_refused(tmp_path):
    verdicts, _ = pv.load_rejected_kinds(_rejected_file(tmp_path, _rejected_record(3)))
    state = {**_g0b_state(verdicts), 1: _state(1)}
    with pytest.raises(pv.PersistError, match="mixes the sources"):
        pv.render_apply([_verdict(1), *verdicts], state)


def test_the_g0b_verify_reads_for_its_own_kinds(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    verdicts, _ = pv.load_rejected_kinds(
        _rejected_file(tmp_path, _rejected_record(3), _rejected_record(4, "other"))
    )
    pv.emit(verdicts, [], _g0b_state(verdicts))
    label = "rows with image_kind in (artifact, other) and no journal row for this run"
    assert label == pv.unjournalled_label(("artifact", "other"))
    assert f"SELECT '{label}'" in pv.verify_sql("x", ("artifact", "other"))

    def metrics(unjournalled: int) -> str:
        return (
            "journal rows for this run|2\n"
            f"{label}|{unjournalled}\n"
            "journal rows for this run outside wiki_images.image_kind|0\n"
            "journal rows for this run with no evidence|0\n"
            "rows with a kind outside the vocabulary|0\n"
        )

    monkeypatch.setattr(pv, "read_rows", lambda sql: [{"row_pks": "3,4", "disagreeing": 0}])
    monkeypatch.setattr(pv, "run_psql", lambda sql, **kw: _psql_result(metrics(0)))
    assert pv.command_verify(tmp_path / "rejected_kinds") == pv.EXIT_OK
    monkeypatch.setattr(pv, "run_psql", lambda sql, **kw: _psql_result(metrics(1)))
    assert pv.command_verify(tmp_path / "rejected_kinds") == pv.EXIT_VERIFY_FAILED
    assert f"{label} = 1 (expected 0)" in capsys.readouterr().out


def test_the_cli_routes_rejected_kinds_to_its_own_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    seen: list[object] = []
    monkeypatch.setattr(pv, "command_rehearse", lambda output: seen.append(output) or 0)
    monkeypatch.setattr(pv, "command_plan", lambda source: seen.append(source) or 0)
    assert pv.main(["--rehearse", "--source", "rejected-kinds"]) == 0
    assert pv.main(["--plan", "--source", "rejected-kinds"]) == 0
    assert pv.main(["--rehearse"]) == 0
    assert seen == [tmp_path / "rejected_kinds", "rejected-kinds", tmp_path]


def test_plan_for_rejected_kinds_names_every_refusal_and_writes_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "OUTPUT", tmp_path)
    path = _rejected_file(
        tmp_path,
        _rejected_record(3),
        _rejected_record(4, "other"),
        _rejected_record(5, verdict="AMBIGUOUS"),
    )
    monkeypatch.setattr(pv, "REJECTED_KINDS", path)
    monkeypatch.setattr(
        pv,
        "read_state",
        lambda ids: {
            i: {**_g0b_state(pv.load_rejected_kinds(path)[0])[i]}
            | ({"image_kind": "artifact"} if i == 4 else {})
            for i in ids
        },
    )
    assert pv.command_plan("rejected-kinds") == pv.EXIT_OK
    out = tmp_path / "rejected_kinds"
    records = pv.load_plan_records(out / "PLAN.jsonl")
    assert [(r["image_id"], r["new_value"]) for r in records] == [(3, "artifact")]
    skipped = [json.loads(line) for line in (out / "SKIPPED.jsonl").read_text().splitlines()]
    assert sorted((s["image_id"], s["reason"]) for s in skipped) == [
        (4, "different-verdict-already-recorded"),
        (5, "mapping-not-proven"),
    ]
    assert pv.verify_delivered(out / "APPLY.sql", records) == pv.plan_digest(records)
    assert pv.verify_delivered(out / "ROLLBACK.sql", records, invert=True) == pv.plan_digest(
        records
    )
