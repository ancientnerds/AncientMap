"""`paper list` and `paper pull`: fetch a dossier from the VPS and write the writer brief.

The dossier parts are rendered in the shapes production writes (stream A's C3): cross-angle
connections and convergent findings carry `{angle_id, finding, source_ids}` objects, contested
claims `for`/`against` objects `{evidence, specialists}`. Keys the Theo schemas do not require
are read with `.get`, so a sparse LLM answer never crashes the pull, and every source id in
them becomes an `[S:<id>]` marker the writer can cite.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pipeline.lyra.dossier_manifest import moderated_source_ids
from pipeline.studio import config, remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import (
    Dossier,
    PaperWorkspace,
    parse_dossier,
    workspace,
    write_json,
)

TEMPLATE_PATH = Path(__file__).with_name("brief_template.md")
LIST_TIMEOUT_S = 120
EXPORT_TIMEOUT_S = 900
DEBATE_LIMIT = 40
ANGLE_FINDINGS_LIMIT = 30
_PLACEHOLDER_RE = re.compile(r"\{\{[a-z_]+\}\}")


def list_dossiers() -> str:
    """What `theo_dossier list` prints (one JSON array, oldest first), unchanged."""
    out = remote.check_module("pipeline.lyra.theo_dossier", ["list"], timeout=LIST_TIMEOUT_S)
    return out.decode("utf-8")


def pull(request_id: str, dossier_from: str | None = None) -> PaperWorkspace:
    """Export a dossier into the workspace of `request_id` and write the texts and the brief.

    With `dossier_from` (`paper pull TARGET --dossier-from RUN`), `request_id` is a public
    paper being rewritten and RUN a fresh Theo run on its question (a `researched` row, owner
    decisions 17 and 18): the workspace, every image web path and every publish call stay
    TARGET's, the dossier is RUN's, and dossier_from.json names RUN; `paper correct TARGET
    --republish` then sends it as `dossier_request_id` (stream A's C5), and `paper publish`
    refuses the workspace. A workspace that holds a paper this studio published
    (published_bundle.json) is rewritten in place with its own dossier, never from a fresh run,
    and a RUN whose export is not `researched` is refused here, before any write (stream A's
    `dossier_source` gate would refuse it only at the republish dry run).
    """
    ws = workspace(request_id)
    source = request_id
    if dossier_from is not None:
        source = config.check_request_id(dossier_from)
        if source == request_id:
            raise StudioError("--dossier-from names the paper itself: pull it without the option")
        if ws.published_bundle.exists():
            raise StudioError(
                f"papers/{request_id} holds a paper this studio published: rewrite it from its "
                "own dossier with `paper correct --republish`"
            )
    raw = remote.check_module(
        "pipeline.lyra.theo_dossier",
        ["export", source, "--texts", "cited"],
        timeout=EXPORT_TIMEOUT_S,
    )
    dossier = parse_dossier(raw)
    if dossier.request_id != source:
        raise StudioError(f"theo_dossier exported {dossier.request_id} for {source}")
    status = dossier.data["request"]["status"]
    if dossier_from is not None and status != "researched":
        raise StudioError(
            f"{source} is {status}, not researched: --dossier-from takes an unwritten Theo run "
            "from `paper list` (stream A's dossier_source gate)"
        )
    ws.root.mkdir(parents=True, exist_ok=True)
    if dossier_from is None:
        ws.dossier_from.unlink(missing_ok=True)
    else:
        write_json(ws.dossier_from, {"request_id": source})
    ws.dossier_gz.write_bytes(raw)
    write_texts(ws, dossier)
    ws.brief.write_text(render_brief(dossier), encoding="utf-8")
    return ws


def write_texts(ws: PaperWorkspace, dossier: Dossier) -> None:
    """One UTF-8 file per archived text; files of sources no longer in the dossier go."""
    ws.texts_dir.mkdir(parents=True, exist_ok=True)
    for stale in ws.texts_dir.glob("*.txt"):
        if stale.stem not in dossier.texts:
            stale.unlink()
    for source_id, text in dossier.texts.items():
        ws.text_path(source_id).write_text(text, encoding="utf-8")


def _markers(source_ids: list[str]) -> str:
    return " ".join(f"[S:{sid}]" for sid in source_ids)


def _cite(text: str, source_ids: list[str] | None) -> str:
    """`text` followed by its source markers (none: no trailing space)."""
    return " ".join(part for part in (text, _markers(source_ids or [])) if part)


def _counts(dossier: Dossier) -> str:
    c = dossier.data["manifest"]["counts"]
    return (
        f"angles {c['angles']} · findings {c['findings']} · sources {c['sources']} · "
        f"final claims {c['final_claims']} · revised {c['revised_claims']} · "
        f"speculative {c['speculative_claims']} · image candidates {c['images']}"
    )


def _archive(dossier: Dossier) -> str:
    a = dossier.data["manifest"]["archive"]
    return (
        f"{a['cited_sources']} cited: full text {a['full_text']}, abstract only "
        f"{a['abstract_only']}, missing {a['missing']}, TDM-reserved {a['tdm_reserved']}"
    )


def _moderated(dossier: Dossier) -> str:
    m = dossier.data["moderated"]
    lines = ["Final claims:"]
    for c in m.get("final_claims") or []:
        lines.append(_cite(f"- ({c.get('confidence') or '?'}) {c['claim']}", c["source_ids"]))
        if c.get("notes"):
            lines.append(f"  notes: {c['notes']}")
    lines.append("")
    lines.append("Revised claims:")
    for c in m.get("revised_claims") or []:
        original = c.get("original", "")
        text = f"- {original} -> {c['revised']}" if original else f"- {c['revised']}"
        if c.get("reason"):
            text += f" ({c['reason']})"
        lines.append(_cite(text, c["source_ids"]))
    lines.append("")
    lines.append("Speculative claims (label them as speculation):")
    for c in m.get("speculative_claims") or []:
        lines.append(_cite(f"- ({c.get('confidence') or '?'}) {c['claim']}", c["source_ids"]))
        if c.get("what_would_strengthen"):
            lines.append(f"  would strengthen: {c['what_would_strengthen']}")
    return "\n".join(lines)


def _synthesis(dossier: Dossier) -> str:
    s = dossier.data["synthesis"]["synthesis"]
    lines = ["Consensus:"]
    for c in s.get("consensus_claims") or []:
        lines.append(_cite(f"- ({c.get('confidence') or '?'}) {c['claim']}", c["source_ids"]))
    lines.append("")
    lines.append("Convergent findings across angles:")
    for f in s.get("convergent_findings") or []:
        lines.append(f"- {f.get('pattern', '')}")
        for involved in f.get("angles_involved") or []:
            lines.append(_cite(f"  - {involved.get('finding', '')}", involved.get("source_ids")))
    lines.append("")
    lines.append("Cross-angle connections:")
    for c in dossier.data["synthesis"].get("cross_angle_connections") or []:
        start = c.get("from_angle") or {}
        end = c.get("to_angle") or {}
        lines.append(f"- {c.get('description', '')}")
        lines.append(_cite(f"  from: {start.get('finding', '')}", start.get("source_ids")))
        lines.append(_cite(f"  to: {end.get('finding', '')}", end.get("source_ids")))
    lines.append("")
    lines.append("Open questions:")
    lines.extend(f"- {q}" for q in s.get("open_questions") or [])
    return "\n".join(lines)


def _contested(dossier: Dossier) -> str:
    s = dossier.data["synthesis"]["synthesis"]
    lines = []
    for c in s.get("contested_claims") or []:
        pro = c.get("for") or {}
        con = c.get("against") or {}
        text = (
            f"- {c['claim']} | for: {pro.get('evidence', '')} | against: {con.get('evidence', '')}"
        )
        lines.append(_cite(text, c.get("source_ids")))
    for c in s.get("contradictions") or []:
        side_a = c.get("side_a") or {}
        side_b = c.get("side_b") or {}
        lines.append(
            f"- contradiction: {c.get('description', '')} "
            f"(A: {side_a.get('position', '')} / B: {side_b.get('position', '')})"
        )
    return "\n".join(lines) if lines else "(none recorded)"


def _overflow(shown: int, total: int, what: str) -> list[str]:
    if total <= shown:
        return []
    return [
        f"(first {shown} of {total} {what} shown; the rest are in dossier.json.gz under debate)"
    ]


def _debate(dossier: Dossier) -> str:
    """Counts, the defenses that accepted a challenge, then the challenges.

    A defense's `suggestion_id` indexes the challenges of one round aimed at that defender;
    the stored debate records no round, so defenses are never paired with challenges here.
    """
    d = dossier.data["debate"]
    challenges: list[dict[str, Any]] = d.get("challenges") or []
    defenses: list[dict[str, Any]] = d.get("defenses") or []
    rounds = d.get("rounds", 0)
    rounds_n = len(rounds) if isinstance(rounds, list) else rounds
    accepted = [x for x in defenses if x.get("response") == "accept"]
    lines = [
        f"{rounds_n} rounds, {len(challenges)} challenges, {len(defenses)} defenses, "
        f"{len(accepted)} challenges accepted by the defender.",
        "",
        "Accepted by the defender:",
    ]
    for x in accepted[:DEBATE_LIMIT]:
        text = f"- {x.get('defender_id', '')} accepted: {x.get('argument', '')}"
        if x.get("additional_evidence"):
            text += f" (evidence: {x['additional_evidence']})"
        lines.append(_cite(text, x.get("source_ids")))
    lines.extend(_overflow(DEBATE_LIMIT, len(accepted), "accepted defenses"))
    lines.append("")
    lines.append("Challenges:")
    for c in challenges[:DEBATE_LIMIT]:
        text = f'- on "{c.get("target_claim", "")}": {c.get("suggestion", "")}'
        lines.append(_cite(text, c.get("source_ids")))
    lines.extend(_overflow(DEBATE_LIMIT, len(challenges), "challenges"))
    return "\n".join(lines)


def _angles(dossier: Dossier) -> str:
    """Each angle with the findings that share a source with the moderated claims."""
    core = set(moderated_source_ids(dossier.data["moderated"]))
    blocks = []
    for angle in dossier.data["angles"]:
        lines = [f"#### {angle.get('topic', '')}"]
        if angle.get("description"):
            lines.extend(["", angle["description"]])
        findings = [
            f for f in angle.get("findings") or [] if core.intersection(f.get("source_ids") or [])
        ]
        lines.append("")
        if not findings:
            lines.append("(no finding of this angle shares a source with the moderated claims)")
        for f in findings[:ANGLE_FINDINGS_LIMIT]:
            text = f"- ({f.get('confidence') or '?'}) {f.get('claim', '')}"
            lines.append(_cite(text, f.get("source_ids")))
        if len(findings) > ANGLE_FINDINGS_LIMIT:
            lines.append(
                f"(first {ANGLE_FINDINGS_LIMIT} of {len(findings)}; the rest are in "
                "dossier.json.gz under angles)"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(none recorded)"


def _source_line(dossier: Dossier, sid: str) -> str:
    s = dossier.sources[sid]
    status = dossier.text_status(sid)
    size = f" ({len(dossier.texts[sid])} chars)" if sid in dossier.texts else ""
    return (
        f"- [S:{sid}] T{s.get('reliability_tier') or '?'} · {s.get('title') or '(untitled)'}"
        f" · {s.get('domain', '')} · {status}{size}"
    )


def _tier_order(dossier: Dossier, ids: list[str]) -> list[str]:
    return sorted(
        ids, key=lambda sid: (int(dossier.sources[sid].get("reliability_tier") or 9), sid)
    )


def _sources(dossier: Dossier) -> str:
    """The citable set: the moderated claims' sources, then those of their angle findings."""
    moderated = moderated_source_ids(dossier.data["moderated"])
    known = [sid for sid in moderated if sid in dossier.sources]
    unknown = [sid for sid in moderated if sid not in dossier.sources]
    lines = [_source_line(dossier, sid) for sid in _tier_order(dossier, known)]
    moderated_set = set(moderated)
    behind = [sid for sid in dossier.citable_ids if sid not in moderated_set]
    if behind:
        lines.extend(["", "Sources of the angle findings behind these claims:", ""])
        lines.extend(_source_line(dossier, sid) for sid in _tier_order(dossier, behind))
    if unknown:
        lines.append("")
        lines.append(f"Ids the moderator cited that are not in the dossier (never cite): {unknown}")
    return "\n".join(lines)


def render_brief(dossier: Dossier, template: str | None = None) -> str:
    text = template if template is not None else TEMPLATE_PATH.read_text(encoding="utf-8")
    values = {
        "{{question}}": dossier.question,
        "{{request_id}}": dossier.request_id,
        "{{counts}}": _counts(dossier),
        "{{archive}}": _archive(dossier),
        "{{moderated}}": _moderated(dossier),
        "{{synthesis}}": _synthesis(dossier),
        "{{contested}}": _contested(dossier),
        "{{debate}}": _debate(dossier),
        "{{angles}}": _angles(dossier),
        "{{sources}}": _sources(dossier),
    }
    for key, value in values.items():
        text = text.replace(key, value)
    left = _PLACEHOLDER_RE.findall(text)
    if left:
        raise StudioError(f"brief template has unfilled placeholders {sorted(set(left))}")
    return text
