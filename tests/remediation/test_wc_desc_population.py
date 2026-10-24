"""The description lane's populations after the losses of 2026-10-24 (`wc/cli.py`):

* `minimax-sites --closed`: the texts of a closed batch whose run is lost (`p4wc-4325`, the WN
  pilot) are named for the D10 re-check from its versioned record;
* `defect-population`: the description-defect population as it stands - every standing defect line
  against the current text hashes, the sites an earlier repair run asks, the sites whose lines are
  lost (`wb-cardgap-2026-10-07`) - and the list of the new sites, in `defect-sites`' shape.

No socket, no model, no database.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from wc import cli as C  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.test_wc_list import (  # noqa: E402
    SITE_ALL,
    SITE_NONE,
    SITE_P4,
    SITE_RET,
    _defect,
    _p4_rows,
)
from tests.remediation.test_wc_repairs import _fresh_rows, _read, _restamp  # noqa: E402
from tests.remediation.wc_fixtures import wiki_cache  # noqa: E402,F401 - the autouse fixture

RECORDS = REPO / "output" / "remediation" / "final-2026-10-08" / "reconstructed"
LOST_SITE = "31000000-0000-4000-8000-000000000031"


# ------------------------------------------------------------------------------ minimax-sites
def _closed_record(path: Path, site_id: str, run: str, *, minimax: bool = True) -> Path:
    path.write_text(
        json.dumps(
            {
                "kind": C.CLOSED_BATCH_KIND,
                "reconstructed": True,
                "batch_id": "p4wc-4325",
                "site_list": [{"site_id": site_id, "run": run, "minimax": minimax}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_texts_of_a_closed_batch_whose_run_is_lost_are_on_the_d10_list(tmp_path: Path) -> None:
    """The WN pilot's run is gone (its handoffs too): its texts are named from the closed batch's
    record, under the rule every source run follows - the live text still the one the run wrote."""
    wn_root = tmp_path / "wn"
    wn_run, wn_plan = WX.build_wn_run(
        wn_root, [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)}, pilot=False
    )
    run = _read(tmp_path, _fresh_rows(wn_plan, [WX.wn_row(WX.SITE_N)]))
    shutil.rmtree(wn_root)  # lost with its worktree
    record = _closed_record(tmp_path / "p4wc-4325.closed.json", WX.SITE_N, wn_run.name)
    out = tmp_path / "minimax.txt"
    report = C.cmd_minimax_sites(run, [], out, closed=[record])
    assert out.read_text(encoding="utf-8").split() == [WX.SITE_N]
    assert report["touched"] == 1 and report["closed"][0]["path"].endswith("p4wc-4325.closed.json")
    other = _closed_record(tmp_path / "other.json", WX.SITE_N, "another-run")
    assert C.cmd_minimax_sites(run, [], tmp_path / "o.txt", closed=[other])["others"] == {
        "rewritten-since": [WX.SITE_N]
    }
    claude = _closed_record(tmp_path / "claude.json", WX.SITE_N, wn_run.name, minimax=False)
    assert C.cmd_minimax_sites(run, [], tmp_path / "c.txt", closed=[claude])["touched"] == 0
    (tmp_path / "bad.json").write_text(json.dumps({"kind": "x"}), encoding="utf-8")
    with pytest.raises(C.WcRunError, match="not the record of a closed WC batch"):
        C.cmd_minimax_sites(run, [], tmp_path / "b.txt", closed=[tmp_path / "bad.json"])


def test_closed_and_source_runs_add_up_and_the_cli_takes_closed(tmp_path: Path) -> None:
    wc_root = tmp_path / "wc"
    from tests.remediation.test_wc_verify import _answers, _rows

    wc_run, wc_plan = FX.build_run(wc_root, _rows(), _answers(), pilot=False, name="wc-02")
    assert _restamp(wc_root / "handoff" / "wc-02-verify") == 2
    wn_root = tmp_path / "wn"
    wn_run, wn_plan = WX.build_wn_run(
        wn_root, [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)}, pilot=False
    )
    fresh = _fresh_rows(wc_plan, _rows()) + _fresh_rows(wn_plan, [WX.wn_row(WX.SITE_N)])
    run = _read(tmp_path, fresh)
    record = _closed_record(tmp_path / "p4wc-4325.closed.json", WX.SITE_N, wn_run.name)
    out = tmp_path / "m.txt"
    code = C.main(
        ["minimax-sites", "--run-dir", str(run), "--from", str(wc_run), "--closed", str(record),
         "--out", str(out)]
    )  # fmt: skip
    assert code == 0
    assert out.read_text(encoding="utf-8").split() == sorted([FX.SITE_A, FX.SITE_B, WX.SITE_N])


def test_the_real_record_of_p4wc_4325_names_the_17_wn_texts() -> None:
    names = C.closed_minimax_sites(RECORDS / "p4wc-4325.closed.json")
    assert len(names) == 17 and set(names.values()) == {"wn-2026-10-06"}


# ------------------------------------------------------------------------------ defect-population
def _lost_record(path: Path, sites: list[tuple[str, str]]) -> Path:
    record = json.loads(
        (RECORDS / "wb-cardgap-2026-10-07.DESCRIPTION_DEFECTS.lost.json").read_text(
            encoding="utf-8"
        )
    )
    record["sites"] = [
        {"site_id": site_id, "name": name, "identified_by": "a test"} for site_id, name in sites
    ]
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_the_defect_population_is_every_standing_line_the_asked_the_new_and_the_lost(
    tmp_path: Path,
) -> None:
    """Three sites carry standing defect lines; an earlier repair run asks two of them; a lost
    record names a fourth (its lines gone); one line is on a text that changed and one on a retired
    site. The population is four: two asked, one new, one lost; the list is the new one, with its
    claims in `defect-sites`' shape, and drives `export --sites --defects` directly."""
    sha = M.text_sha256(WX.P4_TEXT)
    run = _read(tmp_path, _p4_rows())
    defects = tmp_path / "wb-ws" / "DESCRIPTION_DEFECTS.jsonl"
    defects.parent.mkdir()
    lines = [
        _defect(SITE_P4, sha),
        _defect(SITE_ALL, sha, sentence=None, sentence_text=None, claim="They are not Maltese"),
        _defect(SITE_NONE, sha, sentence=1, sentence_text=WX.P4_SENTENCES[0], claim="Not here"),
        _defect(SITE_P4, "c" * 64, claim="on an older text"),
        _defect(SITE_RET, sha),
    ]
    defects.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    earlier = tmp_path / "runs" / "defects-earlier"
    earlier.mkdir(parents=True)
    (earlier / C.SITES_FILE).write_text(
        "".join(json.dumps({"site_id": s}) + "\n" for s in (SITE_P4, SITE_ALL)), encoding="utf-8"
    )
    lost = _lost_record(tmp_path / "lost.json", [(LOST_SITE, "A lost site")])
    out = tmp_path / "DEFECT_SITES.txt"
    report = C.cmd_defect_population(run, [defects], out, asked=[earlier], lost=[lost])
    assert report["population"] == 4
    assert report["counts"] == {"asked": 2, "lost": 1, "new": 1}
    assert report["asked_by_run"] == {"defects-earlier": 2}
    assert report["skipped"] == {"retired": 1, "text-changed-since": 1}
    assert out.read_text(encoding="utf-8").split() == [SITE_NONE]
    population = json.loads(
        out.with_name(out.name + C.POPULATION_SUFFIX).read_text(encoding="utf-8")
    )
    assert population["sites"][LOST_SITE] == {
        "name": "A lost site", "state": "lost", "claims": 0, "in_read": False, "retired": False,
        "record": population["lost_records"][0]["path"],
    }  # fmt: skip
    assert population["sites"][SITE_P4]["state"] == "asked:defects-earlier"
    assert population["sites"][SITE_P4]["claims"] == 1
    C.cmd_export(
        run, tmp_path / "h", batch_size=5, exclude=None, after=[], pilot=None, seed=None,
        sites=out, defects=out.with_name(out.name + ".report.json"),
    )  # fmt: skip
    (asked,) = read_jsonl(run / C.SITES_FILE)
    assert asked["site_id"] == SITE_NONE and asked["defects"][0]["claim"] == "Not here"


def test_a_lost_record_that_is_not_one_stops_the_population(tmp_path: Path) -> None:
    run = _read(tmp_path, _p4_rows())
    defects = tmp_path / "d.jsonl"
    defects.write_text("", encoding="utf-8")
    broken = _lost_record(tmp_path / "lost.json", [("not-a-uuid", "x")])
    with pytest.raises(C.WcRunError):
        C.cmd_defect_population(run, [defects], tmp_path / "o.txt", lost=[broken])
    record = json.loads(broken.read_text(encoding="utf-8"))
    record["rebuilt"] = True
    broken.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(C.WcRunError, match="rebuilt nothing"):
        C.cmd_defect_population(run, [defects], tmp_path / "o.txt", lost=[broken])


def test_the_real_lost_record_of_the_cardgap_run_names_its_five_sites() -> None:
    record = C.read_lost_defects(RECORDS / "wb-cardgap-2026-10-07.DESCRIPTION_DEFECTS.lost.json")
    assert (record["run"], record["lines"], record["rebuilt"]) == (
        "wb-cardgap-2026-10-07", 9, False
    )  # fmt: skip
    assert [s["name"] for s in record["sites"]] == [
        "Wamanmarka, Chumbivilcas", "Tanqa Tanqa", "Lakhan-Jo-Daro", "Wain's Hill",
        "Cave of Niaux",
    ]  # fmt: skip


def test_the_cli_builds_the_population(tmp_path: Path) -> None:
    sha = M.text_sha256(WX.P4_TEXT)
    run = _read(tmp_path, _p4_rows())
    defects = tmp_path / "d.jsonl"
    defects.write_text(json.dumps(_defect(SITE_P4, sha)) + "\n", encoding="utf-8")
    out = tmp_path / "list.txt"
    assert C.main(
        ["defect-population", "--run-dir", str(run), "--defects", str(defects), "--out", str(out)]
    ) == 0  # fmt: skip
    assert out.read_text(encoding="utf-8").split() == [SITE_P4]
