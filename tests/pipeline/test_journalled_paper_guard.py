"""Maintenance tools leave journalled papers alone (Task 21b, contract C7).

A paper whose result_json carries evidence, videos, corrections or a writer
changes only through theo_publish, where every write passes the paper page's
own validators and is journalled. The tools that rewrite result_json outside
it skip such a row, refuse it when a run names it, and never write onto one
that became journalled after they read it.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.lyra import theo_publishing as tp
from pipeline.research_html_renderer import PAPER_EXTRAS_COLUMNS
from tests.fake_sql import RecordingSession

REPO = Path(__file__).resolve().parents[2]
REQ = "11111111-2222-3333-4444-555555555555"
SLUG = "the-baalbek-trilithon"
CLAUSE = f"AND NOT ({tp.JOURNALLED_PAPER_SQL})"
#: refuse_journalled_paper's lookup: answered with a row, the named paper is journalled.
NAMED = "slug = :name OR id::text = :name"
REFUSAL = "a journalled paper changes only through theo_publish --correct"


def _script(name: str):
    # By file: a dependency installs a top-level package named `scripts` into
    # site-packages, which shadows our scripts/ directory for a plain import.
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_clause_names_exactly_the_keys_the_page_validates():
    page_keys = set(re.findall(r"->'(\w+)' AS", PAPER_EXTRAS_COLUMNS))
    assert page_keys == {"evidence", "videos", "corrections", "writer"}
    assert set(re.findall(r"'(\w+)'", tp.JOURNALLED_PAPER_SQL)) == page_keys


def test_a_named_journalled_paper_is_refused():
    session = RecordingSession({NAMED: [(1,)]})
    with pytest.raises(tp.JournalledPaperError, match=f"^{SLUG}: {REFUSAL}$"):
        tp.refuse_journalled_paper(session, SLUG)
    assert tp.JOURNALLED_PAPER_SQL in session.statement_with(NAMED)
    assert session.log[0][1] == {"name": SLUG}
    tp.refuse_journalled_paper(RecordingSession(), "a-legacy-paper")  # no row: not journalled


def test_the_write_never_lands_on_a_journalled_paper():
    session = RecordingSession({"UPDATE research_requests": [object()]})
    tp.write_unjournalled_result(session, REQ, {"report": "x"})
    assert CLAUSE in session.statement_with("UPDATE research_requests")
    assert session.log[0][1] == {"id": REQ, "json": '{"report": "x"}'}
    assert session.rollbacks == 0

    # Journalled (or deleted) since the tool read it: the UPDATE matches no row.
    raced = RecordingSession()
    with pytest.raises(tp.JournalledPaperError, match="nothing written"):
        tp.write_unjournalled_result(raced, REQ, {"report": "x"})
    assert raced.rollbacks == 1


# (module, the _fetch_papers arguments of --all, those of a run that names one paper)
PIPELINE_TOOLS = [
    ("backfill_probative_images", (None,), (SLUG,)),
    ("backfill_hero_image", (None,), (SLUG,)),
    ("clean_image_titles", (None, None), (SLUG, None)),
    ("clean_image_titles", (None, None), (None, REQ)),
    ("fix_source_urls", (None,), (SLUG,)),
    ("reflow_images", (None,), (SLUG,)),
    ("rewrite_image_captions", (None,), (SLUG,)),
]


@pytest.mark.parametrize(("name", "every", "named"), PIPELINE_TOOLS)
def test_a_pipeline_tool_skips_refuses_and_never_overwrites_a_journalled_paper(
    monkeypatch, name, every, named
):
    module = importlib.import_module(f"pipeline.lyra.{name}")
    session = RecordingSession()
    monkeypatch.setattr(module, "engine", SimpleNamespace(connect=lambda: session))

    assert module._fetch_papers(*every) == []
    assert CLAUSE in session.statements()[-1]
    assert module._fetch_papers(*named) == []  # named and not journalled: the SELECT ran
    assert NAMED in session.statements()[-2]
    assert CLAUSE in session.statements()[-1]

    journalled = RecordingSession({NAMED: [(1,)]})
    monkeypatch.setattr(module, "engine", SimpleNamespace(connect=lambda: journalled))
    with pytest.raises(tp.JournalledPaperError, match=REFUSAL):
        module._fetch_papers(*named)
    assert len(journalled.log) == 1  # refused before the paper was read

    # Every write goes through the one guarded UPDATE.
    assert module.write_unjournalled_result is tp.write_unjournalled_result
    assert "UPDATE research_requests" not in inspect.getsource(module)


async def test_the_image_backfill_deletes_old_files_only_after_its_write(monkeypatch):
    from pipeline.lyra import backfill_probative_images as backfill

    old = (
        "# T\n\nProse about the quarry [1].\n\n"
        f"![Quarry](/data/research-images/{REQ}/p1_old.jpg)\n\n"
        "*Quarry. Photo: A / Wikimedia Commons.*\n"
        "[Source](https://commons.wikimedia.org/wiki/File:Quarry.jpg)\n\n"
        "## References\n\n[1] A — https://a.example\n"
    )
    paper = {
        "id": REQ,
        "slug": SLUG,
        "question": "Who cut the stones?",
        "result_json": json.dumps({"title": "T", "report": old, "published_report": old}),
    }
    embedded = [{"web_path": f"/data/research-images/{REQ}/p1_new.jpg"}]

    async def embed(**kwargs):
        return kwargs["paper_text"], embedded, {"sources": ["wikimedia"]}, {}, {}

    deleted: list[str] = []
    monkeypatch.setattr(backfill, "embed_probative_images", embed)
    monkeypatch.setattr(backfill, "pick_hero_image", lambda title, images: images[0])
    monkeypatch.setattr(
        backfill, "_delete_unreferenced_images", lambda paper_id, images: deleted.append(paper_id)
    )

    # Journalled by theo_publish while the backfill spent its LLM calls: the
    # UPDATE matches no row, and the paper keeps its image files.
    raced = RecordingSession()
    monkeypatch.setattr(backfill, "engine", SimpleNamespace(connect=lambda: raced))
    with pytest.raises(tp.JournalledPaperError):
        await backfill._process_paper(paper, apply=True, replace=True)
    assert deleted == []

    written = RecordingSession({"UPDATE research_requests": [object()]})
    monkeypatch.setattr(backfill, "engine", SimpleNamespace(connect=lambda: written))
    assert (await backfill._process_paper(paper, apply=True, replace=True))[1] is True
    assert deleted == [REQ]


def test_the_citation_repair_skips_and_refuses_journalled_papers(monkeypatch):
    module = _script("repair_theo_citations")
    session = RecordingSession()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(sys, "argv", ["repair_theo_citations.py"])
    assert module.main() == 0
    assert CLAUSE in session.statement_with("FROM research_requests")

    journalled = RecordingSession({NAMED: [(1,)]})
    monkeypatch.setattr(module, "get_session", lambda: journalled)
    monkeypatch.setattr(sys, "argv", ["repair_theo_citations.py", "--apply", REQ])
    with pytest.raises(tp.JournalledPaperError, match=f"^{REQ}: {REFUSAL}$"):
        module.main()
    assert len(journalled.log) == 1
    assert module.write_unjournalled_result is tp.write_unjournalled_result
    assert "UPDATE research_requests" not in inspect.getsource(module)


def test_the_payload_swap_refuses_journalled_papers(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # the script reads ./.env at import; none here
    module = _script("swap_theo_payload")
    new = "22222222-3333-4444-5555-666666666666"
    monkeypatch.setattr(sys, "argv", ["swap_theo_payload.py", "--old", REQ, "--new", new])
    clean = RecordingSession(
        {
            "SELECT id::text, result_json, published_at, slug": [
                SimpleNamespace(id=new, result_json="{}", published_at=None, slug=None)
            ],
            "SELECT id::text, slug, is_public": [
                SimpleNamespace(id=REQ, slug=SLUG, is_public=True)
            ],
            "SET result_json = :result": [object()],
        }
    )
    monkeypatch.setattr(module, "get_session", lambda: clean)
    assert module.main() == 0
    for fragment in (
        "SELECT id::text, result_json",
        "SELECT id::text, slug, is_public",
        "SET result_json = :result",
    ):
        assert CLAUSE in clean.statement_with(fragment)

    journalled = RecordingSession({NAMED: [(1,)]})
    monkeypatch.setattr(module, "get_session", lambda: journalled)
    with pytest.raises(tp.JournalledPaperError, match=f"^{REQ}: {REFUSAL}$"):
        module.main()
    assert len(journalled.log) == 1


def test_the_gallery_script_never_touches_a_journalled_paper(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")  # the script reads ./.env at import
    module = _script("apply_meaningful_gallery")
    db = SimpleNamespace(row=None, rowcount=0, sql=[], commits=0, rollbacks=0)

    class Cursor:
        @property
        def rowcount(self):
            return db.rowcount

        def execute(self, sql, params):
            db.sql.append(sql)

        def fetchone(self):
            return db.row

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            db.commits += 1

        def rollback(self):
            db.rollbacks += 1

        def close(self):
            return None

    monkeypatch.setitem(
        sys.modules, "psycopg2", SimpleNamespace(connect=lambda **kwargs: Connection())
    )

    # The read's AND NOT (...) filtered the journalled row out.
    with pytest.raises(tp.JournalledPaperError, match=f"^{module.PAPER_ID}: missing or journalled"):
        module.fetch_current_report()
    # Read before a theo_publish write, written after it: the UPDATE matches no row.
    db.row = (json.dumps({"report": "old"}),)
    with pytest.raises(tp.JournalledPaperError, match="nothing written"):
        module.write_new_report("new")
    assert (db.commits, db.rollbacks) == (0, 1)
    assert len(db.sql) == 3
    assert all(CLAUSE in sql for sql in db.sql)
