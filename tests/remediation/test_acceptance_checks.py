"""Phase 6 acceptance, section 8: the deterministic checks D1-D6 (`acceptance/checks.py`).

D1-D5 run on the frozen values of the 60 drawn sites; D5 and D6 need Postgres (`unaccent`, the scope
residual, the retired ids) and D6 the public `/api/sites/all`. Offline: both production reads are
faked, and the script sent to production is checked to be one read-only transaction. The mutation
cases are `acceptance judge: ...` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from acceptance import checks as C  # noqa: E402
from acceptance import judge as J  # noqa: E402
from mechanical.lane import SCOPE  # noqa: E402
from phase4.model4 import LegacyProvenance, text_sha256  # noqa: E402

from pipeline.lyra.site_key import site_key_sql  # noqa: E402

SAMPLE = REPO / "output" / "remediation" / "acceptance" / "draw-2026-09-25" / "SAMPLE.jsonl"
DESC = "The bridge crosses the river.[1] It is Roman.[2]"
CARD = "The bridge crosses the river."


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def _w_provenance() -> dict[str, Any]:
    """A real lane-W provenance with a card, from the frozen draw, re-pinned to DESC and CARD."""
    for line in SAMPLE.read_text(encoding="utf-8").splitlines():
        prov = json.loads(line)["description_provenance"]
        if prov and prov.get("lane") == "W" and prov.get("card"):
            prov = copy.deepcopy(prov)
            prov["desc_sha256"] = text_sha256(DESC)
            prov["card"]["text_sha256"] = text_sha256(CARD)
            return prov
    raise AssertionError("the frozen draw holds no lane-W site with a card")


def site(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "site_id": _uuid(1),
        "name": "Pont Romà",
        "name_normalized": "pont roma",
        "country": "Spain",
        "civilization": "Spain",
        "period_start": -100,
        "period_name": "500 BC - 1 AD",
        "description": DESC,
        "description_citations": [{"n": 1, "url": "u1"}, {"n": 2, "url": "u2"}],
        "description_provenance": _w_provenance(),
        "card_description": CARD,
    }
    row.update(over)
    return row


# ---------------------------------------------------------------------------------------- D1-D5
def test_d1_every_marker_has_an_entry_and_every_entry_is_cited() -> None:
    assert C.d1(site()) is None
    assert C.d1(site(description="No markers.", description_citations=None)) is None
    assert "[3]" in (C.d1(site(description=DESC + " Also.[3]")) or "")
    assert "never cited" in (C.d1(site(description="Only one.[1]")) or "")
    assert C.d1(site(description_citations=None)) is not None
    assert C.d1(site(description="Grouped.[1, 2]")) is None  # the pipeline's own expander
    assert "not a list" in (C.d1(site(description_citations={"n": 1})) or "")


def test_d2_the_bucket_is_the_start_s_bucket() -> None:
    assert C.d2(site()) is None
    assert "categorize_period" in (C.d2(site(period_name="1 - 500 AD")) or "")
    assert C.d2(site(period_start=-1500, period_name="1500 - 500 BC")) is None
    assert C.d2(site(period_start=None, period_name=None)) is None


def test_d3_the_card_s_civilization_is_the_country() -> None:
    assert C.d3(site()) is None
    assert C.d3(site(civilization="Roman")) is not None


def test_d4_the_provenance_pins_the_served_description_and_card() -> None:
    assert C.d4(site()) is None
    assert "desc_sha256" in (C.d4(site(description=DESC + " ")) or "")
    assert "card" in (C.d4(site(card_description=CARD + "!")) or "")
    assert "card" in (C.d4(site(card_description=None)) or "")
    legacy = LegacyProvenance(desc_sha256=text_sha256(DESC)).to_dict()
    assert C.d4(site(description_provenance=legacy, card_description="anything")) is None
    assert C.d4(site(description_provenance=None)) is None
    broken = dict(legacy, lane="Q")
    assert "does not parse" in (C.d4(site(description_provenance=broken)) or "")


def test_d5_the_stored_key_is_postgres_s_own() -> None:
    assert C.d5(site(), "pont roma") is None
    assert C.d5(site(), "pont romà") is not None


def test_d6_no_undecided_site_outside_e3_and_no_retired_site_served() -> None:
    assert C.d6(0, {}, set()) == []
    assert C.d6(0, {_uuid(5): "ancient_nerds"}, {_uuid(1)}) == []
    assert len(C.d6(2, {}, set())) == 1
    (failure,) = C.d6(0, {_uuid(5): "ancient_nerds"}, {_uuid(5), _uuid(1)})
    assert _uuid(5) in failure


# ------------------------------------------------------------------------------ the production read
def test_the_production_read_is_one_read_only_transaction_of_selects() -> None:
    script = C.export_script([site(), site(site_id=_uuid(2), name="O'Brien's Fort")])
    assert script.startswith("\\set QUIET on\nBEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n")
    assert script.rstrip().endswith("COMMIT;")
    body = script.split("READ ONLY;\n", 1)[1].rsplit("COMMIT;", 1)[0]
    for statement in filter(None, (s.strip() for s in body.split(";\n"))):
        assert statement.startswith("SELECT "), statement
    for word in ("INSERT", "UPDATE", "DELETE", "apply_remediation_change", "TRUNCATE"):
        assert word not in script
    assert site_key_sql("v.name") in script
    assert "'O''Brien''s Fort'" in script
    assert SCOPE.post_commit_residual.predicate in script
    assert "scope_status = 'retired'" in script


def _export(keys: dict[str, str], outside: int, retired: list[tuple[str, str]]) -> str:
    lines = [{"kind": "name_key", "row": {"site_id": k, "sql_key": v}} for k, v in keys.items()]
    lines.append({"kind": "outside_window", "row": {"n": outside}})
    lines += [{"kind": "retired", "row": {"site_id": i, "source_id": s}} for i, s in retired]
    lines.append({"kind": "snapshot", "row": {"exported_at": "2026-09-26 10:00:00+00"}})
    return "".join(json.dumps(line) + "\n" for line in lines)


def _run(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    run = tmp_path / "draw-x"
    run.mkdir()
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    (run / "SAMPLE.jsonl").write_text(text, encoding="utf-8", newline="\n")
    pins = {"SAMPLE.jsonl": hashlib.sha256(text.encode()).hexdigest()}
    (run / "DRAW.json").write_text(json.dumps({"sha256": pins}), encoding="utf-8")
    return run


def test_deterministic_writes_every_check_once(tmp_path: Path) -> None:
    rows = [site(), site(site_id=_uuid(2), period_name="1 - 500 AD")]
    run = _run(tmp_path, rows)
    sources: list[set[str]] = []

    def served(wanted: set[str]) -> tuple[set[str], dict[str, Any]]:
        sources.append(wanted)
        return {_uuid(1), _uuid(2)}, {"sites_served": 2}

    result = J.deterministic(
        run,
        read_export=lambda script: _export({_uuid(1): "pont roma", _uuid(2): "pont roma"}, 0,
                                           [(_uuid(9), "ancient_nerds")]),
        read_served=served,
    )  # fmt: skip
    assert sources == [{"ancient_nerds"}]
    assert result["D2"]["holds"] is False and result["D2"]["failures"][0]["site_id"] == _uuid(2)
    for check in ("D1", "D3", "D4", "D5", "D6"):
        assert result[check]["holds"] is True, check
    assert result["all_hold"] is False
    stored = json.loads((run / "DETERMINISTIC.json").read_text(encoding="utf-8"))
    assert stored == result
    assert (run / "DETERMINISTIC_EXPORT.jsonl").exists()
    with pytest.raises(J.JudgeError, match="once"):
        J.deterministic(run, read_export=lambda s: "", read_served=served)


def test_a_key_postgres_did_not_return_refuses(tmp_path: Path) -> None:
    run = _run(tmp_path, [site()])
    with pytest.raises(J.JudgeError, match="name_key"):
        J.deterministic(
            run,
            read_export=lambda script: _export({}, 0, []),
            read_served=lambda wanted: (set(), {}),
        )
