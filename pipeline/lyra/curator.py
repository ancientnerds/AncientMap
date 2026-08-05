"""Curator agent — the permanent researcher's nightly thinking pass (spec §3).

One structured LLM call Mon–Thu night: update the world model from new
papers, curate miner candidates into `connection` frontier nodes with
targeted questions, formulate falsifiable hypotheses, judge completed
hypothesis runs. Best-effort: any failure degrades to today's behavior, but
(2026-08-05 review) it must ALSO close the 20h schedule gate by writing a
thinking_log row — otherwise a dead LLM key reopens the nightly window on
every poll and the feeder retries the same failing pass for hours (I5/M17).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from pipeline.lyra.minimax_limiter import InsufficientQuotaError, QuotaExhaustedError
from pipeline.lyra.research_graph import is_junk_label, normalize_label

logger = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_PASS = 5
MAX_HYPOTHESES_PER_PASS = 3

# Budget for the LLM-facing user message and the claims section within it
# (spec §6 / I3 review). Claims are capped independently of the SQL LIMIT
# 100 in _gather_inputs — that limit bounds the DB read, this one bounds
# what actually ships in the prompt.
_MAX_USER_MESSAGE_CHARS = 60000
_MAX_CLAIMS_IN_MESSAGE = 60
_MAX_CLAIM_TEXT_CHARS = 300

_VALID_CLAIM_STATUSES = frozenset({"established", "contested", "refuted", "open"})
_VALID_OUTCOMES = frozenset({"confirmed", "refuted", "inconclusive"})

CURATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "node_label": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["established", "contested", "refuted", "open"],
                    },
                    "confidence": {"type": "number"},
                    "external_source_count": {"type": "integer"},
                    "paper_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "status"],
            },
        },
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "question"],
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "question"],
            },
        },
        "hypothesis_outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_label": {"type": "string"},
                    "outcome": {
                        "type": "string",
                        "enum": ["confirmed", "refuted", "inconclusive"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["node_label", "outcome"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["claim_updates", "connections", "hypotheses", "summary"],
}


def thinking_window_open(now_utc: datetime) -> bool:
    """True during the Mon-Thu 02:00-05:00 UTC thinking window (spec §3).
    Fri-Sun are research days (weekend batch gate) — the curator stays
    quiet. Shut ~93% of the week (12h / 168h), so callers should check this
    BEFORE any DB read — the common case must not touch the database.

    `now_utc` must be a timezone-aware UTC datetime.
    """
    if now_utc.weekday() > 3:
        return False
    return 2 <= now_utc.hour < 5


def thinking_pass_due(now_utc: datetime, last_pass_at: datetime | None) -> bool:
    """Nightly Mon–Thu 02:00–05:00 UTC, at most once per 20h. Fri–Sun are
    research days (weekend batch gate) — the curator stays quiet.

    Both `now_utc` and `last_pass_at` must be timezone-aware UTC datetimes
    (naive/aware comparison raises TypeError; callers own that contract).
    """
    if not thinking_window_open(now_utc):
        return False
    return last_pass_at is None or (now_utc - last_pass_at) >= timedelta(hours=20)


def _insert_topic_node(session, label: str, kind: str, question: str, rationale: str) -> bool:
    """Insert a curator-proposed frontier node. Returns True only when a row
    was actually written (I6 — trust rowcount, not "we tried to insert").

    ON CONFLICT DO NOTHING means an already-existing node (any status) keeps
    its current `question` untouched — a later curator pass re-proposing
    the same label must not clobber a stored question with new phrasing
    (M13, deliberate: the node may already be researching/explored with a
    question that shaped the run in progress or the completed paper).
    """
    if is_junk_label(label) or not question.strip():
        return False
    result = session.execute(
        text("""
            INSERT INTO research_nodes
                (id, label, norm_label, kind, status, created_from, source_signal,
                 question, created_at, updated_at)
            VALUES
                (:id, :label, :norm_label, :kind, 'frontier', 'curator', 2.0,
                 :question, NOW(), NOW())
            ON CONFLICT (kind, norm_label) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "label": label.strip()[:500],
            "norm_label": normalize_label(label)[:500],
            "kind": kind,
            "question": question.strip(),
        },
    )
    return result.rowcount == 1


def _link_connection_endpoints(session, conn_label: str) -> None:
    """A connection node 'A ↔ B' gets `connects` edges to A and B when those
    nodes exist — the Knowledge page draws the new line (spec data model).

    A label can exist as BOTH a topic and a site node (the miner's label
    bridge) — edges to both twins are deliberate: the connection anchors to
    every representation of its endpoint. Because a single INSERT..SELECT
    can therefore match MULTIPLE rows (both twins), the id must come from
    `gen_random_uuid()` in the SELECT list, not a single Python-side UUID
    bound once — a scalar `:id` bind reused across every matched row
    produces duplicate primary keys and rolls back the whole pass on
    exactly the multi-twin path this function exists for (C1, 2026-08-05
    review; pattern mirrors graph_full_ingest.py's edge()).
    """
    if "↔" not in conn_label:
        return
    conn_norm = normalize_label(conn_label)[:500]
    for part in conn_label.split("↔"):
        session.execute(
            text("""
                INSERT INTO research_edges (id, src, dst, kind, weight, created_at)
                SELECT gen_random_uuid(), c.id, t.id, 'connects', 1.0, NOW()
                FROM research_nodes c
                JOIN research_nodes t
                  ON t.norm_label = :part_norm AND t.kind != 'connection'
                WHERE c.kind = 'connection' AND c.norm_label = :conn_norm
                ON CONFLICT (src, dst, kind) DO NOTHING
            """),
            {
                "conn_norm": conn_norm,
                "part_norm": normalize_label(part)[:500],
            },
        )


def _apply_curator_output(session, out: dict) -> dict:
    """Apply a validated curator output. Pure DB writes, no LLM. Returns
    counters for the thinking log. Refuted claims never reopen.

    LLM output is untrusted even after schema coercion: `_coerce_to_schema`
    (minimax_shared.py) fills a missing required string with "" and does
    NOT check `enum` constraints, so an out-of-enum `status`/`outcome`
    reaches here unless this function enforces it itself (I4). Enforcing it
    also prevents a DB-level DataError (VARCHAR(20) truncation/constraint)
    from rolling back the whole pass on one bad item.
    """
    stats = {
        "claims": 0,
        "connections": 0,
        "hypotheses": 0,
        "outcomes": 0,
        "dropped": 0,
        "demoted": 0,
    }

    for cu in out.get("claim_updates", []):
        claim_text = (cu.get("text") or "").strip()
        status = cu.get("status")
        if not claim_text or status not in _VALID_CLAIM_STATUSES:
            stats["dropped"] += 1
            continue
        norm = normalize_label(claim_text)[:500]
        # Per-item savepoint: a single bad item (constraint violation,
        # DataError) must not roll back the entire nightly pass
        # (audit 2026-08-05).
        try:
            with session.begin_nested():
                existing = session.execute(
                    text("SELECT status FROM knowledge_claims WHERE norm_text = :norm LIMIT 1"),
                    {"norm": norm},
                ).fetchone()
                if existing and existing.status == "refuted":
                    continue  # refuted is terminal (spec §1)

                ext = int(cu.get("external_source_count") or 0)
                # Hard rule, not prompt-only (spec §5 / I8): "established"
                # requires >=2 independent external sources. The prompt asks
                # the LLM to respect this but nothing enforces it upstream —
                # enforce here.
                if status == "established" and ext < 2:
                    status = "open"
                    stats["demoted"] += 1

                paper_ids = json.dumps(cu.get("paper_ids") or [])
                if existing:
                    session.execute(
                        text("""
                            UPDATE knowledge_claims
                            SET status = :status, confidence = :conf,
                                external_source_count = :ext,
                                paper_ids = (SELECT COALESCE(jsonb_agg(DISTINCT e), '[]'::jsonb)
                                             FROM jsonb_array_elements(
                                                  COALESCE(paper_ids, '[]'::jsonb)
                                                  || CAST(:paper_ids AS jsonb)) e),
                                updated_at = NOW()
                            WHERE norm_text = :norm
                        """),
                        {
                            "status": status,
                            "conf": float(cu.get("confidence") or 0.5),
                            "ext": ext,
                            "paper_ids": paper_ids,
                            "norm": norm,
                        },
                    )
                else:
                    session.execute(
                        text("""
                            INSERT INTO knowledge_claims
                                (id, text, norm_text, node_id, status, confidence,
                                 external_source_count, paper_ids, created_at, updated_at)
                            VALUES
                                (:id, :text, :norm,
                                 (SELECT id FROM research_nodes
                                  WHERE norm_label = :node_norm LIMIT 1),
                                 :status, :conf, :ext, CAST(:paper_ids AS jsonb), NOW(), NOW())
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "text": claim_text,
                            "norm": norm,
                            "node_norm": normalize_label(cu.get("node_label") or "")[:500],
                            "status": status,
                            "conf": float(cu.get("confidence") or 0.5),
                            "ext": ext,
                            "paper_ids": paper_ids,
                        },
                    )
            stats["claims"] += 1
        except Exception as exc:  # noqa: BLE001 — per-item isolation
            logger.warning("[curator] claim update failed, dropping item: %s", exc)
            stats["dropped"] += 1

    for conn in out.get("connections", [])[:MAX_CONNECTIONS_PER_PASS]:
        label = conn.get("label") or ""
        try:
            with session.begin_nested():
                if _insert_topic_node(
                    session,
                    label,
                    "connection",
                    conn.get("question") or "",
                    conn.get("rationale") or "",
                ):
                    _link_connection_endpoints(session, label)
                    stats["connections"] += 1
        except Exception as exc:  # noqa: BLE001 — per-item isolation
            logger.warning("[curator] connection insert failed, dropping item: %s", exc)
            stats["dropped"] += 1

    for hyp in out.get("hypotheses", [])[:MAX_HYPOTHESES_PER_PASS]:
        try:
            with session.begin_nested():
                if _insert_topic_node(
                    session,
                    hyp.get("label") or "",
                    "hypothesis",
                    hyp.get("question") or "",
                    hyp.get("rationale") or "",
                ):
                    stats["hypotheses"] += 1
        except Exception as exc:  # noqa: BLE001 — per-item isolation
            logger.warning("[curator] hypothesis insert failed, dropping item: %s", exc)
            stats["dropped"] += 1

    for ho in out.get("hypothesis_outcomes", []):
        outcome = ho.get("outcome")
        if outcome not in _VALID_OUTCOMES:
            stats["dropped"] += 1
            continue
        try:
            with session.begin_nested():
                result = session.execute(
                    text("""
                        UPDATE research_nodes
                        SET outcome = :outcome, updated_at = NOW()
                        WHERE kind = 'hypothesis' AND norm_label = :norm
                    """),
                    {
                        "outcome": outcome,
                        "norm": normalize_label(ho.get("node_label") or "")[:500],
                    },
                )
                stats["outcomes"] += result.rowcount
        except Exception as exc:  # noqa: BLE001 — per-item isolation
            logger.warning("[curator] outcome update failed, dropping item: %s", exc)
            stats["dropped"] += 1

    session.commit()
    return stats


def _paper_excerpt(
    report: str, *, head: int = 3000, tail: int = 3000, refs_sample: int = 1500
) -> str:
    """Curator-sized excerpt of one paper: prose (head+tail, or verbatim
    when short) plus a capped references sample.

    Every paper ends with a `## References` heading, so a naive
    `report[-N:]` tail is the bibliography, not the conclusions (C2,
    2026-08-05 review). Split via `theo_citations.split_artifact` — the
    PUBLIC splitter built for FINAL artifacts, matching on the LAST
    heading. The private `_find_references_heading` used here originally
    is documented for PRE-final pipeline text and matches the FIRST
    heading; on a final artifact, a fake mid-body "## References" heading
    (e.g. quoted inside prose) would be matched first and truncate real
    trailing content — split_artifact's last-match avoids exactly that
    (F2, 2026-08-05 review). The refs sample still travels (short, capped)
    because its tier labels are exactly what the curator needs to judge
    external_source_count.

    `head`/`tail`/`refs_sample` are overridable so a caller with a
    tighter budget (open_hypotheses' verdict judging, F3) can ask for a
    smaller excerpt than a full new-paper one — a verdict needs
    conclusions + tier labels, not 6K of prose per hypothesis.
    """
    from pipeline.lyra.theo_citations import split_artifact

    prose, _heading, refs = split_artifact(report)
    prose = prose.strip()
    # M10 fix: only split head/tail when there's an actual gap to skip —
    # for prose <= head+tail chars, prose[:head] + prose[-tail:] duplicated
    # the whole thing.
    body = prose if len(prose) <= head + tail else prose[:head] + "\n...\n" + prose[-tail:]

    if refs.strip():
        body += "\n\n[refs sample]\n" + refs[:refs_sample]

    return body


def _build_user_message(inputs: dict) -> str:
    """Serialize gathered inputs into the curator's user message (I3 fix).

    Key order puts action-critical sections first (candidates,
    open_hypotheses, claims) and the bulkiest section (papers) last, then
    drops papers from the END one at a time while the JSON exceeds the
    budget — recording how many were deferred so the curator knows the
    backlog wasn't fully seen (the deferred papers stay eligible for the
    next pass's since-cursor, see I7 in _gather_inputs/run_curator_pass).

    The naive `json.dumps(inputs)[:60000]` this replaces silently sliced
    mid-JSON and could drop `open_hypotheses`/`claims` entirely depending
    on dict key order — the payload built here is ALWAYS complete, valid
    JSON, never string-sliced.
    """
    claims = [
        {**c, "text": (c.get("text") or "")[:_MAX_CLAIM_TEXT_CHARS]}
        for c in (inputs.get("claims") or [])[:_MAX_CLAIMS_IN_MESSAGE]
    ]
    # Papers carry `completed_at` internally (for the since-cursor) but that
    # is bookkeeping, not curator input — strip it from the LLM-facing copy.
    papers = [
        {"request_id": p["request_id"], "question": p["question"], "excerpt": p["excerpt"]}
        for p in (inputs.get("papers") or [])
    ]
    payload = {
        "candidates": inputs.get("candidates") or [],
        "open_hypotheses": inputs.get("open_hypotheses") or [],
        "claims": claims,
        "papers": papers,
    }

    deferred = 0
    while (
        papers
        and len(json.dumps(payload, ensure_ascii=False, default=str)) > _MAX_USER_MESSAGE_CHARS
    ):
        papers.pop()
        deferred += 1
    if deferred:
        payload["papers_deferred"] = deferred

    message = json.dumps(payload, ensure_ascii=False, default=str)
    if len(message) > _MAX_USER_MESSAGE_CHARS:
        # papers is now empty (the loop above only stops early once the
        # budget is met) — candidates/open_hypotheses/claims alone exceed
        # it. Advisory only: this budget isn't enforced beyond dropping
        # papers, so the world-model half of the message can still starve
        # (F3, 2026-08-05 review) — surface it rather than fail silently.
        logger.warning(
            "[THINK] curator user message over budget with no papers left to drop "
            "(%d chars, budget %d)",
            len(message),
            _MAX_USER_MESSAGE_CHARS,
        )
    return message


def _gather_inputs(session) -> dict:
    """Collect world model, new papers, miner candidates, open hypotheses.

    `last_paper_completed_at` (I7 fix) tracks the newest paper actually
    INCLUDED in a past curator message — not just completed, and not "the
    time of the last pass". A paper deferred by the size budget
    (_build_user_message) or gathered during a pass whose LLM call then
    failed must stay in the backlog and re-enter on the next pass rather
    than being silently skipped by a cursor that advanced on pass time
    alone. ORDER BY completed_at ASC drains that backlog oldest-first.
    """
    last_paper_row = session.execute(
        text("""
            SELECT details->>'last_paper_completed_at' AS ts
            FROM thinking_log
            WHERE kind = 'curator' AND details ? 'last_paper_completed_at'
            ORDER BY created_at DESC LIMIT 1
        """)
    ).fetchone()
    since = (
        datetime.fromisoformat(last_paper_row.ts)
        if last_paper_row and last_paper_row.ts
        else datetime(2020, 1, 1)
    )

    claims = session.execute(
        text("""
            SELECT text, status, confidence FROM knowledge_claims
            ORDER BY updated_at DESC LIMIT 100
        """)
    ).fetchall()

    papers = session.execute(
        text("""
            SELECT id::text AS request_id, question, result_json, completed_at
            FROM research_requests
            WHERE status = 'completed' AND is_batch = TRUE AND completed_at > :since
            ORDER BY completed_at ASC LIMIT 5
        """),
        {"since": since},
    ).fetchall()
    paper_excerpts = []
    for p in papers:
        report = (json.loads(p.result_json).get("report") or "") if p.result_json else ""
        paper_excerpts.append(
            {
                "request_id": p.request_id,
                "question": p.question,
                "excerpt": _paper_excerpt(report),
                "completed_at": p.completed_at,
            }
        )

    open_hypotheses = session.execute(
        text("""
            SELECT n.label, n.question, rr.result_json
            FROM research_nodes n
            JOIN research_requests rr ON rr.id = n.paper_id AND rr.status = 'completed'
            WHERE n.kind = 'hypothesis' AND n.status = 'explored' AND n.outcome IS NULL
            LIMIT 5
        """)
    ).fetchall()
    hyp_inputs = [
        {
            "label": h.label,
            "question": h.question,
            # Same references-tail bug as papers (C2) — the outcome verdict
            # needs the refs' tier labels anyway, so reuse _paper_excerpt.
            # Tighter budget than a new-paper excerpt (F3): a verdict needs
            # conclusions + tier labels, not 6K of prose per hypothesis —
            # at the default budget, 5 open hypotheses alone could approach
            # 40K chars and starve the rest of the message.
            "paper_tail": _paper_excerpt(
                json.loads(h.result_json).get("report") or "",
                head=1000,
                tail=1500,
                refs_sample=800,
            )
            if h.result_json
            else "",
        }
        for h in open_hypotheses
    ]

    from pipeline.lyra.graph_miner import run_miner

    return {
        "claims": [dict(r._mapping) for r in claims],
        "papers": paper_excerpts,
        "candidates": run_miner(),
        "open_hypotheses": hyp_inputs,
        "last_paper_completed_at": since,
    }


def run_curator_pass() -> None:
    """One nightly thinking pass. Best-effort — never raises.

    On ANY failure — quota exhaustion, an unusable/empty LLM response (the
    DOCUMENTED dominant `structured_llm_call` failure mode: `{}` is
    returned only after BOTH the structured call and its text-fallback
    retry failed — see minimax_shared.py), a DB error, or anything else —
    this still writes a thinking_log failure row so `thinking_pass_due`'s
    20h gate closes. Otherwise a dead LLM key (or a bad response) reopens
    the 02:00-05:00 window on every feeder poll and the same failing pass
    retries all night (I5/M17, F1).
    """
    try:
        from pipeline.lyra.minimax_limiter import bind_low_priority

        # Spec §3: Denkstunde runs on the crawl lane — a Monday-crossing
        # weekend run or a UI run may share the 5h window; the to_thread
        # context copy cannot leak this back into the feeder.
        bind_low_priority(True)

        from pathlib import Path

        from pipeline.database import get_session
        from pipeline.lyra.config import LyraSettings
        from pipeline.lyra.minimax_shared import structured_llm_call
        from pipeline.lyra.thinking_log import log_thinking

        settings = LyraSettings()
        with get_session() as session:
            inputs = _gather_inputs(session)

        system = (Path(__file__).parent / "prompts" / "curator_pass.txt").read_text(
            encoding="utf-8"
        )
        user_message = _build_user_message(inputs)
        out = structured_llm_call(
            system=system,
            user_message=user_message,
            schema=CURATOR_SCHEMA,
            max_tokens=4096,
            settings=settings,
            temperature=settings.temperature_verification,
        )
        if not out:
            # F1: {} is the DOCUMENTED dominant structured_llm_call failure
            # mode (returned only after both the structured call and its
            # text-fallback retry failed) — without a failure row here the
            # 20h gate never closes and the feeder retries all night.
            logger.warning("[THINK] curator returned empty output — skipping apply")
            log_thinking(
                "curator", "Denkstunde failed: LLM returned no usable output", {"failed": True}
            )
            return

        with get_session() as session:
            stats = _apply_curator_output(session, out)

        # Advance the paper backlog cursor only past papers that actually
        # made it into THIS message (I7) — match by request_id against what
        # was really sent, not against everything _gather_inputs fetched.
        sent = json.loads(user_message)
        included_ids = {p["request_id"] for p in sent.get("papers", [])}
        included_papers = [p for p in inputs.get("papers") or [] if p["request_id"] in included_ids]
        cursor = inputs.get("last_paper_completed_at")
        if included_papers:
            cursor = max(p["completed_at"] for p in included_papers)
        papers_deferred = sent.get("papers_deferred", 0)

        # F3: demoted/dropped/deferred surfaced in the headline, not just
        # details — demoted is the citation-integrity signal (an
        # "established" claim that didn't actually earn it) and must be
        # visible in the Discord embed / activity feed at a glance.
        summary = (
            f"Denkstunde: {stats['claims']} claims ({stats['demoted']} demoted, "
            f"{stats['dropped']} dropped), {stats['connections']} connections, "
            f"{stats['hypotheses']} hypotheses, {stats['outcomes']} verdicts"
        )
        if papers_deferred:
            summary += f", {papers_deferred} papers deferred"
        details = {**stats, "llm_summary": out.get("summary", "")}
        if papers_deferred:
            details["papers_deferred"] = papers_deferred
        if cursor is not None:
            details["last_paper_completed_at"] = cursor.isoformat()
        log_thinking("curator", summary, details)
        try:
            from api.services.notify import send_discord_webhook

            send_discord_webhook(
                {
                    "embeds": [
                        {
                            "title": "🧠 Theo Denkstunde",
                            "description": f"{summary}\n{out.get('summary', '')[:500]}",
                            "color": 0x3498DB,
                        }
                    ]
                }
            )
        except Exception:  # noqa: BLE001 — notification is best-effort
            pass
    except (QuotaExhaustedError, InsufficientQuotaError) as exc:
        logger.error("[THINK] curator pass aborted — quota exhausted: %s", exc, exc_info=True)
        from pipeline.lyra.thinking_log import log_thinking

        log_thinking(
            "curator", f"Denkstunde failed: quota exhausted ({exc})"[:500], {"failed": True}
        )
    except Exception as exc:  # noqa: BLE001 — thinking must never kill the feeder
        logger.error("[THINK] curator pass failed: %s", exc, exc_info=True)
        from pipeline.lyra.thinking_log import log_thinking

        log_thinking("curator", f"Denkstunde failed: {exc}"[:500], {"failed": True})
