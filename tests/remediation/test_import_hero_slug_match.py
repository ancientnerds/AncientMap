# SPDX-License-Identifier: AGPL-3.0-only
"""The file's identity is its upload URL, not the slug in the import's link.

Measured 2026-10-06 on the run `import-hero-2026-10-06-006`: 3 of the 147 downloaded files were
refused as `no_target_row` although the site already held the file, because the import's link
carries a slightly different slug than the stored row - `The_East_Facade_pf_the_Parthenon…` for
`…_of_the_…`, `East_Terrace_(4961323529).jpg` for `Mount_Nemrut_-_East_Terrace_(4961323529).jpg`
and one title that gained `zyklopenhaftes`. All three resolve to the same `original_url`, which is
also the key the unique constraint `(site_id, original_url)` holds.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from import_hero import insert as IN  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from served_image import state as ST  # noqa: E402

SITE = "11111111-1111-1111-1111-111111111111"
IMPORT_IMAGE = (
    "https://upload.wikimedia.org/wikipedia/commons/0/03/"
    "The_East_Facade_pf_the_Parthenon_on_March_22%2C_2021.jpg"
)
#: what the row of the site actually holds, and what the fetch resolves the import's link to
STORED_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/0/03/"
    "The_East_Facade_of_the_Parthenon_on_March_22%2C_2021.jpg"
)
FILENAME = "The_East_Facade_of_the_Parthenon_on_March_22,_2021.webp"


def _row(row_id: int, site_id: str, **over: Any) -> dict[str, Any]:
    row = {
        "id": row_id,
        "site_id": site_id,
        "filename": FILENAME,
        "original_url": STORED_URL,
        "commons_page_url": "",
        "thumb_width": None,
        "author": "",
        "author_url": "",
        "license": "",
        "license_url": "",
        "title": "",
        "is_hero": False,
        "is_lead": False,
        "is_excluded": False,
        "sort_order": 0,
        "source_type": "wikimedia",
        "file_size_bytes": 1,
        "width": 1600,
        "height": 1200,
        "created_at": "2026-01-01",
        "image_kind": None,
    }
    row.update(over)
    return row


def _state(rows: dict[str, list[dict[str, Any]]], thumbs: dict[str, str | None] | None = None):
    return ST.State(
        read_at="2026-10-06T00:00:00Z",
        sha256="0" * 64,
        sites={
            SITE: {
                "id": SITE,
                "name": "Parthenon",
                "source_id": "ancient_nerds",
                "source_url": "https://example.org/parthenon",
                "thumbnail_url": (thumbs or {}).get(SITE),
            }
        },
        rows=rows,
        retired=(),
    )


def _fetch() -> dict[str, Any]:
    entry = {column: f"v-{column}" for column in IH.FETCH_COLUMNS}
    entry.update(
        {
            "filename": FILENAME,
            "original_url": STORED_URL,
            "width": "1600",
            "height": "1200",
            "file_size_bytes": "370830",
        }
    )
    return entry


def _claims(image: str = IMPORT_IMAGE) -> dict[str, dict[str, Any]]:
    return {SITE: {"matched_on": "url", "image": image, "features": 1}}


def test_the_plan_finds_the_row_the_import_links_although_the_slug_differs() -> None:
    state = _state(rows={SITE: [_row(42, SITE)]}, thumbs={SITE: None})
    planned = IH.plan(state, _claims(), dimensions={42: (1600, 1200)}, fetched={SITE: _fetch()})
    assert not planned.refusals, planned.refusals
    # ih1 moves the flag onto the row that exists, ih4 names it as the thumbnail - the same two
    # rules the hero wave applies, so these sites need no row at all
    assert {change.rule for change in planned.changes} == {"ih1", "ih4"}
    assert {change.row_key for change in planned.changes} == {"42", SITE}


def test_without_the_resolved_url_the_claim_still_says_no_row() -> None:
    """The second arm needs measured evidence: without the fetch there is nothing to match on."""
    state = _state(rows={SITE: [_row(42, SITE)]}, thumbs={SITE: None})
    planned = IH.plan(state, _claims(), dimensions={42: (1600, 1200)}, fetched={})
    assert [refusal.reason for refusal in planned.refusals] == ["no_target_row"]


def test_the_insert_lane_refuses_a_row_the_site_already_holds() -> None:
    state = _state(rows={SITE: [_row(42, SITE)]}, thumbs={SITE: None})
    refusal = {"site_id": SITE, "reason": "no_target_row", "detail": ""}
    planned = IN.plan(state, [refusal], fetched={SITE: _fetch()})
    assert not planned.inserts
    assert [r.reason for r in planned.refusals] == ["already_holds_the_file"]
    assert "42" in planned.refusals[0].detail


def test_a_site_that_holds_another_file_still_gets_its_insert() -> None:
    other = _row(
        42, SITE, original_url="https://upload.wikimedia.org/wikipedia/commons/0/03/Other.jpg"
    )
    state = _state(rows={SITE: [other]}, thumbs={SITE: None})
    refusal = {"site_id": SITE, "reason": "no_target_row", "detail": ""}
    planned = IN.plan(state, [refusal], fetched={SITE: _fetch()})
    assert len(planned.inserts) == 1
    assert planned.inserts[0].values["original_url"] == STORED_URL


def test_the_thumbnail_names_the_row_the_site_already_holds() -> None:
    """ih4 takes the fetched name only where ih5 renames the row - measured 2026-10-06 on run
    `import-hero-2026-10-06-007`, whose three sites got a thumbnail for a file that was never
    fetched and the acceptance refused all three."""
    state = _state(rows={SITE: [_row(42, SITE)]}, thumbs={SITE: None})
    planned = IH.plan(state, _claims(), dimensions={42: (1600, 1200)}, fetched={SITE: _fetch()})
    thumb = next(c for c in planned.changes if c.rule == "ih4")
    assert thumb.new_value == f"/data/images/wiki/{SITE[:8]}/{FILENAME}"


def test_a_row_renamed_by_ih5_takes_the_fetched_name() -> None:
    """The other half: where the wave rewrites the row's file, the thumbnail follows that name."""
    state = _state(rows={SITE: [_row(42, SITE, filename="old.webp")]}, thumbs={SITE: None})
    planned = IH.plan(state, _claims(), dimensions={42: (800, 600)}, fetched={SITE: _fetch()})
    thumb = next(c for c in planned.changes if c.rule == "ih4")
    assert thumb.new_value == f"/data/images/wiki/{SITE[:8]}/{FILENAME}"


def test_the_acceptance_accepts_the_row_by_its_upload_url() -> None:
    from import_hero import verify as IV

    wanted_thumb = f"/data/images/wiki/{SITE[:8]}/{FILENAME}"
    state = _state(rows={SITE: [_row(42, SITE, is_hero=True)]}, thumbs={SITE: wanted_thumb})
    ids = [SITE]

    without = IV.check_wave(state, _claims(), ids)
    assert not without.ok, without.problems  # the link's slug does not match the stored name

    with_url = IV.check_wave(state, _claims(), ids, fetched={SITE: _fetch()})
    assert with_url.ok, with_url.problems
    assert with_url.served_the_import == 1
