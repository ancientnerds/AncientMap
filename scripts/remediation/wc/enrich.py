"""Lane E's pieces on top of the WC machinery: which sites an enrichment asks, the questions, the
views the verifier and the judge are shown, the role check and the dispute brief.

Owner decisions D3 (thin descriptions get sourced sentences), D4 (one sourced open question per
Shorts-pool site) and D21 (a disputed site names both positions) of 2026-10-08, orchestrator decision
X1 (lane E); runbook `docs/procedures/SENTENCE_CHECK.md` section 14. `cli.py` runs the rounds; this
module is what is specific to appending sentences to a text the site already has:

* **The population** (`classify`): a shown, not retired description that is a *basis* - a Phase-4
  text of lane W or S whose provenance hashes it, or a March or lane-N text that a sentence check
  hashes (`_description_check`) - and whose markers and citations agree (`wc4.base_problems`), so the
  new sentences can be appended to it as it stands. A text no check has verified is not enriched: the
  new sentences would sit beside old ones nobody checked, and the text would become a card basis it
  is not. Texts of lane T, R and E, texts without a provenance and unchecked March texts are listed
  under their reason, never asked.
* **The question** (`enrich_prompt`): the site, the sentences it has (context), the classes it may
  take - up to three `fact` sentences for a thin text (D3: under `THIN_CHARS`), at most one
  `open_question` (D4) and, for a site with an adjudicated dispute brief, both positions (D21).
* **The verifier's and the judge's views**: the whole text, the new sentences marked for judgement.
* **The roles** (`require_role`, owner decision D6): every answer of the run names its role and the
  role's registered model, so a MiniMax answer, or a Sonnet answer given as the pilot's judge, is
  refused at the import.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402 - the registry (owner decision D6)
from phase4 import model4 as M  # noqa: E402
from phase4 import wc4  # noqa: E402

from wc import answers as A  # noqa: E402
from wc import prompts_enrich as PE  # noqa: E402

#: The kind of run (`cli.run_kind`) and its round-1 stage and batch prefix.
KIND = "wn-enrich"
STAGE = "enrich"
PREFIX = "we"
#: A description under this many characters (markers out) is thin (D3): it may take `MAX_FACTS_THIN`
#: fact sentences. A design number from the descriptions workstream map (459 of the 4,900 shown texts
#: are under it today), not a measured optimum.
THIN_CHARS = 300
MAX_FACTS_THIN = 3

WRITER_ROLE = PE.WRITER_ROLE
VERIFIER_ROLE = PE.VERIFIER_ROLE
JUDGE_ROLE = PE.JUDGE_ROLE

#: The keys of a dispute brief (`disputes.py` writes `DISPUTES.jsonl`, one such record per site) and
#: of one of its positions.
DISPUTE_KEYS = frozenset(
    {
        "site_id", "name", "desc_sha256", "verdict", "position_a", "position_b", "asserting",
        "note", "researched_by", "adjudicated_by",
    }
)  # fmt: skip
POSITION_KEYS = frozenset({"claim", "holders", "sources"})
SOURCE_KEYS = frozenset({"url", "title", "quote"})
DISPUTE_VERDICT = "dispute"


class EnrichError(ValueError):
    """An enrichment input is not what the lane needs: the command stops."""


# ------------------------------------------------------------------------------ the population
def is_thin(text: str) -> bool:
    """Is the description thin (D3)? Its markers do not count."""
    return len(wc4.strip_markers(text)) < THIN_CHARS


def classify(
    site: M.PlanSite, *, excluded: set[str], earlier: set[str]
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """`(reason, marking, sentences)` of a curated, not retired site: the reason it is not asked, or
    `None`, the recorded marking (`wc4.Marking`: `phase4` for a W or S text, `L` or `web` for a
    checked March or lane-N text) and the sentences the text has, markers out."""
    text = site.description
    if text is None or wc4.is_empty(text):
        return "no-description", None, ()
    raw = site.raw_data or {}
    stored = raw.get(M.PROVENANCE_KEY)
    if wc4.ENRICH_KEY in raw or (isinstance(stored, dict) and stored.get("lane") == "E"):
        return "enriched-before", None, ()
    if stored is None:
        return "no-provenance", None, ()
    try:
        provenance = M.provenance_from_dict(stored)
    except ValueError:
        return "provenance-unreadable", None, ()
    digest = M.text_sha256(text)
    if provenance.desc_sha256 != digest:
        return "provenance-hash-differs", None, ()
    if isinstance(provenance, M.Provenance):
        if provenance.lane not in M.ENRICHABLE_LANES:
            return "phase4-lane-not-enrichable", None, ()
        marking = wc4.Marking.PHASE4
    else:
        marking = wc4.Marking.L if isinstance(provenance, M.LegacyProvenance) else wc4.Marking.WEB
        try:
            check = wc4.DescriptionCheck.from_dict(raw.get(wc4.CHECK_KEY))
        except (ValueError, KeyError):
            return "unchecked-text", None, ()
        if check.desc_sha256 != digest or check.verified_sha256 != digest:
            return "unchecked-text", None, ()
    if site.site_id in excluded:
        return "excluded", None, ()
    if site.site_id in earlier:
        return "earlier-run", None, ()
    if wc4.base_problems(text, raw.get(M.CITATIONS_KEY)):
        return "base-not-enrichable", None, ()
    sentences = wc4.checked_sentences(text)
    if marking is wc4.Marking.PHASE4 and len(provenance.sentences) != len(sentences):
        return "provenance-misaligned", None, ()
    return None, marking.value, sentences


def entry_extras(site: M.PlanSite, existing: Sequence[str]) -> dict[str, Any]:
    """What an enrichment entry carries beside the site's id, name and marking: the sentences the
    text has (context), the base the new ones are appended to - text and citations as stored -, the
    check record of a checked text (it moves into the enrichment record), whether the text is thin
    and the dispute brief (`None` until `--disputes` attaches one). `sentences`, the NEW ones, are
    empty until the write round is imported (`DRAFTS.jsonl`)."""
    raw = site.raw_data or {}
    base = wc4.Base(
        text=str(site.description),
        citations=tuple(dict(c) for c in (raw.get(M.CITATIONS_KEY) or ())),
    )
    check = raw.get(wc4.CHECK_KEY)
    return {
        "sentences": [],
        "existing": list(existing),
        "base": base.to_dict(),
        "base_check": None if check is None else dict(check),
        "thin": is_thin(base.text),
        "dispute": None,
    }


def max_facts(entry: Mapping[str, Any]) -> int:
    """How many `fact` sentences the entry's description may take (D3: only a thin one)."""
    return MAX_FACTS_THIN if entry["thin"] else 0


def base_of_entry(entry: Mapping[str, Any]) -> wc4.Base:
    return wc4.Base.from_dict(entry["base"])


def classes_of_entry(entry: Mapping[str, Any]) -> dict[int, str]:
    """Sentence number -> class of the NEW sentences the write round imported."""
    return dict(enumerate(entry["classes"], start=1))


# ------------------------------------------------------------------------------ the disputes
def dispute_record_problems(record: Any) -> list[str]:
    """Why a dispute brief is not one (`disputes.py` writes them), or nothing."""
    if not isinstance(record, dict) or set(record) != DISPUTE_KEYS:
        keys = sorted(record) if isinstance(record, dict) else type(record).__name__
        return [f"a dispute brief carries {keys}, not {sorted(DISPUTE_KEYS)}"]
    problems: list[str] = []
    if record["verdict"] != DISPUTE_VERDICT:
        problems.append(f"verdict {record['verdict']!r} is not {DISPUTE_VERDICT!r}")
    for side in ("position_a", "position_b"):
        position = record[side]
        if not isinstance(position, dict) or set(position) != POSITION_KEYS:
            problems.append(f"{side} is not {sorted(POSITION_KEYS)}")
            continue
        for key in ("claim", "holders"):
            if not isinstance(position[key], str) or not position[key].strip():
                problems.append(f"{side}.{key} is empty")
        sources = position["sources"]
        if not isinstance(sources, list) or not sources:
            problems.append(f"{side} names no source")
            continue
        for source in sources:
            if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
                problems.append(f"{side}: a source is not {sorted(SOURCE_KEYS)}")
            elif any(
                not isinstance(source[key], str) or not source[key].strip() for key in SOURCE_KEYS
            ):
                problems.append(f"{side}: a source has an empty field")
    return problems


def dispute_block(record: Mapping[str, Any] | None) -> str:
    """The question's dispute block for a site with a brief, empty without (`prompts_enrich`)."""
    if record is None:
        return ""
    a, b = record["position_a"], record["position_b"]
    return PE.DISPUTE_BLOCK.format(
        a_claim=a["claim"],
        a_holders=a["holders"],
        a_url=a["sources"][0]["url"],
        a_quote=a["sources"][0]["quote"],
        b_claim=b["claim"],
        b_holders=b["holders"],
        b_url=b["sources"][0]["url"],
        b_quote=b["sources"][0]["quote"],
    )


# ------------------------------------------------------------------------------ the questions
def classes_block(entry: Mapping[str, Any]) -> str:
    facts = (
        PE.CLASS_FACT_THIN.format(max_facts=max_facts(entry))
        if entry["thin"]
        else PE.CLASS_FACT_NONE
    )
    return "\n".join([facts, PE.CLASS_HOOK.format(max_hook=A.MAX_HOOK_CHARS)])


def enrich_prompt(entry: Mapping[str, Any], *, site: str) -> str:
    """The write question about one site (`site`: the site block, `cli.site_block`)."""
    return PE.ENRICH_QUESTION.format(
        site=site,
        sentences=_numbered(entry["existing"]),
        classes=classes_block(entry),
        dispute=dispute_block(entry["dispute"]),
        min_chars=A.MIN_SENTENCE_CHARS,
        max_chars=A.MAX_SENTENCE_CHARS,
        max_run=A.MAX_SHARED_RUN,
        max_added=A.MAX_ADDED_CHARS,
        site_id=entry["site_id"],
    )


def new_sentence_lines(
    decisions: Sequence[wc4.Decision],
    quotes: Mapping[int, Sequence[wc4.Quote]],
    classes: Mapping[int, str],
) -> tuple[str, str]:
    """The kept new sentences as `K<k> [class]: text` with their quotes, and the removed ones as
    `D<d> [class]: text`: what a verifier and the judge are shown."""
    kept: list[str] = []
    dropped: list[str] = []
    number = 0
    for decision in decisions:
        if decision.text is None:
            dropped.append(f"D{len(dropped) + 1} [{classes[decision.n]}]: {decision.sentence}")
            continue
        number += 1
        kept.append(f"K{number} [{classes[decision.n]}]: {decision.text}")
        kept.extend(f'    quote: "{q.quote}" - {q.url}' for q in quotes.get(decision.n, ()))
    return "\n".join(kept) or "(none)", "\n".join(dropped) or "(none)"


def _numbered(sentences: Sequence[str]) -> str:
    """The sentences as `S<n>: text` lines: the old text, as a question or a verifier shows it."""
    return "\n".join(f"S{n}: {text}" for n, text in enumerate(sentences, start=1))


def verify_prompt(
    entry: Mapping[str, Any],
    decisions: Sequence[wc4.Decision],
    quotes: Mapping[int, Sequence[wc4.Quote]],
    *,
    site: str,
) -> str:
    """The verifier's question about the new sentences that stand at this verification round."""
    kept, dropped = new_sentence_lines(decisions, quotes, classes_of_entry(entry))
    return PE.VERIFY_QUESTION_ENRICH.format(
        site=site,
        old=_numbered(entry["existing"]),
        kept=kept,
        dropped=dropped,
        site_id=entry["site_id"],
        kept_count=sum(1 for d in decisions if d.kept),
    )


def judge_prompt(final: Mapping[str, Any], *, site: str) -> str:
    """The pilot judge's question about one built site, from its journal evidence alone: the old
    sentences are those of the base text the evidence records."""
    decisions, quotes = wc4.decisions_of(final["evidence"])
    kept, dropped = new_sentence_lines(decisions, quotes, wc4.classes_of(final["evidence"]))
    base = wc4.base_of(final["evidence"])
    return PE.JUDGE_QUESTION_ENRICH.format(
        site=site,
        old=_numbered(wc4.checked_sentences(base.text)),
        kept=kept,
        dropped=dropped,
        site_id=final["site_id"],
        kept_count=sum(1 for d in decisions if d.kept),
        dropped_count=sum(1 for d in decisions if not d.kept),
    )


def judge_counts(final: Mapping[str, Any]) -> tuple[int, int, list[int]]:
    """`(kept, dropped, hooks)` of a built site: the new sentences kept and removed, and the K
    numbers of the kept ones that are open questions (the only ones the judge may find INVENTED)."""
    decisions, _ = wc4.decisions_of(final["evidence"])
    classes = wc4.classes_of(final["evidence"])
    kept = [d for d in decisions if d.kept]
    hooks = [k for k, d in enumerate(kept, start=1) if classes[d.n] == wc4.OPEN_QUESTION]
    return len(kept), len(decisions) - len(kept), hooks


# ------------------------------------------------------------------------------ the evidence
def evidence_detail(entry: Mapping[str, Any]) -> dict[str, Any]:
    """The enrichment block of the journal evidence (`wc4.ENRICH_EVIDENCE_KEY`): the base as stored,
    the old check record, every new sentence's class, the dispute brief and whether the text was thin
    - what lets the database alone compose the text again (`wc4.enrichment_evidence_problems`)."""
    return {
        "base": entry["base"],
        "base_check": entry["base_check"],
        "classes": {str(n): kind for n, kind in classes_of_entry(entry).items()},
        "dispute": entry["dispute"],
        "thin": entry["thin"],
    }


def enrichment_parts(
    site: M.PlanSite,
    entry: Mapping[str, Any],
    composed: wc4.Composed,
    decisions: Sequence[wc4.Decision],
    quotes: Mapping[int, Sequence[wc4.Quote]],
    verification: Mapping[str, Any],
    *,
    run_name: str,
    writer: str,
) -> dict[str, Any] | None:
    """The `raw_data` a verified enrichment leaves, or `None` when no sentence was kept."""
    if composed.description is None:
        return None
    base = base_of_entry(entry)
    record = wc4.enrichment_record(
        decisions,
        classes_of_entry(entry),
        composed,
        quotes,
        run=run_name,
        base=base,
        base_check=entry["base_check"],
        verification=verification,
        writer=writer,
    )
    provenance = wc4.enriched_provenance(
        site.raw_data,
        composed,
        base=base,
        ai_system=writer,
        marking=wc4.Marking(entry["marking"]),
    )
    return wc4.enriched_raw_data(site, composed, record, provenance)


# ------------------------------------------------------------------------------ the roles
def require_role(answer: OH.Answer, role: str, where: str) -> None:
    """Refuse an answer that is not given in `role`: its `answered_by` names the role
    (`opus_handoff.py answer --role`) and its stamp is the stamp of the role's registered model. A
    MiniMax answer, an answer recorded before the registry and a Sonnet answer given as the pilot's
    judge are all refused (owner decision D6: the roles are Claude's, and each is calibrated)."""
    named = RO.role_of(answer.answered_by)
    if named != role:
        raise EnrichError(
            f"{where}: {answer.answered_by!r} does not name the role {role!r} - record the answer "
            f"with opus_handoff.py answer --role {role} --model {RO.role(role).model}"
        )
    problem = RO.answer_problem(answer.answered_by, answer.model)
    if problem is not None:
        raise EnrichError(f"{where}: {problem}")
