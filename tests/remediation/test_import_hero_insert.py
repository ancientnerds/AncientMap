# SPDX-License-Identifier: AGPL-3.0-only
"""The INSERT lane: a row for the picture the owner linked, and the guards that keep it one row.

The shared writer writes conditional UPDATEs through `apply_remediation_change()` and its lint
refuses an INSERT, so the `no_target_row` sites could not be given the owner's picture. This lane
creates the row and its journal rows in one transaction instead - no migration, because the journal
has the columns for it - and undoes it with a DELETE named by the triple it wrote.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from import_hero import insert as IN  # noqa: E402
from served_image import state as ST  # noqa: E402

SITE_A = "11111111-1111-1111-1111-111111111111"
SITE_B = "22222222-2222-2222-2222-222222222222"
SITE_C = "33333333-3333-3333-3333-333333333333"

FILENAME = "Area archeologica di Herakleia e Siris - 3.webp"
ORIGINAL = (
    "https://upload.wikimedia.org/wikipedia/commons/1/1e/"
    "Area_archeologica_di_Herakleia_e_Siris_-_3.jpg"
)
COMMONS_PAGE = (
    "https://commons.wikimedia.org/wiki/File:Area_archeologica_di_Herakleia_e_Siris_-_3.jpg"
)

VALUES = {
    "filename": FILENAME,
    "original_url": ORIGINAL,
    "commons_page_url": COMMONS_PAGE,
    "title": "Area archeologica di Herakleia e Siris",
    "author": "Alessandro Antonelli",
    "author_url": "https://commons.wikimedia.org/wiki/User:Una_giornata_uggiosa_%2794",
    "license": "CC BY 3.0",
    "license_url": "https://creativecommons.org/licenses/by/3.0",
    "width": "1600",
    "height": "1200",
    "file_size_bytes": "548938",
}


def _values_of(sql: str) -> list[str]:
    """The values of the first planned row, split at the commas that separate them.

    A URL, a file name and the JSON evidence all carry commas of their own, so the split has to
    know about quotes: counting commas alone read 24 values where the column list names 19.
    """
    body = sql.split(") VALUES\n", 1)[1].splitlines()[0].strip().rstrip(";")
    assert body.startswith("(") and body.endswith(")"), body[:80]
    body = body[1:-1]
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0
    while index < len(body):
        char = body[index]
        if in_string:
            if char == "'":
                if body[index + 1 : index + 2] == "'":  # an escaped quote
                    current.append("''")
                    index += 2
                    continue
                in_string = False
            current.append(char)
        elif char == "'":
            in_string = True
            current.append(char)
        elif char == ",":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current).strip())
    return parts


def _row(
    row_id: int, site_id: str, *, hero: bool = False, excluded: bool = False
) -> dict[str, Any]:
    return {
        "id": row_id,
        "site_id": site_id,
        "filename": "hero.webp",
        "original_url": f"https://upload.wikimedia.org/wikipedia/commons/9/99/{row_id}.jpg",
        "commons_page_url": None,
        "title": None,
        "author": None,
        "author_url": None,
        "license": None,
        "license_url": None,
        "width": 800,
        "height": 600,
        "file_size_bytes": 12_345,
        "is_hero": hero,
        "is_excluded": excluded,
    }


def _site(site_id: str, thumbnail: str | None) -> dict[str, Any]:
    return {
        "id": site_id,
        "name": "Herakleia Siris",
        "source_url": "https://en.wikipedia.org/wiki/Herakleia_Siris",
        "thumbnail_url": thumbnail,
    }


def _state(*, rows: dict[str, list[dict[str, Any]]], thumbs: dict[str, str | None]) -> ST.State:
    return ST.State(
        sites={sid: _site(sid, thumbs.get(sid)) for sid in (SITE_A, SITE_B, SITE_C)},
        rows=rows,
        retired=(),
        read_at="2026-10-06T00:00:00Z",
        sha256="0" * 64,
    )


def _refusal(site_id: str, reason: str = "no_target_row") -> dict[str, Any]:
    return {"site_id": site_id, "reason": reason, "detail": ""}


def _fetched(*site_ids: str) -> dict[str, dict[str, str]]:
    return {sid: dict(VALUES) for sid in site_ids}


class TestThePlanOfTheInsertWave:
    def test_a_no_target_row_site_with_a_fetched_file_becomes_one_insert(self) -> None:
        state = _state(rows={SITE_A: [_row(7, SITE_A, hero=True)]}, thumbs={SITE_A: "/x/hero.webp"})
        planned = IN.plan(state, [_refusal(SITE_A)], fetched=_fetched(SITE_A))
        assert len(planned.inserts) == 1 and not planned.refusals
        row = planned.inserts[0]
        assert row.site_id == SITE_A
        assert [row.values[c] for c in IN.INSERT_COLUMNS] == [VALUES[c] for c in IN.INSERT_COLUMNS]
        # the row that gives up the flag, and the thumbnail that follows the new row
        assert row.demoted_id == "7"
        assert row.new_thumbnail == f"/data/images/wiki/{SITE_A[:8]}/{FILENAME}"
        assert row.thumbnail_changes is True
        # 14 written columns + demotion + thumbnail
        assert row.journal_rows == 16
        assert len(IN.JOURNAL_COLUMNS) == 14

    def test_a_site_with_no_row_at_all_stays_with_the_owners_decision(self) -> None:
        """2026-10-05 (18:32): a site with only a `thumbnail_url` gets no gallery image made up."""
        state = _state(rows={SITE_A: []}, thumbs={SITE_A: "/x/whatever.webp"})
        planned = IN.plan(state, [_refusal(SITE_A)], fetched=_fetched(SITE_A))
        assert not planned.inserts
        assert [r.reason for r in planned.refusals] == ["no_row_at_all"]
        assert "2026-10-05" in planned.refusals[0].detail

    def test_a_site_that_shows_nothing_at_all_gets_its_first_row(self) -> None:
        """The owner's decision of 2026-10-06 extends the rule: its reason - a site keeps the
        picture it already shows - holds only where it shows one. Measured on the read `b053ac17`
        (2026-10-06, 4,900 shown sites), 1,144 sites have neither a row nor a `thumbnail_url`, so
        they show nothing at all; for those the first row is what the page needs.

        The row is journalled with the refusal's own words, never with the 2025 import's: nothing
        in this wave came from the import, and a journal that says otherwise is not an audit."""
        state = _state(rows={SITE_A: []}, thumbs={SITE_A: None})
        refusal = {
            **_refusal(SITE_A),
            "source": "a model judged this file 'depicts' and the site showed nothing at all",
            "evidence_source": "the candidate search's confirmed verdict",
        }
        planned = IN.plan(state, [refusal], fetched=_fetched(SITE_A))
        assert not planned.refusals
        assert len(planned.inserts) == 1
        row = planned.inserts[0]
        assert row.reason == refusal["source"]
        assert row.evidence[0]["source"] == refusal["evidence_source"]
        # nothing to demote, and the thumbnail the page had (none) is replaced by the new row's file
        assert row.demoted_id is None
        assert row.old_thumbnail is None
        assert row.new_thumbnail == f"/data/images/wiki/{SITE_A[:8]}/{FILENAME}"
        assert row.thumbnail_changes is True
        # 14 written columns, no demotion, the thumbnail change
        assert row.journal_rows == 15

    def test_a_site_whose_fetch_was_refused_is_refused_by_name(self) -> None:
        """A row cannot name a file that is not on disk."""
        state = _state(rows={SITE_A: [_row(7, SITE_A)]}, thumbs={SITE_A: None})
        planned = IN.plan(state, [_refusal(SITE_A)], fetched={})
        assert not planned.inserts
        assert [r.reason for r in planned.refusals] == ["not_fetched"]

    def test_a_site_that_has_no_hero_row_yet_needs_no_demotion(self) -> None:
        state = _state(rows={SITE_A: [_row(7, SITE_A)]}, thumbs={SITE_A: "/x/hero.webp"})
        row = IN.plan(state, [_refusal(SITE_A)], fetched=_fetched(SITE_A)).inserts[0]
        assert row.demoted_id is None
        assert row.journal_rows == 15

    def test_only_no_target_row_refusals_are_candidates(self) -> None:
        state = _state(rows={SITE_A: [_row(7, SITE_A)]}, thumbs={SITE_A: None})
        planned = IN.plan(
            state, [_refusal(SITE_A, "local_file_too_small")], fetched=_fetched(SITE_A)
        )
        assert not planned.inserts and not planned.refusals

    def test_an_empty_plan_is_refused_by_name(self, tmp_path: Path) -> None:
        empty = IN.InsertPlan(inserts=[])
        with pytest.raises(IN.ImportHeroError, match="no row"):
            IN.write_chunks(empty, tmp_path / "run")
        with pytest.raises(IN.ImportHeroError, match="per_chunk"):
            IN.chunks_of(
                IN.InsertPlan(
                    inserts=[
                        IN.plan(
                            _state(rows={SITE_A: [_row(1, SITE_A)]}, thumbs={SITE_A: None}),
                            [_refusal(SITE_A)],
                            fetched=_fetched(SITE_A),
                        ).inserts[0]
                    ]
                ),
                "run",
                per_chunk=0,
            )


class TestSeedingAWaveFromAnImportRun:
    """`fetch --target insert` reads the claims and the refusals out of the run directory, and only the
    2025 import wrote them - into its own run directories, over its own target list. A wave over the
    sites that show nothing although the import links a picture therefore has nothing to read until
    this copies those two records out of the run that refused them."""

    def _source(self, tmp_path: Path, **kwargs: Any) -> Path:
        refusals = kwargs.pop(
            "refusals",
            [{"site_id": SITE_A, "reason": "no_target_row", "detail": "its rows hold no file"}],
        )
        claims = kwargs.pop("claims", {SITE_A: {"image": ORIGINAL, "import_title": "Herakleia"}})
        source = tmp_path / "import-hero-2026-10-06-009"
        source.mkdir(parents=True, exist_ok=True)
        (source / "IMPORT_CLAIMS.json").write_text(
            json.dumps(claims, ensure_ascii=False), encoding="utf-8"
        )
        (source / "IMPORT_HERO_REFUSALS.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in refusals),
            encoding="utf-8",
            newline="\n",
        )
        return source

    def test_a_no_target_row_site_gets_the_claims_claim_and_a_refusal(self, tmp_path: Path) -> None:
        source = self._source(tmp_path)
        run = tmp_path / "insert-2026-10-07-009"
        out = IN.seed_from_import_run(source, run, [SITE_A])

        assert out["sites_seeded"] == 1 and not out["refused_sites"]
        claims = json.loads((run / "IMPORT_CLAIMS.json").read_text(encoding="utf-8"))
        assert claims[SITE_A]["image"] == ORIGINAL
        refusals = [
            json.loads(line)
            for line in (run / "IMPORT_HERO_REFUSALS.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        assert [r["reason"] for r in refusals] == ["no_target_row"]
        # The row this produces is journalled with this refusal's own words, and they have to name
        # the run the claim came out of - the wave did not ask for this file, the import did.
        assert "no_target_row" == refusals[0]["reason"]
        assert source.name in refusals[0]["source"]
        assert source.name in refusals[0]["evidence_source"]

    def test_a_site_the_import_refused_for_another_reason_is_refused_by_name(
        self, tmp_path: Path
    ) -> None:
        """Seeding its claim would turn `local_file_too_small` into a written row."""
        source = self._source(
            tmp_path,
            refusals=[{"site_id": SITE_A, "reason": "local_file_too_small", "detail": "640x480"}],
        )
        out = IN.seed_from_import_run(source, tmp_path / "run", [SITE_A])

        assert out["sites_seeded"] == 0
        assert [r["reason"] for r in out["refused_sites"]] == ["not_a_candidate"]
        assert "local_file_too_small" in out["refused_sites"][0]["detail"]

    def test_a_site_without_a_claim_in_the_source_run_is_refused_by_name(
        self, tmp_path: Path
    ) -> None:
        source = self._source(tmp_path, refusals=[])
        out = IN.seed_from_import_run(source, tmp_path / "run", [SITE_B])

        assert out["sites_seeded"] == 0
        assert [r["reason"] for r in out["refused_sites"]] == ["no_import_claim"]

    def test_a_second_claim_for_one_site_is_refused_and_never_overwrites(
        self, tmp_path: Path
    ) -> None:
        other = "https://upload.wikimedia.org/wikipedia/commons/9/9a/Other.jpg"
        source = self._source(
            tmp_path,
            claims={SITE_A: {"image": other, "import_title": "x"}, SITE_C: {"image": ORIGINAL}},
            refusals=[
                {"site_id": SITE_A, "reason": "no_target_row", "detail": ""},
                {"site_id": SITE_C, "reason": "no_target_row", "detail": ""},
            ],
        )
        run = tmp_path / "run"
        run.mkdir()
        (run / "IMPORT_CLAIMS.json").write_text(
            json.dumps({SITE_A: {"image": ORIGINAL}}), encoding="utf-8"
        )
        out = IN.seed_from_import_run(source, run, [SITE_A, SITE_C])

        assert [r["reason"] for r in out["refused_sites"]] == ["claim_conflict"]
        assert out["sites_seeded"] == 1
        claims = json.loads((run / "IMPORT_CLAIMS.json").read_text(encoding="utf-8"))
        assert claims[SITE_A]["image"] == ORIGINAL, "the first claim stands"
        assert claims[SITE_C]["image"] == ORIGINAL

    def test_a_run_without_a_claims_file_is_refused_by_name(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(IN.ImportHeroError, match="claims"):
            IN.seed_from_import_run(empty, tmp_path / "run", [SITE_A])


class TestTheStatement:
    def _sql(self, tmp_path: Path, **kwargs: Any) -> str:
        state = _state(rows={SITE_A: [_row(7, SITE_A, hero=True)]}, thumbs={SITE_A: "/x/hero.webp"})
        planned = IN.plan(state, [_refusal(SITE_A)], fetched=_fetched(SITE_A))
        chunks = IN.write_chunks(planned, tmp_path / "run", per_chunk=50)
        return (tmp_path / "run" / f"chunk-{chunks[0].number:03d}" / "APPLY.sql").read_text(
            encoding="utf-8"
        )

    def test_the_row_and_its_journal_are_written_inside_one_transaction(
        self, tmp_path: Path
    ) -> None:
        sql = self._sql(tmp_path)
        assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
        assert sql.index("BEGIN;") < sql.index("INSERT INTO wiki_images")
        assert sql.index("remediation_change_log") < sql.index("COMMIT;")

    def test_the_journal_names_the_new_row_by_the_id_the_insert_returned(
        self, tmp_path: Path
    ) -> None:
        sql = self._sql(tmp_path)
        assert "RETURNING id INTO new_id" in sql
        assert "new_id::text" in sql
        # one journal row per written column, read back from the row the INSERT created - and the
        # value is the column, never the text of a name (a journal of `r.filename` passes every
        # count and means nothing)
        for column in IN.JOURNAL_COLUMNS:
            assert f"w.{column}::text" in sql
            assert f"'{column}', 'w." not in sql

    def test_the_columns_wiki_images_demands_are_written_and_journalled(
        self, tmp_path: Path
    ) -> None:
        # measured 2026-10-06: is_lead, sort_order and source_type are NOT NULL without a default,
        # so an INSERT that leaves them out does not land
        sql = self._sql(tmp_path)
        assert "is_lead, sort_order, source_type, is_hero, is_excluded" in sql
        assert "COALESCE(MAX(w2.sort_order), -1) + 1" in sql
        assert f"'{IN.SOURCE_TYPE}', true, false" in sql

    def test_no_column_is_declared_or_written_twice(self, tmp_path: Path) -> None:
        # `width` and `file_size_bytes` are both in INSERT_COLUMNS and needed as numbers: naming
        # them once from the tuple and once by hand made the statement fail with `column "width"
        # specified more than once` before it wrote anything (measured 2026-10-06)
        sql = self._sql(tmp_path)
        create = sql.split("CREATE TEMP TABLE _ih_insert (", 1)[1].split(") ON COMMIT DROP", 1)[0]
        body = [line for line in create.splitlines() if line.strip()]
        declared = [line.split()[0] for line in body]
        # every declaration but the last ends in a comma: without them the rehearsal answered
        # `syntax error at or near "site_id"` (measured 2026-10-06)
        assert all(line.rstrip().endswith(",") for line in body[:-1])
        assert len(declared) == len(set(declared)) == 2 + len(IN.INSERT_COLUMNS) + 6
        plan_list = sql.split("INSERT INTO _ih_insert (", 1)[1].split(") VALUES", 1)[0]
        named = [name.strip() for name in plan_list.split(",")]
        assert named == declared
        values = _values_of(sql)
        assert len(values) == len(named)
        assert values[:2] == ["1", f"'{SITE_A}'::uuid"]
        # the numbers are bare, the text is quoted
        assert values[named.index("width")] == "1600"
        assert values[named.index("filename")] == f"'{FILENAME}'"

    def test_the_numbers_are_written_as_numbers(self, tmp_path: Path) -> None:
        sql = self._sql(tmp_path)
        assert "width             INTEGER NOT NULL" in sql
        assert "file_size_bytes   INTEGER NOT NULL" in sql
        # a quoted '1600' would compare as text in guard 3 and against the row in invariant 1
        values = _values_of(sql)
        assert not [value for value in values if value.startswith("'1600'")]
        assert {"1600", "1200", "548938"} <= set(values)

    def test_each_chunk_carries_its_own_journal_stamp(self) -> None:
        state = _state(rows={SITE_A: [_row(7, SITE_A, hero=True)]}, thumbs={SITE_A: "/x/hero.webp"})
        planned = IN.plan(state, [_refusal(SITE_A)], fetched=_fetched(SITE_A))
        chunks = IN.chunks_of(IN.InsertPlan(inserts=planned.inserts * 2), "run-x", per_chunk=1)
        stamps = [chunk.run_stamp for chunk in chunks]
        assert stamps == ["run-x-001", "run-x-002"]
        assert chunks[0].rollback_stamp == "run-x-001-rollback"

    def test_the_statement_carries_the_five_guards(self, tmp_path: Path) -> None:
        sql = self._sql(tmp_path)
        assert "are not ancient_nerds sites" in sql
        assert "already holds this file" in sql
        assert "under the %x% this lane serves" in sql
        assert "the row that held the flag for site" in sql
        assert "the thumbnail of site" in sql

    def test_the_invariants_are_checked_before_the_commit(self, tmp_path: Path) -> None:
        sql = self._sql(tmp_path)
        block = sql.split("DO $$", 1)[1].split("COMMIT;", 1)[0]
        assert block.count("RAISE EXCEPTION") >= 8
        assert "more than one live hero row" in block
        assert "do not have exactly their planned journal rows" in block
        # the loop variable is `r`, so no query in the same block may alias a table `r`: Postgres
        # refuses a reference that could mean either (measured 2026-10-06, rehearsal of chunk-001)
        assert "r    RECORD" in block
        for alias in ("FROM _ih_insert r", "JOIN _ih_insert r "):
            assert alias not in sql

    def test_the_statement_pins_the_plan_it_was_rendered_from(self, tmp_path: Path) -> None:
        sql = self._sql(tmp_path)
        digest = IN.digest_of(IN.InsertPlan(inserts=[]).inserts) if False else None
        assert "pin:" in sql
        header = json.loads(
            (tmp_path / "run" / "chunk-001" / "CHUNK.json").read_text(encoding="utf-8")
        )
        assert f"pin: {header['digest']}" in sql
        assert digest is None


class TestTheReversal:
    def _rollback(self, tmp_path: Path) -> str:
        state = _state(rows={SITE_A: [_row(7, SITE_A, hero=True)]}, thumbs={SITE_A: "/x/hero.webp"})
        planned = IN.plan(state, [_refusal(SITE_A)], fetched=_fetched(SITE_A))
        IN.write_chunks(planned, tmp_path / "run", per_chunk=50)
        return (tmp_path / "run" / "chunk-001" / "ROLLBACK.sql").read_text(encoding="utf-8")

    def test_the_reversal_deletes_the_row_by_the_triple_this_lane_wrote(
        self, tmp_path: Path
    ) -> None:
        sql = self._rollback(tmp_path)
        assert "file_size_bytes = r.file_size_bytes" in sql
        assert "w.original_url = r.original_url" in sql
        # and it puts back what it took
        assert "SET is_hero = true" in sql
        assert "SET thumbnail_url = r.old_thumbnail" in sql
        assert "DELETE FROM remediation_change_log" in sql

    def test_the_reversal_never_deletes_a_site(self, tmp_path: Path) -> None:
        sql = self._rollback(tmp_path)
        assert "DELETE FROM unified_sites" not in sql
        assert "TRUNCATE" not in sql


class TestTheLint:
    def test_it_refuses_a_statement_that_creates_no_row(self) -> None:
        with pytest.raises(IN.ImportHeroError, match="creates no wiki_images row"):
            IN.lint_statement("BEGIN;\nINSERT INTO remediation_change_log SELECT 1;\nCOMMIT;\n")

    def test_an_apply_may_not_delete_and_a_rollback_may_not_create(self) -> None:
        apply_with_delete = (
            "BEGIN;\nINSERT INTO wiki_images (filename) VALUES ('a');\n"
            "INSERT INTO remediation_change_log (run_stamp) VALUES ('x');\n"
            "DELETE FROM wiki_images WHERE is_hero;\nCOMMIT;\n"
        )
        with pytest.raises(IN.ImportHeroError, match="creates rows and deletes none"):
            IN.lint_statement(apply_with_delete, kind="apply")
        rollback_with_insert = (
            "BEGIN;\nINSERT INTO wiki_images (filename) VALUES ('a');\n"
            "DELETE FROM wiki_images WHERE file_size_bytes = r.file_size_bytes;\n"
            "DELETE FROM remediation_change_log WHERE run_stamp = 'x';\nCOMMIT;\n"
        )
        with pytest.raises(IN.ImportHeroError, match="creates no row"):
            IN.lint_statement(rollback_with_insert, kind="rollback")

    def test_it_refuses_a_journal_written_after_the_commit(self) -> None:
        sql = (
            "BEGIN;\nINSERT INTO wiki_images (filename) VALUES ('a');\nCOMMIT;\n"
            "INSERT INTO remediation_change_log (run_stamp) VALUES ('x');\n"
        )
        with pytest.raises(IN.ImportHeroError, match="before the COMMIT"):
            IN.lint_statement(sql)

    def test_it_refuses_a_delete_that_does_not_name_the_row(self) -> None:
        sql = (
            "BEGIN;\nDELETE FROM wiki_images WHERE is_hero;\nCOMMIT;\n"
            "DELETE FROM remediation_change_log WHERE run_stamp = 'x';\n"
        )
        with pytest.raises(IN.ImportHeroError, match="triple this lane wrote"):
            IN.lint_statement(sql, kind="rollback")

    def test_it_refuses_a_statement_this_lane_may_not_make(self) -> None:
        for forbidden in ("TRUNCATE wiki_images", "DROP TABLE wiki_images"):
            sql = (
                "BEGIN;\nINSERT INTO wiki_images (filename) VALUES ('a');\n"
                "INSERT INTO remediation_change_log (run_stamp) VALUES ('x');\n"
                f"{forbidden};\nCOMMIT;\n"
            )
            with pytest.raises(IN.ImportHeroError):
                IN.lint_statement(sql)


class TestTheAcceptance:
    def test_a_row_that_stands_answers_all_three_questions(self) -> None:
        row = IN.Insert.from_json(
            json.loads(
                json.dumps(
                    {
                        "site_id": SITE_A,
                        "values": VALUES,
                        "demoted_id": "7",
                        "old_thumbnail": "/x/hero.webp",
                        "new_thumbnail": f"/data/images/wiki/{SITE_A[:8]}/{FILENAME}",
                        "change_key": "import-hero/insert:x",
                        "reason": "",
                        "evidence": [],
                    }
                )
            )
        )
        inserted = {**VALUES, "id": 99, "site_id": SITE_A, "is_hero": True, "is_excluded": False}
        state = _state(rows={SITE_A: [inserted]}, thumbs={SITE_A: row.new_thumbnail})
        result = IN.check(state, [row])
        assert result["ok"] is True
        assert (result["served_the_import"], result["thumbnail_follows"], result["one_hero"]) == (
            1,
            1,
            1,
        )

    def test_a_stale_thumbnail_is_reported_by_name(self) -> None:
        """The failure the hero wave ran into on 2026-10-06, pinned for this lane."""
        row = IN.Insert.from_json(
            {
                "site_id": SITE_A,
                "values": VALUES,
                "demoted_id": "7",
                "old_thumbnail": "/x/hero.webp",
                "new_thumbnail": f"/data/images/wiki/{SITE_A[:8]}/{FILENAME}",
                "change_key": "k",
                "reason": "",
                "evidence": [],
            }
        )
        inserted = {**VALUES, "id": 99, "site_id": SITE_A, "is_hero": True, "is_excluded": False}
        state = _state(rows={SITE_A: [inserted]}, thumbs={SITE_A: "/x/hero.webp"})
        result = IN.check(state, [row])
        assert result["ok"] is False
        assert any("does not name the served row" in p for p in result["problems"])

    def test_two_live_hero_rows_are_reported(self) -> None:
        row = IN.Insert.from_json(
            {
                "site_id": SITE_A,
                "values": VALUES,
                "demoted_id": None,
                "old_thumbnail": None,
                "new_thumbnail": f"/data/images/wiki/{SITE_A[:8]}/{FILENAME}",
                "change_key": "k",
                "reason": "",
                "evidence": [],
            }
        )
        inserted = {**VALUES, "id": 99, "site_id": SITE_A, "is_hero": True, "is_excluded": False}
        state = _state(
            rows={SITE_A: [inserted, _row(7, SITE_A, hero=True)]},
            thumbs={SITE_A: row.new_thumbnail},
        )
        result = IN.check(state, [row])
        assert result["ok"] is False
        assert any("live hero row" in p for p in result["problems"])
