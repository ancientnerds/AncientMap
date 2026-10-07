"""`scripts/paper24.py` drives the owner's 24 paper topics through the studio.

Pinned here, because the driver's value is that it is unattended: a session must be
able to run a step without knowing the state of the others. Three things would
break that quietly, and none of them would raise.

1. `scan` has to work with an empty campaign (no dossier, no workspace, no report)
   and still answer. It is the step a human runs to find out what to do next.
2. The iteration counter is the workspace's own check history, not a counter the
   driver keeps in its state file: a state file that is lost, shared or written by a
   foreign id must not restart a paper's count.
3. The read-only boundary is a claim this module makes in prose. It is checked here
   by reading the module: `publish` must not appear in it at all.
4. The ledger refuses to write a table whose campaign numbers collide, because a kept
   row that collides is a lost topic, not a foreign campaign.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from tests.pipeline.studio import fixtures as fx

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "paper24.py"


def _load():
    spec = importlib.util.spec_from_file_location("paper24", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dossier_list(*rows: dict) -> bytes:
    return json.dumps(list(rows)).encode("utf-8")


def test_scan_answers_with_an_empty_campaign(monkeypatch, tmp_path, capsys):
    driver = _load()
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(driver.remote, "check_module", lambda *a, **k: _dossier_list())
    monkeypatch.setattr(driver.mcode, "weekly_remaining_percent", lambda: 71.0)
    monkeypatch.setattr(driver.mcode, "weekly_stop", lambda: False)
    monkeypatch.setattr(driver.mcode, "tree_state", lambda repo: "clean")
    assert driver.main(["scan"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dossiers_on_record"] == 0
    assert out["ready_to_pull"] == [] and out["already_pulled"] == [] and out["bundled"] == []
    assert out["mcode"]["weekly_stopped"] is False


def test_scan_sorts_dossiers_that_have_not_been_taken_yet(monkeypatch, tmp_path, capsys):
    driver = _load()
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(
        driver.remote,
        "check_module",
        lambda *a, **k: _dossier_list(
            {"request_id": "cccccccc-0000-0000-0000-000000000001", "status": "researched"},
            {"request_id": "aaaaaaaa-0000-0000-0000-000000000001", "status": "researched"},
        ),
    )
    monkeypatch.setattr(driver.mcode, "weekly_remaining_percent", lambda: 71.0)
    monkeypatch.setattr(driver.mcode, "weekly_stop", lambda: False)
    monkeypatch.setattr(driver.mcode, "tree_state", lambda repo: "clean")
    assert driver.main(["scan"]) == 0
    ready = json.loads(capsys.readouterr().out)["ready_to_pull"]
    assert [r["request_id"] for r in ready] == sorted(r["request_id"] for r in ready)


def test_the_iteration_count_outlives_any_rewrite_of_the_driver_state(
    monkeypatch, tmp_path, capsys
):
    """The count is the campaign's own limit ("at most two iterations per paper"), so
    it is read from the workspace, not from the state file. Two gate runs, then the
    state file is rewritten by something else: the ledger still says 2."""
    driver = _load()
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(driver, "LEDGER", tmp_path / "ledger.md")
    ws = driver._ws("bbbbbbbb-0000-0000-0000-000000000001")
    ws.root.mkdir(parents=True)
    ws.dossier_gz.write_bytes(fx.dossier_gz_bytes())
    failed = {
        "passed": False,
        "gates": [
            {
                "name": "support",
                "passed": False,
                "detail": {
                    "issues": [
                        {"rule": "located_sentence"},
                        {"rule": "located_sentence"},
                        {"rule": "number_exact"},
                    ]
                },
            }
        ],
    }
    green = {"passed": True, "gates": []}
    ws.check_report.write_text(json.dumps(failed), encoding="utf-8")
    assert driver._record_check(ws, failed) == 1
    ws.check_report.write_text(json.dumps(green), encoding="utf-8")
    assert driver._record_check(ws, green) == 2
    # another writer owns the state file and knows nothing about the count
    driver._save({"pulled": [ws.request_id], "bundled": []})
    assert driver.main(["ledger"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 1
    table = (tmp_path / "ledger.md").read_text(encoding="utf-8")
    cells = [cell.strip() for cell in table.splitlines()[2].split("|")]
    assert cells[1] == "1", cells  # the campaign number
    assert cells[2] == f"`{ws.request_id}`", cells
    assert cells[4] == "2", cells  # iterations
    assert cells[5] == "yes", cells  # green
    assert cells[6] == "-", cells  # rote Gates
    assert cells[7] == "0", cells  # support findings: the report on disk is green
    assert cells[8] == "no", cells  # bundle
    # the topic cell is the dossier's question, on one line and without a pipe
    assert "How were the Baalbek megaliths moved?" in table


def test_the_ledger_replaces_a_row_instead_of_appending_a_second(monkeypatch, tmp_path):
    driver = _load()
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(driver, "LEDGER", tmp_path / "ledger.md")
    ws = driver._ws("bbbbbbbb-0000-0000-0000-000000000001")
    ws.root.mkdir(parents=True)
    ws.dossier_gz.write_bytes(fx.dossier_gz_bytes())
    ws.check_report.write_text(json.dumps({"passed": True, "gates": []}), encoding="utf-8")
    driver._save({"pulled": [ws.request_id], "bundled": []})
    assert driver.main(["ledger"]) == 0
    assert driver.main(["ledger"]) == 0
    table = (tmp_path / "ledger.md").read_text(encoding="utf-8")
    # header + separator + exactly one data row, no matter how often it is rewritten
    assert table.count(ws.request_id) == 1
    assert len(table.strip().splitlines()) == 3


def test_the_ledger_refuses_a_list_that_lost_a_topic(monkeypatch, tmp_path, capsys):
    """A kept row whose campaign number the rewritten rows also claim is a lost topic,
    not a foreign campaign. Writing the table would renumber the campaign silently, so
    the command stops and says which number and which id collide."""
    driver = _load()
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ledger = tmp_path / "ledger.md"
    monkeypatch.setattr(driver, "LEDGER", ledger)
    lost = "cccccccc-0000-0000-0000-000000000001"
    ledger.write_text(
        driver.LEDGER_HEADER
        + f"| 1 | `{lost}` | A topic the driver lost | 1 | yes | - | 0 | yes | |\n",
        encoding="utf-8",
    )
    ws = driver._ws("bbbbbbbb-0000-0000-0000-000000000001")
    ws.root.mkdir(parents=True)
    ws.dossier_gz.write_bytes(fx.dossier_gz_bytes())
    ws.check_report.write_text(json.dumps({"passed": True, "gates": []}), encoding="utf-8")
    driver._save({"pulled": [ws.request_id], "bundled": []})
    before = ledger.read_text(encoding="utf-8")
    assert driver.main(["ledger"]) == 2
    err = capsys.readouterr().err
    assert "claimed twice" in err and lost in err
    assert ledger.read_text(encoding="utf-8") == before, "the table must not be written"


def test_the_ledger_says_a_missing_history_is_not_zero_iterations(monkeypatch, tmp_path, capsys):
    """A workspace with no `checks.jsonl` had its gates run by another writer.

    Six of the ten published papers were checked through the studio CLI rather than
    through this driver, so they carry no history file. Counting that as `0` put
    papers that went through many cycles into the ledger as ones that went through
    none, and read as the campaign limit of two being met. The cell says the count is
    unknown, and the command names the ids it could not measure.
    """
    driver = _load()
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr(driver, "LEDGER", tmp_path / "ledger.md")
    ws = driver._ws("bbbbbbbb-0000-0000-0000-000000000009")
    ws.root.mkdir(parents=True)
    ws.dossier_gz.write_bytes(fx.dossier_gz_bytes())
    ws.check_report.write_text(json.dumps({"passed": True, "gates": []}), encoding="utf-8")
    ws.bundle.write_text("{}", encoding="utf-8")
    assert not ws.checks.exists()
    driver._save({"pulled": [ws.request_id], "bundled": []})

    assert driver._iterations(ws) is None
    assert driver._iterations_cell(ws) == "nicht gemessen"

    assert driver.main(["ledger"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["iterations_not_measured"] == 1, out
    assert out["iterations_not_measured_ids"] == [ws.request_id], out

    table = (tmp_path / "ledger.md").read_text(encoding="utf-8")
    cells = [cell.strip() for cell in table.splitlines()[2].split("|")]
    assert cells[4] == "nicht gemessen", cells
    assert cells[4] != "0", cells
    # the paper is still recorded as what it is: green and bundled
    assert cells[5] == "yes", cells
    assert cells[8] == "yes", cells


def test_the_driver_cannot_reach_a_publish_call():
    """The campaign stops at `bundle`. A publish call in here would be the one write
    the owner ruled out, and it would read as a mechanical step. The check is on the
    call, not the word: `finish` reports `"published": False`, which is the point."""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "publish.publish" not in text
    assert "theo_publish" not in text
    # `publish` must not even be imported from the studio: an unused import is the
    # step waiting to be written.
    for line in text.splitlines():
        if line.startswith(("import ", "from ")) and "publish" in line:
            raise AssertionError(f"the driver imports a publisher: {line}")


def test_every_step_is_registered():
    driver = _load()
    parser = argparse_parser(driver)
    action = parser._subparsers._group_actions[0]  # noqa: SLF001
    assert set(action.choices) == {
        "scan",
        "pull",
        "draft",
        "check",
        "claims",
        "images",
        "finish",
        "ledger",
    }


def argparse_parser(driver):
    import argparse

    parser = argparse.ArgumentParser(prog="paper24")
    driver.register(parser.add_subparsers(dest="command", required=True))
    return parser
