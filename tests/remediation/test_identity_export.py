"""The identity discovery reads production once, read-only - and reads the answer back faithfully."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from identity import common, entities, export  # noqa: E402

from tests.remediation.identity_fixtures import entity, export_of, ext, site, store_of  # noqa: E402

WRITE_VERB = re.compile(
    r"\b(insert|update|delete|truncate|drop|alter|create|grant|revoke|copy|call|do|vacuum)\b", re.I
)


class TestTheReadIsReadOnly:
    def test_the_script_sets_the_session_read_only_before_anything_runs(self) -> None:
        script = export.build_script()
        lines = script.splitlines()
        assert lines[0] == "\\set QUIET on"
        assert lines[1] == "SET default_transaction_read_only = on;"

    def test_a_tagged_export_that_no_longer_starts_quiet_is_refused(self, monkeypatch) -> None:
        monkeypatch.setattr(export, "tagged_export_script", lambda parts: "BEGIN;")
        with pytest.raises(common.IdentityError, match="QUIET"):
            export.build_script()

    def test_the_script_runs_inside_a_read_only_repeatable_read_transaction(self) -> None:
        script = export.build_script()
        assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script
        assert script.rstrip().endswith("COMMIT;")

    def test_no_part_names_a_write_verb(self) -> None:
        for kind, sql in export.PARTS:
            # a string literal or a column alias is not a verb: strip the quoted text first
            bare = re.sub(r"'[^']*'", "''", sql)
            assert not WRITE_VERB.search(bare), (kind, WRITE_VERB.search(bare).group(0))

    def test_every_kind_the_modules_read_is_a_part_and_the_other_way_round(self) -> None:
        assert tuple(kind for kind, _ in export.PARTS) == export.KINDS

    def test_the_window_in_the_shown_part_is_the_scope_lanes_own_rule(self) -> None:
        from mechanical.lane import outside_e3_window

        assert outside_e3_window("u.") in export.SHOWN_SQL
        assert outside_e3_window("u.") in export.PERIOD_JOURNAL_SQL

    def test_the_period_journal_leaves_out_rollbacks_and_probes(self) -> None:
        assert "NOT LIKE '%rollback%'" in export.PERIOD_JOURNAL_SQL
        assert "NOT LIKE '%probe%'" in export.PERIOD_JOURNAL_SQL


class TestTheAnswerIsReadBack:
    def lines(self, shown: list[dict]) -> str:
        parts = [json.dumps({"kind": "shown", "row": s}) for s in shown] + [
            json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-10-08 20:00:00+00"}})
        ]
        return "\n".join(parts) + "\n"

    def test_load_export_returns_the_rows_of_each_kind_and_the_clock(self, tmp_path) -> None:
        path = tmp_path / "EXPORT.jsonl"
        path.write_text(self.lines([site()]), encoding="utf-8")
        loaded = export.load_export(path)
        assert len(loaded.shown) == 1 and loaded.pairs == [] and loaded.losers == []
        assert loaded.exported_at == "2026-10-08 20:00:00+00"

    def test_an_export_without_a_shown_site_is_refused_not_read_as_empty(self, tmp_path) -> None:
        path = tmp_path / "EXPORT.jsonl"
        path.write_text(self.lines([]), encoding="utf-8")
        with pytest.raises(common.IdentityError, match="no shown site"):
            export.load_export(path)

    def test_qids_and_titles_are_grouped_per_site_in_the_tables_order(self) -> None:
        rows = [
            ext("a", "wikidata_qid", "Q1"),
            ext("a", "wikidata_qid", "Q2"),
            ext("a", "enwiki_title", "A_b"),
            ext("b", "wikidata_qid", "Q3"),
        ]
        assert export.qids_by_site(rows) == {"a": ["Q1", "Q2"], "b": ["Q3"]}
        assert export.enwiki_by_site(rows) == {"a": ["A_b"]}

    def test_two_rows_with_one_id_are_refused(self) -> None:
        one = site()
        with pytest.raises(common.IdentityError, match="same id"):
            common.rows_by_id([one, dict(one)])


class TestTheEntitiesComeFromTheHarvestThenTheDelta:
    def test_a_harvested_item_is_found_in_the_harvest(self, tmp_path) -> None:
        store = store_of(tmp_path, {"Q1": entity("Q1", label="One")}, {})
        item, source = store.get("Q1")
        assert item["id"] == "Q1" and source == entities.SOURCE_HARVEST

    def test_an_item_both_roots_hold_is_read_from_the_harvest(self, tmp_path) -> None:
        store = store_of(
            tmp_path,
            {"Q1": entity("Q1", label="Harvest")},
            {},
            delta={"Q1": entity("Q1", label="Delta")},
        )
        item, source = store.get("Q1")
        assert source == entities.SOURCE_HARVEST
        assert item["labels"]["en"]["value"] == "Harvest"

    def test_an_item_only_the_delta_holds_is_found_there(self, tmp_path) -> None:
        store = store_of(tmp_path, {}, {}, delta={"Q2": entity("Q2")})
        assert store.get("Q2")[1] == entities.SOURCE_DELTA
        assert store.missing(["Q2", "Q3"]) == ["Q3"]

    def test_a_class_without_a_label_is_named_by_its_id_never_by_an_empty_string(
        self, tmp_path
    ) -> None:
        store = store_of(tmp_path, {}, {"Q5": "village"})
        assert store.class_label("Q5") == "village"
        assert store.class_label("Q6") == "Q6"

    def test_the_fetch_asks_only_for_the_items_neither_root_holds_and_seeds_the_classes(
        self, tmp_path, monkeypatch
    ) -> None:
        from fields import harvest as H

        store_of(tmp_path, {"Q1": entity("Q1", p31=("Q5",))}, {"Q5": "village"})
        asked: list[list[str]] = []

        def fake_fetch(net, root, qids, **kw):
            asked.append(list(qids))
            for q in qids:
                H._write_json(H.entity_path(root, q), entity(q, p31=("Q5",)))
            return {"items": len(asked[-1]), "fetched": len(asked[-1]), "cached": 0}

        monkeypatch.setattr(H, "fetch_entities", fake_fetch)
        monkeypatch.setattr(H, "fetch_classes", lambda *a, **k: {"classes": 1, "fetched": 0})
        result = entities.fetch_delta(
            ["Q1", "Q9"], tmp_path / "harvest", tmp_path / "delta", net=object()
        )
        assert asked == [["Q9"]] and result == {"asked": 1, "fetched": 1}
        # the delta's class file starts as the harvest's, so a class already labelled is not asked
        seeded = json.loads((tmp_path / "delta" / "CLASSES.json").read_text(encoding="utf-8"))
        assert seeded["Q5"]["label"] == "village"

    def test_nothing_missing_means_no_fetcher_is_opened(self, tmp_path, monkeypatch) -> None:
        from fields import harvest as H

        store_of(tmp_path, {"Q1": entity("Q1")}, {})

        def refuse(*_a, **_k):
            raise AssertionError("a fetcher was opened though nothing is missing")

        monkeypatch.setattr(H, "open_fetcher", refuse)
        out = entities.fetch_delta(["Q1"], tmp_path / "harvest", tmp_path / "delta")
        assert out == {"asked": 0, "fetched": 0}
        assert export_of([site()]).shown
