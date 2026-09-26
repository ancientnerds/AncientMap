"""The machine checks of an L5 answer - what `questions.parse` cannot check without the pages.

An answer is **decided** when every check passes, and **held** otherwise: nothing of a held site is
written, and its reason is what a re-ask shows the next agent (`questions.prompt(earlier=...)`).

1. **Quotes.** Every quote is found verbatim (whitespace-normalised) in the page it cites
   (`opus_audit/quotes.py`, the re-verification's check and nothing fuzzier).
2. **A replacement item** is the item its entity page describes (`Special:EntityData/<QID>.json`
   answers with that id, not a redirect target) and lies at the site's place: its truthy `P625`
   (`bcases.collect.claims_record`), or the coordinates of the article kept or written beside it,
   within `qid_repair.GATE_M` (1 km) of the stored point - waves 2 and 3's gate, because "a wrong
   replacement QID is worse than a known-bad generic one, because dedup trusts QIDs".
3. **The article kept or written** exists on English Wikipedia under exactly that title (not a
   redirect, not a disambiguation page), resolved the way `refresh_site_external_ids` resolves a
   title (`pipeline.lyra.prospector.wiki.resolve_titles`), and its item is the item kept or
   written - so the refresh's `--all` path would store exactly these two rows (its fixed point).

Pure: the pages, the entity bodies and the title resolutions are given.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import qid_repair as QR  # noqa: E402
from bcases.collect import claims_record  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from l5 import questions as QN  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402

DECIDED, HELD = "decided", "held"


@dataclass(frozen=True)
class Decision:
    """What one answer settles for one site: each stored value's fate, with its evidence."""

    site_id: str
    name: str
    status: str
    reason: str
    round: str
    answered_by: str
    #: `{verdict, old, new, why, quotes, note}` per stored value; `name` only when it was asked.
    cells: dict[str, dict[str, Any]]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class Held(Exception):
    """One check failed; the message is the site's hold reason."""


def _metres(lat: float, lon: float, other_lat: float, other_lon: float) -> float:
    return 1000.0 * haversine_distance(lat, lon, other_lat, other_lon)


def _quotes_found(
    key: str, cell: QN.Cell, library: Q.Library, site_id: str, record: dict[str, Any]
) -> None:
    """Every quote found in its page; each quote's outcome is recorded in `record` first."""
    if not cell.quotes:
        return
    check = Q.check_verdict(
        {"quotes": list(cell.quotes)}, {"change_key": site_id, "evidence_files": []}, library
    )
    record["quote_outcomes"] = [f"{r.outcome}: {r.detail}".rstrip(": ") for r in check.quotes]
    if not check.counted:
        failed = next(r for r in check.quotes if r.outcome != Q.FOUND)
        raise Held(f"{key}: a quote does not count ({failed.outcome}: {failed.source})")


def _entity(library: Q.Library, qid: str) -> Mapping[str, Any]:
    """The item as its cited entity page served it - never a redirect target's."""
    url = QN.ENTITY_DATA.format(qid)
    page = library.url(url)
    if page.failure:
        raise Held(f"wikidata_qid: {url} could not be read ({page.failure})")
    body = json.loads((library.pages / f"{Q.url_key(url)}.body").read_bytes().decode("utf-8"))
    entities = body.get("entities") or {}
    if qid not in entities:
        raise Held(f"wikidata_qid: {url} answers for {sorted(entities)}, not {qid} (a redirect)")
    return dict(entities[qid])


def _article(title: str, titles: Mapping[str, Mapping[str, Any]], item: str | None) -> str:
    """Check the article kept or written; return a note for the evidence."""
    res = titles.get(title)
    if res is None:
        raise Held(f"enwiki_title: {title!r} was not resolved - run the import again")
    if not res["canonical_title"]:
        raise Held(f"enwiki_title: no English Wikipedia page is titled {title!r}")
    if res["disambiguation"]:
        raise Held(f"enwiki_title: {title!r} is a disambiguation page")
    if res["redirected"] or res["canonical_title"] != title:
        raise Held(f"enwiki_title: {title!r} redirects to {res['canonical_title']!r}")
    if res["qid"] != item:
        raise Held(
            f"enwiki_title: the article {title!r} is the item {res['qid']}, the answer keeps "
            f"{item} - the daily refresh would write another pair"
        )
    return f"en.wikipedia {title!r} is the article of {item} (resolved as the refresh resolves it)"


def decide(
    site: Mapping[str, Any],
    member: Mapping[str, Any],
    answer: QN.Answer,
    *,
    round_name: str,
    answered_by: str,
    library: Q.Library,
    titles: Mapping[str, Mapping[str, Any]],
) -> Decision:
    """Every machine check of one parsed answer, in order; the first failure holds the site."""
    stored_qid = QN.stored(site, "wikidata_qid")
    stored_title = QN.stored(site, "enwiki_title")
    final = {
        "wikidata_qid": {
            "KEEP": stored_qid,
            "REPLACE": answer.qid.value,
            "REMOVE": None,
        }[answer.qid.verdict],
        "enwiki_title": {
            "KEEP": stored_title,
            "REPLACE": answer.title.value,
            "REMOVE": None,
        }[answer.title.verdict],
    }
    cells: dict[str, dict[str, Any]] = {
        "wikidata_qid": {"old": stored_qid, "new": final["wikidata_qid"], "note": ""},
        "enwiki_title": {"old": stored_title, "new": final["enwiki_title"], "note": ""},
        "source_url": {
            "old": site["source_url"],
            "new": {
                "KEEP": site["source_url"],
                "REPLACE": answer.source_url.value,
                "CLEAR": None,
            }[answer.source_url.verdict],
            "note": "",
        },
    }
    parts = {
        "wikidata_qid": answer.qid,
        "enwiki_title": answer.title,
        "source_url": answer.source_url,
    }
    if answer.name is not None:
        parts["name"] = answer.name
        cells["name"] = {
            "old": site["name"],
            "new": answer.name.value if answer.name.verdict == "RENAME" else site["name"],
            "note": "",
        }
    for key, cell in parts.items():
        cells[key].update({"verdict": cell.verdict, "why": cell.why, "quotes": list(cell.quotes)})

    def decision(status: str, reason: str) -> Decision:
        return Decision(
            site["site_id"], site["name"], status, reason, round_name, answered_by, cells
        )

    try:
        for key, cell in parts.items():
            _quotes_found(key, cell, library, site["site_id"], cells[key])
        item, title = final["wikidata_qid"], final["enwiki_title"]
        if title is not None:
            cells["enwiki_title"]["note"] = _article(title, titles, item)
        if answer.qid.verdict == "REPLACE" and item is not None:
            record = claims_record(_entity(library, item))
            lat, lon = float(site["lat"]), float(site["lon"])
            proofs = []
            if record["p625"] is not None:
                proofs.append(
                    ("P625", _metres(lat, lon, record["p625"]["lat"], record["p625"]["lon"]))
                )
            if title is not None and titles[title]["lat"] is not None:
                res = titles[title]
                proofs.append(("the article", _metres(lat, lon, res["lat"], res["lon"])))
            placed = [(what, m) for what, m in proofs if m <= QR.GATE_M]
            if not placed:
                seen = ", ".join(f"{what} {m:.0f} m" for what, m in proofs) or "no coordinates"
                raise Held(
                    f"wikidata_qid: {item} is not proven at the site's place ({seen}; the gate is "
                    f"{QR.GATE_M:.0f} m) - a coordinate question for WD1 first"
                )
            what, metres = min(placed, key=lambda p: p[1])
            cells["wikidata_qid"]["note"] = (
                f"{item} ({record['en_label']!r}): {what} {metres:.0f} m from the stored point"
            )
    except Held as exc:
        return decision(HELD, str(exc))
    return decision(DECIDED, "")
