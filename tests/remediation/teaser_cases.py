"""Fixtures of lane WB (teaser cards): real live descriptions, their sites as production rows, and
the answers an Opus writer, checker and judge would give.

The four descriptions are the live lane-W texts of Skara Brae, Newgrange, Stonehenge and
Sacsayhuamán, whole and byte for byte as a read-only SELECT returned them on 2026-09-26 01:13 UTC
(markers included), so the sentence splitting, the numeral reading and the prompt's examples are
tested on the text they will meet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from teaser import prompts as P  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation.phase4_cases import fake_card_fit  # noqa: E402

fit = fake_card_fit

SKARA = "2cbc1c11-5750-4b96-973b-7f1f8c847003"
NEWGRANGE = "e4f22a09-abfb-43d9-a7af-e87c033ae455"
STONEHENGE = "21b2278e-c3f2-4723-ae40-fa8a6161e3fb"
SACSAY = "61e8d3cd-1e93-4c78-a558-f2955a9fe221"
MARCH = "0a000000-0000-4000-8000-000000000001"
EMPTY = "0b000000-0000-4000-8000-000000000002"
RETIRED_SITE = "0c000000-0000-4000-8000-000000000003"

DESCRIPTIONS = {
    SKARA: (
        "Skara Brae is a stone-built Neolithic settlement located along the Bay of Skaill on the "
        "west coast of Mainland, Orkney [1]. The site was discovered following a storm exposing the "
        "presence of stone structures within the coastal sand dunes [1]. The site was occupied from "
        "roughly 3180 BC to around 2500 BC and is Europe's most complete Neolithic village [1]. "
        'Skara Brae gained UNESCO World Heritage Site status as one of four sites making up "The '
        'Heart of Neolithic Orkney" [1]. The inhabitants of Skara Brae were makers and users of '
        "grooved ware, a distinctive style of pottery that had recently appeared in northern "
        "Scotland [1]. The buildings follow a similar layout with a central hearth, beds on either "
        "side of the hearth, and a dresser opposite the entrance [1]."
    ),
    NEWGRANGE: (
        "Newgrange is a prehistoric monument in County Meath in Ireland, placed on a rise "
        "overlooking the River Boyne [1]. Newgrange is the main monument in the Brú na Bóinne "
        "complex, a World Heritage Site that also includes the passage tombs of Knowth and "
        "Dowth, as well as other henges, burial mounds and standing stones [1]. Newgrange "
        "consists of a large circular mound with an inner stone passageway and cruciform "
        "chamber [1]. Burnt and unburnt human bones and possible grave goods or votive "
        "offerings were found in this chamber [1]. The monument has a striking façade made "
        "mostly of white quartz cobblestones and ringed by engraved kerbstones [1]. Many of the "
        "larger stones of Newgrange are covered in megalithic art [1]. The mound is 85 metres "
        "wide at its widest point and 12 metres high, and covers 4,500 square metres of ground "
        '[1]. Excavations in the late 1960s and early 1970s revealed seven "marbles", four '
        "pendants, two beads, a used flint flake, a bone chisel, and fragments of bone pins and "
        "points [1]."
    ),
    STONEHENGE: (
        "Stonehenge is a prehistoric megalithic structure on Salisbury Plain in Wiltshire, "
        "England, two miles west of Amesbury [1]. It consists of an outer ring of vertical "
        "sarsen standing stones, each around 13 feet high, seven feet wide, and weighing around "
        "25 tons, topped by connecting horizontal lintel stones which are held in place with "
        "mortise and tenon joints—a feature unique among contemporary monuments [1]. Inside is "
        "a ring of smaller bluestones [1]. Inside these are free-standing trilithons: two "
        "bulkier vertical sarsens joined by a single lintel [1]. The whole monument, now in "
        "ruins, is aligned towards the sunrise on the summer solstice and sunset on the winter "
        "solstice [1]. The stones are set within earthworks in the middle of the densest "
        "complex of Neolithic and Bronze Age monuments in England, including several hundred "
        "tumuli (burial mounds) [1]. Stonehenge was constructed in several phases, beginning "
        "about 3100 BC and continuing until about 1600 BC [1]. The famous circle of large "
        "sarsen stones was placed between 2600 BC and 2400 BC [1]."
    ),
    SACSAY: (
        "Sacsayhuamán or Saksaywaman is a citadel on the northern outskirts of the city of "
        "Cusco, Peru, the historic capital of the Inca Empire [1]. The site is an important "
        "example of Inca architecture and sits at an altitude of 3,701 metres [1]. The Spanish "
        "chroniclers recorded that within the Inca's oral history, the fortress was said to be "
        "built during the reign of Sapa Inca Pachacuti and his successors, Topa Inca Yupanqui "
        "and Huayna Capac [1]. Dry stone walls constructed of huge stones were built on the "
        "site, with the workers carefully cutting the boulders to fit them together tightly "
        "without mortar [1]. Archeological studies of surface collections of pottery at "
        "Sacsayhuamán indicate that the earliest occupation of the hilltop dates to about 900 "
        "CE [1]. During the 15th century, the Imperial Inca expanded on this settlement, "
        "building dry stone walls constructed of huge stones [1]."
    ),
    MARCH: "An old March text about a hill fort built c. 500 BC by unknown people.",
}
NAMES = {
    SKARA: "Skara Brae",
    NEWGRANGE: "Newgrange",
    STONEHENGE: "Stonehenge",
    SACSAY: "Sacsayhuamán",
    MARCH: "Old Hill Fort",
    EMPTY: "Nameless Mound",
    RETIRED_SITE: "Retired Tomb",
}
SITE_OF = {name: site_id for site_id, name in NAMES.items()}
COUNTRIES = {
    SKARA: "Scotland",
    NEWGRANGE: "Ireland",
    STONEHENGE: "England",
    SACSAY: "Peru",
    MARCH: "Wales",
    EMPTY: "France",
    RETIRED_SITE: "Italy",
}

#: The prompt's example cards (`teaser.prompts.EXAMPLES`), by site: each passes the mechanical contract
#: against its site's full live description, and `test_teaser.TestTheExamples` pins that the sentences
#: an example shows are that description's own, by id and text.
GOOD = {SITE_OF[example.site]: example.card for example in P.EXAMPLES}

OLD_CARD = "An old card from the March file."


def sha(text: str) -> str:
    return CP.text_sha256(text)


def row(site_id: str, **over: Any) -> dict[str, Any]:
    """One `run.SITES_SQL` row, as the tagged export returns it: lane W, provenance hashing the
    description, no sentence check, an old card, no teaser provenance."""
    description = DESCRIPTIONS.get(site_id)
    base: dict[str, Any] = {
        "site_id": site_id,
        "name": NAMES[site_id],
        "country": COUNTRIES[site_id],
        "description": description,
        "scope_status": None,
        "lane": "W",
        "provenance_desc_sha256": None if description is None else sha(description),
        "check_desc_sha256": None,
        "card_provenance": None,
        "has_card_row": True,
        "card": OLD_CARD,
        "alt_names": [NAMES[site_id]],
    }
    base.update(over)
    return base


def production_rows() -> list[dict[str, Any]]:
    """The curated sites of the fixture production: four lane-W candidates, a March text, a site
    without a description (its card is cleared) and a retired one."""
    return [
        row(SKARA),
        row(NEWGRANGE),
        row(STONEHENGE),
        row(SACSAY),
        row(MARCH, lane="L"),
        row(EMPTY, description=None, lane=None, provenance_desc_sha256=None),
        row(RETIRED_SITE, description="A tomb.", scope_status="retired"),
    ]


def tagged(kind_rows: dict[str, list[dict[str, Any]]], at: str = "2026-09-26 12:00:00+00") -> str:
    """The text of a `tagged_export_script` read: one line per row, then the snapshot line."""
    lines = [
        json.dumps({"kind": kind, "row": r}, ensure_ascii=False)
        for kind, rows in kind_rows.items()
        for r in rows
    ]
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": at}}))
    return "\n".join(lines) + "\n"


def writer_answer(card: str, basis: list[str] | None = None) -> str:
    return json.dumps({"card": card, "basis": basis or ["S1"]}, ensure_ascii=False)


def checker_answer(
    verdict: str = "PASS",
    claims: list[tuple[str, list[str]]] | None = None,
    reasons: list[str] | None = None,
    tone_ok: bool = True,
    this_site: bool = True,
) -> str:
    claims = claims or [("the site's main facts", ["S1"])]
    return json.dumps(
        {
            "claims": [{"claim": c, "support": s} for c, s in claims],
            "tone_ok": tone_ok,
            "this_site": this_site,
            "verdict": verdict,
            "reasons": reasons or [],
        }
    )


def teaser(site_id: str, card: str | None = None, description: str | None = None) -> dict:
    """A lane-WB provenance of the site's good card."""
    return CP.build(
        run="wb-test",
        ai_system="Claude Opus (Anthropic): test",
        card=GOOD[site_id] if card is None else card,
        description=DESCRIPTIONS[site_id] if description is None else description,
        stage="check",
        checker="teaser-check-001",
        checked_at="2026-09-26T12:00:00+00:00",
        claims=[{"claim": "the site's main facts", "support": ["S1"]}],
    )
