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
    payload = S.scope_payload(_rows(), _cleared(), inputs=INPUTS, version=1)
    assert payload["lists"] == {S.CLEARED_DESCRIPTION: 2, S.CLEARED_CARD: 2, S.UNGROUNDED_CARD: 1}
    assert payload["sites"] == [
        {"site_id": uuid(1), "lists": [S.CLEARED_DESCRIPTION]},
        {"site_id": uuid(2), "lists": [S.CLEARED_CARD]},
        {"site_id": uuid(3), "lists": [S.CLEARED_DESCRIPTION, S.CLEARED_CARD]},
        {"site_id": uuid(4), "lists": [S.UNGROUNDED_CARD]},
    ]
    assert payload["unclaimed"] == {S.UNGROUNDED_CARD: {S.NOT_IN_SNAPSHOT: [uuid(6)]}}
    assert payload["inputs"] == INPUTS and payload["version"] == 1
    assert payload["sites_sha256"] == S.sites_digest(payload["sites"])


def test_a_cleared_defect_of_a_site_that_is_no_curated_row_stops_the_scope() -> None:
    with pytest.raises(S.ScopeError, match="not curated rows"):
        S.scope_payload(_rows(), {uuid(9): {"description"}}, inputs=INPUTS, version=1)


def test_a_cleared_defect_of_another_field_stops_the_scope() -> None:
    with pytest.raises(S.ScopeError, match="country"):
        S.scope_payload(_rows(), {uuid(1): {"country"}}, inputs=INPUTS, version=1)


def test_the_scope_file_round_trips_and_is_byte_identical_across_builds() -> None:
    first = S.render_scope(S.scope_payload(_rows(), _cleared(), inputs=INPUTS, version=1))
    second = S.render_scope(
        S.scope_payload(list(reversed(_rows())), _cleared(), inputs=INPUTS, version=1)
    )
    assert first == second and first.endswith(b"\n")
    scope = S.parse_scope(first)
    assert scope.sha256 == hashlib.sha256(first).hexdigest()
    assert uuid(3) in scope and uuid(5) not in scope and uuid(6) not in scope
    assert scope.sites[uuid(3)] == (S.CLEARED_DESCRIPTION, S.CLEARED_CARD)
    assert scope.label == f"SCOPE4.json v1 {scope.sha256[:16]}"


def _payload() -> dict[str, Any]:
    return S.scope_payload(_rows(), _cleared(), inputs=INPUTS, version=1)


def _resealed(payload: dict[str, Any]) -> bytes:
    payload["sites_sha256"] = S.sites_digest(payload["sites"])
    return S.render_scope(payload)


@pytest.mark.parametrize(
    ("tamper", "match"),
    [
        (lambda p: p.update(version=4), "version"),
        (lambda p: p.pop("unclaimed"), "keys"),
        (lambda p: p["sites"].reverse(), "sorted"),
        (lambda p: p["sites"].append(dict(p["sites"][-1])), "sorted"),
        (lambda p: p["sites"][0].update(site_id="Tarxien Temples"), "not a site id"),
        (lambda p: p["sites"][0].update(lists=[]), "no list"),
        (lambda p: p["sites"][0].update(lists=["t03-severe"]), "not a list"),
        (lambda p: p["sites"][2].update(lists=[S.CLEARED_CARD, S.CLEARED_DESCRIPTION]), "order"),
        (lambda p: p["sites"][0].update(note="x"), "keys"),
        (lambda p: p["lists"].update({S.UNGROUNDED_CARD: 2}), "counts"),
        (
            lambda p: p["sites"][0].update(
                lists=[S.CLEARED_DESCRIPTION, S.D1_MARKER_WITHOUT_ENTRY]
            ),
            "version 1 carries no list",
        ),
        (lambda p: p["lists"].update({S.D1_MARKER_WITHOUT_ENTRY: 0}), "counts"),
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
        "a-later-versions-list",
        "a-later-versions-count",
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


def _pinned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data: bytes, *, version: int = S.SCOPE_VERSION
) -> Path:
    """`data` put in place of the pinned file of `version` (the current one, or an earlier one)."""
    names = {
        1: ("SCOPE_V1_FILE", "SCOPE_V1_SHA256"),
        2: ("SCOPE_V2_FILE", "SCOPE_V2_SHA256"),
        S.SCOPE_VERSION: ("SCOPE_FILE", "SCOPE_SHA256"),
    }
    file_name, pin_name = names[version]
    path = tmp_path / f"SCOPE4.v{version}.json"
    path.write_bytes(data)
    monkeypatch.setattr(S, file_name, path)
    monkeypatch.setattr(S, pin_name, hashlib.sha256(data).hexdigest())
    return path


def test_the_scope_is_read_only_from_the_pinned_file(monkeypatch, tmp_path: Path) -> None:
    """A new scope is a new version and a new pin in code, never an edit of the file."""
    data = S.render_scope(_v3_payload())
    path = _pinned(monkeypatch, tmp_path, data)
    assert set(S.load_scope().sites) == {uuid(1), uuid(2), uuid(3), uuid(4)}
    path.write_bytes(data.replace(b'"version": 3', b'"version":  3'))
    with pytest.raises(S.ScopeError, match="is not the pinned scope"):
        S.load_scope()


def test_each_version_is_read_from_its_own_pinned_file_and_is_that_version(
    monkeypatch, tmp_path: Path
) -> None:
    """Versions 1 and 2 stay readable at their own pins (the mass run's plan is rebuilt from version
    1, version 3 is checked against version 2); the writers read the current version. A file of one
    version at another's pin is refused, as is a version no file is pinned for."""
    one = S.render_scope(_payload())
    two = S.render_scope(S.scope_payload(_rows(), _cleared(), inputs=INPUTS, version=2))
    three = S.render_scope(_v3_payload())
    _pinned(monkeypatch, tmp_path, one, version=1)
    _pinned(monkeypatch, tmp_path, two, version=2)
    _pinned(monkeypatch, tmp_path, three)
    assert (S.load_scope(1).version, S.load_scope(2).version, S.load_scope().version) == (1, 2, 3)
    assert S.load_scope(1).label == f"SCOPE4.v1.json v1 {hashlib.sha256(one).hexdigest()[:16]}"
    assert S.load_scope(2).label == f"SCOPE4.v2.json v2 {hashlib.sha256(two).hexdigest()[:16]}"
    assert S.load_scope().label == f"SCOPE4.v3.json v3 {hashlib.sha256(three).hexdigest()[:16]}"
    swapped = tmp_path / "swapped"
    swapped.mkdir()
    _pinned(monkeypatch, swapped, two)  # version 2's bytes at the current version's pin
    with pytest.raises(S.ScopeError, match="pinned as version 3"):
        S.load_scope()
    _pinned(monkeypatch, swapped, three, version=2)  # version 3's bytes at version 2's pin
    with pytest.raises(S.ScopeError, match="pinned as version 2"):
        S.load_scope(2)
    with pytest.raises(S.ScopeError, match="no pinned scope of version 4"):
        S.load_scope(4)


# ===================================================================== the committed artefact

#: The orphan-citations lane's listing (`mechanical_citations/SKIPPED.jsonl`, HUMAN_ONLY D9): the
#: nine curated sites whose description sets a [N] marker without an entry, 2026-09-25.
D9_SITES = frozenset(
    {
        "1c899f53-4414-4954-821d-9119802aa39a",  # Laüs
        "1f66729b-c7e8-476a-b9cc-84b23a36074f",  # Porth Hellick Down
        "867f08af-8934-4ec0-bbcc-2c730bb2a93a",  # Killa Mach'ay, in version 1 already
        "89f1d2b7-2579-4c33-82b3-8b58d7857c53",  # Acci
        "a9c5d1bf-b6d0-4486-a507-8dddfdc57a02",  # Ağbulaq Necropolis
        "bf538bd9-912c-471a-964a-f94842e17491",  # Temple of Zeus (Kyrene)
        "c0e10d6e-fb0e-4e9c-a910-631da9e578ea",  # Afrodit Tapınağı
        "fb9e7ccb-2ffd-4bb8-a78d-1e2993881090",  # Absalom's Tomb
        "fe4edbed-be84-4b80-b5de-62ab3e4c88ef",  # A Figa
    }
)
KILLA_MACHAY = "867f08af-8934-4ec0-bbcc-2c730bb2a93a"
D1 = S.D1_MARKER_WITHOUT_ENTRY


def test_the_committed_version_2_is_pinned_with_the_recorded_counts() -> None:
    """`SCOPE4.v2.json`, version 2 (owner order 2026-09-25, HUMAN_ONLY D9 (c)): version 1's 322 + 709
    cleared defects and 876 ungrounded cards, and the 9 sites whose description sets a marker
    without an entry - 1,631 sites, Killa Mach'ay (a cleared card) in two lists. Plan section 5.1's
    three named examples are ungrounded, Baalshamin is not claimed."""
    scope = S.load_scope(2)
    payload = json.loads(S.SCOPE_V2_FILE.read_text(encoding="utf-8"))
    assert (scope.version, S.SCOPE_V2_FILE.name) == (2, "SCOPE4.v2.json")
    assert scope.sha256 == "7256a1962ffe1b2449c7028e1174fe623d7de19fdddde2083f560790f7003173"
    assert payload["lists"] == {
        S.CLEARED_DESCRIPTION: 322,
        S.CLEARED_CARD: 709,
        S.UNGROUNDED_CARD: 876,
        D1: 9,
    }
    assert len(scope.sites) == 1631
    assert payload["inputs"] == {
        "S0_ROWS.jsonl": "2c99f96f899447000659ad3ff6b24bc2dc9eddd2f96cdfe73afeabb1829272a8",
        "ALL_REFUSED.jsonl": "7b4026d0e39d6c0c1355442a65cea9a5bae9b8762897b1685a8f44b1d6cd75f9",
        "SKIPPED.jsonl": "28dadb0b09a9c0e4173cc07590b328e9ad3bbb113977d529dd021b07c640f192",
    }
    assert {site for site, lists in scope.sites.items() if D1 in lists} == D9_SITES
    assert scope.sites[KILLA_MACHAY] == (S.CLEARED_CARD, D1)
    for prefix in ("45ac8925", "2968fd35", "3dd6b568"):  # House of Taga, Hatunmarka, Maray Qalla
        (site,) = [s for s in scope.sites if s.startswith(prefix)]
        assert S.UNGROUNDED_CARD in scope.sites[site]
    assert payload["unclaimed"] == {
        S.UNGROUNDED_CARD: {S.NOT_IN_SNAPSHOT: ["95b33efa-d5eb-4cb8-ab61-746b3822762a"]}
    }
    assert payload["decision"] == f"{S.DECISION} {S.ORDER_2026_09_25}"


def test_version_1_is_kept_at_its_pin_and_version_2_refuses_nothing_it_allowed() -> None:
    """`SCOPE4.json` v1 (2026-09-23/24, the mass run's): file and pin unchanged. Every version-1 site
    is a version-2 site whose lists begin with its version-1 lists, so the gate refuses nothing
    version 1 allowed; version 2 adds the 8 listed sites version 1 did not hold, each in the new
    list alone."""
    one, two = S.load_scope(1), S.load_scope(2)
    assert (one.version, S.SCOPE_V1_FILE.name, len(one.sites)) == (1, "SCOPE4.json", 1623)
    assert one.sha256 == "19a57e9fd17f53601fecdd5424d3ea3e085c2690e8250cb72b004f010f833d6a"
    for site_id, lists in one.sites.items():
        assert two.sites[site_id][: len(lists)] == lists
    added = set(two.sites) - set(one.sites)
    assert added == D9_SITES - {KILLA_MACHAY}
    assert {two.sites[site_id] for site_id in added} == {(D1,)}


def test_the_audit_log_records_the_pinned_scope() -> None:
    """Every pin: version 1's, which the mass run was planned and written under, version 2's (the
    D9 run's) and the current."""
    log = (MAIN_OUTPUT / "AUDIT_LOG.md").read_text(encoding="utf-8")
    for pin in (S.SCOPE_V1_SHA256, S.SCOPE_V2_SHA256, S.SCOPE_SHA256):
        assert f"`{pin}`" in log


needs_inputs = pytest.mark.skipif(
    not (RUNNER / "S0_ROWS.jsonl").exists()
    or not (MAIN_OUTPUT / "logs" / "_write_dry" / "ALL_REFUSED.jsonl").exists(),
    reason="the gitignored S0 export or Phase 3's refusals are not in this checkout",
)


@needs_inputs
def test_the_committed_scope_is_rebuilt_byte_for_byte_from_its_inputs(tmp_path: Path) -> None:
    """Every version from its inputs: version 1 from the S0 rows and Phase 3's refusals, version 2
    from those and the orphan-citations lane's committed listing, the current one from those and the
    committed March read (both the defaults)."""
    inputs = [
        "scope",
        f"--rows={RUNNER / 'S0_ROWS.jsonl'}",
        f"--refused={MAIN_OUTPUT / 'logs' / '_write_dry' / 'ALL_REFUSED.jsonl'}",
    ]
    one, two = tmp_path / "SCOPE4.json", tmp_path / "SCOPE4.v2.json"
    three = tmp_path / "SCOPE4.v3.json"
    assert P.main([*inputs, "--version=1", f"--out={one}"]) == 0
    assert P.main([*inputs, "--version=2", f"--out={two}"]) == 0
    assert P.main([*inputs, f"--out={three}"]) == 0
    assert one.read_bytes() == S.SCOPE_V1_FILE.read_bytes()
    assert two.read_bytes() == S.SCOPE_V2_FILE.read_bytes()
    assert three.read_bytes() == S.SCOPE_FILE.read_bytes()


# ================================================= version 2: a marker without an entry (D9)

CITED = {"description_citations": [{"n": 1, "url": "https://example.org/one"}]}
#: Postgres' own digest of `raw_data::text` stands in the read; any hex digest does here.
CITED_SHA = "d" * 64
INPUTS_V2 = {**INPUTS, "SKIPPED.jsonl": "c" * 64}
INPUTS_V3 = {**INPUTS_V2, "MARCH4_ROWS.jsonl": "f" * 64}
#: The D9 plan's own shape of the list plan (`plan4.py build --scope-list d1-marker-without-entry
#: --first-batch 901`).
D9 = {"scope_lists": [S.D1_MARKER_WITHOUT_ENTRY], "first_batch": 901, "excluded": set()}


def march_row(n: int, **over: Any) -> dict[str, Any]:
    """One row in the exact shape `plan4.MARCH_SQL` returns (measured on production 2026-09-26)."""
    return {
        "id": uuid(n),
        "scope_status": None,
        "lane": None,
        "card": False,
        "live_p5": False,
        **over,
    }


def _march_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The March read of `rows`' sites: 1 March text and card, 3 a March card beside an unmarked
    description, 4 a March description without a card, 5 marked but retired, 2 a live Phase-5
    card, every other site neither."""
    special = {
        1: {"lane": "L", "card": True},
        2: {"lane": "W", "card": True, "live_p5": True},
        3: {"card": True},
        4: {"lane": "L"},
        5: {"lane": "L", "card": True, "scope_status": "retired"},
    }
    return [march_row(int(r["id"][-12:]), **special.get(int(r["id"][-12:]), {})) for r in rows]


def _v3_payload() -> dict[str, Any]:
    return S.scope_payload(
        _rows(), _cleared(), inputs=INPUTS_V3, version=3, march_rows=_march_rows(_rows())
    )


def _marker_rows() -> list[dict[str, Any]]:
    """`_rows()` with site 1's text citing a [2] beside its one entry, and two more sites: 7 cites a
    marker without an entry, 8 only the entry it has."""
    cited = {"raw_data": CITED, "raw_data_sha256": CITED_SHA}
    rows = _rows()
    rows[0] = row(1, description="Site 1 was a temple [1], later a fort [2].", **cited)
    return [
        *rows,
        row(7, description="A tomb [1] of the 1st century [2].", **cited),
        row(8, description="A tomb [1].", **cited),
    ]


def test_version_2_is_version_1_and_the_list_of_markers_without_an_entry() -> None:
    one = S.scope_payload(_marker_rows(), _cleared(), inputs=INPUTS, version=1)
    two = S.scope_payload(
        _marker_rows(), _cleared(), inputs=INPUTS_V2, version=2, markers=[uuid(7), uuid(1)]
    )
    assert (one["version"], two["version"]) == (1, 2)
    assert two["lists"] == {
        S.CLEARED_DESCRIPTION: 2,
        S.CLEARED_CARD: 2,
        S.UNGROUNDED_CARD: 1,
        D1: 2,
    }
    assert two["sites"] == [
        {"site_id": uuid(1), "lists": [S.CLEARED_DESCRIPTION, D1]},
        {"site_id": uuid(2), "lists": [S.CLEARED_CARD]},
        {"site_id": uuid(3), "lists": [S.CLEARED_DESCRIPTION, S.CLEARED_CARD]},
        {"site_id": uuid(4), "lists": [S.UNGROUNDED_CARD]},
        {"site_id": uuid(7), "lists": [D1]},
    ]
    earlier = {site["site_id"]: site["lists"] for site in one["sites"]}
    later = {site["site_id"]: site["lists"] for site in two["sites"]}
    assert all(later[site][: len(lists)] == lists for site, lists in earlier.items())
    assert (one["decision"], two["decision"]) == (S.DECISION, f"{S.DECISION} {S.ORDER_2026_09_25}")
    assert (set(one["methods"]), set(two["methods"])) == (set(S.LISTS[:3]), set(S.LISTS[:4]))
    assert S.parse_scope(S.render_scope(two)).sites[uuid(1)] == (S.CLEARED_DESCRIPTION, D1)


def test_a_listed_site_must_fail_d1_on_its_own_row() -> None:
    """The listing is the lane's read of 2026-09-25; the scope checks each listed site against the
    rows it is built from with D1's own reading (census T08): a site whose every marker has its
    entry, or that is no curated row, stops the build - no site is taken on the listing's word."""
    with pytest.raises(S.ScopeError, match="sets no marker without an entry"):
        S.scope_payload(_marker_rows(), _cleared(), inputs=INPUTS_V2, version=2, markers=[uuid(8)])
    with pytest.raises(S.ScopeError, match="not curated rows"):
        S.scope_payload(_marker_rows(), _cleared(), inputs=INPUTS_V2, version=2, markers=[uuid(9)])


def test_version_1_takes_no_marker_list_and_no_other_version_is_built() -> None:
    with pytest.raises(S.ScopeError, match="version 1 carries no list"):
        S.scope_payload(_marker_rows(), _cleared(), inputs=INPUTS, version=1, markers=[uuid(7)])
    with pytest.raises(S.ScopeError, match="no scope version 4"):
        S.scope_payload(_marker_rows(), _cleared(), inputs=INPUTS, version=4)


def test_a_marker_without_an_entry_is_read_as_d1_reads_it() -> None:
    """D1's first half (`acceptance/checks.d1`): the markers the census's T08 reads - a range
    expanded first - less the entries' numbers; a site without an array has no entry."""
    assert S.markers_without_entry(row(7, description="A tomb [1] of AD 100 [2].", raw_data=CITED)) == [2]  # fmt: skip
    assert S.markers_without_entry(row(7, description="Tombs [1-3].", raw_data=CITED)) == [2, 3]
    assert S.markers_without_entry(row(7, description="A tomb [1].", raw_data=CITED)) == []
    assert S.markers_without_entry(row(7, description="A tomb [1].", raw_data=None)) == [1]
    assert S.markers_without_entry(row(7, description=None, raw_data=CITED)) == []


def test_the_listing_gives_its_marker_without_entry_sites_once_each_in_its_order() -> None:
    """`SKIPPED.jsonl` lists every site the orphan-citations lane did not write, by reason; the list
    is the `marker-without-entry` ones (the lane's own spelling), each once."""
    from mechanical import citations

    assert S.D1_REASON == citations.MARKER_WITHOUT_ENTRY
    records = [
        {"site_id": uuid(7), "reason": S.D1_REASON},
        {"site_id": uuid(2), "reason": "citations-not-readable"},
        {"site_id": uuid(1), "reason": S.D1_REASON},
    ]
    assert S.listed_markers(records) == [uuid(7), uuid(1)]
    with pytest.raises(S.ScopeError, match="twice"):
        S.listed_markers([*records, records[0]])
    with pytest.raises(S.ScopeError, match="lacks a site id and a reason"):
        S.listed_markers([{"reason": S.D1_REASON}])


# ================================================================== plan4: scope and the plan


def _scope_inputs(tmp_path: Path, rows: list[dict[str, Any]]) -> list[str]:
    (tmp_path / "S0_ROWS.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    refused = [
        {"site_id": uuid(1), "field": "description", "rule": "report-only-field"},
        {"site_id": uuid(2), "field": "card_description", "rule": "report-only-field"},
        {"site_id": uuid(5), "field": "description", "rule": "reviewer-did-not-clear"},
    ]
    (tmp_path / "ALL_REFUSED.jsonl").write_text("".join(json.dumps(r) + "\n" for r in refused))
    return [
        "scope",
        f"--rows={tmp_path / 'S0_ROWS.jsonl'}",
        f"--refused={tmp_path / 'ALL_REFUSED.jsonl'}",
    ]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plan4_scope_writes_the_scope_file_from_the_rows_and_the_refusals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "SCOPE4.json"

    code = P.main([*_scope_inputs(tmp_path, _rows()), "--version=1", f"--out={out}"])

    printed = capsys.readouterr().out
    assert code == 0 and printed.rstrip().endswith("STAGE_EXIT=0")
    scope = S.parse_scope(out.read_bytes())
    assert set(scope.sites) == {uuid(1), uuid(2), uuid(4)}  # refuted is no defect
    assert scope.version == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["inputs"] == {
        "S0_ROWS.jsonl": _digest(tmp_path / "S0_ROWS.jsonl"),
        "ALL_REFUSED.jsonl": _digest(tmp_path / "ALL_REFUSED.jsonl"),
    }
    summary = json.loads(printed.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert (summary["sites"], summary["sha256"]) == (3, scope.sha256)


def test_plan4_scope_writes_version_2_with_the_d1_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Version 1's lists and the listing's sites, each checked against its row; the listing's
    digest joins the inputs."""
    argv = _scope_inputs(tmp_path, _marker_rows())
    listing = tmp_path / "SKIPPED.jsonl"
    skipped = [
        {"site_id": uuid(7), "reason": S.D1_REASON},
        {"site_id": uuid(1), "reason": S.D1_REASON},
    ]
    listing.write_text("".join(json.dumps(r) + "\n" for r in skipped), encoding="utf-8")
    out = tmp_path / "SCOPE4.v2.json"

    assert P.main([*argv, "--version=2", f"--markers={listing}", f"--out={out}"]) == 0

    scope = S.parse_scope(out.read_bytes())
    assert scope.version == 2
    assert scope.sites[uuid(7)] == (D1,)
    assert scope.sites[uuid(1)] == (S.CLEARED_DESCRIPTION, D1)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["inputs"]["SKIPPED.jsonl"] == _digest(listing)
    summary = json.loads(capsys.readouterr().out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert summary["lists"][D1] == 2 and summary["version"] == 2


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
    """The mass run's plan is version 1's (it was planned and written under it): a site only the
    current version adds (here uuid 7) never enters it, so the plan rebuilds byte for byte."""
    from tests.remediation.test_phase4_plan import _build_inputs

    argv = _build_inputs(tmp_path, [row(n) for n in range(1, 8)])
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"site_id": uuid(5)}) + "\n", encoding="utf-8")
    data = S.render_scope(S.scope_payload(_rows(), _cleared(), inputs=INPUTS, version=1))
    _pinned(monkeypatch, tmp_path, data, version=1)  # uuid 1-4 in scope, uuid 5 the pilot
    later = S.scope_payload(
        _marker_rows(),
        _cleared(),
        inputs=INPUTS_V3,
        version=3,
        markers=[uuid(7)],
        march_rows=_march_rows(_marker_rows()),
    )
    _pinned(monkeypatch, tmp_path, S.render_scope(later))  # the current version adds uuid 7

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


# ============================================ plan4: the plan of one list (build --scope-list)


def _listing_scope(sites: dict[str, tuple[str, ...]], *, version: int = 2) -> S.DefectScope:
    return S.DefectScope(version=version, sha256="c" * 64, sites=sites)


def test_the_list_plan_is_the_lists_sites_after_the_pilot_less_every_earlier_plans(
    tmp_path: Path,
) -> None:
    """HUMAN_ONLY D9 (owner order 2026-09-25): the sites of one list of the current scope, in the
    plan's order, less the pilot's and less every site an earlier plan carries - that run held or
    wrote it and never asks it again, and `verify_writes4.index_runs` refuses a site two runs carry
    (Killa Mach'ay: the mass run's p4-0042 held it `abstained`)."""
    rows = [row(n) for n in range(1, 41)]
    sites = build(rows, cleared={uuid(31): {"card_description"}}, gold=[uuid(1), uuid(2), uuid(3)])
    scope = _listing_scope(
        {
            uuid(1): (D1,),
            uuid(5): (S.CLEARED_CARD, D1),
            uuid(6): (D1,),
            uuid(30): (S.CLEARED_CARD,),
            uuid(31): (S.CLEARED_CARD, D1),
            uuid(32): (S.UNGROUNDED_CARD, D1),
        }
    )
    path = tmp_path / "PLAN4.d9.jsonl"

    tail = P.write_list_plan(path, sites, pilot=3, scope=scope, earlier={uuid(5)}, taken=115, **D9)

    assert [site.site_id for site in tail] == [uuid(31), uuid(6), uuid(32)]
    (batch,) = R.read_jsonl(path)
    assert (batch["batch_id"], batch["ordinal"]) == ("p4-0901", 901)
    assert [M.PlanSite.from_dict(s) for s in batch["sites"]] == tail


def test_the_list_plan_is_numbered_in_its_own_block_past_the_mass_runs_re_queue(
    tmp_path: Path,
) -> None:
    """A journal stamp names its batch (`phase4:p4-NNNN:chunk-NNNN`) and every run writes into the
    one P4 apply root. The mass run's plan ends at p4-0115 and `mass4.requeue_lines` numbers its
    re-queued sites on from p4-0116, so the D9 plan starts at p4-0901 (`--first-batch 901`), and a
    plan refuses to start where an earlier plan numbers that far already."""
    sites = build([row(n) for n in range(1, 25)], gold=[uuid(1)])
    scope = _listing_scope(dict.fromkeys([uuid(n) for n in range(2, 22)], (D1,)))
    path = tmp_path / "PLAN4.d9.jsonl"

    P.write_list_plan(path, sites, pilot=1, scope=scope, earlier=set(), taken=115, **D9)

    batches = R.read_jsonl(path)
    assert [(b["batch_id"], b["ordinal"], len(b["sites"])) for b in batches] == [
        ("p4-0901", 901, 15), ("p4-0902", 902, 5)
    ]  # fmt: skip
    again = tmp_path / "again.jsonl"
    with pytest.raises(R.InputError, match="p4-0901"):
        P.write_list_plan(again, sites, pilot=1, scope=scope, earlier=set(), taken=901, **D9)
    assert not again.exists()


def test_every_listed_site_is_accounted_for_and_the_list_plan_is_never_empty(
    tmp_path: Path,
) -> None:
    """A listed site the build's rows do not have is no site this plan, the pilot or an earlier
    plan accounts for; a list whose every site is carried elsewhere writes no plan; a list the
    scope's version does not carry is no list."""
    sites = build([row(n) for n in range(1, 6)], gold=[uuid(1)])
    path = tmp_path / "PLAN4.d9.jsonl"
    stray = _listing_scope({uuid(2): (D1,), uuid(9): (D1,)})
    with pytest.raises(R.InputError, match="no plan accounts for"):
        P.write_list_plan(path, sites, pilot=1, scope=stray, earlier=set(), taken=115, **D9)
    carried = _listing_scope({uuid(2): (D1,)})
    with pytest.raises(R.InputError, match="no site of d1-marker-without-entry"):
        P.write_list_plan(path, sites, pilot=1, scope=carried, earlier={uuid(2)}, taken=115, **D9)
    older = _listing_scope({uuid(2): (S.CLEARED_CARD,)}, version=1)
    with pytest.raises(R.InputError, match="version 1 carries no list"):
        P.write_list_plan(path, sites, pilot=1, scope=older, earlier=set(), taken=115, **D9)
    assert not path.exists()


def test_build_with_a_scope_list_writes_the_lists_plan_after_the_earlier_plans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.remediation.test_phase4_plan import _build_inputs

    argv = _build_inputs(tmp_path, _marker_rows())
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"site_id": uuid(5)}) + "\n", encoding="utf-8")
    earlier = tmp_path / "PLAN4.scope.jsonl"
    line = {"batch_id": "p4-0010", "ordinal": 10, "sites": [X.plan_site(uuid(1)).to_dict()]}
    earlier.write_text(json.dumps(line) + "\n", encoding="utf-8")
    scope = S.scope_payload(
        _marker_rows(),
        _cleared(),
        inputs=INPUTS_V3,
        version=3,
        markers=[uuid(1), uuid(7)],
        march_rows=_march_rows(_marker_rows()),
    )
    data = S.render_scope(scope)
    _pinned(monkeypatch, tmp_path, data)

    argv = [
        *argv,
        f"--pilot={pilot}",
        f"--scope-list={D1}",
        f"--after={earlier}",
        "--first-batch=901",
    ]
    assert P.main(argv) == 0

    (batch,) = R.read_jsonl(tmp_path / "PLAN4.jsonl")
    assert (batch["batch_id"], [s["site_id"] for s in batch["sites"]]) == ("p4-0901", [uuid(7)])
    assert "pass" not in batch  # the D9 plan writes cards: its bytes are the ones it was run from
    summary = json.loads(capsys.readouterr().out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert summary["lists"] == [D1] and summary["listed"] == 2 and summary["pass"] is None
    assert summary["carried_by_earlier_plans"] == [uuid(1)]
    assert (summary["sites"], summary["first_batch"]) == (1, "p4-0901")
    assert summary["scope"] == S.parse_scope(data).label


def test_build_with_a_scope_list_needs_the_pilot_and_the_earlier_plans(tmp_path: Path) -> None:
    argv = _build_inputs_of(tmp_path)
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"site_id": uuid(1)}) + "\n", encoding="utf-8")
    listed = [f"--scope-list={D1}", "--first-batch=901"]
    with pytest.raises(R.InputError, match="--after"):
        P.main([*argv, f"--pilot={pilot}", *listed])
    with pytest.raises(R.InputError, match="--pilot"):
        P.main([*argv, *listed, f"--after={pilot}"])
    with pytest.raises(R.InputError, match="--defect-scope"):
        P.main([*argv, f"--pilot={pilot}", *listed, f"--after={pilot}", "--defect-scope"])
    with pytest.raises(R.InputError, match="--first-batch"):
        P.main([*argv, f"--pilot={pilot}", f"--scope-list={D1}", f"--after={pilot}"])
    for flag in ("--first-batch=901", f"--exclude={pilot}", f"--take-deferred={tmp_path}"):
        with pytest.raises(R.InputError, match="name the lists"):
            P.main([*argv, f"--pilot={pilot}", f"--after={pilot}", flag])
    assert not (tmp_path / "PLAN4.jsonl").exists()


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
