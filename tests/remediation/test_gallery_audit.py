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
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "remediation" / "gallery_audit" / "persist_verdicts.py"


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


def test_load_verdicts_on_the_real_input_finds_105_rows():
    """The measured shape of the artifact, pinned. If the pipeline adds verdicts this changes."""
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
    assert "w.image_kind IS DISTINCT FROM p.old_value" in sql
    assert "IS NOT DISTINCT FROM" in sql
    # The file *explains* why `= NULL` is wrong, so the check must ignore comments - otherwise it
    # fires on its own documentation and proves nothing about the SQL.
    code = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    offenders = [line for line in code if "image_kind = NULL" in line]
    assert offenders == [], offenders


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
    assert "do not hold the value being rolled back" in sql


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
    """The rehearsal must run the real file, not a hand-written approximation of it."""
    apply_sql = "BEGIN;\nSELECT 1;\nCOMMIT;\n"
    rehearsal = apply_sql.rstrip()[: -len("COMMIT;")] + "ROLLBACK;\n"
    assert rehearsal == "BEGIN;\nSELECT 1;\nROLLBACK;\n"
    assert rehearsal.count("ROLLBACK;") == 1


def test_rehearsal_refuses_a_file_that_does_not_end_in_one_commit():
    for bad in ("BEGIN;\nCOMMIT;\nCOMMIT;\n", "BEGIN;\nSELECT 1;\n"):
        assert bad.count("COMMIT;") != 1 or not bad.rstrip().endswith("COMMIT;")


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
