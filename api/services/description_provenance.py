# SPDX-License-Identifier: AGPL-3.0-only
"""What a site description discloses: the AI mark and the CC BY-SA attribution, from provenance.

The 2026-09 remediation (Phases 4 and 5, design entry [6] of
``output/remediation/logs/design_texts_images_2026-09-22.json``, section licensing_and_ai_act)
writes ``raw_data._description_provenance`` beside every description it publishes. The key is the
render key of the EU-AI-Act disclosure, graded by provenance:

* ``ai: 'selected'`` (lanes W and S): verbatim Wikipedia sentences an AI system only chose and
  shortened. Shown as the attribution line under the description; no IPTC type is claimed.
* ``ai: 'generated'`` (lanes T and R, and the legacy lane L for held March-LLM text): the AI wrote
  the words. Shown with the existing AI footnote; lane T, a translated adaptation, also carries the
  attribution line.

Per-site attribution meets CC BY-SA 4.0 section 3(a) - the article title and its revision
permalink, the licence and its link, and the change note - and is surfaced only for the lanes
whose text adapts a CC BY-SA source (W, S, T). R's pages are restricted: their facts are restated,
nothing of their wording is published, and no attribution line names them.

A disclosure is a statement about one text. It is made only while the description served is the
one the provenance hashes (``desc_sha256``): a description edited afterwards by any other path is
no longer the text the provenance describes, so nothing is claimed for it, as for a description
without provenance. The same holds for the card (``card.text_sha256``, and a teaser card's own
``raw_data._card_provenance``, see ``card_ai``).

One derivation for every reader - ``/api/sites/{id}`` (camelCase), the SSR payload of
``/sites/{country}/{slug}`` and the public v1 API - so the three cannot disagree. The frontend
renders what this returns (``src/components/DescriptionDisclosure.tsx``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pipeline.utils.card_provenance import card_ai as teaser_card_ai

#: The raw_data key the writer uses (``scripts/remediation/phase4/model4.py:PROVENANCE_KEY``; a
#: test pins that the two spellings agree). The leading underscore keeps it out of the generic
#: raw_data panel (``ancient-nerds-map/src/config/sourceFields.ts``).
PROVENANCE_KEY = "_description_provenance"

#: The lanes whose published text adapts a CC BY-SA source and therefore names it.
ATTRIBUTION_LANES = frozenset({"W", "S", "T"})

#: The AI marks the writer uses; anything else is not a provenance this module reads.
AI_MARKS = frozenset({"selected", "generated"})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def provenance_of(raw_data: Any) -> dict[str, Any] | None:
    """The provenance object of a ``raw_data`` value (a dict, a JSON string or ``None``).

    ``None`` only when there is no provenance: no ``raw_data`` object, or no key. A key that is
    present and is not an object (a double-encoded JSON string, a list) raises ``ValueError``: a
    malformed provenance fails on every reader alike, as an unknown ``ai`` mark does in
    ``description_disclosure``, instead of reading as "nothing to disclose" here only.
    """
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)
    if not isinstance(raw_data, Mapping) or PROVENANCE_KEY not in raw_data:
        return None
    provenance = raw_data[PROVENANCE_KEY]
    if not isinstance(provenance, dict):
        raise ValueError(
            f"{PROVENANCE_KEY} is not a JSON object but {type(provenance).__name__}: "
            f"{str(provenance)[:80]!r}"
        )
    return provenance


def description_disclosure(
    provenance: Mapping[str, Any] | None, description: str | None
) -> dict[str, Any] | None:
    """The disclosure of `description`, or ``None`` when nothing may be claimed for it.

    ``{"ai", "lane", "aiSystem", "licence", "attribution"}``; ``attribution`` is
    ``{"title", "url", "licence", "licenceUrl", "changes", "revisionDate"}`` for lanes W, S and T and
    ``None`` otherwise; ``licence`` is ``None`` for the legacy lane, which claims none.
    """
    if provenance is None or description is None:
        return None
    if provenance["desc_sha256"] != _sha256(description):
        return None
    ai = provenance["ai"]
    if ai not in AI_MARKS:
        raise ValueError(f"_description_provenance.ai is {ai!r}, not one of {sorted(AI_MARKS)}")
    lane = provenance["lane"]
    attribution = None
    if lane in ATTRIBUTION_LANES:
        credit = provenance["attribution"]
        pinned = [source for source in provenance["sources"] if source["url"] == credit["url"]]
        if len(pinned) != 1:
            raise ValueError("_description_provenance.attribution names no single cited source")
        timestamp = pinned[0]["rev_timestamp"]
        attribution = {
            "title": credit["title"],
            "url": credit["url"],
            "licence": provenance["licence"],
            "licenceUrl": credit["licence_url"],
            "changes": credit["changes"],
            "revisionDate": None if timestamp is None else timestamp[:10],
        }
    return {
        "ai": ai,
        "lane": lane,
        "aiSystem": provenance["ai_system"],
        "licence": None if lane == "L" else provenance["licence"],
        "attribution": attribution,
    }


def card_ai(
    provenance: Mapping[str, Any] | None,
    card_provenance: Mapping[str, Any] | None,
    card: str | None,
) -> str | None:
    """The AI mark of a card, when it is exactly the card a provenance hashes; else ``None``.

    A teaser card (lane WB, ``raw_data._card_provenance``, ``pipeline.utils.card_provenance``) is
    the only statement about the card once it exists: it marks the card ``generated`` while it
    hashes it, and says nothing for any other card. Without it, the extractive Phase-5 card key of
    the description's provenance (``card.text_sha256``) is read as before; lane WB sets that key to
    ``null`` when it writes a teaser, so the two never both describe one card.
    """
    if card_provenance is not None:
        return teaser_card_ai(card_provenance, card)
    if provenance is None or card is None or provenance["lane"] == "L":
        return None
    recorded = provenance["card"]
    if recorded is None or recorded["text_sha256"] != _sha256(card):
        return None
    return provenance["ai"]
