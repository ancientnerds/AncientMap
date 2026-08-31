"""Content fetch — the prompt path and the corpus path must stay independent.

The archive rides along on downloads the pipeline performs anyway. These
tests pin the two guarantees that make that safe: the LLM keeps seeing
exactly the capped text it saw before, and a failing archive can never fail a
research run.
"""

import asyncio

import pytest

from pipeline.lyra.handlers import content_fetch as cf
from pipeline.lyra.research_events import EventBus
from pipeline.lyra.research_state import ResearchAngle, ResearchState
from pipeline.lyra.training_corpus import DomainPolicy


@pytest.fixture
def archived():
    """Documents handed to the archive during a test."""
    return []


@pytest.fixture
def handler(monkeypatch, archived):
    """A ContentFetchHandler wired to fakes instead of network and database."""
    # No request_id: EventBus.emit flushes run progress to the database when
    # one is set, which these tests neither need nor have a database for.
    state = ResearchState(question="test")
    state.angles = [ResearchAngle(id="a1", topic="Ur", description="")]
    handler = cf.ContentFetchHandler(state, EventBus(state=state), asyncio.Semaphore(4))

    monkeypatch.setattr(cf, "already_archived", lambda ids: set())
    monkeypatch.setattr(cf, "archive_documents", lambda docs: archived.extend(docs) or len(docs))
    monkeypatch.setattr(cf, "_resolve_max_content_chars", lambda: 10)

    async def _no_reservation(domain):
        return DomainPolicy()

    monkeypatch.setattr(cf.ContentFetchHandler, "_domain_policy", staticmethod(_no_reservation))

    async def _page(sid, url):
        return cf._Page(
            sid=sid,
            url=url,
            text="FULL PAGE TEXT, well beyond the prompt cap",
            html="<html><body>FULL PAGE TEXT</body></html>",
            status=200,
            content_type="text/html",
        )

    monkeypatch.setattr(cf.ContentFetchHandler, "_fetch_one", staticmethod(_page))
    return handler


def _add_source(handler, url, snippet):
    sid = handler.state.registry.register_source(url=url, title="t", snippet=snippet)
    handler.state.angles[0].source_ids.append(sid)
    return sid


async def _run(handler):
    await handler._on_sources_audited(cf.SourcesAudited(angle_id="a1", accepted=1, rejected=0))


async def test_prompt_gets_capped_text_archive_gets_full_text(handler, archived):
    sid = _add_source(handler, "https://x.example/a", "short")

    await _run(handler)

    # The LLM sees the cap; the corpus keeps everything.
    assert handler.state.registry.get_reference(sid).snippet == "FULL PAGE "
    assert len(archived) == 1
    assert archived[0].full_text == "FULL PAGE TEXT, well beyond the prompt cap"
    assert archived[0].archive_only is False


async def test_source_with_substantial_snippet_is_left_alone(handler, monkeypatch, archived):
    """The >=500-char rule governs the prompt path and is not relaxed."""
    long_snippet = "x" * 600
    sid = _add_source(handler, "https://x.example/a", long_snippet)

    await _run(handler)

    assert handler.state.registry.get_reference(sid).snippet == long_snippet
    assert archived == []  # extra fetching is off by default


async def test_extra_fetch_archives_wikipedia_without_touching_the_prompt(
    handler, monkeypatch, archived
):
    """Wikipedia is worthless in a prompt and valuable as licensed corpus text."""
    monkeypatch.setattr(cf, "_resolve_archive_settings", lambda: (True, 800))
    sid = _add_source(handler, "https://en.wikipedia.org/wiki/Ur", "lead paragraph")

    await _run(handler)

    assert handler.state.registry.get_reference(sid).snippet == "lead paragraph"
    assert [doc.source_id for doc in archived] == [sid]
    assert archived[0].archive_only is True
    assert archived[0].license == "CC BY-SA 4.0"


async def test_reserved_host_is_not_fetched_for_the_archive(handler, monkeypatch, archived):
    monkeypatch.setattr(cf, "_resolve_archive_settings", lambda: (True, 800))

    async def _reserved(domain):
        return DomainPolicy(robots=cf.parse_robots("User-agent: *\nDisallow: /"))

    monkeypatch.setattr(cf.ContentFetchHandler, "_domain_policy", staticmethod(_reserved))
    _add_source(handler, "https://en.wikipedia.org/wiki/Ur", "lead paragraph")

    await _run(handler)

    assert archived == []


async def test_reserved_host_on_the_prompt_path_is_stored_without_a_body(
    handler, monkeypatch, archived
):
    """A page the prompt path fetches anyway still respects the reservation.

    The finding itself is recorded — it is the evidence that we looked, and it
    cannot be reconstructed later.
    """

    async def _reserved(domain):
        return DomainPolicy(robots=cf.parse_robots("User-agent: *\nDisallow: /"))

    monkeypatch.setattr(cf.ContentFetchHandler, "_domain_policy", staticmethod(_reserved))
    _add_source(handler, "https://x.example/a", "short")

    await _run(handler)

    assert len(archived) == 1
    assert archived[0].tdm_opt_out is True
    assert archived[0].tdm_signal == "robots_txt"


async def test_archive_failure_never_fails_the_run(handler, monkeypatch):
    """A broken corpus write costs a document, never a research run."""

    def _boom(docs):
        raise RuntimeError("archive table is gone")

    monkeypatch.setattr(cf, "archive_documents", _boom)
    sid = _add_source(handler, "https://x.example/a", "short")

    await _run(handler)

    assert handler.state.registry.get_reference(sid).snippet == "FULL PAGE "
    assert not handler.state.error
    assert any("ARCHIVE WRITE FAILED" in entry["msg"] for entry in handler.state.debug_log)
