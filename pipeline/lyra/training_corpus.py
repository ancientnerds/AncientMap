"""Durable capture of what Theo reads and how it reasons.

The research pipeline currently discards two things that are expensive to
produce and impossible to recover afterwards:

* **Source texts.** ``content_fetch`` downloads a whole page, truncates it to
  the prompt cap and keeps the remainder nowhere. What survives a run is a
  URL in the references list.
* **Intermediate reasoning.** Angle findings, specialist analyses, synthesis,
  debate and the curator's structured output live on the in-memory
  ``ResearchState`` and die with the run; only the finished paper is stored.

Both are the raw material for a future Ancient Nerds domain model, so this
module writes them to ``theo_source_archive`` / ``research_artifacts`` at the
exact points where they would otherwise be dropped.

Two rules hold everywhere in here:

1. **The LLM path is not touched.** Prompt caps, ``_SKIP_DOMAINS`` and quota
   behaviour are identical whether or not this module runs. The archive keeps
   the *uncapped* text; the prompt keeps its cap.
2. **Provenance travels with the row.** Licence, licence origin and the
   machine-readable TDM reservation found at fetch time are stored per
   document, modelled on ``source_records``. A reservation is not
   reconstructable later, which is why it is captured on the spot.

Nothing in the system reads these tables back for control flow.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib import robotparser

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Uncapped in the sense that the prompt cap does not apply — but a single
# pathological page must not become a 50 MB row.
MAX_TEXT_CHARS = 500_000
MAX_HTML_CHARS = 2_000_000

# A source archived within this window is not re-fetched for the corpus.
# Without a window the (source_id, content_hash) versioning would be dead
# code: a page that changes after first capture would never be seen again.
REFETCH_AFTER_DAYS = 90

# Licences that follow from the domain alone. Deliberately tiny — a wrong
# licence tag is worse than an empty one, and empty is handled explicitly by
# the export policy (docs/TRAINING_DATA_POLICY.md).
_DOMAIN_LICENSES: tuple[tuple[str, str], ...] = (
    ("wikipedia.org", "CC BY-SA 4.0"),
    ("wikisource.org", "CC BY-SA 4.0"),
    ("wikimedia.org", "CC BY-SA 4.0"),
    ("wikidata.org", "CC0 1.0"),
)

# Marks rows whose text is the adapter-provided abstract rather than a fetched
# page. Paired with http_status = 0.
SNIPPET_CONTENT_TYPE = "adapter/snippet"


# Lazy + wrapped, mirroring thinking_log: keeps pipeline.database out of the
# import graph at module load and gives tests a seam.
def _session_factory():
    from pipeline.database import get_session

    return get_session()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@dataclass
class ArchiveDocument:
    """One captured source text, ready to be written to theo_source_archive."""

    source_id: str
    url: str
    domain: str = ""
    title: str = ""
    full_text: str = ""
    raw_html: str = ""
    http_status: int = 0
    content_type: str = ""
    archive_only: bool = False
    source_api: str = ""
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    reliability_tier: int = 0
    license: str = ""
    license_source: str = ""
    tdm_opt_out: bool = False
    tdm_signal: str = ""


def resolve_license(domain: str, adapter_license: str) -> tuple[str, str]:
    """Return (licence, origin) for a source. Empty origin means unresolved.

    Adapter knowledge wins over the domain table: OpenAlex and Europeana
    report the actual per-record licence, which can differ from whatever the
    hosting domain generally uses.
    """
    if adapter_license:
        return adapter_license, "adapter"
    host = (domain or "").lower().removeprefix("www.")
    for suffix, license_name in _DOMAIN_LICENSES:
        if host == suffix or host.endswith("." + suffix):
            return license_name, "domain_map"
    return "", ""


def document_from_source(
    source: Any,
    *,
    full_text: str,
    raw_html: str = "",
    http_status: int = 0,
    content_type: str = "",
    archive_only: bool = False,
    tdm_opt_out: bool = False,
    tdm_signal: str = "",
) -> ArchiveDocument:
    """Build an archive document from a CitationRegistry ``CitedSource``."""
    license_name, license_origin = resolve_license(source.domain, getattr(source, "license", ""))
    return ArchiveDocument(
        source_id=source.id,
        url=source.url,
        domain=source.domain,
        title=source.title,
        full_text=full_text,
        raw_html=raw_html,
        http_status=http_status,
        content_type=content_type,
        archive_only=archive_only,
        source_api=getattr(source, "source_api", ""),
        doi=source.doi,
        authors=list(source.authors or []),
        venue=source.venue,
        reliability_tier=source.reliability_tier,
        license=license_name,
        license_source=license_origin,
        tdm_opt_out=tdm_opt_out,
        tdm_signal=tdm_signal,
    )


def already_archived(source_ids: list[str]) -> set[str]:
    """Subset of ``source_ids`` captured within the re-fetch window."""
    if not source_ids:
        return set()
    with _session_factory() as session:
        rows = session.execute(
            text("""
                SELECT DISTINCT source_id FROM theo_source_archive
                WHERE source_id = ANY(:ids)
                  AND fetched_at > NOW() - make_interval(days => :days)
            """),
            {"ids": list(source_ids), "days": REFETCH_AFTER_DAYS},
        ).fetchall()
    return {row.source_id for row in rows}


def archive_documents(documents: list[ArchiveDocument]) -> int:
    """Insert captured documents. Returns the number of new rows.

    Same source, same text is a no-op; same source, changed text is a new
    version. Compression happens here so callers can stay on the event loop
    and hand this whole function to a worker thread.
    """
    if not documents:
        return 0

    params: list[dict[str, Any]] = []
    for doc in documents:
        body = doc.full_text[:MAX_TEXT_CHARS]
        # A reservation row records that we looked and were told not to keep
        # the text — the finding itself is the point, so it is stored without
        # a body.
        if doc.tdm_opt_out:
            body = ""
        html_gz = None
        if body and doc.raw_html:
            html_gz = gzip.compress(doc.raw_html[:MAX_HTML_CHARS].encode("utf-8", "replace"))
        params.append(
            {
                "source_id": doc.source_id,
                "content_hash": hashlib.sha256(body.encode()).hexdigest() if body else "",
                "url": doc.url,
                "domain": doc.domain,
                "title": doc.title[:2000],
                "full_text": body or None,
                "raw_html_gz": html_gz,
                "text_chars": len(body),
                "http_status": doc.http_status,
                "content_type": doc.content_type,
                "archive_only": doc.archive_only,
                "source_api": doc.source_api,
                "doi": doc.doi,
                "authors": json.dumps(doc.authors) if doc.authors else None,
                "venue": doc.venue[:500],
                "reliability_tier": doc.reliability_tier,
                "license": doc.license,
                "license_source": doc.license_source,
                "tdm_opt_out": doc.tdm_opt_out,
                "tdm_signal": doc.tdm_signal,
                "tdm_checked": bool(doc.tdm_signal) or doc.tdm_opt_out,
            }
        )

    with _session_factory() as session:
        result = session.execute(
            text("""
                INSERT INTO theo_source_archive (
                    source_id, content_hash, url, domain, title, full_text, raw_html_gz,
                    text_chars, http_status, content_type, archive_only, source_api, doi,
                    authors, venue, reliability_tier, license, license_source,
                    tdm_opt_out, tdm_signal, tdm_checked_at
                ) VALUES (
                    :source_id, :content_hash, :url, :domain, :title, :full_text, :raw_html_gz,
                    :text_chars, :http_status, :content_type, :archive_only, :source_api, :doi,
                    CAST(:authors AS jsonb), :venue, :reliability_tier, :license, :license_source,
                    :tdm_opt_out, :tdm_signal, CASE WHEN :tdm_checked THEN NOW() END
                )
                ON CONFLICT (source_id, content_hash) DO NOTHING
            """),
            params,
        )
        session.commit()
    return result.rowcount if result.rowcount and result.rowcount > 0 else 0


# ---------------------------------------------------------------------------
# TDM reservations (§44b(3) UrhG / DSM Art. 4)
# ---------------------------------------------------------------------------

# Reservation checks are evaluated against the wildcard robots group: the
# conservative reading, and the only one that does not depend on which
# user-agent string the fetcher happens to send.
_ROBOTS_AGENT = "*"


@dataclass
class DomainPolicy:
    """Reservation signals published by one host."""

    robots: robotparser.RobotFileParser | None = None
    reserved_paths: tuple[str, ...] = ()
    check_error: str = ""


@dataclass
class TdmVerdict:
    opt_out: bool = False
    signal: str = ""


def parse_robots(body: str) -> robotparser.RobotFileParser:
    """Parse robots.txt content. No network access — the caller fetches."""
    parser = robotparser.RobotFileParser()
    parser.parse(body.splitlines())
    return parser


def parse_tdmrep(body: str) -> tuple[str, ...]:
    """Path prefixes carrying an active reservation in a tdmrep.json document.

    Accepts both the bare list and the ``{"tdm": [...]}`` wrapper seen in the
    wild. Entries without a reservation flag are ignored.
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return ()
    if isinstance(data, dict):
        data = data.get("tdm") or data.get("tdmrep") or []
    if not isinstance(data, list):
        return ()
    paths: list[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if not entry.get("tdm-reservation"):
            continue
        location = entry.get("location") or "/"
        if not isinstance(location, str):
            continue
        paths.append("/" if location in ("*", "") else location)
    return tuple(paths)


def reservation_for(url: str, policy: DomainPolicy) -> TdmVerdict:
    """Verdict for one URL against its host's published policy."""
    if policy.check_error:
        # Recorded rather than swallowed: a row with signal 'check_failed' is
        # queryable, an unchecked row silently claiming "no reservation" is not.
        return TdmVerdict(opt_out=False, signal="check_failed")
    path = urllib.parse.urlsplit(url).path or "/"
    if any(path.startswith(prefix) for prefix in policy.reserved_paths):
        return TdmVerdict(opt_out=True, signal="tdmrep")
    if policy.robots is not None and not policy.robots.can_fetch(_ROBOTS_AGENT, url):
        return TdmVerdict(opt_out=True, signal="robots_txt")
    return TdmVerdict(opt_out=False, signal="")


def html_reserves_tdm(html: str) -> bool:
    """True when the document carries a ``tdm-reservation`` meta tag."""
    lowered = html[:20_000].lower()
    idx = lowered.find('name="tdm-reservation"')
    if idx == -1:
        idx = lowered.find("name='tdm-reservation'")
    if idx == -1:
        return False
    tag_end = lowered.find(">", idx)
    tag = lowered[idx : tag_end if tag_end != -1 else idx + 200]
    return 'content="0"' not in tag and "content='0'" not in tag


# ---------------------------------------------------------------------------
# Reasoning artifacts
# ---------------------------------------------------------------------------


def save_artifact(request_id: str | None, kind: str, payload: Any, ref: str = "") -> None:
    """Store one intermediate reasoning artifact.

    ``request_id`` is None for passes that belong to no research run (curator,
    miner). ``ref`` scopes the kind — an angle id, or the pass date.
    """
    with _session_factory() as session:
        session.execute(
            text("""
                INSERT INTO research_artifacts (request_id, kind, ref, payload)
                VALUES (:request_id, :kind, :ref, CAST(:payload AS jsonb))
            """),
            {
                "request_id": request_id or None,
                "kind": kind,
                "ref": ref[:200],
                "payload": json.dumps(payload, default=str),
            },
        )
        session.commit()


def _registry_payload(registry: Any) -> dict:
    """Registry structure without the snippet bodies.

    The snippets are the *capped* texts the LLM actually saw. Storing them
    here as well would duplicate megabytes per run, so the bodies live in
    theo_source_archive under the same source_id and this payload keeps the
    structure: which sources existed, what backed each claim, and which
    reference number each source ended up with.
    """
    sources = []
    for source in registry.sources.values():
        entry = {k: v for k, v in asdict(source).items() if k != "snippet"}
        entry["snippet_chars"] = len(source.snippet)
        sources.append(entry)
    return {
        "sources": sources,
        "claims": [asdict(claim) for claim in registry.claims],
        "reference_numbers": dict(registry.reference_numbers),
    }


def record_run_links(request_id: str, links: list[dict]) -> int:
    """Store which sources a run saw, under which query, and which it cited."""
    if not links:
        return 0
    with _session_factory() as session:
        result = session.execute(
            text("""
                INSERT INTO theo_source_archive_runs
                    (request_id, source_id, angle_id, search_query, cited)
                VALUES (:request_id, :source_id, :angle_id, :search_query, :cited)
                ON CONFLICT (request_id, source_id) DO UPDATE
                    SET angle_id = EXCLUDED.angle_id,
                        search_query = EXCLUDED.search_query,
                        cited = EXCLUDED.cited
            """),
            [{"request_id": request_id, **link} for link in links],
        )
        session.commit()
    return result.rowcount if result.rowcount and result.rowcount > 0 else 0


def persist_run_corpus(state: Any, request_id: str) -> dict:
    """Close out a run: archive un-fetched source texts, link them, store the registry.

    Runs at the very end of a run — successful or failed — which is the only
    point where the citation state is final (reference pruning happens during
    presentation) and every source the run touched is known.
    """
    registry = getattr(state, "registry", None)
    if registry is None or not registry.sources:
        return {"documents": 0, "links": 0}

    angle_of: dict[str, str] = {}
    query_of: dict[str, str] = {}
    for angle in getattr(state, "angles", None) or []:
        for sid in angle.source_ids:
            angle_of.setdefault(sid, angle.id)
    for sid, source in registry.sources.items():
        if source.search_query:
            query_of[sid] = source.search_query

    # Sources whose page was fetched are already archived with their full
    # text; everything else contributes the adapter abstract, so the archive
    # holds the text of every source exactly once.
    known = already_archived(list(registry.sources))
    documents = [
        document_from_source(
            source,
            full_text=source.snippet,
            content_type=SNIPPET_CONTENT_TYPE,
        )
        for sid, source in registry.sources.items()
        if sid not in known and source.snippet
    ]
    written = archive_documents(documents)

    # Standalone passes (request_id="") have no run identity worth keying on —
    # their documents are archived, but they contribute no run linkage.
    linked = 0
    if request_id:
        cited = set(registry.reference_numbers)
        linked = record_run_links(
            request_id,
            [
                {
                    "source_id": sid,
                    "angle_id": angle_of.get(sid, ""),
                    "search_query": query_of.get(sid, "")[:2000],
                    "cited": sid in cited,
                }
                for sid in registry.sources
            ],
        )

    save_artifact(request_id, "citation_registry", _registry_payload(registry))
    return {"documents": written, "links": linked}


# ---------------------------------------------------------------------------
# Size reporting (consumed by the quota watchdog)
# ---------------------------------------------------------------------------


def corpus_size_report() -> dict:
    """Total on-disk size and row counts of the corpus tables."""
    with _session_factory() as session:
        row = session.execute(
            text("""
                SELECT
                    pg_total_relation_size('theo_source_archive')
                      + pg_total_relation_size('theo_source_archive_runs')
                      + pg_total_relation_size('research_artifacts')
                      + pg_total_relation_size('thinking_log_archive')
                      + pg_total_relation_size('research_requests_archive') AS total_bytes,
                    (SELECT COUNT(*) FROM theo_source_archive) AS documents,
                    (SELECT COUNT(*) FROM research_artifacts) AS artifacts
            """)
        ).fetchone()
    return {
        "total_bytes": int(row.total_bytes or 0),
        "documents": int(row.documents or 0),
        "artifacts": int(row.artifacts or 0),
    }
