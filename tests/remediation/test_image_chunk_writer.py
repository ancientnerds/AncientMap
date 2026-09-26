"""The image lanes' shared chunk writer (`scripts/remediation/gallery_audit/chunk_writer.py`), and
the two pieces it takes from the hero repair (`scripts/remediation/hero_repair/apply.py`): the
one-hero invariant, extracted into a function, and the transport, now `prod_write`'s.

Offline: no database, no network. Production is a `FakePsql` that **parses** what it is sent - the
plan rows of a statement, the reads the writer makes - applies a statement the way
`apply_remediation_change()` does (a row that no longer holds its planned old value aborts the whole
transaction, psql exit 3) and refuses any SQL it does not recognise. The read-backs are answered
from a small model of the rows (heroes, exclusions, kinds, sources): every metric the invariant read
names is computed from the predicates its SQL states, and a predicate the fake cannot read is
refused; the journal read returns exactly the columns it selects. The guards of the `DO` block are
not re-implemented here - a fake that simulated them would test itself - so each one is asserted,
condition line for condition line, on the rendered text of both statements.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import chunk_writer as C  # noqa: E402
from hero_repair import apply as HA  # noqa: E402
from hero_repair.plan import ChangeRecord  # noqa: E402

S1 = "00000000-0000-4000-8000-000000000001"
S2 = "00000000-0000-4000-8000-000000000002"
LANE = C.Lane("img-test", "T09/attribution", "img-test-2026-09-23", "authoritative", "img test")
EV = [{"source": "commons:File page", "revid": 7, "sha256": "ab" * 32}]


def _change(key: str, column: str = "author", old=None, new="Jane", site=S1, table="wiki_images"):
    return C.Change(table, column, key, site, old, new, "A1", f"{column} of {key}", EV)


def _chunk(*changes: C.Change, may_empty=()) -> C.Chunk:
    (chunk,) = C.chunk_changes(LANE, list(changes), may_empty=may_empty)
    return chunk


# --------------------------------------------------------------------------------------------
# a psql that parses what it is given
# --------------------------------------------------------------------------------------------


def _literals(tuple_text: str) -> list[str | None]:
    """The fields of one rendered VALUES tuple, SQL-unquoted; refuses what it cannot read."""
    fields: list[str | None] = []
    i, text = 0, tuple_text
    while i < len(text):
        if text[i] == "'":
            j, buf = i + 1, []
            while True:
                if text[j] == "'" and text[j + 1 : j + 2] == "'":
                    buf.append("'")
                    j += 2
                elif text[j] == "'":
                    break
                else:
                    buf.append(text[j])
                    j += 1
            fields.append("".join(buf))
            i = j + 1
            i = text.index(",", i) + 1 if "," in text[i:] else len(text)
        else:
            end = text.find(",", i)
            bare = (text[i:] if end == -1 else text[i:end]).strip()
            fields.append(None if bare == "NULL" else bare)
            i = len(text) if end == -1 else end + 1
        while i < len(text) and text[i] == " ":
            i += 1
    return fields


PLAN_ROW = re.compile(r"^    \((\d+, '.*)\)(?:,|;)$", re.M)
WRITER_CALL = re.compile(
    r"r\.old_value, r\.new_value,\n\s+'([^']*)', '([^']*)', r\.change_key, '([^']*)', "
)


JOURNAL_COLUMNS = (
    "table_name",
    "column_name",
    "row_pk",
    "old_value",
    "new_value",
    "change_key",
    "test_id",
    "confidence",
)
AFTER_METRIC = re.compile(r"\(SELECT count\(\*\) FROM (.+?)\)::int AS (\w+)", re.S)
JOURNAL_READ = re.compile(
    r"SELECT row_to_json\(t\) FROM \(SELECT ([\w, ]+) FROM remediation_change_log"
    r" WHERE run_stamp = '([^']*)' ORDER BY id\) t;"
)


def _uuids(listed: str) -> list[str]:
    """The sites of a rendered `IN (...)` list; refuses anything but `'<uuid>'::uuid` items."""
    items = [item.strip() for item in listed.split(",")]
    got = [re.fullmatch(r"'([0-9a-f-]{36})'::uuid", item) for item in items]
    assert all(got), f"the fake cannot read this site list: {listed}"
    return [m.group(1) for m in got if m]


class FakePsql:
    """Answers `persist_verdicts.run_psql(sql, rows=..., check=...)` like production would."""

    def __init__(
        self,
        data: dict[tuple[str, str, str], str | None],
        site_of: dict[str, str],
        images: dict[str, dict[str, Any]] | None = None,
        sources: dict[str, str] | None = None,
    ):
        self.data = dict(data)
        self.site_of = dict(site_of)
        #: The image rows of the touched sites, as the invariant read sees them.
        self.images = {k: dict(v) for k, v in (images or {}).items()}
        #: unified_sites.source_id per site.
        self.sources = dict(sources or {})
        self.journal: list[dict[str, Any]] = []
        self.sent: list[str] = []
        self.timeout_after_commit = False
        self.timeout_before_commit = False
        #: An exit code the channel reports although the statement ran (ssh's 255, psql's 2).
        self.exit_code: int | None = None
        #: What psql prints for a statement, when a test needs output other than the real run's.
        self.stdout_override: str | None = None

    def __call__(self, sql: str, *, rows: bool = False, check: bool = True, **_: Any):
        self.sent.append(sql)
        if sql.startswith("-- Generated by scripts/remediation/gallery_audit/chunk_writer.py"):
            proc = self._transaction(sql)
        elif sql.startswith("SELECT row_to_json(t) FROM (SELECT\n  (SELECT count(*)"):
            proc = self._ok(json.dumps(self._after(sql)))
        elif "count(*)::int AS n FROM remediation_change_log" in sql:
            stamp = re.search(r"run_stamp = '([^']*)'", sql).group(1)
            n = sum(1 for j in self.journal if j["run_stamp"] == stamp)
            proc = self._ok(json.dumps({"n": n}))
        elif "FROM remediation_change_log WHERE run_stamp = " in sql and "ORDER BY id" in sql:
            m = JOURNAL_READ.fullmatch(sql)
            assert m is not None, f"the fake cannot read: {sql}"
            columns, stamp = [c.strip() for c in m.group(1).split(",")], m.group(2)
            assert set(columns) <= set(JOURNAL_COLUMNS), f"unknown journal column in {columns}"
            lines = [
                json.dumps({k: j[k] for k in columns})
                for j in self.journal
                if j["run_stamp"] == stamp
            ]
            proc = self._ok("\n".join(lines))
        elif "::text AS value FROM" in sql:
            m = re.search(r"SELECT id::text AS row_key, (\w+)::text AS value FROM (\w+) WHERE", sql)
            assert m is not None, f"the fake cannot read: {sql}"
            column, table = m.groups()
            keys = re.findall(r"'([^']+)'::(?:integer|uuid)", sql)
            lines = [
                json.dumps({"row_key": k, "value": self.data[(table, column, k)]})
                for k in keys
                if (table, column, k) in self.data
            ]
            proc = self._ok("\n".join(lines))
        else:
            raise AssertionError(f"the fake psql does not understand this statement:\n{sql[:300]}")
        if check and proc.returncode != 0:
            raise C.pv.PersistError(f"psql exited {proc.returncode}")
        return proc

    def _after(self, sql: str) -> dict[str, int]:
        """Every metric the invariant read names, computed from the predicates it states."""
        out: dict[str, int] = {}
        for body, name in AFTER_METRIC.findall(sql):
            body = " ".join(body.split())
            heroes = re.fullmatch(
                r"\(SELECT w\.site_id FROM wiki_images w WHERE w\.site_id IN \(([^)]*)\)"
                r" GROUP BY w\.site_id HAVING count\(\*\) FILTER \(WHERE w\.is_hero\) > 1\) x",
                body,
            )
            images = re.fullmatch(r"wiki_images w WHERE w\.site_id IN \(([^)]*)\) AND (.+)", body)
            sites = re.fullmatch(
                r"unified_sites u WHERE u\.id IN \(([^)]*)\) AND u\.source_id <> '([^']*)'", body
            )
            if heroes:
                listed = set(_uuids(heroes.group(1)))
                per_site = dict.fromkeys(listed, 0)
                for row in self.images.values():
                    if row["site_id"] in listed and row["is_hero"]:
                        per_site[row["site_id"]] += 1
                out[name] = sum(1 for n in per_site.values() if n > 1)
            elif images:
                listed = set(_uuids(images.group(1)))
                tests = [self._predicate(p) for p in images.group(2).split(" AND ")]
                out[name] = sum(
                    1
                    for row in self.images.values()
                    if row["site_id"] in listed and all(test(row) for test in tests)
                )
            elif sites:
                listed = _uuids(sites.group(1))
                out[name] = sum(1 for s in listed if self.sources[s] != sites.group(2))
            else:
                raise AssertionError(f"the fake cannot read this metric: {body}")
        assert out, f"the fake found no metric in: {sql}"
        return out

    @staticmethod
    def _predicate(text: str):
        """One conjunct of the invariant read, as a test on a model row; refuses the unknown."""
        if text == "w.is_hero":
            return lambda row: row["is_hero"]
        if text == "w.is_excluded IS TRUE":
            return lambda row: row["is_excluded"] is True
        if text == "w.image_kind IS NOT NULL":
            return lambda row: row["image_kind"] is not None
        vocab = re.fullmatch(r"w\.image_kind NOT IN \(((?:'[a-z_]+'(?:, )?)+)\)", text)
        if vocab:
            kinds = set(re.findall(r"'([a-z_]+)'", vocab.group(1)))
            return lambda row: row["image_kind"] is not None and row["image_kind"] not in kinds
        raise AssertionError(f"the fake cannot read this predicate: {text!r}")

    @staticmethod
    def _ok(stdout: str, code: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(["psql"], code, stdout, stderr)

    def _transaction(self, sql: str) -> subprocess.CompletedProcess:
        assert "\\set ON_ERROR_STOP on\nBEGIN;\n" in sql, "not a transaction this fake can run"
        call = WRITER_CALL.search(sql)
        assert call is not None, "the statement has no apply_remediation_change loop"
        test_id, stamp, confidence = call.groups()
        rows = [_literals(m.group(1)) for m in PLAN_ROW.finditer(sql)]
        assert rows, "the statement carries no plan rows"
        data, journal = dict(self.data), list(self.journal)
        for _seq, table, column, key, site, old, new, ckey, _reason, _evidence in rows:
            assert self.site_of.get(key, key) == site, "a plan row on another site's image"
            ident = (table, column, key)
            if ident not in data or data[ident] != old:
                return self._ok(
                    "BEGIN\n", 3, f"ERROR:  apply_remediation_change: {ident} expected 1 row"
                )
            data[ident] = new
            journal.append(
                {
                    "run_stamp": stamp,
                    "table_name": table,
                    "column_name": column,
                    "row_pk": key,
                    "old_value": old,
                    "new_value": new,
                    "change_key": ckey,
                    "test_id": test_id,
                    "confidence": confidence,
                }
            )
        ends = sql.rstrip().rsplit("\n", 1)[-1]
        assert ends in ("COMMIT;", "ROLLBACK;"), f"the statement ends in {ends!r}"
        n = sum(1 for j in journal if j["run_stamp"] == stamp)
        out = f"BEGIN\nCREATE TABLE\nINSERT 0 {len(rows)}\nDO\n journal rows for this run | {n}\n"
        if self.timeout_before_commit:
            raise C.OutcomeUnknown("psql did not answer within 900s")
        if self.exit_code is not None:
            return self._ok("", self.exit_code, "ssh: connection reset")
        if ends == "COMMIT;":
            self.data, self.journal = data, journal
            if self.timeout_after_commit:
                raise C.OutcomeUnknown("psql did not answer within 900s")
            return self._ok(out + "COMMIT\n")
        if self.stdout_override is not None:
            return self._ok(self.stdout_override)
        return self._ok(out + "ROLLBACK\n")


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Two sites, three image rows and a thumbnail, and an emitted chunk over them."""
    data = {
        ("wiki_images", "author", "101"): None,
        ("wiki_images", "author_url", "101"): None,
        ("wiki_images", "author", "202"): None,
        ("unified_sites", "thumbnail_url", S2): "/data/images/wiki/00000000/hero.webp",
    }
    images = {
        "101": {"site_id": S1, "is_hero": False, "is_excluded": False, "image_kind": None},
        "202": {"site_id": S2, "is_hero": False, "is_excluded": None, "image_kind": "artifact"},
        # the served hero of S1: a hero, live, with a kind - what the invariant read must accept
        "303": {"site_id": S1, "is_hero": True, "is_excluded": False, "image_kind": "site_photo"},
    }
    psql = FakePsql(
        data,
        {"101": S1, "202": S2},
        images=images,
        sources={S1: "ancient_nerds", S2: "ancient_nerds"},
    )
    monkeypatch.setattr(C.pv, "run_psql", psql)
    chunk = _chunk(
        _change("101", new="Jane O'Hara"),
        _change("101", "author_url", new="https://commons.wikimedia.org/wiki/User:Jane"),
        _change("202", new="Ardfern", site=S2),
        _change(
            S2,
            "thumbnail_url",
            old="/data/images/wiki/00000000/hero.webp",
            new="/data/images/wiki/00000000/Gate.webp",
            site=S2,
            table="unified_sites",
        ),
    )
    directory = C.emit_chunk(tmp_path, chunk)
    return psql, chunk, directory


# --------------------------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------------------------


def test_chunks_hold_at_most_100_whole_sites_in_the_callers_order():
    sites = [f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 251)]
    changes = []
    for n, site in enumerate(reversed(sites)):
        changes.append(_change(str(1000 + 2 * n), site=site))
        changes.append(_change(str(1000 + 2 * n), "author_url", new="https://x", site=site))
    chunks = C.chunk_changes(LANE, changes)
    assert [len(c.sites) for c in chunks] == [100, 100, 50]
    assert [c.run_stamp for c in chunks] == [
        "img-test-2026-09-23-001",
        "img-test-2026-09-23-002",
        "img-test-2026-09-23-003",
    ]
    # a site is never split, and the first chunk holds the caller's first 100 sites
    assert {c.site_id for c in chunks[0].changes} == set(list(reversed(sites))[:100])
    assert all(len(c.changes) == 2 * len(c.sites) for c in chunks)


def test_a_row_planned_twice_is_refused():
    with pytest.raises(C.ChunkError, match="planned twice"):
        C.chunk_changes(LANE, [_change("101"), _change("101", new="Other")])


def test_an_empty_plan_and_an_oversized_chunk_are_refused():
    with pytest.raises(C.ChunkError, match="empty plan"):
        C.chunk_changes(LANE, [])
    with pytest.raises(C.ChunkError, match="1..100 sites"):
        C.chunk_changes(LANE, [_change("101")], sites_per_chunk=101)


def test_may_empty_names_only_sites_the_plan_touches():
    with pytest.raises(C.ChunkError, match="does not touch"):
        C.chunk_changes(LANE, [_change("101")], may_empty=[S2])


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (_change("101", column="license"), "not a column the image lanes write"),
        (_change("101", column="is_excluded", old="false", new="yes"), "'true' or 'false'"),
        (_change("101", column="width", old="800", new="1600px"), "not an integer"),
        (_change("101", old="Jane", new="Jane"), "a no-op is not a change"),
        (_change("101", site="not-a-uuid"), "lower-case UUID"),
        (_change("x1"), "not a row id"),
        (_change(S2, "thumbnail_url", old="/a", new="/b", table="unified_sites"), "is its site"),
        (_change("101", column="image_kind", new="photo"), "0019's vocabulary"),
        (_change("101", column="is_hero", old="true", new=None), "never cleared to NULL"),
        (_change("101", new="line\nbreak"), "control character"),
        # the three characters json.dumps writes raw and str.splitlines() breaks a record at
        (_change("101", new="Jane\u2028Doe"), "control character"),
        (_change("101", new="Jane\x85Doe"), "control character"),
        (C.Change("wiki_images", "author", "101", S1, None, "J", "A1", "why\rnot", EV), "a reason"),
        (C.Change("wiki_images", "author", "101", S1, None, "J", "A 1", "why", EV), "rule id"),
        (C.Change("wiki_images", "author", "101", S1, None, "J", "A1", "why", []), "evidence"),
        (C.Change("wiki_images", "author", "101", S1, None, "J", "A1", " ", EV), "reason"),
    ],
)
def test_a_change_the_writer_cannot_express_exactly_is_refused(change, says):
    with pytest.raises(C.ChunkError, match=re.escape(says)):
        C.validate_change(change)


def test_a_lane_whose_identity_could_break_the_sql_is_refused():
    with pytest.raises(C.ChunkError, match="confidence"):
        C.Lane("img-x", "T09/x", "img-x-1", "certain", "img x")
    with pytest.raises(C.ChunkError, match="RAISE message"):
        C.Lane("img-x", "T09/x", "img-x-1", "weak", "img 'x'")
    with pytest.raises(C.ChunkError, match="lower-case token"):
        C.Lane("img x", "T09/x", "img-x-1", "weak", "img x")


# --------------------------------------------------------------------------------------------
# the statements
# --------------------------------------------------------------------------------------------


def _code(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def test_the_write_goes_through_the_journal_primitive_only(world):
    _, chunk, directory = world
    sql = (directory / "APPLY.sql").read_text(encoding="utf-8")
    code = _code(sql)
    assert code.count("apply_remediation_change(") == 1
    assert "'T09/attribution', 'img-test-2026-09-23-001', r.change_key, 'authoritative'" in code
    assert not re.search(r"\b(DELETE|UPDATE|TRUNCATE)\b", C._strip_literals_and_comments(sql))
    assert sql.rstrip().endswith("\nCOMMIT;") and code.count("COMMIT;") == 1
    assert sql.count("-- plan sha256 ") == 1
    assert C.chunk_digest(C.header(chunk), C.records(chunk)) in sql


def test_the_scope_guard_refuses_every_site_outside_the_curated_source(world):
    _, _, directory = world
    code = _code((directory / "APPLY.sql").read_text(encoding="utf-8"))
    assert "WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';" in code
    assert "are not % sites', bad, 'ancient_nerds';" in code


def test_a_site_the_chunk_may_empty_is_named_in_the_statement(tmp_path):
    chunk = _chunk(
        _change("101", "is_excluded", old="false", new="true"),
        _change("202", site=S2),
        may_empty=[S1],
    )
    sql = C.render_statement(chunk)
    assert f"INSERT INTO _img_may_empty (site_id) VALUES ('{S1}'::uuid);" in sql
    assert "AND b.site_id NOT IN (SELECT site_id FROM _img_may_empty);" in sql
    # a chunk that names none may not lose any site's last live image
    assert "INSERT INTO _img_may_empty" not in C.render_statement(_chunk(_change("202", site=S2)))


def test_every_key_cast_is_guarded_by_its_table(world):
    """PostgreSQL may evaluate a join condition before the WHERE: `'<uuid>'::integer` raises."""
    _, _, directory = world
    code = _code((directory / "APPLY.sql").read_text(encoding="utf-8"))
    casts = re.findall(r"p\.row_key::(\w+)", code)
    assert casts and set(casts) == {"integer", "uuid"}
    for line in code.splitlines():
        if "p.row_key::" in line:
            assert re.search(r"CASE WHEN p\.table_name = '(\w+)' THEN p\.row_key::\w+ END", line), (
                line
            )


def test_the_old_value_guard_and_the_new_value_invariant_are_null_safe_per_column(world):
    _, _, directory = world
    code = _code((directory / "APPLY.sql").read_text(encoding="utf-8"))
    for column in ("author", "author_url", "thumbnail_url"):
        assert f"AND t.{column}::text IS DISTINCT FROM p.old_value;" in code
        assert f"AND t.{column}::text IS DISTINCT FROM p.new_value;" in code
    assert "= NULL" not in code


def test_the_hero_invariant_is_the_hero_repairs_own_in_its_at_most_form(world):
    _, _, directory = world
    sql = (directory / "APPLY.sql").read_text(encoding="utf-8")
    block = "\n".join(
        HA.one_hero_invariant_sql("_img_plan", label="img test chunk 001", at_most=True)
    )
    assert block in sql
    assert "HAVING count(*) FILTER (WHERE w.is_hero) > 1) x;" in block


def test_the_journal_is_reconciled_both_ways_inside_the_transaction(world):
    _, _, directory = world
    do_block = _code((directory / "APPLY.sql").read_text(encoding="utf-8")).split("DO $$", 1)[1]
    do_block = do_block.split("END $$;", 1)[0]
    assert "planned row(s) disagree with the journal" in do_block
    assert "NOT EXISTS (SELECT 1 FROM _img_plan p" in do_block
    assert "<> expected THEN" in do_block
    assert "lost their last live image" in do_block
    assert "hero row(s) are excluded" in do_block


#: Every guard of the DO block, as its condition must read in the rendered statement. `{s}` is
#: the statement's own run stamp. The fake does not run these - so the text is the proof.
DO_BLOCK_GUARDS = {
    "every planned image row lives on the site the plan names": (
        "    SELECT count(*) INTO bad FROM _img_plan p\n"
        "      LEFT JOIN wiki_images w ON w.id = CASE WHEN p.table_name = 'wiki_images'"
        " THEN p.row_key::integer END\n"
        "     WHERE p.table_name = 'wiki_images' AND (w.id IS NULL OR w.site_id IS DISTINCT FROM"
        " p.site_id);\n"
        "    IF bad > 0 THEN\n"
        "        RAISE EXCEPTION '{label}: % planned image row(s) do not live on the site the plan"
        " names', bad;\n"
    ),
    "exactly the planned number of rows moved": (
        "    IF moved <> expected THEN\n"
        "        RAISE EXCEPTION '{label}: % row(s) changed, % planned', moved, expected;\n"
    ),
    "plan -> journal with the planned values and keys": (
        "    SELECT count(*) INTO bad FROM _img_plan p\n"
        "      LEFT JOIN remediation_change_log l\n"
        "        ON l.run_stamp = '{s}' AND l.table_name = p.table_name\n"
        "       AND l.column_name = p.column_name AND l.row_pk = p.row_key\n"
        "     WHERE l.id IS NULL OR l.old_value IS DISTINCT FROM p.old_value\n"
        "        OR l.new_value IS DISTINCT FROM p.new_value OR l.change_key IS DISTINCT FROM"
        " p.change_key;\n"
        "    IF bad > 0 THEN\n"
    ),
    "journal -> plan, and nothing else under the stamp": (
        "    SELECT count(*) INTO bad FROM remediation_change_log l\n"
        "     WHERE l.run_stamp = '{s}'\n"
        "       AND NOT EXISTS (SELECT 1 FROM _img_plan p\n"
        "                        WHERE p.table_name = l.table_name AND p.column_name ="
        " l.column_name\n"
        "                          AND p.row_key = l.row_pk);\n"
        "    IF bad > 0 OR (SELECT count(*) FROM remediation_change_log WHERE run_stamp = '{s}')"
        " <> expected THEN\n"
    ),
    "no hero on an excluded row": (
        "    SELECT count(*) INTO bad FROM wiki_images w\n"
        "     WHERE w.site_id IN (SELECT site_id FROM _img_plan) AND w.is_hero AND w.is_excluded IS"
        " TRUE;\n"
        "    IF bad > 0 THEN\n"
        "        RAISE EXCEPTION '{label}: % hero row(s) are excluded', bad;\n"
    ),
    "the sites that had a live image before": (
        "CREATE TEMP TABLE _img_live_before ON COMMIT DROP AS\n"
        "  SELECT DISTINCT w.site_id FROM wiki_images w\n"
        "   WHERE w.site_id IN (SELECT site_id FROM _img_plan) AND w.is_excluded IS NOT TRUE;\n"
    ),
    "a site that had a live image keeps one": (
        "    SELECT count(*) INTO bad FROM _img_live_before b\n"
        "     WHERE NOT EXISTS (SELECT 1 FROM wiki_images w\n"
        "                        WHERE w.site_id = b.site_id AND w.is_excluded IS NOT TRUE)\n"
        "       AND b.site_id NOT IN (SELECT site_id FROM _img_may_empty);\n"
        "    IF bad > 0 THEN\n"
        "        RAISE EXCEPTION '{label}: % site(s) lost their last live image', bad;\n"
    ),
    "every kind is in 0019's vocabulary": (
        "    SELECT count(*) INTO bad FROM wiki_images w\n"
        "     WHERE w.site_id IN (SELECT site_id FROM _img_plan)\n"
        "       AND w.image_kind IS NOT NULL AND w.image_kind NOT IN ('artifact', 'map_or_document',"
        " 'other', 'painting_or_artwork', 'people', 'site_photo', 'unknown');\n"
        "    IF bad > 0 THEN\n"
        "        RAISE EXCEPTION '{label}: % image kind(s) outside the vocabulary', bad;\n"
    ),
    "every planned row still holds its old value": (
        "    SELECT count(*) INTO bad FROM _img_plan p JOIN wiki_images t ON t.id = CASE WHEN"
        " p.table_name = 'wiki_images' THEN p.row_key::integer END\n"
        "     WHERE p.table_name = 'wiki_images' AND p.column_name = 'author'\n"
        "       AND t.author::text IS DISTINCT FROM p.old_value;\n"
        "    IF bad > 0 THEN\n"
    ),
    "every planned row now holds its new value": (
        "    SELECT count(*) INTO bad FROM _img_plan p JOIN unified_sites t ON t.id = CASE WHEN"
        " p.table_name = 'unified_sites' THEN p.row_key::uuid END\n"
        "     WHERE p.table_name = 'unified_sites' AND p.column_name = 'thumbnail_url'\n"
        "       AND t.thumbnail_url::text IS DISTINCT FROM p.new_value;\n"
        "    IF bad > 0 THEN\n"
    ),
}


@pytest.mark.parametrize("guard", sorted(DO_BLOCK_GUARDS))
@pytest.mark.parametrize(("name", "rollback"), [("APPLY.sql", False), ("ROLLBACK.sql", True)])
def test_every_guard_of_the_transaction_is_rendered_with_its_exact_condition(
    world, guard, name, rollback
):
    _, chunk, directory = world
    sql = (directory / name).read_text(encoding="utf-8")
    stamp = chunk.rollback_stamp if rollback else chunk.run_stamp
    label = f"img test {'rollback ' if rollback else ''}chunk 001"
    block = DO_BLOCK_GUARDS[guard].replace("{s}", stamp).replace("{label}", label)
    assert block in sql, guard


def test_the_rollback_inverts_every_row_under_its_own_stamp_and_keys(world):
    _, chunk, directory = world
    sql = (directory / "ROLLBACK.sql").read_text(encoding="utf-8")
    rows = [_literals(m.group(1)) for m in PLAN_ROW.finditer(sql)]
    forward = {(r["table"], r["column"], r["row_key"]): r for r in C.records(chunk)}
    assert len(rows) == len(forward) == 4
    for _seq, table, column, key, _site, old, new, ckey, _reason, _ev in rows:
        record = forward[(table, column, key)]
        assert (old, new) == (record["new_value"], record["old_value"])
        assert ckey == f"img-test-rollback:{table}.{column}:{key}"
    assert "'img-test-2026-09-23-001-rollback', r.change_key" in sql
    # the undo carries the same guards as the write
    for says in (
        "are not % sites",
        "no longer hold the planned old value",
        "disagree with the journal",
    ):
        assert says in sql


def test_the_lint_reads_code_and_not_literals_or_comments():
    ok = "BEGIN;\n-- an UPDATE in a comment\nSELECT 'DELETE me', 1;\nCOMMIT;\n"
    C.lint_statement(ok)
    for bad in (
        "BEGIN;\nUPDATE wiki_images SET author = 'x';\nCOMMIT;\n",
        "BEGIN;\nDELETE FROM wiki_images;\nCOMMIT;\n",
        "BEGIN;\nINSERT INTO wiki_images VALUES (1);\nCOMMIT;\n",
        "BEGIN;\nDROP TABLE x;\nCOMMIT;\n",
        "BEGIN;\nSELECT 1;\n",
        "BEGIN;\nCOMMIT;\nCOMMIT;\n",
    ):
        with pytest.raises(C.ChunkError):
            C.lint_statement(bad)


# --------------------------------------------------------------------------------------------
# the files on disk
# --------------------------------------------------------------------------------------------


def test_the_undo_is_written_before_the_write(tmp_path, monkeypatch):
    order: list[str] = []
    real = Path.write_text

    def recording(self, *args, **kwargs):
        order.append(self.name)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording)
    C.emit_chunk(tmp_path, _chunk(_change("101")))
    assert order.index("ROLLBACK.sql") < order.index("APPLY.sql")


def test_a_delivered_chunk_is_never_replaced(world, tmp_path):
    _, chunk, directory = world
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert C.emit_chunk(tmp_path, chunk) == directory  # the identical chunk: a no-op
    other = _chunk(_change("101", new="Someone else"))
    with pytest.raises(C.ChunkError, match="never replaced"):
        C.emit_chunk(tmp_path, other)
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_a_chunk_checked_out_with_crlf_is_still_the_plans(world):
    """Chunks are versioned; with core.autocrlf=true every file comes back with CRLF."""
    _, chunk, directory = world
    for path in directory.iterdir():
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert C.check_delivered(directory).run_stamp == chunk.run_stamp


def _rewrite_plan(directory: Path, change) -> None:
    """PLAN.jsonl with `change(record)` applied to its first record, written as emit_chunk writes."""
    path = directory / "PLAN.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]
    change(records[0])
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def test_a_plan_record_whose_change_key_this_lane_does_not_make_is_refused(world):
    psql, _, directory = world
    _rewrite_plan(directory, lambda r: r.update(change_key="another-lane:wiki_images.author:101"))
    with pytest.raises(C.ChunkError, match="carries a change key this lane does not make"):
        C.load_chunk(directory)
    assert psql.sent == []


def test_a_delivered_value_with_a_line_separator_is_refused_by_name_not_by_traceback(world):
    """json.dumps writes U+2028 raw: read with splitlines(), the record came apart."""
    psql, _, directory = world
    _rewrite_plan(directory, lambda r: r.update(reason=r["reason"] + "\u2028more"))
    assert "\u2028" in (directory / "PLAN.jsonl").read_text(encoding="utf-8")
    with pytest.raises(C.ChunkError, match="a reason carries a control character"):
        C.load_chunk(directory)
    assert C.main([str(directory), "--check"]) == C.EXIT_REFUSED
    assert psql.sent == []


@pytest.mark.parametrize(
    ("name", "old", "new", "says"),
    [
        ("APPLY.sql", "'Jane O''Hara'", "'Jane OHara'", "not the statement its plan renders"),
        ("ROLLBACK.sql", "'Ardfern', NULL", "'Ardfern', 'x'", "not the statement its plan renders"),
        ("APPLY.sql", "-- plan sha256 ", "-- plan sha 256 ", "not pinned to this plan"),
        ("PLAN.jsonl", '"new_value": "Ardfern"', '"new_value": "Ardfern2"', "not pinned"),
        ("CHUNK.json", '"chunk": 1', '"chunk": 2', "does not describe the rows"),
    ],
)
def test_a_file_that_is_not_the_plans_is_refused_before_anything_is_sent(
    world, name, old, new, says
):
    psql, _, directory = world
    path = directory / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, old)
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    with pytest.raises(C.ChunkError, match=says):
        C.check_delivered(directory)
    assert C.main([str(directory), "--apply"]) == C.EXIT_REFUSED
    assert psql.sent == []


# --------------------------------------------------------------------------------------------
# production steps against the fake
# --------------------------------------------------------------------------------------------


def test_the_rehearsal_sends_the_write_with_rollback_and_keeps_nothing(world):
    psql, _, directory = world
    before = dict(psql.data)
    assert C.command_rehearse(directory) == C.EXIT_OK
    rehearsal = psql.sent[0]
    assert rehearsal.rstrip().endswith("\nROLLBACK;") and "\nCOMMIT;" not in rehearsal
    head = (directory / "APPLY.sql").read_text(encoding="utf-8").rsplit("COMMIT;", 1)[0]
    assert rehearsal.startswith(head)
    assert psql.data == before and psql.journal == []


def test_the_apply_writes_journals_and_reads_back_both_ways(world, capsys):
    psql, chunk, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    assert psql.data[("wiki_images", "author", "101")] == "Jane O'Hara"
    assert psql.data[("unified_sites", "thumbnail_url", S2)].endswith("Gate.webp")
    assert len(psql.journal) == len(chunk.changes)
    assert "APPLY OK" in capsys.readouterr().out
    assert C.command_readback(directory) == C.EXIT_OK
    # never twice: the stamp is journalled now
    with pytest.raises(C.ChunkError, match="never apply twice"):
        C.command_apply(directory)


def test_data_changed_underneath_is_not_committed(world, capsys):
    psql, _, directory = world
    psql.data[("wiki_images", "author", "202")] = "A founder typed this"
    assert C.command_apply(directory) == C.EXIT_NOT_COMMITTED
    assert psql.journal == [] and psql.data[("wiki_images", "author", "101")] is None
    assert "NOT COMMITTED" in capsys.readouterr().out


def test_a_timeout_with_an_empty_journal_is_an_unknown_outcome(world, capsys):
    psql, _, directory = world
    psql.timeout_before_commit = True
    assert C.main([str(directory), "--apply"]) == C.EXIT_UNKNOWN
    err = capsys.readouterr().err
    assert "OUTCOME UNKNOWN" in err
    assert "run_stamp = 'img-test-2026-09-23-001'" in err and "reads 4" in err


def test_a_dropped_channel_with_an_empty_journal_is_unknown_not_uncommitted(world):
    """Only psql's own exit 3 ends the session; after ssh's 255 the server may still COMMIT."""
    psql, _, directory = world
    psql.exit_code = 255
    with pytest.raises(C.OutcomeUnknown, match="holds 0 rows so far"):
        C.command_apply(directory)


def test_the_rehearsal_that_never_showed_its_read_back_and_rollback_fails(world):
    psql, _, directory = world
    psql.stdout_override = "BEGIN\n"
    assert C.command_rehearse(directory) == C.EXIT_REHEARSAL_FAILED


def test_the_rehearsal_fails_when_its_run_stamp_already_journals_rows(world, capsys):
    """Something else wrote under this chunk's stamp: the rehearsal cannot vouch for the chunk."""
    psql, chunk, directory = world
    psql.journal.append(
        {
            "run_stamp": chunk.run_stamp,
            "table_name": "wiki_images",
            "column_name": "author",
            "row_pk": "555",
            "old_value": None,
            "new_value": "x",
            "change_key": "other",
            "test_id": "T09/attribution",
            "confidence": "weak",
        }
    )
    assert C.command_rehearse(directory) == C.EXIT_REHEARSAL_FAILED
    assert "survived it" in capsys.readouterr().out


def test_a_journal_that_holds_part_of_the_chunk_is_an_unknown_outcome(world):
    """One transaction cannot leave 2 of 4 rows behind: that is never read as committed."""
    psql, chunk, _ = world
    for change in chunk.changes[:2]:
        psql.journal.append(
            {
                "run_stamp": chunk.run_stamp,
                "table_name": change.table,
                "column_name": change.column,
                "row_pk": change.row_key,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "change_key": C.change_key(LANE, change),
                "test_id": LANE.test_id,
                "confidence": LANE.confidence,
            }
        )
    with pytest.raises(C.OutcomeUnknown, match="holds 2 of 4 rows"):
        C.settle(chunk, "psql timed out", session_ended=False)


def test_a_timeout_after_the_commit_is_settled_from_the_journal(world, capsys):
    psql, _, directory = world
    psql.timeout_after_commit = True
    assert C.command_apply(directory) == C.EXIT_COMMITTED_UNCLEAN
    assert "APPLY LANDED" in capsys.readouterr().out


def test_the_readback_names_a_journal_row_the_plan_does_not_have(world, capsys):
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    psql.journal.append({**psql.journal[0], "row_pk": "999", "change_key": "stray"})
    assert C.command_readback(directory) == C.EXIT_COMMITTED_UNCONFIRMED
    assert "journal -> plan" in capsys.readouterr().out


def test_the_readback_names_a_planned_row_the_journal_does_not_have(world, capsys):
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    psql.journal.pop()
    assert C.command_readback(directory) == C.EXIT_COMMITTED_UNCONFIRMED
    assert "plan -> journal" in capsys.readouterr().out


def test_the_readback_names_a_row_that_does_not_hold_its_new_value(world, capsys):
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    psql.data[("wiki_images", "author", "202")] = "Changed afterwards"
    assert C.command_readback(directory) == C.EXIT_COMMITTED_UNCONFIRMED
    assert "holds 'Changed afterwards', planned 'Ardfern'" in capsys.readouterr().out


def test_the_readback_names_a_journal_row_it_holds_twice(world, capsys):
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    psql.journal.append(dict(psql.journal[0]))
    assert C.command_readback(directory) == C.EXIT_COMMITTED_UNCONFIRMED
    assert "twice under img-test-2026-09-23-001" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("column", "wrong"),
    [
        ("old_value", "someone else"),
        ("new_value", "someone else"),
        ("change_key", "another-lane:wiki_images.author:101"),
        ("test_id", "T09/another-test"),
        ("confidence", "weak"),
    ],
)
def test_the_readback_compares_every_journal_column_with_the_plan(world, capsys, column, wrong):
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    row = next(j for j in psql.journal if j["row_pk"] == "202")
    row[column] = wrong
    assert C.command_readback(directory) == C.EXIT_COMMITTED_UNCONFIRMED
    assert f"journal {column} is {wrong!r}" in capsys.readouterr().out


def _heroes_twice(psql):
    psql.images["101"]["is_hero"] = True  # S1 already has 303 as its hero


def _hero_excluded(psql):
    psql.images["303"]["is_excluded"] = True


def _kind_outside(psql):
    psql.images["202"]["image_kind"] = "photo"


def _site_outside(psql):
    psql.sources[S2] = "lyra"


@pytest.mark.parametrize(
    ("metric", "break_it"),
    [
        ("sites_with_two_heroes", _heroes_twice),
        ("excluded_heroes", _hero_excluded),
        ("kinds_outside_vocabulary", _kind_outside),
        ("sites_outside_the_curated_source", _site_outside),
    ],
)
def test_the_readback_names_every_broken_invariant(world, capsys, metric, break_it):
    """The fake computes each metric from the SQL's own predicates: a weakened read misses it."""
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    capsys.readouterr()
    break_it(psql)
    assert C.command_readback(directory) == C.EXIT_COMMITTED_UNCONFIRMED
    out = capsys.readouterr().out
    assert f"invariant {metric} = 1" in out
    assert out.count("invariant ") == 1  # the other three still read 0


def test_the_rollback_rehearsal_runs_on_the_landed_rows_and_keeps_them(world):
    psql, _, directory = world
    assert C.command_apply(directory) == C.EXIT_OK
    landed, journalled = dict(psql.data), list(psql.journal)
    sent_before = len(psql.sent)
    assert C.command_rehearse_rollback(directory) == C.EXIT_OK
    assert psql.data == landed and psql.journal == journalled
    (reversal,) = [s for s in psql.sent[sent_before:] if s.startswith("-- Generated by")]
    assert "'img-test-2026-09-23-001-rollback', r.change_key" in reversal
    assert reversal.rstrip().endswith("\nROLLBACK;")


def test_the_rollback_restores_every_old_value_when_it_is_run(world):
    """What `psql < ROLLBACK.sql` does: the reversal committed, journalled under its own stamp."""
    psql, chunk, directory = world
    before = dict(psql.data)
    assert C.command_apply(directory) == C.EXIT_OK
    psql((directory / "ROLLBACK.sql").read_text(encoding="utf-8"))
    assert psql.data == before
    assert C.readback(chunk, rollback=True) == []


def test_the_rollback_rehearsal_before_any_apply_fails(world):
    """Its guards need the rows the write leaves behind; on the pre-write state they refuse."""
    _, _, directory = world
    assert C.command_rehearse_rollback(directory) == C.EXIT_REHEARSAL_FAILED


# --------------------------------------------------------------------------------------------
# the hero repair: the extracted invariant, the transport, the byte-identical statement
# --------------------------------------------------------------------------------------------

#: sha256 of `render_transaction` over the synthetic plan below, taken from the module *before*
#: the invariant was extracted (2026-09-23). The extraction must not move a byte.
SYNTHETIC_HERO_SHA256 = "193d5c6e4bc0723155d7a3f9abd4fcbb535cbe17739c31908f9a026815cfd4aa"
#: sha256 of the delivered `output/remediation/hero_repair/APPLY.sql` (5,438 rows, applied
#: 2026-09-20): re-emitting it from its PLAN.jsonl must reproduce it byte for byte.
DELIVERED_HERO_SHA256 = "33cbab582f83037806419dfde89d67ea0122aa70c74ec09685acf9794f0b3ed2"
HERO_PLAN = REPO / "output" / "remediation" / "hero_repair" / "PLAN.jsonl"


def _hero_record(image_id, site, role, old, new, reason):
    return ChangeRecord(
        image_id=image_id,
        site_id=site,
        site_name="Site's name",
        role=role,
        old_is_hero=old,
        new_is_hero=new,
        condition=f"id = {image_id} AND is_hero = {str(old).lower()}",
        reason=reason,
        evidence=[{"source": "commons:imageinfo", "quote": "File:O'Brien.jpg -> 4000x3000"}],
    )


def test_the_hero_statement_is_byte_identical_after_the_extraction():
    records = [
        _hero_record(11, S1, "demote", True, False, "old hero of 'S1'"),
        _hero_record(12, S1, "promote", False, True, "new hero of 'S1'"),
        _hero_record(21, S2, "demote", True, False, "old hero"),
        _hero_record(22, S2, "promote", False, True, "new hero"),
    ]
    sql = HA.render_transaction(records, run_stamp=HA.RUN_STAMP, site_ids={S1, S2})
    assert hashlib.sha256(sql.encode("utf-8")).hexdigest() == SYNTHETIC_HERO_SHA256
    assert "\n".join(HA.one_hero_invariant_sql()) in sql


@pytest.mark.skipif(
    not HERO_PLAN.is_file(),
    reason=f"{HERO_PLAN} is gitignored working data; the delivered-statement pin is local",
)
def test_the_delivered_hero_apply_sql_re_emits_byte_identical():
    records = HA.load_records(HERO_PLAN)
    sql = HA.render_transaction(
        records, run_stamp=HA.RUN_STAMP, site_ids={r.site_id for r in records}
    )
    assert len(records) == 5438
    assert hashlib.sha256(sql.encode("utf-8")).hexdigest() == DELIVERED_HERO_SHA256


def test_the_invariant_function_refuses_what_cannot_stand_in_its_sql():
    with pytest.raises(HA.PlanError):
        HA.one_hero_invariant_sql("wiki_images")
    with pytest.raises(HA.PlanError):
        HA.one_hero_invariant_sql(label="it's")
    exact = "\n".join(HA.one_hero_invariant_sql())
    assert "FILTER (WHERE w.is_hero) <> 1) x;" in exact
    assert "do not end with exactly one hero" in exact


def test_the_hero_transport_reports_a_timeout_as_an_unknown_outcome(monkeypatch, capsys):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=900)

    monkeypatch.setattr("prod_write.subprocess.run", timeout)
    with pytest.raises(HA.OutcomeUnknown):
        HA.run_psql("SELECT 1;")
    assert HA.main(["--verify"]) == HA.EXIT_UNKNOWN
    err = capsys.readouterr().err
    assert "OUTCOME UNKNOWN" in err
    assert "run_stamp = '2026-09-20_remediation'" in err


def test_the_hero_transport_is_prod_writes_with_its_channel_timeouts(monkeypatch):
    argv: list[list[str]] = []

    def fake_run(args, **kwargs):
        argv.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("prod_write.subprocess.run", fake_run)
    HA.run_psql("SELECT 1;")
    assert "-o ConnectTimeout=15" in " ".join(argv[0])
    assert not hasattr(HA, "PSQL")
