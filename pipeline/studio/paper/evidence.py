"""evidence.json: Claude's checkable claims, each tied to one paragraph and one verbatim quote.

Entry: {id: "ev-NN", anchor_text, claim, source_ids, quote, quote_source_id, verdict}.
The rule for a publishable entry is the publish gate's own, stream A's
`theo_publishing.check_evidence`, taken unchanged: exactly these keys, an ev-NN id used once,
non-empty strings, 12-hex source ids, quote_source_id among source_ids, `verdict` always
"supported" (theo_publish publishes nothing else, so an entry the claim check does not support
is fixed or removed before the check can pass), and every anchor on exactly one paragraph of
the markdown and, when that passes, of the HTML the paper page serves
(`check_evidence_anchors`; a page issue starts with PAGE_PREFIX, the `page_anchors` gate of
gates.py).

Only once that rule reports nothing but page issues come the checks that need the dossier:
every source id is in the dossier and cited by the paper, and the quote occurs verbatim
(whitespace-normalised) in its source's text. That check is mechanical, never a model's word:
no model vouches for another model's quotation. The text of a TDM-reserved source is the live
text the claim check saved (owner decision 16): before the claim check (`claims-export`,
after_claim_check=False) its quote waits for the live read; after it (`paper check`, the texts
of claims.source_texts) a missing live file means "run the claim check first".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pipeline.lyra import theo_publishing
from pipeline.studio.paper.workspace import Dossier

PAGE_PREFIX = "paper page: "


def ws_normalize(text: str) -> str:
    return " ".join(text.split())


def quote_in_text(quote: str, text: str) -> bool:
    needle = ws_normalize(quote)
    return bool(needle) and needle in ws_normalize(text)


def _entry_problems(
    entry: dict[str, Any],
    dossier: Dossier,
    cited_ids: set[str],
    texts: Mapping[str, str],
    after_claim_check: bool,
) -> list[str]:
    """The dossier-bound checks of one entry theo_publishing.check_evidence accepted."""
    where = entry["id"]
    ids = entry["source_ids"]
    problems: list[str] = []
    unknown = [s for s in ids if s not in dossier.sources]
    if unknown:
        problems.append(f"{where}: source ids not in the dossier: {unknown}")
    uncited = [s for s in ids if s in dossier.sources and s not in cited_ids]
    if uncited:
        problems.append(f"{where}: source ids the paper does not cite: {uncited}")
    qsid = entry["quote_source_id"]
    if qsid not in dossier.sources:
        return problems
    status = dossier.text_status(qsid)
    located = f"claims_check/live/{qsid}.txt" if status == "tdm_reserved" else f"texts/{qsid}.txt"
    if qsid in texts:
        if not quote_in_text(entry["quote"], texts[qsid]):
            problems.append(f"{where}: quote does not occur verbatim in {located}")
    elif status != "tdm_reserved":
        problems.append(f"{where}: {qsid} has no text ({status}); quote a source that has one")
    elif after_claim_check:
        problems.append(
            f"{where}: {qsid} is TDM-reserved and the claim check has not saved its live text "
            f"({located}): run the claim check first"
        )
    return problems


def evidence_problems(
    evidence: Any,
    report: str,
    title: str,
    dossier: Dossier,
    cited_ids: set[str],
    texts: Mapping[str, str],
    *,
    after_claim_check: bool,
) -> list[str]:
    """Every problem in evidence.json against the numbered paper, its page and the source
    texts (the dossier's archived texts, plus the saved live texts once after_claim_check);
    [] when valid."""
    if not isinstance(evidence, list) or not evidence:
        return ["evidence.json must be a non-empty list"]
    problems = list(theo_publishing.check_evidence(report, title, evidence)["issues"])
    if any(not p.startswith(PAGE_PREFIX) for p in problems):
        return problems
    for entry in evidence:
        problems.extend(_entry_problems(entry, dossier, cited_ids, texts, after_claim_check))
    return problems
