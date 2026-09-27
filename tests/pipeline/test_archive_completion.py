"""Archive completion: the full text of every source a moderated claim cites (spec 2.3).

HTTP runs through httpx.MockTransport; the database seams (best_archive_rows,
archive_documents, record_run_links, load_transcript) are replaced by recorders.
"""

from __future__ import annotations

import asyncio
import io

import httpx
import pytest

from pipeline.lyra import archive_completion as ac
from pipeline.lyra.research_state import ResearchAngle
from pipeline.lyra.theo_citations import CitationRegistry
from pipeline.lyra.training_corpus import SNIPPET_CONTENT_TYPE, DomainPolicy

REQ = "11111111-2222-3333-4444-555555555555"
MISSING_SID = "deadbeef0000"


def minimal_pdf(text: str) -> bytes:
    """A one-page PDF whose text pypdf extracts (verified with pypdf 6.19.0)."""
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


# --- pure helpers -------------------------------------------------------------


def test_wikipedia_goes_through_the_rest_html_endpoint():
    assert ac.resolve_fetch_url("https://en.wikipedia.org/wiki/G%C3%B6bekli_Tepe") == (
        "wikipedia",
        "https://en.wikipedia.org/api/rest_v1/page/html/G%C3%B6bekli_Tepe",
    )


def test_doi_and_ordinary_pages_are_plain_web_fetches():
    assert ac.resolve_fetch_url("https://doi.org/10.1000/xyz") == (
        "web",
        "https://doi.org/10.1000/xyz",
    )
    assert ac.resolve_fetch_url("https://en.wikipedia.org/w/index.php?title=X") == (
        "web",
        "https://en.wikipedia.org/w/index.php?title=X",
    )


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://youtu.be/dQw4w9WgXcQ?t=30", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Not 11 characters: YOUTUBE_ID_RE (theo_publishing, the one definition) refuses it.
        ("https://youtu.be/dQw4w9WgXc", None),
        ("https://www.youtube.com/channel/UC123", None),
        ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ],
)
def test_youtube_video_id(url, video_id):
    assert ac.youtube_video_id(url) == video_id
    assert (ac.resolve_fetch_url(url)[0] == "youtube") is (video_id is not None)


def test_limits_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("THEO_ARCHIVE_COMPLETION_MAX_S", raising=False)
    monkeypatch.delenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", raising=False)
    assert ac.archive_completion_limits() == (1800.0, 4)
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_MAX_S", "600")
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "2")
    assert ac.archive_completion_limits() == (600.0, 2)
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "0")
    with pytest.raises(ValueError, match="at least 1"):
        ac.archive_completion_limits()
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "2")
    # Above the worker's stall grace (2700 s) the guard would kill a finished run.
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_MAX_S", "3000")
    with pytest.raises(ValueError, match="between 1 and 2400 s"):
        ac.archive_completion_limits()


def test_pdf_text_is_extracted():
    pytest.importorskip("pypdf")
    assert "Baalbek trilithon weighs 800 tonnes" in ac.pdf_text(
        minimal_pdf("Baalbek trilithon weighs 800 tonnes")
    )


def test_unreadable_pdf_is_a_recorded_failure():
    pytest.importorskip("pypdf")
    with pytest.raises(ac.ArchiveFetchError, match="unreadable PDF"):
        ac.pdf_text(b"%PDF-1.4 this is not a pdf")


async def test_fetch_document_reads_pdf_and_rejects_other_binaries():
    pytest.importorskip("pypdf")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".pdf"):
            return httpx.Response(
                200,
                content=minimal_pdf("Roman capstans"),
                headers={"content-type": "application/pdf"},
            )
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        page = await ac.fetch_document(client, "https://a.example/paper.pdf")
        assert "Roman capstans" in page.text
        assert page.html == ""
        with pytest.raises(ac.ArchiveFetchError, match="unsupported content type"):
            await ac.fetch_document(client, "https://a.example/figure.png")


# --- the whole step ---------------------------------------------------------


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == "https://site.example/page":
        return httpx.Response(
            200, html="<html><body><p>Baalbek quarry blocks weigh 1,000 tonnes.</p></body></html>"
        )
    if url == "https://en.wikipedia.org/api/rest_v1/page/html/Baalbek":
        return httpx.Response(
            200, html="<html><body><p>Baalbek is a city in Lebanon.</p></body></html>"
        )
    if url == "https://doi.org/10.1000/xyz":
        return httpx.Response(302, headers={"location": "https://publisher.example/article"})
    if url == "https://publisher.example/article":
        return httpx.Response(403, html="blocked")
    if url == "https://reserved.example/paper":
        return httpx.Response(200, html="<html><body><p>Reserved text body.</p></body></html>")
    if url == "https://broken.example/x":
        return httpx.Response(500, text="oops")
    raise AssertionError(f"unexpected fetch {url}")


class _Recorder:
    def __init__(self) -> None:
        self.documents: list = []
        self.links: list = []


@pytest.fixture
def seams(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(
        ac, "archive_documents", lambda docs: rec.documents.extend(docs) or len(docs)
    )
    monkeypatch.setattr(
        ac, "record_run_links", lambda request_id, links: rec.links.extend(links) or len(links)
    )
    monkeypatch.setattr(
        ac,
        "load_transcript",
        lambda video_id: "Transcript of the talk." if video_id == "dQw4w9WgXcQ" else "",
    )

    async def policy(host: str) -> DomainPolicy:
        return DomainPolicy(reserved_paths=("/",)) if host == "reserved.example" else DomainPolicy()

    monkeypatch.setattr(ac, "fetch_domain_policy", policy)
    monkeypatch.setattr(
        ac,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(_handler), follow_redirects=True),
    )
    return rec


def _registry_and_ids():
    registry = CitationRegistry()
    ids = {
        "page": registry.register_source(url="https://site.example/page", title="Page", snippet=""),
        "wiki": registry.register_source(
            url="https://en.wikipedia.org/wiki/Baalbek", title="Baalbek", snippet=""
        ),
        "doi": registry.register_source(
            url="https://doi.org/10.1000/xyz", title="Paper", snippet=""
        ),
        "video": registry.register_source(
            url="https://youtu.be/dQw4w9WgXcQ?t=30", title="Talk", snippet=""
        ),
        "known": registry.register_source(
            url="https://old.example/known", title="Known", snippet=""
        ),
        "reserved": registry.register_source(
            url="https://reserved.example/paper", title="Reserved", snippet=""
        ),
        "broken": registry.register_source(
            url="https://broken.example/x", title="Broken", snippet="An abstract."
        ),
    }
    return registry, ids


async def test_every_cited_source_ends_classified_and_recorded(seams, monkeypatch):
    registry, ids = _registry_and_ids()
    monkeypatch.setattr(
        ac,
        "best_archive_rows",
        lambda source_ids, *, with_text: {
            ids["known"]: {
                "source_id": ids["known"],
                "url": "https://old.example/known",
                "content_type": "text/html",
                "text_chars": 5000,
                "fetched_at": None,
                "tdm_opt_out": False,
                "full_text": None,
            }
        },
    )
    moderated = {"final_claims": [{"claim": "c", "source_ids": [*ids.values(), MISSING_SID]}]}
    angles = [
        ResearchAngle(id="ang1", topic="t", description="d", source_ids=[ids["page"], ids["wiki"]])
    ]

    stats = await ac.complete_archive(
        REQ, registry, moderated, angles, max_seconds=30, concurrency=3
    )

    assert (
        stats.cited_sources,
        stats.full_text,
        stats.tdm_reserved,
        stats.abstract_only,
        stats.missing,
    ) == (
        8,
        4,
        1,
        1,
        2,
    )
    assert stats.timed_out is False
    reasons = {failure["source_id"]: failure["reason"] for failure in stats.failures}
    assert reasons[MISSING_SID] == "source id is not in the citation registry"
    assert reasons[ids["doi"]].startswith("HTTP 403 from https://publisher.example/article")
    assert reasons[ids["broken"]].startswith("HTTP 500")
    assert set(reasons) == {MISSING_SID, ids["doi"], ids["broken"]}

    documents = {doc.source_id: doc for doc in seams.documents}
    assert set(documents) == {
        ids["page"],
        ids["wiki"],
        ids["video"],
        ids["reserved"],
        ids["broken"],
    }
    assert documents[ids["page"]].full_text == "Baalbek quarry blocks weigh 1,000 tonnes."
    assert documents[ids["wiki"]].full_text == "Baalbek is a city in Lebanon."
    assert documents[ids["video"]].content_type == ac.TRANSCRIPT_CONTENT_TYPE
    assert documents[ids["reserved"]].tdm_opt_out is True
    assert documents[ids["reserved"]].tdm_signal == "tdmrep"
    assert documents[ids["broken"]].content_type == SNIPPET_CONTENT_TYPE
    assert documents[ids["broken"]].full_text == "An abstract."

    links = {link["source_id"]: link for link in seams.links}
    assert set(links) == set(ids.values())
    assert all(link["cited"] is True for link in links.values())
    assert links[ids["page"]]["angle_id"] == "ang1"
    assert links[ids["doi"]]["angle_id"] == ""


async def test_time_budget_is_enforced_and_recorded(seams, monkeypatch):
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, html="<p>late</p>")

    monkeypatch.setattr(
        ac,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(slow), follow_redirects=True),
    )
    monkeypatch.setattr(ac, "best_archive_rows", lambda source_ids, *, with_text: {})
    registry = CitationRegistry()
    sid = registry.register_source(url="https://slow.example/p", title="Slow", snippet="")
    moderated = {"final_claims": [{"claim": "c", "source_ids": [sid]}]}

    stats = await ac.complete_archive(REQ, registry, moderated, [], max_seconds=0.1, concurrency=2)

    assert stats.timed_out is True
    assert stats.missing == 1
    assert stats.failures == [
        {
            "source_id": sid,
            "url": "https://slow.example/p",
            "reason": "archive completion time budget exhausted",
        }
    ]
