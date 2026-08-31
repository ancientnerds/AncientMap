"""Training corpus — provenance, TDM reservations, run close-out.

Covers the parts that decide what a future training export may legally and
usefully contain: which licence a document carries, whether the host reserved
its text against text-and-data-mining, and whether the run close-out records
the citation state AFTER the presentation stage has pruned references.
"""

from types import SimpleNamespace

import pytest

from pipeline.lyra import training_corpus as tc
from pipeline.lyra.theo_citations import CitationRegistry

# ---------------------------------------------------------------------------
# Licence resolution
# ---------------------------------------------------------------------------


def test_adapter_licence_wins_over_domain():
    """A per-record licence beats the domain table — they can disagree."""
    assert tc.resolve_license("en.wikipedia.org", "CC BY 4.0") == ("CC BY 4.0", "adapter")


def test_domain_licence_applies_to_subdomains():
    assert tc.resolve_license("de.wikipedia.org", "") == ("CC BY-SA 4.0", "domain_map")
    assert tc.resolve_license("wikipedia.org", "") == ("CC BY-SA 4.0", "domain_map")


def test_unknown_domain_stays_unresolved():
    """Never guess: an empty licence is excluded from exports by policy."""
    assert tc.resolve_license("some-blog.example", "") == ("", "")


def test_lookalike_domain_does_not_inherit_licence():
    assert tc.resolve_license("notwikipedia.org", "") == ("", "")


# ---------------------------------------------------------------------------
# TDM reservations (§44b(3) UrhG)
# ---------------------------------------------------------------------------


def test_tdmrep_reserves_matching_path_only():
    paths = tc.parse_tdmrep(
        '[{"location": "/archive", "tdm-reservation": 1},'
        ' {"location": "/open", "tdm-reservation": 0}]'
    )
    policy = tc.DomainPolicy(reserved_paths=paths)
    assert tc.reservation_for("https://x.example/archive/a", policy).opt_out is True
    assert tc.reservation_for("https://x.example/archive/a", policy).signal == "tdmrep"
    assert tc.reservation_for("https://x.example/open/b", policy).opt_out is False


def test_tdmrep_accepts_wrapped_document():
    assert tc.parse_tdmrep('{"tdm": [{"location": "*", "tdm-reservation": 1}]}') == ("/",)


def test_tdmrep_ignores_malformed_document():
    assert tc.parse_tdmrep("not json") == ()
    assert tc.parse_tdmrep('{"unrelated": true}') == ()


def test_robots_disallow_counts_as_reservation():
    policy = tc.DomainPolicy(robots=tc.parse_robots("User-agent: *\nDisallow: /private"))
    assert tc.reservation_for("https://x.example/private/p", policy).signal == "robots_txt"
    assert tc.reservation_for("https://x.example/public/p", policy).opt_out is False


def test_unreachable_host_is_recorded_not_assumed():
    """An unchecked document must never look like a checked one."""
    verdict = tc.reservation_for("https://x.example/a", tc.DomainPolicy(check_error="timeout"))
    assert verdict.opt_out is False
    assert verdict.signal == "check_failed"


@pytest.mark.parametrize(
    ("html", "reserved"),
    [
        ('<meta name="tdm-reservation" content="1">', True),
        ("<meta name='tdm-reservation' content='1'>", True),
        ('<meta name="tdm-reservation" content="0">', False),
        ('<meta name="description" content="1">', False),
    ],
)
def test_meta_tag_reservation(html, reserved):
    assert tc.html_reserves_tdm(html) is reserved


# ---------------------------------------------------------------------------
# Document construction
# ---------------------------------------------------------------------------


def test_document_carries_source_provenance():
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://en.wikipedia.org/wiki/Ur",
        title="Ur",
        snippet="short",
        doi="10.1/x",
        authors=["Woolley, L."],
        venue="Antiquity",
        source_api="wikipedia",
    )
    doc = tc.document_from_source(
        registry.get_reference(sid),
        full_text="the full page",
        http_status=200,
        content_type="text/html",
    )
    assert doc.source_id == sid
    assert doc.doi == "10.1/x"
    assert doc.authors == ["Woolley, L."]
    assert doc.source_api == "wikipedia"
    # Wikipedia has no adapter licence but a known domain licence.
    assert doc.license == "CC BY-SA 4.0"
    assert doc.license_source == "domain_map"


# ---------------------------------------------------------------------------
# Registry payload
# ---------------------------------------------------------------------------


def test_registry_payload_drops_snippet_bodies():
    """Snippet text lives in theo_source_archive; the artifact keeps structure.

    Storing both would duplicate megabytes per run — the join key is source_id.
    """
    registry = CitationRegistry()
    sid = registry.register_source(url="https://x.example/a", title="A", snippet="x" * 5000)
    registry.add_claim("A claim", [sid])
    registry.assign_reference_number(sid)

    payload = tc._registry_payload(registry)

    source = payload["sources"][0]
    assert "snippet" not in source
    assert source["snippet_chars"] == 5000
    assert payload["claims"][0]["claim_text"] == "A claim"
    assert payload["reference_numbers"] == {sid: 1}


# ---------------------------------------------------------------------------
# Run close-out
# ---------------------------------------------------------------------------


class _Recorder:
    """Captures what persist_run_corpus would write."""

    def __init__(self):
        self.documents = []
        self.links = []
        self.artifacts = []


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(tc, "already_archived", lambda ids: set())
    monkeypatch.setattr(
        tc, "archive_documents", lambda docs: rec.documents.extend(docs) or len(docs)
    )
    monkeypatch.setattr(
        tc,
        "record_run_links",
        lambda request_id, links: rec.links.extend(links) or len(links),
    )
    monkeypatch.setattr(
        tc,
        "save_artifact",
        lambda request_id, kind, payload, ref="": rec.artifacts.append((kind, payload)),
    )
    return rec


def _state_with(registry, angle_sources):
    angle = SimpleNamespace(id="a1", source_ids=list(angle_sources))
    return SimpleNamespace(registry=registry, angles=[angle])


def test_run_close_out_records_query_and_citation_state(recorder):
    registry = CitationRegistry()
    cited = registry.register_source(
        url="https://x.example/cited", title="C", snippet="abstract", search_query="ur ziggurat"
    )
    seen = registry.register_source(
        url="https://x.example/seen", title="S", snippet="abstract", search_query="ur pottery"
    )
    # Only the first source survived into the finished paper.
    registry.assign_reference_number(cited)

    stats = tc.persist_run_corpus(_state_with(registry, [cited, seen]), "req-1")

    assert stats == {"documents": 2, "links": 2}
    by_id = {link["source_id"]: link for link in recorder.links}
    assert by_id[cited]["cited"] is True
    assert by_id[cited]["search_query"] == "ur ziggurat"
    assert by_id[seen]["cited"] is False
    assert by_id[seen]["angle_id"] == "a1"
    assert [kind for kind, _ in recorder.artifacts] == ["citation_registry"]


def test_already_archived_sources_are_not_re_stored(recorder, monkeypatch):
    """A fetched page is already in the archive with its full text.

    Writing the capped snippet again afterwards would shadow it with a worse
    copy of the same document.
    """
    registry = CitationRegistry()
    fetched = registry.register_source(url="https://x.example/a", title="A", snippet="page text")
    fresh = registry.register_source(url="https://x.example/b", title="B", snippet="abstract")
    monkeypatch.setattr(tc, "already_archived", lambda ids: {fetched})

    tc.persist_run_corpus(_state_with(registry, [fetched, fresh]), "req-2")

    assert [doc.source_id for doc in recorder.documents] == [fresh]
    # The link is still recorded for both — provenance covers every source seen.
    assert len(recorder.links) == 2


def test_standalone_pass_archives_documents_but_no_run_links(recorder):
    """request_id='' has no run identity worth keying on."""
    registry = CitationRegistry()
    registry.register_source(url="https://x.example/a", title="A", snippet="abstract")

    stats = tc.persist_run_corpus(_state_with(registry, []), "")

    assert stats["documents"] == 1
    assert stats["links"] == 0
