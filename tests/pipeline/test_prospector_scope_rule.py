# SPDX-License-Identifier: AGPL-3.0-only
"""The scope rule D58 in the Prospector and at the proposal's approval.

The Prospector files every name for a founder's review and asks no scope verdict itself, so it
reads the whole rule (`dates.label_scope`): a Viking subject is `out_of_scope` by its Wikidata
item wherever it lies (L'Anse aux Meadows, Q189113, which production held as `in_scope` on
2026-10-24), and a borderline record (a Crusader castle's date in Syria) is filed under the
`scope_verdict` `label_borderline`, the founder's question. The approval refuses a Viking subject.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.routes import proposals
from pipeline.lyra.prospector import propose, resolve
from pipeline.lyra.prospector.resolve import Resolution

L_ANSE = {
    "label_en": "L'Anse aux Meadows",
    "wikipedia_title": "L'Anse aux Meadows",
    "wikipedia_url": "https://en.wikipedia.org/wiki/L%27Anse_aux_Meadows",
    "instance_of": ["Q839954"],
    "country": "Canada",
    "coord_precision": 0.0001,
    "lat": 51.596,
    "lon": -55.533,
    "start_time": "+1000-00-00T00:00:00Z",
}
KRAK = {
    **L_ANSE,
    "label_en": "Krak des Chevaliers",
    "wikipedia_title": "Krak des Chevaliers",
    "country": "Syria",
    "lat": 34.757,
    "lon": 36.294,
    "start_time": "+1142-00-00T00:00:00Z",
}


def resolved(name: str, qid: str, enrich: dict[str, Any]) -> Resolution:
    res = Resolution(name=name, path="title", qid=qid, canonical_title=name)
    with (
        patch.object(resolve, "_enrich_from_wikidata", return_value=enrich),
        patch.object(resolve, "_fetch_wikipedia_summary", return_value={}),
    ):
        resolve._confirm_and_enrich(res)
    assert res.verdict == "resolved"
    return res


class FakeSession:
    """Records the parameters of every statement; finds no existing proposal."""

    def __init__(self) -> None:
        self.params: list[dict[str, Any]] = []

    def execute(self, _statement: Any, params: dict[str, Any] | None = None) -> Any:
        self.params.append(params or {})
        return SimpleNamespace(scalar=lambda: "name-key", fetchone=lambda: None)


def filed(res: Resolution) -> dict[str, Any]:
    session = FakeSession()
    propose.upsert_proposal(
        session,
        name=res.name,
        place_class="site",
        res=res,
        verdict=None,
        country_in_text=None,
        period_phrase=None,
    )
    (insert,) = [p for p in session.params if "scope_verdict" in p]
    return insert


class TestTheProspector:
    def test_l_anse_aux_meadows_is_out_of_scope_by_its_item(self) -> None:
        res = resolved("L'Anse aux Meadows", "Q189113", L_ANSE)
        assert res.scope == "out_of_scope"
        assert propose.derive_status("site", res, None) == "out_of_scope"
        row = filed(res)
        assert (row["status"], row["scope_verdict"]) == ("out_of_scope", "out_of_scope")

    def test_the_same_place_under_another_item_is_in_scope(self) -> None:
        res = resolved("L'Anse aux Meadows", "Q1", L_ANSE)
        assert res.scope == "in_scope"
        assert filed(res)["scope_verdict"] == "in_scope"

    def test_a_borderline_record_is_filed_for_the_founder_s_label_question(self) -> None:
        res = resolved("Krak des Chevaliers", "Q190127", KRAK)
        assert res.scope == "label_borderline"
        assert propose.derive_status("site", res, None) == "new"
        row = filed(res)
        assert (row["status"], row["scope_verdict"]) == ("new", "label_borderline")

    def test_an_unresolved_name_stays_in_scope(self) -> None:
        res = Resolution(name="Somewhere")
        assert filed(res)["scope_verdict"] == "in_scope"


class TestTheApproval:
    def row(self, qid: str | None) -> SimpleNamespace:
        return SimpleNamespace(status="new", wikidata_qid=qid, _mapping={})

    def test_a_viking_subject_is_refused_before_anything_is_written(self) -> None:
        with (
            patch.object(proposals, "_load", return_value=self.row("Q189113")),
            patch.object(proposals, "insert_promoted_site") as insert,
        ):
            with pytest.raises(HTTPException) as refused:
                proposals.approve_proposal("01e29c6e", None, user=None, db=None)
        assert refused.value.status_code == 422
        assert refused.value.detail["out_of_scope"] == ["Q189113"]
        assert "D58" in refused.value.detail["message"]
        insert.assert_not_called()

    def test_another_item_goes_on_to_the_core_field_check(self) -> None:
        with (
            patch.object(proposals, "_load", return_value=self.row("Q1")),
            patch.object(proposals, "_missing_core_fields", return_value=["lat"]),
            patch.object(proposals, "insert_promoted_site") as insert,
        ):
            with pytest.raises(HTTPException) as refused:
                proposals.approve_proposal("x", None, user=None, db=None)
        assert refused.value.detail["missing"] == ["lat"]
        insert.assert_not_called()
