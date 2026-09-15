# SPDX-License-Identifier: AGPL-3.0-only
"""insert_promoted_site is the single INSERT path shared by radar and proposals."""

import inspect
from unittest.mock import MagicMock

from api.routes import proposals, radar
from api.services.site_promotion import insert_promoted_site
from pipeline.lyra.site_key import site_key_sql


def test_radar_no_longer_carries_its_own_insert():
    src = inspect.getsource(radar.promote_to_db)
    assert "INSERT INTO unified_sites" not in src
    assert "insert_promoted_site(" in src


def test_proposals_approve_uses_the_shared_insert():
    src = inspect.getsource(proposals.approve_proposal)
    assert "insert_promoted_site(" in src
    assert 'source_id="lyra"' in src  # owner's decision 2026-09-14: keep the lyra tier


def test_insert_writes_the_db_key_not_a_python_key():
    db = MagicMock()
    site_id = insert_promoted_site(
        db,
        name="Ayşepınar",
        lat=37.0,
        lon=28.0,
        site_type="Settlement",
        period_start=-3000,
        period_end=None,
        period_name="3000 - 1500 BC",
        country="Türkiye",
        description="x" * 60,
        thumbnail_url=None,
        source_url=None,
        source_id="lyra",
        source_record_id="proposal-1",
        edited_by="proposal_approve",
    )
    assert site_id is not None
    sqls = [str(call.args[0]) for call in db.execute.call_args_list]
    assert len(sqls) == 2
    assert site_key_sql(":name") in sqls[0]
    assert site_key_sql(":name") in sqls[1]
    assert "name_normalized" in sqls[0]
    params = db.execute.call_args_list[0].args[1]
    assert params["edited_by"] == "proposal_approve"
    assert "name_normalized" not in params  # computed in SQL, never bound from Python


def test_insert_does_not_commit():
    db = MagicMock()
    insert_promoted_site(
        db,
        name="X",
        lat=1.0,
        lon=2.0,
        site_type=None,
        period_start=None,
        period_end=None,
        period_name=None,
        country=None,
        description=None,
        thumbnail_url=None,
        source_url=None,
        source_id="lyra",
        source_record_id="r",
        edited_by="t",
    )
    db.commit.assert_not_called()
