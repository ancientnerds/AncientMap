"""Phase 6 item 2: the match keys recomputed by Postgres (`scripts/remediation/name_key/plan.py`).

`unified_sites.name_normalized` and `unified_site_names.name_normalized` are the match key
`left(lower(unaccent(name)), 500)` (pipeline/lyra/site_key.py). Read on production 2026-09-25:
0 curated site rows and 11 alias rows of curated sites carry another key - Lyra's Wikidata aliases,
keyed by Python's normalize_name. The lane writes the key Postgres derives, through the shared chunk
writer (`gallery_audit/chunk_writer.py`), which learns the two key columns here:

* a name row must exist and belong to the site the plan names (guard 2b, both directions);
* the planned key must be the one Postgres derives from the row's name at write time (guard 2c,
  the write only - the rollback restores the journalled old key, which is by definition not it);
* a chunk without a key row renders byte for byte as before (the delivered chunks stay checkable).

`plan_keys` is a pure function of the production read; the key it writes is the read's
`sql_key`, computed by Postgres - never by Python.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from gallery_audit import chunk_writer as C  # noqa: E402
from name_key import plan as NK  # noqa: E402

from pipeline.lyra.site_key import site_key_sql  # noqa: E402

YAP = "624a1828-419b-46e4-93d0-ef7b4981aa29"
CERUTTI = "ccccdfe7-8288-4451-a222-07facc1bfe50"
LANE = C.Lane("name-key", "P6/name-key", "name-key-2026-09-25", "authoritative", "name key")
EV = [{"source": "unified_site_names:3617031", "quote": "stored 'x'"}]
THUMBNAIL = REPO / "output" / "remediation" / "hero_repair" / "thumbnail-2026-09-25" / "chunk-001"


def _name_change(row="3617031", site=YAP, old="ヤッフ島", new="ヤップ島"):
    return C.Change("unified_site_names", "name_normalized", row, site, old, new, "K1", "why", EV)


def _site_change(site=CERUTTI, old="eridu, sumeria", new="eridu"):
    return C.Change("unified_sites", "name_normalized", site, site, old, new, "K1", "why", EV)


def _render(*changes, rollback=False) -> str:
    (chunk,) = C.chunk_changes(LANE, list(changes))
    return C.render_statement(chunk, rollback=rollback)


# ------------------------------------------------------------------ the writer's two key columns
class TestTheWriterLearnsTheKeyColumns:
    def test_both_key_columns_are_writable_text(self):
        assert C.WRITABLE[("unified_site_names", "name_normalized")] == "text"
        assert C.WRITABLE[("unified_sites", "name_normalized")] == "text"
        C.validate_change(_name_change())
        C.validate_change(_site_change())

    def test_a_name_row_is_keyed_by_its_integer_id(self):
        with pytest.raises(C.ChunkError, match="not a row id"):
            C.validate_change(_name_change(row="x1"))
        with pytest.raises(C.ChunkError, match="is its site"):
            C.validate_change(
                C.Change("unified_sites", "name_normalized", CERUTTI, YAP, "a", "b", "K1", "w", EV)
            )

    def test_a_key_is_never_cleared(self):
        with pytest.raises(C.ChunkError, match="never cleared"):
            C.validate_change(_name_change(new=None))

    def test_the_name_row_guard_is_rendered_in_both_directions(self):
        for rollback in (False, True):
            sql = _render(_name_change(), rollback=rollback)
            assert "LEFT JOIN unified_site_names n ON n.id = CASE WHEN p.table_name = " in sql
            assert (
                "WHERE p.table_name = 'unified_site_names' AND (n.id IS NULL OR n.site_id IS "
                "DISTINCT FROM p.site_id);"
            ) in sql
            assert "planned name row(s) do not belong to the site the plan names" in sql

    def test_the_key_premise_is_postgres_s_own_key_of_the_row_name_on_the_write_only(self):
        write = _render(_name_change(), _site_change())
        assert f"AND p.new_value IS DISTINCT FROM {site_key_sql('n.name')};" in write
        assert f"AND p.new_value IS DISTINCT FROM {site_key_sql('s.name')};" in write
        assert "planned key(s) are not the key Postgres derives from the name" in write
        undo = _render(_name_change(), _site_change(), rollback=True)
        assert site_key_sql("n.name") not in undo
        assert site_key_sql("s.name") not in undo

    def test_a_chunk_without_a_key_row_renders_as_before(self):
        ev = [{"source": "commons:File page", "quote": "Jane"}]
        sql = _render(C.Change("wiki_images", "author", "101", YAP, None, "Jane", "A1", "why", ev))
        assert "unified_site_names" not in sql
        assert "guard 2b" not in sql and "guard 2c" not in sql
        assert "    END IF;\n\n    -- guard 3:" in sql  # guard 2 runs straight into guard 3
        assert site_key_sql("n.name") not in sql

    def test_the_delivered_thumbnail_chunk_still_checks(self):
        chunk = C.check_delivered(THUMBNAIL)
        assert len(chunk.changes) == 1

    def test_the_key_statement_holds_no_update_and_one_commit(self):
        C.lint_statement(_render(_name_change(), _site_change()))
        C.lint_statement(_render(_name_change(), _site_change(), rollback=True))


# ------------------------------------------------------------------------------- the planner
def _name_row(
    row_id=3617031, site=YAP, name="ヤップ島", stored="ヤッフ島", sql_key="ヤップ島", **over
):
    return {
        "id": row_id,
        "site_id": site,
        "source_id": "ancient_nerds",
        "name": name,
        "name_normalized": stored,
        "sql_key": sql_key,
        "name_type": "wikidata_alias",
        "collides_with": None,
        **over,
    }


def _site_row(site=CERUTTI, name="Eridu", stored="eridu, sumeria", sql_key="eridu", **over):
    return {
        "id": site,
        "source_id": "ancient_nerds",
        "name": name,
        "name_normalized": stored,
        "sql_key": sql_key,
        **over,
    }


class TestThePlan:
    def test_a_divergent_alias_key_becomes_postgres_s_key(self):
        changes, listed = NK.plan_keys([], [_name_row()])
        assert listed == []
        (change,) = changes
        assert (change.table, change.column, change.row_key, change.site_id) == (
            "unified_site_names",
            "name_normalized",
            "3617031",
            YAP,
        )
        assert (change.old_value, change.new_value) == ("ヤッフ島", "ヤップ島")
        assert change.rule == "K1"
        sources = [e["source"] for e in change.evidence]
        assert "unified_site_names:3617031" in sources
        assert "pipeline/lyra/site_key.py" in sources

    def test_a_divergent_site_key_becomes_postgres_s_key(self):
        (change,), _ = NK.plan_keys([_site_row()], [])
        assert (change.table, change.row_key, change.site_id) == ("unified_sites", CERUTTI, CERUTTI)
        assert (change.old_value, change.new_value) == ("eridu, sumeria", "eridu")

    def test_a_key_another_row_of_the_site_already_holds_is_listed_not_planned(self):
        """uq_usn (site_id, name_normalized) would refuse the write; the row is a duplicate of
        the other, and removing it is a DELETE - not this lane's."""
        changes, listed = NK.plan_keys([], [_name_row(collides_with=3617999)])
        assert changes == []
        assert listed == [
            {"table": "unified_site_names", "row": "3617031", "reason": "key-held-by-row-3617999"}
        ]

    def test_a_row_of_another_source_is_listed_not_planned(self):
        changes, listed = NK.plan_keys(
            [_site_row(source_id="lyra")], [_name_row(source_id="ancient_nerds_community")]
        )
        assert changes == []
        assert [entry["reason"] for entry in listed] == [
            "source-lyra-not-the-writer-s",
            "source-ancient_nerds_community-not-the-writer-s",
        ]

    @pytest.mark.parametrize(
        ("row", "says"),
        [
            (_name_row(sql_key=None), "no key from Postgres"),
            (_name_row(sql_key="ヤッフ島"), "already holds"),
        ],
    )
    def test_a_read_the_plan_cannot_trust_is_refused(self, row, says):
        with pytest.raises(NK.NameKeyError, match=re.escape(says)):
            NK.plan_keys([], [row])

    def test_the_plan_never_computes_a_key_in_python(self):
        """No call of normalize_name, no unicodedata, nothing from pipeline.utils.text."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(NK))
        calls = {
            node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert "normalize_name" not in calls and "normalize" not in calls
        modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert "unicodedata" not in modules
        assert "pipeline.utils.text" not in modules

    def test_the_read_computes_the_key_with_the_one_expression(self):
        for sql in (NK.SITES_SQL, NK.NAMES_SQL):
            assert site_key_sql("n.name") in sql or site_key_sql("u.name") in sql
            assert "u.source_id IN ('ancient_nerds', 'lyra', 'ancient_nerds_community')" in sql
        assert "IS DISTINCT FROM" in NK.NAMES_SQL and "collides_with" in NK.NAMES_SQL


class TestTheCommand:
    def test_the_lane_is_stamped_with_its_directory_s_date(self, tmp_path):
        lane = NK.chunk_lane(tmp_path / "name-key-2026-09-25")
        assert (lane.name, lane.test_id, lane.stamp) == (
            "name-key",
            "P6/name-key",
            "name-key-2026-09-25",
        )
        with pytest.raises(NK.NameKeyError):
            NK.chunk_lane(tmp_path / "keys")

    def test_the_command_writes_the_chunk_and_the_read(self, tmp_path, monkeypatch):
        read: dict[str, Any] = {
            "read_at": "2026-09-25T12:00:00Z",
            "sites": [],
            "names": [_name_row()],
        }
        monkeypatch.setattr(NK, "read_production", lambda: read)
        out = tmp_path / "name-key-2026-09-25"
        assert NK.main(["chunk", "--out", str(out)]) == 0
        chunk = C.check_delivered(out / "chunk-001")
        assert [c.row_key for c in chunk.changes] == ["3617031"]
        assert json.loads((out / "READ.json").read_text(encoding="utf-8")) == read

    def test_nothing_divergent_plans_nothing_and_writes_nothing(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            NK, "read_production", lambda: {"read_at": "x", "sites": [], "names": []}
        )
        out = tmp_path / "name-key-2026-09-25"
        assert NK.main(["chunk", "--out", str(out)]) == 1
        assert "nothing to plan" in capsys.readouterr().err
        assert not out.exists()


# --------------------------------------------------- the eleven Lyra alias keys (HUMAN_ONLY Nr. 9)
#: The eleven rows as production held them on 2026-09-26 (read-only): the alias and its stored key.
#: Postgres's key of each is the lower-cased alias itself. The Hangul keys print alike but are the
#: decomposed jamo Python's NFKD left behind (`name_normalized = normalize(name, NFD)` read true);
#: the Japanese ones lost a (han)dakuten, Cerutti's a parenthesised part.
LYRA_READ = [
    (3616643, "848cbe6d-136e-4c15-819c-b017b290a909", "북센티널섬", "NFD"),
    (3616936, "6eb8b50f-b9dc-4069-8135-efeb491b9e1b", "ドッガーランド", "トッカーラント"),
    (3616938, "6eb8b50f-b9dc-4069-8135-efeb491b9e1b", "도거랜드", "NFD"),
    (3617031, YAP, "ヤップ島", "ヤッフ島"),
    (3617034, YAP, "야프 제도", "NFD"),
    (3617035, YAP, "야프섬", "NFD"),
    (3617036, YAP, "야프제도", "NFD"),
    (3617283, CERUTTI, "Cerutti Mastodon (CM) site", "cerutti mastodon  site"),
    (3617346, "85dbd052-9423-4404-a059-3f69cb7bb82d", "ループクンド湖", "ルーフクント湖"),
    (3617349, "dab28cc0-615f-4779-9fef-882586a6ab6f", "チャーンウッドの森", "チャーンウットの森"),
    (
        3617350,
        "dab28cc0-615f-4779-9fef-882586a6ab6f",
        "チャーンウッドフォレスト",
        "チャーンウットフォレスト",
    ),
]


def _lyra_rows() -> list[dict[str, Any]]:
    import unicodedata

    return [
        _name_row(
            row_id,
            site,
            name,
            unicodedata.normalize("NFD", name) if stored == "NFD" else stored,
            name.lower(),
            source_id="lyra",
        )
        for row_id, site, name, stored in LYRA_READ
    ]


class TestTheLyraAliasKeys:
    def test_the_decision_names_eleven_rows_on_six_sites(self):
        assert len(NK.LYRA_ALIAS_ROWS) == len(set(NK.LYRA_ALIAS_ROWS)) == 11
        assert sorted(NK.LYRA_ALIAS_ROWS) == [row for row, *_ in LYRA_READ]
        assert len({site for _, site, *_ in LYRA_READ}) == 6

    def test_a_lyra_directory_names_the_lyra_lane(self, tmp_path):
        lane = NK.chunk_lane(tmp_path / "name-key-lyra-2026-09-26")
        assert (lane.name, lane.test_id, lane.stamp, lane.source) == (
            "name-key-lyra",
            "P6/name-key-lyra",
            "name-key-lyra-2026-09-26",
            "lyra",
        )
        assert NK.chunk_lane(tmp_path / "name-key-2026-09-26").source == "ancient_nerds"

    def test_the_lyra_lane_plans_exactly_the_decided_rows(self):
        rows = _lyra_rows()
        changes, listed = NK.plan_keys([], rows, source="lyra")
        assert listed == []
        assert [int(c.row_key) for c in changes] == sorted(NK.LYRA_ALIAS_ROWS)
        for change, row in zip(changes, rows, strict=True):
            assert (change.old_value, change.new_value) == (row["name_normalized"], row["sql_key"])

    def test_the_lyra_lane_lists_every_other_row(self):
        undecided = _name_row(3700000, YAP, "Yap", "yap island", "yap", source_id="lyra")
        curated = _name_row()
        site = _site_row(source_id="lyra")
        changes, listed = NK.plan_keys([site], [undecided, curated], source="lyra")
        assert changes == []
        assert [(e["row"], e["reason"]) for e in listed] == [
            (CERUTTI, "lyra-row-not-decided"),
            ("3700000", "lyra-row-not-decided"),
            ("3617031", "source-ancient_nerds-not-the-writer-s"),
        ]

    def test_the_curated_lane_still_lists_the_lyra_rows(self):
        changes, listed = NK.plan_keys([], _lyra_rows())
        assert changes == [] and len(listed) == 11
        assert {e["reason"] for e in listed} == {"source-lyra-not-the-writer-s"}

    def test_the_command_writes_one_chunk_of_eleven_keys_whose_guard_1_asks_for_lyra(
        self, tmp_path, monkeypatch
    ):
        read = {"read_at": "2026-09-26T01:00:00Z", "sites": [], "names": _lyra_rows()}
        monkeypatch.setattr(NK, "read_production", lambda: read)
        out = tmp_path / "name-key-lyra-2026-09-26"
        assert NK.main(["chunk", "--out", str(out)]) == 0
        chunk = C.check_delivered(out / "chunk-001")
        assert chunk.lane.source == "lyra" and chunk.run_stamp == "name-key-lyra-2026-09-26-001"
        assert len(chunk.changes) == 11 and len(chunk.sites) == 6
        head = json.loads((out / "chunk-001" / "CHUNK.json").read_text(encoding="utf-8"))
        assert head["source"] == "lyra"
        apply_sql = (out / "chunk-001" / "APPLY.sql").read_text(encoding="utf-8")
        assert "WHERE u.id IS NULL OR u.source_id <> 'lyra';" in apply_sql
        assert "planned site(s) are not % sites', bad, 'lyra';" in apply_sql
        assert "-- scope source_id = 'lyra';" in apply_sql
        assert "'ancient_nerds'" not in apply_sql
        C.lint_statement(apply_sql)


class TestTheWriterSource:
    def test_a_curated_chunk_names_no_source_and_renders_as_before(self):
        (chunk,) = C.chunk_changes(LANE, [_name_change()])
        assert "source" not in C.header(chunk)
        sql = C.render_statement(chunk)
        assert "WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';" in sql

    def test_only_the_key_only_sources_can_be_named(self):
        with pytest.raises(C.ChunkError, match="alias keys of"):
            C.Lane("x", "P6/x", "x-2026-09-26", "authoritative", "x", "geonames")

    @pytest.mark.parametrize(
        "change",
        [
            _site_change(),
            C.Change("wiki_images", "is_hero", "101", YAP, "false", "true", "H1", "w", EV),
        ],
    )
    def test_a_lyra_lane_writes_alias_keys_and_nothing_else(self, change):
        lane = C.Lane("k", "P6/k", "k-2026-09-26", "authoritative", "k", "lyra")
        with pytest.raises(C.ChunkError, match="alias keys only"):
            C.chunk_changes(lane, [change])

    def test_a_delivered_lyra_chunk_that_writes_another_column_is_refused(self, tmp_path):
        lane = C.Lane("k", "P6/k", "k-2026-09-26", "authoritative", "k", "lyra")
        (chunk,) = C.chunk_changes(lane, [_name_change()])
        directory = C.emit_chunk(tmp_path, chunk)
        assert C.check_delivered(directory).lane == lane
        plan = directory / "PLAN.jsonl"
        row = json.loads(plan.read_text(encoding="utf-8"))
        row.update(table="unified_sites", column="name_normalized", row_key=YAP)
        row["change_key"] = C.change_key(lane, C.Change(**{k: row[k] for k in (
            "table", "column", "row_key", "site_id", "old_value", "new_value", "rule", "reason",
            "evidence")}))  # fmt: skip
        plan.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        with pytest.raises(C.ChunkError, match="alias keys only"):
            C.load_chunk(directory)
