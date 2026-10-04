"""`paper list` and `paper pull`: fetch a dossier from the VPS and write the writer brief.

The dossier parts are rendered in the shapes production writes (stream A's C3): cross-angle
connections and convergent findings carry `{angle_id, finding, source_ids}` objects, contested
claims `for`/`against` objects `{evidence, specialists}`. Keys the Theo schemas do not require
are read with `.get`, so a sparse LLM answer never crashes the pull, and every citable source
id in them (Dossier.citable_ids, the brief's source list) becomes an `[S:<id>]` marker.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pipeline.lyra.claim_support import Located, locate_support
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
    # Rendered before anything is written: a brief that cannot be rendered leaves the
    # workspace as it was, never a new dossier beside an old brief.
    brief = render_brief(dossier, target=request_id if dossier_from is not None else None)
    ws.root.mkdir(parents=True, exist_ok=True)
    if dossier_from is None:
        ws.dossier_from.unlink(missing_ok=True)
    else:
        write_json(ws.dossier_from, {"request_id": source})
    ws.dossier_gz.write_bytes(raw)
    write_texts(ws, dossier)
    ws.brief.write_text(brief, encoding="utf-8")
    return ws


def write_texts(ws: PaperWorkspace, dossier: Dossier) -> None:
    """One UTF-8 file per archived text; files of sources no longer in the dossier go."""
    ws.texts_dir.mkdir(parents=True, exist_ok=True)
    for stale in ws.texts_dir.glob("*.txt"):
        if stale.stem not in dossier.texts:
            stale.unlink()
    for source_id, text in dossier.texts.items():
        ws.text_path(source_id).write_text(text, encoding="utf-8")


def _cite(text: str, source_ids: list[str] | None, citable: set[str]) -> str:
    """`text` followed by the markers of its citable sources (none: no trailing space).

    Synthesis, contested claims and the debate draw on every specialist finding: a marker
    for a source outside the citable set (Dossier.citable_ids, the brief's source list)
    would invite a citation `paper number` refuses."""
    markers = " ".join(f"[S:{sid}]" for sid in source_ids or [] if sid in citable)
    return " ".join(part for part in (text, markers) if part)


def _carried(claim: str, source_ids: list[str] | None, dossier: Dossier) -> tuple[list[str], list[str]]:
    """The cited sources whose archived text carries the claim, and those that do not.

    The defect report's rule 1 is "a marker requires a located sentence", and the
    31-paper audit measured where it breaks: of 2 105 findings, 384 were
    `misattributed` - a true-sounding sentence whose marker points at a source that
    does not carry it. Paper 1 showed where those markers come from: the brief. It
    renders the dossier's moderated claims at high confidence with their markers
    attached, so the writer copies a citation the research stage never verified.

    `locate_support` is the same call `paper_claim_gate` makes on the numbered
    paper, so a marker this function keeps is a marker the gate can confirm, and the
    two never disagree about what a source says. A source with no archived text
    carries nothing here: the claim check may read a TDM-reserved page live, but
    this pull cannot, so it does not hand the writer a marker it cannot show.
    """
    carried: list[str] = []
    uncited: list[str] = []
    for sid in source_ids or []:
        text = dossier.texts.get(sid)
        if text and locate_support(claim, text) is not None:
            carried.append(sid)
        else:
            uncited.append(sid)
    return carried, uncited


def _quotable(claim: str, claim_source_ids: list[str] | None, dossier: Dossier) -> Located | None:
    """A located sentence for `claim` from any citable source, for the re-source hint."""
    for sid in dossier.citable_ids:
        if sid in (claim_source_ids or []):
            continue
        text = dossier.texts.get(sid)
        if not text:
            continue
        located = locate_support(claim, text)
        if located is not None:
            return located
    return None


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


def _moderated(dossier: Dossier) -> tuple[str, str]:
    """The research result, and the claims its own cited sources do not carry.

    Two blocks, because they ask two different things of the writer. The first
    carries a marker only where the archived text carries the sentence
    (`_carried`), so a claim the gate can confirm is stated as settled. The second
    names the claims no cited source carries: the writer must re-source them from
    the source list, narrow them, or leave them out. They stay in the brief on
    purpose - dropping them here would lose material the research paid for, and
    handing them over with their markers would have the writer publish a
    citation nobody verified.
    """
    m = dossier.data["moderated"]
    citable = set(dossier.citable_ids)
    lines = ["Final claims:"]
    unsourced: list[str] = []
    for c in m.get("final_claims") or []:
        text = f"- ({c.get('confidence') or '?'}) {c['claim']}"
        carried, uncited = _carried(c["claim"], c.get("source_ids"), dossier)
        lines.append(_cite(text, [s for s in carried if s in citable], citable))
        if uncited:
            unsourced.append(_unsourced_line(c["claim"], uncited, c.get("source_ids"), dossier))
        if c.get("notes"):
            lines.append(f"  notes: {c['notes']}")
    lines.append("")
    lines.append("Revised claims:")
    for c in m.get("revised_claims") or []:
        original = c.get("original", "")
        text = f"- {original} -> {c['revised']}" if original else f"- {c['revised']}"
        if c.get("reason"):
            text += f" ({c['reason']})"
        carried, uncited = _carried(c["revised"], c.get("source_ids"), dossier)
        lines.append(_cite(text, [s for s in carried if s in citable], citable))
        if uncited:
            unsourced.append(_unsourced_line(c["revised"], uncited, c.get("source_ids"), dossier))
    lines.append("")
    lines.append("Speculative claims (label them as speculation):")
    for c in m.get("speculative_claims") or []:
        text = f"- ({c.get('confidence') or '?'}) {c['claim']}"
        carried, uncited = _carried(c["claim"], c.get("source_ids"), dossier)
        lines.append(_cite(text, [s for s in carried if s in citable], citable))
        if uncited:
            unsourced.append(_unsourced_line(c["claim"], uncited, c.get("source_ids"), dossier))
        if c.get("what_would_strengthen"):
            lines.append(f"  would strengthen: {c['what_would_strengthen']}")
    return "\n".join(lines), "\n".join(unsourced)


def _unsourced_line(
    claim: str, uncited: list[str], claim_source_ids: list[str] | None, dossier: Dossier
) -> str:
    """One uncarried claim, with the sentence that does carry it when one exists."""
    ids = ", ".join(f"[S:{sid}]" for sid in uncited)
    line = f"- {claim} — cited by {ids}, none of which carries this sentence."
    located = _quotable(claim, claim_source_ids, dossier)
    if located is not None:
        line += f' Another source does: "{_one_line(located.quote)}"'
    return line


def _one_line(quote: str, limit: int = 240) -> str:
    """A quote on one line, shortened - the brief is read, not parsed."""
    text = " ".join(quote.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _synthesis(dossier: Dossier) -> str:
    s = dossier.data["synthesis"]["synthesis"]
    citable = set(dossier.citable_ids)
    lines = ["Consensus:"]
    for c in s.get("consensus_claims") or []:
        text = f"- ({c.get('confidence') or '?'}) {c['claim']}"
        lines.append(_cite(text, c["source_ids"], citable))
    lines.append("")
    lines.append("Convergent findings across angles:")
    for f in s.get("convergent_findings") or []:
        lines.append(f"- {f.get('pattern', '')}")
        for involved in f.get("angles_involved") or []:
            text = f"  - {involved.get('finding', '')}"
            lines.append(_cite(text, involved.get("source_ids"), citable))
    lines.append("")
    lines.append("Cross-angle connections:")
    for c in dossier.data["synthesis"].get("cross_angle_connections") or []:
        start = c.get("from_angle") or {}
        end = c.get("to_angle") or {}
        lines.append(f"- {c.get('description', '')}")
        lines.append(_cite(f"  from: {start.get('finding', '')}", start.get("source_ids"), citable))
        lines.append(_cite(f"  to: {end.get('finding', '')}", end.get("source_ids"), citable))
    lines.append("")
    lines.append("Open questions:")
    lines.extend(f"- {q}" for q in s.get("open_questions") or [])
    return "\n".join(lines)


def _contested(dossier: Dossier) -> str:
    s = dossier.data["synthesis"]["synthesis"]
    citable = set(dossier.citable_ids)
    lines = []
    for c in s.get("contested_claims") or []:
        pro = c.get("for") or {}
        con = c.get("against") or {}
        text = (
            f"- {c['claim']} | for: {pro.get('evidence', '')} | against: {con.get('evidence', '')}"
        )
        lines.append(_cite(text, c.get("source_ids"), citable))
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
    citable = set(dossier.citable_ids)
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
        lines.append(_cite(text, x.get("source_ids"), citable))
    lines.extend(_overflow(DEBATE_LIMIT, len(accepted), "accepted defenses"))
    lines.append("")
    lines.append("Challenges:")
    for c in challenges[:DEBATE_LIMIT]:
        text = f'- on "{c.get("target_claim", "")}": {c.get("suggestion", "")}'
        lines.append(_cite(text, c.get("source_ids"), citable))
    lines.extend(_overflow(DEBATE_LIMIT, len(challenges), "challenges"))
    return "\n".join(lines)


def _angles(dossier: Dossier) -> str:
    """Each angle with the findings that share a source with the moderated claims."""
    core = set(moderated_source_ids(dossier.data["moderated"]))
    citable = set(dossier.citable_ids)
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
            lines.append(_cite(text, f.get("source_ids"), citable))
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


def _rewrite_note(dossier: Dossier, target: str | None) -> str:
    if target is None:
        return ""
    return (
        f"\n\nThis is the rewrite of the public paper `{target}` from the dossier of the fresh "
        f"Theo run `{dossier.request_id}`: every `paper` command takes `{target}`, and the "
        f"paper goes out with `paper correct {target} --republish`, never `paper publish`."
    )


def render_brief(
    dossier: Dossier, template: str | None = None, *, target: str | None = None
) -> str:
    """The writer brief. `target`: the public paper a `--dossier-from` pull rewrites, whose
    workspace every command takes (the dossier is the fresh run's).

    The placeholders are filled in one pass over the template, so dossier text that looks
    like a placeholder (a claim quoting wiki markup such as {{sfn}}) stays text."""
    text = template if template is not None else TEMPLATE_PATH.read_text(encoding="utf-8")
    moderated, unsourced = _moderated(dossier)
    values = {
        "{{question}}": dossier.question,
        "{{request_id}}": target if target is not None else dossier.request_id,
        "{{rewrite}}": _rewrite_note(dossier, target),
        "{{counts}}": _counts(dossier),
        "{{archive}}": _archive(dossier),
        "{{moderated}}": moderated,
        "{{unsourced}}": unsourced or "(none: every moderated claim's cited source carries it)",
        "{{synthesis}}": _synthesis(dossier),
        "{{contested}}": _contested(dossier),
        "{{debate}}": _debate(dossier),
        "{{angles}}": _angles(dossier),
        "{{sources}}": _sources(dossier),
    }
    unknown = sorted(set(_PLACEHOLDER_RE.findall(text)) - set(values))
    if unknown:
        raise StudioError(f"brief template has unfilled placeholders {unknown}")
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(0)], text)
