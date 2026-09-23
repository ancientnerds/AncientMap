"""The Phase-4 cases the verifier's and the acceptance's tests share (not a test module).

One clean site per lane - W (and S), T, R - built from hand-written pinned texts and hand-written
published strings, never from `phase4/verify4.py`'s own edit list, so a wrong edit list cannot move
an expectation with it. Also the seams: a card measurement without the gitignored brand fonts, and
contract-shaped stand-ins for the two modules other tracks own (`phase4.licences`, WB-A2, and
`phase4.write4`, WB-D2), installed only while those modules are not on the tree.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PIL import ImageFont

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

import phase4  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3.run import Batch  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import verify4 as V  # noqa: E402

from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS, listed_domain_of  # noqa: E402
from pipeline.video import shorts_audit  # noqa: E402

SITE_ID = "4a5a324f-1111-4111-8111-111111111111"
HEX_RAW = hashlib.sha256(b"the raw response").hexdigest()


def sha(text: str) -> str:
    """sha256 of the UTF-8 bytes, lowercase hex - written out here, not taken from `model4`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------
# Lane W: the pinned English article, its offered spans and the published text, by hand
# ------------------------------------------------------------------------------------------------

S1 = (
    "The Tarxien Temples are an archaeological complex of four megalithic structures, built "
    "between 3600 and 2500 BC, near the village of Tarxien."
)
S2 = (
    "The site was excavated in 1915 by Themistocles Zammit (the director of the museum), who "
    "found statues and altars."
)
S3 = "It contains a large statue of a fertility goddess and carved spiral reliefs."
S4 = "In 1992, the temples were declared a World Heritage Site as part of the Megalithic Temples."
S5 = "The temples were not built at once, and the earliest phase may date to 3600 BC."
TEXT = f"{S1} {S2} {S3} {S4}\n\n\n== History ==\n{S5}"

A1 = ", built between 3600 and 2500 BC,"  # S1: a paired-comma insertion
P2 = " (the director of the museum)"  # S2: a parenthesis with the space before it
T2 = ", who found statues and altars"  # S2: the last comma segment
L4 = "In 1992, "  # S4: a leading phrase
T4 = ", the temples were declared a World Heritage Site as part of the Megalithic Temples"

PUB1 = (
    "The Tarxien Temples are an archaeological complex of four megalithic structures near the "
    "village of Tarxien."
)
PUB2 = "The site was excavated in 1915 by Themistocles Zammit, who found statues and altars."
PUB3 = S3
CARD = PUB1

PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567"
STORED = (
    "Tarxien Temples is a group of megalithic temples in Malta dating from about 3150 BC [1]. "
    "The site was discovered in 1914 by local farmers and excavated by Themistocles Zammit, who "
    "found carved altars, a colossal statue of a fertility goddess and spiral reliefs [1]. It is "
    "part of a World Heritage Site [1]."
)
OLD_RAW: dict[str, Any] = {
    "description_citations": [
        {
            "n": 1,
            "url": "https://en.wikipedia.org/wiki/Tarxien_Temples",
            "title": "Wikipedia",
            "domain": "en.wikipedia.org",
            "claim": "megalithic temples",
        }
    ],
    "heritage": {"unesco": True},
}


@dataclass(frozen=True)
class Pick:
    """One published sentence: its source sentence, the pieces dropped from it, the result."""

    sentence: str
    drops: tuple[str, ...]
    published: str  #: without its marker, ending in '.'


W_PICKS = (Pick(S1, (A1,), PUB1), Pick(S2, (P2,), PUB2), Pick(S3, (), PUB3))


def locate(text: str, sentence: str) -> tuple[int, int]:
    start = text.index(sentence)
    return start, start + len(sentence)


def piece_range(text: str, sentence: str, piece: str) -> tuple[int, int]:
    start, end = locate(text, sentence)
    at = text.index(piece, start, end)
    return at, at + len(piece)


def with_marker(published: str, n: int) -> str:
    assert published.endswith(".")
    return f"{published[:-1]} [{n}]."


def gate(verdict: str = "own", **over: Any) -> M.SubjectGate:
    values: dict[str, Any] = {
        "qid_match": True,
        "shared": verdict == "shared",
        "concept": False,
        "place_item": False,
        "km": 0.4,
        "name_score": 100.0,
        "verdict": M.SubjectVerdict(verdict),
    }
    values.update(over)
    return M.SubjectGate(**values)


def wiki_meta(source_id: str, text: str, *, lang: str, title: str, revid: int, **over: Any):
    permalink = (
        f"https://{lang}.wikipedia.org/w/index.php?title={title.replace(' ', '_')}&oldid={revid}"
    )
    doc = M.SourceDoc(
        id=source_id,
        url=f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
        permalink=permalink,
        title=title,
        pageid=4242,
        revid=revid,
        lastrevid=revid,
        rev_timestamp="2026-09-01T10:00:00Z",
        retrieved_at="2026-09-23T08:00:00Z",
        sha256_raw=HEX_RAW,
        sha256_text=sha(text),
        licence=M.Licence.CC_BY_SA_4,
        route=M.Route.ENWIKI_TITLE,
        subject_gate=over.pop("subject_gate", gate()),
        tdm=None,
        final_url=None,
        truncated=None,
    )
    return {**doc.to_dict(), **over}


def plan_site(**over: Any) -> M.PlanSite:
    values: dict[str, Any] = {
        "site_id": SITE_ID,
        "name": "Tarxien Temples",
        "aliases": ("Tarxien",),
        "country": "Malta",
        "site_type": "Temple",
        "period_start": -3600,
        "period_end": None,
        "lat": 35.869,
        "lon": 14.512,
        "description": STORED,
        "description_sha256": sha(STORED),
        "raw_data": OLD_RAW,
        "raw_data_sha256": HEX_RAW,
        "card": "An old card.",
        "card_sha256": sha("An old card."),
        "source_url": "https://en.wikipedia.org/wiki/Tarxien_Temples",
        "wikidata_qid": "Q1353330",
        "enwiki_title": "Tarxien Temples",
        "in_snapshot": True,
        "snapshot_description": None,
        "flags": frozenset(),
    }
    values.update(over)
    return M.PlanSite(**values)


@dataclass
class Case:
    """One site's verification inputs; `run()` is `verify_site` over them."""

    site: M.PlanSite
    assembly: M.Assembly
    metas: dict[str, dict[str, Any]]
    texts: dict[str, str]
    quotes: list[str]
    new_raw_data: dict[str, Any] = field(default_factory=dict)

    def run(self) -> tuple[M.Hold, ...]:
        return V.verify_site(
            self.site,
            self.assembly,
            metas=self.metas,
            texts=self.texts,
            quotes=self.quotes,
            new_raw_data=self.new_raw_data,
        )

    def reasons(self) -> set[str]:
        return {hold.reason.value for hold in self.run()}

    def detail(self, reason: str) -> str:
        return " | ".join(h.detail for h in self.run() if h.reason.value == reason)

    def replace(self, **over: Any) -> Case:
        """The same site with the assembly's fields replaced; raw_data follows the assembly."""
        assembly = dataclasses.replace(self.assembly, **over)
        return dataclasses.replace(
            self, assembly=assembly, new_raw_data=new_raw(self.site, assembly)
        )


def new_raw(site: M.PlanSite, assembly: M.Assembly) -> dict[str, Any]:
    """What `write4.new_raw_data` returns by contract (PHASE4_CONTRACTS.md section 5, Track D)."""
    out = dict(site.raw_data or {})
    out[M.CITATIONS_KEY] = [citation.to_dict() for citation in assembly.citations]
    out[M.PROVENANCE_KEY] = assembly.provenance.to_dict()
    return out


def make_case(
    *,
    lane: str = "W",
    text: str = TEXT,
    picks: tuple[Pick, ...] = W_PICKS,
    card: str | None = CARD,
    card_items: tuple[tuple[int, tuple[str, ...]], ...] = ((0, (A1,)),),
    site: M.PlanSite | None = None,
    subject_gate: M.SubjectGate | None = None,
) -> Case:
    """A clean lane-W or lane-S site (lane S: the W source under a 'shared' verdict)."""
    site = site or plan_site()
    verdict = gate("shared" if lane == "S" else "own")
    meta = wiki_meta(
        "W",
        text,
        lang="en",
        title="Tarxien Temples",
        revid=1234567,
        subject_gate=subject_gate or verdict,
    )
    sentences = []
    for pick in picks:
        start, end = locate(text, pick.sentence)
        drop = tuple(sorted(piece_range(text, pick.sentence, d) for d in pick.drops))
        sentences.append(M.PublishedSentence(n=1, src="W", start=start, end=end, drop=drop))
    description = " ".join(with_marker(pick.published, 1) for pick in picks)
    card_record = None
    if card is not None:
        items = tuple(
            M.CardItem(
                sentence=index,
                drop=tuple(sorted(piece_range(text, picks[index].sentence, d) for d in drops)),
            )
            for index, drops in card_items
        )
        card_record = M.Card(items=items, text_sha256=sha(card))
    provenance = M.Provenance(
        run="pilot-20260923",
        lane=M.Lane(lane),
        ai=M.AiMark.SELECTED,
        ai_system=M.AI_SYSTEM,
        licence=M.Licence.CC_BY_SA_4,
        attribution=M.Attribution(
            title="Tarxien Temples",
            url=PERMALINK,
            licence_url=M.PUBLISHED_LICENCE_URL,
            changes=M.Changes.SELECTED_AND_SHORTENED,
        ),
        sources=(
            M.SourceRef(
                id="W",
                url=PERMALINK,
                revid=1234567,
                rev_timestamp="2026-09-01T10:00:00Z",
                text_sha256=sha(text),
                licence=M.Licence.CC_BY_SA_4,
            ),
        ),
        sentences=tuple(sentences),
        card=card_record,
        desc_sha256=sha(description),
    )
    assembly = M.Assembly(
        site_id=site.site_id,
        description=description,
        citations=(
            M.Citation(
                n=1,
                url=PERMALINK,
                title="Wikipedia: Tarxien Temples",
                domain="en.wikipedia.org",
                license=M.Licence.CC_BY_SA_4,
            ),
        ),
        card=card,
        provenance=provenance,
    )
    return Case(
        site=site,
        assembly=assembly,
        metas={"W": meta},
        texts={"W": text},
        quotes=[text[s.start : s.end] for s in sentences],
        new_raw_data=new_raw(site, assembly),
    )


# ------------------------------------------------------------------------------------------------
# Lanes T and R: generated English over a pinned French article or a restricted page
# ------------------------------------------------------------------------------------------------

FR1 = "Le temple de Tarxien fut construit vers 3600 et fouillé en 1915 par Themistocles Zammit."
FR2 = "Les fouilles ont livré des statues, des autels et des reliefs sculptés de spirales."
FR3 = "Le site compte quatre structures mégalithiques reliées par des cours intérieures."
FR_TEXT = f"{FR1} {FR2} {FR3}"
EN1 = "The temple of Tarxien was built around 3600 and excavated in 1915 by Themistocles Zammit."
EN2 = "The excavations yielded statues, altars and carved reliefs of spirals."
EN3 = "The site has four megalithic structures linked by inner courtyards."
FR_PERMALINK = "https://fr.wikipedia.org/w/index.php?title=Temples_de_Tarxien&oldid=7654321"

Q1 = "The Tarxien Temples complex, dated to around 3150 BC, contains four megalithic temples."
Q2 = "Its southern temple preserves altars decorated with running spirals and animal friezes."
Q3 = "The temples were excavated by Themistocles Zammit between 1915 and 1919."
PAGE = f"{Q1} {Q2} Visitors reach the site from Paola on foot. {Q3}"
R1 = "Tarxien holds four megalithic temples that were built around 3150 BC."
R2 = "Altars in the southern temple carry carved spirals and friezes of animals."
R3 = "Themistocles Zammit led the digging of the temples from 1915 until 1919."
R_URL = "https://www.heritagemalta.mt/explore/tarxien-temples/"


def make_generated_case(lane: str) -> Case:
    """A clean lane-T (French article, translated) or lane-R (restricted page, restated) site."""
    site = plan_site()
    if lane == "T":
        source_id, text, quotes, published = "T.fr", FR_TEXT, (FR1, FR2, FR3), (EN1, EN2, EN3)
        meta = wiki_meta(source_id, text, lang="fr", title="Temples de Tarxien", revid=7654321)
        url, title, citation_title = (
            FR_PERMALINK,
            "Temples de Tarxien",
            "Wikipedia: Temples de Tarxien",
        )
        licence, revid, stamp = M.Licence.CC_BY_SA_4, 7654321, "2026-09-01T10:00:00Z"
        changes = M.Changes.TRANSLATED
    else:
        source_id, text, quotes, published = "R1", PAGE, (Q1, Q2, Q3), (R1, R2, R3)
        meta = M.SourceDoc(
            id="R1",
            url=R_URL,
            permalink=None,
            title="Tarxien Temples - Heritage Malta",
            pageid=None,
            revid=None,
            lastrevid=None,
            rev_timestamp=None,
            retrieved_at="2026-09-23T08:00:00Z",
            sha256_raw=HEX_RAW,
            sha256_text=sha(text),
            licence=M.Licence.RESTRICTED,
            route=M.Route.MINIMAX,
            subject_gate=None,
            tdm=M.Tdm(checked=True, reserved=False, signal=None),
            final_url=R_URL,
            truncated=False,
        ).to_dict()
        url, title = R_URL, "Tarxien Temples - Heritage Malta"
        citation_title = title
        licence, revid, stamp = M.Licence.RESTRICTED, None, None
        changes = M.Changes.FACTS_RESTATED
    sentences = tuple(
        M.PublishedSentence(n=1, src=source_id, start=a, end=b, drop=())
        for a, b in (locate(text, quote) for quote in quotes)
    )
    description = " ".join(with_marker(p, 1) for p in published)
    provenance = M.Provenance(
        run="pilot-20260923",
        lane=M.Lane(lane),
        ai=M.AiMark.GENERATED,
        ai_system=M.AI_SYSTEM,
        licence=M.PUBLISHED_LICENCE,
        attribution=M.Attribution(
            title=title, url=url, licence_url=M.PUBLISHED_LICENCE_URL, changes=changes
        ),
        sources=(
            M.SourceRef(
                id=source_id,
                url=url,
                revid=revid,
                rev_timestamp=stamp,
                text_sha256=sha(text),
                licence=licence,
            ),
        ),
        sentences=sentences,
        card=None,
        desc_sha256=sha(description),
    )
    # the host without a leading `www.`: the production form (`api/main.py`'s seeded citations)
    domain = "fr.wikipedia.org" if lane == "T" else "heritagemalta.mt"
    assembly = M.Assembly(
        site_id=site.site_id,
        description=description,
        citations=(M.Citation(n=1, url=url, title=citation_title, domain=domain, license=licence),),
        card=None,
        provenance=provenance,
    )
    return Case(
        site=site,
        assembly=assembly,
        metas={source_id: meta},
        texts={source_id: text},
        quotes=list(quotes),
        new_raw_data=new_raw(site, assembly),
    )


def reprovenance(case: Case, **over: Any) -> Case:
    """The case with provenance fields replaced (desc_sha256 kept honest)."""
    provenance = dataclasses.replace(case.assembly.provenance, **over)
    return case.replace(provenance=provenance)


def republish(case: Case, description: str) -> Case:
    """The case with another published description, its hash kept honest (V13 stays quiet)."""
    provenance = dataclasses.replace(case.assembly.provenance, desc_sha256=sha(description))
    return case.replace(description=description, provenance=provenance)


# ------------------------------------------------------------------------------------------------
# Seams: the card's font measurement, and the two modules of other tracks
# ------------------------------------------------------------------------------------------------

#: A real FreeType face (Pillow's own), at the caption size the short draws.
CAPTION_FACE = ImageFont.load_default(size=shorts_audit.CAPTION_SIZE)
#: What the fake face covers: Basic Latin to Latin Extended-A, as JetBrains Mono does. U+02BF
#: (`Jabal al-ʿHayn`, plan section 7, S4) lies outside it, as it lies outside both brand fonts.
FAKE_CMAP_LAST = 0x017F


def fake_card_fit(name: str, card: str) -> V.CardFit:
    """`card_fit` without the gitignored brand fonts: missing glyphs from a fixed Latin cmap, the
    widest word measured by the real `shorts_audit.widest_word_px` with a real face."""
    shown = f"{name} {card}"
    missing = tuple(sorted({ch for ch in shown if not ch.isspace() and ord(ch) > FAKE_CMAP_LAST}))
    widest, px = shorts_audit.widest_word_px(card.split(), CAPTION_FACE)
    return V.CardFit(missing=missing, widest=widest, px=px)


#: The design's AI aggregators and Wikipedia mirrors (source_store, "DENY LIST").
_AI_AGGREGATORS = ("grokipedia.com", "aroundus.com", "mindtrip.ai", "evendo.com", "wanderlog.com")
_MIRRORS = ("kiddle.co", "wikiwand.com", "dbpedia.org", "alchetron.com", "wiki2.org")


def licences_stand_in() -> types.ModuleType:
    """Track A's `phase4.licences.deny_family` as the contract states it (PHASE4_CONTRACTS.md
    section 5, Track A): an AI aggregator, a Wikipedia mirror or `BLOCKED_DOMAINS`, else None.
    Used only while WB-A2 is not on this branch; once it is, the real module is tested."""
    from urllib.parse import urlsplit

    module = types.ModuleType("phase4.licences")

    def deny_family(url: str) -> str | None:
        if not isinstance(url, str):
            raise TypeError(f"{url!r} is not a URL")
        host = (urlsplit(url).hostname or "").lower()
        if listed_domain_of(host, _AI_AGGREGATORS):
            return "ai-aggregator"
        if listed_domain_of(host, _MIRRORS):
            return "wikipedia-mirror"
        if listed_domain_of(host, BLOCKED_DOMAINS):
            return "blocked"
        return None

    module.deny_family = deny_family  # type: ignore[attr-defined]
    return module


def write4_stand_in() -> types.ModuleType:
    """Track D's `phase4.write4.new_raw_data` as the contract states it; only while WB-D2 is not
    on this branch."""
    module = types.ModuleType("phase4.write4")

    def new_raw_data(old: dict[str, Any] | None, assembly: M.Assembly) -> dict[str, Any]:
        if not isinstance(assembly, M.Assembly):
            raise TypeError(f"{assembly!r} is not an Assembly")
        return new_raw(dataclasses.replace(plan_site(), raw_data=old), assembly)

    module.new_raw_data = new_raw_data  # type: ignore[attr-defined]
    return module


def other_track(monkeypatch: pytest.MonkeyPatch, name: str, stand_in: types.ModuleType) -> None:
    if importlib.util.find_spec(f"phase4.{name}") is None:
        monkeypatch.setitem(sys.modules, f"phase4.{name}", stand_in)
        monkeypatch.setattr(phase4, name, stand_in, raising=False)


HELD_SITE = "0529af31-2222-4222-8222-222222222222"


def write_batch(
    parent: Path, case: Case, *, lane: str = "W", sources: tuple[str, ...] = ("W",)
) -> Path:
    """One batch directory `p4-0001` under `parent` as S0-S4 leave it: the plan's two sites
    (the case's and one held in lane 0), their lanes (the case's with `sources`), the case's
    assembly and every pinned source of the case in the evidence store."""
    batch_dir = parent / "p4-0001"
    batch_dir.mkdir(parents=True)
    held = plan_site(site_id=HELD_SITE, name="Bulls of Guisando")
    batch = Batch(batch_id="p4-0001", ordinal=1, sites=(case.site.to_dict(), held.to_dict()))
    (batch_dir / M.INPUT_FILE).write_text(batch.to_json() + "\n", encoding="utf-8")
    lanes = [
        M.LaneAssignment(site_id=SITE_ID, lane=M.Lane(lane), sources=sources, detail="assigned"),
        M.LaneAssignment(site_id=HELD_SITE, lane=M.Lane.ZERO, sources=(), detail="nothing"),
    ]
    (batch_dir / M.LANES_FILE).write_text(M.dump_jsonl(lanes), encoding="utf-8")
    (batch_dir / M.ASSEMBLY_FILE).write_text(M.dump_jsonl([case.assembly]), encoding="utf-8")
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    for source_id, meta in case.metas.items():
        store.write(
            site_id=SITE_ID,
            feature=M.source_feature(source_id, "meta"),
            body=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
        )
        store.write(
            site_id=SITE_ID,
            feature=M.source_feature(source_id, "txt"),
            body=case.texts[source_id].encode("utf-8"),
        )
    return batch_dir
